"""Every script prints UTF-8 whatever the console code page.

The scripts run with -I, which ignores PYTHONUTF8 and PYTHONIOENCODING, so on a Windows host
stdout is the ANSI code page (cp1252) unless the script sets UTF-8 itself. A transcript line
holding a stray byte becomes U+FFFD after decoding with errors="replace", and printing it used
to end usertext_top.py with UnicodeEncodeError. This reproduces that console on any OS: the
scripts are started without -I, with UTF-8 mode off and stdout forced to cp1252.
"""
import os
import subprocess
import sys

import pytest

from conftest import ROOT, write_jsonl


def run_cp1252(script, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    env["PYTHONIOENCODING"] = "cp1252"
    return subprocess.run([sys.executable, "-X", "utf8=0", str(ROOT / script), *args],
                          cwd=ROOT, capture_output=True, env=env)


def ok(result, expected):
    err = result.stderr.decode("utf-8", "replace")
    assert "UnicodeEncodeError" not in err and "Traceback" not in err, err
    assert result.returncode == 0, err
    try:
        out = result.stdout.decode("utf-8")
    except UnicodeDecodeError:
        pytest.fail(f"stdout is not UTF-8: {result.stdout!r}")
    assert expected in out


@pytest.mark.parametrize("script, expected", [("usertext_top.py", "please list"),
                                              ("usertext_split.py", "typed by user")])
def test_user_text_scripts_print_the_replacement_character(script, expected, tmp_path):
    odd = tmp_path / "odd.jsonl"
    odd.write_bytes(b'{"message": {"role": "user", "content": "caf\xe9 please list the files"}}\n')
    ok(run_cp1252(f"scripts/{script}", str(odd)), expected)


def test_toolresult_share_prints_a_non_ascii_tool_name(tmp_path):
    path = write_jsonl(tmp_path / "t.jsonl", [
        {"message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t1", "name": "mcp__x__café", "input": {}}]}},
        {"message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "x" * 20}]}},
    ])
    ok(run_cp1252("scripts/toolresult_share.py", str(path)), "mcp:café")


def test_unused_tools_prints_a_non_ascii_tool_name(tmp_path):
    write_jsonl(tmp_path / "t.jsonl", [
        {"message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t1", "name": "Café", "input": {}}]}},
    ])
    ok(run_cp1252("scripts/unused_tools.py", str(tmp_path)), "Café: 1")


# scripts/usage_breakdown.py prints only ASCII (counts and fixed keys); tests/test_source_rules.py
# keeps its UTF-8 stdout. A cp1252 run of it cannot tell the fixed script from the old one.
