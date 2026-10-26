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


def test_a_non_utf8_note_is_one_line_and_exit_1(keyline_hook, tmp_path, monkeypatch, capsys):
    # The handler was landed without a test; and its message read "cannot read: <path> is not
    # UTF-8", a stray colon because `where` is empty when the error names the note itself.
    note = tmp_path / "notes" / "todo.txt"
    note.parent.mkdir()
    note.write_bytes(b"Deploy at 14:00.\n\xff\xfe\n")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    event = {"tool_name": "Write", "cwd": str(tmp_path), "tool_input": {"file_path": str(note)}}
    assert run_main(keyline_hook, monkeypatch, event) == 1
    err = capsys.readouterr().err
    assert "Traceback" not in err and err.count("\n") == 1
    assert "todo.txt" in err and "not UTF-8" in err
    assert "read:" not in err


def test_a_dotfile_under_notes_is_not_a_note(keyline_hook, tmp_path, monkeypatch, capsys):
    # Path(".gitignore").suffix is "", so a dotfile written under notes/ was linted as an
    # extension-less note ("furniture: header", exit 2) or, when binary, was a read error.
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / ".gitignore").write_text("# Ignore\n*.bak\n", encoding="utf-8")
    (notes / ".DS_Store").write_bytes(b"Bud1\x00\x00\xff\xfe")
    (notes / ".env.he.txt").write_bytes(b"\xff\xfe")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    for name in (".gitignore", ".DS_Store", ".env.he.txt"):
        event = {"tool_name": "Write", "cwd": str(tmp_path), "tool_input": {"file_path": str(notes / name)}}
        assert run_main(keyline_hook, monkeypatch, event) == 0, name
        assert capsys.readouterr().err == "", name


