"""The GPT adapter must work from outside its source directory under -I."""
import subprocess
import sys

import pytest

from conftest import ROOT


@pytest.mark.skipif(sys.version_info < (3, 11), reason="GPT adapter requires Python 3.11+")
def test_gpt_standard_library_suite():
    """Include GPT's own suite in the existing repository CI on supported Python versions."""
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT / "gpt", capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(sys.version_info < (3, 11), reason="GPT adapter requires Python 3.11+")
def test_gpt_entrypoint_is_isolated_and_separate(tmp_path):
    result = subprocess.run(
        [sys.executable, "-I", str(ROOT / "gpt" / "umbrella.py"), "--help"],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "GPT Umbrella" in result.stdout
    assert "install" in result.stdout


def test_readme_distinguishes_platforms():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "[GPT / OpenAI Codex](gpt/README.md)" in readme
    assert "~/.claude" in readme
    assert "~/.codex" in readme


@pytest.mark.skipif(sys.version_info < (3, 11), reason="GPT adapter requires Python 3.11+")
def test_deep_json_is_a_short_cli_error(tmp_path):
    request = tmp_path / "request.json"
    request.write_text("[" * 2000 + "0" + "]" * 2000, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-I", str(ROOT / "gpt" / "umbrella.py"), "audit-requests", str(request)],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 1
    assert "GPT Umbrella:" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.skipif(sys.version_info < (3, 11), reason="GPT adapter requires Python 3.11+")
def test_output_path_prints_in_utf8_under_isolation(tmp_path):
    output = tmp_path / "report-\u2602.json"
    # Force the legacy ANSI setting on Windows even where the OS defaults to UTF-8.
    code = (
        "import runpy, sys; sys.stdout.reconfigure(encoding='cp1252'); "
        f"sys.argv = [{str(ROOT / 'gpt' / 'umbrella.py')!r}, 'audit', {str(tmp_path)!r}, "
        f"'--output', {str(output)!r}]; runpy.run_path(sys.argv[0], run_name='__main__')"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert str(output).encode("utf-8") in result.stdout
