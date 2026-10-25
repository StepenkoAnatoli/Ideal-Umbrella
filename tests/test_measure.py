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
