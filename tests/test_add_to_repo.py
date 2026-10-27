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


def test_json_nested_too_deep_is_rejected_without_writing(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".claude").mkdir(parents=True)
    (repo / ".claude" / "settings.json").write_text("[" * 100000, encoding="utf-8")
    result = run(repo)
    assert result.returncode == 1
    assert "nested too deeply" in result.stderr and "Traceback" not in result.stderr
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
def test_new_files_get_the_umask_mode_not_the_temp_file_mode(add_to_repo, tmp_path, umask_022):
    # The umask is pinned: under 077 a plain write's mode is the temp file's 0600 too, and
    # the test held without the fix.
    repo = tmp_path / "repo"
    repo.mkdir()
    add_to_repo._add(str(repo), force=False)
    for name in ("settings.json", os.path.join("hooks", "context_check.py")):
        path = repo / ".claude" / name
        assert path.stat().st_mode & 0o777 == 0o644, name


def test_writing_a_new_file_never_touches_the_process_umask(add_to_repo, tmp_path, monkeypatch):
    # The mode came from reading the umask, which os.umask can only do by setting it: files
    # another thread created in that window were made 0666.
    monkeypatch.setattr(os, "umask", lambda *a: pytest.fail("os.umask was called"))
    add_to_repo._write_bytes(str(tmp_path / "new.txt"), b"x\n")
    assert (tmp_path / "new.txt").read_bytes() == b"x\n"


def test_hooks_folder_in_the_way_leaves_settings_unwritten(tmp_path):
    # settings.json was written before the hook was copied, so a `.claude/hooks` that is a file
    # left a hook entry pointing at a hook that was never written.
    repo = tmp_path / "repo"
    (repo / ".claude").mkdir(parents=True)
    (repo / ".claude" / "hooks").write_text("in the way", encoding="utf-8")
    result = run(repo)
    assert result.returncode == 1
    assert result.stderr.startswith("Error:") and "Traceback" not in result.stderr
    assert not (repo / ".claude" / "settings.json").exists()


def test_error_after_a_write_lists_what_was_written(add_to_repo, tmp_path, monkeypatch, capsys):
    # install.py and uninstall.py list the files written before an error; add_to_repo.py did not.
    repo = tmp_path / "repo"
    repo.mkdir()

    def boom(path, data):
        raise OSError(28, "simulated disk full", str(path))

    monkeypatch.setattr(add_to_repo, "_write_json", boom)
    assert add_to_repo.main([str(repo)]) == 1
    err = capsys.readouterr().err
    assert "Done before the error" in err and "context_check.py written" in err, err
    assert (repo / ".claude" / "hooks" / "context_check.py").is_file()


