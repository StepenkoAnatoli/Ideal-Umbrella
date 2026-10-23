import json
import subprocess
import sys

from conftest import ROOT

ADD = ROOT / "config" / "add_to_repo.py"
TEMPLATE = json.loads((ROOT / "config" / "repo-settings.json").read_text(encoding="utf-8"))


def run(repo):
    return subprocess.run(
        [sys.executable, "-I", str(ADD), str(repo)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_merge_preserves_custom_keys_and_sibling_hooks(add_to_repo):
    settings = {
        "customKey": "keep-me",
        "hooks": {
            "UserPromptSubmit": [{
                "hooks": [
                    {"type": "command", "command": "bash my-own-hook.sh"},
                    {"type": "command", "command": "python3 -I old/context_check.py", "timeout": 5},
                ]
            }]
        },
    }
    changes = add_to_repo.merge(settings, TEMPLATE)
    assert settings["customKey"] == "keep-me"
    assert settings["autoCompactWindow"] == 250000
    assert len(settings["hooks"]["UserPromptSubmit"]) == 1
    commands = [hook["command"] for hook in settings["hooks"]["UserPromptSubmit"][0]["hooks"]]
    assert "bash my-own-hook.sh" in commands
    ours = [hook for hook in settings["hooks"]["UserPromptSubmit"][0]["hooks"] if "context_check.py" in hook["command"]]
    assert len(ours) == 1
    assert ours[0]["timeout"] == 5
    assert changes
    assert add_to_repo.merge(settings, TEMPLATE) == []


def test_adds_entry_without_touching_other_events(add_to_repo):
    settings = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo stop"}]}]}}
    add_to_repo.merge(settings, TEMPLATE)
    assert settings["hooks"]["Stop"][0]["hooks"][0]["command"] == "echo stop"
    assert len(settings["hooks"]["UserPromptSubmit"]) == 1


def test_bom_settings_file_is_read_and_rewritten(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".claude").mkdir(parents=True)
    (repo / ".claude" / "settings.json").write_text(
        '\ufeff{"customKey": "keep"}', encoding="utf-8"
    )
    result = run(repo)
    assert result.returncode == 0, result.stderr
    data = json.loads((repo / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert data["customKey"] == "keep"
    assert (repo / ".claude" / "hooks" / "context_check.py").is_file()


def test_non_object_json_is_rejected_without_writing(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".claude").mkdir(parents=True)
    original = "[]"
    (repo / ".claude" / "settings.json").write_text(original, encoding="utf-8")
    result = run(repo)
    assert result.returncode != 0
    assert "JSON object" in result.stderr
    assert (repo / ".claude" / "settings.json").read_text(encoding="utf-8") == original
    assert not (repo / ".claude" / "hooks").exists()


def test_second_run_is_idempotent(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    first = run(repo)
    assert first.returncode == 0, first.stderr
    before = (repo / ".claude" / "settings.json").read_bytes()
    second = run(repo)
    assert second.returncode == 0, second.stderr
    assert "already up to date" in second.stdout
    assert (repo / ".claude" / "settings.json").read_bytes() == before
