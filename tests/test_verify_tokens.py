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
