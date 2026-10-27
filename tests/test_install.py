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
    record = install_module.read_record(paths["record"]) or {}
    assert not any(record.get(k) for k in ("added_keys", "replaced", "deny_added", "installed"))
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
