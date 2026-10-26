import subprocess
import sys

from conftest import ROOT


def test_missing_tiktoken_gives_an_install_hint():
    code = ("import sys; sys.modules['tiktoken'] = None; import runpy; "
            f"runpy.run_path({str(ROOT / 'keyline' / 'measure.py')!r}, run_name='__main__')")
    result = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert "pip install -r keyline/requirements.txt" in result.stderr


def test_unreadable_file_is_skipped_not_a_traceback(tmp_path):
    import pytest
    pytest.importorskip("tiktoken")
    good = tmp_path / "good.txt"
    good.write_text("hello\n", encoding="utf-8")
    link = tmp_path / "gone.txt"
    try:
        link.symlink_to(tmp_path / "missing.txt")
    except OSError:
        pytest.skip("cannot create symlinks here")
    result = subprocess.run([sys.executable, "-I", str(ROOT / "keyline" / "measure.py"), str(tmp_path)],
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr and "skip" in result.stderr and "gone.txt" in result.stderr
    assert "good.txt" in result.stdout
