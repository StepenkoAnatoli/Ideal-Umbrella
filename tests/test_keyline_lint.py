import sys

import pytest

from conftest import load_module


def test_missing_tiktoken_gives_an_install_hint(tmp_path, monkeypatch):
    # A fresh clone has no keyline/cache/ (gitignored), so the first lint builds it and needs
    # tiktoken. Without it the hook used to show a ModuleNotFoundError traceback on every write.
    keyline_lint = load_module("keyline_lint", "keyline/keyline_lint.py")
    monkeypatch.setattr(keyline_lint, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(keyline_lint, "WORDS_CACHE", tmp_path / "cache" / "words.txt")
    monkeypatch.setitem(sys.modules, "tiktoken", None)  # import tiktoken -> ImportError
    with pytest.raises(SystemExit) as exc:
        keyline_lint.load_words()
    assert "pip install -r keyline/requirements.txt" in str(exc.value)
    assert not (tmp_path / "cache").exists()


def test_non_utf8_note_is_a_read_error(tmp_path):
    keyline_lint = load_module("keyline_lint", "keyline/keyline_lint.py")
    note = tmp_path / "latin.txt"
    note.write_bytes(b"caf\xe9\n")
    with pytest.raises(OSError, match="not UTF-8"):
        keyline_lint.lint_file(note, words=set())
