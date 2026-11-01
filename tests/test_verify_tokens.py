import pytest

from conftest import ROOT, load_module, python_314_pathlib, refuse_looks_inside


def test_fixture_path_points_at_keyline_tests():
    module = load_module("verify_tokens", "config/verify-tokens.py")
    assert module.FIXTURES == ROOT / "keyline" / "tests"
    for name in module.DEFAULT_FIXTURES:
        assert (module.FIXTURES / name).is_file(), name


def test_no_retired_model_is_baked_in():
    source = (ROOT / "config" / "verify-tokens.py").read_text(encoding="utf-8")
    assert "claude-3-5-sonnet" not in source
    assert "ANTHROPIC_MODEL" in source


def test_unreadable_file_is_reported_not_raised(tmp_path, capsys, monkeypatch):
    module = load_module("verify_tokens", "config/verify-tokens.py")

    class Client:
        def __init__(self, **kw):
            pass

    monkeypatch.setattr(module, "anthropic", type("A", (), {"Anthropic": Client}))
    monkeypatch.setattr(module, "count_anthropic", lambda client, text, model: 1)
    monkeypatch.setattr(module, "count_tiktoken", lambda text: (1, 1))   # without tiktoken too
    bad = tmp_path / "latin.txt"
    bad.write_bytes(b"caf\xe9\n")
    folder = tmp_path / "folder"
    folder.mkdir()
    good = tmp_path / "good.txt"
    good.write_text("fine\n", encoding="utf-8")
    assert module.main(["--api-key", "k", "--model", "m", str(bad), str(folder), str(good)]) == 0
    out = capsys.readouterr()
    assert "Traceback" not in out.err
    assert out.err.count("Error reading") == 2
    assert "good.txt" in out.out


def _client(module, monkeypatch):
    class Client:
        def __init__(self, **kw):
            pass

    monkeypatch.setattr(module, "anthropic", type("A", (), {"Anthropic": Client}))


def test_tiktoken_failure_is_one_error_and_exit_1(tmp_path, capsys, monkeypatch):
    # A tiktoken download failure was reported as "Error reading" for every file, exit 0.
    module = load_module("verify_tokens", "config/verify-tokens.py")
    _client(module, monkeypatch)
    monkeypatch.setattr(module, "count_anthropic", lambda client, text, model: 1)

    def fail(text):
        raise RuntimeError("download failed")

    monkeypatch.setattr(module, "count_tiktoken", fail)
    files = []
    for name in ("a.txt", "b.txt"):
        (tmp_path / name).write_text("fine\n", encoding="utf-8")
        files.append(str(tmp_path / name))
    assert module.main(["--api-key", "k", "--model", "m", *files]) == 1
    err = capsys.readouterr().err
    assert err.count("download failed") == 1 and "Error reading" not in err and "Traceback" not in err


def test_no_api_count_at_all_is_exit_1(tmp_path, capsys, monkeypatch):
    # Every file ERROR on the API side printed no average and exited 0.
    module = load_module("verify_tokens", "config/verify-tokens.py")
    _client(module, monkeypatch)

    def fail(client, text, model):
        raise RuntimeError("boom")

    monkeypatch.setattr(module, "count_anthropic", fail)
    monkeypatch.setattr(module, "count_tiktoken", lambda text: (1, 1))   # without tiktoken too
    good = tmp_path / "good.txt"
    good.write_text("fine\n", encoding="utf-8")
    assert module.main(["--api-key", "k", "--model", "m", str(good)]) == 1
    out = capsys.readouterr()
    assert "ERROR" in out.out and "no file was counted" in out.err


def test_the_offset_of_a_byte_that_is_not_utf8_counts_a_bom(tmp_path, capsys, monkeypatch):
    # Review 22, I1: utf-8-sig counts from after a BOM, so the offset was 3 bytes too low.
    module = load_module("verify_tokens", "config/verify-tokens.py")
    _client(module, monkeypatch)
    for bom in (b"", b"\xef\xbb\xbf"):
        bad = tmp_path / "latin.txt"
        bad.write_bytes(bom + b"caf\xe9\n")
        module.main(["--api-key", "k", "--model", "m", str(bad)])
        assert f"not UTF-8 (invalid continuation byte at byte {len(bom) + 3})" in capsys.readouterr().err


