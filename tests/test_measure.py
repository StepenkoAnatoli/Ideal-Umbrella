import os
import subprocess
import sys

import pytest

from conftest import ROOT, load_module, python_314_pathlib, refuse_looks_inside


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


@pytest.mark.parametrize("pathlib_kind", ["3.13", "3.14"])
@pytest.mark.parametrize("walked", [False, True], ids=["argument", "walked"])
def test_a_file_in_a_folder_that_cannot_be_searched_says_cannot_read(tmp_path, capsys, monkeypatch, pathlib_kind,
                                                                    walked):
    # Review 24, F1 other hits: on Python 3.14 is_file() and is_dir() say False for a file in a
    # folder that cannot be searched, so measure said "no such file or folder" for an argument
    # and "not a regular file" for a walked file; this runs as root too, unlike the tests above.
    pytest.importorskip("tiktoken")
    measure = load_module("measure", "keyline/measure.py")
    (tmp_path / "good.txt").write_text("hello\n", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "hidden.txt").write_text("hello\n", encoding="utf-8")
    if pathlib_kind == "3.14":
        python_314_pathlib(monkeypatch)
    refuse_looks_inside(sub, monkeypatch)
    if walked:
        assert measure.main([str(tmp_path)]) == 0
        captured = capsys.readouterr()
        assert "skip (cannot read: Permission denied)" in captured.err and "hidden.txt" in captured.err, captured
        assert "good.txt" in captured.out
    else:
        assert measure.main([str(sub / "hidden.txt")]) == 2
        err = capsys.readouterr().err
        assert "cannot read" in err and "hidden.txt" in err and "no such file" not in err, err