@pytest.mark.parametrize("argv", [["--watch"], ["--watch", ""], ["--wacth", "x"], ["--watch", "x", "-v"]])
def test_a_watch_flag_without_a_pattern_is_an_error(keyline_hook, tmp_path, monkeypatch, capsys, argv):
    # `--watch` with no value, an empty one or a misspelt flag was ignored in silence and the
    # hook fell back to the notes/plans rule; keyline_lint's main() refuses the same shapes.
    note = tmp_path / "notes" / "todo.txt"
    note.parent.mkdir()
    note.write_text("Deploy at 14:00.\n", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    event = {"tool_name": "Write", "cwd": str(tmp_path), "tool_input": {"file_path": str(note)}}
    assert run_main(keyline_hook, monkeypatch, event, argv) == 1
    err = capsys.readouterr().err
    assert "Traceback" not in err and err.count("\n") == 1
    assert "keyline hook:" in err and argv[-1 if argv[-1].startswith("-") else 0] in err


def test_a_failed_rendering_names_the_rendering(keyline_hook, tmp_path, monkeypatch, capsys):
    # With the note clean and only the check failing, the header still said "this machine note
    # breaks the Keyline rules; fix the file", pointing Claude at the wrong file.
    pytest.importorskip("tiktoken")
    notes = tmp_path / "notes"
    notes.mkdir()
    note = notes / "a.txt"
    note.write_text("Deploy at 14:00 done.\n", encoding="utf-8")
    (notes / "a.he.txt").write_text("פריסה ב-15:00 הושלמה.\n", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    for written in (note, notes / "a.he.txt"):
        event = {"tool_name": "Write", "cwd": str(tmp_path), "tool_input": {"file_path": str(written)}}
        assert run_main(keyline_hook, monkeypatch, event) == 2
        err = capsys.readouterr().err
        head = err.splitlines()[0]
        assert "rendering" in head and "breaks the Keyline rules" not in head, err
        assert "FAIL notes/a.he.txt" in err
    # A note that breaks the lint keeps the note header, with or without a failing rendering.
    note.write_text("# Header\nDeploy at 14:00 done.\n", encoding="utf-8")
    event = {"tool_name": "Write", "cwd": str(tmp_path), "tool_input": {"file_path": str(note)}}
    assert run_main(keyline_hook, monkeypatch, event) == 2
    err = capsys.readouterr().err
    assert "breaks the Keyline rules" in err.splitlines()[0] and "FAIL notes/a.he.txt" in err


def test_a_markdown_rendering_is_a_rendering(keyline_hook, tmp_path, monkeypatch, capsys):
    # Only .he.txt was a rendering: notes/b.he.md was linted as a note, and its own rendering
    # looked for at b.he.he.txt; a write of notes/b.md never checked b.he.md.
    pytest.importorskip("tiktoken")
    notes = tmp_path / "notes"
    notes.mkdir()
    note = notes / "b.md"
    note.write_text("Deploy at 14:00 done.\n", encoding="utf-8")
    rendering = notes / "b.he.md"
    rendering.write_text("פריסה ב-15:00 הושלמה.\n", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    for written in (note, rendering):
        event = {"tool_name": "Write", "cwd": str(tmp_path), "tool_input": {"file_path": str(written)}}
        assert run_main(keyline_hook, monkeypatch, event) == 2, written
        err = capsys.readouterr().err
        assert "FAIL notes/b.he.md" in err and "checked against notes/b.md" in err, err
        assert "furniture" not in err and "b.he.he" not in err
    rendering.write_text("פריסה ב-14:00 הושלמה.\n", encoding="utf-8")
    event = {"tool_name": "Write", "cwd": str(tmp_path), "tool_input": {"file_path": str(rendering)}}
    assert run_main(keyline_hook, monkeypatch, event) == 0
    assert capsys.readouterr().err == ""


def test_two_notes_for_one_rendering_are_reported(keyline_hook, tmp_path, monkeypatch, capsys):
    # note_for() returned the first of four candidates: with c.txt and c.md beside c.he.txt
    # the .md note was never checked and nothing said so.
    pytest.importorskip("tiktoken")
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "c.txt").write_text("Deploy at 14:00 done.\n", encoding="utf-8")
    (notes / "c.md").write_text("Deploy at 16:00 done.\n", encoding="utf-8")
    rendering = notes / "c.he.txt"
    rendering.write_text("פריסה ב-14:00 הושלמה.\n", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    event = {"tool_name": "Write", "cwd": str(tmp_path), "tool_input": {"file_path": str(rendering)}}
    assert run_main(keyline_hook, monkeypatch, event) == 2
    err = capsys.readouterr().err
    assert "Traceback" not in err
    # The first line said "fix the rendering" and the per-note checks ran, so the second note's
    # FAIL block was shown as if the rendering were wrong: the fix is to remove a note, which
    # gets its own first line, and the checks wait until one note is left.
    lines = err.splitlines()
    assert lines[0] == keyline_hook.TWO_NOTES_HEADER, err
    assert "fix the rendering" not in lines[0] and "FAIL" not in err, err
    assert "notes/c.txt" in err and "notes/c.md" in err, err
    (notes / "c.md").unlink()
    assert run_main(keyline_hook, monkeypatch, event) == 0
    assert capsys.readouterr().err == ""


def test_an_explicit_watch_pattern_names_a_dotfile(keyline_hook, tmp_path, monkeypatch, capsys):
    # The dotfile rule (notes/.gitignore is not a note) ran after the --watch match, so a
    # pattern that named notes/.hidden.txt was accepted and the file was never linted: an
    # explicit pattern says what the user means, as it does for the notes/ folder rule.
    pytest.importorskip("tiktoken")
    note = tmp_path / "notes" / ".hidden.txt"
    note.parent.mkdir()
    note.write_text("- Server down 2026-10-20 14:00\n", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    event = {"tool_name": "Write", "cwd": str(tmp_path), "tool_input": {"file_path": str(note)}}
    assert run_main(keyline_hook, monkeypatch, event, argv=["--watch", "notes/.hidden.txt"]) == 2
    err = capsys.readouterr().err
    assert err.splitlines()[0] == keyline_hook.NOTE_HEADER and "furniture" in err, err
    assert run_main(keyline_hook, monkeypatch, event) == 0          # without a pattern: not a note
    assert capsys.readouterr().err == ""


@pytest.mark.skipif(os.name == "nt", reason="a file name outside UTF-8 needs a POSIX file system")
def test_a_file_name_outside_utf8_is_reported_not_a_traceback(keyline_hook, tmp_path, monkeypatch, capsys):
    # reconfigure(encoding="utf-8") also set errors="strict" on stderr (its default is
    # backslashreplace): a surrogate-escaped name from a non-UTF-8 file name turned every
    # message, findings and the one-line error alike, into a UnicodeEncodeError traceback.
    pytest.importorskip("tiktoken")
    notes = tmp_path / "notes"
    notes.mkdir()
    note = notes / os.fsdecode(b"\xff.txt")
    note.write_text("- Server down 2026-10-20 14:00\n", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    event = {"tool_name": "Write", "cwd": str(tmp_path), "tool_input": {"file_path": str(note)}}
    assert run_main(keyline_hook, monkeypatch, event) == 2
    err = capsys.readouterr().err
    assert "Traceback" not in err and err.splitlines()[0] == keyline_hook.NOTE_HEADER, err
    assert "\\udcff.txt" in err and "furniture" in err, err    # the escape, not the surrogate
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return                                     # root reads a mode-000 file
    note.chmod(0)
    try:
        assert run_main(keyline_hook, monkeypatch, event) == 1
        err = capsys.readouterr().err
        assert "Traceback" not in err and err.count("\n") == 1 and "cannot read" in err, err
    finally:
        note.chmod(0o644)
