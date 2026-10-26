import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ROOT, load_module

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
    # values that were never installed, so settings.json goes first and the final record last;
    # the interim record before them lists the same data marked unfinished, so the undo knows
    # a listed key it does not find was never written.
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
    record = install_module.read_record(paths["record"]) or {}
    assert record["unfinished"] is True and "autoCompactWindow" in record["added_keys"], record
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


def test_verify_reports_a_file_system_error_in_one_line(install_module, tmp_path, capsys):
    # verify() ran outside the handler that install() has: a hook path that is a folder gave
    # a traceback from --verify-only and from the verification after an install.
    home = tmp_path / "home"
    install_module.install(home)
    hook = home / ".claude" / "ballast" / "context_check.py"
    hook.unlink()
    hook.mkdir()
    assert install_module.main(["--home", str(home), "--verify-only"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("Error:") and "Traceback" not in err


def test_non_utf8_settings_say_so(install_module, tmp_path, capsys):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_bytes(b'{"a": "caf\xe9"}')
    assert install_module.main(["--home", str(home)]) == 1
    err = capsys.readouterr().err
    assert "not UTF-8" in err and "Traceback" not in err


def test_verify_fails_when_the_hook_interpreter_is_missing(install_module, tmp_path, monkeypatch):
    # The command embeds the interpreter that ran the installer; after a deleted venv or a pyenv
    # bump the hook never runs ("|| exit 0" hides it) and verify() used to say all is well.
    home = tmp_path / "home"
    install_module.install(home)
    settings = json.loads(settings_file(home).read_text(encoding="utf-8"))
    hook = settings["hooks"]["UserPromptSubmit"][0]["hooks"][0]
    gone = str(tmp_path / "gone venv" / "bin" / "python")
    hook["command"] = hook["command"].replace(install_module.quote(sys.executable), install_module.quote(gone))
    assert gone in hook["command"]
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")
    ok, issues, _ = install_module.verify(home)
    assert not ok
    assert any(gone in issue and "interpreter" in issue for issue in issues), issues

    # A bare name found on PATH (a hand-edited command) is fine.
    monkeypatch.setenv("PATH", str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""))
    hook["command"] = hook["command"].replace(install_module.quote(gone), Path(sys.executable).name)
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")
    ok, issues, _ = install_module.verify(home)
    assert ok, issues


def test_failed_claude_md_write_keeps_the_file_and_names_the_backup(install_module, tmp_path, monkeypatch, capsys):
    # CLAUDE.md was overwritten in place: a write error left a truncated file, and the backup
    # that holds the original was never named because the error path dropped the changes list.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    (claude / "CLAUDE.md").write_text("my own rules\n", encoding="utf-8")
    real_write_text, real_replace = Path.write_text, os.replace

    def truncating_write_text(self, data, *args, **kwargs):
        if self.name == "CLAUDE.md":
            with open(self, "w", encoding="utf-8") as f:
                f.write(data[:5])
            raise OSError(28, "No space left on device")
        return real_write_text(self, data, *args, **kwargs)

    def failing_replace(src, dst, *args, **kwargs):
        if str(dst).endswith("CLAUDE.md"):
            raise OSError(28, "No space left on device")
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", truncating_write_text)
    monkeypatch.setattr(install_module.os, "replace", failing_replace)
    assert install_module.main(["--home", str(home)]) == 1
    out, err = capsys.readouterr()
    assert "No space left" in err and "Traceback" not in err
    assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == "my own rules\n"
    backups = [p.name for p in claude.glob("CLAUDE.md.bak-*")]
    assert len(backups) == 1
    assert backups[0] in out + err
    assert not list(claude.glob(".*CLAUDE*")), "temp file left behind"


@pytest.mark.parametrize("name", ["hook", "record"])
def test_dangling_hook_or_record_symlink_is_reported_before_anything_is_written(install_module, tmp_path, capsys, name):
    # settings.json and CLAUDE.md had this check; the hook and the record did not, so a
    # dangling link there gave "No such file or directory" naming a temp file.
    home = tmp_path / "home"
    target = install_module.layout(home)[name]
    target.parent.mkdir(parents=True)
    try:
        target.symlink_to(tmp_path / "missing" / target.name)
    except OSError:
        pytest.skip("cannot create symlinks here")
    assert install_module.main(["--home", str(home)]) == 1
    err = capsys.readouterr().err
    assert "symlink to a missing target" in err and "nothing written" in err, err
    assert not settings_file(home).exists()
    assert not (home / ".claude" / "CLAUDE.md").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_new_files_get_the_umask_mode_not_the_temp_file_mode(install_module, tmp_path, umask_022):
    """A file written for the first time gets the mode a plain write would give it (0644 under
    umask 022), not the private 0600 of the temp file it was written through. The umask is
    pinned: under 077 the two modes are the same and the test held without the fix."""
    home = tmp_path / "home"
    install_module.install(home)
    for name in ("settings.json", "CLAUDE.md", os.path.join("ballast", "context_check.py")):
        path = home / ".claude" / name
        assert path.stat().st_mode & 0o777 == 0o644, name


def test_writing_a_new_file_never_touches_the_process_umask(install_module, tmp_path, monkeypatch):
    # The mode came from reading the umask, which os.umask can only do by setting it: files
    # another thread created in that window were made 0666.
    monkeypatch.setattr(os, "umask", lambda *a: pytest.fail("os.umask was called"))
    install_module._write_bytes(tmp_path / "new.txt", b"x\n")
    assert (tmp_path / "new.txt").read_bytes() == b"x\n"


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root writes read-only files")
def test_write_bytes_refuses_a_read_only_target(install_module, tmp_path):
    # Replacing the file through a rename ignored the read-only bit the user set; main's plain
    # write raised PermissionError and changed nothing.
    target = tmp_path / "CLAUDE.md"
    target.write_text("old\n", encoding="utf-8")
    target.chmod(0o444)
    try:
        with pytest.raises(PermissionError):
            install_module._write_bytes(target, b"new\n")
        assert target.read_text(encoding="utf-8") == "old\n"
        assert [p.name for p in tmp_path.iterdir()] == ["CLAUDE.md"]
    finally:
        target.chmod(0o644)


def test_verify_accepts_a_hook_interpreter_written_with_tilde_or_a_variable(install_module, tmp_path, monkeypatch):
    # README's manual install writes the hook path with ~; _runnable looked for the literal "~".
    home = tmp_path / "home"
    install_module.install(home)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    exe = home / "venv" / "bin" / "python"
    exe.parent.mkdir(parents=True)
    exe.write_text("", encoding="utf-8")
    for form in ("~/venv/bin/python", "$HOME/venv/bin/python"):
        assert install_module._runnable(form), form


@pytest.mark.parametrize("value", [None, 5, "x"])
def test_verify_reports_a_user_prompt_submit_that_is_not_a_list(install_module, tmp_path, value):
    # `--verify-only` on a settings.json with "UserPromptSubmit": null was a TypeError.
    home = tmp_path / "home"
    install_module.install(home)
    settings = json.loads(settings_file(home).read_text(encoding="utf-8"))
    settings["hooks"]["UserPromptSubmit"] = value
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")
    ok, issues, _ = install_module.verify(home)
    assert not ok
    assert any("UserPromptSubmit is not a list" in issue for issue in issues), issues


def test_shell_risk_names_what_bash_changes_in_a_double_quoted_windows_path(install_module):
    # On Windows the hook path is double-quoted; bash expands $name, `cmd` and \\ inside it.
    assert install_module.shell_risk(r"C:\Users\me\.claude\ballast\context_check.py", windows=True) is None
    for path in (r"C:\Users\$me\x.py", r"C:\Users\`me`\x.py", r"\\server\share\x.py"):
        assert install_module.shell_risk(path, windows=True), path
    assert install_module.shell_risk("/home/$me/x.py", windows=False) is None


def test_claude_config_dir_is_honoured_when_home_is_not_given(install_module, tmp_path, monkeypatch):
    # Claude Code reads CLAUDE_CONFIG_DIR instead of ~/.claude when it is set; the installer
    # always wrote to ~/.claude.
    config = tmp_path / "cfg"
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    assert install_module.main([]) == 0
    assert (config / "settings.json").is_file()
    assert (config / "ballast" / "context_check.py").is_file()
    assert str(config / "ballast") in json.loads((config / "settings.json").read_text(encoding="utf-8"))["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    assert not (home / ".claude").exists()
    assert install_module.main(["--verify-only"]) == 0
    # An explicit --home wins over the variable.
    assert install_module.main(["--home", str(tmp_path / "other")]) == 0
    assert (tmp_path / "other" / ".claude" / "settings.json").is_file()


def test_write_bytes_removes_the_temp_file_when_the_rename_fails(install_module, tmp_path, monkeypatch):
    # With a read-only target the temp file got the read-only mode too; on Windows the failing
    # rename then left it behind, since os.remove cannot delete a read-only file. The refusal of
    # a read-only target happens first, so the access check is bypassed here to reach the rename.
    target = tmp_path / "CLAUDE.md"
    target.write_text("old\n", encoding="utf-8")
    target.chmod(0o444)
    try:
        def boom(src, dst):
            raise PermissionError(13, "simulated rename failure", dst)
        monkeypatch.setattr(install_module.os, "access", lambda *a, **k: True)
        monkeypatch.setattr(install_module.os, "replace", boom)
        with pytest.raises(PermissionError, match="simulated"):
            install_module._write_bytes(target, b"new\n")
        assert target.read_text(encoding="utf-8") == "old\n"
        assert [p.name for p in tmp_path.iterdir()] == ["CLAUDE.md"]
    finally:
        target.chmod(0o644)


def test_a_failed_settings_write_after_claude_md_still_lets_uninstall_restore_it(install_module, tmp_path, monkeypatch):
    # CLAUDE.md was replaced and backed up, then the settings write failed and no record was
    # written; the next install saw a CLAUDE.md that already matched, recorded nothing for it,
    # and uninstall never restored the user's file from the first backup.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    (claude / "CLAUDE.md").write_text("my own rules\n", encoding="utf-8")
    paths = install_module.layout(home)
    real_write = install_module._write_json

    def failing_write(path, data):
        if path == paths["settings"]:
            raise OSError("disk full")
        real_write(path, data)

    monkeypatch.setattr(install_module, "_write_json", failing_write)
    with pytest.raises(OSError):
        install_module.install(home)
    monkeypatch.setattr(install_module, "_write_json", real_write)
    install_module.install(home)
    uninstall_module = load_module("uninstall_module", "config/uninstall.py")
    changes, notices = uninstall_module.uninstall(home)
    assert any(c.startswith("CLAUDE.md restored from") for c in changes), (changes, notices)
    assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == "my own rules\n"


def test_reinstall_after_a_template_change_does_not_back_up_the_installers_own_file(install_module, tmp_path, monkeypatch):
    # A CLAUDE.md still holding what the last install wrote was backed up again when the
    # template changed, leaving a *.bak-* of the installer's own text that nothing restores.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    (claude / "CLAUDE.md").write_text("my own rules\n", encoding="utf-8")
    install_module.install(home)
    newer = tmp_path / "CLAUDE.md"
    newer.write_text(install_module._read_text(install_module.CLAUDE_MD) + "\n- one more rule\n", encoding="utf-8")
    monkeypatch.setattr(install_module, "CLAUDE_MD", newer)
    changes, _ = install_module.install(home)
    assert "CLAUDE.md updated" in changes
    assert not any(c.startswith("CLAUDE.md backup:") for c in changes), changes
    backups = sorted(claude.glob("CLAUDE.md.bak-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "my own rules\n"


@pytest.mark.parametrize("record", [{"added_keys": 5}, {"installed": None}, {"replaced": "x"}, {"created": "hooks"}])
def test_record_with_a_wrong_typed_field_stops_the_install_before_any_write(install_module, tmp_path, capsys, record):
    # A record that is a JSON object with a wrong-typed field passed read_record and raised a
    # TypeError in _merge_record, after the hook and CLAUDE.md were written: the user's
    # CLAUDE.md was replaced with its backup unrecorded.
    home = tmp_path / "home"
    claude = home / ".claude"
    paths = install_module.layout(home)
    paths["record"].parent.mkdir(parents=True)
    (claude / "CLAUDE.md").write_text("my own rules\n", encoding="utf-8")
    paths["record"].write_text(json.dumps(record), encoding="utf-8")
    assert install_module.main(["--home", str(home)]) == 1
    err = capsys.readouterr().err
    assert err.count("\n") == 1 and "Traceback" not in err, err
    assert str(paths["record"]) in err and "fix it or delete it first" in err and "nothing written" in err, err
    assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == "my own rules\n"
    assert not paths["hook"].exists() and not settings_file(home).exists()
    assert not list(claude.glob("*.bak-*"))
    assert json.loads(paths["record"].read_text(encoding="utf-8")) == record


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root writes read-only files")
@pytest.mark.parametrize("name", ["CLAUDE.md", "settings.json"])
def test_a_read_only_target_is_refused_before_any_write(install_module, tmp_path, capsys, name):
    # _write_bytes refused the read-only file only when its turn came, after its backup (and
    # the hook, and for settings.json also CLAUDE.md) were written: every attempt left one
    # more orphan *.bak-*. Writability is checkable while reading, so it is checked there.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    settings_file(home).write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    (claude / "CLAUDE.md").write_text("my own rules\n", encoding="utf-8")
    target = claude / name
    target.chmod(0o444)
    try:
        for _ in range(2):
            assert install_module.main(["--home", str(home)]) == 1
            err = capsys.readouterr().err
            assert "read-only" in err and "nothing written" in err and "Traceback" not in err, err
        assert not list(claude.glob("*.bak-*")), list(claude.iterdir())
        assert not (claude / "ballast").exists()
        assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == "my own rules\n"
        assert json.loads(settings_file(home).read_text(encoding="utf-8")) == {"model": "opus"}
    finally:
        target.chmod(0o644)


def test_interrupt_before_the_interim_record_is_recovered_by_the_next_install(install_module, tmp_path, monkeypatch):
    # CLAUDE.md was written before the interim record: an interruption between the two left a
    # template CLAUDE.md with no record of its backup, the next install saw a file that already
    # matched and recorded nothing, and the uninstall said "not written by this install".
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    (claude / "CLAUDE.md").write_text("my own rules\n", encoding="utf-8")
    real_write = install_module._write_json
    calls = []

    def failing_once(path, data):
        calls.append(path)
        if len(calls) == 1:
            raise OSError(28, "No space left on device")
        real_write(path, data)

    monkeypatch.setattr(install_module, "_write_json", failing_once)
    with pytest.raises(OSError):
        install_module.install(home)
    assert calls == [install_module.layout(home)["record"]]
    # The record comes first, so the interrupted run never got to replace the file.
    assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == "my own rules\n"
    monkeypatch.setattr(install_module, "_write_json", real_write)
    install_module.install(home)
    assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == install_module._read_text(install_module.CLAUDE_MD)
    uninstall_module = load_module("uninstall_module", "config/uninstall.py")
    changes, notices = uninstall_module.uninstall(home)
    assert any(c.startswith("CLAUDE.md restored from") for c in changes), (changes, notices)
    assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == "my own rules\n"


def test_record_with_a_bom_is_read(install_module, tmp_path):
    # _read_json accepts a BOM (a hand repair in a Windows editor, which the error message
    # invites); read_record did not, and both scripts refused the record as "not valid JSON".
    home = tmp_path / "home"
    install_module.install(home)
    record = install_module.layout(home)["record"]
    data = json.loads(record.read_text(encoding="utf-8"))
    record.write_bytes(b"\xef\xbb\xbf" + json.dumps(data).encode("utf-8"))
    assert install_module.read_record(record) == data
    assert install_module.install(home) == ([], [])


def test_legacy_record_without_sha256_reports_the_second_backup(install_module, tmp_path, monkeypatch):
    # With a record from before sha256 existed, an edited CLAUDE.md plus a template change
    # backed the edits up but kept the first backup in the record, and nothing said which one
    # the uninstall restores.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    (claude / "CLAUDE.md").write_text("my own rules\n", encoding="utf-8")
    install_module.install(home)
    record = install_module.layout(home)["record"]
    data = json.loads(record.read_text(encoding="utf-8"))
    first = data["claude_md"]["backup"]
    del data["claude_md"]["sha256"]
    record.write_text(json.dumps(data), encoding="utf-8")
    (claude / "CLAUDE.md").write_text("edited after install\n", encoding="utf-8")
    newer = tmp_path / "CLAUDE.md"
    newer.write_text(install_module._read_text(install_module.CLAUDE_MD) + "\n- one more rule\n", encoding="utf-8")
    monkeypatch.setattr(install_module, "CLAUDE_MD", newer)

    changes, notices = install_module.install(home)
    backups = sorted(p.name for p in claude.glob("CLAUDE.md.bak-*"))
    assert len(backups) == 2 and first in backups
    second = next(b for b in backups if b != first)
    assert any(first in n and second in n and "uninstall" in n for n in notices), notices
    uninstall_module = load_module("uninstall_module", "config/uninstall.py")
    changes, _ = uninstall_module.uninstall(home)
    assert f"CLAUDE.md restored from {first}" in changes, changes
    assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == "my own rules\n"


ROOT_USER = hasattr(os, "geteuid") and os.geteuid() == 0


def _interrupt(install_module, home, which, calls_before, force=False):
    """Run install(home) with the `which`-th _write_json of the record (1 = the interim one,
    2 = the final one) failing like a full disk; returns the paths written up to it."""
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
            install_module.install(home, force=force, progress=calls_before)
    finally:
        install_module._write_json = real_write
    return calls


INTERIM_FIELDS = ["added_keys", "created", "deny_added", "installed", "pre_write", "replaced",
                  "settings_backup", "unfinished"]


def _interrupt_write(install_module, home, name, force=False):
    """Run install(home) with the write of the file `name` (a layout key: hook, claude_md,
    settings) failing like a full disk; returns the progress lines up to it."""
    target = install_module.layout(home)[name]
    real_write = install_module._write_bytes
    progress = []

    def failing(path, data):
        if Path(path) == target:
            raise OSError(28, "No space left on device")
        real_write(path, data)

    install_module._write_bytes = failing
    try:
        with pytest.raises(OSError):
            install_module.install(home, force=force, progress=progress)
    finally:
        install_module._write_bytes = real_write
    return progress


def _interrupt_settings_write(install_module, home, force=False):
    """Run install(home) with the settings.json write failing like a full disk: the interim
    record, the hook and CLAUDE.md are written, settings.json and the final record are not."""
    settings_path = install_module.layout(home)["settings"]
    real_write = install_module._write_json

    def failing(path, data):
        if path == settings_path:
            raise OSError(28, "No space left on device")
        real_write(path, data)

    install_module._write_json = failing
    try:
        with pytest.raises(OSError):
            install_module.install(home, force=force)
    finally:
        install_module._write_json = real_write


def test_interrupt_at_the_final_record_is_undone_by_the_uninstall(install_module, tmp_path):
    # An interim record without the unfinished flag that said the install added nothing to
    # settings.json was believed after an interrupt at the final record (the last of the five
    # writes) while the file held every template key: the re-install recorded nothing (the
    # values were "the user's own") and the uninstall left the keys and wrote the clean
    # marker. The interim record lists what the run writes and is marked unfinished, so the
    # undo restores all of it, the deny tools and the containers the run made included.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    settings_file(home).write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    (claude / "CLAUDE.md").write_text("my own rules\n", encoding="utf-8")
    progress = []
    _interrupt(install_module, home, 2, progress)
    assert "settings.json written" in progress
    record = json.loads(install_module.layout(home)["record"].read_text(encoding="utf-8"))
    assert sorted(record) == sorted(INTERIM_FIELDS + ["claude_md"]), record
    deny = install_module._read_json(install_module.USER_SETTINGS)["permissions"]["deny"]
    assert record["deny_added"] == deny and record["created"] == [
        "permissions", "permissions.deny", "hooks", "hooks.UserPromptSubmit"], record
    uninstall_module = load_module("uninstall_module", "config/uninstall.py")
    changes, notices = uninstall_module.uninstall(home)
    assert json.loads(settings_file(home).read_text(encoding="utf-8")) == {"model": "opus"}, changes
    assert not any("did not finish" in n for n in notices), notices
    assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == "my own rules\n"
    assert not install_module.layout(home)["hook"].exists()
    assert json.loads(install_module.layout(home)["record"].read_text(encoding="utf-8")) == {"uninstalled": True}


def test_interrupt_at_the_final_record_over_a_marker_is_an_unfinished_record(install_module, tmp_path):
    # The interim record was the old record plus claude_md, so over the marker an uninstall
    # leaves ({"uninstalled": true}) it kept that key: the next uninstall read the record as
    # neither unfinished nor absent, removed the keys from the hook evidence but left the deny
    # tools with no notice at all. The marker key is not part of an install's record.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    settings_file(home).write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    (claude / "CLAUDE.md").write_text("my own rules\n", encoding="utf-8")
    install_module.install(home)
    uninstall_module = load_module("uninstall_module", "config/uninstall.py")
    uninstall_module.uninstall(home)
    record_path = install_module.layout(home)["record"]
    assert json.loads(record_path.read_text(encoding="utf-8")) == {"uninstalled": True}
    _interrupt(install_module, home, 2, [])
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert sorted(record) == sorted(INTERIM_FIELDS + ["claude_md"]), record
    changes, notices = uninstall_module.uninstall(home)
    assert not any("did not finish" in n for n in notices), notices
    assert json.loads(settings_file(home).read_text(encoding="utf-8")) == {"model": "opus"}, changes
    assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == "my own rules\n"
    assert json.loads(record_path.read_text(encoding="utf-8")) == {"uninstalled": True}


def test_interrupt_at_the_final_record_over_a_marker_with_a_leftover_key_is_an_unfinished_record(install_module, tmp_path):
    # The marker an uninstall leaves when a value was left as is also holds added_keys,
    # replaced, installed and created for that one key; carried into the interim record, they
    # made the record of an interrupted re-install read as a full one: the next uninstall undid
    # only the leftover key, and left the key the interrupted install added and the deny tools
    # in settings.json with no notice. The interim record keeps the leftovers (they are what a
    # later run has to put back) beside this run's data and says the install is unfinished.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    settings_file(home).write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    (claude / "CLAUDE.md").write_text("my own rules\n", encoding="utf-8")
    install_module.install(home)
    settings = json.loads(settings_file(home).read_text(encoding="utf-8"))
    settings["autoCompactWindow"] = 123456
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")
    uninstall_module = load_module("uninstall_module", "config/uninstall.py")
    _, notices = uninstall_module.uninstall(home)
    assert any("autoCompactWindow" in n and "left as is" in n for n in notices), notices
    record_path = install_module.layout(home)["record"]
    marker = json.loads(record_path.read_text(encoding="utf-8"))
    assert marker["uninstalled"] is True and marker["added_keys"] == ["autoCompactWindow"], marker
    _interrupt(install_module, home, 2, [])
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["unfinished"] is True, record
    assert record["added_keys"] == ["autoCompactWindow", "skillListingBudgetFraction"], record
    assert "uninstalled" not in record and "claude_md" in record
    changes, notices = uninstall_module.uninstall(home)
    settings = json.loads(settings_file(home).read_text(encoding="utf-8"))
    assert settings == {"model": "opus", "autoCompactWindow": 123456}, (settings, changes)
    assert any("autoCompactWindow" in n and "left as is" in n for n in notices), notices
    assert not any("did not finish" in n for n in notices), notices
    assert not install_module.layout(home)["hook"].exists()
    assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == "my own rules\n"
    # The marker this uninstall leaves keeps the fields of the key still left as is, and not
    # the unfinished flag, so a third run reads it as a marker.
    marker = json.loads(record_path.read_text(encoding="utf-8"))
    assert marker["uninstalled"] is True and marker["added_keys"] == ["autoCompactWindow"], marker
    assert "unfinished" not in marker


def test_interrupt_at_the_final_record_over_a_marker_with_only_the_hook_to_write_is_an_unfinished_record(install_module, tmp_path):
    # With CLAUDE.md equal to the template and settings.json already holding every value, the
    # run writes the hook and the final record only: the interim record is still written first,
    # so an interrupt at the final record leaves an unfinished record that lists nothing of
    # the values, and the uninstall names the template values it removes from the evidence
    # and the deny tools it leaves instead of doing either in silence.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    settings_file(home).write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    template_md = install_module._read_text(install_module.CLAUDE_MD)
    (claude / "CLAUDE.md").write_text(template_md, encoding="utf-8")
    install_module.install(home)
    full = settings_file(home).read_text(encoding="utf-8")
    uninstall_module = load_module("uninstall_module", "config/uninstall.py")
    uninstall_module.uninstall(home)
    record_path = install_module.layout(home)["record"]
    assert json.loads(record_path.read_text(encoding="utf-8")) == {"uninstalled": True}
    settings_file(home).write_text(full, encoding="utf-8")     # the user put every value back
    progress = []
    _interrupt(install_module, home, 2, progress)
    assert progress == ["hook written"], progress
    assert json.loads(record_path.read_text(encoding="utf-8")) == {
        "added_keys": [], "replaced": {}, "deny_added": [], "installed": {}, "created": [],
        "pre_write": [], "unfinished": True}
    changes, notices = uninstall_module.uninstall(home)
    template = install_module._read_json(install_module.USER_SETTINGS)
    keys = [k for k in template if k not in ("hooks", "permissions")]
    assert any("did not finish" in n and n.endswith("removed as without a record: " + ", ".join(keys))
               for n in notices), notices
    assert any("did not finish" in n and "permissions.deny" in n
               and n.endswith("left as is: " + ", ".join(template["permissions"]["deny"]))
               for n in notices), notices
    settings = json.loads(settings_file(home).read_text(encoding="utf-8"))
    assert all(k not in settings for k in keys), (settings, changes)
    assert settings["permissions"]["deny"] == template["permissions"]["deny"], settings


def test_interrupt_at_the_final_record_over_a_marker_without_a_claude_md_write_is_an_unfinished_record(install_module, tmp_path):
    # With CLAUDE.md already equal to the template no interim record was written at all, so an
    # interrupt at the final record left the marker itself while settings.json held the keys,
    # the deny tools and the hook entry: the next uninstall read the marker as neither
    # unfinished nor absent and left the deny tools with no notice. The interim record (this
    # run's data and the flag) is written before the first file whenever the run writes one.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    settings_file(home).write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    template_md = install_module._read_text(install_module.CLAUDE_MD)
    (claude / "CLAUDE.md").write_text(template_md, encoding="utf-8")
    install_module.install(home)
    uninstall_module = load_module("uninstall_module", "config/uninstall.py")
    _, notices = uninstall_module.uninstall(home)
    assert any("not written by this install" in n for n in notices), notices
    record_path = install_module.layout(home)["record"]
    assert json.loads(record_path.read_text(encoding="utf-8")) == {"uninstalled": True}
    progress = []
    _interrupt(install_module, home, 2, progress)
    assert "settings.json written" in progress, progress
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert sorted(record) == INTERIM_FIELDS, record
    changes, notices = uninstall_module.uninstall(home)
    assert not any("did not finish" in n for n in notices), notices
    assert json.loads(settings_file(home).read_text(encoding="utf-8")) == {"model": "opus"}, changes
    assert not install_module.layout(home)["hook"].exists()
    assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == template_md


def test_interrupt_at_the_interim_record_leaves_no_orphan_backup(install_module, tmp_path):
    # The backup of CLAUDE.md was made before the interim record that names it: an interrupt
    # at that record left a CLAUDE.md.bak-* nothing knew about, and the next install made a
    # second copy of the same file.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    (claude / "CLAUDE.md").write_text("my own rules\n", encoding="utf-8")
    progress = []
    _interrupt(install_module, home, 1, progress)
    assert not list(claude.glob("CLAUDE.md.bak-*")), list(claude.iterdir())
    assert not any("backup" in line for line in progress), progress
    install_module.install(home)
    assert len(list(claude.glob("CLAUDE.md.bak-*"))) == 1
    uninstall_module = load_module("uninstall_module", "config/uninstall.py")
    uninstall_module.uninstall(home)
    assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == "my own rules\n"
    assert not list(claude.glob("CLAUDE.md.bak-*")), list(claude.iterdir())


def test_interrupt_at_the_claude_md_write_reuses_the_recorded_backup(install_module, tmp_path, monkeypatch):
    # With the interim record written and the CLAUDE.md write interrupted, the user's file was
    # still there beside its backup; the next install saw a file that differed from the
    # record's hash and backed it up again, leaving two copies of the same file.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    (claude / "CLAUDE.md").write_text("my own rules\n", encoding="utf-8")
    real_write = install_module._write_bytes

    def failing_once(path, data):
        if Path(path).name == "CLAUDE.md":
            monkeypatch.setattr(install_module, "_write_bytes", real_write)
            raise OSError(28, "No space left on device")
        real_write(path, data)

    monkeypatch.setattr(install_module, "_write_bytes", failing_once)
    with pytest.raises(OSError):
        install_module.install(home)
    assert len(list(claude.glob("CLAUDE.md.bak-*"))) == 1
    changes, notices = install_module.install(home)
    assert len(list(claude.glob("CLAUDE.md.bak-*"))) == 1, list(claude.iterdir())
    assert not any("edits made after" in n for n in notices), notices
    uninstall_module = load_module("uninstall_module", "config/uninstall.py")
    changes, _ = uninstall_module.uninstall(home)
    assert any(c.startswith("CLAUDE.md restored from") for c in changes), changes
    assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == "my own rules\n"
    assert not list(claude.glob("CLAUDE.md.bak-*"))


@pytest.mark.skipif(ROOT_USER, reason="root writes into read-only folders")
@pytest.mark.skipif(os.name == "nt", reason="os.access does not see a Windows folder as read-only")
@pytest.mark.parametrize("folder", [".claude", ".claude/ballast"])
def test_a_read_only_folder_is_refused_before_any_write(install_module, tmp_path, capsys, folder):
    # Only the target files were checked for writability: a read-only .claude/ (or ballast/)
    # folder was found by the temp file of the first write into it, after the files before it
    # were written ("Done before the error"), on every attempt.
    home = tmp_path / "home"
    claude = home / ".claude"
    (claude / "ballast").mkdir(parents=True)
    settings_file(home).write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    target = home / folder
    target.chmod(0o555)
    try:
        for _ in range(2):
            assert install_module.main(["--home", str(home)]) == 1
            err = capsys.readouterr().err
            assert "read-only" in err and "nothing written" in err and "Traceback" not in err, err
            assert "Done before" not in err, err
        assert not install_module.layout(home)["hook"].exists()
        assert not (claude / "CLAUDE.md").exists()
        assert sorted(p.name for p in claude.iterdir()) == ["ballast", "settings.json"]
        assert json.loads(settings_file(home).read_text(encoding="utf-8")) == {"model": "opus"}
    finally:
        target.chmod(0o755)


def test_an_interrupted_re_install_over_a_marker_keeps_the_markers_leftovers(install_module, tmp_path):
    # The interim record written over a marker held nothing of it, so an interrupt at the
    # final record dropped the value a --force install had replaced and the uninstall had kept
    # for a later run: once the user put the installed value back, the undo removed the key
    # instead of restoring their own value. The interim record keeps the leftovers beside this
    # run's data and says the install is unfinished, so the undo restores what it lists.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    settings_file(home).write_text(json.dumps({"model": "opus", "autoCompactWindow": 100}), encoding="utf-8")
    (claude / "CLAUDE.md").write_text("my own rules\n", encoding="utf-8")
    install_module.install(home, force=True)
    template = install_module._read_json(install_module.USER_SETTINGS)
    settings = json.loads(settings_file(home).read_text(encoding="utf-8"))
    settings["autoCompactWindow"] = 123456
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")
    uninstall_module = load_module("uninstall_module", "config/uninstall.py")
    uninstall_module.uninstall(home)
    record_path = install_module.layout(home)["record"]
    marker = json.loads(record_path.read_text(encoding="utf-8"))
    assert marker["uninstalled"] is True and marker["replaced"] == {"autoCompactWindow": 100}, marker
    _interrupt(install_module, home, 2, [])
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["unfinished"] is True and record["replaced"] == {"autoCompactWindow": 100}, record
    assert "uninstalled" not in record and record["added_keys"] == ["skillListingBudgetFraction"], record
    settings = json.loads(settings_file(home).read_text(encoding="utf-8"))
    settings["autoCompactWindow"] = template["autoCompactWindow"]   # the user put it back
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")
    changes, notices = uninstall_module.uninstall(home)
    settings = json.loads(settings_file(home).read_text(encoding="utf-8"))
    assert settings == {"model": "opus", "autoCompactWindow": 100}, (settings, changes)
    assert not any("did not finish" in n for n in notices), notices
    assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == "my own rules\n"
    assert json.loads(record_path.read_text(encoding="utf-8")) == {"uninstalled": True}


def test_an_interrupted_re_install_over_a_marker_keeps_a_pending_claude_md_backup(install_module, tmp_path):
    # A marker keeps the CLAUDE.md entry when its backup was missing at uninstall time, so a
    # later run can still restore it; the interim record of a re-install dropped that entry,
    # and after an interrupt at the final record the undo called the installer's own CLAUDE.md
    # "not written by this install" and left it, with the backup back on disk.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    settings_file(home).write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    (claude / "CLAUDE.md").write_text("my own rules\n", encoding="utf-8")
    install_module.install(home)
    record_path = install_module.layout(home)["record"]
    backup_name = json.loads(record_path.read_text(encoding="utf-8"))["claude_md"]["backup"]
    stash = (claude / backup_name).read_bytes()
    (claude / backup_name).unlink()
    uninstall_module = load_module("uninstall_module", "config/uninstall.py")
    _, notices = uninstall_module.uninstall(home)
    assert any("missing" in n for n in notices), notices
    marker = json.loads(record_path.read_text(encoding="utf-8"))
    assert marker["claude_md"]["backup"] == backup_name, marker
    progress = []
    _interrupt(install_module, home, 2, progress)
    assert "settings.json written" in progress, progress
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["claude_md"] == marker["claude_md"] and record["unfinished"] is True, record
    (claude / backup_name).write_bytes(stash)
    changes, notices = uninstall_module.uninstall(home)
    assert any(c.startswith("CLAUDE.md restored from") for c in changes), (changes, notices)
    assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == "my own rules\n"
    assert not any("not written by this install" in n for n in notices), notices


def test_interrupt_at_the_interim_record_over_a_marker_writes_nothing_before_it(install_module, tmp_path):
    # Over a marker with a CLAUDE.md write the hook was written before the interim record, so
    # a failure at that record left the hook beside the untouched marker: the next uninstall
    # took the hook as evidence, removed the keys and left the deny tools with no notice. The
    # interim record is the run's first write in every case.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    settings_file(home).write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    install_module.install(home)
    full = settings_file(home).read_text(encoding="utf-8")
    uninstall_module = load_module("uninstall_module", "config/uninstall.py")
    uninstall_module.uninstall(home)
    assert not (claude / "CLAUDE.md").exists()
    record_path = install_module.layout(home)["record"]
    assert json.loads(record_path.read_text(encoding="utf-8")) == {"uninstalled": True}
    settings_file(home).write_text(full, encoding="utf-8")     # the user put every value back
    progress = []
    _interrupt(install_module, home, 1, progress)
    assert progress == [], progress
    assert not install_module.layout(home)["hook"].exists()
    assert not (claude / "CLAUDE.md").exists()
    assert json.loads(record_path.read_text(encoding="utf-8")) == {"uninstalled": True}


def test_a_re_install_over_an_unfinished_record_completes_it(install_module, tmp_path):
    # After an interrupt at the final record, running the installer again found nothing to
    # change and left the unfinished record as it was, so the undo could only ever remove the
    # template values "as without a record". The re-run writes the full record; the interim
    # record already lists everything, so nothing is left to claim or to name.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    settings_file(home).write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    (claude / "CLAUDE.md").write_text("my own rules\n", encoding="utf-8")
    _interrupt(install_module, home, 2, [])
    record_path = install_module.layout(home)["record"]
    assert json.loads(record_path.read_text(encoding="utf-8"))["unfinished"] is True
    template = install_module._read_json(install_module.USER_SETTINGS)
    changes, notices = install_module.install(home)
    assert (changes, notices) == (["install record completed"], []), (changes, notices)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    keys = [k for k in template if k not in ("hooks", "permissions")]
    assert "unfinished" not in record and sorted(record["added_keys"]) == sorted(keys), record
    assert record["installed"] == {k: template[k] for k in keys}
    assert record["deny_added"] == template["permissions"]["deny"]
    assert install_module.install(home) == ([], [])
    uninstall_module = load_module("uninstall_module", "config/uninstall.py")
    changes, notices = uninstall_module.uninstall(home)
    assert json.loads(settings_file(home).read_text(encoding="utf-8")) == {"model": "opus"}, changes
    assert not any("did not finish" in n for n in notices), notices
    assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == "my own rules\n"


def test_a_completing_re_run_keeps_the_containers_it_made(install_module, tmp_path):
    # Completing a record from before it carried the run's data (one without "created")
    # dropped the containers field, since who made the ones the interrupted install filled is
    # unknown; it dropped it even when this run made them itself, so the undo deleted the
    # permissions object the user had. The field stays when this run created anything.
    home = tmp_path / "home"
    paths = install_module.layout(home)
    paths["record"].parent.mkdir(parents=True)
    settings_file(home).write_text(json.dumps({"model": "opus", "permissions": {}}), encoding="utf-8")
    paths["record"].write_text(json.dumps({"unfinished": True}), encoding="utf-8")
    install_module.install(home)
    record = json.loads(paths["record"].read_text(encoding="utf-8"))
    assert record["created"] == ["permissions.deny", "hooks", "hooks.UserPromptSubmit"], record
    uninstall_module = load_module("uninstall_module", "config/uninstall.py")
    changes, _ = uninstall_module.uninstall(home)
    assert json.loads(settings_file(home).read_text(encoding="utf-8")) == {
        "model": "opus", "permissions": {}}, changes
    # The interrupted install made the containers: this run makes none, and the field is
    # dropped so the undo removes the ones it empties, as for a record from before it (the
    # deny tools such a record cannot claim stay, and keep their container).
    install_module.install(home)
    full = settings_file(home).read_text(encoding="utf-8")
    uninstall_module.uninstall(home)
    settings_file(home).write_text(full, encoding="utf-8")
    paths["record"].write_text(json.dumps({"unfinished": True}), encoding="utf-8")
    install_module.install(home)
    record = json.loads(paths["record"].read_text(encoding="utf-8"))
    assert "created" not in record, record
    changes, _ = uninstall_module.uninstall(home)
    template = install_module._read_json(install_module.USER_SETTINGS)
    assert json.loads(settings_file(home).read_text(encoding="utf-8")) == {
        "model": "opus", "permissions": {"deny": template["permissions"]["deny"]}}, changes


@pytest.mark.parametrize("re_run", [False, True])
def test_a_force_install_interrupted_at_the_final_record_keeps_the_replaced_value(install_module, tmp_path, re_run):
    # The interim record carried nothing of the run, so a --force install interrupted at the
    # final record lost the value it replaced: the undo removed the key as one judged from the
    # evidence, and a re-run claimed it as added. The interim record lists the replaced value.
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    settings_file(home).write_text(json.dumps({"model": "opus", "autoCompactWindow": 100}), encoding="utf-8")
    _interrupt(install_module, home, 2, [], force=True)
    record_path = install_module.layout(home)["record"]
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["unfinished"] is True and record["replaced"] == {"autoCompactWindow": 100}, record
    assert record["installed"]["autoCompactWindow"] != 100 and record["added_keys"] == ["skillListingBudgetFraction"]
    if re_run:
        changes, notices = install_module.install(home)
        assert (changes, notices) == (["install record completed"], []), (changes, notices)
        record = json.loads(record_path.read_text(encoding="utf-8"))
        assert "unfinished" not in record and record["replaced"] == {"autoCompactWindow": 100}, record
    uninstall_module = load_module("uninstall_module", "config/uninstall.py")
    changes, notices = uninstall_module.uninstall(home)
    assert "autoCompactWindow: restored 100" in changes, (changes, notices)
    assert json.loads(settings_file(home).read_text(encoding="utf-8")) == {
        "model": "opus", "autoCompactWindow": 100}, changes


def test_a_force_install_interrupted_before_the_settings_write_leaves_the_users_value_alone(install_module, tmp_path):
    # The interim record lists the value --force replaces before settings.json is written: an
    # interrupt in between leaves the user's value in place, and the undo has nothing to put
    # back for it (no "not the installed value" notice, nothing kept in the marker).
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    settings_file(home).write_text(json.dumps({"model": "opus", "autoCompactWindow": 100}), encoding="utf-8")
    _interrupt_settings_write(install_module, home, force=True)
    record_path = install_module.layout(home)["record"]
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["unfinished"] is True and record["replaced"] == {"autoCompactWindow": 100}, record
    uninstall_module = load_module("uninstall_module", "config/uninstall.py")
    changes, notices = uninstall_module.uninstall(home)
    assert json.loads(settings_file(home).read_text(encoding="utf-8")) == {
        "model": "opus", "autoCompactWindow": 100}, changes
    assert not any("autoCompactWindow" in n for n in notices), notices
    assert not any("autoCompactWindow" in c for c in changes), changes
    assert json.loads(record_path.read_text(encoding="utf-8")) == {"uninstalled": True}


def test_completing_a_record_refreshes_the_installed_value_of_a_listed_key(install_module, tmp_path, monkeypatch):
    # The template changed and the re-install that wrote the new value was interrupted at the
    # final record. Completing a record from before it carried the run's data skipped every
    # key the record already listed, so "installed" kept the old value and the undo left the
    # new one as "not the installed value".
    home = tmp_path / "home"
    install_module.install(home)
    paths = install_module.layout(home)
    template = install_module._read_json(install_module.USER_SETTINGS)
    template["autoCompactWindow"] = 300000
    newer = tmp_path / "user-settings.json"
    newer.write_text(json.dumps(template), encoding="utf-8")
    monkeypatch.setattr(install_module, "USER_SETTINGS", newer)
    settings = json.loads(settings_file(home).read_text(encoding="utf-8"))
    settings["autoCompactWindow"] = 300000                  # what the interrupted run wrote
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")
    record = json.loads(paths["record"].read_text(encoding="utf-8"))
    assert record["installed"]["autoCompactWindow"] != 300000
    record["unfinished"] = True                             # ... before its final record
    paths["record"].write_text(json.dumps(record), encoding="utf-8")
    changes, notices = install_module.install(home)
    assert changes == ["install record completed"], (changes, notices)
    assert notices == ["the install record did not finish (an earlier install stopped before its "
                       "last write); the template values in settings.json are recorded as "
                       "installed: autoCompactWindow"], notices
    record = json.loads(paths["record"].read_text(encoding="utf-8"))
    assert record["installed"]["autoCompactWindow"] == 300000 and record["added_keys"] == [
        "autoCompactWindow", "skillListingBudgetFraction"], record
    uninstall_module = load_module("uninstall_module", "config/uninstall.py")
    monkeypatch.setattr(uninstall_module.install, "USER_SETTINGS", newer)
    changes, notices = uninstall_module.uninstall(home)
    assert json.loads(settings_file(home).read_text(encoding="utf-8")) == {}, (changes, notices)


def test_completing_a_record_names_what_it_claims_and_what_it_cannot(install_module, tmp_path):
    # The notice said the deny tools "are not recorded" whatever the record held, and that the
    # template values "are recorded" when none were: it names the keys it records, and the
    # template deny tools it cannot claim (the user's own tools are theirs, and not named).
    home = tmp_path / "home"
    paths = install_module.layout(home)
    install_module.install(home)
    full = json.loads(settings_file(home).read_text(encoding="utf-8"))
    template = install_module._read_json(install_module.USER_SETTINGS)
    full["permissions"]["deny"].append("MyOwnTool")
    settings_file(home).write_text(json.dumps(full), encoding="utf-8")
    paths["record"].write_text(json.dumps({"unfinished": True}), encoding="utf-8")
    changes, notices = install_module.install(home)
    assert changes == ["install record completed"], (changes, notices)
    assert notices == ["the install record did not finish (an earlier install stopped before its "
                       "last write); the template values in settings.json are recorded as "
                       "installed: autoCompactWindow, skillListingBudgetFraction; permissions.deny "
                       "tools it does not list are not claimed, remove any that are not yours by "
                       "hand: " + ", ".join(template["permissions"]["deny"])], notices
    # A record that already lists everything has nothing to say.
    record = json.loads(paths["record"].read_text(encoding="utf-8"))
    record["unfinished"] = True
    record["deny_added"] = template["permissions"]["deny"]
    paths["record"].write_text(json.dumps(record), encoding="utf-8")
    assert install_module.install(home) == (["install record completed"], [])


def test_an_interrupted_re_install_over_a_marker_lists_only_the_containers_it_made(install_module, tmp_path):
    # The interim record copied the marker's "created" list, which names the containers the
    # uninstall deleted: after an interrupt at the final record, the undo deleted a hooks
    # object the user had made by hand since. The interim record lists this run's containers.
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    settings_file(home).write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    install_module.install(home)
    uninstall_module = load_module("uninstall_module", "config/uninstall.py")
    uninstall_module.uninstall(home)
    record_path = install_module.layout(home)["record"]
    assert json.loads(record_path.read_text(encoding="utf-8")) == {"uninstalled": True}
    settings_file(home).write_text(json.dumps({"model": "opus", "hooks": {}}), encoding="utf-8")
    _interrupt(install_module, home, 2, [])
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["created"] == ["permissions", "permissions.deny", "hooks.UserPromptSubmit"], record
    changes, _ = uninstall_module.uninstall(home)
    assert json.loads(settings_file(home).read_text(encoding="utf-8")) == {"model": "opus", "hooks": {}}, changes


def test_a_record_with_only_deny_tools_is_finished_to_the_install_and_the_uninstall(install_module, tmp_path):
    # install.py counted deny_added as install data and uninstall.py did not, so a record
    # holding only deny tools was finished to the one and unfinished to the other: the undo
    # removed template values it did not list "as without a record". One tuple serves both.
    uninstall_module = load_module("uninstall_module", "config/uninstall.py")
    assert uninstall_module.install.INSTALL_DATA == install_module.INSTALL_DATA
    assert not uninstall_module._is_unfinished({"deny_added": [], "created": []})
    assert not uninstall_module._is_unfinished({"uninstalled": True})
    assert uninstall_module._is_unfinished({"uninstalled": True, "unfinished": True})
    assert uninstall_module._is_unfinished({"claude_md": {"backup": None, "sha256": "x"}})
    home = tmp_path / "home"
    install_module.install(home)
    paths = install_module.layout(home)
    template = install_module._read_json(install_module.USER_SETTINGS)
    paths["record"].write_text(json.dumps({"deny_added": template["permissions"]["deny"], "created": []}),
                               encoding="utf-8")
    changes, notices = install_module.install(home)
    assert (changes, notices) == ([], []), (changes, notices)
    changes, notices = uninstall_module.uninstall(home)
    settings = json.loads(settings_file(home).read_text(encoding="utf-8"))
    assert settings["autoCompactWindow"] == template["autoCompactWindow"], (settings, changes)
    assert not any("did not finish" in n for n in notices), notices


@pytest.mark.parametrize("re_run", [False, True])
def test_a_template_change_interrupted_before_the_settings_write_keeps_the_earlier_value_as_installed(install_module, tmp_path, monkeypatch, re_run):
    # The interim record is the final record marked unfinished, so it listed the new template
    # value as installed before the settings write happened. An interrupt in between left
    # settings.json at the earlier install's value: the undo said "not the installed value;
    # left as is" and kept the key, and a plain re-run said "use --force" about a value the
    # installer itself had written. The interim lists the value the key holds until the run
    # writes it; the write the run got to is told from the template value.
    home = tmp_path / "home"
    install_module.install(home)
    paths = install_module.layout(home)
    template = install_module._read_json(install_module.USER_SETTINGS)
    template["autoCompactWindow"] = 300000
    newer = tmp_path / "user-settings.json"
    newer.write_text(json.dumps(template), encoding="utf-8")
    monkeypatch.setattr(install_module, "USER_SETTINGS", newer)
    _interrupt_settings_write(install_module, home)
    record = json.loads(paths["record"].read_text(encoding="utf-8"))
    assert record["unfinished"] is True and record["installed"]["autoCompactWindow"] != 300000, record
    assert json.loads(settings_file(home).read_text(encoding="utf-8"))["autoCompactWindow"] != 300000
    if re_run:
        changes, notices = install_module.install(home)
        assert notices == [] and "(template changed)" in " ".join(changes), (changes, notices)
        assert json.loads(settings_file(home).read_text(encoding="utf-8"))["autoCompactWindow"] == 300000
        record = json.loads(paths["record"].read_text(encoding="utf-8"))
        assert "unfinished" not in record and record["installed"]["autoCompactWindow"] == 300000, record
    uninstall_module = load_module("uninstall_module", "config/uninstall.py")
    monkeypatch.setattr(uninstall_module.install, "USER_SETTINGS", newer)
    changes, notices = uninstall_module.uninstall(home)
    assert notices == [] and "autoCompactWindow: removed" in changes, (changes, notices)
    assert json.loads(settings_file(home).read_text(encoding="utf-8")) == {}, changes
    assert json.loads(paths["record"].read_text(encoding="utf-8")) == {"uninstalled": True}


def test_a_template_change_interrupted_at_the_final_record_is_undone_from_the_template_value(install_module, tmp_path, monkeypatch):
    # The twin of the case above: the run wrote the new template value and was interrupted at
    # the final record, so settings.json holds a value the interim record does not list as
    # installed. A listed key holding the template value under an unfinished record was
    # written by the interrupted run: it is removed, not left as "not the installed value".
    home = tmp_path / "home"
    install_module.install(home)
    template = install_module._read_json(install_module.USER_SETTINGS)
    template["autoCompactWindow"] = 300000
    newer = tmp_path / "user-settings.json"
    newer.write_text(json.dumps(template), encoding="utf-8")
    monkeypatch.setattr(install_module, "USER_SETTINGS", newer)
    _interrupt(install_module, home, 2, [])
    assert json.loads(settings_file(home).read_text(encoding="utf-8"))["autoCompactWindow"] == 300000
    # The interim record left behind lists the key with the value it held before the write,
    # and names it as such: that is what tells the undo that the template value is the run's.
    record = json.loads(install_module.layout(home)["record"].read_text(encoding="utf-8"))
    assert record["pre_write"] == ["autoCompactWindow"], record
    assert record["installed"]["autoCompactWindow"] != 300000, record
    uninstall_module = load_module("uninstall_module", "config/uninstall.py")
    monkeypatch.setattr(uninstall_module.install, "USER_SETTINGS", newer)
    changes, notices = uninstall_module.uninstall(home)
    assert notices == [] and "autoCompactWindow: removed" in changes, (changes, notices)
    assert json.loads(settings_file(home).read_text(encoding="utf-8")) == {}, changes


def test_the_pre_write_list_survives_an_undo_that_found_settings_json_missing(install_module, tmp_path, monkeypatch):
    # The same interrupt, with settings.json missing when the undo first runs: the marker it
    # left kept the listed key with its pre-write value and the unfinished flag, but not the
    # pre_write list, so the run that found the file back read the template value as the
    # user's own ("not the installed value; left as is") and kept the key for good.
    home = tmp_path / "home"
    install_module.install(home)
    template = install_module._read_json(install_module.USER_SETTINGS)
    template["autoCompactWindow"] = 300000
    newer = tmp_path / "user-settings.json"
    newer.write_text(json.dumps(template), encoding="utf-8")
    monkeypatch.setattr(install_module, "USER_SETTINGS", newer)
    _interrupt(install_module, home, 2, [])
    uninstall_module = load_module("uninstall_module", "config/uninstall.py")
    monkeypatch.setattr(uninstall_module.install, "USER_SETTINGS", newer)
    full = settings_file(home).read_text(encoding="utf-8")
    settings_file(home).unlink()
    uninstall_module.uninstall(home)
    record = json.loads(install_module.layout(home)["record"].read_text(encoding="utf-8"))
    assert record["pre_write"] == ["autoCompactWindow"] and record["unfinished"] is True, record
    settings_file(home).write_text(full, encoding="utf-8")
    changes, notices = uninstall_module.uninstall(home)
    assert notices == [] and "autoCompactWindow: removed" in changes, (changes, notices)
    assert json.loads(settings_file(home).read_text(encoding="utf-8")) == {}, changes
    assert json.loads(install_module.layout(home)["record"].read_text(encoding="utf-8")) == {"uninstalled": True}


def test_completing_a_record_drops_a_replacement_the_interrupted_run_never_wrote(install_module, tmp_path):
    # A --force install interrupted before the settings write lists the user's value as
    # replaced; a plain re-run cannot replace it (no --force), but the completed record kept
    # the claim and the new value as installed, so the undo said "not the installed value;
    # left as is" about the user's own value and the marker carried the claim for good. A
    # listed replacement whose key still holds the replaced value, and which this run does not
    # make, never happened: it is dropped.
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    settings_file(home).write_text(json.dumps({"model": "opus", "autoCompactWindow": 100}), encoding="utf-8")
    _interrupt_settings_write(install_module, home, force=True)
    record_path = install_module.layout(home)["record"]
    changes, notices = install_module.install(home)
    assert notices == ["autoCompactWindow is 100, template has 250000; left unchanged (use --force)"], notices
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert "unfinished" not in record and record["replaced"] == {}, record
    assert "autoCompactWindow" not in record["installed"] and "autoCompactWindow" not in record["added_keys"], record
    uninstall_module = load_module("uninstall_module", "config/uninstall.py")
    changes, notices = uninstall_module.uninstall(home)
    assert not any("autoCompactWindow" in n for n in notices), notices
    assert json.loads(settings_file(home).read_text(encoding="utf-8")) == {"model": "opus", "autoCompactWindow": 100}
    assert json.loads(record_path.read_text(encoding="utf-8")) == {"uninstalled": True}
    # A --force re-run replaces it afresh, and the undo puts it back.
    install_module.install(home, force=True)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["replaced"] == {"autoCompactWindow": 100}, record
    uninstall_module.uninstall(home)
    assert json.loads(settings_file(home).read_text(encoding="utf-8")) == {"model": "opus", "autoCompactWindow": 100}


def test_a_re_install_over_a_marker_that_stayed_unfinished_keeps_the_containers_it_lists(install_module, tmp_path):
    # An uninstall that found settings.json missing keeps the record unfinished with the
    # containers the interrupted install made. The re-install over that marker took its own
    # list of containers (none: they exist), as over a clean marker, so the later undo left
    # the emptied containers behind. A marker that never undid settings.json keeps its list.
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    settings_file(home).write_text(json.dumps({"model": "opus", "autoCompactWindow": 100}), encoding="utf-8")
    _interrupt(install_module, home, 2, [], force=True)
    paths = install_module.layout(home)
    full = settings_file(home).read_text(encoding="utf-8")
    settings_file(home).unlink()
    uninstall_module = load_module("uninstall_module", "config/uninstall.py")
    uninstall_module.uninstall(home)
    marker = json.loads(paths["record"].read_text(encoding="utf-8"))
    assert marker["uninstalled"] is True and marker["unfinished"] is True and marker["created"], marker
    settings_file(home).write_text(full, encoding="utf-8")
    install_module.install(home)
    record = json.loads(paths["record"].read_text(encoding="utf-8"))
    assert record["created"] == marker["created"], record
    changes, notices = uninstall_module.uninstall(home)
    assert json.loads(settings_file(home).read_text(encoding="utf-8")) == {
        "model": "opus", "autoCompactWindow": 100}, (changes, notices)


def test_a_re_install_after_an_interrupted_settings_write_reuses_the_recorded_settings_backup(install_module, tmp_path):
    # The copy an install makes of settings.json before replacing it was made after the
    # interim record, so an interrupt at the settings write left a copy nothing recorded and
    # nothing removed. The copy is made first and named in the interim record; the run that
    # completes the install reuses it while it still equals the file, rather than making a
    # second copy of the same file.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    settings_file(home).write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    _interrupt_settings_write(install_module, home)
    paths = install_module.layout(home)
    copies = sorted(claude.glob("settings.json.bak-*"))
    record = json.loads(paths["record"].read_text(encoding="utf-8"))
    assert len(copies) == 1 and record["settings_backup"] == copies[0].name, (copies, record)
    changes, notices = install_module.install(home)
    # The line names the copy as reused: the run made none, so "settings backup: <name>"
    # alone would report a copy that was there before it.
    assert f"settings backup: {copies[0].name} (reused)" in changes, changes
    assert f"settings backup: {copies[0].name}" not in changes, changes
    assert sorted(claude.glob("settings.json.bak-*")) == copies
    assert copies[0].read_text(encoding="utf-8") == json.dumps({"model": "opus"})
    record = json.loads(paths["record"].read_text(encoding="utf-8"))
    assert "unfinished" not in record and "settings_backup" not in record, record


def test_completing_a_record_keeps_a_replacement_when_the_template_moved_to_the_replaced_value(install_module, tmp_path, monkeypatch):
    # The drop of a replacement the interrupted --force run never wrote looked only at the key
    # still holding the replaced value. When the template has since moved to that very value,
    # the key holds it as the user's own and as the template's at once: the drop removed the
    # claim, the completion loop then recorded the user's value as added and installed, and
    # the undo removed it. A key whose value is also the template's keeps the replaced claim
    # (the installed value is refreshed to it), so the undo puts the user's value back.
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    settings_file(home).write_text(json.dumps({"model": "opus", "autoCompactWindow": 100}), encoding="utf-8")
    _interrupt_settings_write(install_module, home, force=True)
    paths = install_module.layout(home)
    template = install_module._read_json(install_module.USER_SETTINGS)
    template["autoCompactWindow"] = 100
    newer = tmp_path / "user-settings.json"
    newer.write_text(json.dumps(template), encoding="utf-8")
    monkeypatch.setattr(install_module, "USER_SETTINGS", newer)
    changes, notices = install_module.install(home)
    record = json.loads(paths["record"].read_text(encoding="utf-8"))
    assert "unfinished" not in record and record["replaced"] == {"autoCompactWindow": 100}, record
    assert "autoCompactWindow" not in record["added_keys"], record
    uninstall_module = load_module("uninstall_module", "config/uninstall.py")
    monkeypatch.setattr(uninstall_module.install, "USER_SETTINGS", newer)
    changes, notices = uninstall_module.uninstall(home)
    assert not any("autoCompactWindow" in n for n in notices), notices
    assert json.loads(settings_file(home).read_text(encoding="utf-8")) == {"model": "opus", "autoCompactWindow": 100}
    assert json.loads(paths["record"].read_text(encoding="utf-8")) == {"uninstalled": True}


def test_a_kept_replacement_guards_the_users_value_from_a_later_template_change(install_module, tmp_path, monkeypatch):
    # The same drop after a finished --force install: a later plain run (the hook was deleted)
    # is interrupted at the hook write with the old record's replaced claim in its interim;
    # the template moves to the user's value, and the completing re-run writes it as a
    # template change and dropped the claim. The next template change was then written over
    # the user's value without --force (the key held "the installed value") and the undo had
    # nothing to put back. The claim stays, and the undo restores the user's value.
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    settings_file(home).write_text(json.dumps({"model": "opus", "autoCompactWindow": 100}), encoding="utf-8")
    install_module.install(home, force=True)
    paths = install_module.layout(home)
    paths["hook"].unlink()
    _interrupt_write(install_module, home, "hook")
    template = install_module._read_json(install_module.USER_SETTINGS)
    newer = tmp_path / "user-settings.json"
    monkeypatch.setattr(install_module, "USER_SETTINGS", newer)
    template["autoCompactWindow"] = 100
    newer.write_text(json.dumps(template), encoding="utf-8")
    changes, notices = install_module.install(home)
    assert "autoCompactWindow: 250000 -> 100 (template changed)" in changes, changes
    record = json.loads(paths["record"].read_text(encoding="utf-8"))
    assert record["replaced"] == {"autoCompactWindow": 100} and "unfinished" not in record, record
    template["autoCompactWindow"] = 777
    newer.write_text(json.dumps(template), encoding="utf-8")
    install_module.install(home)
    uninstall_module = load_module("uninstall_module", "config/uninstall.py")
    monkeypatch.setattr(uninstall_module.install, "USER_SETTINGS", newer)
    changes, notices = uninstall_module.uninstall(home)
    assert "autoCompactWindow: restored 100" in changes, (changes, notices)
    assert json.loads(settings_file(home).read_text(encoding="utf-8")) == {"model": "opus", "autoCompactWindow": 100}


def test_a_re_run_after_you_edited_settings_json_removes_the_copy_the_interrupted_run_made(install_module, tmp_path):
    # A run interrupted at the hook write had copied settings.json and named the copy in the
    # interim record. With the file edited since, the re-run found the copy differing, made a
    # fresh one and named only that: the first stayed beside the file, named nowhere. A copy
    # of a file the interrupted run never got to replace (every key it lists is still as it
    # was before the write) is removed once the fresh copy is recorded, and the run says so.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    settings_file(home).write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    _interrupt_write(install_module, home, "hook")
    copies = sorted(claude.glob("settings.json.bak-*"))
    assert len(copies) == 1, copies
    settings_file(home).write_text(json.dumps({"model": "opus", "customKey": "mine"}), encoding="utf-8")
    changes, notices = install_module.install(home)
    after = sorted(claude.glob("settings.json.bak-*"))
    assert len(after) == 1 and after != copies, (copies, after, changes)
    assert f"settings.json backup {copies[0].name} removed (the interrupted install never replaced " \
           "settings.json)" in changes, changes
    assert f"settings backup: {after[0].name}" in changes, changes
    assert after[0].read_text(encoding="utf-8") == json.dumps({"model": "opus", "customKey": "mine"})
    record = json.loads(install_module.layout(home)["record"].read_text(encoding="utf-8"))
    assert "unfinished" not in record and "settings_backup" not in record, record
    settings = json.loads(settings_file(home).read_text(encoding="utf-8"))
    assert settings["customKey"] == "mine" and "autoCompactWindow" in settings, settings


def test_a_copy_that_differs_after_the_settings_write_is_kept_by_the_re_run(install_module, tmp_path):
    # The twin: the interrupt came at the final record, after the settings write, so the copy
    # the interim names is the backup of the file the run replaced. It differs from the file
    # and is not a stale pre-write copy: the re-run keeps it, as it keeps any finished
    # install's backup, and says nothing about it.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    settings_file(home).write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    _interrupt(install_module, home, 2, [])
    copies = sorted(claude.glob("settings.json.bak-*"))
    assert len(copies) == 1 and copies[0].read_text(encoding="utf-8") == json.dumps({"model": "opus"})
    changes, notices = install_module.install(home)
    assert not any("removed" in c for c in changes), changes
    assert sorted(claude.glob("settings.json.bak-*")) == copies


@pytest.mark.parametrize("which", ["settings.json", "CLAUDE.md"])
def test_a_failed_copy_leaves_no_unrecorded_copy_of_the_other_file(install_module, tmp_path, monkeypatch, which):
    # The copy of settings.json was made after the copy of CLAUDE.md and before the interim
    # record that names both: a settings copy that failed (disk full) left the CLAUDE.md copy
    # on disk with nothing recording it, and the next run made a second copy of the same
    # file. A copy whose record is never written is removed again, whichever copy failed.
    import shutil
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    settings_file(home).write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    (claude / "CLAUDE.md").write_text("mine\n", encoding="utf-8")
    real_copy2 = shutil.copy2

    def failing_copy2(src, dst, *args, **kwargs):
        if Path(src).name == which:
            raise OSError(28, "No space left on device")
        return real_copy2(src, dst, *args, **kwargs)

    monkeypatch.setattr(shutil, "copy2", failing_copy2)
    progress = []
    with pytest.raises(OSError):
        install_module.install(home, progress=progress)
    monkeypatch.undo()
    assert progress == [] and not list(claude.glob("*.bak-*")), (progress, list(claude.iterdir()))
    assert not install_module.layout(home)["record"].exists()
    install_module.install(home)
    assert len(list(claude.glob("CLAUDE.md.bak-*"))) == 1 and len(list(claude.glob("settings.json.bak-*"))) == 1


def test_a_claude_md_backup_name_the_installer_never_writes_is_not_reused(install_module, tmp_path):
    # The record's backup name was taken as the copy to reuse when it was a plain file name
    # and the file equalled CLAUDE.md: the name "CLAUDE.md" passed both (the file equals
    # itself), so the install wrote the template over the user's edits with "their" backup
    # being the file it had just replaced. Only a name the installer writes (CLAUDE.md.bak-*)
    # is a copy to reuse.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    (claude / "CLAUDE.md").write_text("mine\n", encoding="utf-8")
    install_module.install(home)
    record_path = install_module.layout(home)["record"]
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["claude_md"]["backup"] = "CLAUDE.md"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    (claude / "CLAUDE.md").write_text("edited after the install\n", encoding="utf-8")
    changes, notices = install_module.install(home)
    copies = [c for c in changes if c.startswith("CLAUDE.md backup: CLAUDE.md.bak-")]
    assert len(copies) == 1, changes
    backup = claude / copies[0].split(": ", 1)[1]
    assert backup.read_text(encoding="utf-8") == "edited after the install\n"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["claude_md"]["backup"] == backup.name, record


@pytest.mark.parametrize("name", ["settings.json", "settings.local.json"])
def test_a_settings_copy_name_the_installer_never_writes_is_not_reused(install_module, tmp_path, name):
    # The same for the copy of settings.json an unfinished record names: "settings.json" or a
    # sibling of equal content passed the plain-name and content checks, so the run made no
    # copy and wrote settings.json with the record naming the file as the copy of itself.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    settings_file(home).write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    _interrupt_settings_write(install_module, home)
    record_path = install_module.layout(home)["record"]
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["settings_backup"] = name
    record_path.write_text(json.dumps(record), encoding="utf-8")
    (claude / "settings.local.json").write_bytes(settings_file(home).read_bytes())
    changes, notices = install_module.install(home)
    fresh = [c for c in changes if c.startswith("settings backup: settings.json.bak-")]
    assert len(fresh) == 1 and not fresh[0].endswith("(reused)"), changes
    assert f"settings backup: {name}" not in changes, changes
    assert (claude / "settings.local.json").read_text(encoding="utf-8") == json.dumps({"model": "opus"})
    assert "autoCompactWindow" in json.loads(settings_file(home).read_text(encoding="utf-8"))
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert "unfinished" not in record and "settings_backup" not in record, record
