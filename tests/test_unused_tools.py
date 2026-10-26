import json

import pytest

from conftest import load_module, write_jsonl


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


def test_an_unreadable_transcript_is_one_line(unused_tools, tmp_path, capsys, monkeypatch):
    # The transcript was opened outside any try, so a file unreadable between the glob and
    # the read was a traceback; the other transcript scripts open in a try with one line.
    import builtins
    write_jsonl(tmp_path / "good.jsonl", [{"message": {"content": [{"type": "tool_use", "name": "Read"}]}}])
    locked = write_jsonl(tmp_path / "locked.jsonl", [])
    real_open = builtins.open

    def failing_open(file, *args, **kwargs):
        if str(file) == str(locked):
            raise PermissionError(13, "Permission denied", str(file))
        return real_open(file, *args, **kwargs)
    monkeypatch.setattr(builtins, "open", failing_open)
    assert unused_tools.main([str(tmp_path)]) == 0
    out, err = capsys.readouterr()
    assert "Read: 1" in out
    assert err.count("\n") == 1 and "locked.jsonl" in err and "Permission denied" in err


def test_a_transcript_with_a_bom_is_read(unused_tools, tmp_path, capsys):
    # A BOM made the first line unparseable, so its tool call was dropped in silence.
    (tmp_path / "s.jsonl").write_text(
        json.dumps({"message": {"content": [{"type": "tool_use", "name": "Read"}]}}) + "\n", encoding="utf-8-sig")
    assert unused_tools.main([str(tmp_path)]) == 0
    assert "Read: 1" in capsys.readouterr().out
