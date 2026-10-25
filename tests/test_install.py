import json
import os
import subprocess
import sys

import pytest

from conftest import ROOT

INSTALL = ROOT / "config" / "install.py"


def settings_file(home):
    return home / ".claude" / "settings.json"


def test_install_preserves_user_data_and_is_idempotent(install_module, tmp_path):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    settings_file(home).write_text(json.dumps({
        "customKey": "keep-me",
        "permissions": {
            "allow": ["Bash(ls:*)"],
            "ask": ["Bash(git push:*)"],
            "deny": ["MyTool"],
        },
        "hooks": {
            "UserPromptSubmit": [{
                "hooks": [
                    {"type": "command", "command": "bash my-own-hook.sh"},
                    {"type": "command", "command": "python3 -I old/context_check.py", "timeout": 30},
                ]
            }]
        },
    }), encoding="utf-8")
    (claude / "CLAUDE.md").write_text("my own rules\n", encoding="utf-8")

    changes, notices = install_module.install(home)
    assert changes
    assert notices == []

    settings = json.loads(settings_file(home).read_text(encoding="utf-8"))
    assert settings["customKey"] == "keep-me"
    assert settings["permissions"]["allow"] == ["Bash(ls:*)"]
    assert settings["permissions"]["ask"] == ["Bash(git push:*)"]
    assert "MyTool" in settings["permissions"]["deny"]
    assert "Artifact" in settings["permissions"]["deny"]

    hooks = settings["hooks"]["UserPromptSubmit"][0]["hooks"]
    commands = [hook["command"] for hook in hooks]
    assert "bash my-own-hook.sh" in commands
    ours_hooks = [hook for hook in hooks if "context_check.py" in hook["command"]]
    assert len(ours_hooks) == 1
    assert sys.executable in ours_hooks[0]["command"]
    assert ours_hooks[0]["timeout"] == 30

    assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == (
        ROOT / "config" / "CLAUDE.md"
    ).read_text(encoding="utf-8")
    backups = list(claude.glob("CLAUDE.md.bak-*"))
    assert backups and backups[0].read_text(encoding="utf-8") == "my own rules\n"
    assert list(claude.glob("settings.json.bak-*"))

    ok, issues, warnings = install_module.verify(home)
    assert ok, issues
    assert warnings == []

    second_changes, _ = install_module.install(home)
    assert second_changes == []


def test_existing_scalar_is_not_overwritten_without_force(install_module, tmp_path, capsys):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    settings_file(home).write_text(json.dumps({"autoCompactWindow": 100000}), encoding="utf-8")

    _changes, notices = install_module.install(home)
    assert any("autoCompactWindow" in notice for notice in notices)
    settings = json.loads(settings_file(home).read_text(encoding="utf-8"))
    assert settings["autoCompactWindow"] == 100000

    # Keeping your own value is what install does without --force: a warning, not a failure.
    ok, issues, warnings = install_module.verify(home)
    assert ok, issues
    assert any("autoCompactWindow" in warning for warning in warnings)
    assert install_module.main(["--home", str(home), "--verify-only"]) == 0
    assert "warning: autoCompactWindow is 100000" in capsys.readouterr().out

    install_module.install(home, force=True)
    settings = json.loads(settings_file(home).read_text(encoding="utf-8"))
    assert settings["autoCompactWindow"] == 250000
    ok, issues, warnings = install_module.verify(home)
    assert ok, issues
    assert warnings == []


def test_missing_scalar_still_fails_verification(install_module, tmp_path):
    home = tmp_path / "home"
    install_module.install(home)
    settings = json.loads(settings_file(home).read_text(encoding="utf-8"))
    del settings["autoCompactWindow"]
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")

    ok, issues, _ = install_module.verify(home)
    assert not ok
    assert any("autoCompactWindow is missing" in issue for issue in issues)


