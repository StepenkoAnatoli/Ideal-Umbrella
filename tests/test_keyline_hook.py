import io
import json
import os
import subprocess
import sys

import pytest

from conftest import ROOT, load_module, python_314_pathlib, refuse_looks_inside

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


@pytest.mark.parametrize("pathlib_kind", ["3.13", "3.14"])
def test_a_file_that_cannot_be_stated_is_one_line_not_a_traceback(keyline_hook, tmp_path, monkeypatch, capsys,
                                                                  pathlib_kind):
    # path.is_file() on a file in a folder that cannot be searched raises PermissionError;
    # it was outside every handler in main(). Review 24, F1 other hits: on Python 3.14 it says
    # False instead, and the note was passed over without a word.
    note = tmp_path / "notes" / "todo.md"
    note.parent.mkdir()
    note.write_text("# My todo\n", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    event = {"tool_name": "Write", "cwd": str(tmp_path), "tool_input": {"file_path": str(note)}}
    if pathlib_kind == "3.14":
        python_314_pathlib(monkeypatch)
    refuse_looks_inside(note.parent, monkeypatch)
    assert run_main(keyline_hook, monkeypatch, event) == 1
    err = capsys.readouterr().err
    assert "Traceback" not in err and "cannot read" in err and "todo.md" in err


def test_a_path_through_a_file_passes_silently(keyline_hook, tmp_path, monkeypatch, capsys):
    # Review 26, C3: nothing failed when NotADirectoryError ("a_file/x.md") read as "cannot
    # read"; such a path is not a file the hook watches, as a missing one is not.
    (tmp_path / "a_file").write_text("", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    event = {"tool_name": "Write", "cwd": str(tmp_path), "tool_input": {"file_path": str(tmp_path / "a_file" / "x.md")}}
    assert run_main(keyline_hook, monkeypatch, event) == 0
    assert capsys.readouterr().err == ""


def test_a_path_holding_a_nul_byte_passes_silently(keyline_hook, tmp_path, monkeypatch, capsys):
    # Review 26, info 2: os.stat raises ValueError for a NUL byte, a traceback where is_file()
    # said False; no file has such a name, so the hook has nothing to check.
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    event = {"tool_name": "Write", "cwd": str(tmp_path), "tool_input": {"file_path": str(tmp_path / "x\0.md")}}
    assert run_main(keyline_hook, monkeypatch, event) == 0
    assert capsys.readouterr().err == ""


# ---- review 8 (main bcc441c) ----

WORDS = {"please", "wait", "deploy", "today", "buy", "milk", "ignore", "list"}


def notes_project(keyline_hook, tmp_path, monkeypatch):
    """A project with a notes/ folder; the lint's word list is a fixed set (no tiktoken)."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setattr(keyline_hook.keyline_lint, "load_words", lambda: set(WORDS))
    notes = tmp_path / "notes"
    notes.mkdir()
    return notes


def edit(keyline_hook, monkeypatch, path, argv=()):
    return run_main(keyline_hook, monkeypatch, {"tool_name": "Write", "tool_input": {"file_path": str(path)}}, argv)


def test_a_note_that_is_not_utf8_is_named_once_without_a_stray_colon(keyline_hook, tmp_path, monkeypatch, capsys):
    # Review 8, low 5: "cannot read: <path> is not UTF-8".
    notes = notes_project(keyline_hook, tmp_path, monkeypatch)
    note = notes / "c.txt"
    note.write_bytes(b"caf\xe9\n")
    assert edit(keyline_hook, monkeypatch, note) == 1
    err = capsys.readouterr().err
    assert err.startswith(f"keyline hook: {note} is not UTF-8") and "read:" not in err
    assert err.count(str(note)) == 1


def test_a_rendering_that_is_not_utf8_is_not_blamed_on_the_note(keyline_hook, tmp_path, monkeypatch, capsys):
    # Review 8, low 5: "cannot read <note>: <rendering> is not UTF-8".
    notes = notes_project(keyline_hook, tmp_path, monkeypatch)
    note = notes / "c.txt"
    note.write_text("deploy v2 today\n", encoding="utf-8")
    (notes / "c.he.txt").write_bytes(b"\xff\n")
    assert edit(keyline_hook, monkeypatch, note) == 1
    err = capsys.readouterr().err
    assert "c.he.txt is not UTF-8" in err and str(note) not in err


@pytest.mark.parametrize("name, data", [
    (".gitignore", b"# Ignore list\n"),
    (".DS_Store", b"\xff\x00\n"),
    (".obsidian/workspace.md", b"# please wait\n"),
])
def test_a_dotfile_under_notes_is_not_a_note(keyline_hook, tmp_path, monkeypatch, capsys, name, data):
    # Review 8, low 11: .gitignore failed on "furniture: header", .DS_Store on "cannot read".
    notes = notes_project(keyline_hook, tmp_path, monkeypatch)
    path = notes / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    assert edit(keyline_hook, monkeypatch, path) == 0
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("argv", [["--watch"], ["--watch", ""], ["--wacth", "PROGRESS.md"], ["extra"]])
def test_a_bad_hook_argument_is_reported_not_ignored(keyline_hook, tmp_path, monkeypatch, capsys, argv):
    # Review 8, low 12: these fell back to the notes rule without a word.
    notes = notes_project(keyline_hook, tmp_path, monkeypatch)
    note = notes / "c.txt"
    note.write_text("please wait\n", encoding="utf-8")
    assert edit(keyline_hook, monkeypatch, note, argv) == 1
    err = capsys.readouterr().err
    assert err.startswith("keyline hook:") and err.count("\n") == 1 and "Traceback" not in err


def test_an_inconclusive_rendering_alone_does_not_say_the_note_breaks_the_rules(keyline_hook, tmp_path, monkeypatch,
                                                                               capsys):
    # Review 8, low 13.
    notes = notes_project(keyline_hook, tmp_path, monkeypatch)
    note = notes / "c.txt"
    note.write_text("please wait\n", encoding="utf-8")
    (notes / "c.he.txt").write_text("נא להמתין\n", encoding="utf-8")
    assert edit(keyline_hook, monkeypatch, note) == 2
    err = capsys.readouterr().err
    assert "INCONCLUSIVE" in err and "breaks the Keyline rules" not in err


def test_a_lint_finding_still_says_the_note_breaks_the_rules(keyline_hook, tmp_path, monkeypatch, capsys):
    notes = notes_project(keyline_hook, tmp_path, monkeypatch)
    note = notes / "c.txt"
    note.write_text("- please wait\n", encoding="utf-8")
    assert edit(keyline_hook, monkeypatch, note) == 2
    assert "breaks the Keyline rules" in capsys.readouterr().err


@pytest.mark.parametrize("suffix", [".he.md", ".he.keyline"])
def test_a_rendering_in_markdown_or_keyline_is_checked_not_linted(keyline_hook, tmp_path, monkeypatch, capsys,
                                                                  suffix):
    # Review 8, low 14: only .he.txt counted, so b.he.md was linted as a note and never checked.
    notes = notes_project(keyline_hook, tmp_path, monkeypatch)
    note = notes / "b.md"
    note.write_text("deploy v2 today\n", encoding="utf-8")
    rendering = notes / ("b" + suffix)
    rendering.write_text("**לפרוס** v2 היום\n", encoding="utf-8")
    assert edit(keyline_hook, monkeypatch, rendering) == 0, capsys.readouterr().err
    rendering.write_text("לפרוס היום\n", encoding="utf-8")
    assert edit(keyline_hook, monkeypatch, note) == 2
    assert "FAIL" in capsys.readouterr().err


def test_a_rendering_is_checked_against_every_note_with_its_stem(keyline_hook, tmp_path, monkeypatch, capsys):
    # Review 8, low 14: c.he.txt was checked against c.txt only, so a mismatch with c.md passed.
    notes = notes_project(keyline_hook, tmp_path, monkeypatch)
    (notes / "c.txt").write_text("deploy v2 today\n", encoding="utf-8")
    (notes / "c.md").write_text("deploy v3 today\n", encoding="utf-8")
    rendering = notes / "c.he.txt"
    rendering.write_text("לפרוס v2 היום\n", encoding="utf-8")
    assert edit(keyline_hook, monkeypatch, rendering) == 2
    err = capsys.readouterr().err
    assert "c.md" in err and "v3" in err


def test_a_rendering_named_in_capitals_is_found_from_its_note(keyline_hook, tmp_path, monkeypatch, capsys):
    # Review 8, low 40: is_rendering ignored case, the sibling lookup did not.
    notes = notes_project(keyline_hook, tmp_path, monkeypatch)
    note = notes / "c.txt"
    note.write_text("deploy v2 today\n", encoding="utf-8")
    (notes / "c.HE.TXT").write_text("לפרוס היום\n", encoding="utf-8")
    assert edit(keyline_hook, monkeypatch, note) == 2
    assert "c.HE.TXT" in capsys.readouterr().err


# ---- self-review of the review 8 fixes ----

@pytest.mark.parametrize("stem", ["data.json", "v1.2"])
def test_a_rendering_is_not_checked_against_a_file_that_is_not_a_note(keyline_hook, tmp_path, monkeypatch, capsys,
                                                                      stem):
    # S10: editing data.json.he.txt checked it against data.json (exit 2), while editing
    # data.json checked nothing: a file is a note only with a note suffix, in both directions.
    notes = notes_project(keyline_hook, tmp_path, monkeypatch)
    other = notes / stem
    other.write_text("deploy v9 today\n", encoding="utf-8")
    rendering = notes / (stem + ".he.txt")
    rendering.write_text("לפרוס היום\n", encoding="utf-8")
    assert edit(keyline_hook, monkeypatch, other) == 0
    assert edit(keyline_hook, monkeypatch, rendering) == 0
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("argv", [["--watch", "--print-config"], ["--watch", " "], ["--watch", "--watch"]])
def test_a_watch_pattern_that_is_an_option_or_blank_is_refused(keyline_hook, tmp_path, monkeypatch, capsys, argv):
    # S11: "--watch --print-config" took --print-config as a pattern and exited 0.
    notes = notes_project(keyline_hook, tmp_path, monkeypatch)
    note = notes / "c.txt"
    note.write_text("please wait\n", encoding="utf-8")
    assert edit(keyline_hook, monkeypatch, note, argv) == 1
    err = capsys.readouterr().err
    assert err.startswith("keyline hook:") and err.count("\n") == 1


def test_a_rendering_that_cannot_be_opened_is_named_with_the_reason(keyline_hook, tmp_path, monkeypatch, capsys):
    # S9: the e.filename branch of the read-error message had no test.
    import errno
    notes = notes_project(keyline_hook, tmp_path, monkeypatch)
    note = notes / "c.txt"
    note.write_text("deploy v2 today\n", encoding="utf-8")
    rendering = notes / "c.he.txt"
    rendering.write_text("לפרוס v2 היום\n", encoding="utf-8")
    real_read = keyline_hook.keyline_check.read

    def read(path):
        if path == rendering:
            raise PermissionError(errno.EACCES, "Permission denied", str(path))
        return real_read(path)
    monkeypatch.setattr(keyline_hook.keyline_check, "read", read)
    assert edit(keyline_hook, monkeypatch, note) == 1
    assert capsys.readouterr().err == f"keyline hook: cannot read {rendering}: Permission denied\n"


def test_a_folder_named_like_a_rendering_is_not_a_rendering(keyline_hook, tmp_path, monkeypatch, capsys):
    # S9: the is_file() check in _siblings had no test.
    notes = notes_project(keyline_hook, tmp_path, monkeypatch)
    note = notes / "c.txt"
    note.write_text("deploy v2 today\n", encoding="utf-8")
    (notes / "c.he.txt").mkdir()
    assert edit(keyline_hook, monkeypatch, note) == 0
    assert capsys.readouterr().err == ""
