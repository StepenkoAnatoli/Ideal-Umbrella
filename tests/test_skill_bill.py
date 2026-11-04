import os

import pytest

from conftest import load_module


@pytest.fixture
def skill_bill():
    return load_module("skill_bill", "scripts/skill_bill.py")


def words(text):
    return len(text.split())


def make_skill(root, name, body="one two three", description="does a thing", extra_front="", files=None):
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n{extra_front}---\n{body}\n", encoding="utf-8")
    for rel, text in (files or {}).items():
        target = folder / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return folder


def test_always_on_and_invocation_cost(skill_bill, tmp_path):
    make_skill(tmp_path, "alpha", body="a b c d e", description="x y z")
    rows = skill_bill.analyse([str(tmp_path)], words)
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "alpha"
    assert row["always_on"] == words("- alpha: x y z\n")
    assert row["invocation"] == 5                       # the body only, not the frontmatter
    assert row["model"] is None


def test_referenced_files_count_and_unreferenced_ones_do_not(skill_bill, tmp_path):
    make_skill(tmp_path, "beta", body="read references/one.md first",
               files={"references/one.md": "p q r s", "references/two.md": "t u v w x y z"})
    row = skill_bill.analyse([str(tmp_path)], words)[0]
    assert row["invocation"] == 3 + 4


def test_a_model_override_is_flagged_and_inherit_is_not(skill_bill, tmp_path):
    make_skill(tmp_path, "gamma", extra_front="model: opus\n")
    make_skill(tmp_path, "delta", extra_front="model: inherit\n")
    rows = {r["name"]: r for r in skill_bill.analyse([str(tmp_path)], words)}
    assert rows["gamma"]["model"] == "opus"
    assert rows["delta"]["model"] is None


def test_rows_are_sorted_by_invocation_cost(skill_bill, tmp_path):
    make_skill(tmp_path, "small", body="a")
    make_skill(tmp_path, "large", body="a b c d e f g h")
    assert [r["name"] for r in skill_bill.analyse([str(tmp_path)], words)] == ["large", "small"]


def test_odd_skill_files_do_not_stop_the_scan(skill_bill, tmp_path):
    folder = tmp_path / "broken"
    folder.mkdir()
    (folder / "SKILL.md").write_bytes(b"\xff\xfe no frontmatter at all")
    make_skill(tmp_path, "fine")
    names = [r["name"] for r in skill_bill.analyse([str(tmp_path)], words)]
    assert sorted(names) == ["broken", "fine"]


