import json
import os
import subprocess
import sys

import pytest

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
    changes, notices = add_to_repo.merge(settings, TEMPLATE)
    assert settings["customKey"] == "keep-me"
    assert settings["autoCompactWindow"] == 250000
    assert len(settings["hooks"]["UserPromptSubmit"]) == 1
    commands = [hook["command"] for hook in settings["hooks"]["UserPromptSubmit"][0]["hooks"]]
    assert "bash my-own-hook.sh" in commands
    ours = [hook for hook in settings["hooks"]["UserPromptSubmit"][0]["hooks"] if "context_check.py" in hook["command"]]
    assert len(ours) == 1
    assert ours[0]["timeout"] == 5
    assert changes
    assert notices == []
    assert add_to_repo.merge(settings, TEMPLATE) == ([], [])


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


def test_repo_own_value_is_kept_unless_forced(add_to_repo, tmp_path):
    # A repository that sets its own autoCompactWindow used to have it silently replaced.
    settings = {"autoCompactWindow": 100000}
    changes, notices = add_to_repo.merge(settings, TEMPLATE)
    assert settings["autoCompactWindow"] == 100000
    assert not any("autoCompactWindow" in change for change in changes)
    assert any("autoCompactWindow is 100000" in notice and "--force" in notice for notice in notices)

    changes, notices = add_to_repo.merge(settings, TEMPLATE, force=True)
    assert settings["autoCompactWindow"] == TEMPLATE["autoCompactWindow"]
    assert any("autoCompactWindow: 100000 ->" in change for change in changes)
    assert notices == []

    repo = tmp_path / "repo"
    (repo / ".claude").mkdir(parents=True)
    (repo / ".claude" / "settings.json").write_text(json.dumps({"autoCompactWindow": 100000}), encoding="utf-8")
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert "note: autoCompactWindow is 100000" in result.stdout
    assert json.loads((repo / ".claude" / "settings.json").read_text(encoding="utf-8"))["autoCompactWindow"] == 100000
    forced = subprocess.run([sys.executable, "-I", str(ADD), "--force", str(repo)], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8")
    assert forced.returncode == 0, forced.stderr
    assert json.loads((repo / ".claude" / "settings.json").read_text(encoding="utf-8"))["autoCompactWindow"] == TEMPLATE["autoCompactWindow"]


def test_file_system_error_is_one_line(tmp_path):
    # `.claude` as a regular file stops os.makedirs: it used to be a traceback.
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".claude").write_text("in the way", encoding="utf-8")
    result = run(repo)
    assert result.returncode == 1
    assert result.stderr.startswith("Error:") and "Traceback" not in result.stderr


def test_non_utf8_settings_say_so(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".claude").mkdir(parents=True)
    (repo / ".claude" / "settings.json").write_bytes(b'{"a": "caf\xe9"}')
    result = run(repo)
    assert result.returncode == 1
    assert "not UTF-8" in result.stderr and "Traceback" not in result.stderr
    assert (repo / ".claude" / "settings.json").read_bytes() == b'{"a": "caf\xe9"}'


@pytest.mark.parametrize("relative", ["settings.json", "hooks/context_check.py"])
def test_dangling_symlink_is_reported_before_anything_is_written(tmp_path, relative):
    # install.py got this check in an earlier fix; add_to_repo.py, which writes the same two
    # kinds of file, did not: the error named a temp file in the missing target folder.
    repo = tmp_path / "repo"
    link = repo / ".claude" / relative
    link.parent.mkdir(parents=True)
    try:
        link.symlink_to(tmp_path / "gone" / link.name)
    except OSError:
        pytest.skip("cannot create symlinks here")
    result = run(repo)
    assert result.returncode == 1
    assert "symlink to a missing target" in result.stderr and "nothing written" in result.stderr, result.stderr
    assert "Traceback" not in result.stderr
    assert not (repo / ".claude" / "settings.json").is_file()


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_new_files_get_the_umask_mode_not_the_temp_file_mode(add_to_repo, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    add_to_repo._add(str(repo), force=False)
    expected = 0o666 & ~add_to_repo._umask()
    for name in ("settings.json", os.path.join("hooks", "context_check.py")):
        path = repo / ".claude" / name
        assert path.stat().st_mode & 0o777 == expected, name
