import os
import subprocess
import sys

import pytest

from conftest import ROOT, link_or_skip, load_module, not_found_at, python_314_pathlib, refuse_listing, refuse_looks_inside


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
    assert "Traceback" not in result.stderr
    assert f"skip (symlink to a missing target): {link}" in result.stderr, result.stderr   # Review 28, L1
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


@pytest.mark.parametrize("which", ["top", "sub"])
def test_a_folder_that_cannot_be_listed_is_named_not_passed_over(tmp_path, capsys, monkeypatch, which):
    # Review 26, C2: os.walk without onerror passed over a folder it could not list, so its
    # files were missing from the table without a word (an empty table for the top folder).
    pytest.importorskip("tiktoken")
    measure = load_module("measure", "keyline/measure.py")
    (tmp_path / "good.txt").write_text("hello\n", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "hidden.txt").write_text("hello\n", encoding="utf-8")
    refused = tmp_path if which == "top" else sub
    refuse_listing(refused, monkeypatch)
    # Review 8, low 16: a folder argument that produced no row exits 1.
    assert measure.main([str(tmp_path)]) == (1 if which == "top" else 0)
    captured = capsys.readouterr()
    assert f"skip (cannot read: Permission denied): {refused}" in captured.err, captured
    assert ("good.txt" in captured.out) == (which == "sub"), captured


def test_an_argument_through_a_file_is_no_such_file(tmp_path, capsys):
    # Review 26, C3: nothing failed when NotADirectoryError ("a_file/x") read as "cannot read".
    pytest.importorskip("tiktoken")
    measure = load_module("measure", "keyline/measure.py")
    (tmp_path / "a_file").write_text("hello\n", encoding="utf-8")
    assert measure.main([str(tmp_path / "a_file" / "x")]) == 2
    err = capsys.readouterr().err
    assert "no such file or folder" in err and "cannot read" not in err, err


