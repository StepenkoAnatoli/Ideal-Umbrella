import json

import pytest

from conftest import load_module


@pytest.fixture
def plugin_cost():
    return load_module("plugin_cost", "scripts/plugin_cost.py")


def make_plugin(root, name, skills=(), commands=(), mcp=None, hooks=False):
    plugin = root / name
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": name}), encoding="utf-8")
    for skill in skills:
        folder = plugin / "skills" / skill
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(f"---\nname: {skill}\ndescription: Does {skill} things\n---\n# body\n",
                                         encoding="utf-8")
    for command in commands:
        (plugin / "commands").mkdir(exist_ok=True)
        (plugin / "commands" / f"{command}.md").write_text("---\ndescription: a command\n---\n", encoding="utf-8")
    if mcp is not None:
        (plugin / ".mcp.json").write_text(json.dumps({"mcpServers": mcp}), encoding="utf-8")
    if hooks:
        (plugin / "hooks").mkdir()
        (plugin / "hooks" / "hooks.json").write_text("{}", encoding="utf-8")
    return plugin


def test_usage_without_arguments(plugin_cost, capsys):
    assert plugin_cost.main([]) == 2
    assert "Usage:" in capsys.readouterr().err


def test_missing_app_folder_is_an_error(plugin_cost, tmp_path, capsys):
    assert plugin_cost.main([str(tmp_path / "out.json"), str(tmp_path / "missing")]) == 1
    assert "not a folder" in capsys.readouterr().err


def test_default_app_dir_honours_env(plugin_cost, tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_APP_DIR", str(tmp_path))
    assert plugin_cost.default_app_dir() == tmp_path


def test_counts_skills_commands_mcp_and_hooks(plugin_cost, tmp_path, capsys):
    pytest.importorskip("tiktoken")
    app = tmp_path / "Claude"
    make_plugin(app, "alpha", skills=("one", "two"), commands=("go",), mcp={"s": {}, "t": {}}, hooks=True)
    make_plugin(app, "beta")
    out = tmp_path / "out.json"
    assert plugin_cost.main([str(out), str(app)]) == 0
    rows = {r[0]: r for r in json.loads(out.read_text(encoding="utf-8"))}
    assert set(rows) == {"alpha", "beta"}
    name, skills, tokens, mcp, hooks, agents, names = rows["alpha"]
    assert (skills, mcp, hooks, agents, names) == (3, 2, True, 0, ["go", "one", "two"])
    assert tokens > 0
    assert rows["beta"][1:3] == [0, 0]
    assert "2 plugins, 3 skills/commands" in capsys.readouterr().out


def test_a_description_with_a_special_token_or_a_bom_is_counted(plugin_cost, tmp_path, capsys):
    # tiktoken refuses "<|endoftext|>" unless told otherwise, so one plugin description holding
    # it stopped the whole run; and a SKILL.md saved with a BOM had no front matter to the
    # regex, so its description was counted as empty.
    pytest.importorskip("tiktoken")
    plugin = make_plugin(tmp_path, "odd", skills=["special", "bom"])
    (plugin / "skills" / "special" / "SKILL.md").write_text(
        "---\nname: special\ndescription: Stops at <|endoftext|> markers\n---\n", encoding="utf-8")
    (plugin / "skills" / "bom" / "SKILL.md").write_text(
        "---\nname: bom\ndescription: Reads files with a byte order mark\n---\n", encoding="utf-8-sig")
    assert plugin_cost.desc_of(plugin / "skills" / "bom" / "SKILL.md") == "Reads files with a byte order mark"
    assert plugin_cost.main([str(tmp_path / "out.json"), str(tmp_path)]) == 0
    assert "1 plugins, 2 skills/commands" in capsys.readouterr().out
