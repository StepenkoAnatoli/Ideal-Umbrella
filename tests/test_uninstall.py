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


def test_read_only_files_inside_the_state_folder_are_deleted(install_module, uninstall_module, tmp_path, monkeypatch):
    # Windows refuses to delete a read-only file inside the state folder as it does the hook;
    # shutil.rmtree does not clear the attribute. Here rmtree is made to refuse as Windows
    # does, so the test fails without the fix on every platform.
    import shutil
    import stat
    home = tmp_path / "home"
    seed(home, {})
    install_module.install(home)
    state = install_module.layout(home)["state"]
    (state / "sub").mkdir(parents=True)
    files = [state / "s1.json", state / "sub" / "s2.json"]
    for f in files:
        f.write_text("{}", encoding="utf-8")
        f.chmod(stat.S_IREAD)
    real_rmtree = shutil.rmtree

    def windows_like_rmtree(path, *args, **kwargs):
        for f in files:
            if f.exists() and not f.stat().st_mode & stat.S_IWRITE:
                raise PermissionError(13, "Access is denied", str(f))
        real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(shutil, "rmtree", windows_like_rmtree)
    changes, notices = uninstall_module.uninstall(home)
    assert "state folder deleted" in changes, (changes, notices)
    assert not state.exists()


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