@pytest.mark.parametrize("how", ["gone", "too long"])
def test_a_walked_file_that_is_not_found_says_cannot_read(tmp_path, capsys, monkeypatch, how):
    # Review 26, C3: nothing failed when a walked file removed before its stat was called a
    # "symlink to a missing target". Review 28, L1: it was then "no longer there", which is
    # not true on Windows for a path past MAX_PATH, which raises the same "not found".
    pytest.importorskip("tiktoken")
    measure = load_module("measure", "keyline/measure.py")
    (tmp_path / "good.txt").write_text("hello\n", encoding="utf-8")
    missing = tmp_path / "missing.txt"
    if how == "gone":
        real_walk = os.walk

        def walk(top, *args, **kwargs):
            for root, dirs, names in real_walk(top, *args, **kwargs):
                yield root, dirs, names + ["missing.txt"]
        monkeypatch.setattr(measure.os, "walk", walk)
    else:
        missing.write_text("hello\n", encoding="utf-8")
        not_found_at(missing, monkeypatch)
    assert measure.main([str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert "skip (cannot read: " in captured.err and f"): {missing}" in captured.err, captured
    assert "no longer there" not in captured.err and "symlink" not in captured.err, captured
    assert "good.txt" in captured.out and "missing.txt" not in captured.out


def test_a_folder_that_is_not_found_during_the_walk_says_cannot_read(tmp_path, capsys, monkeypatch):
    # Review 28, L1: pass 27 called a folder whose listing said "not found" "no longer there";
    # on Windows a path past MAX_PATH says the same while it is there.
    pytest.importorskip("tiktoken")
    measure = load_module("measure", "keyline/measure.py")
    (tmp_path / "good.txt").write_text("hello\n", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "hidden.txt").write_text("hello\n", encoding="utf-8")
    not_found_at(sub, monkeypatch)
    assert measure.main([str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert f"skip (cannot read: No such file or directory): {sub}" in captured.err, captured
    assert "good.txt" in captured.out and "hidden.txt" not in captured.out


def test_hidden_cache_and_dependency_folders_are_not_walked(tmp_path, capsys):
    # Review 28, L2: nothing failed when a hidden folder, or one in SKIP_DIRS, was walked.
    pytest.importorskip("tiktoken")
    measure = load_module("measure", "keyline/measure.py")
    for folder in (".git", "cache", "__pycache__", "node_modules"):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "x.txt").write_text("hello\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "y.txt").write_text("hello\n", encoding="utf-8")
    assert measure.main([str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert "y.txt" in captured.out and "x.txt" not in captured.out, captured
    assert captured.err == "", captured


@pytest.mark.parametrize("target", ["through a file", "locked"])
def test_a_link_is_a_missing_target_only_when_it_leads_nowhere(tmp_path, capsys, monkeypatch, target):
    # Review 29: a link whose target goes through a file (NotADirectoryError) was "cannot read:
    # Not a directory" (L1); nothing failed when a link into a folder that cannot be searched
    # was called a missing target (L2).
    pytest.importorskip("tiktoken")
    measure = load_module("measure", "keyline/measure.py")
    (tmp_path / "good.txt").write_text("hello\n", encoding="utf-8")
    link = tmp_path / "b.txt"
    if target == "locked":
        locked = tmp_path / "locked"
        locked.mkdir()
        (locked / "x.txt").write_text("hello\n", encoding="utf-8")
        link_or_skip(link, locked / "x.txt")
        refuse_looks_inside(locked, monkeypatch)
        want = f"skip (cannot read: Permission denied): {link}"
    else:
        (tmp_path / "afile").write_text("x", encoding="utf-8")
        link_or_skip(link, tmp_path / "afile" / "b.txt")
        want = f"skip (symlink to a missing target): {link}"
    assert measure.main([str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert want in captured.err, captured
    assert "good.txt" in captured.out


def test_links_are_followed_except_a_walked_link_to_a_folder(tmp_path, capsys):
    # Review 30, L1: nothing failed when an argument that is a link, or a walked link to a file,
    # stopped being followed, or when a walked link to a folder was followed (its files would be
    # counted twice).
    pytest.importorskip("tiktoken")
    measure = load_module("measure", "keyline/measure.py")
    real = tmp_path / "real"
    real.mkdir()
    (real / "a.txt").write_text("hello\n", encoding="utf-8")
    (tmp_path / "f.txt").write_text("hello\n", encoding="utf-8")
    link_or_skip(real / "linkedfile.txt", tmp_path / "f.txt")
    other = tmp_path / "other"
    other.mkdir()
    (other / "o.txt").write_text("hello\n", encoding="utf-8")
    link_or_skip(real / "linkeddir", other, target_is_directory=True)
    link_or_skip(tmp_path / "argfile.txt", tmp_path / "f.txt")
    link_or_skip(tmp_path / "argdir", real, target_is_directory=True)
    assert measure.main([str(tmp_path / "argdir"), str(tmp_path / "argfile.txt")]) == 0
    captured = capsys.readouterr()
    assert captured.err == "", captured
    assert "a.txt" in captured.out and "linkedfile.txt" in captured.out and "argfile.txt" in captured.out, captured
    assert "o.txt" not in captured.out, captured


# ---- review 8 (main bcc441c) ----

def test_a_file_that_fails_to_read_is_skipped_not_a_traceback(tmp_path, capsys, monkeypatch):
    # Review 8, low 8: the per-file OSError handler had no test that needed it as root.
    pytest.importorskip("tiktoken")
    measure = load_module("measure", "keyline/measure.py")
    (tmp_path / "good.txt").write_text("hello\n", encoding="utf-8")
    bad = tmp_path / "bad.txt"
    bad.write_text("hello\n", encoding="utf-8")
    real_read_bytes = measure.Path.read_bytes

    def read_bytes(self):
        if self.name == "bad.txt":
            raise PermissionError(13, "Permission denied", str(self))
        return real_read_bytes(self)
    monkeypatch.setattr(measure.Path, "read_bytes", read_bytes)
    assert measure.main([str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert f"skip (cannot read: Permission denied): {bad}" in captured.err, captured
    assert "good.txt" in captured.out and "bad.txt" not in captured.out


def test_a_named_argument_that_produced_no_row_exits_1(tmp_path, capsys):
    # Review 8, low 16: a skipped named file, or an empty folder, still exited 0.
    pytest.importorskip("tiktoken")
    measure = load_module("measure", "keyline/measure.py")
    good = tmp_path / "good.txt"
    good.write_text("hello\n", encoding="utf-8")
    latin = tmp_path / "latin.txt"
    latin.write_bytes(b"caf\xe9\n")
    empty = tmp_path / "empty"
    empty.mkdir()
    for bad in (latin, empty):
        assert measure.main([str(good), str(bad)]) == 1
        err = capsys.readouterr().err
        assert f"nothing counted for {bad}" in err, err
    assert measure.main([str(good)]) == 0


def test_the_change_line_needs_two_files_that_each_produced_a_row(tmp_path, capsys):
    # Review 8, low 38: "measure.py d/ new.txt" printed the change line between d/a.txt and
    # d/b.txt when new.txt was skipped.
    pytest.importorskip("tiktoken")
    measure = load_module("measure", "keyline/measure.py")
    d = tmp_path / "d"
    d.mkdir()
    (d / "a.txt").write_text("hi\n", encoding="utf-8")
    (d / "b.txt").write_text("hello there, a longer line\n", encoding="utf-8")
    new = tmp_path / "new.txt"
    new.write_bytes(b"\xff\n")
    empty = tmp_path / "empty"
    empty.mkdir()
    for argv in ([d, new], [d, empty], [d / "a.txt", new]):
        measure.main([str(a) for a in argv])
        assert "change:" not in capsys.readouterr().out
    assert measure.main([str(d / "a.txt"), str(d / "b.txt")]) == 0
    assert "change:" in capsys.readouterr().out


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no named pipes here")
def test_a_named_pipe_argument_is_not_called_missing(tmp_path, capsys):
    # Review 8, low 39: a FIFO argument printed "error: no such file or folder".
    pytest.importorskip("tiktoken")
    measure = load_module("measure", "keyline/measure.py")
    pipe = tmp_path / "pipe.txt"
    os.mkfifo(pipe)
    assert measure.main([str(pipe)]) == 2
    err = capsys.readouterr().err
    assert f"not a regular file or folder: {pipe}" in err and "no such file" not in err, err


def test_a_hidden_file_in_a_walked_folder_is_not_counted(tmp_path, capsys):
    # Review 8, low 11 other hit: hidden folders were skipped but .DS_Store was read.
    pytest.importorskip("tiktoken")
    measure = load_module("measure", "keyline/measure.py")
    (tmp_path / "good.txt").write_text("hello\n", encoding="utf-8")
    (tmp_path / ".DS_Store").write_bytes(b"\xff\x00")
    assert measure.main([str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert ".DS_Store" not in captured.out + captured.err, captured
    assert measure.main([str(tmp_path / ".DS_Store")]) == 1      # a named hidden file is still read


def test_the_docstring_says_a_walked_symlinked_folder_is_not_followed():
    # Review 8, low 17: a test pins this on purpose; the docstring did not say so.
    doc = (ROOT / "keyline" / "measure.py").read_text(encoding="utf-8").split('"""')[1]
    assert "symlinked sub-folder" in doc and "not followed" in doc


def test_an_encoding_that_cannot_load_is_one_line_not_a_traceback(tmp_path, capsys, monkeypatch):
    # Review 8, low 19 other hit: tiktoken.get_encoding was unguarded here too.
    pytest.importorskip("tiktoken")
    measure = load_module("measure", "keyline/measure.py")

    def broken(name):
        raise ValueError("hash mismatch for o200k_base")
    monkeypatch.setattr(measure.tiktoken, "get_encoding", broken)
    (tmp_path / "a.txt").write_text("hi\n", encoding="utf-8")
    assert measure.main([str(tmp_path / "a.txt")]) == 2
    err = capsys.readouterr().err
    assert err == "error: tiktoken could not load o200k_base: hash mismatch for o200k_base\n", err
