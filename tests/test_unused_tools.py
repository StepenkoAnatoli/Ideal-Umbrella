import pytest

from conftest import load_module, python_314_pathlib, refuse_looks_inside, write_jsonl


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