def test_main_reports_and_flags(skill_bill, tmp_path, capsys, monkeypatch):
    make_skill(tmp_path, "gamma", extra_front="model: opus\n")
    monkeypatch.setattr(skill_bill, "load_counter", lambda: words)
    assert skill_bill.main([str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "gamma" in out and "model: opus" in out and "proxy" in out


def test_main_errors_are_one_line(skill_bill, tmp_path, monkeypatch):
    monkeypatch.setattr(skill_bill, "load_counter", lambda: words)
    with pytest.raises(SystemExit) as e:
        skill_bill.main([str(tmp_path / "missing")])
    assert "not a folder" in str(e.value)
    with pytest.raises(SystemExit) as e:
        skill_bill.main([str(tmp_path)])
    assert "no SKILL.md" in str(e.value)
    assert os.path.isdir(tmp_path)


def test_default_folders_skip_desktop_session_copies_and_count_a_skill_once(skill_bill, tmp_path, monkeypatch):
    app = tmp_path / "app"
    home = tmp_path / "home"
    make_skill(home / ".claude" / "skills", "alpha")
    make_skill(app / "local-agent-mode-sessions" / "s1" / "skills-plugin" / "skills", "alpha")
    plugin = app / "plugins" / "p"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    make_skill(plugin / "skills", "beta")
    monkeypatch.setenv("CLAUDE_APP_DIR", str(app))
    monkeypatch.setattr(skill_bill.Path, "home", classmethod(lambda cls: home))
    rows = skill_bill.analyse(skill_bill.default_folders(), words)
    assert sorted(r["name"] for r in rows) == ["alpha", "p:beta"]


def test_a_symlinked_skill_folder_is_found(skill_bill, tmp_path):
    real = tmp_path / "real"
    make_skill(real, "linked")
    root = tmp_path / "skills"
    root.mkdir()
    try:
        os.symlink(str(real / "linked"), str(root / "linked"), target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available")
    assert [r["name"] for r in skill_bill.analyse([str(root)], words)] == ["linked"]


def test_a_user_only_skill_has_no_always_on_cost_and_is_flagged(skill_bill, tmp_path):
    make_skill(tmp_path, "manual", description="x y z", extra_front="disable-model-invocation: true\n")
    make_skill(tmp_path, "auto", description="x y z")
    rows = {r["name"]: r for r in skill_bill.analyse([str(tmp_path)], words)}
    assert rows["manual"]["always_on"] == 0 and rows["manual"]["user_only"]
    assert rows["auto"]["always_on"] > 0 and not rows["auto"]["user_only"]


def test_a_link_to_a_parent_folder_does_not_add_skills_outside(skill_bill, tmp_path):
    skills = tmp_path / "skills"
    make_skill(skills, "a")
    make_skill(tmp_path / "other", "b")
    try:
        os.symlink(str(tmp_path), str(skills / "up"), target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available")
    assert [r["name"] for r in skill_bill.analyse([str(skills)], words)] == ["a"]


def test_the_cli_plugin_folder_and_the_config_dir_are_default_folders(skill_bill, tmp_path, monkeypatch):
    config = tmp_path / "cfg"
    plugin = config / "plugins" / "cache" / "p"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    make_skill(plugin / "skills", "cliplugin")
    make_skill(config / "skills", "mine")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    monkeypatch.setenv("CLAUDE_APP_DIR", str(tmp_path / "noapp"))
    rows = skill_bill.analyse(skill_bill.default_folders(), words)
    assert sorted(r["name"] for r in rows) == ["mine", "p:cliplugin"]


def test_plugin_skills_are_named_with_the_manifest_name_and_plain_skills_are_not(skill_bill, tmp_path):
    for folder, manifest in (("one", '{"name": "alpha"}'), ("two", '{"name": "beta"}'), ("three", "not json")):
        (tmp_path / folder / ".claude-plugin").mkdir(parents=True)
        (tmp_path / folder / ".claude-plugin" / "plugin.json").write_text(manifest, encoding="utf-8")
        make_skill(tmp_path / folder / "skills", "review")
    make_skill(tmp_path / "plain", "review")
    rows = skill_bill.analyse([str(tmp_path / n) for n in ("one", "two", "three", "plain")], words)
    assert sorted(r["name"] for r in rows) == ["alpha:review", "beta:review", "review", "three:review"]
    assert words("- alpha:review: does a thing\n") in {r["always_on"] for r in rows}


def test_a_folder_that_cannot_be_listed_is_noted_not_silently_skipped(skill_bill, tmp_path, monkeypatch, capsys):
    app = tmp_path / "app"
    (app / "p" / ".claude-plugin").mkdir(parents=True)
    (app / "p" / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    (app / "locked").mkdir()
    real_walk = os.walk

    def walk(top, *args, onerror=None, **kwargs):
        yield from real_walk(top, *args, onerror=onerror, **kwargs)
        if onerror:
            onerror(PermissionError(13, "Permission denied", str(app / "locked")))
    monkeypatch.setattr(os, "walk", walk)
    monkeypatch.setenv("CLAUDE_APP_DIR", str(app))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "nocfg"))
    assert skill_bill.default_folders()[-1] == str(app / "p")
    err = capsys.readouterr().err
    assert "cannot list" in err and "locked" in err and "plugins in it are not counted" in err


def test_a_link_to_the_root_of_another_drive_counts_as_above(skill_bill):
    above = skill_bill.pc.link_above
    assert not above("/a/b", "/a/b")
    if os.name != "nt":
        assert above("/a", "/a/b") and not above("/a/b", "/a")
    else:
        assert above("Z:\\", "C:\\work\\skills")           # another drive's root: not walked
        assert not above("Z:\\other", "C:\\work\\skills")  # a folder on another drive is not a root


def test_an_unreadable_skill_file_is_a_one_line_error_not_a_zero(skill_bill, tmp_path, monkeypatch):
    make_skill(tmp_path, "locked")
    real_open = open

    def refuse(path, *args, **kwargs):
        if str(path).endswith("SKILL.md"):
            raise PermissionError(13, "Permission denied", str(path))
        return real_open(path, *args, **kwargs)
    monkeypatch.setattr("builtins.open", refuse)
    monkeypatch.setattr(skill_bill, "load_counter", lambda: words)
    with pytest.raises(SystemExit) as e:
        skill_bill.main([str(tmp_path)])
    assert "cannot read" in str(e.value) and "\n" not in str(e.value)
