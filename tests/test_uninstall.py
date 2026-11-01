import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ROOT, load_module, python_314_pathlib, refuse_looks_inside

UNINSTALL = ROOT / "config" / "uninstall.py"
TEMPLATE_MD = (ROOT / "config" / "CLAUDE.md").read_text(encoding="utf-8")


@pytest.fixture
def uninstall_module():
    return load_module("uninstall_module", "config/uninstall.py")


def settings_file(home):
    return home / ".claude" / "settings.json"


def read_settings(home):
    return json.loads(settings_file(home).read_text(encoding="utf-8"))


def whole_file_install(install_module, home, backup):
    """What the installer before the marked section left: CLAUDE.md is the template as a whole
    file, and the record names the backup of the user's earlier file (None: the install
    created CLAUDE.md) with the hash of the whole file."""
    install_module.install(home)
    (home / ".claude" / "CLAUDE.md").write_text(TEMPLATE_MD, encoding="utf-8")
    path = home / ".claude" / "ballast" / "install-record.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["claude_md"] = {"backup": backup, "sha256": install_module.text_hash(TEMPLATE_MD)}
    path.write_text(json.dumps(record), encoding="utf-8")


def seed(home, settings, claude_md=None):
    claude = home / ".claude"
    claude.mkdir(parents=True)
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")
    if claude_md is not None:
        (claude / "CLAUDE.md").write_text(claude_md, encoding="utf-8")


