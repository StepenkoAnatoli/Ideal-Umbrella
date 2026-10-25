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
    with pytest.raises(keyline_lint.TiktokenMissing) as exc:
        keyline_lint.load_words()
    assert "pip install -r keyline/requirements.txt" in str(exc.value)
    assert not (tmp_path / "cache").exists()


def test_non_utf8_note_is_a_read_error(tmp_path):
    keyline_lint = load_module("keyline_lint", "keyline/keyline_lint.py")
    note = tmp_path / "latin.txt"
    note.write_bytes(b"caf\xe9\n")
    with pytest.raises(OSError, match="not UTF-8"):
        keyline_lint.lint_file(note, words=set())


def test_missing_tiktoken_with_a_cache_does_not_stop_the_lint(tmp_path, monkeypatch):
    # With the word cache present, tiktoken is only needed to size an abbreviation. The
    # install hint used to escape token_count()'s `except Exception` (SystemExit is not an
    # Exception) and stop the whole lint, and the hook with it.
    keyline_lint = load_module("keyline_lint", "keyline/keyline_lint.py")
    monkeypatch.setitem(sys.modules, "tiktoken", None)
    assert keyline_lint.token_count("mgmt") is None
    findings = list(keyline_lint.lint_text("the mgmt layer\n", {"the", "layer"}, set()))
    assert len(findings) == 1 and "not one token" in findings[0][1]


def test_missing_tiktoken_without_a_cache_is_one_line_from_main(tmp_path, monkeypatch, capsys):
    keyline_lint = load_module("keyline_lint", "keyline/keyline_lint.py")
    monkeypatch.setattr(keyline_lint, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(keyline_lint, "WORDS_CACHE", tmp_path / "cache" / "words.txt")
    monkeypatch.setitem(sys.modules, "tiktoken", None)
    note = tmp_path / "note.txt"
    note.write_text("fine\n", encoding="utf-8")
    assert keyline_lint.main([str(note)]) == 2
    err = capsys.readouterr().err
    assert "pip install -r keyline/requirements.txt" in err and "Traceback" not in err


def test_non_utf8_allow_file_is_a_read_error(tmp_path):
    keyline_lint = load_module("keyline_lint", "keyline/keyline_lint.py")
    (tmp_path / keyline_lint.ALLOW_NAME).write_bytes(b"caf\xe9\n")
    note = tmp_path / "note.txt"
    note.write_text("fine\n", encoding="utf-8")
    with pytest.raises(OSError, match="not UTF-8"):
        keyline_lint.lint_file(note, words=set())


def test_cache_folder_in_the_way_is_one_line_from_main(tmp_path, monkeypatch, capsys):
    # load_words() runs outside the OSError handler that lint_file() has.
    keyline_lint = load_module("keyline_lint", "keyline/keyline_lint.py")
    monkeypatch.setattr(keyline_lint, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(keyline_lint, "WORDS_CACHE", tmp_path / "cache" / "words.txt")
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "words.txt").mkdir()
    note = tmp_path / "note.txt"
    note.write_text("fine\n", encoding="utf-8")
    assert keyline_lint.main([str(note)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("error:") and "Traceback" not in err
