"""A write that fails part way through install must leave a state that a rerun of install,
or an uninstall, still undoes completely.

Every file is written whole or not at all, but install writes several files. Review 2 of the
graphify branch found two orders that stranded a change: CLAUDE.md written before the record
named its section (finding 4), and settings.json written before the record named its keys
(finding 5). The tests fail each write in turn instead of naming the two orders.
"""
import json

import pytest

from conftest import load_module

BEFORE_MD = b"mine\n"
BEFORE_SETTINGS = {"autoCompactWindow": 1, "mine": 1}
WRITES = 6   # more than install makes, so the last cases are a run with no failure


@pytest.fixture
def uninstall_module():
    return load_module("uninstall_module", "config/uninstall.py")


def seed(home):
    claude = home / ".claude"
    claude.mkdir(parents=True)
    (claude / "CLAUDE.md").write_bytes(BEFORE_MD)
    (claude / "settings.json").write_text(json.dumps(BEFORE_SETTINGS), encoding="utf-8")


def fail_write(monkeypatch, inst, number):
    """Make the number-th _write_bytes call (from 0) raise as a full disk does."""
    real, calls = inst._write_bytes, []

    def failing(path, data):
        calls.append(path)
        if len(calls) - 1 == number:
            raise OSError(28, "No space left on device")
        real(path, data)
    monkeypatch.setattr(inst, "_write_bytes", failing)
    return real


def assert_undone(home, notices):
    claude = home / ".claude"
    assert (claude / "CLAUDE.md").read_bytes() == BEFORE_MD
    assert json.loads((claude / "settings.json").read_text(encoding="utf-8")) == BEFORE_SETTINGS
    assert sorted(p.name for p in claude.glob("CLAUDE.md.bak-*")) == []
    assert not (claude / "ballast" / "context_check.py").exists()
    # Undoing a write that never happened is not a value the user changed.
    assert not any("not the installed value" in n for n in notices), notices


@pytest.mark.parametrize("number", range(WRITES))
def test_uninstall_right_after_a_failed_install_undoes_it(uninstall_module, tmp_path, monkeypatch, number):
    inst = uninstall_module.install
    home = tmp_path / "home"
    seed(home)
    real = fail_write(monkeypatch, inst, number)
    try:
        inst.install(home, force=True)
    except OSError:
        pass
    monkeypatch.setattr(inst, "_write_bytes", real)
    _, notices = uninstall_module.uninstall(home)
    assert_undone(home, notices)


@pytest.mark.parametrize("number", range(WRITES))
def test_a_rerun_after_a_failed_install_can_still_be_undone(uninstall_module, tmp_path, monkeypatch, number):
    inst = uninstall_module.install
    home = tmp_path / "home"
    seed(home)
    real = fail_write(monkeypatch, inst, number)
    try:
        inst.install(home, force=True)
    except OSError:
        pass
    monkeypatch.setattr(inst, "_write_bytes", real)
    inst.install(home, force=True)
    _, notices = uninstall_module.uninstall(home)
    assert_undone(home, notices)
