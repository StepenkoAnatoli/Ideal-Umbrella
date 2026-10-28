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

    # The user's own rules stay; the template is added below them as a marked section.
    assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == "my own rules\n\n" + install_module.section_text(
        (ROOT / "config" / "CLAUDE.md").read_text(encoding="utf-8"))
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


@pytest.mark.parametrize("record, ok", [(None, True), ("{not json", False)], ids=["no-record", "corrupt-record"])
def test_verify_only_does_not_need_a_readable_record(install_module, tmp_path, capsys, record, ok):
    # Review 32, finding L2: --verify-only does not check the record, so a deleted one still
    # verifies, and a corrupt one (here with no hooks in settings.json, so verify() binds no
    # other entry first) gives the verification's own result, not a traceback.
    home = tmp_path / "home"
    install_module.install(home)
    path = install_module.layout(home)["record"]
    if record is None:
        path.unlink()
    else:
        path.write_text(record, encoding="utf-8")
        settings_file(home).write_text("{}\n", encoding="utf-8")
    capsys.readouterr()
    assert install_module.main(["--home", str(home), "--verify-only"]) == (0 if ok else 1)
    out = capsys.readouterr().out
    assert ("[OK] Installation verified" if ok else "[FAIL] Verification failed") in out, out


def test_verify_only_does_not_create_files(install_module, tmp_path, capsys):
    home = tmp_path / "home"
    assert install_module.main(["--home", str(home), "--verify-only"]) == 1
    assert not (home / ".claude").exists()
    assert "[FAIL] Verification failed" in capsys.readouterr().out


def _edit_settings(home, change):
    settings = json.loads(settings_file(home).read_text(encoding="utf-8"))
    change(settings)
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")


def _point_hook_elsewhere(settings):
    for entry in settings["hooks"]["UserPromptSubmit"]:
        for hook in entry.get("hooks", []):
            hook["command"] = hook["command"].replace("ballast", "elsewhere")


def _drop_a_required_tool(settings):
    settings["permissions"]["deny"].remove("Artifact")


def _edit_the_section(home):
    path = home / ".claude" / "CLAUDE.md"
    text = path.read_text(encoding="utf-8")
    assert text.count("# Side sessions and subagents") == 1
    path.write_text(text.replace("# Side sessions and subagents", "# Side sessions"), encoding="utf-8")


@pytest.mark.parametrize("breaks, line", [
    (lambda home: settings_file(home).unlink(), "Missing: {settings}"),
    (lambda home: _edit_settings(home, lambda s: s.update(permissions=[])), "permissions is not an object"),
    (lambda home: _edit_settings(home, _drop_a_required_tool), "permissions.deny is missing: Artifact"),
    (lambda home: _edit_settings(home, lambda s: s.update(hooks=[])), "hooks is not an object"),
    (lambda home: _edit_settings(home, lambda s: s["hooks"].update(UserPromptSubmit=[])),
     "Ideal-Umbrella hook not found in UserPromptSubmit"),
    (lambda home: _edit_settings(home, _point_hook_elsewhere), "Hook command does not point at {hook}"),
    (_edit_the_section, "the Ideal-Umbrella section of CLAUDE.md differs from config/CLAUDE.md"),
    (lambda home: (home / ".claude" / "CLAUDE.md").unlink(), "Missing: {claude_md}"),
    (lambda home: (home / ".claude" / "ballast" / "context_check.py").unlink(), "Missing: {hook}"),
    (lambda home: (home / ".claude" / "ballast" / "context_check.py").write_bytes(b"print()\n"),
     "Hook content differs from hooks/context_check.py"),
], ids=["no-settings", "permissions", "deny", "hooks", "no-hook-entry", "hook-elsewhere", "section",
        "no-claude-md", "no-hook", "hook-content"])
