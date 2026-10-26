import os
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
    assert len(findings) == 1 and "mgmt" in findings[0][1]


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


def test_a_one_token_word_is_never_an_abbreviation():
    # "must" is four letters with one vowel, so a word list without it sent the word to tiktoken,
    # and a count of one was reported as "is 1 tokens".
    pytest.importorskip("tiktoken")
    keyline_lint = load_module("keyline_lint", "keyline/keyline_lint.py")
    assert list(keyline_lint.lint_text("this must work\n", {"this", "work"}, set())) == []


def test_a_truncated_word_cache_is_rebuilt(tmp_path, monkeypatch):
    # A cache cut short (disk full, a killed build) was trusted, and every common word missing
    # from it became a finding.
    keyline_lint = load_module("keyline_lint", "keyline/keyline_lint.py")
    cache = tmp_path / "cache" / "words.txt"
    cache.parent.mkdir()
    monkeypatch.setattr(keyline_lint, "CACHE_DIR", cache.parent)
    monkeypatch.setattr(keyline_lint, "WORDS_CACHE", cache)
    rebuilt = {"the", "and", "must"}
    monkeypatch.setattr(keyline_lint, "build_cache", lambda: rebuilt)
    cache.write_text("# built by keyline_lint.py with tiktoken 0; 5000 words\nthe\nand\n", encoding="utf-8")
    assert keyline_lint.load_words() == rebuilt
    cache.write_text("", encoding="utf-8")
    assert keyline_lint.load_words() == rebuilt
    cache.write_text("# built by keyline_lint.py with tiktoken 0; 2 words\nthe\nand\n", encoding="utf-8")
    assert keyline_lint.load_words() == {"the", "and"}


def test_a_cache_build_that_fails_part_way_leaves_no_cache(tmp_path, monkeypatch):
    import types
    keyline_lint = load_module("keyline_lint", "keyline/keyline_lint.py")
    monkeypatch.setattr(keyline_lint, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(keyline_lint, "WORDS_CACHE", tmp_path / "cache" / "words.txt")
    tokens = [b" the", b" and", b"x"]

    class Enc:
        n_vocab = 3

        def decode_single_token_bytes(self, i):
            return tokens[i]

    fake = types.SimpleNamespace(get_encoding=lambda name: Enc(), __version__="0")
    monkeypatch.setattr(keyline_lint, "_tiktoken", lambda: fake)

    def boom(src, dst):
        raise OSError(28, "simulated disk full", dst)

    monkeypatch.setattr(keyline_lint.os, "replace", boom)
    with pytest.raises(OSError, match="simulated"):
        keyline_lint.build_cache()
    assert list((tmp_path / "cache").iterdir()) == []
    monkeypatch.undo()
    monkeypatch.setattr(keyline_lint, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(keyline_lint, "WORDS_CACHE", tmp_path / "cache" / "words.txt")
    monkeypatch.setattr(keyline_lint, "_tiktoken", lambda: fake)
    assert keyline_lint.build_cache() == {"the", "and"}
    assert keyline_lint.load_words() == {"the", "and"}
    assert "; 2 words" in (tmp_path / "cache" / "words.txt").read_text(encoding="utf-8").splitlines()[0]


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_a_rebuilt_cache_gets_the_umask_mode(tmp_path, monkeypatch, umask_022):
    # mkstemp creates the temp file 0600 and the rename keeps it, so a cache built by one user
    # was unreadable to another on a shared checkout. The umask is pinned: under 077 the
    # host's plain-write mode is 0600 too, and the old assertion held without the fix.
    import types
    keyline_lint = load_module("keyline_lint", "keyline/keyline_lint.py")
    monkeypatch.setattr(keyline_lint, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(keyline_lint, "WORDS_CACHE", tmp_path / "cache" / "words.txt")

    class Enc:
        n_vocab = 2

        def decode_single_token_bytes(self, i):
            return [b" the", b" and"][i]

    fake = types.SimpleNamespace(get_encoding=lambda name: Enc(), __version__="0")
    monkeypatch.setattr(keyline_lint, "_tiktoken", lambda: fake)
    keyline_lint.build_cache()
    assert (tmp_path / "cache" / "words.txt").stat().st_mode & 0o777 == 0o644


def test_building_the_cache_never_touches_the_process_umask(tmp_path, monkeypatch):
    # The mode came from reading the umask, and os.umask can only read it by setting it: in
    # a threaded host, files another thread created in that window were made 0666.
    import types
    keyline_lint = load_module("keyline_lint", "keyline/keyline_lint.py")
    monkeypatch.setattr(keyline_lint, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(keyline_lint, "WORDS_CACHE", tmp_path / "cache" / "words.txt")

    class Enc:
        n_vocab = 1

        def decode_single_token_bytes(self, i):
            return b" the"

    fake = types.SimpleNamespace(get_encoding=lambda name: Enc(), __version__="0")
    monkeypatch.setattr(keyline_lint, "_tiktoken", lambda: fake)
    monkeypatch.setattr(os, "umask", lambda *a: pytest.fail("os.umask was called"))
    assert keyline_lint.build_cache() == {"the"}


def test_a_tiktoken_that_cannot_load_its_data_is_not_called_missing(monkeypatch):
    # token_count() returns None for any failure, and the message hard-coded one cause: with
    # tiktoken installed but o200k_base not loadable (offline, a proxy, a corrupt cache) the
    # lint told the user to install a package they had.
    import types
    keyline_lint = load_module("keyline_lint", "keyline/keyline_lint.py")

    def broken(name):
        raise ConnectionError("download of o200k_base failed")

    fake = types.SimpleNamespace(get_encoding=broken, __version__="0")
    monkeypatch.setattr(keyline_lint, "_tiktoken", lambda: fake)
    findings = list(keyline_lint.lint_text("the mgmt layer\n", {"the", "layer"}, set()))
    assert len(findings) == 1
    assert "not counted" in findings[0][1]
    assert "download of o200k_base failed" in findings[0][1]
    assert "missing" not in findings[0][1]


def test_missing_tiktoken_says_the_word_was_not_counted(monkeypatch):
    # With tiktoken missing, a word absent from the list was reported as "not one token",
    # which the lint had not checked.
    keyline_lint = load_module("keyline_lint", "keyline/keyline_lint.py")
    monkeypatch.setitem(sys.modules, "tiktoken", None)
    findings = list(keyline_lint.lint_text("the mgmt layer\n", {"the", "layer"}, set()))
    assert len(findings) == 1
    assert "not counted" in findings[0][1] and "tiktoken" in findings[0][1]
    assert "not one token" not in findings[0][1]