def test_verify_only_does_not_create_files(install_module, tmp_path, capsys):
    home = tmp_path / "home"
    assert install_module.main(["--home", str(home), "--verify-only"]) == 1
    assert not (home / ".claude").exists()
    assert "[FAIL] Verification failed" in capsys.readouterr().out


def test_non_object_settings_are_rejected(install_module, tmp_path):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    original = "[]"
    settings_file(home).write_text(original, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-I", str(INSTALL), "--home", str(home)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode != 0
    assert "JSON object" in result.stderr
    assert settings_file(home).read_text(encoding="utf-8") == original
    assert not (claude / "ballast").exists()


def test_hook_command_quotes_the_running_interpreter(install_module, tmp_path):
    command = install_module.hook_command(tmp_path)
    assert sys.executable in command
    assert "context_check.py" in command
    # The interpreter is recorded by full path, not as a bare "python3" looked up on PATH.
    assert not command.startswith("python3 ")


def test_failed_install_writes_nothing(install_module, tmp_path, capsys):
    # A CLAUDE.md saved as cp1252 used to fail after settings.json already had the hook entry,
    # leaving a hook that points at a missing file and blocks every prompt.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    original = json.dumps({"model": "opus"})
    settings_file(home).write_text(original, encoding="utf-8")
    (claude / "CLAUDE.md").write_bytes("caf\xe9\n".encode("cp1252"))

    assert install_module.main(["--home", str(home)]) == 1
    assert "not UTF-8" in capsys.readouterr().err
    assert settings_file(home).read_text(encoding="utf-8") == original
    assert not (claude / "ballast").exists()


@pytest.mark.parametrize("home_arg", [".", "~"])
def test_relative_home_gives_absolute_hook_path(install_module, tmp_path, monkeypatch, home_arg):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert install_module.main(["--home", home_arg]) == 0

    settings = json.loads(settings_file(tmp_path).read_text(encoding="utf-8"))
    command = settings["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    assert str((tmp_path / ".claude" / "ballast" / "context_check.py").resolve()) in command


def test_symlinked_settings_stay_symlinks(install_module, tmp_path):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    dotfiles = tmp_path / "dotfiles"
    dotfiles.mkdir()
    (dotfiles / "settings.json").write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    try:
        settings_file(home).symlink_to(dotfiles / "settings.json")
    except OSError:
        pytest.skip("cannot create symlinks here")

    install_module.install(home)
    assert settings_file(home).is_symlink()
    settings = json.loads((dotfiles / "settings.json").read_text(encoding="utf-8"))
    assert settings["model"] == "opus"
    assert settings["autoCompactWindow"] == 250000


def test_malformed_hook_entry_does_not_crash(install_module, tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    settings_file(home).write_text(json.dumps({"hooks": {"UserPromptSubmit": [{"hooks": ["echo hi"]}]}}),
                                   encoding="utf-8")

    install_module.install(home)
    ok, issues, _ = install_module.verify(home)
    assert ok, issues
    entries = json.loads(settings_file(home).read_text(encoding="utf-8"))["hooks"]["UserPromptSubmit"]
    assert {"hooks": ["echo hi"]} in entries


def test_hook_command_does_not_block_prompts_when_the_hook_file_is_missing(install_module, tmp_path):
    # A settings.json synced to a machine without ~/.claude/ballast/context_check.py used to
    # make the shell exit 2 (python: can't open file), which Claude Code treats as "block the
    # prompt": every prompt on that machine was refused.
    command = install_module.hook_command(tmp_path)
    assert command.endswith("|| exit 0")
    assert not (tmp_path / ".claude" / "ballast" / "context_check.py").exists()
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_verify_rejects_a_deny_list_that_is_a_string(install_module, tmp_path):
    home = tmp_path / "home"
    install_module.install(home)
    settings = json.loads(settings_file(home).read_text(encoding="utf-8"))
    # "Artifact" in "Artifact,ScheduleWakeup,..." is a substring match, which used to pass.
    settings["permissions"]["deny"] = ",".join(settings["permissions"]["deny"])
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")
    ok, issues, _ = install_module.verify(home)
    assert not ok
    assert any("permissions.deny is not a list" in issue for issue in issues)


def test_os_error_is_reported_not_raised(install_module, tmp_path, capsys):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "ballast").write_text("in the way", encoding="utf-8")
    assert install_module.main(["--home", str(home)]) == 1
    err = capsys.readouterr().err
    assert err.startswith("Error:")
    assert "Traceback" not in err


def test_home_with_a_quote_in_its_path_verifies(install_module, tmp_path):
    home = tmp_path / "it's home"
    install_module.install(home)
    ok, issues, _ = install_module.verify(home)
    assert ok, issues


def test_record_is_written_after_settings(install_module, tmp_path, monkeypatch):
    # A record of an install whose settings.json write failed would make uninstall report
    # values that were never installed, so settings.json goes first and the record last.
    home = tmp_path / "home"
    paths = install_module.layout(home)
    real_write = install_module._write_json

    def failing_write(path, data):
        if path == paths["settings"]:
            raise OSError("disk full")
        real_write(path, data)

    monkeypatch.setattr(install_module, "_write_json", failing_write)
    with pytest.raises(OSError):
        install_module.install(home)
    assert not paths["record"].exists()
    assert not paths["settings"].exists()
    assert paths["hook"].exists()


def test_unreadable_record_stops_the_install(install_module, tmp_path, capsys):
    # The record holds the values an uninstall puts back. It used to be read as "no record"
    # and overwritten; now the user is told to fix or delete it first.
    home = tmp_path / "home"
    install_module.install(home)
    record = install_module.layout(home)["record"]
    record.write_text("{broken", encoding="utf-8")
    settings_before = settings_file(home).read_text(encoding="utf-8")

    assert install_module.main(["--home", str(home), "--force"]) == 1
    err = capsys.readouterr().err
    assert "not valid JSON" in err and "nothing written" in err
    assert record.read_text(encoding="utf-8") == "{broken"
    assert settings_file(home).read_text(encoding="utf-8") == settings_before


def test_record_that_is_not_an_object_is_an_error(install_module, tmp_path):
    record = tmp_path / "install-record.json"
    record.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        install_module.read_record(record)
    assert install_module.read_record(tmp_path / "missing.json") is None


def test_dangling_symlink_is_reported_before_anything_is_written(install_module, tmp_path, capsys):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    try:
        (claude / "CLAUDE.md").symlink_to(tmp_path / "missing" / "CLAUDE.md")
    except OSError:
        pytest.skip("cannot create symlinks here")
    assert install_module.main(["--home", str(home)]) == 1
    err = capsys.readouterr().err
    assert "symlink to a missing target" in err and "nothing written" in err
    assert not (claude / "ballast").exists()
    assert not settings_file(home).exists()


def test_generated_hook_command_runs_the_hook(install_module, tmp_path):
    # The negative test above cannot fail (every error ends in "|| exit 0"); this one proves the
    # quoting is right by running the installed command end to end on a 160k transcript.
    home = tmp_path / "home"
    install_module.install(home)
    command = json.loads(settings_file(home).read_text(encoding="utf-8"))["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(json.dumps({
        "type": "assistant",
        "message": {"usage": {"input_tokens": 100_000, "output_tokens": 60_000}},
    }) + "\n", encoding="utf-8")
    env = dict(os.environ, IDEAL_UMBRELLA_STATE_DIR=str(tmp_path / "state"),
               IDEAL_UMBRELLA_LOG=str(tmp_path / "hook.log"))
    result = subprocess.run(command, shell=True, input=json.dumps({
        "transcript_path": str(transcript), "session_id": "s-1"}),
        capture_output=True, text=True, encoding="utf-8", env=env)
    assert result.returncode == 0, result.stderr
    assert "context about 160k tokens" in json.loads(result.stdout)["systemMessage"]
