import io
import json
import os
import subprocess
import sys

import pytest

from conftest import ROOT, load_module

HOOK = ROOT / "keyline" / "keyline_hook.py"


@pytest.fixture
def keyline_hook():
    return load_module("keyline_hook", "keyline/keyline_hook.py")


def test_a_note_outside_the_project_is_not_watched(keyline_hook, tmp_path):
    # When the path was not under the project, watched() fell back to the absolute path and
    # matched any notes/ or plans/ folder anywhere (~/notes/todo.md).
    proj = tmp_path / "proj"
    inside = proj / "notes" / "todo.md"
    outside = tmp_path / "elsewhere" / "notes" / "todo.md"
    for note in (inside, outside):
        note.parent.mkdir(parents=True)
        note.write_text("# My todo\n- buy milk\n", encoding="utf-8")
    assert keyline_hook.watched(inside, proj)
    assert not keyline_hook.watched(outside, proj)
    assert keyline_hook.watched(outside, proj, [str(outside)])   # an explicit --watch still applies

    event = json.dumps({"tool_name": "Write", "cwd": str(proj), "tool_input": {"file_path": str(outside)}})
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(proj))
    result = subprocess.run([sys.executable, "-I", str(HOOK)], input=event, capture_output=True,
                            text=True, encoding="utf-8", env=env)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


@pytest.mark.skipif(os.name == "nt", reason="symlinks need a privilege on Windows")
def test_a_symlinked_notes_folder_inside_the_project_is_watched(keyline_hook, tmp_path):
    # The outside-project fix resolved the path first, so a notes/ folder that is a symlink to
    # a folder elsewhere (Dropbox, another repo) left the project and was no longer watched.
    proj = tmp_path / "proj"
    proj.mkdir()
    real = tmp_path / "dropbox_notes"
    real.mkdir()
    (proj / "notes").symlink_to(real, target_is_directory=True)
    note = proj / "notes" / "todo.md"
    note.write_text("# My todo\n", encoding="utf-8")
    assert keyline_hook.watched(note, proj)
    assert not keyline_hook.watched(real / "todo.md", proj)


def run_main(keyline_hook, monkeypatch, event, argv=()):
    """Run the hook's main() in process on one event; return its exit code."""
    stdin = io.TextIOWrapper(io.BytesIO(json.dumps(event).encode("utf-8")), encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "argv", ["keyline_hook.py", *argv])
    return keyline_hook.main()


def test_a_word_cache_error_is_not_reported_as_the_note_being_unreadable(keyline_hook, tmp_path, monkeypatch, capsys):
    # An OSError from loading the lint's word cache (a folder in the way, a read-only cache
    # path) was caught by the "cannot read <note>" handler and blamed on the note.
    note = tmp_path / "notes" / "todo.md"
    note.parent.mkdir()
    note.write_text("# My todo\n", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    def failing_load_words():
        raise OSError("cache/o200k_single_token_words.txt is a folder")

    monkeypatch.setattr(keyline_hook.keyline_lint, "load_words", failing_load_words)
    code = run_main(keyline_hook, monkeypatch, {"tool_name": "Write", "tool_input": {"file_path": str(note)}})
    err = capsys.readouterr().err
    assert code == 1
    assert "is a folder" in err and "cannot read" not in err


def test_a_cwd_that_is_not_a_string_is_ignored(keyline_hook, tmp_path, monkeypatch, capsys):
    # A malformed event with "cwd": 5 reached Path(5) and raised TypeError.
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    event = {"tool_name": "Write", "cwd": 5, "tool_input": {"file_path": "elsewhere/todo.md"}}
    assert run_main(keyline_hook, monkeypatch, event) == 0
    assert capsys.readouterr().err == ""


def test_watch_patterns_do_not_lift_the_suffix_rule(keyline_hook, tmp_path, monkeypatch, capsys):
    # The docs said --watch checks the matching files "instead"; a watched .py file is still
    # not a note and is passed over.
    script = tmp_path / "PROGRESS.py"
    script.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    event = {"tool_name": "Write", "tool_input": {"file_path": str(script)}}
    assert run_main(keyline_hook, monkeypatch, event, ["--watch", str(script)]) == 0
    assert capsys.readouterr().err == ""
    doc = keyline_hook.__doc__ + (ROOT / "keyline" / "README.md").read_text(encoding="utf-8")
    assert doc.count("suffix rule still applies") == 2


def test_a_file_that_cannot_be_stated_is_one_line_not_a_traceback(keyline_hook, tmp_path, monkeypatch, capsys):
    # path.is_file() on a file in a folder that cannot be searched raises PermissionError;
    # it was outside every handler in main().
    from pathlib import Path
    note = tmp_path / "notes" / "todo.md"
    note.parent.mkdir()
    note.write_text("# My todo\n", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    real_is_file = Path.is_file

    def is_file(self, *a, **k):
        if self == note:
            raise PermissionError(13, "Permission denied", str(self))
        return real_is_file(self, *a, **k)
    monkeypatch.setattr(Path, "is_file", is_file)
    event = {"tool_name": "Write", "cwd": str(tmp_path), "tool_input": {"file_path": str(note)}}
    assert run_main(keyline_hook, monkeypatch, event) == 1
    err = capsys.readouterr().err
    assert "Traceback" not in err and "cannot read" in err and "todo.md" in err
