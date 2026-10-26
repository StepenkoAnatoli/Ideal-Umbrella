import json
import os
import re
import subprocess
import sys
from pathlib import Path

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
    # The install replaced the user's CLAUDE.md and recorded the backup name. If that backup is
    # gone, deleting the installed file would leave the user with nothing: keep it and say so.
    home = tmp_path / "home"
    seed(home, {}, claude_md="my own rules\n")
    install_module.install(home, force=True)
    claude = home / ".claude"
    backups = list(claude.glob("CLAUDE.md.bak-*"))
    assert len(backups) == 1
    backups[0].unlink()

    changes, notices = uninstall_module.uninstall(home)
    assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == TEMPLATE_MD
    assert not any("CLAUDE.md deleted" in change for change in changes)
    assert any("CLAUDE.md left as is" in notice and backups[0].name in notice for notice in notices)
    record = json.loads((claude / "ballast" / "install-record.json").read_text(encoding="utf-8"))
    assert record["uninstalled"] is True
    assert record["claude_md"]["backup"] == backups[0].name


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
    # matched the template), so the file is the user's own. It used to be passed over in
    # silence; now the uninstall says why it stays.
    home = tmp_path / "home"
    seed(home, {}, claude_md=TEMPLATE_MD)
    install_module.install(home)
    assert "claude_md" not in json.loads(
        (home / ".claude" / "ballast" / "install-record.json").read_text(encoding="utf-8"))

    changes, notices = uninstall_module.uninstall(home)
    assert not any("CLAUDE.md" in c for c in changes), changes
    assert any("not written by this install" in n for n in notices), notices
    assert (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == TEMPLATE_MD


def test_non_string_backup_name_in_record_does_not_crash(install_module, uninstall_module, tmp_path):
    # A backup name that is not a plain file name used to take the "no backup was made" branch
    # and delete CLAUDE.md, while the user's real backup stayed on disk unmentioned: the file
    # stays, the notice names the bad name, and the record keeps the entry.
    home = tmp_path / "home"
    seed(home, {}, claude_md="mine\n")
    install_module.install(home)
    record_path = home / ".claude" / "ballast" / "install-record.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["claude_md"]["backup"] = 1
    record_path.write_text(json.dumps(record), encoding="utf-8")

    changes, notices = uninstall_module.uninstall(home)
    assert not any("CLAUDE.md" in c for c in changes), (changes, notices)
    assert any("CLAUDE.md left as is" in n and "1" in n for n in notices), notices
    assert (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == TEMPLATE_MD
    assert json.loads(record_path.read_text(encoding="utf-8"))["claude_md"]["backup"] == 1


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


def test_failed_restore_never_leaves_a_truncated_claude_md(install_module, uninstall_module, tmp_path, monkeypatch):
    # The backup was copied over CLAUDE.md in place; a write error left a fragment.
    import shutil
    home = tmp_path / "home"
    seed(home, {}, claude_md="my own rules\n")
    install_module.install(home)
    claude_md = home / ".claude" / "CLAUDE.md"
    real_copyfile, real_replace = shutil.copyfile, os.replace

    def truncating_copyfile(src, dst, *args, **kwargs):
        if str(dst).endswith("CLAUDE.md"):
            with open(dst, "w", encoding="utf-8") as f:
                f.write("my o")
            raise OSError(28, "No space left on device")
        return real_copyfile(src, dst, *args, **kwargs)

    def failing_replace(src, dst, *args, **kwargs):
        if str(dst).endswith("CLAUDE.md"):
            raise OSError(28, "No space left on device")
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(shutil, "copyfile", truncating_copyfile)
    monkeypatch.setattr(os, "replace", failing_replace)
    with pytest.raises(OSError):
        uninstall_module.uninstall(home)
    assert claude_md.read_text(encoding="utf-8") == TEMPLATE_MD
    assert list((home / ".claude").glob("CLAUDE.md.bak-*"))


@pytest.mark.parametrize("name", ["../CLAUDE.md.bak", "sub/CLAUDE.md.bak"])
def test_backup_name_with_a_separator_in_record_does_not_crash(install_module, uninstall_module, tmp_path, name):
    # Path.with_name raised ValueError on such a name after settings.json was already rewritten,
    # and main() then said "nothing written"; the first fix then deleted CLAUDE.md as if no
    # backup had been made. The file stays, the notice names the bad name, the record keeps it.
    home = tmp_path / "home"
    seed(home, {}, claude_md="mine\n")
    install_module.install(home)
    record_path = home / ".claude" / "ballast" / "install-record.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["claude_md"]["backup"] = name
    record_path.write_text(json.dumps(record), encoding="utf-8")
    changes, notices = uninstall_module.uninstall(home)
    assert not any("CLAUDE.md" in c for c in changes), (changes, notices)
    assert any("CLAUDE.md left as is" in n and name in n for n in notices), notices
    assert (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == TEMPLATE_MD
    assert json.loads(record_path.read_text(encoding="utf-8"))["claude_md"]["backup"] == name


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


def test_record_with_a_wrong_typed_field_is_reported_not_raised(install_module, uninstall_module, tmp_path, capsys):
    # `{"added_keys": 5}` passed read_record and raised a TypeError in undo_settings, a
    # traceback instead of the one-line "fix it or delete it first" a broken record gets.
    home = tmp_path / "home"
    install_module.install(home)
    record = home / ".claude" / "ballast" / "install-record.json"
    record.write_text(json.dumps({"added_keys": 5}), encoding="utf-8")
    settings_before = settings_file(home).read_text(encoding="utf-8")

    assert uninstall_module.main(["--home", str(home)]) == 1
    err = capsys.readouterr().err
    assert err.count("\n") == 1 and "Traceback" not in err, err
    assert str(record) in err and "fix it or delete it first" in err and "nothing written" in err, err
    assert settings_file(home).read_text(encoding="utf-8") == settings_before
    assert (home / ".claude" / "ballast" / "context_check.py").exists()
    assert json.loads(record.read_text(encoding="utf-8")) == {"added_keys": 5}


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root writes read-only files")
def test_a_read_only_settings_file_is_refused_before_it_is_backed_up(install_module, uninstall_module, tmp_path, capsys):
    # The backup was made, then _write_bytes refused the read-only settings.json: each run left
    # one more orphan settings.json.bak-* and reported the undo as stopped part way.
    home = tmp_path / "home"
    seed(home, {"model": "opus"})
    install_module.install(home)
    claude = home / ".claude"
    for p in claude.glob("settings.json.bak-*"):
        p.unlink()
    settings_before = settings_file(home).read_bytes()
    settings_file(home).chmod(0o444)
    try:
        for _ in range(2):
            assert uninstall_module.main(["--home", str(home)]) == 1
            err = capsys.readouterr().err
            assert "read-only" in err and "nothing written" in err and "Traceback" not in err, err
        assert not list(claude.glob("settings.json.bak-*")), list(claude.iterdir())
        assert settings_file(home).read_bytes() == settings_before
        assert (claude / "ballast" / "context_check.py").exists()
        assert (claude / "CLAUDE.md").exists()
    finally:
        settings_file(home).chmod(0o644)


def test_deleted_claude_md_still_restores_the_backup(install_module, uninstall_module, tmp_path):
    # With CLAUDE.md deleted after the install, the whole CLAUDE.md block was skipped: the
    # backup of the user's pre-install file was neither restored nor mentioned, and the
    # leftover record dropped it, so no later run could restore it either.
    home = tmp_path / "home"
    seed(home, {}, claude_md="mine\n")
    install_module.install(home)
    claude = home / ".claude"
    (claude / "CLAUDE.md").unlink()
    backups = [p.name for p in claude.glob("CLAUDE.md.bak-*")]
    assert len(backups) == 1

    dry, _ = uninstall_module.uninstall(home, dry_run=True)
    assert f"CLAUDE.md restored from {backups[0]}" in dry
    assert not (claude / "CLAUDE.md").exists()
    changes, notices = uninstall_module.uninstall(home)
    assert f"CLAUDE.md restored from {backups[0]}" in changes, (changes, notices)
    assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == "mine\n"
    assert not list(claude.glob("CLAUDE.md.bak-*"))
    record = json.loads((claude / "ballast" / "install-record.json").read_text(encoding="utf-8"))
    assert record == {"uninstalled": True}


def test_deleted_claude_md_with_a_missing_backup_keeps_the_record(install_module, uninstall_module, tmp_path):
    # Both gone: nothing can be restored now, but the record keeps the backup's name so a
    # restored backup plus a later run still works, as it does when CLAUDE.md is present.
    home = tmp_path / "home"
    seed(home, {}, claude_md="mine\n")
    install_module.install(home)
    claude = home / ".claude"
    (claude / "CLAUDE.md").unlink()
    backup = next(claude.glob("CLAUDE.md.bak-*"))
    backup.unlink()
    changes, notices = uninstall_module.uninstall(home)
    assert not any("CLAUDE.md" in c for c in changes), changes
    assert any(backup.name in n and "missing" in n for n in notices), notices
    record = json.loads((claude / "ballast" / "install-record.json").read_text(encoding="utf-8"))
    assert record["claude_md"]["backup"] == backup.name


def test_missing_settings_keeps_the_record_for_a_later_run(install_module, uninstall_module, tmp_path):
    # With settings.json absent, undo_settings never ran and the leftover record was the bare
    # marker: the --force original and deny_added were gone, so after the file came back a
    # later run only removed the hook entry.
    import shutil
    home = tmp_path / "home"
    seed(home, {"autoCompactWindow": 123})
    install_module.install(home, force=True)
    away = tmp_path / "settings.json.away"
    shutil.move(settings_file(home), away)

    changes, notices = uninstall_module.uninstall(home)
    assert any("settings.json" in n and "missing" in n for n in notices), notices
    record = json.loads((home / ".claude" / "ballast" / "install-record.json").read_text(encoding="utf-8"))
    assert record["uninstalled"] is True
    assert record["replaced"] == {"autoCompactWindow": 123}
    assert "skillListingBudgetFraction" in record["added_keys"]
    assert record["deny_added"] == list(install_module.REQUIRED_TOOLS)

    shutil.move(away, settings_file(home))
    changes, notices = uninstall_module.uninstall(home)
    assert "autoCompactWindow: restored 123" in changes, (changes, notices)
    assert read_settings(home) == {"autoCompactWindow": 123}


def test_removed_replaced_key_is_reported(install_module, uninstall_module, tmp_path):
    # A key the user removed after a --force install was skipped in silence and its earlier
    # value dropped from the record; README says values you changed are left alone and reported.
    home = tmp_path / "home"
    seed(home, {"autoCompactWindow": 123})
    install_module.install(home, force=True)
    settings = read_settings(home)
    del settings["autoCompactWindow"]
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")
    changes, notices = uninstall_module.uninstall(home)
    assert any("autoCompactWindow" in n and "123" in n for n in notices), notices
    assert "autoCompactWindow" not in read_settings(home)


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root writes into read-only folders")
@pytest.mark.skipif(os.name == "nt", reason="os.access does not see a Windows folder as read-only")
def test_a_read_only_hook_folder_is_refused_before_settings_is_written(install_module, uninstall_module, tmp_path, capsys):
    # Only settings.json, CLAUDE.md and the record were checked: with ballast/ read-only,
    # settings.json was backed up and rewritten, then the hook's unlink failed and the undo
    # "stopped part way", one more settings.json.bak-* per attempt.
    home = tmp_path / "home"
    seed(home, {"model": "opus"})
    install_module.install(home)
    claude = home / ".claude"
    for p in claude.glob("settings.json.bak-*"):
        p.unlink()
    settings_before = settings_file(home).read_bytes()
    (claude / "ballast").chmod(0o555)
    try:
        for _ in range(2):
            assert uninstall_module.main(["--home", str(home)]) == 1
            err = capsys.readouterr().err
            assert "read-only" in err and "nothing written" in err and "Traceback" not in err, err
        assert not list(claude.glob("settings.json.bak-*")), list(claude.iterdir())
        assert settings_file(home).read_bytes() == settings_before
        assert (claude / "ballast" / "context_check.py").exists()
    finally:
        (claude / "ballast").chmod(0o755)


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root writes into read-only folders")
@pytest.mark.skipif(os.name == "nt", reason="os.access does not see a Windows folder as read-only")
def test_a_read_only_state_folder_is_refused_before_settings_is_written(install_module, uninstall_module, tmp_path, capsys):
    # The folder check covered the folder holding each removed path (ballast/ for the state
    # folder), but rmtree also needs the state folder and its sub-folders to be writable: a
    # read-only state/ was found after settings.json was rewritten and the hook deleted.
    home = tmp_path / "home"
    seed(home, {"model": "opus"})
    install_module.install(home)
    claude = home / ".claude"
    for p in claude.glob("settings.json.bak-*"):
        p.unlink()
    settings_before = settings_file(home).read_bytes()
    state = install_module.layout(home)["state"]
    (state / "sub").mkdir(parents=True)
    (state / "sub" / "s1.json").write_text("{}", encoding="utf-8")
    (state / "sub").chmod(0o555)
    try:
        for _ in range(2):
            assert uninstall_module.main(["--home", str(home)]) == 1
            err = capsys.readouterr().err
            assert "read-only" in err and "nothing written" in err and "Traceback" not in err, err
        assert not list(claude.glob("settings.json.bak-*")), list(claude.iterdir())
        assert settings_file(home).read_bytes() == settings_before
        assert (claude / "ballast" / "context_check.py").exists()
    finally:
        (state / "sub").chmod(0o755)


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root reads and writes any folder")
@pytest.mark.skipif(os.name == "nt", reason="POSIX folder modes")
@pytest.mark.parametrize("where, mode", [("sub", 0o000), ("sub", 0o333), ("sub", 0o644), ("sub", 0o100),
                                         ("state", 0o000), ("state", 0o333)])
def test_an_unlistable_or_unsearchable_state_folder_is_refused_before_settings_is_written(
        install_module, uninstall_module, tmp_path, capsys, where, mode):
    # The tree check walked state/ with os.walk, which passes over a folder it cannot list (no
    # read bit, or no search bit) without a word, and asked only for the write bit, which a
    # 0o644 folder has while nothing inside it can be unlinked: in each of these modes
    # settings.json was rewritten and the hook deleted before rmtree failed in the folder, on
    # every run.
    home = tmp_path / "home"
    seed(home, {"model": "opus"})
    install_module.install(home)
    claude = home / ".claude"
    for p in claude.glob("settings.json.bak-*"):
        p.unlink()
    settings_before = settings_file(home).read_bytes()
    state = install_module.layout(home)["state"]
    (state / "sub").mkdir(parents=True)
    (state / "sub" / "s1.json").write_text("{}", encoding="utf-8")
    folder = state if where == "state" else state / "sub"
    folder.chmod(mode)
    try:
        for _ in range(2):
            assert uninstall_module.main(["--home", str(home)]) == 1
            err = capsys.readouterr().err
            assert str(folder) in err and "nothing written" in err and "Traceback" not in err, err
            expected = {0o000: "cannot be read", 0o333: "cannot be read", 0o100: "cannot be read",
                        0o644: "cannot be entered"}[mode]
            assert expected in err, err
        assert not list(claude.glob("settings.json.bak-*")), list(claude.iterdir())
        assert settings_file(home).read_bytes() == settings_before
        assert (claude / "ballast" / "context_check.py").exists()
    finally:
        folder.chmod(0o755)
    assert (state / "sub" / "s1.json").exists()     # nothing inside the state folder went either


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root writes into read-only folders")
@pytest.mark.skipif(os.name == "nt", reason="POSIX folder modes")
@pytest.mark.parametrize("where", ["state", "sub"])
def test_an_empty_read_only_state_folder_is_removed(install_module, uninstall_module, tmp_path, where):
    # Removing an empty folder needs only its parent (rmdir writes nothing inside it), so a
    # read-only state folder or sub-folder with nothing in it is no reason to refuse the undo:
    # the tree check asked every folder for the write bit and refused one rmtree removes.
    home = tmp_path / "home"
    seed(home, {"model": "opus"})
    install_module.install(home)
    state = install_module.layout(home)["state"]
    folder = state if where == "state" else state / "sub"
    folder.mkdir(parents=True)
    folder.chmod(0o555)
    try:
        changes, notices = uninstall_module.uninstall(home)
    finally:
        if folder.exists():
            folder.chmod(0o755)
    assert "state folder deleted" in changes, (changes, notices)
    assert not state.exists()
    assert not install_module.layout(home)["hook"].exists()


def test_read_only_files_and_folders_inside_the_state_folder_are_deleted(install_module, uninstall_module, tmp_path, monkeypatch):
    # Windows refuses to delete a read-only file inside the state folder as it does the hook,
    # and a read-only sub-folder the same way (RemoveDirectory refuses the attribute as
    # DeleteFile does); shutil.rmtree clears neither, and the folders were not cleared. Here
    # rmtree is made to refuse as Windows does, so the test fails without the fix on every
    # platform. The read-only folder is empty, since on POSIX the tree check refuses a
    # read-only folder that holds entries before anything is written.
    import shutil
    import stat
    from pathlib import Path
    home = tmp_path / "home"
    seed(home, {})
    install_module.install(home)
    state = install_module.layout(home)["state"]
    (state / "sub").mkdir(parents=True)
    files = [state / "s1.json", state / "sub" / "s2.json"]
    for f in files:
        f.write_text("{}", encoding="utf-8")
        f.chmod(stat.S_IREAD)
    folders = [state / "ro"]
    (state / "ro").mkdir()
    (state / "ro").chmod(stat.S_IREAD | stat.S_IEXEC)
    real_rmtree = shutil.rmtree
    real_clear = uninstall_module._clear_read_only
    cleared = []

    def recording_clear(path):
        cleared.append(Path(path))
        real_clear(path)

    def windows_like_rmtree(path, *args, **kwargs):
        for p in [*files, *folders]:
            if p.exists() and not p.stat().st_mode & stat.S_IWRITE:
                raise PermissionError(13, "Access is denied", str(p))
        real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(uninstall_module, "_clear_read_only", recording_clear)
    monkeypatch.setattr(shutil, "rmtree", windows_like_rmtree)
    try:
        changes, notices = uninstall_module.uninstall(home)
    finally:
        if (state / "ro").exists():
            (state / "ro").chmod(0o755)
    assert "state folder deleted" in changes, (changes, notices)
    assert not state.exists()
    # The root and every sub-folder of the walk are cleared, as the files are.
    assert {state, state / "sub", state / "ro"} <= set(cleared), cleared


def test_read_only_files_the_undo_deletes_are_deleted(install_module, uninstall_module, tmp_path, monkeypatch):
    # Windows refuses to delete a file with the read-only attribute (a POSIX unlink needs only
    # the folder): a read-only hook, log or CLAUDE.md backup stopped the undo part way. The
    # mode is cleared before each unlink; here unlink is made to refuse as Windows does, so
    # the test fails without the fix on every platform.
    import stat
    from pathlib import Path
    home = tmp_path / "home"
    seed(home, {}, claude_md="mine\n")
    install_module.install(home)
    paths = install_module.layout(home)
    paths["log"].write_text("log\n", encoding="utf-8")
    backup = next((home / ".claude").glob("CLAUDE.md.bak-*"))
    for p in (paths["hook"], paths["log"], backup):
        p.chmod(stat.S_IREAD)
    real_unlink = Path.unlink

    def windows_like_unlink(self, missing_ok=False):
        if not self.is_symlink() and not self.stat().st_mode & stat.S_IWRITE:
            raise PermissionError(13, "Access is denied", str(self))
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", windows_like_unlink)
    changes, notices = uninstall_module.uninstall(home)
    assert "hook deleted" in changes and "log deleted" in changes, (changes, notices)
    assert any(c.startswith("CLAUDE.md restored from") for c in changes), changes
    assert not paths["hook"].exists() and not paths["log"].exists() and not backup.exists()
    assert (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == "mine\n"


@pytest.mark.parametrize("depth", [1500, 12000])
def test_a_settings_json_nested_too_deep_to_write_back_is_refused_before_any_undo(
        install_module, uninstall_module, tmp_path, depth):
    # The undo reads settings.json and writes it back without the keys: a value you nested
    # deeper than the indented writer writes (json reads far deeper on Python 3.12, where
    # 1500 levels read and do not write; 12000 do neither on 3.12 or 3.13) made it die with a
    # traceback at that write, after the hook and the state folder were removed. The read
    # phase refuses the file before any write, so nothing is undone and the next run finds it
    # all; where the interpreter writes the depth back, the undo goes through whole.
    home = tmp_path / "home"
    seed(home, {"model": "opus"})
    assert any(c.startswith("autoCompactWindow: added") for c in install_module.install(home)[0])
    # Spliced in as text: json.loads may not parse the depth either.
    text = settings_file(home).read_text(encoding="utf-8")
    assert text.startswith("{")
    text = '{"deep": ' + "[" * depth + "]" * depth + ", " + text[1:]
    settings_file(home).write_text(text, encoding="utf-8")
    try:
        changes, notices = uninstall_module.uninstall(home)
    except ValueError as e:
        assert re.fullmatch(r".*settings\.json is nested too deep to (write back|read); flatten it first", str(e)), e
        assert settings_file(home).read_text(encoding="utf-8") == text
        assert (home / ".claude" / "ballast" / "context_check.py").is_file()
        assert "unfinished" not in install_module.read_record(home / ".claude" / "ballast" / "install-record.json")
        return
    assert "autoCompactWindow: removed" in changes, (changes, notices)
    assert read_settings(home) == {"model": "opus", "deep": json.loads(text)["deep"]}


def test_an_unfinished_record_restores_what_it_lists_and_judges_the_rest_from_the_evidence(uninstall_module):
    # The record of an interrupted re-install from before it carried the run's data holds the
    # marker's leftovers (a --force replaced value the earlier undo kept) and says it is
    # unfinished: the listed key is restored from the record, the other template keys are
    # removed from the evidence with a notice naming them, and the deny tools it does not
    # list are left with a notice naming them.
    template = uninstall_module.install._read_json(uninstall_module.install.USER_SETTINGS)
    keys = [k for k in template if k not in ("hooks", "permissions")]
    settings = {"model": "opus", "permissions": {"deny": list(template["permissions"]["deny"])},
                **{k: template[k] for k in keys}}
    record = {"unfinished": True, "added_keys": [], "replaced": {keys[0]: 100},
              "installed": {keys[0]: template[keys[0]]}, "created": [], "deny_added": []}
    changes, notices, left = uninstall_module.undo_settings(settings, template, record, evidence=True)
    assert settings[keys[0]] == 100 and all(k not in settings for k in keys[1:]), (settings, changes)
    assert settings["permissions"]["deny"] == template["permissions"]["deny"]
    assert left == []
    assert any("did not finish" in n and n.endswith("removed as without a record: " + ", ".join(keys[1:]))
               for n in notices), notices
    assert any("did not finish" in n and "permissions.deny" in n
               and n.endswith("left as is: " + ", ".join(template["permissions"]["deny"]))
               for n in notices), notices
    # Without evidence only the listed key is touched.
    settings = {"model": "opus", **{k: template[k] for k in keys}}
    changes, notices, left = uninstall_module.undo_settings(settings, template, dict(record), evidence=False)
    assert settings[keys[0]] == 100 and all(k in settings for k in keys[1:]), (settings, changes)


def test_an_unfinished_record_stays_unfinished_while_settings_json_is_missing(install_module, uninstall_module, tmp_path):
    # With settings.json missing the uninstall kept the recorded keys in the marker for a
    # later run, but not the unfinished flag: the run that found the file back read the
    # marker as finished, so the template values and deny tools it did not list were handled
    # as a full record's, with no notice. The flag stays with the marker.
    home = tmp_path / "home"
    paths = install_module.layout(home)
    install_module.install(home)
    full = settings_file(home).read_text(encoding="utf-8")
    paths["record"].write_text(json.dumps({"unfinished": True}), encoding="utf-8")
    settings_file(home).unlink()
    changes, notices = uninstall_module.uninstall(home)
    assert "hook deleted" in changes, changes
    assert json.loads(paths["record"].read_text(encoding="utf-8")) == {"uninstalled": True, "unfinished": True}
    settings_file(home).write_text(full, encoding="utf-8")
    template = install_module._read_json(install_module.USER_SETTINGS)
    changes, notices = uninstall_module.uninstall(home)
    assert any("did not finish" in n and "permissions.deny" in n
               and n.endswith("left as is: " + ", ".join(template["permissions"]["deny"]))
               for n in notices), notices
    assert any("did not finish" in n and "removed as without a record: autoCompactWindow, "
               "skillListingBudgetFraction" in n for n in notices), notices
    assert json.loads(paths["record"].read_text(encoding="utf-8")) == {"uninstalled": True}


@pytest.mark.parametrize("dry_run", [False, True])
def test_the_undo_of_an_install_interrupted_at_the_hook_write_removes_the_orphan_copy(install_module, uninstall_module, tmp_path, dry_run):
    # An install over the user's CLAUDE.md copies it, records the copy, and was interrupted at
    # the hook write, so the file was never replaced: the undo found a CLAUDE.md that is not
    # the installer's, left it with "differs from what was installed (your earlier file is in
    # ...)" on every run, and kept the identical copy for good. A copy equal to the file has
    # nothing to restore: it is removed and the file is left as the user's own, in silence.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    (claude / "CLAUDE.md").write_text("my own rules\n", encoding="utf-8")
    settings_file(home).write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    paths = install_module.layout(home)
    real_write = install_module._write_bytes

    def failing(path, data):
        if path == paths["hook"]:
            raise OSError(28, "No space left on device")
        real_write(path, data)

    install_module._write_bytes = failing
    try:
        with pytest.raises(OSError):
            install_module.install(home)
    finally:
        install_module._write_bytes = real_write
    copies = sorted(claude.glob("CLAUDE.md.bak-*"))
    settings_copies = sorted(claude.glob("settings.json.bak-*"))
    assert len(copies) == 1 and copies[0].read_text(encoding="utf-8") == "my own rules\n"
    assert len(settings_copies) == 1
    changes, notices = uninstall_module.uninstall(home, dry_run=dry_run)
    assert changes == [
        f"settings.json backup {settings_copies[0].name} removed (settings.json was never replaced)",
        f"CLAUDE.md backup {copies[0].name} removed (CLAUDE.md is still your own file)"], changes
    assert notices == [], notices
    assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == "my own rules\n"
    assert copies[0].exists() is dry_run and settings_copies[0].exists() is dry_run
    if not dry_run:
        assert json.loads(paths["record"].read_text(encoding="utf-8")) == {"uninstalled": True}
        assert uninstall_module.uninstall(home) == ([], [])


def test_a_second_uninstall_says_nothing_about_a_claude_md_the_install_never_wrote(install_module, uninstall_module, tmp_path):
    # After a round trip the marker has no CLAUDE.md entry and the file is the user's own,
    # restored from its backup; the next uninstall still said it "differs from what was
    # installed; left as is". A record without the entry says the install never wrote the
    # file, so there is nothing to say about it.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    (claude / "CLAUDE.md").write_text("my own rules\n", encoding="utf-8")
    install_module.install(home)
    changes, notices = uninstall_module.uninstall(home)
    assert any(c.startswith("CLAUDE.md restored from") for c in changes), (changes, notices)
    assert uninstall_module.uninstall(home) == ([], [])
    # An install that found the template text in place never wrote it either; the user's
    # later edits to their own file are theirs.
    (claude / "CLAUDE.md").write_text(install_module._read_text(install_module.CLAUDE_MD), encoding="utf-8")
    install_module.install(home)
    (claude / "CLAUDE.md").write_text("my own rules again\n", encoding="utf-8")
    changes, notices = uninstall_module.uninstall(home)
    assert not any("CLAUDE.md" in n for n in notices), notices
    assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == "my own rules again\n"


def test_an_unfinished_record_without_the_hook_names_the_values_it_leaves(uninstall_module):
    # Without the hook evidence the template values an unfinished record does not list are
    # the user's own as far as the undo can tell: they are left, and named, so the user can
    # remove one the interrupted install wrote by hand.
    template = uninstall_module.install._read_json(uninstall_module.install.USER_SETTINGS)
    keys = [k for k in template if k not in ("hooks", "permissions")]
    settings = {"model": "opus", keys[1]: template[keys[1]]}
    record = {"unfinished": True, "added_keys": [keys[0]], "replaced": {},
              "installed": {keys[0]: template[keys[0]]}, "created": [], "deny_added": []}
    changes, notices, left = uninstall_module.undo_settings(settings, template, record, evidence=False)
    assert settings == {"model": "opus", keys[1]: template[keys[1]]} and changes == [] and left == []
    assert notices == ["the install record is of an install that did not finish, and there is no "
                       "Ideal-Umbrella hook; settings values it does not list are left as is: " + keys[1]], notices


def test_an_unfinished_record_names_only_template_deny_tools_it_does_not_list(uninstall_module):
    # The deny tools an unfinished record does not list are named for the user to check, but
    # only the template's: a tool the user denied on their own is theirs and not in question.
    template = uninstall_module.install._read_json(uninstall_module.install.USER_SETTINGS)
    wanted = template["permissions"]["deny"]
    settings = {"model": "opus", "permissions": {"deny": ["MyOwnTool", wanted[0], "Another"]}}
    record = {"unfinished": True, "added_keys": [], "replaced": {}, "installed": {}, "created": [],
              "deny_added": []}
    changes, notices, left = uninstall_module.undo_settings(settings, template, record, evidence=True)
    assert settings["permissions"]["deny"] == ["MyOwnTool", wanted[0], "Another"]
    assert [n for n in notices if "permissions.deny" in n] == [
        "the install record is of an install that did not finish; permissions.deny tools it does "
        "not list are left as is: " + wanted[0]], notices


def test_an_unreadable_claude_md_copy_is_refused_before_anything_is_written(install_module, uninstall_module, tmp_path, monkeypatch):
    # The copy an interrupted install recorded is compared with CLAUDE.md to tell an orphan
    # copy from a backup to restore; a copy that cannot be read is reported as such before
    # any write, not raised as a bare OSError part way through the undo.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    (claude / "CLAUDE.md").write_text("my own rules\n", encoding="utf-8")
    settings_file(home).write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    paths = install_module.layout(home)
    real_write = install_module._write_bytes

    def failing(path, data):
        if path == paths["hook"]:
            raise OSError(28, "No space left on device")
        real_write(path, data)

    install_module._write_bytes = failing
    try:
        with pytest.raises(OSError):
            install_module.install(home)
    finally:
        install_module._write_bytes = real_write
    copy = next(claude.glob("CLAUDE.md.bak-*"))
    before = {p.name: p.read_bytes() for p in claude.rglob("*") if p.is_file()}
    real_read = Path.read_bytes

    def unreadable(self):
        if self == copy:
            raise OSError(13, "Permission denied")
        return real_read(self)

    monkeypatch.setattr(Path, "read_bytes", unreadable)
    with pytest.raises(ValueError, match="cannot read .*CLAUDE.md.bak-"):
        uninstall_module.uninstall(home)
    monkeypatch.undo()
    assert {p.name: p.read_bytes() for p in claude.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("dry_run", [False, True])
def test_the_undo_of_an_install_interrupted_at_the_settings_write_removes_the_orphan_settings_copy(install_module, uninstall_module, tmp_path, dry_run):
    # The copy an install made of settings.json before a write that never happened stayed
    # beside the file for good, named only in the install's error message. The interim record
    # names it; a copy still equal to the file has nothing to restore and is removed.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    settings_file(home).write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    settings_path = install_module.layout(home)["settings"]
    real_write = install_module._write_json

    def failing(path, data):
        if path == settings_path:
            raise OSError(28, "No space left on device")
        real_write(path, data)

    install_module._write_json = failing
    try:
        with pytest.raises(OSError):
            install_module.install(home)
    finally:
        install_module._write_json = real_write
    copies = sorted(claude.glob("settings.json.bak-*"))
    assert len(copies) == 1
    changes, notices = uninstall_module.uninstall(home, dry_run=dry_run)
    assert f"settings.json backup {copies[0].name} removed (settings.json was never replaced)" in changes, changes
    assert notices == [], notices
    assert json.loads(settings_file(home).read_text(encoding="utf-8")) == {"model": "opus"}
    assert copies[0].exists() is dry_run
    if not dry_run:
        assert not list(claude.glob("settings.json.bak-*"))
        assert uninstall_module.uninstall(home) == ([], [])


def test_a_removed_key_an_unfinished_record_lists_as_replaced_is_named_as_such(uninstall_module):
    # "was removed after the install; its earlier value is not put back" read as if the
    # replacement had happened; under an unfinished record the install may never have
    # written the key. The notice says what the record claims and what the undo does.
    template = uninstall_module.install._read_json(uninstall_module.install.USER_SETTINGS)
    keys = [k for k in template if k not in ("hooks", "permissions")]
    settings = {"model": "opus"}
    record = {"unfinished": True, "added_keys": [], "replaced": {keys[0]: 100},
              "installed": {keys[0]: template[keys[0]]}, "created": [], "deny_added": []}
    changes, notices, left = uninstall_module.undo_settings(settings, template, record, evidence=True)
    assert settings == {"model": "opus"} and changes == [] and left == []
    assert notices == [f"{keys[0]} is not there; the value 100 an install that did not finish "
                       "listed as replaced is not put back"], notices


def _interrupt_write(install_module, home, name, force=False):
    """Run install(home) with the write of the file `name` (a layout key: hook, claude_md,
    settings) failing like a full disk."""
    target = install_module.layout(home)[name]
    real_write = install_module._write_bytes

    def failing(path, data):
        if Path(path) == target:
            raise OSError(28, "No space left on device")
        real_write(path, data)

    install_module._write_bytes = failing
    try:
        with pytest.raises(OSError):
            install_module.install(home, force=force)
    finally:
        install_module._write_bytes = real_write


@pytest.mark.parametrize("name", ["settings.json", "settings.local.json", "../settings.json.bak-x", ""])
def test_a_settings_copy_name_the_installer_never_writes_is_refused(install_module, uninstall_module, tmp_path, name):
    # The copy of settings.json an unfinished record names was removed when it was a plain
    # file name and the file equalled settings.json: the name "settings.json" passed both (the
    # file equals itself), and the undo deleted settings.json as its own orphan copy; a
    # sibling the user keeps equal (settings.local.json) went the same way. A name with a
    # separator, or an empty one, was passed over in silence. Only a name the installer
    # writes (settings.json.bak-*) is a copy to remove; any other is named and left.
    home = tmp_path / "home"
    claude = home / ".claude"
    seed(home, {"model": "opus"})
    _interrupt_write(install_module, home, "settings")
    record_path = install_module.layout(home)["record"]
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["settings_backup"] = name
    record_path.write_text(json.dumps(record), encoding="utf-8")
    (claude / "settings.local.json").write_bytes(settings_file(home).read_bytes())
    changes, notices = uninstall_module.uninstall(home)
    assert read_settings(home) == {"model": "opus"}
    assert (claude / "settings.local.json").read_text(encoding="utf-8") == json.dumps({"model": "opus"})
    assert not any("settings.json backup" in c for c in changes), changes
    assert notices == [f"the record names a copy of settings.json that is not a name the installer "
                       f"writes ({name!r}); nothing removed"], notices


def test_a_missing_settings_copy_the_record_names_is_reported(install_module, uninstall_module, tmp_path):
    # A copy the record names but that is gone (deleted by hand) was passed over in silence,
    # while a missing CLAUDE.md backup is named. It is named the same way.
    home = tmp_path / "home"
    claude = home / ".claude"
    seed(home, {"model": "opus"})
    _interrupt_write(install_module, home, "settings")
    copy = next(claude.glob("settings.json.bak-*"))
    copy.unlink()
    changes, notices = uninstall_module.uninstall(home, dry_run=True)
    assert not any("settings.json backup" in c for c in changes), changes
    assert notices == [f"the copy of settings.json the record names ({copy.name}) is missing; "
                       "nothing removed"], notices


def test_a_claude_md_backup_name_the_installer_never_writes_is_refused(install_module, uninstall_module, tmp_path):
    # The twin for CLAUDE.md: a record naming "CLAUDE.md" as the backup passed the plain-name
    # check, and the undo restored the file from itself and then deleted it as the backup.
    # Only a name the installer writes (CLAUDE.md.bak-*) is a backup to restore from.
    home = tmp_path / "home"
    seed(home, {}, claude_md="mine\n")
    install_module.install(home)
    record_path = home / ".claude" / "ballast" / "install-record.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["claude_md"]["backup"] = "CLAUDE.md"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    changes, notices = uninstall_module.uninstall(home)
    assert not any("CLAUDE.md" in c for c in changes), (changes, notices)
    assert any("CLAUDE.md left as is" in n and "'CLAUDE.md'" in n for n in notices), notices
    assert (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == TEMPLATE_MD
    assert json.loads(record_path.read_text(encoding="utf-8"))["claude_md"]["backup"] == "CLAUDE.md"


@pytest.mark.parametrize("force_first", [False, True])
def test_a_value_you_set_to_the_template_value_by_hand_survives_the_undo_of_a_later_interrupt(install_module, uninstall_module, tmp_path, monkeypatch, force_first):
    # The undo of an unfinished record took a listed key holding the template value instead
    # of its installed value as the interrupted run's write. A run interrupted at the hook
    # write never touched settings.json, and the interim listed the earlier install's value
    # for a key the run did not change: a value the user had set by hand to the new
    # template's was removed, or an older replaced value put back over it. The interim
    # names the keys it lists with a pre-write value, and only those are read that way.
    home = tmp_path / "home"
    seed(home, {"model": "opus", "autoCompactWindow": 100} if force_first else {"model": "opus"})
    install_module.install(home, force=force_first)
    paths = install_module.layout(home)
    template = install_module._read_json(install_module.USER_SETTINGS)
    earlier = template["autoCompactWindow"]
    template["autoCompactWindow"] = 300000
    newer = tmp_path / "user-settings.json"
    newer.write_text(json.dumps(template), encoding="utf-8")
    monkeypatch.setattr(install_module, "USER_SETTINGS", newer)
    monkeypatch.setattr(uninstall_module.install, "USER_SETTINGS", newer)
    settings = read_settings(home)
    settings["autoCompactWindow"] = 300000
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")
    paths["hook"].unlink()
    _interrupt_write(install_module, home, "hook")
    record = json.loads(paths["record"].read_text(encoding="utf-8"))
    assert record["pre_write"] == [] and record["installed"]["autoCompactWindow"] == earlier, record
    changes, notices = uninstall_module.uninstall(home)
    assert read_settings(home)["autoCompactWindow"] == 300000, (changes, notices)
    assert notices == ["autoCompactWindow is 300000, not the installed value; left as is"], notices


def test_the_undo_removes_the_copy_of_a_settings_json_you_edited_after_the_interrupt(install_module, uninstall_module, tmp_path):
    # The copy an install interrupted at the hook write made of settings.json was removed by
    # the undo only while it still equalled the file; after the user edited the file the copy
    # stayed beside it, named nowhere. A copy of a file the interrupted run never got to
    # replace (every key the record lists is still as it was before the write) is removed.
    home = tmp_path / "home"
    claude = home / ".claude"
    seed(home, {"model": "opus"})
    _interrupt_write(install_module, home, "hook")
    copies = sorted(claude.glob("settings.json.bak-*"))
    assert len(copies) == 1, copies
    settings_file(home).write_text(json.dumps({"model": "opus", "customKey": "mine"}), encoding="utf-8")
    changes, notices = uninstall_module.uninstall(home)
    assert changes == [f"settings.json backup {copies[0].name} removed (settings.json was never replaced)"], changes
    assert notices == [], notices
    assert not list(claude.glob("settings.json.bak-*"))
    assert read_settings(home) == {"model": "opus", "customKey": "mine"}
    assert json.loads((claude / "ballast" / "install-record.json").read_text(encoding="utf-8")) == {"uninstalled": True}


def test_the_copy_of_a_replaced_settings_json_is_kept_by_the_undo(install_module, uninstall_module, tmp_path):
    # The twin: with the interrupt at the final record the write happened, so the copy the
    # interim names is a backup of the replaced file, and it differs from it. It stays.
    # A control: it passes on the modules from before the orphan copy was removed at all.
    home = tmp_path / "home"
    claude = home / ".claude"
    seed(home, {"model": "opus"})
    real_write = install_module._write_json
    record_path = install_module.layout(home)["record"]
    calls = []

    def failing(path, data):
        calls.append(path)
        if path == record_path and calls.count(record_path) == 2:
            raise OSError(28, "No space left on device")
        real_write(path, data)

    install_module._write_json = failing
    try:
        with pytest.raises(OSError):
            install_module.install(home)
    finally:
        install_module._write_json = real_write
    copies = sorted(claude.glob("settings.json.bak-*"))
    assert len(copies) == 1
    changes, notices = uninstall_module.uninstall(home)
    assert not any("backup" in c and "removed" in c for c in changes), changes
    assert copies[0].exists() and read_settings(home) == {"model": "opus"}


def test_the_folder_check_covers_a_claude_md_deleted_beside_an_orphan_settings_copy(install_module, uninstall_module, tmp_path, monkeypatch):
    # The folders the undo deletes in are checked before the first write. The orphan settings
    # copy was added to that list in the middle of an if/elif chain, so with such a copy the
    # CLAUDE.md the undo deletes dropped out of the check. Nothing observable hangs on it
    # (layout() puts both files in the same folder, so the check made for the copy covers the
    # file): this pins the chain's shape, so the list stays one entry per file removed.
    home = tmp_path / "home"
    claude = home / ".claude"
    seed(home, {"model": "opus"})
    _interrupt_write(install_module, home, "settings")
    paths = install_module.layout(home)
    copy = next(claude.glob("settings.json.bak-*"))
    checked = []
    real = uninstall_module.install._refuse_unwritable_folder

    def spy(path, through_link=True):
        checked.append(Path(path))
        return real(path, through_link=through_link)

    monkeypatch.setattr(uninstall_module.install, "_refuse_unwritable_folder", spy)
    changes, notices = uninstall_module.uninstall(home)
    assert "CLAUDE.md deleted" in changes and not copy.exists(), (changes, notices)
    assert paths["claude_md"] in checked and copy in checked, checked


@pytest.mark.parametrize("dry_run", [False, True])
def test_an_unlisted_key_holding_your_own_value_under_an_unfinished_record_is_named_as_unlisted(install_module, uninstall_module, tmp_path, dry_run):
    # Under an unfinished record with the hook in place, a template key the record does not
    # list and that holds the user's own value got "not the installed value; left as is", as
    # if the install had listed it, and went into the marker as a key left as is, so the
    # marker carried empty settings fields for a key it never claimed. The notice says the
    # record does not list it, and the marker stays clean.
    home = tmp_path / "home"
    seed(home, {"model": "opus", "autoCompactWindow": 100})
    _interrupt_write(install_module, home, "claude_md")
    changes, notices = uninstall_module.uninstall(home, dry_run=dry_run)
    assert [c for c in changes if not c.startswith("settings.json backup")] == ["hook deleted"], changes
    assert notices == ["autoCompactWindow is 100, not the template value, and the record of the install "
                       "that did not finish does not list it; left as is"], notices
    assert read_settings(home) == {"model": "opus", "autoCompactWindow": 100}
    if not dry_run:
        assert json.loads((home / ".claude" / "ballast" / "install-record.json").read_text(encoding="utf-8")) == {"uninstalled": True}


def _interrupt_record(install_module, home, which, force=False):
    """Run install(home) with the `which`-th _write_json of the record (1 = the interim one,
    2 = the final one) failing like a full disk."""
    record_path = install_module.layout(home)["record"]
    real_write = install_module._write_json
    calls = []

    def failing(path, data):
        calls.append(path)
        if path == record_path and calls.count(record_path) == which:
            raise OSError(28, "No space left on device")
        real_write(path, data)

    install_module._write_json = failing
    try:
        with pytest.raises(OSError):
            install_module.install(home, force=force)
    finally:
        install_module._write_json = real_write


def _move_template(install_module, uninstall_module, tmp_path, monkeypatch, key, value):
    """Point both modules at a copy of the template with key set to value."""
    template = install_module._read_json(install_module.USER_SETTINGS)
    template[key] = value
    newer = tmp_path / "user-settings.json"
    newer.write_text(json.dumps(template), encoding="utf-8")
    monkeypatch.setattr(install_module, "USER_SETTINGS", newer)
    monkeypatch.setattr(uninstall_module.install, "USER_SETTINGS", newer)


def test_a_record_with_fifty_thousand_pre_write_keys_is_undone_in_bounded_time(uninstall_module, tmp_path):
    # pre_write was read from the record as a list and looked up for every key the undo judges:
    # a record with thousands of keys made the undo take seconds (a list scan per key, inside
    # the per-key loop; 20000 keys took 1.6 s here, 50000 about ten). It is a set once
    # _check_record has seen it is a list of strings.
    import time
    home = tmp_path / "home"
    keys = [f"key{i}" for i in range(50000)]
    seed(home, {k: 2 for k in keys})
    record_path = home / ".claude" / "ballast" / "install-record.json"
    record_path.parent.mkdir()
    record_path.write_text(json.dumps({"added_keys": keys, "replaced": {}, "deny_added": [],
                                       "installed": {k: 1 for k in keys}, "created": [],
                                       "pre_write": keys, "unfinished": True}), encoding="utf-8")
    start = time.perf_counter()
    changes, notices = uninstall_module.uninstall(home, dry_run=True)
    elapsed = time.perf_counter() - start
    assert elapsed < 2, elapsed
    assert changes == [] and len(notices) == 50000, (changes, notices[:3])
    assert all(n.endswith("not the installed value; left as is") for n in notices), notices[:3]


def test_an_interim_record_from_before_pre_write_reads_the_template_value_as_the_runs_write(install_module, uninstall_module, tmp_path, monkeypatch):
    # The undo read a listed key holding the template value as the user's own unless the
    # record named the key in pre_write. The interim record of an earlier installer has no such
    # field at all: with the template value the interrupted run wrote in place, the undo kept
    # it as "not the installed value". A record without the field is read as before the field
    # existed (the template value in any listed key is that run's write) and the undo says so;
    # one with an empty list keeps the rule (see the test of a value set by hand, above).
    home = tmp_path / "home"
    seed(home, {"model": "opus"})
    install_module.install(home)
    paths = install_module.layout(home)
    _move_template(install_module, uninstall_module, tmp_path, monkeypatch, "autoCompactWindow", 300000)
    _interrupt_record(install_module, home, 2)
    record = json.loads(paths["record"].read_text(encoding="utf-8"))
    assert record["pre_write"] == ["autoCompactWindow"] and read_settings(home)["autoCompactWindow"] == 300000, record
    del record["pre_write"]
    # The copy of settings.json was not named by that installer either.
    (home / ".claude" / record.pop("settings_backup")).unlink()
    paths["record"].write_text(json.dumps(record), encoding="utf-8")
    changes, notices = uninstall_module.uninstall(home)
    assert "autoCompactWindow: removed" in changes, (changes, notices)
    assert notices == ["the install record predates pre_write (an earlier installer wrote it); the template "
                       "value in autoCompactWindow is read as the interrupted install's write"], notices
    assert read_settings(home) == {"model": "opus"}
    assert json.loads(paths["record"].read_text(encoding="utf-8")) == {"uninstalled": True}


def test_the_marker_of_an_undo_that_found_settings_json_missing_keeps_an_empty_pre_write(install_module, uninstall_module, tmp_path, monkeypatch):
    # The marker an undo leaves while settings.json is missing carried pre_write only when it
    # named a kept key; an empty list was dropped. Once a record without the field is read as
    # one from before the field existed, that marker would make the later run that finds
    # settings.json back remove a value you set by hand to the template's as the interrupted
    # run's write. The field stays, empty or not, as long as the record had it.
    home = tmp_path / "home"
    seed(home, {"model": "opus"})
    install_module.install(home)
    paths = install_module.layout(home)
    _move_template(install_module, uninstall_module, tmp_path, monkeypatch, "autoCompactWindow", 300000)
    settings = read_settings(home)
    settings["autoCompactWindow"] = 300000
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")
    paths["hook"].unlink()
    _interrupt_write(install_module, home, "hook")
    assert json.loads(paths["record"].read_text(encoding="utf-8"))["pre_write"] == []
    full = settings_file(home).read_text(encoding="utf-8")
    settings_file(home).unlink()
    uninstall_module.uninstall(home)
    marker = json.loads(paths["record"].read_text(encoding="utf-8"))
    assert marker["unfinished"] is True and marker["pre_write"] == [], marker
    settings_file(home).write_text(full, encoding="utf-8")
    changes, notices = uninstall_module.uninstall(home)
    assert read_settings(home)["autoCompactWindow"] == 300000, (changes, notices)
    assert notices == ["autoCompactWindow is 300000, not the installed value; left as is"], notices


def test_the_undo_goes_on_when_the_orphan_settings_copy_cannot_be_removed(install_module, uninstall_module, tmp_path, monkeypatch):
    # The removal of the copy an interrupted install made of settings.json was the undo's first
    # write, with no handling of a failure: a copy that cannot be unlinked (owned by another
    # user in a sticky folder, which the folder check does not see) stopped the whole undo with
    # "the undo stopped part way", on every run, where the undo from before the copy was known
    # finished. The copy is harmless: it is named for the user to remove, and the undo goes on,
    # as the install does with such a copy.
    import errno
    home = tmp_path / "home"
    claude = home / ".claude"
    seed(home, {"model": "opus"}, claude_md="mine\n")
    _interrupt_write(install_module, home, "settings")
    copy = next(claude.glob("settings.json.bak-*"))
    real_unlink = Path.unlink

    def failing(self, missing_ok=False):
        if self == copy:
            raise PermissionError(errno.EPERM, "Operation not permitted", str(self))
        return real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", failing)
    changes, notices = uninstall_module.uninstall(home)
    monkeypatch.undo()
    assert "hook deleted" in changes and any(c.startswith("CLAUDE.md restored from") for c in changes), (changes, notices)
    assert not any("settings.json backup" in c for c in changes), changes
    assert notices == [f"the copy of settings.json the interrupted install made, {copy.name}, could not be "
                       "removed (Operation not permitted); remove it by hand"], notices
    assert copy.exists() and (claude / "CLAUDE.md").read_text(encoding="utf-8") == "mine\n"
    assert json.loads((claude / "ballast" / "install-record.json").read_text(encoding="utf-8")) == {"uninstalled": True}


@pytest.mark.parametrize("kind", ["symlink", "directory"])
@pytest.mark.parametrize("dry_run", [False, True])
def test_a_settings_copy_that_is_not_a_regular_file_is_named_and_left_by_the_undo(install_module, uninstall_module, tmp_path, kind, dry_run):
    # The name check let through whatever sits at the recorded copy name: a symlink to
    # settings.json read as equal to it and was removed as the orphan copy, and a folder was
    # called "missing" while it is there. Neither is a copy the installer writes (a regular
    # file, never a link): each is named for what it is and left.
    home = tmp_path / "home"
    claude = home / ".claude"
    seed(home, {"model": "opus"})
    _interrupt_write(install_module, home, "settings")
    copy = next(claude.glob("settings.json.bak-*"))
    copy.unlink()
    if kind == "symlink":
        copy.symlink_to(settings_file(home))
    else:
        copy.mkdir()
    changes, notices = uninstall_module.uninstall(home, dry_run=dry_run)
    assert not any("settings.json backup" in c for c in changes), changes
    why = "a symlink" if kind == "symlink" else "a directory"
    assert notices == [f"the copy of settings.json the record names ({copy.name}) is {why}, not a copy "
                       "the installer writes; nothing removed"], notices
    assert copy.is_symlink() if kind == "symlink" else copy.is_dir()
    assert read_settings(home) == {"model": "opus"}


@pytest.mark.parametrize("kind", ["symlink", "directory"])
@pytest.mark.parametrize("dry_run", [False, True])
def test_a_claude_md_backup_that_is_not_a_regular_file_is_named_and_left_by_the_undo(install_module, uninstall_module, tmp_path, kind, dry_run):
    # The backup the record names was checked by name and existence only: with a folder at the
    # name the dry run promised "CLAUDE.md restored from" and the real run died at the read
    # ("Is a directory") after the hook and the settings copy were gone; a symlink to CLAUDE.md
    # restored the file from itself and removed the link. Both runs name it for what it is and
    # leave CLAUDE.md and the record entry, as for a name the installer never writes.
    home = tmp_path / "home"
    claude = home / ".claude"
    seed(home, {}, claude_md="mine\n")
    install_module.install(home)
    backup = next(claude.glob("CLAUDE.md.bak-*"))
    backup.unlink()
    if kind == "symlink":
        backup.symlink_to(claude / "CLAUDE.md")
    else:
        backup.mkdir()
    changes, notices = uninstall_module.uninstall(home, dry_run=dry_run)
    assert not any("CLAUDE.md" in c for c in changes), (changes, notices)
    why = "a symlink" if kind == "symlink" else "a directory"
    assert notices == [f"CLAUDE.md left as is: the backup the record names ({backup.name}) is {why}, not a "
                       "copy the installer writes; fix the record first"], notices
    assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == TEMPLATE_MD
    assert backup.is_symlink() if kind == "symlink" else backup.is_dir()
    record = json.loads((claude / "ballast" / "install-record.json").read_text(encoding="utf-8"))
    assert record["claude_md"]["backup"] == backup.name, record

