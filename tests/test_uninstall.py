import json
import os
import subprocess
import sys

import pytest

from conftest import ROOT, load_module

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
    assert read_settings(home) == {}
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
    snapshot = {p: p.read_bytes() for p in claude.rglob("*") if p.is_file()}

    result = subprocess.run(
        [sys.executable, "-I", str(UNINSTALL), "--home", str(home), "--dry-run"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert "nothing written" in result.stdout
    assert {p: p.read_bytes() for p in claude.rglob("*") if p.is_file()} == snapshot


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
    assert read_settings(home) == {}
    assert md.read_bytes() == "caf\xe9\n".encode("cp1252")
    assert any("CLAUDE.md" in n for n in notices)


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


def test_an_os_error_before_any_step_does_not_say_part_way(install_module, uninstall_module, tmp_path, capsys):
    # Review 4, info E2: settings.json replaced by a folder fails the first read, and the
    # message said the undo stopped part way although nothing was done.
    home = tmp_path / "home"
    install_module.install(home)
    settings_file(home).unlink()
    settings_file(home).mkdir()

    assert uninstall_module.main(["--home", str(home)]) == 1
    err = capsys.readouterr().err
    assert err.startswith("Error:") and "run uninstall again" in err
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
    assert any("not written by this install" in n for n in notices), notices
    assert (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == by_hand


def test_non_string_backup_name_in_record_does_not_crash(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    whole_file_install(install_module, home, 1)

    changes, notices = uninstall_module.uninstall(home)
    assert "CLAUDE.md deleted" in changes, (changes, notices)


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
    assert "deny" not in read_settings(home).get("permissions", {})


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


@pytest.mark.parametrize("name", ["../CLAUDE.md.bak", "sub/CLAUDE.md.bak"])
def test_backup_name_with_a_separator_in_record_does_not_crash(install_module, uninstall_module, tmp_path, name):
    # Path.with_name raised ValueError on such a name after settings.json was already rewritten,
    # and main() then said "nothing written".
    home = tmp_path / "home"
    whole_file_install(install_module, home, name)
    changes, notices = uninstall_module.uninstall(home)
    assert "CLAUDE.md deleted" in changes, (changes, notices)


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


def link_or_skip(link, target):
    try:
        link.symlink_to(target)
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


@pytest.mark.parametrize("name", ["settings", "claude_md", "hook", "record"])
def test_a_dangling_symlink_stops_uninstall_before_anything_is_written(install_module, uninstall_module, tmp_path,
                                                                       capsys, name):
    # Review 12, finding C5: a dotfiles folder moved or not mounted. Uninstall took the link for
    # a missing file, dropped the settings undo or the CLAUDE.md entry, and wrote the record as
    # uninstalled: once the folder was back, the settings and the section stayed for good.
    home = tmp_path / "home"
    seed(home, {}, "my own notes\n")
    install_module.install(home)
    path = install_module.layout(home)[name]
    dotfiles = tmp_path / "dotfiles"
    dotfiles.mkdir()
    path.replace(dotfiles / path.name)
    link_or_skip(path, dotfiles / path.name)
    dotfiles.rename(tmp_path / "away")
    record = install_module.layout(home)["record"]
    before = {p: p.read_bytes() for p in (home / ".claude").rglob("*") if p.is_file()}
    assert uninstall_module.main(["--home", str(home)]) == 1
    err = capsys.readouterr().err
    assert "symlink to a missing target" in err and "nothing written" in err, err
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