def run_with(repo, *flags):
    return subprocess.run([sys.executable, "-I", str(ADD), *flags, str(repo)], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8")


def settings_of(repo):
    return json.loads((repo / ".claude" / "settings.json").read_text(encoding="utf-8"))


def repo_with(tmp_path, settings=None):
    repo = tmp_path / "repo"
    (repo / ".claude").mkdir(parents=True)
    if settings is not None:
        (repo / ".claude" / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    return repo


@pytest.mark.parametrize("flags", [["--handoff-at", "120000"], ["--handoff-at=120000"]])
def test_handoff_at_writes_the_env_key_as_a_string(tmp_path, context_check, monkeypatch, flags):
    repo = repo_with(tmp_path)
    result = run_with(repo, *flags)
    assert result.returncode == 0, result.stderr
    assert "env.IDEAL_UMBRELLA_HANDOFF_AT: added '120000'" in result.stdout
    value = settings_of(repo)["env"]["IDEAL_UMBRELLA_HANDOFF_AT"]
    assert value == "120000"   # Claude Code env values are strings
    monkeypatch.setenv("IDEAL_UMBRELLA_HANDOFF_AT", value)
    assert context_check.parse_int("IDEAL_UMBRELLA_HANDOFF_AT", 150000) == 120000


def test_handoff_at_keeps_other_env_keys_and_is_idempotent(tmp_path):
    repo = repo_with(tmp_path, {"env": {"FOO": "1"}})
    assert run_with(repo, "--handoff-at", "90000").returncode == 0
    assert settings_of(repo)["env"] == {"FOO": "1", "IDEAL_UMBRELLA_HANDOFF_AT": "90000"}
    before = (repo / ".claude" / "settings.json").read_bytes()
    again = run_with(repo, "--handoff-at", "90000")
    assert again.returncode == 0 and "already up to date" in again.stdout
    assert (repo / ".claude" / "settings.json").read_bytes() == before


def test_a_different_handoff_value_is_kept_unless_forced(tmp_path):
    repo = repo_with(tmp_path, {"env": {"IDEAL_UMBRELLA_HANDOFF_AT": "100000", "FOO": "1"}})
    kept = run_with(repo, "--handoff-at", "120000")
    assert kept.returncode == 0, kept.stderr
    assert "note: env.IDEAL_UMBRELLA_HANDOFF_AT is '100000'" in kept.stdout and "--force" in kept.stdout
    assert settings_of(repo)["env"]["IDEAL_UMBRELLA_HANDOFF_AT"] == "100000"
    forced = run_with(repo, "--force", "--handoff-at", "120000")
    assert forced.returncode == 0, forced.stderr
    assert settings_of(repo)["env"] == {"IDEAL_UMBRELLA_HANDOFF_AT": "120000", "FOO": "1"}


def test_without_handoff_at_no_env_key_is_written_or_removed(tmp_path):
    repo = repo_with(tmp_path)
    assert run_with(repo).returncode == 0
    assert "env" not in settings_of(repo)
    (repo / ".claude" / "settings.json").write_text(
        json.dumps({**settings_of(repo), "env": {"IDEAL_UMBRELLA_HANDOFF_AT": "100000"}}), encoding="utf-8")
    assert run_with(repo, "--force").returncode == 0
    assert settings_of(repo)["env"] == {"IDEAL_UMBRELLA_HANDOFF_AT": "100000"}


@pytest.mark.parametrize("flags", [
    ["--handoff-at", "0"], ["--handoff-at", "-5"], ["--handoff-at", "abc"], ["--handoff-at", "1.5"],
    ["--handoff-at", "١٢٠"], ["--handoff-at="], ["--handoff-at"], ["--handoff-at", "1", "--handoff-at", "2"],
    ["--handof-at", "1"],
])
def test_a_bad_handoff_value_is_a_usage_error_and_nothing_is_written(tmp_path, flags):
    repo = repo_with(tmp_path)
    result = run_with(repo, *flags)
    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert not (repo / ".claude" / "settings.json").exists()


def test_env_that_is_not_an_object_stops_before_any_write(tmp_path):
    repo = repo_with(tmp_path, {"env": ["IDEAL_UMBRELLA_HANDOFF_AT=1"]})
    before = (repo / ".claude" / "settings.json").read_bytes()
    result = run_with(repo, "--handoff-at", "120000")
    assert result.returncode == 1
    assert "env must be an object" in result.stderr and "nothing written" in result.stderr
    assert (repo / ".claude" / "settings.json").read_bytes() == before
    assert not (repo / ".claude" / "hooks").exists()


def test_an_object_valued_template_key_merges_key_by_key(add_to_repo):
    # Class of the env case: a template key whose value is an object used to be compared as a
    # whole, so a repository with any other key in it got none of the template's keys.
    settings = {"env": {"FOO": "1"}}
    changes, notices = add_to_repo.merge(settings, {"env": {"BAR": "2"}})
    assert settings == {"env": {"FOO": "1", "BAR": "2"}, "hooks": {}}
    assert changes == ["env.BAR: added '2'"] and notices == []


@pytest.mark.parametrize("text, message", [
    pytest.param('{"a": ' + "[" * 150 + "]" * 150 + "}", "nested more than", id="deep"),
    pytest.param('{"statusLine": "\\ud800"}', "not valid Unicode", id="surrogate"),
])
def test_settings_that_cannot_be_written_back_stop_before_any_write(tmp_path, text, message):
    # Review 2, findings 6 and 7: the hook was copied before the settings write failed.
    repo = tmp_path / "repo"
    (repo / ".claude").mkdir(parents=True)
    (repo / ".claude" / "settings.json").write_text(text, encoding="utf-8")
    result = run(repo)
    assert result.returncode == 1
    assert message in result.stderr and "nothing written" in result.stderr and "Traceback" not in result.stderr
    assert not (repo / ".claude" / "hooks").exists()


def test_a_huge_handoff_value_is_a_plain_usage_error(tmp_path):
    # Review 2, info 5: int() of 5000 digits printed Python's own digit-limit message.
    repo = repo_with(tmp_path)
    result = run_with(repo, "--handoff-at", "9" * 5000)
    assert result.returncode != 0
    assert "--handoff-at" in result.stderr and "Exceeds" not in result.stderr
