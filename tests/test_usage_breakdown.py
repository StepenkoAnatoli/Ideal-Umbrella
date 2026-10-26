import json
from conftest import write_jsonl


def test_prices_5m_and_1h_writes_separately(usage_breakdown, tmp_path):
    path = write_jsonl(tmp_path / "transcript.jsonl", [
        {
            "type": "assistant",
            "message": {
                "id": "m1",
                "usage": {
                    "input_tokens": 1_000_000,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 1_000_000,
                    "cache_creation": {
                        "ephemeral_5m_input_tokens": 1_000_000,
                        "ephemeral_1h_input_tokens": 0,
                    },
                    "output_tokens": 0,
                },
                "content": [],
            },
        },
        {
            "type": "assistant",
            "message": {
                "id": "m2",
                "usage": {
                    "input_tokens": 0,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 1_000_000,
                    "cache_creation": {
                        "ephemeral_5m_input_tokens": 0,
                        "ephemeral_1h_input_tokens": 1_000_000,
                    },
                    "output_tokens": 0,
                },
                "content": [],
            },
        },
        # Duplicate message ids are the same API response and must not be billed twice.
        {
            "type": "assistant",
            "message": {
                "id": "m1",
                "usage": {
                    "input_tokens": 1_000_000,
                    "cache_creation_input_tokens": 1_000_000,
                    "cache_creation": {"ephemeral_5m_input_tokens": 1_000_000},
                },
                "content": [],
            },
        },
    ])

    totals, _chars, turns = usage_breakdown.summarize([path])
    assert turns == 2
    assert totals["cache_creation_5m_input_tokens"] == 1_000_000
    assert totals["cache_creation_1h_input_tokens"] == 1_000_000
    assert totals["cache_creation_input_tokens"] == 2_000_000

    cost = usage_breakdown.costs(totals)
    assert cost["cache writes (5m)"] == 5_000_000
    assert cost["cache writes (1h)"] == 8_000_000
    assert cost["fresh input"] == 4_000_000


def test_total_without_breakdown_is_priced_as_5m(usage_breakdown, tmp_path):
    path = write_jsonl(tmp_path / "old.jsonl", [{
        "type": "assistant",
        "message": {
            "id": "old-1",
            "usage": {"cache_creation_input_tokens": 2_000_000},
            "content": [],
        },
    }])
    totals, _chars, _turns = usage_breakdown.summarize([path])
    assert totals["cache_creation_5m_input_tokens"] == 2_000_000
    assert totals["cache_creation_1h_input_tokens"] == 0


def test_report_names_both_write_ttls(usage_breakdown, tmp_path, capsys):
    path = write_jsonl(tmp_path / "one.jsonl", [{
        "type": "assistant",
        "message": {
            "id": "m",
            "usage": {
                "cache_creation_input_tokens": 1_000_000,
                "cache_creation": {"ephemeral_1h_input_tokens": 1_000_000},
            },
            "content": [],
        },
    }])
    totals, chars, turns = usage_breakdown.summarize([path])
    usage_breakdown.print_report([path], totals, chars, turns)
    out = capsys.readouterr().out
    assert "cache_creation_5m_input_tokens" in out
    assert "cache_creation_1h_input_tokens" in out
    assert "cache writes (1h)" in out
    assert "cache writes (5m) 0%" in out


def test_non_object_lines_are_skipped(usage_breakdown, tmp_path):
    # A transcript line holding a JSON list or string used to raise AttributeError.
    path = tmp_path / "transcript.jsonl"
    path.write_text('[1, 2]\n"text"\nnull\n' + json.dumps({
        "type": "assistant",
        "message": {"id": "m1", "usage": {"input_tokens": 10, "output_tokens": 5}, "content": []},
    }) + "\n" + json.dumps({"type": "assistant", "message": "not an object"}) + "\n", encoding="utf-8")
    totals, _, turns = usage_breakdown.summarize([path])
    assert turns == 1
    assert totals["input_tokens"] == 10


def test_folder_with_glob_characters_is_found(usage_breakdown, tmp_path, capsys):
    # The folder went into glob.glob unescaped, so "proj[1]" matched "proj1" and found nothing.
    folder = tmp_path / "proj[1]"
    folder.mkdir()
    write_jsonl(folder / "t.jsonl", [{
        "type": "assistant",
        "message": {"id": "m1", "usage": {"input_tokens": 10, "output_tokens": 5}, "content": []},
    }])
    assert usage_breakdown.main([str(folder)]) == 0
    assert "1 transcripts" in capsys.readouterr().out


def test_a_folder_named_like_a_transcript_is_skipped(usage_breakdown, tmp_path, capsys):
    # The glob matched a folder named x.jsonl and open() raised IsADirectoryError.
    (tmp_path / "x.jsonl").mkdir()
    write_jsonl(tmp_path / "t.jsonl", [{
        "type": "assistant",
        "message": {"id": "m1", "usage": {"input_tokens": 10, "output_tokens": 5}, "content": []},
    }])
    assert usage_breakdown.main([str(tmp_path)]) == 0
    assert "1 transcripts" in capsys.readouterr().out


def test_an_unreadable_transcript_is_one_line(usage_breakdown, tmp_path, capsys, monkeypatch):
    # The transcript was opened outside any try, so a file unreadable between the glob and
    # the read was a traceback; the other transcript scripts open in a try with one line.
    import builtins
    good = write_jsonl(tmp_path / "good.jsonl", [{
        "type": "assistant",
        "message": {"id": "m1", "usage": {"input_tokens": 10, "output_tokens": 5}, "content": []},
    }])
    locked = write_jsonl(tmp_path / "locked.jsonl", [])
    real_open = builtins.open

    def failing_open(file, *args, **kwargs):
        if str(file) == str(locked):
            raise PermissionError(13, "Permission denied", str(file))
        return real_open(file, *args, **kwargs)
    monkeypatch.setattr(builtins, "open", failing_open)
    totals, _, turns = usage_breakdown.summarize([locked, good])
    err = capsys.readouterr().err
    assert turns == 1 and totals["input_tokens"] == 10
    assert err.count("\n") == 1 and "locked.jsonl" in err and "Permission denied" in err


def test_wrong_typed_usage_fields_are_skipped_and_a_bom_is_read(usage_breakdown, tmp_path):
    # `usage` that is a list, `message.id` that is a list and `"text": null` each raised; a
    # BOM made the first line unparseable, so it was dropped in silence.
    path = tmp_path / "transcript.jsonl"
    lines = [
        {"type": "assistant", "message": {"id": "m0", "usage": {"input_tokens": 10}, "content": []}},
        {"type": "assistant", "message": {"id": "m1", "usage": [1], "content": []}},
        {"type": "assistant", "message": {"id": "m2", "usage": "x", "content": []}},
        {"type": "assistant", "message": {"id": ["m3"], "usage": {"input_tokens": 1}, "content": []}},
        {"type": "assistant", "message": {"id": "m4", "usage": {"input_tokens": 1}, "content": [
            {"type": "text", "text": None}, {"type": "thinking", "thinking": 5},
            {"type": "text", "text": "ok"}]}},
        {"type": "assistant", "message": {"id": "m5", "usage": {"input_tokens": 1}, "content": "text"}},
    ]
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8-sig")
    totals, chars, turns = usage_breakdown.summarize([path])
    assert turns == 3 and totals["input_tokens"] == 12
    assert chars["visible text"] == 2
