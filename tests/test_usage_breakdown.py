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
