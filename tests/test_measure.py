import os
import subprocess
import sys

import pytest

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


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no named pipes here")
def test_a_named_pipe_in_a_folder_is_skipped_not_read(tmp_path):
    # os.walk lists a FIFO like any file, and reading it blocked until a writer came along.
    pytest.importorskip("tiktoken")
    (tmp_path / "good.txt").write_text("hello\n", encoding="utf-8")
    os.mkfifo(tmp_path / "pipe.txt")
    result = subprocess.run([sys.executable, "-I", str(ROOT / "keyline" / "measure.py"), str(tmp_path)],
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr and "skip" in result.stderr and "pipe.txt" in result.stderr
    assert "good.txt" in result.stdout


@pytest.mark.skipif(os.name == "nt" or not hasattr(os, "geteuid") or os.geteuid() == 0,
                    reason="needs a user that file modes apply to")
def test_a_file_that_cannot_be_stated_is_skipped_not_a_traceback(tmp_path):
    # A readable but not searchable folder lists its names, and then every stat of a name in
    # it fails; the walk must skip those files, as it skips a file it cannot read.
    pytest.importorskip("tiktoken")
    (tmp_path / "good.txt").write_text("hello\n", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "hidden.txt").write_text("hello\n", encoding="utf-8")
    sub.chmod(0o444)
    try:
        result = subprocess.run([sys.executable, "-I", str(ROOT / "keyline" / "measure.py"), str(tmp_path)],
                                capture_output=True, text=True, encoding="utf-8", timeout=30)
    finally:
        sub.chmod(0o755)
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr and "skip" in result.stderr and "hidden.txt" in result.stderr
    assert "good.txt" in result.stdout


@pytest.mark.skipif(os.name == "nt" or not hasattr(os, "geteuid") or os.geteuid() == 0,
                    reason="needs a user that file modes apply to")
def test_an_argument_that_cannot_be_stated_is_one_line_not_a_traceback(tmp_path):
    pytest.importorskip("tiktoken")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "hidden.txt").write_text("hello\n", encoding="utf-8")
    sub.chmod(0o444)
    try:
        result = subprocess.run([sys.executable, "-I", str(ROOT / "keyline" / "measure.py"), str(sub / "hidden.txt")],
                                capture_output=True, text=True, encoding="utf-8", timeout=30)
    finally:
        sub.chmod(0o755)
    assert result.returncode == 2
    assert "Traceback" not in result.stderr and "cannot read" in result.stderr and "hidden.txt" in result.stderr


@pytest.mark.skipif(os.name == "nt" or not hasattr(os, "geteuid") or os.geteuid() == 0,
                    reason="needs a user that file modes apply to")
def test_a_file_that_cannot_be_read_is_skipped_not_a_traceback(tmp_path):
    # The read handler was landed without a test: the dangling-symlink test is now caught by
    # the is_file() check before any read, so deleting the handler left every test green.
    pytest.importorskip("tiktoken")
    (tmp_path / "good.txt").write_text("hello\n", encoding="utf-8")
    locked = tmp_path / "locked.txt"
    locked.write_text("secret\n", encoding="utf-8")
    locked.chmod(0)
    try:
        result = subprocess.run([sys.executable, "-I", str(ROOT / "keyline" / "measure.py"), str(tmp_path)],
                                capture_output=True, text=True, encoding="utf-8", timeout=30)
    finally:
        locked.chmod(0o644)
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr and "skip" in result.stderr and "locked.txt" in result.stderr
    assert "good.txt" in result.stdout and "locked.txt" not in result.stdout


def test_a_named_file_that_cannot_be_counted_is_an_error(tmp_path):
    # The skip path was written for walked folders: a file named on the command line that is
    # not UTF-8 was "skipped" with exit 0 and the change line left out in silence; an empty
    # folder printed the header only.
    pytest.importorskip("tiktoken")
    good = tmp_path / "good.txt"
    good.write_text("hello\n", encoding="utf-8")
    bad = tmp_path / "bad.txt"
    bad.write_bytes(b"a\xff\n")
    result = subprocess.run([sys.executable, "-I", str(ROOT / "keyline" / "measure.py"), str(good), str(bad)],
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 2, result.stderr
    assert "Traceback" not in result.stderr and "error" in result.stderr and "bad.txt" in result.stderr
    assert "good.txt" in result.stdout and "change:" not in result.stdout
    empty = tmp_path / "empty"
    empty.mkdir()
    result = subprocess.run([sys.executable, "-I", str(ROOT / "keyline" / "measure.py"), str(empty)],
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 2, result.stderr
    assert "Traceback" not in result.stderr and "error" in result.stderr and "empty" in result.stderr


@pytest.mark.skipif(os.name == "nt", reason="symlinks need a privilege on Windows")
def test_a_symlinked_folder_is_reported(tmp_path):
    # os.walk does not follow a symlinked sub-folder, so its files were left out with no
    # "skip" line, while a symlinked file was counted.
    pytest.importorskip("tiktoken")
    real = tmp_path / "real"
    real.mkdir()
    (real / "x.txt").write_text("hi\n", encoding="utf-8")
    walk = tmp_path / "walk"
    walk.mkdir()
    (walk / "y.txt").write_text("hi\n", encoding="utf-8")
    try:
        (walk / "linked").symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("cannot create symlinks here")
    result = subprocess.run([sys.executable, "-I", str(ROOT / "keyline" / "measure.py"), str(walk)],
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert "skip (symlinked folder)" in result.stderr and "linked" in result.stderr
    assert "y.txt" in result.stdout and "x.txt" not in result.stdout
