import json
import os

import pytest

from conftest import load_module, python_314_pathlib, refuse_looks_inside


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


@pytest.mark.parametrize("pathlib_kind", ["3.13", "3.14"])
def test_an_app_folder_that_cannot_be_looked_at_says_cannot_read(plugin_cost, tmp_path, capsys, monkeypatch,
                                                                 pathlib_kind):
    # Review 24, F1 other hits: on 3.13 is_dir() raised PermissionError (a traceback); on 3.14
    # it says False, and the folder was "not a folder".
    app = tmp_path / "blocked" / "app"
    app.mkdir(parents=True)
    if pathlib_kind == "3.14":
        python_314_pathlib(monkeypatch)
    refuse_looks_inside(tmp_path / "blocked", monkeypatch)
    assert plugin_cost.main([str(tmp_path / "out.json"), str(app)]) == 1
    err = capsys.readouterr().err
    assert f"cannot read {app}" in err and "not a folder" not in err, err


def test_an_app_folder_through_a_file_is_not_a_folder(plugin_cost, tmp_path, capsys):
    # Review 26, C3: nothing failed when NotADirectoryError ("a_file/x") read as "cannot read".
    (tmp_path / "a_file").write_text("", encoding="utf-8")
    assert plugin_cost.main([str(tmp_path / "out.json"), str(tmp_path / "a_file" / "x")]) == 1
    err = capsys.readouterr().err
    assert "not a folder" in err and "cannot read" not in err, err
    assert not (tmp_path / "out.json").exists()


# ---- review 8 (main bcc441c) ----

def test_a_plugin_json_with_a_bom_keeps_its_name(plugin_cost, tmp_path, capsys):
    # Review 8, low 18: the folder name was shown instead of the plugin's name; the .mcp.json
    # beside it (other hit) counted 0 servers.
    pytest.importorskip("tiktoken")
    plugin = make_plugin(tmp_path, "folder-name", mcp={"s": {}})
    (plugin / ".claude-plugin" / "plugin.json").write_text('{"name": "real-name"}', encoding="utf-8-sig")
    (plugin / ".mcp.json").write_text('{"mcpServers": {"s": {}}}', encoding="utf-8-sig")
    out = tmp_path / "out.json"
    assert plugin_cost.main([str(out), str(tmp_path)]) == 0
    (row,) = json.loads(out.read_text(encoding="utf-8"))
    assert row[0] == "real-name" and row[3] == 1


@pytest.mark.parametrize("name", [["x"], 7, None, ""])
def test_a_plugin_name_that_is_not_text_falls_back_to_the_folder(plugin_cost, tmp_path, capsys, name):
    # Review 8, low 41: ["x"] raised "unsupported format string passed to list.__format__".
    pytest.importorskip("tiktoken")
    plugin = make_plugin(tmp_path, "folder-name", skills=["one"])
    (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": name}), encoding="utf-8")
    out = tmp_path / "out.json"
    assert plugin_cost.main([str(out), str(tmp_path)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))[0][0] == "folder-name"


def test_an_output_path_in_a_missing_folder_is_one_line_not_a_traceback(plugin_cost, tmp_path, capsys):
    # Review 8, low 19.
    pytest.importorskip("tiktoken")
    make_plugin(tmp_path / "app", "alpha")
    out = tmp_path / "missing" / "out.json"
    assert plugin_cost.main([str(out), str(tmp_path / "app")]) == 1
    err = capsys.readouterr().err
    assert err.startswith(f"Error: cannot write {out}") and err.count("\n") == 1, err


def test_an_encoding_that_cannot_load_is_one_line_not_a_traceback(plugin_cost, tmp_path, capsys, monkeypatch):
    # Review 8, low 19: tiktoken.get_encoding was unguarded (offline, a proxy, a corrupt cache).
    import sys
    import types

    def broken(name):
        raise ValueError("hash mismatch for o200k_base")
    monkeypatch.setitem(sys.modules, "tiktoken", types.SimpleNamespace(get_encoding=broken))
    make_plugin(tmp_path / "app", "alpha")
    assert plugin_cost.main([str(tmp_path / "out.json"), str(tmp_path / "app")]) == 1
    err = capsys.readouterr().err
    assert "hash mismatch for o200k_base" in err and err.count("\n") == 1, err


def test_a_plugin_under_a_hidden_folder_is_counted(plugin_cost, tmp_path, capsys):
    # Review 8, low 20: glob("**") without include_hidden passed over .hidden/plugin.
    pytest.importorskip("tiktoken")
    make_plugin(tmp_path / ".cache", "hidden-one")
    make_plugin(tmp_path, "plain")
    assert {os.path.basename(r) for r in plugin_cost.plugin_roots(tmp_path)} == {"hidden-one", "plain"}


@pytest.mark.parametrize("front, want", [
    ("description: >\n  Folded text\n  here\n", "Folded text here"),
    ("description: >-\n  Folded text here\n", "Folded text here"),
    ("description: |\n  Literal text\n  here\n", "Literal text here"),
    ("description: |2+\n  Literal\n", "Literal"),
    ("description: Plain > text\n", "Plain > text"),
])
def test_a_folded_or_literal_description_is_read_without_its_indicator(plugin_cost, tmp_path, front, want):
    # Review 8, low 21: desc_of returned "> Folded text here".
    md = tmp_path / "SKILL.md"
    md.write_text(f"---\nname: x\n{front}---\n", encoding="utf-8")
    assert plugin_cost.desc_of(md) == want
