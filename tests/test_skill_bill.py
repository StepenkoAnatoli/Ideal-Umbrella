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