def test_round_trip_restores_what_was_there(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    before = {
        "customKey": "keep-me",
        "autoCompactWindow": 123,
        "permissions": {"allow": ["Bash(ls:*)"], "deny": ["MyTool", "Artifact"]},
        "hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "bash my-own-hook.sh"}]}]},
    }
    seed(home, before, claude_md="my own rules\n")

    install_module.install(home, force=True)
    assert read_settings(home)["autoCompactWindow"] == 250000
    assert (home / ".claude" / "ballast" / "context_check.py").exists()

    changes, notices = uninstall_module.uninstall(home)
    assert changes
    assert notices == []
    assert read_settings(home) == before
    assert (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == "my own rules\n"
    assert not (home / ".claude" / "ballast" / "context_check.py").exists()
    record = json.loads((home / ".claude" / "ballast" / "install-record.json").read_text(encoding="utf-8"))
    assert record == {"uninstalled": True}


def test_fresh_install_round_trip_removes_everything(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    install_module.install(home)
    install_module.install(home)  # a second run must not lose the first run's record

    uninstall_module.uninstall(home)
    # The install created settings.json, so it goes too (review 8, low 44), with no backup.
    assert not settings_file(home).exists()
    assert list((home / ".claude").glob("settings.json.bak-*")) == []
    assert not (home / ".claude" / "CLAUDE.md").exists()


def test_values_changed_after_install_are_kept(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    install_module.install(home)
    settings = read_settings(home)
    settings["autoCompactWindow"] = 300000
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")
    (home / ".claude" / "CLAUDE.md").write_text("edited after install\n", encoding="utf-8")

    _, notices = uninstall_module.uninstall(home)
    after = read_settings(home)
    assert after["autoCompactWindow"] == 300000
    assert "skillListingBudgetFraction" not in after
    assert (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == "edited after install\n"
    assert any("autoCompactWindow" in n for n in notices)
    assert any("CLAUDE.md" in n for n in notices)


def test_sibling_hook_in_same_entry_is_kept(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    seed(home, {"hooks": {"UserPromptSubmit": [{"hooks": [
        {"type": "command", "command": "bash my-own-hook.sh"},
        {"type": "command", "command": "python3 -I old/context_check.py"},
    ]}]}})
    install_module.install(home)
    uninstall_module.uninstall(home)
    assert read_settings(home)["hooks"] == {
        "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "bash my-own-hook.sh"}]}]
    }


def test_without_record_leaves_deny_alone(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    install_module.install(home)
    (home / ".claude" / "ballast" / "install-record.json").unlink()

    _, notices = uninstall_module.uninstall(home)
    after = read_settings(home)
    assert "autoCompactWindow" not in after
    assert "hooks" not in after
    assert "Artifact" in after["permissions"]["deny"]
    assert not (home / ".claude" / "CLAUDE.md").exists()
    assert any("permissions.deny" in n for n in notices)


@pytest.mark.parametrize("evidence", [False, True])
def test_without_a_record_a_claude_md_of_the_users_is_not_said_to_differ(install_module, uninstall_module, tmp_path,
                                                                         evidence):
    # Review 8, finding L1: with no record nothing says what was installed, yet a CLAUDE.md with
    # no section was reported as differing "from what was installed", even in a home where
    # nothing was ever installed, and after an earlier run had removed the section.
    home = tmp_path / "home"
    seed(home, {"model": "opus"}, "mine\n")
    if evidence:
        install_module.install(home)
        (home / ".claude" / "ballast" / "install-record.json").unlink()
        (home / ".claude" / "CLAUDE.md").write_text("mine, rewritten\n", encoding="utf-8")
    _, notices = uninstall_module.uninstall(home)
    assert not any("what was installed" in n for n in notices), notices
    assert [n for n in notices if "CLAUDE.md" in n] == (
        ["CLAUDE.md has no Ideal-Umbrella section and is not the rules file; left as is"] if evidence else [])
    assert (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == ("mine, rewritten\n" if evidence else "mine\n")


def test_dry_run_writes_nothing(install_module, tmp_path):
    home = tmp_path / "home"
    install_module.install(home)
    claude = home / ".claude"
    snapshot = tree(claude)

    result = subprocess.run(
        [sys.executable, "-I", str(UNINSTALL), "--home", str(home), "--dry-run"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert "Would change:" in result.stdout and "nothing written" in result.stdout
    assert tree(claude) == snapshot


def test_nothing_installed_is_a_no_op(uninstall_module, tmp_path):
    changes, _ = uninstall_module.uninstall(tmp_path / "home")
    assert changes == []


def test_second_uninstall_keeps_the_users_own_values(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    before = {"autoCompactWindow": 250000, "skillListingBudgetFraction": 0.005, "model": "opus"}
    seed(home, before, claude_md=TEMPLATE_MD)

    install_module.install(home)
    uninstall_module.uninstall(home)
    changes, _ = uninstall_module.uninstall(home)
    assert read_settings(home) == before
    assert (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == TEMPLATE_MD
    assert not any("removed" in c or "deleted" in c for c in changes)


def test_without_record_or_hook_nothing_is_removed(uninstall_module, tmp_path):
    home = tmp_path / "home"
    before = {"autoCompactWindow": 250000, "skillListingBudgetFraction": 0.005}
    seed(home, before, claude_md=TEMPLATE_MD)

    uninstall_module.uninstall(home)
    assert read_settings(home) == before
    assert (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == TEMPLATE_MD


def changed_templates(uninstall_module, tmp_path, monkeypatch):
    """Simulate a git pull between install and uninstall."""
    inst = uninstall_module.install
    settings = json.loads(inst.USER_SETTINGS.read_text(encoding="utf-8"))
    settings["autoCompactWindow"] = 300000
    new_settings = tmp_path / "user-settings.json"
    new_settings.write_text(json.dumps(settings), encoding="utf-8")
    new_md = tmp_path / "CLAUDE.md"
    new_md.write_text(TEMPLATE_MD + "- a rule added later\n", encoding="utf-8")
    monkeypatch.setattr(inst, "USER_SETTINGS", new_settings)
    monkeypatch.setattr(inst, "CLAUDE_MD", new_md)


def test_uninstall_after_template_change_undoes_the_install(uninstall_module, tmp_path, monkeypatch):
    home = tmp_path / "home"
    seed(home, {"model": "opus"}, claude_md="my own rules\n")
    uninstall_module.install.install(home)
    changed_templates(uninstall_module, tmp_path, monkeypatch)

    _, notices = uninstall_module.uninstall(home)
    assert read_settings(home) == {"model": "opus"}
    assert (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == "my own rules\n"
    assert notices == []


def test_reinstall_keeps_edits_made_after_the_first_install(uninstall_module, tmp_path, monkeypatch):
    home = tmp_path / "home"
    seed(home, {}, claude_md="mine v1\n")
    inst = uninstall_module.install
    inst.install(home)
    (home / ".claude" / "CLAUDE.md").write_text("mine v2\n", encoding="utf-8")
    settings = read_settings(home)
    settings["autoCompactWindow"] = 100000
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")

    changed_templates(uninstall_module, tmp_path, monkeypatch)
    inst.install(home, force=True)
    uninstall_module.uninstall(home)
    assert (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == "mine v2\n"
    assert read_settings(home) == {"autoCompactWindow": 100000}


def test_symlinks_survive_uninstall(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    dotfiles = tmp_path / "dotfiles"
    dotfiles.mkdir()
    (dotfiles / "settings.json").write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    (dotfiles / "CLAUDE.md").write_text("my own rules\n", encoding="utf-8")
    try:
        settings_file(home).symlink_to(dotfiles / "settings.json")
        (claude / "CLAUDE.md").symlink_to(dotfiles / "CLAUDE.md")
    except OSError:
        pytest.skip("cannot create symlinks here")

    install_module.install(home)
    uninstall_module.uninstall(home)
    assert settings_file(home).is_symlink()
    assert (claude / "CLAUDE.md").is_symlink()
    assert json.loads((dotfiles / "settings.json").read_text(encoding="utf-8")) == {"model": "opus"}
    assert (dotfiles / "CLAUDE.md").read_text(encoding="utf-8") == "my own rules\n"


@pytest.mark.parametrize("backup", ["CLAUDE.md.bak-20250101-000000", None], ids=["restored", "created"])
def test_the_copy_made_before_the_section_is_named_when_the_file_is_restored_or_deleted(
        install_module, uninstall_module, tmp_path, backup):
    # Review 10, finding L3: an upgrade from the whole-file installer after the user rewrote
    # CLAUDE.md, then deleted their text so only the section was left. Uninstall restored the
    # whole-file installer's backup (or deleted the file it had created) and returned before it
    # looked at the copy made before the section was added: that copy stayed, never named.
    home = tmp_path / "home"
    claude = home / ".claude"
    seed(home, {})
    whole_file_install(install_module, home, backup)
    for name in claude.glob("CLAUDE.md.bak-*"):
        name.unlink()
    if backup:
        (claude / backup).write_text("mine\n", encoding="utf-8")
    (claude / "CLAUDE.md").write_text("my notes\n", encoding="utf-8")
    install_module.install(home)
    text = (claude / "CLAUDE.md").read_text(encoding="utf-8")
    (claude / "CLAUDE.md").write_text(text[text.index("<!--"):], encoding="utf-8")

    changes, notices = uninstall_module.uninstall(home)
    if backup:
        assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == "mine\n"
    else:
        assert not (claude / "CLAUDE.md").exists()
    (kept,) = claude.glob("CLAUDE.md.bak-*")
    assert kept.read_text(encoding="utf-8") == "my notes\n"
    assert any(kept.name in n for n in notices), (changes, notices)
    assert uninstall_module.uninstall(home) == ([], [])


def test_the_copy_made_before_the_section_is_deleted_when_the_file_is_restored_to_the_same_bytes(
        install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    claude = home / ".claude"
    seed(home, {})
    whole_file_install(install_module, home, "CLAUDE.md.bak-20250101-000000")
    for name in claude.glob("CLAUDE.md.bak-*"):
        name.unlink()
    (claude / "CLAUDE.md.bak-20250101-000000").write_text("mine\n", encoding="utf-8")
    (claude / "CLAUDE.md").write_text("mine\n", encoding="utf-8")
    install_module.install(home)
    text = (claude / "CLAUDE.md").read_text(encoding="utf-8")
    (claude / "CLAUDE.md").write_text(text[text.index("<!--"):], encoding="utf-8")

    changes, notices = uninstall_module.uninstall(home)
    assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == "mine\n"
    assert not list(claude.glob("CLAUDE.md.bak-*")), (changes, notices)
    assert not any("kept in" in n for n in notices), notices


def a_created_section(install_module, home):
    install_module.install(home)


def a_created_whole_file(install_module, home):
    whole_file_install(install_module, home, None)


def a_section_without_a_record(install_module, home):
    install_module.install(home)
    (home / ".claude" / "ballast" / "install-record.json").unlink()


def a_whole_file_without_a_record(install_module, home):
    install_module.install(home)
    (home / ".claude" / "ballast" / "install-record.json").unlink()
    (home / ".claude" / "CLAUDE.md").write_text(TEMPLATE_MD, encoding="utf-8")


@pytest.mark.parametrize("make", [a_created_section, a_created_whole_file, a_section_without_a_record,
                                  a_whole_file_without_a_record], ids=lambda make: make.__name__)
def test_a_symlinked_claude_md_that_holds_only_the_rules_is_emptied_through_the_link(
        install_module, uninstall_module, tmp_path, make):
    # Review 10, finding L4: the install created CLAUDE.md and the user moved it into dotfiles,
    # linked back. Uninstall deleted the link and left the rules in the dotfiles copy, which the
    # next stow brought back for good. The install writes through such a link; so does uninstall.
    home = tmp_path / "home"
    claude = home / ".claude"
    seed(home, {})
    make(install_module, home)
    dotfiles = tmp_path / "dotfiles"
    dotfiles.mkdir()
    (claude / "CLAUDE.md").replace(dotfiles / "CLAUDE.md")
    installed = (dotfiles / "CLAUDE.md").read_bytes()
    try:
        (claude / "CLAUDE.md").symlink_to(dotfiles / "CLAUDE.md")
    except OSError:
        pytest.skip("cannot create symlinks here")

    changes, notices = uninstall_module.uninstall(home)
    assert (claude / "CLAUDE.md").is_symlink(), (changes, notices)
    assert (dotfiles / "CLAUDE.md").read_bytes() == b"", (changes, notices)
    assert any("CLAUDE.md emptied" in c and "link" in c for c in changes), changes
    # Without a record the file may be the user's own copy, so one is kept, as for a file.
    kept = [b.read_bytes() for b in claude.glob("CLAUDE.md.bak-*")]
    assert kept == ([installed] if "without_a_record" in make.__name__ else []), changes
    assert uninstall_module.uninstall(home)[0] == []


def test_malformed_hook_entry_survives_uninstall(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    seed(home, {"hooks": {"UserPromptSubmit": [{"hooks": ["echo hi"]}]}})
    install_module.install(home)
    uninstall_module.uninstall(home)
    assert read_settings(home)["hooks"] == {"UserPromptSubmit": [{"hooks": ["echo hi"]}]}


def test_non_utf8_claude_md_does_not_block_uninstall(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    install_module.install(home)
    md = home / ".claude" / "CLAUDE.md"
    md.write_bytes("caf\xe9\n".encode("cp1252"))
    ok, issues, _ = install_module.verify(home)
    assert not ok and any("CLAUDE.md" in i for i in issues)

    _, notices = uninstall_module.uninstall(home)
    assert not settings_file(home).exists()   # the install created it
    assert md.read_bytes() == "caf\xe9\n".encode("cp1252")
    assert any("CLAUDE.md" in n for n in notices)


def test_a_non_utf8_claude_md_with_the_section_is_undone_once_the_byte_is_fixed(install_module, uninstall_module,
                                                                                tmp_path):
    # Review 32, M5 (mutant U306): the test above replaces the whole file, so its section is
    # gone and the not-UTF-8 branch is never reached. There the file is left, and so must be
    # its record entry: with the entry dropped, the run after the user fixed the byte said
    # "Nothing to undo." and the section stayed for good.
    home = tmp_path / "home"
    seed(home, {}, claude_md="mine\n")
    md = home / ".claude" / "CLAUDE.md"
    own = md.read_bytes()   # "mine" and the line break the seed wrote (CRLF on Windows)
    install_module.install(home)
    installed = md.read_bytes()
    md.write_bytes(b"caf\xe9\n" + installed)   # a Latin-1 byte the user typed
    _, notices = uninstall_module.uninstall(home)
    assert "CLAUDE.md is not UTF-8; left as is with its Ideal-Umbrella section" in notices, notices
    assert md.read_bytes() == b"caf\xe9\n" + installed

    md.write_bytes(b"cafe\n" + installed)      # fixed; the uninstall is run again
    changes, notices = uninstall_module.uninstall(home)
    assert "CLAUDE.md: Ideal-Umbrella section removed" in changes, (changes, notices)
    assert md.read_bytes() == b"cafe\n" + own


def test_reinstall_updates_a_value_an_earlier_install_wrote(uninstall_module, tmp_path, monkeypatch):
    home = tmp_path / "home"
    seed(home, {"model": "opus"})
    inst = uninstall_module.install
    inst.install(home)
    changed_templates(uninstall_module, tmp_path, monkeypatch)

    changes, _ = inst.install(home)
    assert any("template changed" in change for change in changes)
    assert read_settings(home)["autoCompactWindow"] == 300000
    ok, issues, warnings = inst.verify(home)
    assert ok, issues
    assert warnings == []
    uninstall_module.uninstall(home)
    assert read_settings(home) == {"model": "opus"}


def test_reinstall_keeps_a_value_the_user_set_after_install(uninstall_module, tmp_path, monkeypatch):
    home = tmp_path / "home"
    seed(home, {})
    inst = uninstall_module.install
    inst.install(home)
    settings = read_settings(home)
    settings["autoCompactWindow"] = 100000
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")
    changed_templates(uninstall_module, tmp_path, monkeypatch)

    _, notices = inst.install(home)
    assert any("autoCompactWindow" in notice for notice in notices)
    assert read_settings(home)["autoCompactWindow"] == 100000


def test_missing_claude_md_backup_keeps_the_file(install_module, uninstall_module, tmp_path):
    # The whole-file install replaced the user's CLAUDE.md and recorded the backup name. If that
    # backup is gone, deleting the installed file would leave the user with nothing: keep it
    # and say so. (tests/test_claude_md_section.py has the same case after the migration.)
    home = tmp_path / "home"
    name = "CLAUDE.md.bak-20250101-000000"
    whole_file_install(install_module, home, name)
    claude = home / ".claude"

    changes, notices = uninstall_module.uninstall(home)
    assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == TEMPLATE_MD
    assert not any("CLAUDE.md deleted" in change for change in changes)
    assert any("CLAUDE.md left as is" in notice and name in notice for notice in notices)
    record = json.loads((claude / "ballast" / "install-record.json").read_text(encoding="utf-8"))
    assert record["uninstalled"] is True
    assert record["claude_md"]["backup"] == name


def test_unreadable_record_is_not_overwritten(install_module, uninstall_module, tmp_path, capsys):
    home = tmp_path / "home"
    install_module.install(home)
    record = home / ".claude" / "ballast" / "install-record.json"
    record.write_text("{broken", encoding="utf-8")
    settings_before = settings_file(home).read_text(encoding="utf-8")

    assert uninstall_module.main(["--home", str(home)]) == 1
    err = capsys.readouterr().err
    assert "not valid JSON" in err and "nothing written" in err
    assert record.read_text(encoding="utf-8") == "{broken"
    assert settings_file(home).read_text(encoding="utf-8") == settings_before
    assert (home / ".claude" / "ballast" / "context_check.py").exists()


@pytest.mark.parametrize("run", ["install", "uninstall"])
def test_a_record_saved_with_a_bom_is_read(install_module, uninstall_module, tmp_path, capsys, run):
    # Review 20, finding B1: an editor that saves UTF-8 with a BOM (Notepad before 2019,
    # PowerShell 5) made both runs stop, and the error advised deleting the record, which
    # holds what uninstall puts back. Review 21, I1: the record's contents must be used, not
    # taken for no record.
    home = tmp_path / "home"
    settings_file(home).parent.mkdir(parents=True)
    settings_file(home).write_text('{"autoCompactWindow": 100000}', encoding="utf-8")
    install_module.install(home, force=True)
    record = home / ".claude" / "ballast" / "install-record.json"
    record.write_bytes(b"\xef\xbb\xbf" + record.read_bytes())
    module = install_module if run == "install" else uninstall_module
    assert module.main(["--home", str(home)]) == 0, capsys.readouterr().err
    if run == "install":
        assert json.loads(record.read_text(encoding="utf-8-sig"))["replaced"] == {"autoCompactWindow": 100000}
    else:
        assert not (home / ".claude" / "ballast" / "context_check.py").exists()
        assert json.loads(settings_file(home).read_text(encoding="utf-8")) == {"autoCompactWindow": 100000}


def test_a_record_saved_as_utf16_is_said_to_be_not_utf8(install_module, uninstall_module, tmp_path, capsys):
    # Review 21, finding L2: PowerShell 5's `>` and Out-File save UTF-16; the record was called
    # "not valid JSON" while settings.json in the same state is called "not UTF-8".
    home = tmp_path / "home"
    install_module.install(home)
    record = home / ".claude" / "ballast" / "install-record.json"
    record.write_bytes(record.read_text(encoding="utf-8").encode("utf-16"))
    for module in (install_module, uninstall_module):
        assert module.main(["--home", str(home)]) == 1
        err = capsys.readouterr().err
        assert "is not UTF-8" in err and install_module.RECORD_KEPT in err and "not valid JSON" not in err, err
        assert "delete it" not in err, err


@pytest.mark.parametrize("record_kind", ["current", "before-installed"])
def test_a_key_deleted_by_hand_after_a_forced_install_stays_deleted(install_module, uninstall_module, tmp_path,
                                                                   record_kind):
    # Review 21, finding L1: the second install added the key again, but the record kept the
    # first install's value as the one to put back, so uninstall brought back a value the
    # user had deleted. Review 22, I2: a record from before "installed" existed too.
    home = tmp_path / "home"
    settings_file(home).parent.mkdir(parents=True)
    settings_file(home).write_text('{"autoCompactWindow": 100000, "mine": 1}', encoding="utf-8")
    install_module.install(home, force=True)
    if record_kind == "before-installed":
        record_path = home / ".claude" / "ballast" / "install-record.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        del record["installed"]
        record_path.write_text(json.dumps(record), encoding="utf-8")
    settings = json.loads(settings_file(home).read_text(encoding="utf-8"))
    del settings["autoCompactWindow"]
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")
    install_module.install(home)
    uninstall_module.uninstall(home)
    assert json.loads(settings_file(home).read_text(encoding="utf-8")) == {"mine": 1}


def test_a_value_changed_after_a_forced_install_is_named_and_the_settings_backup_too(install_module,
                                                                                    uninstall_module, tmp_path):
    # Review 32, L3: a value the install replaced, then changed by the user, is neither the
    # installed value nor the one from before; it was left with no note (mutant U98, which took
    # it for a value the install never wrote). Mutant U543 lost the line naming the backup.
    home = tmp_path / "home"
    seed(home, {"autoCompactWindow": 1000})
    install_module.install(home, force=True)
    settings = read_settings(home)
    settings["autoCompactWindow"] = 2000
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")
    changes, notices = uninstall_module.uninstall(home)
    assert "autoCompactWindow is 2000, not the installed value; left as is" in notices, notices
    assert read_settings(home)["autoCompactWindow"] == 2000
    (named,) = [c[len("settings backup: "):] for c in changes if c.startswith("settings backup: ")]
    assert named.startswith("settings.json.bak-") and (home / ".claude" / named).is_file(), changes


def test_a_pending_record_naming_a_key_the_user_deleted_is_no_traceback(install_module, uninstall_module, tmp_path,
                                                                        capsys):
    # Review 32, L2 (mutant I609, the uninstall side): a record still holding "pending" (an
    # install stopped by a failed write) whose earlier "installed" names a key no longer in
    # settings.json stopped uninstall with a KeyError.
    home = tmp_path / "home"
    install_module.install(home)
    path = home / ".claude" / "ballast" / "install-record.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["pending"] = {k: v for k, v in record.items() if k != "claude_md"}
    path.write_text(json.dumps(record), encoding="utf-8")
    settings = read_settings(home)
    del settings["autoCompactWindow"]
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")
    assert uninstall_module.main(["--home", str(home)]) == 0, capsys.readouterr().err
    assert not settings_file(home).exists()   # the install created it
    assert not (home / ".claude" / "ballast" / "context_check.py").exists()


@pytest.mark.parametrize("content", ["{broken", "[1]", '{"added_keys": 5}', '{"a": "\\ud800"}',
                                     pytest.param("[" * 100000, id="deep")])
def test_the_error_for_a_bad_record_does_not_advise_deleting_it(install_module, uninstall_module, tmp_path, capsys,
                                                               content):
    # Review 20, finding B1: deleting the record loses the values uninstall puts back.
    home = tmp_path / "home"
    install_module.install(home)
    (home / ".claude" / "ballast" / "install-record.json").write_text(content, encoding="utf-8")
    for module in (install_module, uninstall_module):
        assert module.main(["--home", str(home)]) == 1
        err = capsys.readouterr().err
        assert install_module.RECORD_ADVICE in err and "delete it" not in err, err


def test_an_os_error_before_any_step_does_not_say_part_way(install_module, uninstall_module, tmp_path, capsys):
    # Review 4, info E2: settings.json replaced by a folder fails the first read, and the
    # message said the undo stopped part way although nothing was done. Review 23: it is the
    # read error, which says nothing was written.
    home = tmp_path / "home"
    install_module.install(home)
    settings_file(home).unlink()
    settings_file(home).mkdir()

    assert uninstall_module.main(["--home", str(home)]) == 1
    err = capsys.readouterr().err
    assert err.startswith("Error: cannot read") and "nothing written" in err
    assert "part way" not in err and "Done before the error" not in err


def test_os_error_mid_undo_is_reported_not_raised(install_module, uninstall_module, tmp_path, capsys):
    # The hook path replaced by a folder: unlink() raises after settings.json was already
    # undone. The message says so; a second run after removing the folder finishes the undo.
    home = tmp_path / "home"
    seed(home, {"model": "opus"})
    install_module.install(home)
    hook = home / ".claude" / "ballast" / "context_check.py"
    hook.unlink()
    hook.mkdir()

    assert uninstall_module.main(["--home", str(home)]) == 1
    err = capsys.readouterr().err
    assert err.startswith("Error:") and "run again" in err
    assert "Traceback" not in err and "nothing written" not in err
    # Review 32, L3 (mutant U545): what was done before the error includes the settings write.
    done = err[err.index("Done before the error:"):].splitlines()
    assert "  - settings.json written" in done and any(d.startswith("  - settings backup: ") for d in done), err
    assert read_settings(home) == {"model": "opus"}

    hook.rmdir()
    assert uninstall_module.main(["--home", str(home)]) == 0
    assert not (home / ".claude" / "ballast" / "context_check.py").exists()
    record = json.loads((home / ".claude" / "ballast" / "install-record.json").read_text(encoding="utf-8"))
    assert record == {"uninstalled": True}


def test_record_without_claude_md_entry_keeps_the_file_and_says_so(install_module, uninstall_module, tmp_path):
    # A record without a claude_md entry means the install never wrote CLAUDE.md (it already
    # held the section, added by hand), so the section is the user's own. It used to be passed
    # over in silence; now the uninstall says why it stays.
    home = tmp_path / "home"
    by_hand = "mine\n\n" + install_module.section_text(TEMPLATE_MD)
    seed(home, {}, claude_md=by_hand)
    install_module.install(home)
    assert "claude_md" not in json.loads(
        (home / ".claude" / "ballast" / "install-record.json").read_text(encoding="utf-8"))

    changes, notices = uninstall_module.uninstall(home)
    assert not any("CLAUDE.md" in c for c in changes), changes
    # Review 32, L3 (mutant U443): both notes end "not written by this install"; this one says
    # the rules match.
    assert "CLAUDE.md's Ideal-Umbrella section matches the template but was not written by this install; " \
           "left as is" in notices, notices
    assert (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == by_hand


def test_a_section_the_install_did_not_write_whose_rules_differ_is_said_to_differ(install_module, uninstall_module,
                                                                                  tmp_path):
    # Review 32, L3 (mutant U443): a record that names no CLAUDE.md change, and a section whose
    # rules are not config/CLAUDE.md's, got the note that the section matches the template.
    home = tmp_path / "home"
    seed(home, {}, claude_md="my rules\n")
    install_module.install(home)
    md = home / ".claude" / "CLAUDE.md"
    text = md.read_text(encoding="utf-8").replace("Keep decisions in files", "Keep MY decisions in files")
    md.write_text(text, encoding="utf-8")
    path = home / ".claude" / "ballast" / "install-record.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["claude_md"] = None
    path.write_text(json.dumps(record), encoding="utf-8")
    _, notices = uninstall_module.uninstall(home)
    assert [n for n in notices if "CLAUDE.md" in n] == [
        "the Ideal-Umbrella section of CLAUDE.md differs from config/CLAUDE.md and was not written by this "
        "install; left as is"], notices
    assert md.read_text(encoding="utf-8") == text


def test_non_string_backup_name_in_record_does_not_crash(install_module, uninstall_module, tmp_path):
    # Review 8, low 27 (old #18): a backup name backup_of rejects was read as "no backup", so
    # CLAUDE.md was deleted. The record names a backup, so the file is left as is.
    home = tmp_path / "home"
    whole_file_install(install_module, home, 1)

    changes, notices = uninstall_module.uninstall(home)
    assert not any(c.startswith("CLAUDE.md") for c in changes), (changes, notices)
    assert (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == TEMPLATE_MD
    assert "CLAUDE.md left as is: the backup 1 the install record names is not usable" in notices, notices


def test_deny_that_is_not_a_list_is_reported_and_kept_in_the_record(install_module, uninstall_module, tmp_path):
    # The deny undo was gated on isinstance(list) with no else: a string deny was skipped in
    # silence and deny_added dropped from the record, so the tools could never be removed.
    home = tmp_path / "home"
    install_module.install(home)
    settings = read_settings(home)
    settings["permissions"]["deny"] = ",".join(settings["permissions"]["deny"])
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")
    changes, notices = uninstall_module.uninstall(home)
    assert any("permissions.deny" in n and "not a list" in n for n in notices), notices
    record = json.loads((home / ".claude" / "ballast" / "install-record.json").read_text(encoding="utf-8"))
    assert record["deny_added"] == list(install_module.REQUIRED_TOOLS)

    settings = read_settings(home)
    settings["permissions"]["deny"] = settings["permissions"]["deny"].split(",")
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")
    changes, notices = uninstall_module.uninstall(home)
    assert any(c.startswith("permissions.deny: removed") for c in changes), changes
    # The install created settings.json, and the second run left it empty: it is deleted.
    assert not settings_file(home).exists()


def test_a_failed_section_removal_never_leaves_a_truncated_claude_md(install_module, uninstall_module, tmp_path, monkeypatch):
    # The file is written to a temp file and renamed over CLAUDE.md; a failed rename keeps the
    # old file whole. (The legacy-backup restore: tests/test_claude_md_section.py.)
    home = tmp_path / "home"
    seed(home, {}, claude_md="my own rules\n")
    install_module.install(home)
    claude_md = home / ".claude" / "CLAUDE.md"
    installed = claude_md.read_text(encoding="utf-8")
    real_replace = os.replace

    def failing_replace(src, dst, *args, **kwargs):
        if str(dst).endswith("CLAUDE.md"):
            raise OSError(28, "No space left on device")
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "replace", failing_replace)
    with pytest.raises(OSError):
        uninstall_module.uninstall(home)
    assert claude_md.read_text(encoding="utf-8") == installed
    assert list((home / ".claude").glob("CLAUDE.md.bak-*"))


@pytest.mark.parametrize("own, kept", [("mine", "mine\n"), ("first\r\nmine", "first\r\nmine\r\n")],
                         ids=["lf", "crlf"])
def test_a_deleted_blank_line_above_the_section_costs_none_of_the_users_text(install_module, uninstall_module,
                                                                             tmp_path, own, kept):
    # Review 32, M1 (mutant U188): a file with no final line break gets two before the section,
    # and the record says so. The user deleted the blank line, so one is left: it is taken, and
    # the cut stops at the user's own text, not one character into it ("min").
    home = tmp_path / "home"
    seed(home, {})
    md = home / ".claude" / "CLAUDE.md"
    md.write_bytes(own.encode("utf-8"))
    install_module.install(home)
    text = md.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in own else "\n"
    assert text.startswith(own + newline * 2 + "<!--"), text[:40]
    md.write_bytes((own + newline + text[len(own + newline * 2):]).encode("utf-8"))
    changes, notices = uninstall_module.uninstall(home)
    assert "CLAUDE.md: Ideal-Umbrella section removed" in changes, (changes, notices)
    assert md.read_bytes() == kept.encode("utf-8")


@pytest.mark.parametrize("own", ["mine\n", "first\r\nmine\r\n"], ids=["lf", "crlf"])
def test_a_deleted_blank_line_above_the_section_keeps_the_users_final_line_break(install_module, uninstall_module,
                                                                                 tmp_path, own):
    # Review 32: a file ending in a line break gets one more before the section. With the blank
    # line deleted, the break left is the user's own, so uninstall keeps it ("mine\n", not "mine").
    home = tmp_path / "home"
    seed(home, {})
    md = home / ".claude" / "CLAUDE.md"
    md.write_bytes(own.encode("utf-8"))
    install_module.install(home)
    text = md.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in own else "\n"
    assert text.startswith(own + newline + "<!--"), text[:40]
    md.write_bytes((own + text[len(own + newline):]).encode("utf-8"))
    changes, notices = uninstall_module.uninstall(home)
    assert "CLAUDE.md: Ideal-Umbrella section removed" in changes, (changes, notices)
    assert md.read_bytes() == own.encode("utf-8")


@pytest.mark.parametrize("own", [b"mine\rmore\r", b"mine", b"first\r\nmine", b"a\r\nb\r", b"a\nb\r\n"],
                         ids=["cr", "lf", "crlf", "crlf-then-cr", "lf-then-crlf"])
def test_a_file_ending_in_a_bare_cr_is_given_back_byte_for_byte(install_module, uninstall_module, tmp_path, own):
    # Review 33: classic Mac line ends. The text has no final LF, so install puts two LF before
    # the section; counting them back as line breaks read the user's last CR and the first LF
    # as one CRLF and took the CR too. Review 34 (T1): the separator as recorded is taken whole,
    # also when it is two CRLF, and a CRLF one is a CRLF in a file that also has a bare LF.
    home = tmp_path / "home"
    seed(home, {})
    md = home / ".claude" / "CLAUDE.md"
    md.write_bytes(own)
    install_module.install(home)
    changes, notices = uninstall_module.uninstall(home)
    assert "CLAUDE.md: Ideal-Umbrella section removed" in changes, (changes, notices)
    assert md.read_bytes() == own
    assert not list((home / ".claude").glob("CLAUDE.md.bak-*")), notices


@pytest.mark.parametrize("own", [b"rules\nmine\n\r", b"mine\n\n\r"], ids=["lf-cr", "blank-cr"])
def test_a_deleted_blank_line_after_a_bare_cr_costs_none_of_the_users_text(install_module, uninstall_module,
                                                                           tmp_path, own):
    # Review 34, L1: a text with LF line ends that ends in a bare CR gets two LF before the
    # section. With the blank line deleted, the user's CR and the LF left read as one CRLF, so
    # the count took them and then the user's own LF. The file never had a CRLF, so a CR before
    # an LF is the user's: one LF of the installer's stays, as for "mine" above.
    home = tmp_path / "home"
    seed(home, {})
    md = home / ".claude" / "CLAUDE.md"
    md.write_bytes(own)
    install_module.install(home)
    data = md.read_bytes()
    assert data.startswith(own + b"\n\n<!--"), data[:40]
    md.write_bytes(own + b"\n" + data[len(own) + 2:])
    changes, notices = uninstall_module.uninstall(home)
    assert "CLAUDE.md: Ideal-Umbrella section removed" in changes, (changes, notices)
    assert md.read_bytes() == own + b"\n"


def _to_crlf(data):
    return data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


@pytest.mark.parametrize("own, kept", [(b"mine", b"note\nmine"), (b"a\nb\n", b"note\na\r\nb\r\n")],
                         ids=["no-final-break", "final-break"])
def test_a_line_added_with_lf_above_a_file_turned_to_crlf_leaves_no_separator(install_module, uninstall_module,
                                                                               tmp_path, own, kept):
    # Review 35, L1: the file was turned to CRLF after the install, then a line was added at the
    # top with an LF tool. That one bare LF made each CRLF of the separator read as two breaks,
    # and the installer's blank line stayed. Any other CRLF above means the file was converted.
    home = tmp_path / "home"
    seed(home, {})
    md = home / ".claude" / "CLAUDE.md"
    md.write_bytes(own)
    install_module.install(home)
    md.write_bytes(b"note\n" + _to_crlf(md.read_bytes()))
    changes, notices = uninstall_module.uninstall(home)
    assert "CLAUDE.md: Ideal-Umbrella section removed" in changes, (changes, notices)
    assert md.read_bytes() == kept


@pytest.mark.parametrize("own, kept", [(b"a", b"a\r\n"), (b"x\ny", b"x\r\ny\r\n")], ids=["one-line", "two-lines"])
def test_a_blank_lf_line_above_the_section_of_a_crlf_file_splits_no_crlf(install_module, uninstall_module,
                                                                         tmp_path, own, kept):
    # Review 35, L2: after a CRLF conversion, a blank line added with an LF tool just above the
    # section leaves "\r\n\r\n\n". Its tail is the recorded "\n\n", and cutting those bytes split
    # a CRLF and left a bare CR. The breaks are counted instead, so no bare CR is written.
    home = tmp_path / "home"
    seed(home, {})
    md = home / ".claude" / "CLAUDE.md"
    md.write_bytes(own)
    install_module.install(home)
    data = _to_crlf(md.read_bytes())
    at = data.index(b"<!--")
    md.write_bytes(data[:at] + b"\n" + data[at:])
    changes, notices = uninstall_module.uninstall(home)
    assert "CLAUDE.md: Ideal-Umbrella section removed" in changes, (changes, notices)
    assert md.read_bytes() == kept


def test_a_crlf_separator_goes_when_the_lines_above_it_were_rewritten_with_lf(install_module, uninstall_module,
                                                                             tmp_path):
    # Review 35 (mutant f8): install wrote its blank line as CRLF, the file's line end. The user's
    # line above was then rewritten with an LF tool: the CRLF is still one break, not two.
    home = tmp_path / "home"
    seed(home, {})
    md = home / ".claude" / "CLAUDE.md"
    md.write_bytes(b"a\r\n")
    install_module.install(home)
    data = md.read_bytes()
    assert data.startswith(b"a\r\n\r\n<!--"), data[:40]
    md.write_bytes(b"note\n" + data[len(b"a\r\n"):])
    changes, notices = uninstall_module.uninstall(home)
    assert "CLAUDE.md: Ideal-Umbrella section removed" in changes, (changes, notices)
    assert md.read_bytes() == b"note\n"


# Review 37, T1: the last three pin each term of the check that the CR is the text's own: a blank
# line then a CR (only "\r\n\n", not "\n\n", is excluded), two CRs, and an LF then a CR.
@pytest.mark.parametrize("own", [b"mine\rmore\r", b"a\nb\r", b"a\n\n\r", b"a\r\r", b"a\n\r"],
                         ids=["cr-only", "lf-cr", "blank-cr", "cr-cr", "lf-only-cr"])
def test_a_crlf_line_added_above_a_text_ending_in_a_bare_cr_keeps_that_cr(install_module, uninstall_module,
                                                                          tmp_path, own):
    # Review 36, L1: a text ending in a bare CR gets two LF before the section. A line added at
    # the top with CRLF put a CRLF above, which read as a CRLF conversion: the user's CR and the
    # first LF were cut as one CRLF. The file was not converted, so both LF go and the CR stays.
    home = tmp_path / "home"
    seed(home, {})
    md = home / ".claude" / "CLAUDE.md"
    md.write_bytes(own)
    install_module.install(home)
    assert md.read_bytes().startswith(own + b"\n\n<!--")
    md.write_bytes(b"note\r\n" + md.read_bytes())
    changes, notices = uninstall_module.uninstall(home)
    assert "CLAUDE.md: Ideal-Umbrella section removed" in changes, (changes, notices)
    assert md.read_bytes() == b"note\r\n" + own


def test_a_crlf_line_added_above_and_the_blank_line_deleted_reads_the_crlf_end_as_typed(
        install_module, uninstall_module, tmp_path):
    # Review 40, L1: these bytes have two readings. "a\n\r" installed (two LF recorded), a line
    # added at the top with CRLF and the blank line above the section deleted gives
    # "note\r\na\n\r\n" above it. That is also the text "a" with the same line added, the blank
    # line deleted and a CRLF blank line typed in its place, and uninstall reads it that way (the
    # rule for a CRLF typed into an LF file): "\n\r\n" goes. Keeping it instead would leave the
    # installer's LF in far more files. This test pins that choice so a later change is deliberate.
    home = tmp_path / "home"
    seed(home, {})
    md = home / ".claude" / "CLAUDE.md"
    md.write_bytes(b"a\n\r")
    install_module.install(home)
    data = md.read_bytes()
    at = data.index(b"<!--")
    assert data[:at] == b"a\n\r\n\n"
    md.write_bytes(b"note\r\n" + data[:at - 1] + data[at:])
    changes, notices = uninstall_module.uninstall(home)
    assert "CLAUDE.md: Ideal-Umbrella section removed" in changes, (changes, notices)
    assert md.read_bytes() == b"note\r\na"


def test_a_crlf_text_with_a_crlf_line_added_above_and_the_blank_line_deleted_keeps_its_end(
        install_module, uninstall_module, tmp_path):
    # Review 41, L1: the Review 40 reading is for a text with LF line ends. "a\r\n\r" is written
    # with CRLF (two CRLF recorded), so its last line break and CR are the user's in every reading:
    # with a CRLF line added on top and the blank line deleted, they stay, with one installer CRLF.
    home = tmp_path / "home"
    seed(home, {})
    md = home / ".claude" / "CLAUDE.md"
    md.write_bytes(b"a\r\n\r")
    install_module.install(home)
    data = md.read_bytes()
    at = data.index(b"<!--")
    assert data[:at] == b"a\r\n\r\r\n\r\n"
    md.write_bytes(b"note\r\n" + data[:at - 2] + data[at:])
    changes, notices = uninstall_module.uninstall(home)
    assert "CLAUDE.md: Ideal-Umbrella section removed" in changes, (changes, notices)
    assert md.read_bytes() == b"note\r\na\r\n\r\r\n"


@pytest.mark.parametrize("text, expected", [(b"\r", b"note\r\n"), (b"\n\r", b"note\r\n\n")])
def test_a_text_that_is_only_a_bare_cr_reads_as_blank_lines_under_a_crlf_line_added_above(
        install_module, uninstall_module, tmp_path, text, expected):
    # Review 41, I2: the README's exception to "a line added with CRLF above keeps that CR". With
    # nothing before the CR but line breaks, "note\r\n" + the text + the installer's LF is also
    # "note" followed by CRLF blank lines typed above the section, and is read that way.
    home = tmp_path / "home"
    seed(home, {})
    md = home / ".claude" / "CLAUDE.md"
    md.write_bytes(text)
    install_module.install(home)
    md.write_bytes(b"note\r\n" + md.read_bytes())
    changes, notices = uninstall_module.uninstall(home)
    assert "CLAUDE.md: Ideal-Umbrella section removed" in changes, (changes, notices)
    assert md.read_bytes() == expected


def test_a_text_that_is_only_a_bare_cr_with_the_blank_line_deleted_reads_as_a_crlf_conversion(
        install_module, uninstall_module, tmp_path):
    # Review 42, L2: the README clause for this history. With the blank line above the section
    # also deleted (before or after the line is added), "note\r\n\r\n" is left above it: the
    # same bytes as the text "note" with no final line break, installed with two LF and converted
    # to CRLF (test_line_endings_changed_after_install_leave_no_trace_on_uninstall), and read that
    # way. The CR and the CRLF typed before it go.
    home = tmp_path / "home"
    seed(home, {})
    md = home / ".claude" / "CLAUDE.md"
    md.write_bytes(b"\r")
    install_module.install(home)
    data = md.read_bytes()
    at = data.index(b"<!--")
    assert data[:at] == b"\r\n\n"
    md.write_bytes(b"note\r\n" + data[:at - 1] + data[at:])
    changes, notices = uninstall_module.uninstall(home)
    assert "CLAUDE.md: Ideal-Umbrella section removed" in changes, (changes, notices)
    assert md.read_bytes() == b"note"


@pytest.mark.parametrize("text, expected", [
    (b"a\r\r\nb\r", b"a\r\nb\r\n"),         # no line break before the last CR: the CR stays
    (b"a\r\r\n\r\r", b"a\r\n\r\r\n"),
    (b"a\r\n\r\r\n\r", b"a\n"),             # a line break and the CR: both go
    (b"a\r\r\n\r\n\r", b"a\r\n"),
])
def test_a_cr_cr_lf_text_converted_to_lf_with_the_blank_line_deleted(
        install_module, uninstall_module, tmp_path, text, expected):
    # Review 41, L2: what the README says such a text keeps and loses. The conversion leaves a
    # CRLF where the text had CR CR LF; then the line break before the last CR goes only when
    # there is one, and with none the CR stays, with one of the installer's LF.
    home = tmp_path / "home"
    seed(home, {})
    md = home / ".claude" / "CLAUDE.md"
    md.write_bytes(text)
    install_module.install(home)
    data = md.read_bytes().replace(b"\r\n", b"\n")
    at = data.index(b"<!--")
    assert data[at - 1:at] == b"\n"
    md.write_bytes(data[:at - 1] + data[at:])
    changes, notices = uninstall_module.uninstall(home)
    assert "CLAUDE.md: Ideal-Umbrella section removed" in changes, (changes, notices)
    assert md.read_bytes() == expected


def test_a_crlf_conversion_then_a_deleted_and_an_lf_blank_line_is_read_as_a_bare_cr_text(
        install_module, uninstall_module, tmp_path):
    # Review 37, L1: these bytes have two readings, and no rule gets both right. "x\ny" installed
    # (two LF recorded), the file converted to CRLF, the blank line above the section deleted and
    # an LF blank line added gives "x\r\ny\r\n\n" above the section. That is also the text "y\r"
    # with a line "x" added at the top with CRLF, and uninstall reads it that way: it keeps the
    # CR. This test pins that choice so a later change to it is deliberate.
    home = tmp_path / "home"
    seed(home, {})
    md = home / ".claude" / "CLAUDE.md"
    md.write_bytes(b"x\ny")
    install_module.install(home)
    data = md.read_bytes()
    assert data.startswith(b"x\ny\n\n<!--"), data[:40]
    data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    assert data.startswith(b"x\r\ny\r\n\r\n<!--"), data[:40]
    md.write_bytes(b"x\r\ny\r\n\n" + data[len(b"x\r\ny\r\n\r\n"):])
    changes, notices = uninstall_module.uninstall(home)
    assert "CLAUDE.md: Ideal-Umbrella section removed" in changes, (changes, notices)
    assert md.read_bytes() == b"x\r\ny\r"


@pytest.mark.parametrize("own, top", [(b"a\r\nb\r", b""), (b"one\r\ntwo\r\nthree\r", b""),
                                       (b"a\r\nb\r", b"note\n")], ids=["two-lines", "three-lines", "line-on-top"])
def test_a_crlf_text_ending_in_a_bare_cr_converted_to_lf_keeps_that_cr(install_module, uninstall_module,
                                                                       tmp_path, own, top):
    # Review 38, L1: install writes the separator with CRLF for a text holding a CRLF. A conversion
    # to LF afterwards (dos2unix, git eol=lf) keeps a lone CR, so the text's own final CR is then
    # followed by the installer's two LF. It was cut with them as a CRLF.
    home = tmp_path / "home"
    seed(home, {})
    md = home / ".claude" / "CLAUDE.md"
    md.write_bytes(own)
    install_module.install(home)
    assert md.read_bytes().startswith(own + b"\r\n\r\n<!--")
    md.write_bytes(top + md.read_bytes().replace(b"\r\n", b"\n"))
    changes, notices = uninstall_module.uninstall(home)
    assert "CLAUDE.md: Ideal-Umbrella section removed" in changes, (changes, notices)
    assert md.read_bytes() == top + own.replace(b"\r\n", b"\n")


@pytest.mark.parametrize("own, top", [(b"a\r\n\r", b""), (b"a\r\nb\r\n\r", b""),
                                       (b"one\r\ntwo\r\nthree\r\n\r", b"note\n")],
                         ids=["one-line", "two-lines", "line-on-top"])
def test_a_crlf_text_ending_in_a_break_and_a_bare_cr_converted_to_lf_keeps_them_without_the_blank_line(
        install_module, uninstall_module, tmp_path, own, top):
    # Review 39, L1: as above, but the blank line above the section was then deleted. The text's
    # line break and CR were cut with the installer's one LF left. Only a CRLF install of a text
    # without a final line break can end in a CR, so the last CRLF is read as that CR and the
    # installer's LF; the installer's other LF may stay, but none of the text goes.
    home = tmp_path / "home"
    seed(home, {})
    md = home / ".claude" / "CLAUDE.md"
    md.write_bytes(own)
    install_module.install(home)
    assert md.read_bytes().startswith(own + b"\r\n\r\n<!--")
    data = md.read_bytes().replace(b"\r\n", b"\n")
    lf = own.replace(b"\r\n", b"\n")
    assert data.startswith(lf + b"\n\n<!--"), data[:40]
    md.write_bytes(top + lf + data[len(lf) + 1:])
    changes, notices = uninstall_module.uninstall(home)
    assert "CLAUDE.md: Ideal-Umbrella section removed" in changes, (changes, notices)
    assert md.read_bytes() == top + lf + b"\n"


def test_a_crlf_blank_line_typed_after_a_conversion_to_lf_keeps_every_line_break(
        install_module, uninstall_module, tmp_path):
    # Review 39, the cost of the rule above: a CRLF blank line typed above the section of a CRLF
    # install converted to LF has the same last bytes as a text's CR and the installer's LF, so
    # nothing above the section is cut. The installer's two LF stay with the user's blank line;
    # no byte of the text is lost.
    home = tmp_path / "home"
    seed(home, {})
    md = home / ".claude" / "CLAUDE.md"
    md.write_bytes(b"a\r\nb")
    install_module.install(home)
    data = md.read_bytes().replace(b"\r\n", b"\n")
    assert data.startswith(b"a\nb\n\n<!--"), data[:40]
    md.write_bytes(b"a\nb\n\n\r\n" + data[len(b"a\nb\n\n"):])
    changes, notices = uninstall_module.uninstall(home)
    assert "CLAUDE.md: Ideal-Umbrella section removed" in changes, (changes, notices)
    assert md.read_bytes() == b"a\nb\n\n\r\n"


def test_a_crlf_file_with_its_blank_line_replaced_by_an_lf_one_keeps_no_installer_cr(
        install_module, uninstall_module, tmp_path):
    # Review 38, T1: the other reading of a CR before two LF with a CRLF separator recorded. The
    # file still holds a CRLF, so it was not converted: the user deleted the installer's blank line
    # and typed one with LF, and the CR is the installer's.
    home = tmp_path / "home"
    seed(home, {})
    md = home / ".claude" / "CLAUDE.md"
    md.write_bytes(b"a\r\nb")
    install_module.install(home)
    data = md.read_bytes()
    assert data.startswith(b"a\r\nb\r\n\r\n<!--"), data[:40]
    md.write_bytes(b"a\r\nb\r\n\n" + data[len(b"a\r\nb\r\n\r\n"):])
    changes, notices = uninstall_module.uninstall(home)
    assert "CLAUDE.md: Ideal-Umbrella section removed" in changes, (changes, notices)
    assert md.read_bytes() == b"a\r\nb"


def test_a_crlf_blank_line_added_after_a_bare_cr_is_not_split(install_module, uninstall_module, tmp_path):
    # Review 36 (mutant j5): a blank line with CRLF, then one with LF, added above the section
    # of a text ending in a bare CR. The text's CR is followed by two LF as above, but the CRLF
    # just before them is the user's blank line: reading its CR as a text's own CR would cut
    # its LF and leave half a CRLF.
    home = tmp_path / "home"
    seed(home, {})
    md = home / ".claude" / "CLAUDE.md"
    md.write_bytes(b"a\r")
    install_module.install(home)
    data = md.read_bytes()
    assert data.startswith(b"a\r\n\n<!--"), data[:40]
    md.write_bytes(b"a\r\n\n\r\n\n" + data[len(b"a\r\n\n"):])
    changes, notices = uninstall_module.uninstall(home)
    assert "CLAUDE.md: Ideal-Umbrella section removed" in changes, (changes, notices)
    result = md.read_bytes()
    assert result.startswith(b"a\r") and b"<!--" not in result and not result.endswith(b"\r"), result


@pytest.mark.parametrize("own, kept", [(b"a\n", b"a\r\n"), (b"x\ny\n", b"x\r\ny\r\n")], ids=["one-line", "two-lines"])
def test_a_deleted_blank_line_then_a_crlf_conversion_keeps_the_users_line_break(install_module, uninstall_module,
                                                                                tmp_path, own, kept):
    # Review 36 (mutant h4): install adds one break after a text ending in one. With it deleted
    # and the file turned to CRLF, the user's own break is the only one left above the section.
    home = tmp_path / "home"
    seed(home, {})
    md = home / ".claude" / "CLAUDE.md"
    md.write_bytes(own)
    install_module.install(home)
    data = md.read_bytes()
    assert data.startswith(own + b"\n<!--"), data[:40]
    md.write_bytes(_to_crlf(own + data[len(own) + 1:]))
    changes, notices = uninstall_module.uninstall(home)
    assert "CLAUDE.md: Ideal-Umbrella section removed" in changes, (changes, notices)
    assert md.read_bytes() == kept


def test_a_joined_that_is_not_text_in_the_record_is_no_traceback(install_module, uninstall_module, tmp_path,
                                                                 capsys):
    # Review 32, L2 (mutant U45): a hand-edited "joined": 5 reached joined.strip() and stopped
    # uninstall with an AttributeError. It is no separator: the section goes, the text above stays.
    home = tmp_path / "home"
    seed(home, {}, claude_md="my rules\n")
    install_module.install(home)
    path = home / ".claude" / "ballast" / "install-record.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["claude_md"]["joined"] = 5
    path.write_text(json.dumps(record), encoding="utf-8")
    assert uninstall_module.main(["--home", str(home)]) == 0, capsys.readouterr().err
    text = (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
    assert text.startswith("my rules\n") and "Ideal-Umbrella" not in text, text


@pytest.mark.parametrize("name", ["../CLAUDE.md.bak", "sub/CLAUDE.md.bak", "../.claude/my-backup.md"])
def test_backup_name_with_a_separator_in_record_does_not_crash(install_module, uninstall_module, tmp_path, name):
    # Path.with_name raised ValueError on such a name after settings.json was already rewritten,
    # and main() then said "nothing written".
    # Review 8, low 27 (old #18): it then deleted CLAUDE.md; the file is left as is now.
    home = tmp_path / "home"
    whole_file_install(install_module, home, name)
    changes, notices = uninstall_module.uninstall(home)
    assert not any(c.startswith("CLAUDE.md") for c in changes), (changes, notices)
    assert (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == TEMPLATE_MD
    assert f"CLAUDE.md left as is: the backup {name!r} the install record names is not usable" in notices, notices


def test_uninstall_removes_the_state_folder_and_the_log(install_module, uninstall_module, tmp_path):
    # The hook's ballast/state/ folder and context_check.log stayed behind, and neither README
    # nor the docstring named them.
    home = tmp_path / "home"
    install_module.install(home)
    ballast = home / ".claude" / "ballast"
    (ballast / "state").mkdir()
    (ballast / "state" / "session-1").write_text("1", encoding="utf-8")
    (ballast / "context_check.log").write_text("log\n", encoding="utf-8")
    dry, _ = uninstall_module.uninstall(home, dry_run=True)
    assert "state folder deleted" in dry and "log deleted" in dry
    assert (ballast / "state").is_dir() and (ballast / "context_check.log").is_file()
    changes, _ = uninstall_module.uninstall(home)
    assert "state folder deleted" in changes and "log deleted" in changes
    assert not (ballast / "state").exists() and not (ballast / "context_check.log").exists()
    assert (ballast / "install-record.json").is_file()


def test_a_symlinked_state_folder_is_unlinked_not_followed(install_module, uninstall_module, tmp_path):
    # shutil.rmtree refuses a symlink, so the undo stopped after the hook was deleted and every
    # rerun failed at the same place.
    home = tmp_path / "home"
    install_module.install(home)
    ballast = home / ".claude" / "ballast"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "session-1").write_text("1", encoding="utf-8")
    try:
        (ballast / "state").symlink_to(elsewhere, target_is_directory=True)
    except OSError:
        pytest.skip("cannot create symlinks here")
    changes, _ = uninstall_module.uninstall(home)
    assert "state link removed" in changes
    assert not (ballast / "state").is_symlink()
    assert (elsewhere / "session-1").is_file()
    assert json.loads((ballast / "install-record.json").read_text(encoding="utf-8")).get("uninstalled")


@pytest.mark.skipif(os.name != "nt", reason="a junction is a Windows directory link")
def test_a_junctioned_state_folder_is_unlinked_not_followed(install_module, uninstall_module, tmp_path):
    # Path.is_symlink() does not see a junction (the one directory link a Windows user can make
    # without privileges), while shutil.rmtree refuses it, so the undo stopped on it as it had
    # on a symlink.
    home = tmp_path / "home"
    install_module.install(home)
    ballast = home / ".claude" / "ballast"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "session-1").write_text("1", encoding="utf-8")
    made = subprocess.run(["cmd", "/c", "mklink", "/J", str(ballast / "state"), str(elsewhere)],
                          capture_output=True)
    if made.returncode != 0:
        pytest.skip("cannot create a junction here")
    changes, _ = uninstall_module.uninstall(home)
    assert "state link removed" in changes
    assert not os.path.lexists(ballast / "state")
    assert (elsewhere / "session-1").is_file()
    assert json.loads((ballast / "install-record.json").read_text(encoding="utf-8")).get("uninstalled")


def test_empty_containers_the_user_had_before_are_kept(install_module, uninstall_module, tmp_path):
    # permissions, permissions.deny, hooks and hooks.<event> were deleted when the undo left
    # them empty, whether or not the install had created them.
    home = tmp_path / "home"
    before = {"permissions": {"deny": []}, "hooks": {"UserPromptSubmit": []}}
    seed(home, before)
    install_module.install(home)
    uninstall_module.uninstall(home)
    assert read_settings(home) == before


def test_containers_the_install_created_are_removed(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    seed(home, {"customKey": "keep-me"})
    install_module.install(home)
    uninstall_module.uninstall(home)
    assert read_settings(home) == {"customKey": "keep-me"}


def test_reinstall_over_a_record_without_created_still_removes_the_containers(uninstall_module, tmp_path, monkeypatch):
    # A record from before "created" was written says nothing about who made the containers,
    # and a re-install after a pull must not turn that into "the install created nothing".
    home = tmp_path / "home"
    seed(home, {})
    inst = uninstall_module.install
    inst.install(home)
    record_path = home / ".claude" / "ballast" / "install-record.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    del record["created"]
    record_path.write_text(json.dumps(record), encoding="utf-8")

    changed_templates(uninstall_module, tmp_path, monkeypatch)
    inst.install(home)
    assert "created" not in json.loads(record_path.read_text(encoding="utf-8"))
    uninstall_module.uninstall(home)
    assert read_settings(home) == {}


def test_a_second_uninstall_run_still_keeps_the_users_empty_container(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    seed(home, {"hooks": {}})
    install_module.install(home)
    settings = read_settings(home)
    installed_value = settings["autoCompactWindow"]
    settings["autoCompactWindow"] = 1
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")
    uninstall_module.uninstall(home)
    assert read_settings(home) == {"hooks": {}, "autoCompactWindow": 1}

    settings = read_settings(home)
    settings["autoCompactWindow"] = installed_value
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")
    uninstall_module.uninstall(home)
    assert read_settings(home) == {"hooks": {}}


def test_reinstall_after_a_clean_uninstall_still_knows_what_it_created(install_module, uninstall_module, tmp_path):
    # A clean uninstall leaves the marker record {"uninstalled": true}; a re-install over it
    # must record the containers it creates, or the next uninstall deletes the user's own.
    home = tmp_path / "home"
    seed(home, {"hooks": {}})
    install_module.install(home)
    uninstall_module.uninstall(home)
    assert read_settings(home) == {"hooks": {}}
    install_module.install(home)
    record = json.loads((home / ".claude" / "ballast" / "install-record.json").read_text(encoding="utf-8"))
    assert "permissions" in record["created"] and "hooks" not in record["created"]
    uninstall_module.uninstall(home)
    assert read_settings(home) == {"hooks": {}}


def test_a_container_the_user_adds_between_uninstall_and_reinstall_is_kept(install_module, uninstall_module, tmp_path):
    # The leftover record carries "created"; a re-install must not union a container the
    # first uninstall already deleted and the user then made by hand.
    home = tmp_path / "home"
    seed(home, {"hooks": {}})
    install_module.install(home)
    settings = read_settings(home)
    installed_value = settings["autoCompactWindow"]
    settings["autoCompactWindow"] = 1
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")
    uninstall_module.uninstall(home)
    assert read_settings(home) == {"hooks": {}, "autoCompactWindow": 1}

    settings = read_settings(home)
    settings["permissions"] = {}
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")
    install_module.install(home)
    settings = read_settings(home)
    settings["autoCompactWindow"] = installed_value
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")
    uninstall_module.uninstall(home)
    assert read_settings(home) == {"hooks": {}, "permissions": {}}


@pytest.mark.parametrize("text, message", [
    pytest.param('{"a": ' + "[" * 150 + "]" * 150 + "}", "nested more than", id="deep"),
    pytest.param('{"statusLine": "\\ud800"}', "not valid Unicode", id="surrogate"),
])
def test_settings_that_cannot_be_written_back_stop_the_undo_before_any_write(install_module, uninstall_module, tmp_path, capsys, text, message):
    # Review 2, findings 6 and 7: the undo made its settings backup, then failed to write.
    home = tmp_path / "home"
    install_module.install(home)
    settings_file(home).write_text(text, encoding="utf-8")
    before = sorted(p.name for p in (home / ".claude").rglob("*"))
    assert uninstall_module.main(["--home", str(home)]) == 1
    err = capsys.readouterr().err
    assert message in err and "nothing written" in err and "Traceback" not in err
    assert sorted(p.name for p in (home / ".claude").rglob("*")) == before


@pytest.mark.parametrize("field, value", [("added_keys", None), ("replaced", None), ("installed", ["a"]),
                                          ("deny_added", "Artifact"), ("created", 5)])
def test_a_record_field_of_the_wrong_type_stops_uninstall_with_one_line(install_module, uninstall_module, tmp_path,
                                                                        capsys, field, value):
    # Review 5, finding L5.
    home = tmp_path / "home"
    install_module.install(home)
    path = home / ".claude" / "ballast" / "install-record.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record[field] = value
    path.write_text(json.dumps(record), encoding="utf-8")
    assert uninstall_module.main(["--home", str(home)]) == 1
    err = capsys.readouterr().err
    assert "Traceback" not in err and "nothing written" in err and field in err


def link_or_skip(link, target, target_is_directory=False):
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except OSError:
        pytest.skip("cannot create symlinks here")


def a_section_install(install_module, home):
    """The safety backup holds "my own notes" and CLAUDE.md is linked to it."""
    (home / ".claude" / "CLAUDE.md").write_text("my own notes\n", encoding="utf-8")
    install_module.install(home)
    (backup,) = (home / ".claude").glob("CLAUDE.md.bak-*")
    return backup


def a_whole_file_record(install_module, home):
    whole_file_install(install_module, home, "CLAUDE.md.bak-20250101-000000")
    for name in (home / ".claude").glob("CLAUDE.md.bak-*"):
        name.unlink()
    backup = home / ".claude" / "CLAUDE.md.bak-20250101-000000"
    backup.write_text("my own notes\n", encoding="utf-8")
    return backup


def a_legacy_backup(install_module, home):
    backup = a_whole_file_record(install_module, home)
    install_module.install(home)   # turns the whole file into the section
    return backup


def an_edited_section(install_module, home):
    (home / ".claude" / "CLAUDE.md").write_text("my own notes\n", encoding="utf-8")
    install_module.install(home)
    md = home / ".claude" / "CLAUDE.md"
    text = md.read_text(encoding="utf-8")
    end = text.index("<!-- Ideal-Umbrella rules: end -->")
    edited = home / ".claude" / "CLAUDE.md.bak-20250101-000000"
    edited.write_text(text[:end] + "- my own rule\n" + text[end:], encoding="utf-8")
    path = home / ".claude" / "ballast" / "install-record.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["claude_md"]["edited_backup"] = edited.name
    path.write_text(json.dumps(record), encoding="utf-8")
    return edited


def a_legacy_backup_holding_the_section(install_module, home):
    """The file from before the whole-file install held nothing but the section, so uninstall
    restores it (mutant n17 of review 11)."""
    backup = a_legacy_backup(install_module, home)
    backup.write_bytes((home / ".claude" / "CLAUDE.md").read_bytes())
    return backup


@pytest.mark.parametrize("make", [a_section_install, a_whole_file_record, a_legacy_backup, an_edited_section,
                                  a_legacy_backup_holding_the_section],
                         ids=lambda make: make.__name__)
def test_a_claude_md_linked_to_its_own_backup_keeps_the_backup(install_module, uninstall_module, tmp_path, make):
    # Review 11, finding B3: the user put CLAUDE.md back by linking it to a backup
    # (ln -sf CLAUDE.md.bak-... CLAUDE.md). Uninstall saw the same bytes and deleted the backup,
    # which was the link's target: CLAUDE.md was left dangling and the user's text was gone.
    home = tmp_path / "home"
    seed(home, {})
    backup = make(install_module, home)
    md = home / ".claude" / "CLAUDE.md"
    held = backup.read_bytes()
    md.unlink()
    link_or_skip(md, backup.name)
    changes, notices = uninstall_module.uninstall(home)
    assert backup.is_file() and md.read_bytes() == held, (changes, notices)
    assert not any("deleted" in c and backup.name in c for c in changes), changes
    # Review 14, findings E1 and E3: the backup is the file, so no note names it as a copy to
    # delete, and the documented way back is not reported as a section taken out by hand.
    assert not any(backup.name in n and ("delete" in n or " in " + backup.name in n) for n in notices), notices
    assert not any("no Ideal-Umbrella section" in n for n in notices), notices


@pytest.mark.parametrize("own_text", [True, False], ids=["section-removed", "restored"])
def test_a_folder_named_as_the_legacy_backup_is_no_backup(install_module, uninstall_module, tmp_path, own_text):
    # Review 11, finding B5: the section removal named the folder as "your CLAUDE.md from before
    # the first install is still in ...", and the restore read it and stopped on every run with
    # "Is a directory". Only a file can hold the user's CLAUDE.md.
    home = tmp_path / "home"
    claude = home / ".claude"
    seed(home, {})
    legacy = a_legacy_backup(install_module, home)
    if own_text:
        md = claude / "CLAUDE.md"
        md.write_text("notes\n\n" + md.read_text(encoding="utf-8"), encoding="utf-8")
    legacy.unlink()
    legacy.mkdir()
    changes, notices = uninstall_module.uninstall(home)
    assert not any(legacy.name in n and "still in" in n for n in notices), notices
    if own_text:
        assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == "notes\n\n"
    else:
        assert any("missing" in n for n in notices), notices
    assert legacy.is_dir()


def test_a_folder_named_as_the_whole_file_backup_is_no_backup(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    seed(home, {})
    backup = a_whole_file_record(install_module, home)
    backup.unlink()
    backup.mkdir()
    changes, notices = uninstall_module.uninstall(home)
    assert (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == TEMPLATE_MD
    assert any("missing" in n for n in notices), notices
    assert backup.is_dir()


def test_a_folder_named_as_the_legacy_backup_is_not_named_when_the_section_was_taken_out(
        install_module, uninstall_module, tmp_path):
    # Review 11, mutant t24: the leave() path, where the file has no section.
    home = tmp_path / "home"
    claude = home / ".claude"
    seed(home, {})
    legacy = a_legacy_backup(install_module, home)
    (claude / "CLAUDE.md").write_text("notes\n", encoding="utf-8")
    legacy.unlink()
    legacy.mkdir()
    _, notices = uninstall_module.uninstall(home)
    assert not any(legacy.name in n for n in notices), notices
    assert legacy.is_dir()


def test_a_symlink_named_as_the_safety_backup_is_neither_deleted_nor_named(install_module, uninstall_module,
                                                                           tmp_path):
    # Review 11, mutant t09: the installer never makes a link as a backup, so one with that name
    # is not its own.
    home = tmp_path / "home"
    claude = home / ".claude"
    seed(home, {})
    backup = a_section_install(install_module, home)
    (claude / "CLAUDE.md").write_text("my own notes\n", encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.write_text("my own notes\n", encoding="utf-8")
    backup.unlink()
    link_or_skip(backup, elsewhere)
    changes, notices = uninstall_module.uninstall(home)
    assert backup.is_symlink() and elsewhere.read_text(encoding="utf-8") == "my own notes\n"
    assert not any(backup.name in s for s in changes + notices), (changes, notices)


@pytest.mark.parametrize("make", [a_section_install, a_whole_file_record, a_legacy_backup],
                         ids=lambda make: make.__name__)
def test_a_backup_is_named_when_claude_md_is_gone(install_module, uninstall_module, tmp_path, make):
    # Review 11, finding B6: with CLAUDE.md gone, uninstall named only the whole-file installer's
    # backup of a section install; the copy made before the section (or the whole-file record's
    # backup) was kept with no word, and the record entry that named it went.
    home = tmp_path / "home"
    seed(home, {})
    backup = make(install_module, home)
    (home / ".claude" / "CLAUDE.md").unlink()
    changes, notices = uninstall_module.uninstall(home)
    assert backup.read_text(encoding="utf-8") == "my own notes\n"
    assert any(backup.name in n and "gone" in n for n in notices), (changes, notices)
    assert uninstall_module.uninstall(home) == ([], [])


def test_an_edited_section_names_the_copy_made_before_the_install(install_module, uninstall_module, tmp_path):
    # Review 11, finding B7: the section is left (the user edited it) and so is the copy of the
    # file from before the install; the hand-section branch named that copy, this one did not.
    home = tmp_path / "home"
    claude = home / ".claude"
    seed(home, {})
    backup = a_section_install(install_module, home)
    md = claude / "CLAUDE.md"
    text = md.read_text(encoding="utf-8")
    end = text.index("<!-- Ideal-Umbrella rules: end -->")
    md.write_text(text[:end] + "- my own rule\n" + text[end:], encoding="utf-8")
    _, notices = uninstall_module.uninstall(home)
    assert any("differs" in n and backup.name in n for n in notices), notices


def test_a_claude_md_linked_to_a_read_only_file_stops_uninstall_at_its_step_with_the_path(
        install_module, uninstall_module, tmp_path, monkeypatch):
    # Review 11, finding B4: home-manager links into the read-only Nix store, which no write
    # through the link can change; the README no longer claims it. The error names the file
    # the link points at, and the rerun after the link is replaced finishes the undo.
    home = tmp_path / "home"
    claude = home / ".claude"
    seed(home, {})
    install_module.install(home)
    store = tmp_path / "store" / "CLAUDE.md"
    store.parent.mkdir()
    (claude / "CLAUDE.md").replace(store)
    link_or_skip(claude / "CLAUDE.md", store)
    real_access = os.access
    monkeypatch.setattr(os, "access", lambda p, mode, *a, **k: False if str(p) == str(store.resolve())
                        and mode == os.W_OK else real_access(p, mode, *a, **k))
    with pytest.raises(PermissionError) as error:
        uninstall_module.uninstall(home)
    assert error.value.filename == str(store.resolve())
    monkeypatch.setattr(os, "access", real_access)
    (claude / "CLAUDE.md").unlink()
    (claude / "CLAUDE.md").write_bytes(store.read_bytes())
    uninstall_module.uninstall(home)
    assert not (claude / "CLAUDE.md").exists()
    assert not (claude / "ballast" / "context_check.py").exists()


def test_a_backup_is_kept_when_it_cannot_be_told_whether_claude_md_links_to_it(uninstall_module, tmp_path,
                                                                               monkeypatch):
    # Review 11, mutant n02: a path that cannot be compared may still be the link's target.
    backup, md = tmp_path / "CLAUDE.md.bak-20250101-000000", tmp_path / "CLAUDE.md"

    def refuse(*args, **kwargs):
        raise OSError("cannot compare")
    monkeypatch.setattr(os.path, "samefile", refuse)
    assert uninstall_module._is_target(backup, md) is True


def a_hand_section(install_module, home):
    backup = a_section_install(install_module, home)
    path = home / ".claude" / "ballast" / "install-record.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["claude_md"]["hand_section"] = True
    path.write_text(json.dumps(record), encoding="utf-8")
    return backup


def a_rewritten_whole_file(install_module, home):
    backup = a_whole_file_record(install_module, home)
    (home / ".claude" / "CLAUDE.md").write_text("rewritten\n", encoding="utf-8")
    return backup


def an_edited_section_in_the_file(install_module, home):
    edited = an_edited_section(install_module, home)
    (home / ".claude" / "CLAUDE.md").write_bytes(edited.read_bytes())
    return edited


@pytest.mark.parametrize("make, gone", [
    (a_hand_section, False), (a_rewritten_whole_file, False), (an_edited_section_in_the_file, False),
    (a_section_install, True), (a_whole_file_record, True), (a_legacy_backup, True)],
    ids=["hand-section", "whole-file-differs", "edited", "section-gone", "whole-file-gone", "legacy-gone"])
def test_a_folder_named_as_a_backup_is_neither_read_nor_named(install_module, uninstall_module, tmp_path,
                                                              make, gone):
    # Review 11, mutants n18 to n21: every note that names a backup, and every read of one,
    # checks that it is a file (finding B5).
    home = tmp_path / "home"
    seed(home, {})
    backup = make(install_module, home)
    if gone:
        (home / ".claude" / "CLAUDE.md").unlink()
    backup.unlink()
    backup.mkdir()
    changes, notices = uninstall_module.uninstall(home)
    assert backup.is_dir()
    assert not any(backup.name in s for s in changes + notices), (changes, notices)


# Review 13, finding D2: the ~/.claude and ballast folders too (a dangling ballast link read as
# no record, so the no-record undo dropped a replaced value for good).
@pytest.mark.parametrize("name", ["settings", "claude_md", "hook", "record", "claude", "ballast"])
def test_a_dangling_symlink_stops_uninstall_before_anything_is_written(install_module, uninstall_module, tmp_path,
                                                                       capsys, name):
    # Review 12, finding C5: a dotfiles folder moved or not mounted. Uninstall took the link for
    # a missing file, dropped the settings undo or the CLAUDE.md entry, and wrote the record as
    # uninstalled: once the folder was back, the settings and the section stayed for good.
    home = tmp_path / "home"
    seed(home, {}, "my own notes\n")
    install_module.install(home)
    layout = install_module.layout(home)
    path = layout["record"].parent if name == "ballast" else layout[name]
    dotfiles = tmp_path / "dotfiles"
    dotfiles.mkdir()
    path.replace(dotfiles / path.name)
    link_or_skip(path, dotfiles / path.name)
    dotfiles.rename(tmp_path / "away")
    record = install_module.layout(home)["record"]
    before = {p: p.read_bytes() for p in (home / ".claude").rglob("*") if p.is_file()}
    assert uninstall_module.main(["--home", str(home)]) == 1
    err = capsys.readouterr().err
    assert "symlink to a missing target" in err and "put the target back" in err and "remove it" not in err and "nothing written" in err, err
    assert {p: p.read_bytes() for p in (home / ".claude").rglob("*") if p.is_file()} == before
    (tmp_path / "away").rename(dotfiles)
    uninstall_module.uninstall(home)
    assert json.loads(settings_file(home).read_text(encoding="utf-8")) == {}
    assert (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == "my own notes\n"
    assert json.loads(record.read_text(encoding="utf-8")) == {"uninstalled": True}


def test_a_whole_file_record_without_a_backup_on_a_changed_file_is_left_and_kept(install_module, uninstall_module,
                                                                                tmp_path):
    # Review 12, mutant m01: the file the install created was rewritten, not emptied.
    home = tmp_path / "home"
    seed(home, {})
    whole_file_install(install_module, home, None)
    (home / ".claude" / "CLAUDE.md").write_text("my own notes\n", encoding="utf-8")
    _, notices = uninstall_module.uninstall(home)
    assert any("differs" in n for n in notices), notices
    _, notices = uninstall_module.uninstall(home)
    assert any("differs" in n for n in notices), notices


def test_a_whole_file_record_with_a_backup_on_an_emptied_file_names_the_backup(install_module, uninstall_module,
                                                                              tmp_path):
    # Review 12, mutant m02: an empty file is the finished step only when there is no backup.
    home = tmp_path / "home"
    seed(home, {})
    backup = a_whole_file_record(install_module, home)
    (home / ".claude" / "CLAUDE.md").write_text("", encoding="utf-8")
    _, notices = uninstall_module.uninstall(home)
    assert any("differs" in n and backup.name in n for n in notices), notices


def test_a_whole_file_record_on_a_changed_file_whose_backup_is_gone_says_so(install_module, uninstall_module,
                                                                           tmp_path):
    # Review 32, L3 (mutant U493): the note was the only word; without it the run was silent.
    home = tmp_path / "home"
    seed(home, {})
    name = "CLAUDE.md.bak-20250101-000000"
    whole_file_install(install_module, home, name)
    for path in (home / ".claude").glob("CLAUDE.md.bak-*"):
        path.unlink()
    md = home / ".claude" / "CLAUDE.md"
    md.write_text("my rules, put back by hand\n", encoding="utf-8")
    _, notices = uninstall_module.uninstall(home)
    assert [n for n in notices if "CLAUDE.md" in n] == [
        f"CLAUDE.md is not the file the install wrote, and the backup {name} is gone; left as is"], notices
    assert md.read_text(encoding="utf-8") == "my rules, put back by hand\n"


def test_a_folder_named_as_the_safety_backup_is_no_backup_when_the_section_is_removed(
        install_module, uninstall_module, tmp_path):
    # Review 12, mutants m06 and m07: finish() reads the copy from before the section.
    home = tmp_path / "home"
    seed(home, {})
    backup = a_section_install(install_module, home)
    backup.unlink()
    backup.mkdir()
    changes, notices = uninstall_module.uninstall(home)
    assert (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == "my own notes\n"
    assert backup.is_dir() and not any(backup.name in s for s in changes + notices), (changes, notices)
    assert uninstall_module.uninstall(home) == ([], [])


def one_backup_in_two_roles(install_module, home):
    """The user took the converted section out, back to their own text, and installed again:
    the copy made before the section is the whole-file installer's backup, reused."""
    legacy = a_legacy_backup(install_module, home)
    (home / ".claude" / "CLAUDE.md").write_text("my own notes\n", encoding="utf-8")
    install_module.install(home)
    record = json.loads((home / ".claude" / "ballast" / "install-record.json").read_text(encoding="utf-8"))
    assert record["claude_md"]["safety_backup"] == record["claude_md"]["legacy_backup"] == legacy.name
    return legacy


def test_one_backup_in_two_roles_is_named_once_when_claude_md_is_gone(install_module, uninstall_module, tmp_path):
    # Review 12, finding C4.
    home = tmp_path / "home"
    seed(home, {})
    legacy = one_backup_in_two_roles(install_module, home)
    (home / ".claude" / "CLAUDE.md").unlink()
    _, notices = uninstall_module.uninstall(home)
    assert len([n for n in notices if legacy.name in n]) == 1, notices


def test_a_dry_run_of_one_backup_in_two_roles_says_what_the_real_run_does(install_module, uninstall_module,
                                                                         tmp_path):
    # Review 12, finding C4: the dry run said the backup is still there; the real run deletes it.
    home = tmp_path / "home"
    seed(home, {})
    legacy = one_backup_in_two_roles(install_module, home)
    _, dry = uninstall_module.uninstall(home, dry_run=True)
    _, real = uninstall_module.uninstall(home)
    assert dry == real and not legacy.exists(), (dry, real)


def test_a_dry_run_of_one_backup_in_two_roles_lists_the_real_run_changes_once(install_module, uninstall_module,
                                                                               tmp_path):
    # Review 12, finding C4, the leave() path: CLAUDE.md is put back as the backup holds it.
    home = tmp_path / "home"
    seed(home, {})
    legacy = one_backup_in_two_roles(install_module, home)
    (home / ".claude" / "CLAUDE.md").write_bytes(legacy.read_bytes())
    dry, _ = uninstall_module.uninstall(home, dry_run=True)
    real, _ = uninstall_module.uninstall(home)
    dry, real = ([c for c in changes if legacy.name in c] for changes in (dry, real))
    assert dry == real and len(real) == 1 and not legacy.exists(), (dry, real)


def test_a_claude_md_linked_to_its_recorded_backup_holding_the_section_has_the_section_removed(
        install_module, uninstall_module, tmp_path):
    # Review 13, finding D3: the record from before review 12's fix names the link's target as
    # the copy from before the section, and the section was written into it. Uninstall took the
    # file for that copy, left the section and dropped the record entry, with no word.
    home = tmp_path / "home"
    seed(home, {})
    md = home / ".claude" / "CLAUDE.md"
    backup = a_section_install(install_module, home)
    backup.write_bytes(md.read_bytes())
    md.unlink()
    link_or_skip(md, backup.name)
    changes, notices = uninstall_module.uninstall(home)
    assert md.is_symlink() and backup.read_text(encoding="utf-8") == "my own notes\n"
    # Review 14, finding E1: the note said to delete the backup, which is the file.
    assert not any(backup.name in n for n in notices), notices
    assert uninstall_module.uninstall(home) == ([], [])


@pytest.mark.parametrize("own_text", ["my own notes\n", ""], ids=["own-text", "blank"])
def test_a_claude_md_linked_to_the_legacy_backup_and_installed_again_has_the_section_removed(
        install_module, uninstall_module, tmp_path, own_text):
    # Review 14, finding E1 (b): CLAUDE.md put back with `ln -s` to the whole-file installer's
    # backup, then installed again (the section goes into that file through the link). The note
    # said the file from before the first install "is still in" it, which is CLAUDE.md; with
    # nothing else in the file, uninstall "restored" it from itself and the section stayed.
    home = tmp_path / "home"
    seed(home, {})
    md = home / ".claude" / "CLAUDE.md"
    legacy = a_legacy_backup(install_module, home)
    legacy.write_text(own_text, encoding="utf-8")
    md.unlink()
    link_or_skip(md, legacy.name)
    install_module.install(home)
    held = legacy.read_bytes()
    changes, notices = uninstall_module.uninstall(home)
    assert md.is_symlink() and not any(legacy.name in c for c in changes), (changes, notices)
    if own_text:
        assert legacy.read_text(encoding="utf-8") == own_text and notices == [], (changes, notices)
        assert uninstall_module.uninstall(home) == ([], [])
    else:
        # Nothing but the section, as in the file the user had before the first install
        # (a_legacy_backup_holding_the_section): it is kept, and the note says why.
        assert legacy.read_bytes() == held, (changes, notices)
        assert [n for n in notices if legacy.name in n] == [
            f"CLAUDE.md is a link to {legacy.name}, your file from before the first install, and holds "
            "nothing but the Ideal-Umbrella section; left as is"], notices
        # Review 15, finding F2: the entry is dropped, so the note is not repeated on every run.
        record = json.loads((home / ".claude" / "ballast" / "install-record.json").read_text(encoding="utf-8"))
        assert "claude_md" not in record, record
        _, again = uninstall_module.uninstall(home)
        assert not any(legacy.name in n for n in again), again


def test_a_blank_claude_md_linked_to_its_safety_backup_holding_the_section_is_blank_again(
        install_module, uninstall_module, tmp_path):
    # Review 15, finding F3: the file was blank before the install and is put back with `ln -s`
    # to its safety backup, which holds the section. No test had a linked safety backup with
    # nothing else in it (a mutant taking it for the legacy case left the section, with a note).
    home = tmp_path / "home"
    seed(home, {})
    md = home / ".claude" / "CLAUDE.md"
    md.write_bytes(b"\n")
    install_module.install(home)
    record_path = home / ".claude" / "ballast" / "install-record.json"
    safety = home / ".claude" / json.loads(record_path.read_text(encoding="utf-8"))["claude_md"]["safety_backup"]
    safety.write_bytes(md.read_bytes())
    md.unlink()
    link_or_skip(md, safety.name)
    changes, notices = uninstall_module.uninstall(home)
    assert md.is_symlink() and safety.read_bytes() == b"\n" and notices == [], (changes, notices)
    assert "claude_md" not in json.loads(record_path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("which", ["safety_backup", "legacy_backup"])
def test_a_backup_replaced_by_a_dangling_link_is_not_taken_for_gone(install_module, uninstall_module, tmp_path,
                                                                    which):
    # Review 15, finding F4: the "no section" note when the recorded backup is still there; a
    # backup replaced by a link to nothing is still there (it is not read or deleted), and no
    # test checked that it was not taken for one already deleted.
    home = tmp_path / "home"
    seed(home, {})
    md = home / ".claude" / "CLAUDE.md"
    if which == "safety_backup":
        md.write_bytes(b"mine\n")
        install_module.install(home)
    else:
        a_legacy_backup(install_module, home)
    record = json.loads((home / ".claude" / "ballast" / "install-record.json").read_text(encoding="utf-8"))
    backup = home / ".claude" / record["claude_md"][which]
    backup.unlink()
    link_or_skip(backup, "nowhere")
    md.write_bytes(b"mine\n")   # the section taken out by hand
    changes, notices = uninstall_module.uninstall(home)
    assert md.read_bytes() == b"mine\n" and backup.is_symlink(), (changes, notices)
    assert "CLAUDE.md has no Ideal-Umbrella section; left as is" in notices, notices


def test_a_section_taken_out_by_hand_is_named_when_the_legacy_backup_differs(install_module, uninstall_module,
                                                                             tmp_path):
    # Review 32, L3 (mutant U269): a first-install backup that differs from the file is no sign
    # that an earlier uninstall restored it, so the section was taken out by hand: say so.
    home = tmp_path / "home"
    seed(home, {}, claude_md="my rules\n")
    install_module.install(home)
    md = home / ".claude" / "CLAUDE.md"
    md.write_text("my rules, edited\n", encoding="utf-8")
    legacy = "CLAUDE.md.bak-20250101-000000"
    (home / ".claude" / legacy).write_text("the whole-file rules\n", encoding="utf-8")
    path = home / ".claude" / "ballast" / "install-record.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["claude_md"]["legacy_backup"] = legacy
    path.write_text(json.dumps(record), encoding="utf-8")
    _, notices = uninstall_module.uninstall(home)
    assert "CLAUDE.md has no Ideal-Umbrella section; left as is" in notices, notices
    assert f"your CLAUDE.md from before the first install is still in {legacy}" in notices, notices
    assert md.read_text(encoding="utf-8") == "my rules, edited\n"


@pytest.mark.parametrize("script", ["install", "uninstall"])
@pytest.mark.parametrize("how", ["env", "home"])
def test_a_config_dir_that_cannot_be_looked_at_is_a_one_line_error(install_module, uninstall_module, tmp_path,
                                                                   monkeypatch, capsys, script, how):
    # Review 14, finding E2: the dangling-link check in target() asked exists() of each folder
    # above the path, outside main()'s try; a folder the user may not search gave a traceback.
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    # The folder first: on Windows a link made to a missing target is a file link, which
    # cannot be followed into a folder ("Access is denied").
    (tmp_path / "locked").mkdir()
    link_or_skip(tmp_path / "link", tmp_path / "locked", target_is_directory=True)
    config = tmp_path / "link" / "cfg"
    # Review 25: the check now looks with lstat/stat, not exists(), so refuse those.
    refuse_looks_inside(tmp_path / "locked", monkeypatch)
    if how == "env":
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
        args = []
    else:
        monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
        args = ["--home", str(config)]
    module = install_module if script == "install" else uninstall_module
    assert module.main(args) == 1
    err = capsys.readouterr().err
    assert err.startswith("Error: ") and "cannot look at" in err and "nothing written" in err, err
    assert len(err.splitlines()) == 1, err


@pytest.mark.parametrize("script", ["install", "uninstall"])
def test_an_empty_home_argument_is_refused(install_module, uninstall_module, tmp_path, monkeypatch, capsys,
                                           script):
    # Review 14, finding E7: `--home ""` (a script's unset variable) was taken as no --home, so
    # the run changed the real config with no word.
    home = tmp_path / "home"
    seed(home, {})
    install_module.install(home)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    before = {p: p.read_bytes() for p in home.rglob("*") if p.is_file()}
    module = install_module if script == "install" else uninstall_module
    assert module.main(["--home", ""]) == 1
    err = capsys.readouterr().err
    assert "--home is empty" in err and "nothing written" in err, err
    assert {p: p.read_bytes() for p in home.rglob("*") if p.is_file()} == before



@pytest.mark.parametrize("case", ["home", "no-home"])
@pytest.mark.parametrize("script", ["install", "uninstall"])
def test_a_home_that_cannot_be_found_is_a_one_line_error(install_module, uninstall_module, tmp_path, monkeypatch,
                                                         capsys, script, case):
    # Review 15, finding F1: `--home '~nosuchuser'`, CLAUDE_CONFIG_DIR='~nosuchuser/cfg', or a
    # user with no HOME and no passwd entry made Path.expanduser() or Path.home() raise
    # RuntimeError, which neither main caught: a traceback, not a one-line error. (A "~" in
    # CLAUDE_CONFIG_DIR is refused before it is expanded since review 18, L1.)
    real_expanduser = Path.expanduser

    def expanduser(self):
        if str(self).startswith("~nosuchuser"):
            raise RuntimeError("Could not determine home directory.")
        return real_expanduser(self)

    def no_home(cls=None):
        raise RuntimeError("Could not determine home directory.")
    monkeypatch.setattr(Path, "expanduser", expanduser)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    argv = []
    if case == "home":
        argv = ["--home", "~nosuchuser"]
    else:
        monkeypatch.setattr(Path, "home", classmethod(no_home))
    module = install_module if script == "install" else uninstall_module
    assert module.main(argv) == 1
    err = capsys.readouterr().err
    assert err.startswith("Error: ") and err.count("\n") == 1 and "nothing written" in err, err
    assert "home folder" in err, err
    if case != "no-home":
        # Review 16, finding G6: the error names the path that holds the "~name".
        assert "~nosuchuser" in err, err
    assert not (tmp_path / "home").exists()


@pytest.mark.parametrize("script", ["install", "uninstall"])
def test_no_home_folder_is_no_matter_when_claude_config_dir_is_set(install_module, uninstall_module, tmp_path,
                                                                    monkeypatch, capsys, script):
    # Review 16, finding G1: with no home folder to be found (no HOME, no passwd entry) a set
    # CLAUDE_CONFIG_DIR was refused, and the advice to give --home installed into
    # <home>/.claude, a folder Claude Code does not read when CLAUDE_CONFIG_DIR is set.
    def no_home(cls=None):
        raise RuntimeError("Could not determine home directory.")
    config = tmp_path / "cfg"
    monkeypatch.setattr(Path, "home", classmethod(no_home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    module = install_module if script == "install" else uninstall_module
    assert module.main([]) == 0, capsys.readouterr()
    if script == "install":
        assert (config / "settings.json").is_file() and (config / "CLAUDE.md").is_file()
    else:
        assert "Nothing to undo" in capsys.readouterr().out


@pytest.mark.parametrize("kind", ["dangling", "loop"])
@pytest.mark.parametrize("script", ["install", "uninstall"])
def test_a_home_that_is_a_link_to_nothing_is_a_one_line_error(install_module, uninstall_module, tmp_path,
                                                               monkeypatch, capsys, script, kind):
    # Review 16, findings G2 and G3: a HOME that is a symlink to a missing folder (an unmounted
    # volume) was resolved, so install created the missing folder and wrote beneath the mount
    # point; a HOME that is a symlink loop ended in a traceback on Python 3.10-3.12. --home and
    # CLAUDE_CONFIG_DIR already stopped both with one line.
    home = tmp_path / "home"
    link_or_skip(home, tmp_path / "mnt" / "vol" / "home" if kind == "dangling" else home)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    module = install_module if script == "install" else uninstall_module
    assert module.main([]) == 1
    err = capsys.readouterr().err
    assert err.startswith("Error: ") and err.count("\n") == 1 and "nothing written" in err, err
    assert not (tmp_path / "mnt").exists()


def confine(monkeypatch, tmp_path, *modules):
    """Fail the test before any write when a run would act outside tmp_path: a refusal that
    regresses must not install into the real /.claude when the tests run as root (review 17, K5)."""
    for module in modules:
        real = module.layout

        def layout(home, config_dir=None, real=real):
            paths = real(home, config_dir)
            assert Path(os.path.abspath(paths["claude"])).is_relative_to(tmp_path), paths["claude"]
            return paths
        monkeypatch.setattr(module, "layout", layout)


@pytest.mark.parametrize("how", ["plain", "--home ~"])
@pytest.mark.parametrize("variable", ["HOME", "USERPROFILE"])
@pytest.mark.parametrize("value", ["", "relative"])
@pytest.mark.parametrize("script", ["install", "uninstall"])
def test_an_empty_or_relative_home_variable_is_refused(install_module, uninstall_module, tmp_path, monkeypatch,
                                                       capsys, script, value, variable, how):
    # Review 16, finding G5: HOME="" was taken as "/" (and USERPROFILE="" on Windows as the
    # current folder), so the run acted on /.claude; Claude Code reads a relative .claude there.
    # Review 17, K3: the same home reached through "~" in --home.
    if (variable == "HOME") == (os.name == "nt"):
        pytest.skip("Path.home() reads HOME on POSIX and USERPROFILE on Windows")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(variable, value)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    argv = ["--home", "~"] if how == "--home ~" else []
    module = install_module if script == "install" else uninstall_module
    confine(monkeypatch, tmp_path, install_module, uninstall_module.install)
    assert module.main(argv) == 1
    err = capsys.readouterr().err
    assert err.startswith("Error: ") and err.count("\n") == 1 and "nothing written" in err, err
    assert f"{variable} is" in err and "--home" in err, err
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(os.name == "nt", reason="the passwd entry is POSIX only")
@pytest.mark.parametrize("how", ["plain", "--home ~", "--home ~/sub"])
@pytest.mark.parametrize("script", ["install", "uninstall"])
def test_an_empty_home_in_the_passwd_entry_is_refused(install_module, uninstall_module, tmp_path, monkeypatch,
                                                      capsys, script, how):
    # Review 18, L2: with no HOME, Path.home() reads the passwd entry and takes an empty home
    # field there for "/", so the run acted on /.claude; Claude Code reads a relative .claude.
    import pwd
    # Built from scratch: the user running the tests may have no passwd entry (review 19, T1).
    entry = pwd.struct_passwd(("u", "x", os.getuid(), os.getgid(), "", "", "/bin/sh"))
    monkeypatch.setattr(pwd, "getpwuid", lambda uid: entry)
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    argv = how.split() if how != "plain" else []
    module = install_module if script == "install" else uninstall_module
    confine(monkeypatch, tmp_path, install_module, uninstall_module.install)
    assert module.main(argv) == 1
    err = capsys.readouterr().err
    assert err.startswith("Error: ") and err.count("\n") == 1 and "nothing written" in err, err
    assert "passwd" in err and "--home" in err, err
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("value", ["cfg", "./~other/cfg", "~/cfg", "~other/cfg", ""])
@pytest.mark.parametrize("script", ["install", "uninstall"])
def test_a_relative_claude_config_dir_is_refused(install_module, uninstall_module, tmp_path, monkeypatch, capsys,
                                                 script, value):
    # Review 17, K3: a relative CLAUDE_CONFIG_DIR was taken from the folder the installer ran in,
    # but Claude Code and the hook read it from each project folder; "./~other/cfg" also went to
    # that user's home (pathlib drops the "./", K2).
    # Review 18, L1: Claude Code takes the value as it is: it does not expand "~" and does not
    # take an empty value for unset, so "~/cfg" and "" were installed where it does not read.
    real_expanduser = Path.expanduser
    monkeypatch.setattr(Path, "expanduser", lambda self: tmp_path / "other"
                        if self.parts and self.parts[0] == "~other" else real_expanduser(self))
    (tmp_path / "home").mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    (tmp_path / "other").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", value)
    module = install_module if script == "install" else uninstall_module
    confine(monkeypatch, tmp_path, install_module, uninstall_module.install)
    assert module.main([]) == 1
    err = capsys.readouterr().err
    assert err.startswith("Error: ") and err.count("\n") == 1 and "nothing written" in err, err
    assert "CLAUDE_CONFIG_DIR" in err and "absolute" in err, err
    assert sorted(p.name for p in tmp_path.rglob("*")) == ["home", "other"]


@pytest.mark.parametrize("script", ["install", "uninstall"])
def test_a_home_of_another_user_that_is_not_there_is_refused(install_module, uninstall_module, tmp_path,
                                                            monkeypatch, capsys, script):
    # Review 16, finding G4: on Windows "~name" expands to a folder beside your own home
    # (C:\Users\name) whether or not that user exists, so a typo was installed into, not refused.
    # Review 18, T1: your own home is there, so only the other user's missing home can stop it.
    real_expanduser = Path.expanduser
    users = tmp_path / "Users"

    def expanduser(self):
        if self.parts and self.parts[0] == "~nosuchuser":
            return users.joinpath("nosuchuser", *self.parts[1:])
        return real_expanduser(self)
    monkeypatch.setattr(Path, "expanduser", expanduser)
    (tmp_path / "home").mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    module = install_module if script == "install" else uninstall_module
    assert module.main(["--home", "~nosuchuser"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("Error: ") and err.count("\n") == 1 and "nothing written" in err, err
    assert "~nosuchuser" in err and "home folder" in err, err
    assert not users.exists()


@pytest.mark.parametrize("script", ["install", "uninstall"])
def test_your_own_home_that_is_not_there_is_refused(install_module, uninstall_module, tmp_path, monkeypatch,
                                                    capsys, script):
    # Review 18, T1: a bare "~" whose home folder is missing is refused on purpose, but no test
    # held it: install created the missing home.
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    module = install_module if script == "install" else uninstall_module
    assert module.main(["--home", "~"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("Error: ") and err.count("\n") == 1 and "nothing written" in err, err
    assert "home folder" in err, err
    assert list(tmp_path.iterdir()) == []

def tree(folder):
    """Every entry under folder, links as links (not followed), files with their bytes."""
    out = {}
    for root, dirs, files in os.walk(folder):
        for name in dirs + files:
            p = Path(root) / name
            out[p] = (("link", os.readlink(p)) if p.is_symlink() else ("dir",) if p.is_dir()
                      else ("file", p.read_bytes()))
    return out


@pytest.mark.parametrize("kind", ["no-record-section", "no-record-rules", "whole-file-restore"])
def test_a_dry_run_lists_what_the_real_run_does_and_writes_nothing(install_module, uninstall_module, tmp_path,
                                                                   kind):
    # Review 14, finding E6: no test looked at these dry-run lines, and the dry-run snapshot
    # saw only files, so a dry run that removed the state link passed.
    home = tmp_path / "home"
    seed(home, {})
    claude = home / ".claude"
    if kind == "whole-file-restore":
        a_whole_file_record(install_module, home)
    else:
        if kind == "no-record-section":
            (claude / "CLAUDE.md").write_text("mine\n", encoding="utf-8")
        install_module.install(home)
        if kind == "no-record-rules":
            (claude / "CLAUDE.md").write_text(TEMPLATE_MD, encoding="utf-8")
        (claude / "ballast" / "install-record.json").unlink()
        for name in claude.glob("CLAUDE.md.bak-*"):
            name.unlink()
    (tmp_path / "state").mkdir()
    link_or_skip(claude / "ballast" / "state", tmp_path / "state")
    before = tree(home)
    dry, _ = uninstall_module.uninstall(home, dry_run=True)
    assert tree(home) == before
    real, _ = uninstall_module.uninstall(home)
    real = [re.sub(r" \(copy kept as [^)]*\)$", " (a backup is kept)", c) for c in real
            if not c.startswith("settings backup: ")]
    assert dry == real
    assert "state link removed" in dry and any(c.startswith("CLAUDE.md") for c in dry), dry


def _unreadable(path, how, monkeypatch):
    """Make path unreadable: a folder in its place (EISDIR; PermissionError on Windows), or an
    open that is refused (a 0600 file left by a sudo run, which root in CI could still read)."""
    if how == "folder":
        if path.exists():
            path.unlink()
        path.mkdir(parents=True)
        return
    import builtins
    real_open = builtins.open

    def refuse(file, mode="r", *args, **kwargs):
        if str(file) == str(path) and "r" in mode:
            raise PermissionError(13, "Permission denied", str(file))
        return real_open(file, mode, *args, **kwargs)
    monkeypatch.setattr(builtins, "open", refuse)


@pytest.mark.parametrize("how", ["folder", "denied"])
@pytest.mark.parametrize("run", ["install", "uninstall"])
def test_a_record_that_cannot_be_read_stops_before_anything_is_written(install_module, uninstall_module, tmp_path,
                                                                       capsys, monkeypatch, run, how):
    # Review 23, F1: the pass-22 read opened the record outside its try, so the "cannot read"
    # handler was dead and the error was a bare [Errno] without "nothing written".
    home = tmp_path / "home"
    install_module.install(home)
    before = settings_file(home).read_bytes()
    _unreadable(home / ".claude" / "ballast" / "install-record.json", how, monkeypatch)
    module = install_module if run == "install" else uninstall_module
    assert module.main(["--home", str(home)]) == 1
    err = capsys.readouterr().err
    assert "cannot read" in err and "nothing written" in err and "[Errno" not in err, err
    assert settings_file(home).read_bytes() == before


@pytest.mark.parametrize("how", ["folder", "denied"])
def test_verify_only_does_not_stop_on_a_record_that_cannot_be_read(install_module, tmp_path, capsys, monkeypatch,
                                                                   how):
    # Review 23, F1: the record is checked by install and uninstall, not by --verify-only; an
    # OSError from it made verification stop with exit 1 and no report.
    home = tmp_path / "home"
    install_module.install(home)
    _unreadable(home / ".claude" / "ballast" / "install-record.json", how, monkeypatch)
    assert install_module.main(["--home", str(home), "--verify-only"]) == 0, capsys.readouterr().err


@pytest.mark.parametrize("how", ["folder", "denied"])
@pytest.mark.parametrize("run", ["install", "uninstall"])
def test_a_settings_file_that_cannot_be_read_stops_before_anything_is_written(install_module, uninstall_module,
                                                                              tmp_path, capsys, monkeypatch, run,
                                                                              how):
    # Review 23, F1 other hits: settings.json was read outside any OSError catch, so the error
    # was a bare [Errno] without "nothing written".
    home = tmp_path / "home"
    install_module.install(home)
    _unreadable(settings_file(home), how, monkeypatch)
    module = install_module if run == "install" else uninstall_module
    assert module.main(["--home", str(home)]) == 1
    err = capsys.readouterr().err
    assert "cannot read" in err and "nothing written" in err and "[Errno" not in err, err


@pytest.mark.parametrize("which", ["settings", "record"])
def test_a_json_error_in_a_file_with_bare_cr_line_ends_names_the_line(install_module, tmp_path, capsys, which):
    # Review 23, I1: reading bytes kept bare CRs (classic Mac line ends), so a JSON error on
    # line 3 was reported on line 1; text mode reads them as line ends.
    home = tmp_path / "home"
    if which == "record":
        install_module.install(home)
        path = home / ".claude" / "ballast" / "install-record.json"
    else:
        path = settings_file(home)
        path.parent.mkdir(parents=True)
    path.write_bytes(b'{\r"a": 1,\r"b": }\r')
    assert install_module.main(["--home", str(home)]) == 1
    assert "line 3" in capsys.readouterr().err


@pytest.mark.parametrize("pathlib_kind", ["3.13", "3.14"])
@pytest.mark.parametrize("folder", ["ballast", "claude"])
@pytest.mark.parametrize("run", ["install", "uninstall", "verify"])
def test_a_folder_that_cannot_be_searched_stops_before_anything_is_written(install_module, uninstall_module, tmp_path,
                                                                           capsys, monkeypatch, run, folder,
                                                                           pathlib_kind):
    # Review 24, F1: on Python 3.14 exists() says False for a record in a folder that cannot be
    # searched, so uninstall ran as if there were no install and dropped the user's own value
    # that only the record held; on 3.13 the error was a bare [Errno 13].
    home = tmp_path / "home"
    settings_file(home).parent.mkdir(parents=True)
    settings_file(home).write_text('{"autoCompactWindow": 100000}', encoding="utf-8")
    install_module.install(home, force=True)
    before = {p: p.read_bytes() for p in (home / ".claude").rglob("*") if p.is_file()}
    blocked = home / ".claude" / "ballast" if folder == "ballast" else home / ".claude"
    if pathlib_kind == "3.14":
        python_314_pathlib(monkeypatch)
    refuse_looks_inside(blocked, monkeypatch)
    module = uninstall_module if run == "uninstall" else install_module
    argv = ["--home", str(home)] + (["--verify-only"] if run == "verify" else [])
    assert module.main(argv) == 1
    captured = capsys.readouterr()
    assert "cannot look at" in captured.err and "[Errno" not in captured.err, captured
    assert "Missing" not in captured.out and "Nothing to undo" not in captured.out, captured
    if run != "verify":
        assert "nothing written" in captured.err, captured.err
    monkeypatch.undo()
    assert {p: p.read_bytes() for p in (home / ".claude").rglob("*") if p.is_file()} == before


def test_a_record_is_read_whatever_exists_says(install_module, tmp_path, monkeypatch):
    # Review 24, F1 (mutant a05): read_record decided "no record" with exists(), which on 3.14
    # is False for a record it cannot look at.
    home = tmp_path / "home"
    install_module.install(home)
    record = install_module.layout(home)["record"]
    monkeypatch.setattr(Path, "exists", lambda self, **kwargs: False)
    monkeypatch.setattr(os.path, "exists", lambda path: False)
    assert install_module.read_record(record) is not None
    assert install_module.read_record(record.parent / "missing.json") is None
    assert install_module.read_record(record / "below-a-file.json") is None


@pytest.mark.parametrize("pathlib_kind", ["3.13", "3.14"])
def test_a_link_into_a_folder_that_cannot_be_searched_is_not_called_missing(install_module, uninstall_module, tmp_path,
                                                                            capsys, monkeypatch, pathlib_kind):
    # Review 24, F1: the target is there, it just cannot be looked at (macOS: dotfiles under
    # ~/Documents without access); "put the target back" was wrong advice.
    home = tmp_path / "home"
    install_module.install(home)
    dotfiles = tmp_path / "dotfiles"
    dotfiles.mkdir()
    settings_file(home).replace(dotfiles / "settings.json")
    link_or_skip(settings_file(home), dotfiles / "settings.json")
    if pathlib_kind == "3.14":
        python_314_pathlib(monkeypatch)
    refuse_looks_inside(dotfiles, monkeypatch)
    for module in (install_module, uninstall_module):
        assert module.main(["--home", str(home)]) == 1
        err = capsys.readouterr().err
        assert "cannot look at" in err and "missing target" not in err and "nothing written" in err, err


@pytest.mark.parametrize("pathlib_kind", ["3.13", "3.14"])
@pytest.mark.parametrize("name", ["settings", "claude_md"])
def test_verify_says_cannot_look_at_for_a_link_into_a_folder_that_cannot_be_searched(install_module, tmp_path, capsys,
                                                                                    monkeypatch, name, pathlib_kind):
    # Review 25, E: no test covered the verify gate for a linked settings.json or CLAUDE.md;
    # without it 3.14 said "Missing:" and 3.13 a bare [Errno 13].
    home = tmp_path / "home"
    install_module.install(home)
    dotfiles = tmp_path / "dotfiles"
    dotfiles.mkdir()
    path = install_module.layout(home)[name]
    path.replace(dotfiles / path.name)
    link_or_skip(path, dotfiles / path.name)
    if pathlib_kind == "3.14":
        python_314_pathlib(monkeypatch)
    refuse_looks_inside(dotfiles, monkeypatch)
    assert install_module.main(["--home", str(home), "--verify-only"]) == 1
    captured = capsys.readouterr()
    assert "cannot look at" in captured.err and "[Errno" not in captured.err, captured
    assert "Missing" not in captured.out + captured.err, captured


@pytest.mark.parametrize("pathlib_kind", ["3.13", "3.14"])
@pytest.mark.parametrize("how", ["--home link", "~"])
def test_a_home_that_cannot_be_looked_at_says_cannot_look_at(install_module, uninstall_module, tmp_path, capsys,
                                                             monkeypatch, how, pathlib_kind):
    # Review 25, D: _absolute() ran before the gate and used exists() and is_dir(): on 3.13 a
    # --home link into a folder that cannot be searched gave a bare [Errno 13], and on 3.14 a
    # "~" home there was "cannot find the home folder".
    dotfiles = tmp_path / "dotfiles"
    real_home = dotfiles / "home"
    real_home.mkdir(parents=True)
    if how == "~":
        monkeypatch.setenv(install_module.HOME_VARIABLE, str(real_home))
        home_arg = "~"
    else:
        link_or_skip(tmp_path / "homelink", real_home, target_is_directory=True)
        home_arg = str(tmp_path / "homelink")
    if pathlib_kind == "3.14":
        python_314_pathlib(monkeypatch)
    refuse_looks_inside(dotfiles, monkeypatch)
    for module in (install_module, uninstall_module):
        assert module.main(["--home", home_arg]) == 1
        err = capsys.readouterr().err
        assert "cannot look at" in err and "[Errno" not in err and "cannot find" not in err, err
        assert "nothing written" in err, err
    monkeypatch.undo()
    assert list(real_home.iterdir()) == []


def test_a_home_that_is_a_link_to_a_folder_is_followed(install_module, uninstall_module, tmp_path, capsys,
                                                       monkeypatch):
    # Review 26, C3: nothing failed when the "~" check looked at the link itself, not at the
    # folder it names (a home reached through a link, such as /home -> /usr/home).
    real_home = tmp_path / "real"
    real_home.mkdir()
    link_or_skip(tmp_path / "home", real_home, target_is_directory=True)
    monkeypatch.setenv(install_module.HOME_VARIABLE, str(tmp_path / "home"))
    assert install_module.main(["--home", "~"]) == 0, capsys.readouterr().err
    assert (real_home / ".claude" / "settings.json").is_file()
    assert uninstall_module.main(["--home", "~"]) == 0, capsys.readouterr().err


def test_a_home_that_is_a_file_is_not_found(install_module, uninstall_module, tmp_path, capsys, monkeypatch):
    # Review 26, C3: nothing failed when the "~" check took any file for the home folder.
    (tmp_path / "home").write_text("not a folder\n", encoding="utf-8")
    monkeypatch.setenv(install_module.HOME_VARIABLE, str(tmp_path / "home"))
    for module in (install_module, uninstall_module):
        assert module.main(["--home", "~"]) == 1
        err = capsys.readouterr().err
        assert "cannot find the home folder" in err and "nothing written" in err, err
    assert (tmp_path / "home").read_text(encoding="utf-8") == "not a folder\n"


def test_an_os_error_while_finding_the_home_is_a_one_line_error(uninstall_module, tmp_path, capsys, monkeypatch):
    # Review 32, L2 (mutant U571): a relative --home run from a folder that was deleted makes
    # os.getcwd() raise FileNotFoundError inside target(); it was a traceback without the
    # OSError in main's except. target() is made to raise it, as no folder can be deleted under
    # the current process on Windows.
    import errno

    def gone(home):
        raise FileNotFoundError(errno.ENOENT, "No such file or directory")
    monkeypatch.setattr(uninstall_module.install, "target", gone)
    assert uninstall_module.main(["--home", "relhome"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("Error: ") and "nothing written" in err and len(err.splitlines()) == 1, err


def test_an_os_error_at_the_first_write_does_not_say_part_way(install_module, uninstall_module, tmp_path, capsys,
                                                              monkeypatch):
    # Review 24, F2: the review-4 test now reaches the read error, so nothing covered an
    # OSError raised before any step of the undo was done.
    import errno
    home = tmp_path / "home"
    seed(home, {}, "my own notes\n")
    install_module.install(home)

    def full(path, data):
        raise OSError(errno.ENOSPC, "No space left on device", str(path))
    monkeypatch.setattr(uninstall_module.install, "_write_bytes", full)
    assert uninstall_module.main(["--home", str(home)]) == 1
    err = capsys.readouterr().err
    assert "No space left" in err and "run uninstall again" in err, err
    assert "part way" not in err and "Done before the error" not in err and "nothing written" not in err, err


@pytest.mark.parametrize("name", ["ballast/context_check.py", "CLAUDE.md"])
def test_verify_names_a_file_it_cannot_read(install_module, tmp_path, capsys, name):
    # Review 24, F3 other hits: verify read the hook and CLAUDE.md outside any handler, so a
    # folder in their place gave a bare [Errno 21].
    home = tmp_path / "home"
    install_module.install(home)
    path = home / ".claude" / name
    path.unlink()
    path.mkdir()
    assert install_module.main(["--home", str(home), "--verify-only"]) == 1
    err = capsys.readouterr().err
    assert "cannot read" in err and "[Errno" not in err, err


def test_settings_missing_at_uninstall_are_kept_for_a_later_run(install_module, uninstall_module, tmp_path):
    # Review 8, low 23 (old #14): with settings.json gone at uninstall time the leftover record
    # was {"uninstalled": true}; when the file came back, a second run removed only the hook
    # entry, and the value the install replaced (123) was lost. Absent is not empty.
    home = tmp_path / "home"
    seed(home, {"autoCompactWindow": 123})
    install_module.install(home, force=True)
    away = tmp_path / "settings.json"
    settings_file(home).rename(away)
    _, notices = uninstall_module.uninstall(home)
    assert "settings.json not found; settings left for a later run" in notices, notices
    away.rename(settings_file(home))
    uninstall_module.uninstall(home)
    assert read_settings(home) == {"autoCompactWindow": 123}
    assert uninstall_module.uninstall(home) == ([], [])


def test_a_replaced_key_the_user_deleted_names_the_value_from_before(install_module, uninstall_module, tmp_path):
    # Review 8, low 24 (old #15): the key stays deleted (README), but the value the install
    # replaced was skipped without a word.
    home = tmp_path / "home"
    seed(home, {"autoCompactWindow": 123})
    install_module.install(home, force=True)
    settings = read_settings(home)
    del settings["autoCompactWindow"]
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")
    _, notices = uninstall_module.uninstall(home)
    assert "autoCompactWindow: you deleted it; it was 123 before the install" in notices, notices
    assert "autoCompactWindow" not in read_settings(home)


def test_a_settings_file_the_install_created_is_deleted(install_module, uninstall_module, tmp_path):
    # Review 8, low 44 (N7): uninstall left {} and a backup instead of removing the file.
    home = tmp_path / "home"
    install_module.install(home)
    install_module.install(home)   # a second run finds the file, and must not forget who made it
    changes, _ = uninstall_module.uninstall(home)
    assert not settings_file(home).exists(), changes
    assert list((home / ".claude").glob("settings.json.bak-*")) == []
    assert "settings.json deleted (the install created it)" in changes, changes
    assert uninstall_module.uninstall(home) == ([], [])


def test_a_settings_file_the_install_created_keeps_the_users_own_keys(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    install_module.install(home)
    settings = read_settings(home)
    settings["mine"] = 1
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")
    uninstall_module.uninstall(home)
    assert read_settings(home) == {"mine": 1}


def test_a_record_that_does_not_say_who_made_settings_json_keeps_it(install_module, uninstall_module, tmp_path):
    # Absent is not empty: a record from before "settings_created" says nothing, so the file
    # stays, as before.
    home = tmp_path / "home"
    install_module.install(home)
    record_path = home / ".claude" / "ballast" / "install-record.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record.pop("settings_created") is True
    record_path.write_text(json.dumps(record), encoding="utf-8")
    uninstall_module.uninstall(home)
    assert read_settings(home) == {}


def test_a_settings_file_that_was_there_is_kept_empty(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    seed(home, {})
    install_module.install(home)
    record = json.loads((home / ".claude" / "ballast" / "install-record.json").read_text(encoding="utf-8"))
    assert "settings_created" not in record
    uninstall_module.uninstall(home)
    assert read_settings(home) == {}


def test_an_uninstall_stopped_after_deleting_the_created_settings_json_finishes(install_module, uninstall_module, tmp_path):
    # Review 8 self-review M1 (halfway state): uninstall deleted the settings.json the install
    # created, then failed (a folder where the hook file is). The record still held every
    # settings field, so each rerun said "settings.json not found; settings left for a later
    # run", and a settings.json the user made later was undone and deleted.
    home = tmp_path / "home"
    install_module.install(home)
    hook = home / ".claude" / "ballast" / "context_check.py"
    hook.unlink()
    hook.mkdir()
    with pytest.raises(OSError):
        uninstall_module.uninstall(home)
    assert not settings_file(home).exists()
    hook.rmdir()
    _, notices = uninstall_module.uninstall(home)
    assert not any("later run" in n for n in notices), notices
    assert uninstall_module.uninstall(home) == ([], [])
    settings_file(home).write_text('{"autoCompactWindow": 250000}', encoding="utf-8")
    uninstall_module.uninstall(home)
    assert read_settings(home) == {"autoCompactWindow": 250000}


def test_an_install_while_settings_json_is_away_keeps_the_value_from_before(install_module, uninstall_module, tmp_path):
    # Review 8 self-review M2 (absent is not empty): an install run while settings.json was
    # away (a dotfiles folder not linked yet) read it as {}, marked the file as created and
    # moved the value kept from before the first install into added_keys. Once the file was
    # back, uninstall removed the user's value and deleted the file.
    home = tmp_path / "home"
    seed(home, {"autoCompactWindow": 100000})
    install_module.install(home, force=True)
    away = tmp_path / "settings.json"
    settings_file(home).rename(away)
    install_module.install(home)
    settings_file(home).unlink()
    away.rename(settings_file(home))
    uninstall_module.uninstall(home)
    assert read_settings(home) == {"autoCompactWindow": 100000}


def test_an_install_after_an_uninstall_with_settings_away_keeps_the_value_from_before(install_module, uninstall_module, tmp_path):
    # M2, second path: uninstall with the file away keeps its part for a later run; an install
    # before the file is back must not turn that part into keys the install added.
    home = tmp_path / "home"
    seed(home, {"autoCompactWindow": 123})
    install_module.install(home, force=True)
    away = tmp_path / "settings.json"
    settings_file(home).rename(away)
    uninstall_module.uninstall(home)
    install_module.install(home)
    settings_file(home).unlink()
    away.rename(settings_file(home))
    uninstall_module.uninstall(home)
    assert read_settings(home) == {"autoCompactWindow": 123}


def test_settings_created_false_in_a_record_is_read_as_missing(install_module, uninstall_module, tmp_path):
    # Review 8 self-review L1: only true was accepted, so a false (a hand edit, a sync tool)
    # stopped install and uninstall with a field-type error.
    home = tmp_path / "home"
    install_module.install(home)
    record_path = home / ".claude" / "ballast" / "install-record.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["settings_created"] = False
    record_path.write_text(json.dumps(record), encoding="utf-8")
    install_module.install(home)
    uninstall_module.uninstall(home)
    assert read_settings(home) == {}


# Review 9, B1-B4 and B6-B7: a settings.json counts as created by the install only while it is
# the file the install created: one that still holds something the install wrote (its hook
# entry, or a key it added with the value it wrote). A file that was gone or that the user
# wrote is not undone against, or deleted for, a "settings_created" kept from before.

def _record(home):
    return json.loads((home / ".claude" / "ballast" / "install-record.json").read_text(encoding="utf-8"))


def _write_settings(home, data):
    settings_file(home).write_text(json.dumps(data), encoding="utf-8")


def test_a_settings_json_the_user_wrote_after_deleting_the_created_one_is_kept(install_module, uninstall_module, tmp_path):
    # Review 9, B1: the second install kept "settings_created" from the first, so uninstall
    # deleted the user's file ("the install created it"), and the first-wins deny list took the
    # user's own Artifact deny for the installer's.
    home = tmp_path / "home"
    install_module.install(home)
    settings_file(home).unlink()
    mine = {"permissions": {"deny": ["Artifact"]}}
    _write_settings(home, mine)
    install_module.install(home)
    assert "settings_created" not in _record(home)
    changes, _ = uninstall_module.uninstall(home)
    assert read_settings(home) == mine, changes
    assert "settings.json deleted (the install created it)" not in changes
    assert any(c.startswith("settings backup: ") for c in changes), changes


def test_a_settings_json_the_user_made_after_a_failed_first_install_is_kept(install_module, uninstall_module, tmp_path,
                                                                            monkeypatch):
    # Review 9, B1 variant: the first install stopped at its settings write, so its record said
    # "settings_created"; the user then made the file.
    home = tmp_path / "home"

    def fail(*args, **kwargs):
        raise OSError("disk full")
    with monkeypatch.context() as m:
        m.setattr(install_module, "replace_json", fail)
        with pytest.raises(OSError):
            install_module.install(home)
    assert _record(home).get("settings_created") is True
    mine = {"permissions": {"deny": ["Artifact"]}}
    _write_settings(home, mine)
    install_module.install(home)
    uninstall_module.uninstall(home)
    assert read_settings(home) == mine


def test_an_install_after_a_failed_first_install_says_nothing_of_a_settings_json_away(install_module, uninstall_module,
                                                                                      tmp_path, monkeypatch):
    # Review 9, B6: the rerun said "settings.json not found, though the install record holds
    # changes to it", of a file that was never written, and did not mark the file it then wrote.
    home = tmp_path / "home"

    def fail(*args, **kwargs):
        raise OSError("disk full")
    with monkeypatch.context() as m:
        m.setattr(install_module, "replace_json", fail)
        with pytest.raises(OSError):
            install_module.install(home)
    _, notices = install_module.install(home)
    assert not any("not found" in n for n in notices), notices
    assert _record(home).get("settings_created") is True
    changes, _ = uninstall_module.uninstall(home)
    assert not settings_file(home).exists(), changes


def test_a_users_own_empty_settings_json_is_not_deleted(install_module, uninstall_module, tmp_path):
    # Review 9, B7: the user replaced the created file with their own {}; uninstall deleted it.
    home = tmp_path / "home"
    install_module.install(home)
    settings_file(home).unlink()
    _write_settings(home, {})
    changes, _ = uninstall_module.uninstall(home)
    assert read_settings(home) == {}, changes
    assert "settings.json deleted (the install created it)" not in changes


def test_a_created_settings_json_an_uninstall_deleted_is_dropped_also_with_a_replaced_value(
        install_module, uninstall_module, tmp_path):
    # Review 9, B2 (M6): the record part of a created settings.json that is gone was kept when
    # it held a value a --force install replaced, so a settings.json the user made later was
    # undone against it and deleted.
    home = tmp_path / "home"
    install_module.install(home)
    settings = read_settings(home)
    settings["autoCompactWindow"] = 123
    _write_settings(home, settings)
    install_module.install(home, force=True)
    settings = read_settings(home)
    del settings["autoCompactWindow"]
    _write_settings(home, settings)
    hook = home / ".claude" / "ballast" / "context_check.py"
    hook.unlink()
    hook.mkdir()
    with pytest.raises(OSError):
        uninstall_module.uninstall(home)
    assert not settings_file(home).exists()
    hook.rmdir()
    _, notices = uninstall_module.uninstall(home)
    assert "settings.json not found; the install created it, so nothing in it is left to undo" in notices, notices
    mine = {"permissions": {"deny": ["Artifact"]}, "skillListingBudgetFraction": 0.005}
    _write_settings(home, mine)
    assert uninstall_module.uninstall(home) == ([], [])
    assert read_settings(home) == mine


def test_an_install_after_the_created_settings_json_was_left_and_deleted_marks_the_new_one(
        install_module, uninstall_module, tmp_path):
    # Review 9, B3: uninstall left a created settings.json holding a value the user changed; the
    # user deleted it; the next install read the leftover record as a settings.json away, did
    # not mark the file it wrote as created, and the next uninstall left {} and a backup.
    home = tmp_path / "home"
    install_module.install(home)
    settings = read_settings(home)
    settings["autoCompactWindow"] = 123
    _write_settings(home, settings)
    uninstall_module.uninstall(home)
    assert read_settings(home) == {"autoCompactWindow": 123}
    settings_file(home).unlink()
    _, notices = install_module.install(home)
    assert not any("not found" in n for n in notices), notices
    assert _record(home).get("settings_created") is True
    changes, _ = uninstall_module.uninstall(home)
    assert not settings_file(home).exists(), changes
    assert not any(c.startswith("settings backup") for c in changes), changes


def test_an_install_on_the_users_file_after_an_uninstall_does_not_keep_settings_created(
        install_module, uninstall_module, tmp_path):
    # Review 9, B4 (M2): after an uninstall only this run's finding counts; the leftover
    # "settings_created" of a file the uninstall left must not mark the user's later file.
    home = tmp_path / "home"
    install_module.install(home)
    settings = read_settings(home)
    settings["autoCompactWindow"] = 123
    _write_settings(home, settings)
    uninstall_module.uninstall(home)
    assert _record(home).get("settings_created") is True
    _write_settings(home, {})
    install_module.install(home)
    assert "settings_created" not in _record(home)
    uninstall_module.uninstall(home)
    assert read_settings(home) == {}


def test_an_install_while_settings_json_is_away_sees_a_record_without_added_keys(install_module, tmp_path):
    # Review 9, B4 (M7): a record whose keys were all there already holds only the deny list.
    home = tmp_path / "home"
    seed(home, {"autoCompactWindow": 250000, "skillListingBudgetFraction": 0.005})
    install_module.install(home)
    assert _record(home)["added_keys"] == []
    settings_file(home).rename(tmp_path / "settings.json")
    _, notices = install_module.install(home)
    assert any(n.startswith("settings.json not found, though the install record holds changes") for n in notices), notices
    assert "settings_created" not in _record(home)


def test_settings_missing_at_uninstall_after_an_install_without_force_are_kept(install_module, uninstall_module, tmp_path):
    # Review 9, B4 (M13): a record with no replaced value still holds changes to a file away.
    home = tmp_path / "home"
    seed(home, {"mine": 1})
    install_module.install(home)
    away = tmp_path / "settings.json"
    settings_file(home).rename(away)
    _, notices = uninstall_module.uninstall(home)
    assert "settings.json not found; settings left for a later run" in notices, notices
    away.rename(settings_file(home))
    uninstall_module.uninstall(home)
    assert read_settings(home) == {"mine": 1}


def test_settings_missing_at_uninstall_keep_which_containers_were_there(install_module, uninstall_module, tmp_path):
    # Review 9, B4 (M15): the leftover record must keep "created", or the later run takes the
    # user's own empty permissions object for one the install made.
    home = tmp_path / "home"
    before = {"autoCompactWindow": 123, "permissions": {}}
    seed(home, before)
    install_module.install(home, force=True)
    away = tmp_path / "settings.json"
    settings_file(home).rename(away)
    uninstall_module.uninstall(home)
    away.rename(settings_file(home))
    uninstall_module.uninstall(home)
    assert read_settings(home) == before


def test_a_backup_delete_is_not_a_claude_md_change(uninstall_module):
    # Review 9, B4 (M8): deleting a backup of CLAUDE.md leaves CLAUDE.md as it is, so a
    # read-only CLAUDE.md must not stop that run.
    assert uninstall_module._changes_claude_md("CLAUDE.md deleted")
    assert not uninstall_module._changes_claude_md(
        "CLAUDE.md backup CLAUDE.md.bak-20250101-000000 deleted (CLAUDE.md holds the same bytes)")


def test_a_failed_settings_write_takes_back_its_new_backup(install_module, tmp_path, monkeypatch):
    # Review 9, B4 (M10): the backup this call made is deleted and no longer named in progress.
    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")

    def fail(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(install_module, "_write_json", fail)
    progress = []
    with pytest.raises(OSError):
        install_module.replace_json(path, {"a": 1}, progress)
    assert progress == []
    assert list(tmp_path.glob("settings.json.bak-*")) == []


def test_a_failed_settings_write_keeps_an_earlier_backup_it_reused(install_module, tmp_path, monkeypatch):
    # Review 9, B4 (M14): a backup an earlier run made, holding the same bytes, is reused; it is
    # not this call's to delete.
    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")
    earlier = tmp_path / "settings.json.bak-20250101-000000"
    earlier.write_text("{}", encoding="utf-8")

    def fail(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(install_module, "_write_json", fail)
    progress = []
    with pytest.raises(OSError):
        install_module.replace_json(path, {"a": 1}, progress)
    assert earlier.read_text(encoding="utf-8") == "{}"
    assert progress == [f"settings backup: {earlier.name}"]


@pytest.mark.parametrize("value", ['"false"', "0", "[]"])
def test_an_uninstalled_field_that_is_not_true_or_false_is_refused(install_module, uninstall_module, tmp_path, capsys,
                                                                   value):
    # Review 9, I-3: "uninstalled" was read for its truth value, so "false" (a hand edit) read as
    # true and the next install treated the record as one an uninstall left.
    home = tmp_path / "home"
    install_module.install(home)
    path = home / ".claude" / "ballast" / "install-record.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(dict(record, uninstalled=json.loads(value))), encoding="utf-8")
    for module in (install_module, uninstall_module):
        assert module.main(["--home", str(home)]) == 1
        err = capsys.readouterr().err
        assert '"uninstalled" must be true or false' in err, err


def test_a_created_settings_json_without_the_hook_entry_is_still_the_installers(install_module, uninstall_module, tmp_path):
    # Review 9, B1 fix: the file is the one the install created while it holds a key the install
    # added with its value, also with the hook entry and deny list taken out by hand; started
    # afresh, the record would forget the keys and uninstall would leave them.
    home = tmp_path / "home"
    install_module.install(home)
    settings = read_settings(home)
    del settings["hooks"], settings["permissions"]
    _write_settings(home, settings)
    install_module.install(home)
    assert _record(home).get("settings_created") is True
    changes, _ = uninstall_module.uninstall(home)
    assert not settings_file(home).exists(), changes


def test_an_install_after_an_uninstall_keeps_what_the_uninstall_left(install_module, uninstall_module, tmp_path):
    # Review 9, B1 fix: after an uninstall the file holds nothing the install wrote (the undo took
    # it out), so that is no sign of a file the user wrote; the leftover record part stays.
    home = tmp_path / "home"
    install_module.install(home)
    settings = read_settings(home)
    settings["autoCompactWindow"] = 123
    _write_settings(home, settings)
    uninstall_module.uninstall(home)
    install_module.install(home)
    assert "autoCompactWindow" in _record(home)["added_keys"]


# Review 9 self-review, SB1-SB3: a created settings.json whose added keys the user set and a
# --force install then took back holds its installed values as replaced keys; and one that no
# longer holds anything the install wrote keeps the values the uninstall compares by value.

def _forced_over_users_values(install_module, home):
    """Install with no settings.json; the user sets both keys; install --force takes them back."""
    install_module.install(home)
    settings = read_settings(home)
    settings["autoCompactWindow"] = 123
    settings["skillListingBudgetFraction"] = 0.5
    _write_settings(home, settings)
    install_module.install(home, force=True)
    assert _record(home)["replaced"] == {"autoCompactWindow": 123, "skillListingBudgetFraction": 0.5}


def test_a_created_settings_json_holding_replaced_keys_is_still_the_installers(install_module, uninstall_module,
                                                                              tmp_path):
    # SB1: holds_install checked only added_keys, so the reinstall dropped the settings part of the
    # record; the uninstall then left 123 and 0.5 unrestored and five of the installer's deny tools.
    home = tmp_path / "home"
    _forced_over_users_values(install_module, home)
    settings = read_settings(home)
    del settings["hooks"]
    settings["permissions"]["deny"].remove("Artifact")
    _write_settings(home, settings)
    install_module.install(home)
    record = _record(home)
    assert record["replaced"] == {"autoCompactWindow": 123, "skillListingBudgetFraction": 0.5}, record
    assert record.get("settings_created") is True, record
    changes, _ = uninstall_module.uninstall(home)
    assert read_settings(home) == {"autoCompactWindow": 123, "skillListingBudgetFraction": 0.5}, changes


def test_a_created_settings_json_holding_nothing_installed_keeps_the_values_to_compare(install_module,
                                                                                      uninstall_module, tmp_path):
    # SB1 (b): a created file that fails holds_install drops only settings_created, deny_added and
    # created from the record; the keys and values uninstall compares by value stay, so a value the
    # user puts back is still undone. The deny tools of such a file stay (README, Undo).
    home = tmp_path / "home"
    _forced_over_users_values(install_module, home)
    settings = read_settings(home)
    del settings["hooks"]
    settings["permissions"]["deny"].remove("Artifact")
    settings["autoCompactWindow"] = 7
    settings["skillListingBudgetFraction"] = 0.7
    _write_settings(home, settings)
    install_module.install(home)
    record = _record(home)
    assert "settings_created" not in record, record
    assert record["replaced"] == {"autoCompactWindow": 123, "skillListingBudgetFraction": 0.5}, record
    assert record["installed"] == {"autoCompactWindow": 250000, "skillListingBudgetFraction": 0.005}, record
    assert record["deny_added"] == ["Artifact"], record
    # Not missing, which reads as a record from before the field (any container emptied goes).
    assert record["created"] == ["hooks", "hooks.UserPromptSubmit"], record
    settings = read_settings(home)
    settings["autoCompactWindow"] = 250000
    _write_settings(home, settings)
    changes, _ = uninstall_module.uninstall(home)
    after = read_settings(home)
    assert after["autoCompactWindow"] == 123, changes
    assert after["skillListingBudgetFraction"] == 0.7, changes
    assert after["permissions"]["deny"] == ["ScheduleWakeup", "ReportFindings", "SearchPlugins",
                                            "SuggestPluginInstall", "SuggestSkills"], changes


def test_holds_install_counts_the_hook_entry_alone(install_module):
    # SB2: kills a mutant without the hook check.
    settings = {"hooks": {"UserPromptSubmit": [{"hooks": [{"command": "python3 context_check.py"}]}]}}
    assert install_module.holds_install(settings, {}) is True
    assert install_module.holds_install({"hooks": {"UserPromptSubmit": []}}, {}) is False


def test_holds_install_counts_an_added_key_only_with_its_installed_value(install_module):
    # SB2: kills a mutant without the value check.
    record = {"added_keys": ["autoCompactWindow"], "installed": {"autoCompactWindow": 250000}}
    assert install_module.holds_install({"autoCompactWindow": 250000}, record) is True
    assert install_module.holds_install({"autoCompactWindow": 1}, record) is False


def test_holds_install_counts_a_replaced_key_with_its_installed_value(install_module):
    # SB1 (a).
    record = {"added_keys": [], "replaced": {"autoCompactWindow": 123},
              "installed": {"autoCompactWindow": 250000}}
    assert install_module.holds_install({"autoCompactWindow": 250000}, record) is True
    assert install_module.holds_install({"autoCompactWindow": 123}, record) is False


def test_holds_install_needs_a_deny_tool_the_install_added(install_module):
    # SB2: kills a mutant without the bool(added) guard: all() of no tools is true.
    assert install_module.holds_install({"permissions": {"deny": []}}, {"deny_added": []}) is False
    assert install_module.holds_install({"permissions": {"deny": ["X"]}}, {}) is False
    assert install_module.holds_install({"permissions": {"deny": ["X", "Y"]}}, {"deny_added": ["X"]}) is True


def test_a_created_settings_json_the_user_emptied_is_left_empty_with_a_note(install_module, uninstall_module,
                                                                           tmp_path):
    # SB3: the user took out everything the install wrote; the undo then takes out the rest of
    # the deny list and leaves {} and a backup. Content alone cannot tell it from a {} of the
    # user's, so it stays, with a note naming the backup.
    home = tmp_path / "home"
    install_module.install(home)
    settings = read_settings(home)
    del settings["hooks"], settings["autoCompactWindow"], settings["skillListingBudgetFraction"]
    settings["permissions"]["deny"].remove("Artifact")
    _write_settings(home, settings)
    changes, notices = uninstall_module.uninstall(home)
    assert read_settings(home) == {}, changes
    backups = list((home / ".claude").glob("settings.json.bak-*"))
    assert len(backups) == 1, backups
    note = [n for n in notices if n.startswith("settings.json left as {}")]
    assert len(note) == 1 and backups[0].name in note[0], notices


def test_a_users_own_empty_settings_json_gets_the_note_without_a_backup(install_module, uninstall_module, tmp_path):
    # SB3: nothing is written, so no backup is named.
    home = tmp_path / "home"
    install_module.install(home)
    settings_file(home).unlink()
    _write_settings(home, {})
    _, notices = uninstall_module.uninstall(home)
    note = [n for n in notices if n.startswith("settings.json left as {}")]
    assert len(note) == 1 and "bak-" not in note[0], notices


def test_a_linked_created_settings_json_left_empty_gets_no_note_that_it_held_nothing(install_module,
                                                                                     uninstall_module, tmp_path):
    # SB3: a created file that is a link is emptied rather than deleted; it held the install,
    # so the note for a file that held nothing the install wrote is not given.
    home = tmp_path / "home"
    install_module.install(home)
    dotfiles = tmp_path / "dotfiles"
    dotfiles.mkdir()
    settings_file(home).rename(dotfiles / "settings.json")
    try:
        settings_file(home).symlink_to(dotfiles / "settings.json")
    except OSError:
        pytest.skip("cannot create symlinks here")
    _, notices = uninstall_module.uninstall(home)
    assert json.loads((dotfiles / "settings.json").read_text(encoding="utf-8")) == {}
    assert not any(n.startswith("settings.json left as {}") for n in notices), notices


def test_a_users_own_settings_json_with_content_gets_no_empty_note(install_module, uninstall_module, tmp_path):
    # SB3: the note is for a file left as {} only.
    home = tmp_path / "home"
    install_module.install(home)
    settings_file(home).unlink()
    _write_settings(home, {"mine": 1})
    _, notices = uninstall_module.uninstall(home)
    assert read_settings(home) == {"mine": 1}
    assert not any(n.startswith("settings.json left as {}") for n in notices), notices