def test_a_missing_file_is_a_warning_and_the_rest_are_counted(tmp_path, capsys, monkeypatch):
    # Review 32, L3 (mutant V265): no test had a missing file, so its warning could go (the run
    # went silent) or turn into "Error reading" with the FileNotFoundError branch deleted.
    module = load_module("verify_tokens", "config/verify-tokens.py")
    _client(module, monkeypatch)
    monkeypatch.setattr(module, "count_anthropic", lambda client, text, model: 1)
    monkeypatch.setattr(module, "count_tiktoken", lambda text: (1, 1))
    missing = tmp_path / "missing.txt"
    good = tmp_path / "good.txt"
    good.write_text("fine\n", encoding="utf-8")
    assert module.main(["--api-key", "k", "--model", "m", str(missing), str(good)]) == 0
    out = capsys.readouterr()
    assert out.err == f"Warning: {missing} not found, skipping\n", out.err
    assert "good.txt" in out.out and "missing.txt" not in out.out


@pytest.mark.parametrize("pathlib_kind", ["3.13", "3.14"])
def test_a_file_that_cannot_be_looked_at_is_not_called_missing(tmp_path, capsys, monkeypatch, pathlib_kind):
    # Review 24, F1 other hits: on 3.14 exists() says False for a file in a folder that cannot
    # be searched, which was reported as "not found".
    module = load_module("verify_tokens", "config/verify-tokens.py")
    _client(module, monkeypatch)
    monkeypatch.setattr(module, "count_anthropic", lambda client, text, model: 1)
    monkeypatch.setattr(module, "count_tiktoken", lambda text: (1, 1))   # without tiktoken too
    hidden = tmp_path / "blocked" / "hidden.txt"
    hidden.parent.mkdir()
    hidden.write_text("hello\n", encoding="utf-8")
    good = tmp_path / "good.txt"
    good.write_text("fine\n", encoding="utf-8")
    if pathlib_kind == "3.14":
        python_314_pathlib(monkeypatch)
    refuse_looks_inside(hidden.parent, monkeypatch)
    module.main(["--api-key", "k", "--model", "m", str(hidden), str(good)])
    out = capsys.readouterr()
    assert "Traceback" not in out.err and "not found" not in out.err, out.err
    assert "Error reading" in out.err and "hidden.txt" in out.err and "good.txt" in out.out


def test_an_api_count_of_0_is_not_a_division_by_zero(tmp_path, capsys, monkeypatch):
    # Review 9, I-2: the ratio divided by the API count, so 0 raised ZeroDivisionError.
    module = load_module("verify_tokens", "config/verify-tokens.py")
    _client(module, monkeypatch)
    monkeypatch.setattr(module, "count_anthropic", lambda client, text, model: 0)
    monkeypatch.setattr(module, "count_tiktoken", lambda text: (1, 1))
    good = tmp_path / "good.txt"
    good.write_text("fine\n", encoding="utf-8")
    assert module.main(["--api-key", "k", "--model", "m", str(good)]) == 1
    out = capsys.readouterr()
    assert "n/a" in out.out and "no file was counted" in out.err, out


def test_a_tiktoken_count_of_0_is_not_a_division_by_zero(tmp_path, capsys, monkeypatch):
    # Review 9, I-2 other hit: "multiply by 1/average" divided by an average ratio of 0 (empty files).
    module = load_module("verify_tokens", "config/verify-tokens.py")
    _client(module, monkeypatch)
    monkeypatch.setattr(module, "count_anthropic", lambda client, text, model: 3)
    monkeypatch.setattr(module, "count_tiktoken", lambda text: (0, 0))
    good = tmp_path / "good.txt"
    good.write_text("fine\n", encoding="utf-8")
    assert module.main(["--api-key", "k", "--model", "m", str(good)]) == 0
    out = capsys.readouterr()
    assert "AVERAGE" in out.out and "Traceback" not in out.err, out
