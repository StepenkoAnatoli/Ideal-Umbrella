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
