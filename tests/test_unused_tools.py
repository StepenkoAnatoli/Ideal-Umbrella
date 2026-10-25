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
