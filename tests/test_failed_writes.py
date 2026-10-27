"""A write that fails part way through install must leave a state that a rerun of install,
or an uninstall, still undoes completely.

Every file is written whole or not at all, but install writes several files. Review 2 of the
graphify branch found two orders that stranded a change: CLAUDE.md written before the record
named its section (finding 4), and settings.json written before the record named its keys
(finding 5). Review 3 found that the fix, the record written first, was right only for a
first install: in a run that updates an earlier install, the record written first replaced the
description of what was still on disk (findings 1, 2 and 6). So the tests fail each write in
turn, backup copies included, for every kind of run: a first install, a settings or CLAUDE.md
template change, the move from the whole-file installer, and a hand copy of the rules.
"""
import hashlib
import json

import pytest

from conftest import ROOT, load_module

RULES = (ROOT / "config" / "CLAUDE.md").read_bytes().decode("utf-8").replace("\r\n", "\n")
BEFORE_SETTINGS = {"mine": 1}
OLD_BACKUP = "CLAUDE.md.bak-20250101-000000"
WRITES = 9   # more than install makes, so the last cases are a run with no failure


@pytest.fixture
def uninstall_module():
    return load_module("uninstall_module", "config/uninstall.py")


def claude(home):
    return home / ".claude"


def seed(home, md=b"mine\n"):
    claude(home).mkdir(parents=True)
    (claude(home) / "CLAUDE.md").write_bytes(md)
    (claude(home) / "settings.json").write_text(json.dumps(BEFORE_SETTINGS), encoding="utf-8")


def new_template(inst, tmp_path, monkeypatch, settings=None, md=None):
    """Change the template between two runs, as a git pull does."""
    if settings is not None:
        path = tmp_path / "user-settings.json"
        template = json.loads(inst.USER_SETTINGS.read_text(encoding="utf-8"))
        template.update(settings)
        path.write_text(json.dumps(template), encoding="utf-8")
        monkeypatch.setattr(inst, "USER_SETTINGS", path)
    if md is not None:
        path = tmp_path / "CLAUDE.md"
        path.write_bytes(md.encode("utf-8"))
        monkeypatch.setattr(inst, "CLAUDE_MD", path)


# Each kind of run: prepare the home and the template for the run that will fail, and return
# the CLAUDE.md bytes the uninstall must give back.
def first_install(inst, home, tmp_path, monkeypatch):
    seed(home)
    return b"mine\n"


def settings_template_change(inst, home, tmp_path, monkeypatch):
    seed(home)
    inst.install(home)
    new_template(inst, tmp_path, monkeypatch, settings={"autoCompactWindow": 123456})
    return b"mine\n"


def claude_md_template_change(inst, home, tmp_path, monkeypatch):
    seed(home)
    inst.install(home)
    new_template(inst, tmp_path, monkeypatch, md=RULES + "- a rule added later\n")
    return b"mine\n"


def from_the_whole_file_installer(inst, home, tmp_path, monkeypatch):
    seed(home)
    inst.install(home)
    # What the installer before the marker section left: CLAUDE.md is the rules, the user's
    # file is in a backup, and the record holds the backup name and the whole file's hash.
    (claude(home) / "CLAUDE.md").write_bytes(RULES.encode("utf-8"))
    for name in claude(home).glob("CLAUDE.md.bak-*"):
        name.unlink()
    (claude(home) / OLD_BACKUP).write_bytes(b"mine\n")
    path = claude(home) / "ballast" / "install-record.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["claude_md"] = {"backup": OLD_BACKUP, "sha256": hashlib.sha256(RULES.encode("utf-8")).hexdigest()}
    path.write_text(json.dumps(record), encoding="utf-8")
    return b"mine\n"


def a_hand_copy_of_the_rules(inst, home, tmp_path, monkeypatch):
    before = ("# My notes\n" + RULES + "more of mine\n").encode("utf-8")
    seed(home, before)
    return before


RUNS = [first_install, settings_template_change, claude_md_template_change,
        from_the_whole_file_installer, a_hand_copy_of_the_rules]


def fail_write(monkeypatch, inst, number):
    """Make the number-th file write (from 0) fail as a full disk does. Backups go through the
    same whole-file write (review 3, finding 6: a shutil.copy2 that failed part way left a
    truncated backup). Returns a function that ends the failure."""
    real_write, calls = inst._write_bytes, []

    def failing(path, data):
        calls.append(path)
        if len(calls) - 1 == number:
            raise OSError(28, "No space left on device")
        real_write(path, data)
    monkeypatch.setattr(inst, "_write_bytes", failing)

    def stop():
        monkeypatch.setattr(inst, "_write_bytes", real_write)
    return stop


def assert_undone(home, md, notices):
    assert (claude(home) / "CLAUDE.md").read_bytes() == md
    assert json.loads((claude(home) / "settings.json").read_text(encoding="utf-8")) == BEFORE_SETTINGS
    assert sorted(p.name for p in claude(home).glob("CLAUDE.md.bak-*")) == []
    assert not (claude(home) / "ballast" / "context_check.py").exists()
    # Undoing a write that never happened is not a value or a section the user changed.
    assert not any("not the installed value" in n or "section of CLAUDE.md differs" in n
                   or "no Ideal-Umbrella section" in n
                   for n in notices), notices


def failed_run(inst, home, tmp_path, monkeypatch, run, number):
    md = run(inst, home, tmp_path, monkeypatch)
    stop = fail_write(monkeypatch, inst, number)
    try:
        inst.install(home)
    except OSError:
        pass
    stop()
    return md


@pytest.mark.parametrize("number", range(WRITES))
@pytest.mark.parametrize("run", RUNS)
def test_uninstall_right_after_a_failed_install_undoes_it(uninstall_module, tmp_path, monkeypatch, run, number):
    inst = uninstall_module.install
    home = tmp_path / "home"
    md = failed_run(inst, home, tmp_path, monkeypatch, run, number)
    _, notices = uninstall_module.uninstall(home)
    assert_undone(home, md, notices)


@pytest.mark.parametrize("number", range(WRITES))
@pytest.mark.parametrize("run", RUNS)
def test_a_rerun_after_a_failed_install_finishes_it_and_can_be_undone(uninstall_module, tmp_path, monkeypatch,
                                                                       run, number):
    inst = uninstall_module.install
    home = tmp_path / "home"
    md = failed_run(inst, home, tmp_path, monkeypatch, run, number)
    _, notices = inst.install(home)
    assert not any("had edits" in n or "left unchanged" in n for n in notices), notices
    assert inst.install(home) == ([], [])
    ok, issues, _ = inst.verify(home)
    assert ok, issues
    _, notices = uninstall_module.uninstall(home)
    assert_undone(home, md, notices)
