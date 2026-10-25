"""The three small transcript scripts: usage, non-object lines, empty input, a normal run."""
import subprocess
import sys

import pytest

from conftest import ROOT, write_jsonl

SCRIPTS = ["toolresult_share.py", "usertext_split.py", "usertext_top.py"]


def run(script, *args):
    return subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / script), *args],
                          cwd=ROOT, capture_output=True, text=True, encoding="utf-8")


@pytest.mark.parametrize("script", SCRIPTS)
def test_no_arguments_prints_usage(script):
    result = run(script)
    assert result.returncode != 0
    assert "usage:" in result.stderr


@pytest.mark.parametrize("script", SCRIPTS)
def test_non_object_lines_and_empty_input_do_not_crash(script, tmp_path):
    # A line holding a JSON list used to raise AttributeError; an empty file divided by zero.
    odd = tmp_path / "odd.jsonl"
    odd.write_text('[1, 2]\n"text"\nnull\n', encoding="utf-8")
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    for path in (odd, empty):
        result = run(script, str(path))
        assert "Traceback" not in result.stderr, result.stderr
        assert "no " in result.stderr and "found" in result.stderr


def transcript(tmp_path):
    return write_jsonl(tmp_path / "t.jsonl", [
        {"message": {"role": "user", "content": "please list the files"}},
        {"message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}}]}},
        {"message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "a.py\nb.py\n"},
            {"type": "text", "text": "<system-reminder>keep going</system-reminder>"}]}},
        {"message": {"role": "assistant", "content": [{"type": "text", "text": "two files"}]}},
    ])


def test_toolresult_share_reports_by_tool(tmp_path):
    result = run("toolresult_share.py", str(transcript(tmp_path)))
    assert result.returncode == 0, result.stderr
    assert "tool results 10" in result.stdout
    assert "Bash" in result.stdout


def test_usertext_split_classifies_blocks(tmp_path):
    result = run("usertext_split.py", str(transcript(tmp_path)))
    assert result.returncode == 0, result.stderr
    assert "other system-reminder" in result.stdout
    assert "typed by user / other" in result.stdout


def test_usertext_top_groups_by_head(tmp_path):
    result = run("usertext_top.py", str(transcript(tmp_path)))
    assert result.returncode == 0, result.stderr
    assert "<system-reminder>" in result.stdout
    assert "please list the" in result.stdout
