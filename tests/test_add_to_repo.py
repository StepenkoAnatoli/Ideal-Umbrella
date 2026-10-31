import json
import os
import subprocess
import sys

import pytest

from conftest import ROOT

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
    assert "symlink to a missing target" in result.stderr and "nothing written" in result.stderr, result.stderr
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
    assert "note: .claude/settings.json is ignored by git" in result.stdout
    assert "note: .claude/hooks/context_check.py is ignored by git" in result.stdout
    assert "Commit notes/learnings.md in that repository." in result.stdout
    again = run(repo)   # the note stood on the first run only: a second one said "up to date"
    assert "note: .claude/settings.json is ignored by git" in again.stdout
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
    fake.write_text("#!/bin/sh\nexit 128\n", encoding="utf-8")
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
        assert ("note: .claude/settings.json is reached through the symlink .claude, which git "
                "ignores") in result.stdout
        assert ("note: .claude/hooks/context_check.py is reached through the symlink .claude"
                in result.stdout)
        assert "Commit" not in result.stdout
        assert "notes/learnings.md not copied: git ignores it" in result.stdout
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
    assert "note: .claude/hooks/context_check.py lands outside the repository" in result.stdout
    assert "note: notes/learnings.md not copied: a symlink puts it outside the repository" in result.stdout
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
    os.symlink(odd, os.path.join(os.fsencode(str(repo)), b"notes"))
    result = run(repo)
    assert result.returncode == 0, result.stderr
    assert (repo / ".claude" / "hooks" / "context_check.py").is_file()
    assert os.path.isfile(os.path.join(odd, b"learnings.md"))
    assert "could not say" not in result.stdout
