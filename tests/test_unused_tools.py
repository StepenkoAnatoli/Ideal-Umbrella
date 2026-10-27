import pytest

import os
import sys

from conftest import ROOT, link_or_skip, load_module, loop_or_skip, not_found_at, python_314_pathlib, refuse_listing, refuse_looks_inside, write_jsonl


@pytest.fixture
def unused_tools():
    return load_module("unused_tools", "scripts/unused_tools.py")


def test_missing_folder_is_an_error(unused_tools, tmp_path, capsys):
    assert unused_tools.main([str(tmp_path / "no-such-dir")]) != 0
    assert "not a folder" in capsys.readouterr().err


def test_folder_without_transcripts_is_an_error(unused_tools, tmp_path, capsys):
    assert unused_tools.main([str(tmp_path)]) != 0
    assert "no *.jsonl transcripts" in capsys.readouterr().err


def test_denied_tool_that_was_called_is_flagged(unused_tools, tmp_path, capsys):
    write_jsonl(tmp_path / "s.jsonl", [
        {"message": {"content": [{"type": "tool_use", "name": "Artifact"}]}},
    ])
    assert unused_tools.main([str(tmp_path)]) == 0
    assert "Artifact: called 1 time(s)  <- review" in capsys.readouterr().out


def test_tool_use_without_a_name_is_not_counted(unused_tools, tmp_path, capsys):
    # A block with no "name" used to be counted as a tool called None.
    write_jsonl(tmp_path / "s.jsonl", [
        {"message": {"content": [{"type": "tool_use"}, {"type": "tool_use", "name": "Read"}]}},
    ])
    assert unused_tools.main([str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "1 tool calls, 1 distinct tools" in out
    assert "None" not in out


def test_a_folder_named_like_a_transcript_is_skipped(unused_tools, tmp_path, capsys):
    # rglob matched a folder named x.jsonl and open() raised IsADirectoryError.
    (tmp_path / "x.jsonl").mkdir()
    write_jsonl(tmp_path / "t.jsonl", [{"message": {"content": [{"type": "tool_use", "name": "Read"}]}}])
    assert unused_tools.main([str(tmp_path)]) == 0
    assert "Read" in capsys.readouterr().out


@pytest.mark.parametrize("pathlib_kind", ["3.13", "3.14"])
@pytest.mark.parametrize("where", ["argument", "walked"])
def test_a_transcript_that_cannot_be_looked_at_says_cannot_read(unused_tools, tmp_path, capsys, monkeypatch, where,
                                                                pathlib_kind):
    # Review 24, F1 other hits: on 3.13 the stat raised PermissionError (a traceback); on 3.14
    # is_dir() said "not a folder" for the argument and is_file() passed a transcript over, so
    # its tool calls went uncounted and a tool it called could be listed as unused.
    write_jsonl(tmp_path / "a.jsonl", [{"message": {"content": [{"type": "tool_use", "name": "Read"}]}}])
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    write_jsonl(blocked / "b.jsonl", [{"message": {"content": [{"type": "tool_use", "name": "Artifact"}]}}])
    if where == "argument":
        (blocked / "dir").mkdir()
    if pathlib_kind == "3.14":
        python_314_pathlib(monkeypatch)
    refuse_looks_inside(blocked, monkeypatch)
    arg = blocked / "dir" if where == "argument" else tmp_path
    assert unused_tools.main([str(arg)]) == 1
    err = capsys.readouterr().err
    assert "cannot read" in err and "not a folder" not in err, err
    assert str(arg if where == "argument" else blocked / "b.jsonl") in err, err


@pytest.mark.parametrize("which", ["top", "sub"])
def test_a_folder_that_cannot_be_listed_says_cannot_read(unused_tools, tmp_path, capsys, monkeypatch, which):
    # Review 26, C2: the rglob walk passed over a folder it could not list, so a transcript in
    # it went uncounted (exit 0), and an unlistable top folder read as "no *.jsonl transcripts".
    write_jsonl(tmp_path / "a.jsonl", [{"message": {"content": [{"type": "tool_use", "name": "Read"}]}}])
    sub = tmp_path / "sub"
    sub.mkdir()
    write_jsonl(sub / "b.jsonl", [{"message": {"content": [{"type": "tool_use", "name": "Artifact"}]}}])
    refused = tmp_path if which == "top" else sub
    refuse_listing(refused, monkeypatch)
    assert unused_tools.main([str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert f"cannot read {refused} (" in err and "no *.jsonl" not in err, err


@pytest.mark.skipif(os.name == "nt" or not hasattr(os, "geteuid") or os.geteuid() == 0,
                    reason="needs a user that file modes apply to")
def test_a_subfolder_that_cannot_be_listed_is_an_error_for_real(tmp_path):
    import subprocess
    write_jsonl(tmp_path / "a.jsonl", [{"message": {"content": [{"type": "tool_use", "name": "Read"}]}}])
    sub = tmp_path / "sub"
    sub.mkdir()
    write_jsonl(sub / "b.jsonl", [{"message": {"content": [{"type": "tool_use", "name": "Artifact"}]}}])
    sub.chmod(0o311)
    try:
        result = subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "unused_tools.py"), str(tmp_path)],
                                capture_output=True, text=True, encoding="utf-8", timeout=60)
    finally:
        sub.chmod(0o755)
    assert result.returncode == 1, result
    assert f"cannot read {sub} (" in result.stderr and "Traceback" not in result.stderr, result.stderr


def _calls(name, n=1):
    return [{"message": {"content": [{"type": "tool_use", "name": name}]}}] * n


def test_the_walk_keeps_rglobs_rules(unused_tools, tmp_path, capsys):
    # Review 27, L1: os.walk never puts a folder in names, so the folder test above no longer
    # reached the regular-file filter, and nothing pinned the rest of rglob's rules.
    write_jsonl(tmp_path / "t.jsonl", _calls("Read"))
    (tmp_path / ".hidden").mkdir()
    write_jsonl(tmp_path / ".hidden" / "h.jsonl", _calls("Grep"))      # rglob reads hidden folders
    write_jsonl(tmp_path / "notes.jsonl.bak", _calls("Bash"))            # not *.jsonl
    write_jsonl(tmp_path / "U.JSONL", _calls("Glob"))                    # *.jsonl on Windows only
    assert unused_tools.main([str(tmp_path)]) == 0
    out = capsys.readouterr().out
    n = 3 if os.name == "nt" else 2
    assert out.startswith(f"{n} transcripts, {n} tool calls, {n} distinct tools"), out
    assert "Bash" not in out


def test_a_linked_folder_and_a_dangling_link_are_not_counted(unused_tools, tmp_path, capsys):
    # Review 27, L1: as rglob, the walk does not follow a link to a folder (its transcripts would
    # be counted twice), and a dangling link named *.jsonl is passed over, not "cannot read".
    sub = tmp_path / "sub"
    sub.mkdir()
    write_jsonl(sub / "s.jsonl", _calls("Edit"))
    link_or_skip(tmp_path / "linked", sub, target_is_directory=True)
    link_or_skip(tmp_path / "gone.jsonl", tmp_path / "missing")
    assert unused_tools.main([str(tmp_path)]) == 0
    assert capsys.readouterr().out.startswith("1 transcripts, 1 tool calls")


def test_a_symlink_loop_named_like_a_transcript_is_passed_over(unused_tools, tmp_path, capsys):
    # Review 27, I2: os.stat raised ELOOP and the run stopped with "cannot read"; a loop holds
    # no transcript, so passing over it leaves nothing out (install's _look does the same).
    write_jsonl(tmp_path / "t.jsonl", _calls("Read"))
    loop_or_skip(tmp_path / "loop.jsonl")
    assert unused_tools.main([str(tmp_path)]) == 0
    assert capsys.readouterr().out.startswith("1 transcripts, 1 tool calls")


@pytest.mark.parametrize("which", ["file", "folder"])
def test_a_listed_name_that_is_not_found_says_cannot_read(unused_tools, tmp_path, capsys, monkeypatch, which):
    # Review 28, L1: pass 27 passed over a listed file or folder that os.stat or os.scandir
    # said was not found, as one removed during the walk. On Windows a path past MAX_PATH
    # says the same while it is there, and its transcripts went uncounted with exit 0.
    write_jsonl(tmp_path / "t.jsonl", _calls("Read"))
    sub = tmp_path / "sub"
    sub.mkdir()
    write_jsonl(sub / "u.jsonl", _calls("Edit"))
    hidden = sub / "u.jsonl" if which == "file" else sub
    not_found_at(hidden, monkeypatch)
    assert unused_tools.main([str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert f"cannot read {hidden}" in err, err


@pytest.mark.parametrize("target", ["missing", "through a file"])
def test_a_link_that_leads_nowhere_is_passed_over(unused_tools, tmp_path, capsys, target):
    # Review 29, L1: a dangling link whose target goes through a file gives NotADirectoryError,
    # not FileNotFoundError, and pass 28 stopped the run with "cannot read" for it.
    write_jsonl(tmp_path / "t.jsonl", _calls("Read"))
    (tmp_path / "afile").write_text("x", encoding="utf-8")
    link_or_skip(tmp_path / "b.jsonl", tmp_path / ("missing" if target == "missing" else "afile/b.jsonl"))
    assert unused_tools.main([str(tmp_path)]) == 0
    assert capsys.readouterr().out.startswith("1 transcripts, 1 tool calls")


def test_a_link_into_a_folder_that_cannot_be_searched_says_cannot_read(unused_tools, tmp_path, capsys, monkeypatch):
    # Review 29, L2: nothing failed when every error on a link was passed over, so a link to a
    # transcript in a folder that cannot be searched would have gone uncounted.
    write_jsonl(tmp_path / "t.jsonl", _calls("Read"))
    locked = tmp_path / "locked"
    locked.mkdir()
    write_jsonl(locked / "x.jsonl", _calls("Edit"))
    link_or_skip(tmp_path / "b.jsonl", locked / "x.jsonl")
    refuse_looks_inside(locked, monkeypatch)
    assert unused_tools.main([str(tmp_path)]) == 1
    assert f"cannot read {tmp_path / 'b.jsonl'}" in capsys.readouterr().err


@pytest.mark.parametrize("kind", ["through a file", "loop"])
def test_an_argument_that_leads_nowhere_is_not_a_folder(unused_tools, tmp_path, capsys, kind):
    # Review 29, info 2: nothing pinned _is's not-a-directory and loop branches, which now judge
    # only the argument.
    if kind == "loop":
        arg = tmp_path / "loop"
        loop_or_skip(arg)
    else:
        (tmp_path / "afile").write_text("x", encoding="utf-8")
        arg = tmp_path / "afile" / "sub"
    assert unused_tools.main([str(arg)]) == 2
    assert f"{arg} is not a folder" in capsys.readouterr().err
