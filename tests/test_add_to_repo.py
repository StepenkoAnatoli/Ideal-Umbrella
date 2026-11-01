import io
import json
import os
import subprocess
import sys

import pytest

from conftest import ROOT, refuse_looks_inside

ADD = ROOT / "config" / "add_to_repo.py"
TEMPLATE = json.loads((ROOT / "config" / "repo-settings.json").read_text(encoding="utf-8"))
LEARNINGS = (ROOT / "config" / "learnings.md").read_bytes()


def git_env(**extra):
    """The environment without the host's git settings: no GIT_* variable (a GIT_DIR from a
    git hook running pytest), no global or system config, no global excludes file."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", XDG_CONFIG_HOME=os.devnull)
    env.update(extra)
    return env


def run(repo, env=None):
    return subprocess.run(
        [sys.executable, "-I", str(ADD), str(repo)],
        cwd=ROOT,
        env=env if env is not None else git_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="surrogateescape",   # a folder name that is not UTF-8 is printed as its bytes
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
    # Closed nesting inside an object: 3.14 parses 100000 levels with a big stack, so either
    # the RecursionError message or the depth check's message is right here.
    (repo / ".claude" / "settings.json").write_text('{"a": ' + "[" * 100000 + "]" * 100000 + "}",
                                                    encoding="utf-8")
    result = run(repo)
    assert result.returncode == 1
    assert "nested too deeply" in result.stderr or "nested more than 100 levels deep" in result.stderr
    assert "nothing written" in result.stderr and "Traceback" not in result.stderr
    assert not (repo / ".claude" / "hooks").exists()


def test_a_recursion_error_while_reading_is_a_one_line_error(add_to_repo, tmp_path, capsys, monkeypatch):
    # The RecursionError branch on any stack: json.load raises it for the repo's settings.json.
    repo = tmp_path / "repo"
    (repo / ".claude").mkdir(parents=True)
    path = repo / ".claude" / "settings.json"
    path.write_text("{}", encoding="utf-8")
    real = json.load

    def load(f, *args, **kwargs):
        if os.path.samefile(f.name, path):
            raise RecursionError("maximum recursion depth exceeded")
        return real(f, *args, **kwargs)

    monkeypatch.setattr(add_to_repo.json, "load", load)
    assert add_to_repo.main([str(repo)]) == 1
    err = capsys.readouterr().err
    assert "nested too deeply" in err and "nothing written" in err and "Traceback" not in err
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


@pytest.mark.parametrize("relative", [".claude", ".claude/hooks"])
def test_a_dangling_folder_link_is_reported_before_anything_is_written(tmp_path, relative):
    # Review 13, finding D2: only the files were checked, so a .claude or hooks folder linked
    # into a moved folder was created at the missing target and written there.
    repo = tmp_path / "repo"
    link = repo / relative
    link.parent.mkdir(parents=True)
    try:
        link.symlink_to(tmp_path / "gone")
    except OSError:
        pytest.skip("cannot create symlinks here")
    result = run(repo)
    assert result.returncode == 1
    assert "symlink to a missing target" in result.stderr and "put the target back" in result.stderr and "remove it" not in result.stderr and "nothing written" in result.stderr, result.stderr
    assert not (tmp_path / "gone").exists()


@pytest.mark.parametrize("relative", [".claude/settings.json", ".claude/hooks/context_check.py"])
def test_dangling_symlink_is_reported_before_anything_is_written(tmp_path, relative):
    # install.py got this check in an earlier fix; add_to_repo.py, which writes the same two
    # kinds of file, did not: the error named a temp file in the missing target folder.
    repo = tmp_path / "repo"
    link = repo / relative
    link.parent.mkdir(parents=True)
    try:
        link.symlink_to(tmp_path / "gone" / link.name)
    except OSError:
        pytest.skip("cannot create symlinks here")
    result = run(repo)
    assert result.returncode == 1
    assert "symlink to a missing target" in result.stderr and "put the target back" in result.stderr and "remove it" not in result.stderr and "nothing written" in result.stderr, result.stderr
    assert "Traceback" not in result.stderr
    assert not (repo / ".claude" / "settings.json").is_file()
    assert not (repo / ".claude" / "hooks" / "context_check.py").is_file()
    assert not (repo / "notes" / "learnings.md").is_file()


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
    assert (repo / "notes" / "learnings.md").stat().st_mode & 0o777 == 0o644


def test_a_symlinked_settings_file_stays_a_link_and_its_target_is_updated(add_to_repo, tmp_path):
    # Review 20, finding T2: nothing tested the write through a link.
    repo = tmp_path / "repo"
    (repo / ".claude").mkdir(parents=True)
    dotfiles = tmp_path / "dotfiles"
    dotfiles.mkdir()
    (dotfiles / "settings.json").write_text('{"customKey": 1}\n', encoding="utf-8")
    link = repo / ".claude" / "settings.json"
    try:
        link.symlink_to(dotfiles / "settings.json")
    except OSError:
        pytest.skip("cannot create symlinks here")
    add_to_repo._add(str(repo), force=False)
    assert link.is_symlink()
    settings = json.loads((dotfiles / "settings.json").read_text(encoding="utf-8"))
    assert settings["customKey"] == 1 and "UserPromptSubmit" in settings["hooks"]


def test_a_symlinked_hook_stays_a_link_and_its_target_is_updated(add_to_repo, tmp_path):
    # Review 8, low 45 (N8): only the settings link was tested; the hook goes through the same
    # realpath write, and abspath there would replace the link with a file.
    repo = tmp_path / "repo"
    (repo / ".claude" / "hooks").mkdir(parents=True)
    dotfiles = tmp_path / "dotfiles"
    dotfiles.mkdir()
    (dotfiles / "context_check.py").write_text("# an older hook\n", encoding="utf-8")
    link = repo / ".claude" / "hooks" / "context_check.py"
    try:
        link.symlink_to(dotfiles / "context_check.py")
    except OSError:
        pytest.skip("cannot create symlinks here")
    add_to_repo._add(str(repo), force=False)
    assert link.is_symlink()
    assert (dotfiles / "context_check.py").read_bytes() == (ROOT / "hooks" / "context_check.py").read_bytes()


def test_write_bytes_removes_the_temp_file_when_the_rename_fails(add_to_repo, tmp_path, monkeypatch):
    # Review 8, low 26 (old #9): the cleanup in _write_bytes' finally had no test; install.py's
    # twin has one (tests/test_install.py).
    target = tmp_path / "settings.json"
    target.write_text("{}\n", encoding="utf-8")

    def boom(src, dst):
        raise PermissionError(13, "simulated rename failure", dst)
    monkeypatch.setattr(add_to_repo.os, "replace", boom)
    with pytest.raises(PermissionError, match="simulated"):
        add_to_repo._write_bytes(str(target), b'{"new": 1}\n')
    assert target.read_text(encoding="utf-8") == "{}\n"
    assert [p.name for p in tmp_path.iterdir()] == ["settings.json"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_an_existing_file_keeps_its_mode(add_to_repo, tmp_path):
    # Review 20, finding T2: nothing tested that a rewrite keeps the mode.
    repo = tmp_path / "repo"
    (repo / ".claude" / "hooks").mkdir(parents=True)
    settings = repo / ".claude" / "settings.json"
    hook = repo / ".claude" / "hooks" / "context_check.py"
    settings.write_text("{}\n", encoding="utf-8")
    hook.write_text("old\n", encoding="utf-8")
    settings.chmod(0o640)   # neither is a mode a new file gets (0644 or 0600)
    hook.chmod(0o750)
    add_to_repo._add(str(repo), force=False)
    assert "UserPromptSubmit" in settings.read_text(encoding="utf-8")
    assert hook.read_text(encoding="utf-8") != "old\n"
    assert settings.stat().st_mode & 0o777 == 0o640
    assert hook.stat().st_mode & 0o777 == 0o750


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


@pytest.mark.parametrize("flags, message", [
    (["--handoff-at", "1", "--handoff-at", "2"], "--handoff-at is given more than once"),
    (["--handoff-at", "abc"], "--handoff-at needs a whole number of tokens above 0, not 'abc'"),
], ids=["twice", "not-a-number"])
def test_a_bad_handoff_value_says_what_is_wrong_before_the_usage_line(add_to_repo, tmp_path, flags, message):
    # Review 32, L3 (mutant A90): without the reason only the usage line was printed.
    repo = repo_with(tmp_path)
    with pytest.raises(SystemExit) as e:
        add_to_repo.main([*flags, str(repo)])
    assert e.value.code == f"{message}\n{add_to_repo.USAGE}"
    assert not (repo / ".claude" / "settings.json").exists()


@pytest.mark.parametrize("args", [[], ["no-such-repo"]], ids=["no-argument", "missing-repo"])
def test_no_repo_or_a_missing_one_is_the_usage_line(add_to_repo, tmp_path, args):
    # Review 32, L2: no argument gave an IndexError (mutant A47), and a repo that is not there an
    # AttributeError on None (mutant A50), where the usage line is right.
    with pytest.raises(SystemExit) as e:
        add_to_repo.main([str(tmp_path / a) for a in args])
    assert e.value.code == add_to_repo.USAGE
    assert not (tmp_path / "no-such-repo").exists()


@pytest.mark.parametrize("depth, ok", [(100, True), (101, False)])
def test_settings_nested_up_to_the_limit_are_read(add_to_repo, depth, ok):
    # Review 32, L4 (mutant A135): test_install.py has this boundary test, add_to_repo had not.
    # The outermost list is level 1.
    value = 1
    for _ in range(depth):
        value = [value]
    if ok:
        add_to_repo._check_json(value, "settings.json")
    else:
        with pytest.raises(ValueError, match="nested"):
            add_to_repo._check_json(value, "settings.json")


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
    pytest.param('{"\\ud800": 1}', "not valid Unicode", id="surrogate-key"),
    # Review 3, finding 5: written back as Infinity, which Claude Code cannot read.
    pytest.param('{"limit": 1e400}', "not a JSON number", id="too-big"),
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
    # Review 32, L3 (mutant A90): the usage line names --handoff-at too, so check the reason.
    assert f"--handoff-at {'9' * 20}... is too large" in result.stderr and "Exceeds" not in result.stderr


def test_a_handoff_value_padded_with_zeros_is_read_without_the_digit_limit(tmp_path):
    # Review 3, info 1: leading zeros got past the digit limit to int(), which counts them.
    repo = repo_with(tmp_path)
    result = run_with(repo, "--handoff-at", "0" * 5000 + "120000")
    assert result.returncode == 0, result.stderr[-300:]
    assert settings_of(repo)["env"]["IDEAL_UMBRELLA_HANDOFF_AT"] == "120000"


@pytest.mark.parametrize("value, ok", [("9" * 15, True), ("1" + "0" * 15, False)])
def test_the_handoff_value_takes_at_most_fifteen_digits(tmp_path, value, ok):
    # Review 6, info I1 (n24): the limit itself was not tested.
    repo = repo_with(tmp_path)
    result = run_with(repo, "--handoff-at", value)
    assert (result.returncode == 0) is ok, result.stderr[-300:]


@pytest.mark.parametrize("bom", [b"", b"\xef\xbb\xbf"], ids=["no-bom", "bom"])
def test_the_offset_of_a_byte_that_is_not_utf8_counts_a_bom(tmp_path, bom):
    # Review 22, I1: utf-8-sig counts from after a BOM, so the offset was 3 bytes too low.
    repo = tmp_path / "repo"
    (repo / ".claude").mkdir(parents=True)
    body = b'{"a": "caf\xe9"}'
    (repo / ".claude" / "settings.json").write_bytes(bom + body)
    result = run(repo)
    assert result.returncode == 1
    assert f"at byte {len(bom) + body.index(0xE9)})" in result.stderr, result.stderr


def test_a_settings_file_that_cannot_be_read_stops_before_anything_is_written(tmp_path):
    # Review 23, F1 other hits: settings.json was read outside any OSError catch, so the error
    # was a bare [Errno] without "nothing written".
    repo = tmp_path / "repo"
    (repo / ".claude" / "settings.json").mkdir(parents=True)
    result = run(repo)
    assert result.returncode == 1
    assert "cannot read" in result.stderr and "nothing written" in result.stderr, result.stderr
    assert "[Errno" not in result.stderr, result.stderr


def test_a_json_error_in_a_file_with_bare_cr_line_ends_names_the_line(tmp_path):
    # Review 23, I1: reading bytes kept bare CRs, so a JSON error on line 3 was reported on line 1.
    repo = tmp_path / "repo"
    (repo / ".claude").mkdir(parents=True)
    (repo / ".claude" / "settings.json").write_bytes(b'{\r"a": 1,\r"b": }\r')
    result = run(repo)
    assert result.returncode == 1
    assert "line 3" in result.stderr, result.stderr


def test_a_hook_file_that_cannot_be_read_stops_before_anything_is_written(tmp_path):
    # Review 24, F3: the hook was read outside any handler, so a folder in its place gave a
    # bare [Errno 21] without "nothing written".
    repo = tmp_path / "repo"
    (repo / ".claude" / "hooks" / "context_check.py").mkdir(parents=True)
    result = run(repo)
    assert result.returncode == 1
    assert "cannot read" in result.stderr and "nothing written" in result.stderr, result.stderr
    assert "[Errno" not in result.stderr and not (repo / ".claude" / "settings.json").exists(), result.stderr


def test_a_source_hook_that_cannot_be_read_stops_before_anything_is_written(add_to_repo, tmp_path, capsys, monkeypatch):
    # Review 24, F3: the hook shipped with the repo was read outside any handler too.
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(add_to_repo, "SCRIPT", os.fspath(tmp_path))
    assert add_to_repo.main([str(repo)]) == 1
    err = capsys.readouterr().err
    assert "cannot read" in err and "nothing written" in err and "[Errno" not in err, err
    assert not (repo / ".claude").exists()


def test_a_folder_that_cannot_be_searched_stops_before_anything_is_written(add_to_repo, tmp_path, capsys, monkeypatch):
    # Review 24, F1 other hits: os.path.exists() says False for a hook it cannot look at (a
    # folder only root may search), so the user's own hook would be taken for none.
    repo = tmp_path / "repo"
    hooks = repo / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "context_check.py").write_text("# my own hook\n", encoding="utf-8")
    refuse_looks_inside(hooks, monkeypatch)
    assert add_to_repo.main([str(repo)]) == 1
    err = capsys.readouterr().err
    assert "cannot look at" in err and "nothing written" in err and "[Errno" not in err, err
    monkeypatch.undo()
    assert not (repo / ".claude" / "settings.json").exists()


def test_a_settings_link_into_a_folder_that_cannot_be_searched_is_not_called_missing(add_to_repo, tmp_path, capsys,
                                                                                    monkeypatch):
    # Review 25, E (mutant b04): the target is there, it just cannot be looked at; "put the
    # target back" would be wrong advice.
    repo = tmp_path / "repo"
    (repo / ".claude").mkdir(parents=True)
    dotfiles = tmp_path / "dotfiles"
    dotfiles.mkdir()
    (dotfiles / "settings.json").write_text("{}", encoding="utf-8")
    try:
        (repo / ".claude" / "settings.json").symlink_to(dotfiles / "settings.json")
    except OSError:
        pytest.skip("cannot create symlinks here")
    refuse_looks_inside(dotfiles, monkeypatch)
    assert add_to_repo.main([str(repo)]) == 1
    err = capsys.readouterr().err
    assert "cannot look at" in err and "missing target" not in err and "nothing written" in err, err
    monkeypatch.undo()
    assert (dotfiles / "settings.json").read_text(encoding="utf-8") == "{}"


def test_a_repo_that_cannot_be_looked_at_says_so_not_usage(add_to_repo, tmp_path, capsys, monkeypatch):
    # Review 25, info 2: os.path.isdir() says False for a repo in a folder that cannot be
    # searched, so the user got the usage line instead of the reason.
    locked = tmp_path / "locked"
    (locked / "repo").mkdir(parents=True)
    refuse_looks_inside(locked, monkeypatch)
    assert add_to_repo.main([str(locked / "repo")]) == 1
    err = capsys.readouterr().err
    assert "cannot look at" in err and "nothing written" in err and "usage" not in err, err


def test_a_repo_that_is_a_link_to_a_folder_is_followed(add_to_repo, tmp_path, capsys):
    # Review 26, C3: nothing failed when the repo check looked at the link itself, not at the
    # folder it names.
    (tmp_path / "repo").mkdir()
    try:
        (tmp_path / "link").symlink_to(tmp_path / "repo", target_is_directory=True)
    except OSError:
        pytest.skip("cannot create symlinks here")
    assert add_to_repo.main([str(tmp_path / "link")]) == 0, capsys.readouterr().err
    assert (tmp_path / "repo" / ".claude" / "settings.json").is_file()


def test_a_repo_that_is_a_file_is_the_usage_line(add_to_repo, tmp_path):
    # Review 26, C3: nothing failed when the repo check took any file for a folder.
    (tmp_path / "repo").write_text("not a folder\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        add_to_repo.main([str(tmp_path / "repo")])
    assert e.value.code == add_to_repo.USAGE
    assert (tmp_path / "repo").read_text(encoding="utf-8") == "not a folder\n"


# --- the learnings template -------------------------------------------------------------

def test_learnings_template_is_copied_once_and_then_left_alone(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    first = run(repo)
    assert first.returncode == 0, first.stderr
    learnings = repo / "notes" / "learnings.md"
    assert learnings.read_bytes() == LEARNINGS
    assert "notes/learnings.md written" in first.stdout
    assert ("Commit .claude/hooks/context_check.py, .claude/settings.json and notes/learnings.md "
            "in that repository.") in first.stdout

    # The file is the repository's data from now on: a second run, forced or not, leaves it.
    mine = "decided: keep the old parser; the new one drops trailing commas\n"
    learnings.write_text(mine, encoding="utf-8")
    second = run(repo)
    assert second.returncode == 0, second.stderr
    assert "already up to date" in second.stdout
    assert "notes/learnings.md" not in second.stdout
    forced = subprocess.run([sys.executable, "-I", str(ADD), "--force", str(repo)], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8")
    assert forced.returncode == 0, forced.stderr
    assert learnings.read_text(encoding="utf-8") == mine


def test_existing_learnings_file_is_not_replaced_and_not_named(tmp_path):
    repo = tmp_path / "repo"
    (repo / "notes").mkdir(parents=True)
    (repo / "notes" / "learnings.md").write_bytes(b"")   # even an empty one is the user's
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert (repo / "notes" / "learnings.md").read_bytes() == b""
    assert "notes/learnings.md" not in result.stdout
    assert "Commit .claude/hooks/context_check.py and .claude/settings.json in that repository." in result.stdout


def test_commit_hint_names_only_the_files_written_this_run(tmp_path):
    # A repository that already had the hook and settings and now gets only the learnings file
    # was told to commit all three.
    repo = tmp_path / "repo"
    repo.mkdir()
    assert run(repo).returncode == 0
    (repo / "notes" / "learnings.md").unlink()
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert "Commit notes/learnings.md in that repository." in result.stdout


@pytest.mark.parametrize("folder", [".claude", ".claude/hooks"])
def test_dangling_folder_link_is_reported_before_anything_is_written(tmp_path, folder):
    # A dangling `notes -> /mnt/sync/notes` was written through: the missing folder was
    # created where the link points and the template written outside the repository.
    repo = tmp_path / "repo"
    link = repo / folder
    link.parent.mkdir(parents=True, exist_ok=True)
    gone = tmp_path / "gone" / "target"
    try:
        link.symlink_to(gone, target_is_directory=True)
    except OSError:
        pytest.skip("cannot create symlinks here")
    result = run(repo)
    assert result.returncode == 1
    assert "symlink to a missing target" in result.stderr and "nothing written" in result.stderr, result.stderr
    assert not (tmp_path / "gone").exists()


@pytest.mark.parametrize("relative,is_dir", [("notes", True), ("notes/learnings.md", False)])
def test_a_learnings_link_into_a_folder_that_cannot_be_searched_is_not_called_missing(
        add_to_repo, tmp_path, capsys, monkeypatch, relative, is_dir):
    # Review 42, L3: os.path.exists() says False for a target it cannot look at, so a `notes`
    # link that is fine got "a symlink to a missing target" (put back a target that is there).
    repo = tmp_path / "repo"
    link = repo / relative
    link.parent.mkdir(parents=True, exist_ok=True)
    locked = tmp_path / "locked"
    (locked / "real").mkdir(parents=True)
    real = locked / "real" if is_dir else locked / "real" / "learnings.md"
    if not is_dir:
        real.write_text("# mine\n", encoding="utf-8")
    try:
        link.symlink_to(real, target_is_directory=is_dir)
    except OSError:
        pytest.skip("cannot create symlinks here")
    refuse_looks_inside(locked, monkeypatch)
    assert add_to_repo.main([str(repo)]) == 0
    out = capsys.readouterr().out
    monkeypatch.undo()
    assert "note: notes/learnings.md not copied: cannot look at" in out, out
    assert "missing target" not in out, out
    assert (repo / ".claude" / "settings.json").is_file()
    assert (repo / ".claude" / "hooks" / "context_check.py").is_file()
    assert sorted(p.name for p in (locked / "real").iterdir()) == ([] if is_dir else ["learnings.md"])


@pytest.mark.parametrize("relative,is_dir", [("notes", True), ("notes/learnings.md", False)])
def test_dangling_learnings_link_is_a_notice_not_an_error(tmp_path, relative, is_dir):
    # The learnings file is a courtesy: a dangling link on it or on `notes` used to fail the
    # whole run (exit 1, nothing written). Now it gets no copy and a note.
    repo = tmp_path / "repo"
    link = repo / relative
    link.parent.mkdir(parents=True, exist_ok=True)
    gone = tmp_path / "gone" / "target"
    try:
        link.symlink_to(gone, target_is_directory=is_dir)
    except OSError:
        pytest.skip("cannot create symlinks here")
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert "note: notes/learnings.md not copied:" in result.stdout
    assert "is a symlink to a missing target" in result.stdout
    assert (repo / ".claude" / "settings.json").is_file()
    assert (repo / ".claude" / "hooks" / "context_check.py").is_file()
    assert "Commit .claude/hooks/context_check.py and .claude/settings.json in that repository." in result.stdout
    assert not (tmp_path / "gone").exists()


def test_notes_as_a_file_in_the_way_is_a_notice_not_an_error(tmp_path):
    # The learnings file is a courtesy and is written last: a `notes` that is a file used to
    # make every run exit 1 with no commit hint, the core install whole all along.
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "notes").write_text("in the way", encoding="utf-8")
    first_hint = "Commit .claude/hooks/context_check.py and .claude/settings.json in that repository."
    for attempt in range(2):
        result = run(repo)
        assert result.returncode == 0, result.stderr
        assert "note: notes/learnings.md not written" in result.stdout
        if attempt == 0:
            assert first_hint in result.stdout
    assert (repo / ".claude" / "hooks" / "context_check.py").is_file()
    assert (repo / ".claude" / "settings.json").is_file()
    assert (repo / "notes").read_text(encoding="utf-8") == "in the way"
    assert first_hint not in result.stdout   # the second run wrote nothing


def test_notes_ignored_by_git_gets_no_copy(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    try:
        subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True, env=git_env())
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git is not available")
    (repo / ".gitignore").write_text("notes/\n", encoding="utf-8")
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert not (repo / "notes" / "learnings.md").exists()
    assert "note: notes/learnings.md not copied: git ignores it" in result.stdout
    assert "Commit .claude/hooks/context_check.py and .claude/settings.json in that repository." in result.stdout


def _git_init(repo):
    repo.mkdir()
    try:
        subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True, env=git_env())
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git is not available")


def test_ignored_claude_folder_is_written_with_a_note(tmp_path):
    # A gitignored .claude/ got the hook and settings and the hint told the user to commit them.
    repo = tmp_path / "repo"
    _git_init(repo)
    (repo / ".gitignore").write_text(".claude/\n", encoding="utf-8")
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert (repo / ".claude" / "settings.json").is_file()
    assert "note: .claude/settings.json is installed, but git ignores it" in result.stdout
    assert "note: .claude/hooks/context_check.py is installed, but git ignores it" in result.stdout
    assert "Commit notes/learnings.md in that repository." in result.stdout
    again = run(repo)   # the note stood on the first run only: a second one said "up to date"
    assert "note: .claude/settings.json is installed, but git ignores it" in again.stdout
    assert "Commit" not in again.stdout


@pytest.mark.skipif(os.name == "nt", reason="a fake git on PATH is a POSIX script")
def test_git_that_cannot_answer_is_a_note_not_not_ignored(tmp_path):
    # Exit 128 (dubious ownership, a GIT_DIR elsewhere) was read as "not ignored", silently.
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "git"
    fake.write_text("#!/bin/sh\nexit 128\n", encoding="utf-8", newline="\n")   # a CR would end up in the shebang
    fake.chmod(0o755)
    env = git_env(PATH=str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))
    result = run(repo, env=env)
    assert result.returncode == 0, result.stderr
    assert "note: git could not say whether notes/learnings.md is ignored" in result.stdout
    assert "note: git could not say whether .claude/settings.json is ignored" in result.stdout
    assert (repo / "notes" / "learnings.md").is_file()
    # When the copy then fails, no note claims it was written.
    other = tmp_path / "other"
    other.mkdir()
    (other / ".git").mkdir()
    (other / "notes").write_text("in the way", encoding="utf-8")
    result = run(other, env=env)
    assert "note: notes/learnings.md not written" in result.stdout
    assert "whether notes/learnings.md is ignored" not in result.stdout


def test_folder_outside_any_repository_gets_no_git_note(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert "git could not say" not in result.stdout
    assert "could not list" not in result.stdout


def test_notes_symlinked_inside_the_repository_is_named_by_its_real_path(tmp_path):
    # `notes -> docs`: git refuses "notes/learnings.md" (beyond a symbolic link), so the note
    # said git could not say, and the hint named a path `git add` rejects.
    repo = tmp_path / "repo"
    _git_init(repo)
    (repo / "docs").mkdir()
    try:
        (repo / "notes").symlink_to("docs", target_is_directory=True)
    except OSError:
        pytest.skip("cannot create symlinks here")
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert "could not say" not in result.stdout
    # The hint names the real path and the link itself, which the cloud clone goes through.
    assert ("Commit .claude/hooks/context_check.py, .claude/settings.json, docs/learnings.md "
            "and notes in that repository.") in result.stdout
    assert (repo / "docs" / "learnings.md").is_file()


def test_a_claude_folder_link_is_named_in_the_hint(tmp_path):
    # `.claude -> docs/claude`: the hint named only docs/claude/..., so the clone had no .claude.
    repo = tmp_path / "repo"
    _git_init(repo)
    (repo / "docs" / "claude").mkdir(parents=True)
    try:
        (repo / ".claude").symlink_to(os.path.join("docs", "claude"), target_is_directory=True)
    except OSError:
        pytest.skip("cannot create symlinks here")
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert ("Commit docs/claude/hooks/context_check.py, .claude, docs/claude/settings.json "
            "and notes/learnings.md in that repository.") in result.stdout


def test_an_ignored_link_gets_a_note_and_no_hint(tmp_path):
    repo = tmp_path / "repo"
    _git_init(repo)
    (repo / "docs" / "claude").mkdir(parents=True)
    (repo / "docs" / "n").mkdir()
    try:
        (repo / ".claude").symlink_to(os.path.join("docs", "claude"), target_is_directory=True)
        (repo / "notes").symlink_to(os.path.join("docs", "n"), target_is_directory=True)
    except OSError:
        pytest.skip("cannot create symlinks here")
    (repo / ".gitignore").write_text("/.claude\n/notes\n", encoding="utf-8")
    for _ in range(2):
        result = run(repo)
        assert result.returncode == 0, result.stderr
        assert ("note: .claude/settings.json is installed, but it is reached through the symlink .claude, which git "
                "ignores") in result.stdout
        assert ("note: .claude/hooks/context_check.py is installed, but it is reached through the symlink .claude"
                in result.stdout)
        assert "Commit" not in result.stdout
        assert ("notes/learnings.md not copied: it is reached through the symlink notes, "
                "which git ignores") in result.stdout
    assert not (repo / "docs" / "n" / "learnings.md").exists()


def test_a_folder_whose_name_starts_with_a_colon_is_not_pathspec_magic(tmp_path):
    if os.name == "nt":
        pytest.skip("':' is not allowed in a Windows file name")
    repo = tmp_path / "repo"
    _git_init(repo)
    (repo / ":x").mkdir()
    (repo / "notes").symlink_to(":x", target_is_directory=True)
    (repo / ".gitignore").write_text("/:x/\n", encoding="utf-8")
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert "notes/learnings.md not copied: git ignores it" in result.stdout
    assert not (repo / ":x" / "learnings.md").exists()


def test_files_a_symlink_puts_outside_the_repository_are_noted_not_hinted(tmp_path):
    repo = tmp_path / "repo"
    _git_init(repo)
    (repo / ".claude").mkdir()
    outside = tmp_path / "outside"
    (outside / "hooks").mkdir(parents=True)
    (outside / "notes").mkdir()
    try:
        (repo / ".claude" / "hooks").symlink_to(outside / "hooks", target_is_directory=True)
        (repo / "notes").symlink_to(outside / "notes", target_is_directory=True)
    except OSError:
        pytest.skip("cannot create symlinks here")
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert "note: .claude/hooks/context_check.py is installed, but it lands outside the repository" in result.stdout
    assert "note: notes/learnings.md not copied: it lands outside the repository (" in result.stdout
    assert not (outside / "notes" / "learnings.md").exists()
    assert "Commit .claude/settings.json in that repository." in result.stdout


def test_a_git_file_marks_a_worktree_as_a_repository(tmp_path):
    # A worktree or submodule has a .git file, not a folder.
    main_repo = tmp_path / "main"
    _git_init(main_repo)
    env = git_env(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
                  GIT_COMMITTER_EMAIL="t@t")
    (main_repo / ".gitignore").write_text("notes/\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(main_repo), "add", ".gitignore"], check=True, env=env)
    subprocess.run(["git", "-C", str(main_repo), "commit", "-qm", "init"], check=True, env=env)
    tree = tmp_path / "tree"
    subprocess.run(["git", "-C", str(main_repo), "worktree", "add", "-q", str(tree)],
                   check=True, capture_output=True, env=env)
    assert (tree / ".git").is_file()
    result = run(tree)
    assert result.returncode == 0, result.stderr
    assert "note: notes/learnings.md not copied: git ignores it" in result.stdout


def test_git_dir_in_the_environment_is_a_repository(tmp_path):
    # GIT_DIR names a repository with no .git entry in the folder: the .git walk alone read
    # it as no repository, and an ignored notes/ got the copy.
    store = tmp_path / "store"
    _git_init(store)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitignore").write_text("notes/\n", encoding="utf-8")
    result = run(repo, env=git_env(GIT_DIR=str(store / ".git"), GIT_WORK_TREE=str(repo)))
    assert result.returncode == 0, result.stderr
    assert "note: notes/learnings.md not copied: git ignores it" in result.stdout


@pytest.mark.skipif(os.name == "nt" or sys.platform == "darwin",
                    reason="a folder name that is not UTF-8 needs a byte-name file system")
def test_folder_name_that_is_not_utf8_does_not_abort_the_install(tmp_path):
    # The paths were encoded as strict UTF-8 for git: UnicodeEncodeError, exit 1, no hook.
    repo = tmp_path / "repo"
    _git_init(repo)
    odd = os.path.join(os.fsencode(str(repo)), b"d\xff")
    os.mkdir(odd)
    os.symlink(b"d\xff", os.path.join(os.fsencode(str(repo)), b"notes"))
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert (repo / ".claude" / "hooks" / "context_check.py").is_file()
    assert os.path.isfile(os.path.join(odd, b"learnings.md"))
    assert "could not say" not in result.stdout
    # The hint names the folder by its bytes on disk, a path `git add` takes.
    assert os.fsdecode(b"d\xff/learnings.md") in result.stdout


def test_a_broken_git_dir_is_a_note_not_no_repository(tmp_path):
    # "fatal: not a git repository: '/nonexistent'" was read as "no repository": a confident
    # hint naming files git ignores.
    repo = tmp_path / "repo"
    _git_init(repo)
    (repo / ".gitignore").write_text(".claude/\n", encoding="utf-8")
    result = run(repo, env=git_env(GIT_DIR=str(tmp_path / "nowhere")))
    assert result.returncode == 0, result.stderr
    assert "note: git could not say whether .claude/settings.json is ignored" in result.stdout


def _symlink_or_skip(link, to):
    try:
        os.symlink(to, link, target_is_directory=True)
    except OSError:
        pytest.skip("cannot create symlinks here")


def test_an_ignored_link_in_the_middle_of_a_chain_is_noted(tmp_path):
    # notes -> mid -> docs with mid ignored: the clone had a notes link to nothing.
    repo = tmp_path / "repo"
    _git_init(repo)
    (repo / "docs").mkdir()
    _symlink_or_skip(repo / "mid", "docs")
    _symlink_or_skip(repo / "notes", "mid")
    (repo / ".gitignore").write_text("/mid\n", encoding="utf-8")
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert ("notes/learnings.md not copied: it is reached through the symlink mid, which git "
            "ignores") in result.stdout
    assert not (repo / "docs" / "learnings.md").exists()
    # Not ignored: both links are named in the hint.
    (repo / ".gitignore").unlink()
    result = run(repo)
    assert "docs/learnings.md, notes and mid in that repository." in result.stdout


def test_a_link_with_an_absolute_target_is_noted_not_hinted(tmp_path):
    repo = tmp_path / "repo"
    _git_init(repo)
    (repo / "docs").mkdir()
    _symlink_or_skip(repo / "notes", str(repo / "docs"))
    (repo / "c").mkdir()
    _symlink_or_skip(repo / ".claude", os.path.join("..", "repo", "c"))
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert ("notes/learnings.md not copied: it is reached through the symlink notes, whose "
            "target is an absolute path or lies outside the repository") in result.stdout
    assert ("note: .claude/settings.json is installed, but it is reached through the symlink .claude, whose target"
            in result.stdout)
    assert "Commit" not in result.stdout
    assert (repo / "c" / "settings.json").is_file()   # local sessions still get it


@pytest.mark.skipif(os.name == "nt", reason="a fake git needs a POSIX shell")
def test_a_shared_link_gets_one_could_not_say_note(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "sub").mkdir()
    _symlink_or_skip(repo / ".claude", "sub")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "git"
    fake.write_text("#!/bin/sh\nexit 2\n", encoding="utf-8", newline="\n")   # a CR would end up in the shebang
    fake.chmod(0o755)
    env = git_env(PATH=str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))
    for _ in range(2):
        result = run(repo, env=env)
        assert result.returncode == 0, result.stderr
        assert result.stdout.count("git could not say whether .claude is ignored") == 1


def test_a_submodule_on_the_way_is_outside_the_repository(tmp_path):
    # `notes` a submodule: git check-ignore exited 128 for the whole batch ("could not say"
    # for every file) and the hint named a path git add refuses.
    repo = tmp_path / "repo"
    _git_init(repo)
    _git_init(repo / "notes")
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert "could not say" not in result.stdout
    assert "note: notes/learnings.md not copied: it lands in a submodule, a nested repository or .git (notes/learnings.md)" in result.stdout
    assert ("Commit .claude/hooks/context_check.py and .claude/settings.json in that "
            "repository.") in result.stdout
    assert not (repo / "notes" / "learnings.md").exists()


def test_a_link_in_the_middle_of_a_target_is_followed(tmp_path):
    # notes -> lnk/docs with lnk -> real ignored: lnk was never seen, notes broke in a clone.
    repo = tmp_path / "repo"
    _git_init(repo)
    (repo / "real" / "docs").mkdir(parents=True)
    _symlink_or_skip(repo / "lnk", "real")
    _symlink_or_skip(repo / "notes", os.path.join("lnk", "docs"))
    (repo / ".gitignore").write_text("/lnk\n", encoding="utf-8")
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert ("notes/learnings.md not copied: it is reached through the symlink lnk, which git "
            "ignores") in result.stdout
    (repo / ".gitignore").unlink()
    result = run(repo)
    assert "real/docs/learnings.md, notes and lnk in that repository." in result.stdout


def test_a_link_inside_a_nested_repository_is_noted(tmp_path):
    # notes -> sub/x, sub a nested repository, x -> ../docs: git never records sub/x.
    repo = tmp_path / "repo"
    _git_init(repo)
    (repo / "docs").mkdir()
    _git_init(repo / "sub")
    _symlink_or_skip(repo / "sub" / "x", os.path.join("..", "docs"))
    _symlink_or_skip(repo / "notes", os.path.join("sub", "x"))
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert ("notes/learnings.md not copied: it is reached through the symlink sub/x, which lies "
            "in a submodule, a nested repository or .git") in result.stdout
    assert not (repo / "docs" / "learnings.md").exists()


def test_a_link_under_a_linked_folder_is_named_by_its_own_path(tmp_path):
    # .claude -> cfg, cfg/hooks -> ../real: git is asked about cfg/hooks, not .claude/hooks
    # (behind a link, which git add refuses).
    repo = tmp_path / "repo"
    _git_init(repo)
    (repo / "cfg").mkdir()
    (repo / "real").mkdir()
    _symlink_or_skip(repo / ".claude", "cfg")
    _symlink_or_skip(repo / "cfg" / "hooks", os.path.join("..", "real"))
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert "could not say" not in result.stdout
    assert ("Commit real/context_check.py, .claude, cfg/hooks, cfg/settings.json and "
            "notes/learnings.md in that repository.") in result.stdout


def test_a_chain_out_of_the_repository_and_back_is_noted(tmp_path):
    repo = tmp_path / "repo"
    _git_init(repo)
    (repo / "docs").mkdir()
    (tmp_path / "out").mkdir()
    _symlink_or_skip(tmp_path / "out" / "n", str(repo / "docs"))
    _symlink_or_skip(repo / "notes", os.path.join("..", "out", "n"))
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert ("notes/learnings.md not copied: it is reached through the symlink notes, whose "
            "target is an absolute path or lies outside the repository") in result.stdout


def test_an_ignored_learnings_folder_is_not_told_to_force_add(tmp_path):
    # The learnings file is not written when git ignores it: "git add -f" had nothing to add.
    repo = tmp_path / "repo"
    _git_init(repo)
    (repo / ".gitignore").write_text("/notes/\n", encoding="utf-8")
    (repo / "notes").mkdir()
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert ("note: notes/learnings.md not copied: git ignores it, so cloud sessions would not "
            "see it; unignore it and run this again") in result.stdout
    assert "git add -f" not in result.stdout


def test_an_ignored_file_behind_a_link_is_force_added_by_its_real_path(tmp_path):
    # .claude -> cfg with cfg ignored: "git add -f .claude/settings.json" is refused (beyond a
    # symbolic link); the fix names cfg/settings.json.
    repo = tmp_path / "repo"
    _git_init(repo)
    (repo / "cfg").mkdir()
    _symlink_or_skip(repo / ".claude", "cfg")
    (repo / ".gitignore").write_text("/cfg/\n", encoding="utf-8")
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert ("note: .claude/settings.json is installed, but git ignores it, so cloud sessions "
            "will not see it; unignore it or commit it with git add -f cfg/settings.json") in result.stdout


def test_an_ignored_link_is_force_added_by_its_own_path(tmp_path):
    repo = tmp_path / "repo"
    _git_init(repo)
    (repo / "cfg").mkdir()
    _symlink_or_skip(repo / ".claude", "cfg")
    (repo / ".gitignore").write_text("/.claude\n", encoding="utf-8")
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert ("note: .claude/settings.json is installed, but it is reached through the symlink "
            ".claude, which git ignores, so cloud sessions will not see it; unignore .claude or "
            "commit it with git add -f .claude") in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="Windows folds .. in a link target as text")
def test_a_target_that_climbs_out_and_back_by_name_is_noted(tmp_path):
    # notes -> a/b/lnk/../r3/docs with lnk -> ../..: the text stays inside, the walk leaves
    # the repository and comes back by its folder name, which a clone elsewhere lacks.
    repo = tmp_path / "r3"
    _git_init(repo)
    (repo / "docs").mkdir()
    (repo / "a" / "b").mkdir(parents=True)
    _symlink_or_skip(repo / "a" / "b" / "lnk", os.path.join("..", ".."))
    _symlink_or_skip(repo / "notes", os.path.join("a", "b", "lnk", "..", "r3", "docs"))
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert ("notes/learnings.md not copied: it is reached through the symlink notes, whose "
            "target is an absolute path or lies outside the repository") in result.stdout
    assert not (repo / "docs" / "learnings.md").exists()


@pytest.mark.skipif(os.name == "nt", reason="Windows folds .. in a link target as text")
def test_a_target_that_only_looks_outside_is_followed(tmp_path):
    # notes -> lnk/../../docs with lnk -> a/b/c lands in a/docs: inside, so it is copied.
    repo = tmp_path / "repo"
    _git_init(repo)
    (repo / "a" / "b" / "c").mkdir(parents=True)
    (repo / "a" / "b" / "c" / "keep").write_text("", encoding="utf-8")
    _git(repo, "add", "a")
    (repo / "a" / "docs").mkdir()
    _symlink_or_skip(repo / "lnk", os.path.join("a", "b", "c"))
    _symlink_or_skip(repo / "notes", os.path.join("lnk", "..", "..", "docs"))
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert "not copied" not in result.stdout
    assert (repo / "a" / "docs" / "learnings.md").exists()
    assert "a/docs/learnings.md, notes and lnk in that repository." in result.stdout


def test_a_link_into_the_git_folder_is_noted(tmp_path):
    # notes -> .git/info: git add stages nothing there, yet the hint named it.
    repo = tmp_path / "repo"
    _git_init(repo)
    _symlink_or_skip(repo / "notes", os.path.join(".git", "info"))
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert ("notes/learnings.md not copied: it lands in a submodule, a nested repository or .git "
            "(.git/info/learnings.md)") in result.stdout
    assert not (repo / ".git" / "info" / "learnings.md").exists()


def test_a_submodule_that_is_not_checked_out_is_noted(tmp_path):
    # A plain clone leaves a submodule's folder empty, with no .git: it was missed.
    repo = tmp_path / "repo"
    _git_init(repo)
    subprocess.run(["git", "-C", str(repo), "update-index", "--add", "--cacheinfo",
                    "160000," + "1" * 40 + ",sub"], check=True, capture_output=True, env=git_env())
    (repo / "sub" / "notes").mkdir(parents=True)
    _symlink_or_skip(repo / "notes", os.path.join("sub", "notes"))
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert "could not say" not in result.stdout
    assert ("notes/learnings.md not copied: it lands in a submodule, a nested repository or .git "
            "(sub/notes/learnings.md)") in result.stdout


def test_a_link_past_the_hop_limit_is_judged_by_where_it_lands(add_to_repo, tmp_path):
    # Past 40 links the walker falls back to realpath, and called the link "ok" even when it
    # led outside the repository.
    repo = tmp_path / "repo"
    repo.mkdir()
    (tmp_path / "out").mkdir()
    _symlink_or_skip(repo / "l40", str(tmp_path / "out"))
    for i in range(39, 0, -1):
        _symlink_or_skip(repo / f"l{i}", f"l{i + 1}")
    _symlink_or_skip(repo / "notes", "l1")
    found, _ = add_to_repo._links(os.path.realpath(repo), "notes/learnings.md")
    assert found["l40"] == "absolute"


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=git_env())


def test_both_an_ignored_file_and_an_ignored_link_are_named(tmp_path):
    # .claude -> cfg with cfg and .claude ignored: "git add -f cfg/settings.json" alone left
    # the .claude link out of the clone.
    repo = tmp_path / "repo"
    _git_init(repo)
    (repo / "cfg").mkdir()
    _symlink_or_skip(repo / ".claude", "cfg")
    (repo / ".gitignore").write_text("/cfg/\n/.claude\n", encoding="utf-8")
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert ("note: .claude/settings.json is installed, but git ignores it and the symlink "
            ".claude, so cloud sessions will not see it; unignore them or commit them with git "
            "add -f cfg/settings.json .claude") in result.stdout


def test_the_force_add_path_is_quoted(tmp_path):
    repo = tmp_path / "repo"
    _git_init(repo)
    (repo / "my cfg").mkdir()
    _symlink_or_skip(repo / ".claude", "my cfg")
    (repo / ".gitignore").write_text("/my cfg/\n", encoding="utf-8")
    result = run(repo)
    assert result.returncode == 0, result.stderr
    quoted = '"my cfg/settings.json"' if os.name == "nt" else "'my cfg/settings.json'"
    assert "commit it with git add -f " + quoted in result.stdout


@pytest.mark.parametrize("layout", ["ignored", "untracked", "nested"])
def test_a_folder_a_link_passes_through_must_reach_a_clone(tmp_path, layout):
    # notes -> build/../docs: a clone without build has a notes link to nothing.
    repo = tmp_path / "repo"
    _git_init(repo)
    (repo / "docs").mkdir()
    if layout == "nested":
        _git_init(repo / "build")
    else:
        (repo / "build").mkdir()
        (repo / "build" / "keep").write_text("", encoding="utf-8")
    if layout == "ignored":
        (repo / ".gitignore").write_text("/build/\n", encoding="utf-8")
    _symlink_or_skip(repo / "notes", os.path.join("build", "..", "docs"))
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert "could not say" not in result.stdout
    why = {"ignored": "git ignores", "untracked": "git does not track (a clone lacks it)",
           "nested": "lies in a submodule, a nested repository or .git"}[layout]
    assert ("notes/learnings.md not copied: a symlink on its way passes through the folder "
            "build, which " + why) in result.stdout
    assert not (repo / "docs" / "learnings.md").exists()
    if layout == "untracked":
        _git(repo, "add", "build")
        result = run(repo)
        assert "not copied" not in result.stdout
        assert (repo / "docs" / "learnings.md").exists()


def test_a_link_at_a_submodule_path_is_noted(tmp_path):
    # notes recorded as a submodule, a notes -> docs link on disk: git add notes would
    # replace the submodule with the link.
    repo = tmp_path / "repo"
    _git_init(repo)
    _git(repo, "update-index", "--add", "--cacheinfo", "160000," + "1" * 40 + ",notes")
    (repo / "docs").mkdir()
    _symlink_or_skip(repo / "notes", "docs")
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert ("notes/learnings.md not copied: it is reached through the symlink notes, which lies "
            "in a submodule, a nested repository or .git") in result.stdout


def test_a_link_inside_a_submodule_that_is_not_checked_out_is_noted(tmp_path):
    # sub recorded as a submodule with no .git on disk, sub/x -> ../docs, notes -> sub/x.
    repo = tmp_path / "repo"
    _git_init(repo)
    _git(repo, "update-index", "--add", "--cacheinfo", "160000," + "1" * 40 + ",sub")
    (repo / "docs").mkdir()
    (repo / "sub").mkdir()
    _symlink_or_skip(repo / "sub" / "x", os.path.join("..", "docs"))
    _symlink_or_skip(repo / "notes", os.path.join("sub", "x"))
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert ("notes/learnings.md not copied: it is reached through the symlink sub/x, which lies "
            "in a submodule, a nested repository or .git") in result.stdout


def test_a_stderr_without_reconfigure_does_not_stop_the_run(add_to_repo, tmp_path, monkeypatch):
    # Only stdout was checked for reconfigure: a plain stderr raised AttributeError.
    class Plain:
        def write(self, text):
            return len(text)

        def flush(self):
            pass
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(io.BytesIO(), encoding="utf-8"))
    monkeypatch.setattr(sys, "stderr", Plain())
    with pytest.raises(SystemExit) as stopped:
        add_to_repo.main([str(tmp_path / "missing")])
    assert "usage:" in str(stopped.value)


@pytest.mark.skipif(os.name != "nt" and sys.platform != "darwin",
                    reason="needs a case-insensitive file system")
def test_a_submodule_recorded_in_other_case_is_noted(tmp_path):
    repo = tmp_path / "repo"
    _git_init(repo)
    _git(repo, "update-index", "--add", "--cacheinfo", "160000," + "1" * 40 + ",Notes")
    (repo / "notes").mkdir()
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert "notes/learnings.md not copied: it lands in a submodule" in result.stdout


def test_a_hook_link_out_of_a_new_claude_folder_is_hinted(tmp_path):
    # .claude/hooks/context_check.py -> ../../tools/context_check.py, nothing committed yet:
    # the hint commits .claude/hooks with the link, yet the walk's ".." through it was called
    # untracked and the hook dropped out of the hint.
    repo = tmp_path / "repo"
    _git_init(repo)
    (repo / "tools").mkdir()
    (repo / "tools" / "context_check.py").write_text("# old\n", encoding="utf-8")
    (repo / ".claude" / "hooks").mkdir(parents=True)
    try:
        os.symlink(os.path.join("..", "..", "tools", "context_check.py"),
                   repo / ".claude" / "hooks" / "context_check.py")
    except OSError:
        pytest.skip("cannot create symlinks here")
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert "note:" not in result.stdout
    assert "tools/context_check.py" in result.stdout
    assert ".claude/hooks/context_check.py" in result.stdout.splitlines()[-1]


def test_a_folder_holding_only_a_hinted_link_is_tracked(tmp_path):
    # notes -> sub/n, sub/n -> ../docs, sub new: committing the hinted link sub/n gives the
    # clone sub.
    repo = tmp_path / "repo"
    _git_init(repo)
    (repo / "docs").mkdir()
    (repo / "sub").mkdir()
    _symlink_or_skip(repo / "sub" / "n", os.path.join("..", "docs"))
    _symlink_or_skip(repo / "notes", os.path.join("sub", "n"))
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert "not copied" not in result.stdout
    assert (repo / "docs" / "learnings.md").exists()
    hint = result.stdout.splitlines()[-1]
    assert "docs/learnings.md" in hint and "sub/n" in hint and "notes" in hint


@pytest.mark.skipif(os.name == "nt", reason="Windows folds .. in a link target as text")
def test_passing_through_a_submodule_folder_is_fine(tmp_path):
    # notes -> sub/../docs with sub a recorded submodule: a clone has the (empty) sub folder.
    repo = tmp_path / "repo"
    _git_init(repo)
    _git(repo, "update-index", "--add", "--cacheinfo", "160000," + "1" * 40 + ",sub")
    (repo / "docs").mkdir()
    (repo / "sub").mkdir()
    _symlink_or_skip(repo / "notes", "sub/../docs")
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert "not copied" not in result.stdout
    assert (repo / "docs" / "learnings.md").exists()


@pytest.mark.skipif(os.name == "nt", reason="a fake git on PATH is a POSIX script")
def test_git_that_cannot_list_its_index_is_a_note(tmp_path):
    # ls-files failing (a timeout, an error) skipped the submodule and untracked checks
    # silently.
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "git"
    fake.write_text('#!/bin/sh\n[ "$3" = ls-files ] && exit 2\nexit 1\n', encoding="utf-8")
    fake.chmod(0o755)
    result = run(repo, env=git_env(PATH=str(bin_dir) + os.pathsep + os.environ.get("PATH", "")))
    assert result.returncode == 0, result.stderr
    assert ("note: git could not list what it records on the way, so submodules that are not "
            "checked out and folders git does not track went unchecked") in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="a fake git on PATH is a POSIX script")
def test_a_passed_folder_git_cannot_judge_is_a_note(tmp_path):
    # notes -> build/../docs, build recorded, check-ignore unable to answer: build itself got
    # no "could not say" note.
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "docs").mkdir()
    (repo / "build").mkdir()
    _symlink_or_skip(repo / "notes", "build/../docs")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "git"
    fake.write_text('#!/bin/sh\nif [ "$3" = ls-files ]; then\n'
                    "  printf '100644 %s 0\\tbuild/keep\\0' " + "1" * 40 + "\n  exit 0\nfi\n"
                    "exit 2\n", encoding="utf-8")
    fake.chmod(0o755)
    result = run(repo, env=git_env(PATH=str(bin_dir) + os.pathsep + os.environ.get("PATH", "")))
    assert result.returncode == 0, result.stderr
    assert "note: git could not say whether build is ignored" in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="':' cannot be in a Windows file name")
def test_a_passed_folder_is_asked_about_literally(tmp_path):
    # notes -> :b/../docs with :b/keep recorded: without literal pathspecs git reads ":b" as
    # magic for "b", lists nothing, and the tracked folder was called untracked.
    repo = tmp_path / "repo"
    _git_init(repo)
    (repo / "docs").mkdir()
    (repo / ":b").mkdir()
    (repo / ":b" / "keep").write_text("", encoding="utf-8")
    _git(repo, "add", "./:b")
    _symlink_or_skip(repo / "notes", ":b/../docs")
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert "not copied" not in result.stdout
    assert (repo / "docs" / "learnings.md").exists()


def test_a_path_is_quoted_for_the_shell(add_to_repo, monkeypatch):
    assert add_to_repo._arg("-x") == "./-x"
    assert add_to_repo._arg("a/b.json") == "a/b.json"
    monkeypatch.setattr(add_to_repo.os, "name", "nt")
    assert add_to_repo._arg("-x") == "./-x"
    assert add_to_repo._arg("@cfg/settings.json") == '"@cfg/settings.json"'
    assert add_to_repo._arg("100%/x") == '"100%/x"'
    assert "$ %" in add_to_repo._risk(["a$b/%x%"])
    assert add_to_repo._risk(["plain"]) == ""
