import pytest

from conftest import ROOT, load_module


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
