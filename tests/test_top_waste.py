import pytest

from conftest import load_module, write_jsonl


@pytest.fixture
def top_waste():
    return load_module("top_waste", "scripts/top_waste.py")


def call(uid, tool_id, name, command=None, uuid=None):
    inp = {"command": command} if command is not None else {}
    return {"type": "assistant", "uuid": uuid or uid,
            "message": {"id": "m" + uid, "role": "assistant",
                        "content": [{"type": "tool_use", "id": tool_id, "name": name, "input": inp}]}}


def result(uid, tool_id, text):
    return {"type": "user", "uuid": uid,
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_id, "content": text}]}}


def test_bash_size_buckets(top_waste):
    assert [top_waste.size_bucket(n) for n in (0, 1999, 2000, 7999, 8000, 11999, 12000, 29999, 30000)] == [
        "<2k", "<2k", "2-8k", "2-8k", "8-12k", "8-12k", "12-30k", "12-30k", ">30k"]


def test_share_histogram_and_repeats(top_waste, tmp_path):
    path = write_jsonl(tmp_path / "s.jsonl", [
        call("1", "t1", "Bash", "git status"), result("r1", "t1", "x" * 100),
        call("2", "t2", "Bash", "git status"), result("r2", "t2", "x" * 9000),
        call("3", "t3", "Read"), result("r3", "t3", "y" * 900),
        call("4", "t4", "Bash", "pytest -q"), result("r4", "t4", "z" * 40000),
    ])
    data = top_waste.analyse([str(path)])
    assert data["by_tool"]["Bash"] == 100 + 9000 + 40000
    assert data["by_tool"]["Read"] == 900
    assert data["bash_buckets"]["<2k"] == (1, 100)
    assert data["bash_buckets"]["8-12k"] == (1, 9000)
    assert data["bash_buckets"][">30k"] == (1, 40000)
    assert data["repeats"][0] == ("git status", 2, 9100)


def test_a_repeated_uuid_counts_once_and_odd_input_is_skipped(top_waste, tmp_path):
    lines = [call("1", "t1", "Bash", "ls"), result("r1", "t1", "a" * 10), result("r1", "t1", "a" * 10),
             {"type": "user", "message": {"content": "plain text"}},
             {"type": "user", "uuid": "q", "message": {"content": [{"type": "tool_result", "tool_use_id": ["x"],
                                                                     "content": None}]}}]
    path = write_jsonl(tmp_path / "s.jsonl", lines)
    data = top_waste.analyse([str(path)])
    assert data["by_tool"]["Bash"] == 10
    assert data["by_tool"]["?"] == 0


def test_report_and_errors(top_waste, tmp_path, capsys):
    write_jsonl(tmp_path / "s.jsonl", [call("1", "t1", "Bash", "ls"), result("r1", "t1", "a" * 10)])
    assert top_waste.main([str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "Bash" in out and "<2k" in out
    with pytest.raises(SystemExit) as e:
        top_waste.main([])
    assert "usage" in str(e.value)
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(SystemExit) as e:
        top_waste.main([str(empty)])
    assert "no .jsonl" in str(e.value)
    with pytest.raises(SystemExit) as e:
        top_waste.main([str(tmp_path / "missing")])
    assert "cannot read" in str(e.value)
