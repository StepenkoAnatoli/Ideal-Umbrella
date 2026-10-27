import pytest

from conftest import ROOT, load_module, python_314_pathlib, refuse_looks_inside


@pytest.fixture
def lint_validate():
    return load_module("lint_validate", "scripts/lint_validate.py")


def test_usage_without_arguments(lint_validate, capsys):
    assert lint_validate.main([]) == 2
    assert "Usage:" in capsys.readouterr().err


def test_missing_corpus_folder_is_an_error(lint_validate, tmp_path, capsys):
    old = ROOT / "keyline" / "keyline_lint.py"
    assert lint_validate.main([str(old), str(tmp_path / "missing")]) == 1
    assert "not a folder" in capsys.readouterr().err


def test_runs_against_a_given_corpus_folder(lint_validate, tmp_path, capsys):
    pytest.importorskip("tiktoken")
    (tmp_path / "notes.md").write_text("The worktree was rerun with mgmt approval.\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "skip.md").write_text("ignored\n", encoding="utf-8")
    old = ROOT / "keyline" / "keyline_lint.py"
    assert lint_validate.main([str(old), str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "corpus: 1 files" in out
    assert "old rule: " in out


@pytest.mark.parametrize("pathlib_kind", ["3.13", "3.14"])
@pytest.mark.parametrize("which", ["file", "folder"])
def test_a_path_that_cannot_be_looked_at_says_cannot_read(lint_validate, tmp_path, capsys, monkeypatch, which,
                                                          pathlib_kind):
    # Review 24, F1 other hits: on 3.13 is_file() raised PermissionError (a traceback); on 3.14
    # it says False, and a file in a folder that cannot be searched was "not a file".
    blocked = tmp_path / "blocked"
    (blocked / "corpus").mkdir(parents=True)
    old = blocked / "old.py" if which == "file" else ROOT / "keyline" / "keyline_lint.py"
    if which == "file":
        old.write_text("", encoding="utf-8")
    folder = blocked / "corpus" if which == "folder" else tmp_path
    if pathlib_kind == "3.14":
        python_314_pathlib(monkeypatch)
    refuse_looks_inside(blocked, monkeypatch)
    assert lint_validate.main([str(old), str(folder)]) == 1
    err = capsys.readouterr().err
    assert f"cannot read {old if which == 'file' else folder}" in err, err
    assert "not a file" not in err and "not a folder" not in err


def test_a_corpus_path_through_a_file_is_not_a_folder(lint_validate, tmp_path, capsys):
    # Review 26, C3: nothing failed when NotADirectoryError ("a_file/x") read as "cannot read".
    (tmp_path / "a_file").write_text("", encoding="utf-8")
    old = ROOT / "keyline" / "keyline_lint.py"
    assert lint_validate.main([str(old), str(tmp_path / "a_file" / "x")]) == 1
    err = capsys.readouterr().err
    assert "is not a folder" in err and "cannot read" not in err, err