def test_verify_only_names_each_kind_of_broken_install(install_module, tmp_path, capsys, breaks, line):
    # Review 20, finding T1: no test reached these branches of verify(), so a regression could
    # have made --verify-only print OK for a broken install.
    home = tmp_path / "home"
    install_module.install(home)
    breaks(home)
    capsys.readouterr()
    assert install_module.main(["--home", str(home), "--verify-only"]) == 1
    out = capsys.readouterr().out
    paths = {name: str(path) for name, path in install_module.layout(home).items()}
    assert line.format(**paths) in out, out
    assert "[FAIL] Verification failed" in out


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


@pytest.mark.parametrize("home_arg", [".", "~", "~other", None, "~/sub", "./~other"])
def test_relative_home_gives_absolute_hook_path(install_module, tmp_path, monkeypatch, home_arg):
    # None: no --home and a HOME with ".." in it; "~other": another user's home that exists
    # (review 16: the HOME is resolved as --home is, and only a "~name" that is not there is refused).
    # "~/sub": a folder not made yet in your own home (review 17, K4). "./~other": a folder named
    # "~other" here, not that user's home; pathlib drops the "./" (review 17, K2).
    monkeypatch.chdir(tmp_path)
    (tmp_path / "x").mkdir()
    home = tmp_path / "x" / ".." if home_arg is None else tmp_path
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    real_expanduser = Path.expanduser
    if home_arg == "~other":
        monkeypatch.setattr(Path, "expanduser", lambda self: tmp_path.joinpath(*self.parts[1:])
                            if self.parts and self.parts[0] == "~other" else real_expanduser(self))
    if home_arg == "./~other":
        (tmp_path / "~other").mkdir()
        monkeypatch.setattr(Path, "expanduser", lambda self: tmp_path / "x"
                            if self.parts and self.parts[0] == "~other" else real_expanduser(self))
    assert install_module.main([] if home_arg is None else ["--home", home_arg]) == 0

    home = tmp_path / {"~/sub": "sub", "./~other": "~other"}.get(home_arg, "")
    settings = json.loads(settings_file(home).read_text(encoding="utf-8"))
    command = settings["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    assert str((home / ".claude" / "ballast" / "context_check.py").resolve()) in command
    assert str(tmp_path / "x" / "..") not in command
    assert list((tmp_path / "x").iterdir()) == []


@pytest.mark.skipif(os.name == "nt", reason="Windows cannot delete the current folder")
def test_a_relative_home_from_a_deleted_current_folder_is_a_one_line_error(install_module, tmp_path, monkeypatch,
                                                                            capsys):
    # Review 32, finding L2: making the home absolute needs the current folder, and its
    # FileNotFoundError is reported as the other errors before any write are.
    gone = tmp_path / "gone"
    gone.mkdir()
    monkeypatch.chdir(gone)
    gone.rmdir()
    assert install_module.main(["--home", "relhome"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("Error:") and err.endswith("; nothing written\n") and "Traceback" not in err, err


@pytest.mark.skipif(os.name == "nt", reason="the passwd entry is POSIX")
def test_an_unset_home_is_taken_from_the_passwd_entry(install_module, tmp_path, monkeypatch):
    # Review 17, K4: cron, env -i and systemd units run with no HOME; Path.home() then reads the
    # passwd entry, which is where Claude Code looks too. Only an empty HOME is refused.
    import pwd
    home = tmp_path / "home"
    home.mkdir()
    # Built from scratch: the user running the tests may have no passwd entry (review 19, T1).
    entry = pwd.struct_passwd(("u", "x", os.getuid(), os.getgid(), "", str(home), "/bin/sh"))
    monkeypatch.setattr(pwd, "getpwuid", lambda uid: entry)
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    assert install_module.main([]) == 0
    assert settings_file(home).is_file()


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


def test_a_record_written_before_a_failed_settings_write_undoes_cleanly(install_module, tmp_path, monkeypatch):
    # The record is written first and names this run's changes (review 2, findings 4 and 5:
    # written last, it stranded what landed before a failed write). A key it names that never
    # reached settings.json must not be reported as a value the user changed.
    uninstall_module = load_module("uninstall_module", "config/uninstall.py")
    home = tmp_path / "home"
    paths = install_module.layout(home)
    settings_file(home).parent.mkdir(parents=True)
    settings_file(home).write_text(json.dumps({"autoCompactWindow": 1}), encoding="utf-8")
    real_write = uninstall_module.install._write_json

    def failing_write(path, data):
        if path == paths["settings"]:
            raise OSError("disk full")
        real_write(path, data)

    monkeypatch.setattr(uninstall_module.install, "_write_json", failing_write)
    with pytest.raises(OSError):
        uninstall_module.install.install(home, force=True)
    monkeypatch.setattr(uninstall_module.install, "_write_json", real_write)
    assert install_module.read_record(paths["record"])["replaced"] == {"autoCompactWindow": 1}
    assert json.loads(settings_file(home).read_text(encoding="utf-8")) == {"autoCompactWindow": 1}
    _, notices = uninstall_module.uninstall(home)
    assert not any("not the installed value" in n for n in notices), notices
    assert json.loads(settings_file(home).read_text(encoding="utf-8")) == {"autoCompactWindow": 1}
    assert not paths["hook"].exists()


@pytest.mark.parametrize("tool", ["install", "uninstall"])
def test_a_pending_record_naming_a_key_deleted_since_is_settled(install_module, tmp_path, capsys, tool):
    # Review 32, finding L2: a record left pending by a failed write, whose earlier install
    # wrote a key the user has deleted since; settling it must not look the key up.
    home = tmp_path / "home"
    install_module.install(home)
    path = install_module.layout(home)["record"]
    record = json.loads(path.read_text(encoding="utf-8"))
    record["pending"] = {k: v for k, v in record.items() if k != "claude_md"}
    path.write_text(json.dumps(record), encoding="utf-8")
    _edit_settings(home, lambda s: s.pop("autoCompactWindow"))
    module = install_module if tool == "install" else load_module("uninstall_module", "config/uninstall.py")
    capsys.readouterr()
    assert module.main(["--home", str(home)]) == 0, capsys.readouterr().err
    settings = json.loads(settings_file(home).read_text(encoding="utf-8"))
    # install adds the key again; uninstall leaves it deleted.
    assert ("autoCompactWindow" in settings) == (tool == "install")


def test_unreadable_record_stops_the_install(install_module, tmp_path, capsys):
    # The record holds the values an uninstall puts back. It used to be read as "no record"
    # and overwritten; now the user is told to fix it first.
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


DEEP = '{"a": ' + "[" * 100000 + "]" * 100000 + "}"


@pytest.mark.parametrize("name", ["settings", "record"])
def test_json_nested_too_deep_is_a_one_line_error(install_module, tmp_path, capsys, name):
    # json.load raises RecursionError, not ValueError, for a file nested thousands of levels
    # deep; it used to end the install with a traceback instead of the one-line error. Whether
    # it does depends on the stack (3.14 parses 100000 levels with a big one), so either the
    # RecursionError message or the depth check's message is right here.
    home = tmp_path / "home"
    install_module.install(home)
    path = install_module.layout(home)[name]
    path.write_text(DEEP, encoding="utf-8")
    assert install_module.main(["--home", str(home)]) == 1
    err = capsys.readouterr().err
    assert "nested too deeply" in err or "nested more than 100 levels deep" in err, err
    assert "nothing written" in err and "Traceback" not in err
    assert path.read_text(encoding="utf-8") == DEEP


@pytest.mark.parametrize("name", ["settings", "record"])
def test_a_recursion_error_while_reading_is_a_one_line_error(install_module, tmp_path, capsys, monkeypatch,
                                                            name):
    # The RecursionError branch on any stack: json.load raises it for this one file.
    home = tmp_path / "home"
    install_module.install(home)
    path = install_module.layout(home)[name]
    real = json.load

    def load(f, *args, **kwargs):
        if os.path.samefile(f.name, path):
            raise RecursionError("maximum recursion depth exceeded")
        return real(f, *args, **kwargs)

    monkeypatch.setattr(install_module.json, "load", load)
    assert install_module.main(["--home", str(home)]) == 1
    err = capsys.readouterr().err
    assert "nested too deeply" in err and "nothing written" in err and "Traceback" not in err


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
    assert "symlink to a missing target" in err and "put the target back" in err and "remove it" not in err and "nothing written" in err
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
    assert "symlink to a missing target" in err and "put the target back" in err and "remove it" not in err and "nothing written" in err, err
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
    # CLAUDE.md was changed, then the settings write failed and no record was written; the
    # next install saw a CLAUDE.md that already matched, recorded nothing for it, and uninstall
    # never undid the CLAUDE.md change.
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
    assert "CLAUDE.md: Ideal-Umbrella section removed" in changes, (changes, notices)
    assert (claude / "CLAUDE.md").read_text(encoding="utf-8") == "my own rules\n"


@pytest.mark.parametrize("own", [b"mine\rmore\r", b"rules\nmine\r"], ids=["cr", "lf-then-cr"])
def test_a_rules_update_keeps_the_line_ends_of_the_section(install_module, tmp_path, monkeypatch, own):
    # Review 34, I1: a text ending in a bare CR is followed by the installer's LF, which makes a
    # CRLF at the join; an update took that for a CRLF file and wrote the new rules with CRLF.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    md = claude / "CLAUDE.md"
    md.write_bytes(own)
    install_module.install(home)
    newer = tmp_path / "CLAUDE.md"
    # Bytes, not write_text: on Windows the template is checked out with CRLF, and write_text
    # would make each of its line ends CR CR LF.
    rules = install_module._lf(install_module._read_text(install_module.CLAUDE_MD))
    newer.write_bytes((rules + "\n- one more rule\n").encode("utf-8"))
    monkeypatch.setattr(install_module, "CLAUDE_MD", newer)
    changes, _ = install_module.install(home)
    assert "CLAUDE.md section updated" in changes
    data = md.read_bytes()
    assert data.startswith(own + b"\n\n<!--"), data[:40]
    assert b"one more rule" in data and data.count(b"\r\n") == 1, data.count(b"\r\n")


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
    assert "CLAUDE.md section updated" in changes
    assert not any(c.startswith("CLAUDE.md backup:") for c in changes), changes
    backups = sorted(claude.glob("CLAUDE.md.bak-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "my own rules\n"


NOT_WRITABLE = [
    # Review 2, finding 6: json.loads reads this, but on Python 3.12 json.dumps(indent=2) runs
    # out of stack writing it back, after the hook and CLAUDE.md were already written.
    pytest.param('{"a": ' + "[" * 150 + "]" * 150 + "}", "nested more than", id="deep"),
    # Review 2, finding 7: valid JSON holding a lone surrogate, which UTF-8 cannot encode.
    pytest.param('{"statusLine": "\\ud800"}', "not valid Unicode", id="surrogate"),
    # Review 3, info 2d: the same in a key.
    pytest.param('{"\\ud800": 1}', "not valid Unicode", id="surrogate-key"),
    # Review 3, finding 5: read as inf and written back as Infinity, which is not JSON, so
    # Claude Code could read none of settings.json.
    pytest.param('{"myTool": {"limit": 1e400}}', "not a JSON number", id="too-big"),
    pytest.param('{"limit": NaN}', "not a JSON number", id="nan"),
]


@pytest.mark.parametrize("text, message", NOT_WRITABLE)
def test_settings_that_cannot_be_written_back_stop_before_any_write(install_module, tmp_path, capsys, text, message):
    home = tmp_path / "home"
    settings_file(home).parent.mkdir(parents=True)
    settings_file(home).write_text(text, encoding="utf-8")
    assert install_module.main(["--home", str(home)]) == 1
    err = capsys.readouterr().err
    assert message in err and "nothing written" in err and "Traceback" not in err
    assert sorted(p.name for p in (home / ".claude").iterdir()) == ["settings.json"]


def test_an_error_after_a_write_does_not_say_nothing_was_written(install_module, tmp_path, capsys, monkeypatch):
    # Review 2, finding 7, the class: main() said "nothing written" for every ValueError.
    home = tmp_path / "home"
    real = install_module._write_json

    def failing(path, data):
        if path.name == "settings.json":
            raise ValueError("cannot encode")
        real(path, data)
    monkeypatch.setattr(install_module, "_write_json", failing)
    assert install_module.main(["--home", str(home)]) == 1
    err = capsys.readouterr().err
    assert "nothing written" not in err and "Done before the error" in err and "hook written" in err
    # Review 32, finding L3: the record is written first, and is named too.
    assert "  - install record written\n" in err, err


@pytest.mark.skipif(sys.platform != "linux", reason="a path that is not UTF-8 needs a Linux file system")
def test_a_home_path_that_is_not_utf8_stops_before_any_write_and_verify_has_no_traceback(tmp_path):
    # Review 3 of the graphify branch, finding 4: the hook command holds the path, and
    # settings.json is UTF-8, so the install wrote the record, the hook and CLAUDE.md and then
    # failed on settings.json, on every rerun; --verify-only printed a traceback.
    home = os.fsencode(tmp_path) + b"/caf\xe9-home"
    os.makedirs(home + b"/.claude")
    run = [os.fsencode(sys.executable), b"-I", os.fsencode(INSTALL), b"--home", home]
    result = subprocess.run(run, cwd=ROOT, capture_output=True)
    stderr = result.stderr.decode("utf-8", "replace")
    assert result.returncode != 0
    assert "UTF-8" in stderr and "Traceback" not in stderr and "nothing written" in stderr, stderr
    assert os.listdir(home + b"/.claude") == []
    result = subprocess.run(run + [b"--verify-only"], cwd=ROOT, capture_output=True)
    assert result.returncode != 0
    assert b"Traceback" not in result.stderr, result.stderr


@pytest.mark.parametrize("depth, ok", [(100, True), (101, False)])
def test_settings_nested_up_to_the_limit_are_read(install_module, tmp_path, depth, ok):
    # Review 5, info I1 (m16): the limit itself was not tested. The outermost list is level 1.
    value = 1
    for _ in range(depth):
        value = [value]
    if ok:
        install_module._check_json(value, "settings.json")
    else:
        with pytest.raises(ValueError, match="nested"):
            install_module._check_json(value, "settings.json")


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_a_private_settings_file_stays_private(install_module, tmp_path):
    # Review 5, info I2 (m35): nothing checked that a rewrite keeps the file's mode.
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    settings = home / ".claude" / "settings.json"
    settings.write_text("{}", encoding="utf-8")
    settings.chmod(0o600)
    install_module.install(home)
    assert settings.stat().st_mode & 0o777 == 0o600


# Review 5, finding L5: a record field of the wrong JSON type ended in a TypeError traceback
# (or a cryptic message) instead of the one-line error a broken record gives.
BAD_FIELDS = [("added_keys", 5), ("added_keys", None), ("added_keys", [1]), ("replaced", None),
              ("replaced", ["a"]), ("replaced", "ab"), ("installed", ["autoCompactWindow"]),
              ("deny_added", 5), ("deny_added", "Artifact"), ("created", 5), ("claude_md", "x"),
              ("pending", 5), ("pending", {"added_keys": 5}),
              # Review 32, finding L6: a list holding something other than a name.
              ("deny_added", ["Artifact", 5]), ("created", [5])]


@pytest.mark.parametrize("field, value", BAD_FIELDS)
def test_a_record_field_of_the_wrong_type_is_a_one_line_error(install_module, tmp_path, field, value):
    home = tmp_path / "home"
    install_module.install(home)
    path = home / ".claude" / "ballast" / "install-record.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record[field] = value
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="install-record.json"):
        install_module.install(home)


def link_or_skip(link, target):
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("cannot create symlinks here")


def test_a_claude_md_linked_to_an_earlier_backup_gets_a_backup_of_its_own(install_module, tmp_path):
    # Review 12, finding C1: the earlier backup holds the same bytes as CLAUDE.md (it is the
    # file), so it was reused as the backup, and the section was written into it through the
    # link. Uninstall then found CLAUDE.md equal to its backup and left the section for good.
    uninstall_module = load_module("uninstall", ROOT / "config" / "uninstall.py")
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    earlier = claude / "CLAUDE.md.bak-20250101-000000"
    earlier.write_text("my own notes\n", encoding="utf-8")
    link_or_skip(claude / "CLAUDE.md", earlier.name)
    install_module.install(home)
    record = json.loads((claude / "ballast" / "install-record.json").read_text(encoding="utf-8"))
    assert record["claude_md"]["safety_backup"] != earlier.name
    uninstall_module.uninstall(home)
    assert (claude / "CLAUDE.md").is_symlink() and earlier.read_text(encoding="utf-8") == "my own notes\n"
    assert uninstall_module.uninstall(home) == ([], [])


def test_edits_in_a_section_whose_recorded_backup_is_the_file_itself_are_backed_up(install_module, tmp_path):
    # Review 12, finding C1 (b): a record from before the fix names the link's target as the
    # backup. The check for "an earlier run made this backup, then stopped" took the target
    # for that backup, so the edits were written over with no copy.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    md = claude / "CLAUDE.md"
    md.write_text("my own notes\n", encoding="utf-8")
    install_module.install(home)
    path = claude / "ballast" / "install-record.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    target = claude / record["claude_md"]["safety_backup"]
    text = md.read_text(encoding="utf-8")
    end = text.index("<!-- Ideal-Umbrella rules: end -->")
    edited = text[:end] + "- my own rule\n" + text[end:]
    target.write_text(edited, encoding="utf-8")
    md.unlink()
    link_or_skip(md, target.name)
    record["claude_md"]["sha256"] = "0" * 64   # a template change since: the section is replaced
    path.write_text(json.dumps(record), encoding="utf-8")
    install_module.install(home)
    copies = [b for b in claude.glob("CLAUDE.md.bak-*") if b != target]
    assert any(b.read_text(encoding="utf-8") == edited for b in copies), [b.name for b in copies]


def test_a_settings_file_linked_to_an_earlier_backup_gets_a_backup_of_its_own(install_module, tmp_path):
    # Review 12, finding C1, other hit: the same for settings.json; no copy of the settings
    # from before the run was left.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    earlier = claude / "settings.json.bak-20250101-000000"
    earlier.write_text('{"model": "mine"}', encoding="utf-8")
    link_or_skip(settings_file(home), earlier.name)
    install_module.install(home)
    copies = [b for b in claude.glob("settings.json.bak-*") if b != earlier]
    assert [b.read_text(encoding="utf-8") for b in copies] == ['{"model": "mine"}']


@pytest.mark.parametrize("name", ["settings", "claude", "ballast"])
def test_a_dangling_settings_or_folder_link_stops_install_before_anything_is_written(install_module, tmp_path,
                                                                                     capsys, name):
    # Review 13, finding D2 (and mutant x01 for settings.json): only the last part of each path
    # was checked, so a ~/.claude or ballast folder linked into a moved dotfiles folder was
    # created at the missing target and written there.
    home = tmp_path / "home"
    paths = install_module.layout(home)
    link = {"settings": paths["settings"], "claude": paths["claude"], "ballast": paths["record"].parent}[name]
    link.parent.mkdir(parents=True, exist_ok=True)
    link_or_skip(link, tmp_path / "missing")
    assert install_module.main(["--home", str(home)]) == 1
    err = capsys.readouterr().err
    assert "symlink to a missing target" in err and "put the target back" in err and "remove it" not in err and "nothing written" in err, err
    assert not (tmp_path / "missing").exists()


def test_a_dangling_claude_config_dir_stops_install_before_anything_is_written(install_module, tmp_path,
                                                                               monkeypatch, capsys):
    # Review 13, finding D2 (D): CLAUDE_CONFIG_DIR was resolved first, so the link was gone by
    # the time of the check and the install wrote into the missing target.
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    config = tmp_path / "cfg"
    link_or_skip(config, tmp_path / "missing")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    assert install_module.main([]) == 1
    err = capsys.readouterr().err
    assert "symlink to a missing target" in err and "put the target back" in err and "remove it" not in err and "nothing written" in err, err
    assert not (tmp_path / "missing").exists()


@pytest.mark.parametrize("how", ["env", "home"])
def test_a_config_dir_under_a_dangling_folder_link_stops_install(install_module, tmp_path, monkeypatch,
                                                                 capsys, how):
    # Review 13, mutant y3: the dangling link is a folder above the config dir, not the dir itself.
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    link_or_skip(tmp_path / "link", tmp_path / "missing")
    if how == "env":
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "link" / "cfg"))
        args = []
    else:
        monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
        args = ["--home", str(tmp_path / "link" / "h")]
    assert install_module.main(args) == 1
    err = capsys.readouterr().err
    assert "symlink to a missing target" in err and "put the target back" in err and "remove it" not in err and "nothing written" in err, err
    assert not (tmp_path / "missing").exists()


def test_a_symlinked_claude_md_reuses_the_backup_of_a_run_that_failed(install_module, tmp_path, monkeypatch):
    # Review 13, mutant x23: a run that failed after its backup, then a rerun, with CLAUDE.md
    # linked into dotfiles: the rerun reuses the backup with the same bytes, not a second one.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    dotfiles = tmp_path / "dotfiles"
    dotfiles.mkdir()
    (dotfiles / "CLAUDE.md").write_text("my own notes\n", encoding="utf-8")
    link_or_skip(claude / "CLAUDE.md", dotfiles / "CLAUDE.md")
    write = install_module._write_bytes

    def fail_claude_md(path, data):
        if Path(path).resolve() == (dotfiles / "CLAUDE.md").resolve():
            raise OSError(28, "No space left on device")
        write(path, data)
    monkeypatch.setattr(install_module, "_write_bytes", fail_claude_md)
    with pytest.raises(OSError):
        install_module.install(home)
    monkeypatch.setattr(install_module, "_write_bytes", write)
    install_module.install(home)
    assert len(list(claude.glob("CLAUDE.md.bak-*"))) == 1


def test_an_unreadable_old_backup_does_not_stop_the_install(install_module, tmp_path, monkeypatch):
    # Review 13, finding D5: a backup left unreadable (root-owned by a sudo run) stopped every
    # install while looking for one to reuse; it is no match.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    (claude / "CLAUDE.md").write_text("my own notes\n", encoding="utf-8")
    old = claude / "CLAUDE.md.bak-20250101-000000"
    old.write_text("older notes\n", encoding="utf-8")
    read = Path.read_bytes

    def refuse(self):
        if self.name == old.name:
            raise PermissionError(13, "Permission denied", str(self))
        return read(self)
    monkeypatch.setattr(Path, "read_bytes", refuse)
    install_module.install(home)
    backups = sorted(b.name for b in claude.glob("CLAUDE.md.bak-*"))
    assert len(backups) == 2 and old.name in backups


@pytest.mark.parametrize("bom", [b"", b"\xef\xbb\xbf"], ids=["no-bom", "bom"])
@pytest.mark.parametrize("which", ["settings", "record"])
def test_the_offset_of_a_byte_that_is_not_utf8_counts_a_bom(install_module, tmp_path, capsys, which, bom):
    # Review 22, I1: utf-8-sig counts from after a BOM, so the offset was 3 bytes too low.
    home = tmp_path / "home"
    if which == "record":
        install_module.install(home)
        path = home / ".claude" / "ballast" / "install-record.json"
    else:
        path = home / ".claude" / "settings.json"
        path.parent.mkdir(parents=True)
    body = b'{"a": "caf\xe9"}'
    path.write_bytes(bom + body)
    assert install_module.main(["--home", str(home)]) == 1
    assert f"at byte {len(bom) + body.index(0xE9)})" in capsys.readouterr().err
