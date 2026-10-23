import json
import subprocess
import sys

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

    ok, issues = install_module.verify(home)
    assert ok, issues

    second_changes, _ = install_module.install(home)
    assert second_changes == []


def test_existing_scalar_is_not_overwritten_without_force(install_module, tmp_path):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    settings_file(home).write_text(json.dumps({"autoCompactWindow": 100000}), encoding="utf-8")

    _changes, notices = install_module.install(home)
    assert any("autoCompactWindow" in notice for notice in notices)
    settings = json.loads(settings_file(home).read_text(encoding="utf-8"))
    assert settings["autoCompactWindow"] == 100000

    ok, issues = install_module.verify(home)
    assert not ok
    assert any("autoCompactWindow" in issue for issue in issues)

    install_module.install(home, force=True)
    settings = json.loads(settings_file(home).read_text(encoding="utf-8"))
    assert settings["autoCompactWindow"] == 250000
    ok, issues = install_module.verify(home)
    assert ok, issues


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
    assert "python3" not in command
