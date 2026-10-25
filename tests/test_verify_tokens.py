from conftest import ROOT, load_module


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
    good = tmp_path / "good.txt"
    good.write_text("fine\n", encoding="utf-8")
    assert module.main(["--api-key", "k", "--model", "m", str(good)]) == 1
    out = capsys.readouterr()
    assert "ERROR" in out.out and "no file was counted" in out.err
