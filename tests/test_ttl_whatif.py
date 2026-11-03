import json

import pytest

from conftest import load_module, write_jsonl


@pytest.fixture
def ttl_whatif():
    return load_module("ttl_whatif", "scripts/ttl_whatif.py")


def response(mid, ts, read=0, write5=0, write1=0, uuid=None):
    return {
        "type": "assistant",
        "uuid": uuid or f"u-{mid}",
        "timestamp": ts,
        "message": {
            "id": mid,
            "usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_input_tokens": read,
                "cache_creation_input_tokens": write5 + write1,
                "cache_creation": {"ephemeral_5m_input_tokens": write5, "ephemeral_1h_input_tokens": write1},
            },
            "content": [],
        },
    }


def test_gap_buckets(ttl_whatif):
    assert ttl_whatif.bucket(0) == "<5m"
    assert ttl_whatif.bucket(299) == "<5m"
    assert ttl_whatif.bucket(300) == "5-15m"
    assert ttl_whatif.bucket(1800) == "30-60m"
    assert ttl_whatif.bucket(3600) == "1-4h"
    assert ttl_whatif.bucket(4 * 3600) == ">4h"


def test_a_gap_over_five_minutes_turns_a_read_into_a_rewrite(ttl_whatif, tmp_path):
    path = write_jsonl(tmp_path / "s.jsonl", [
        response("m1", "2026-01-01T00:00:00Z", write1=1_000_000),
        response("m2", "2026-01-01T00:02:00Z", read=1_000_000),       # 2 min: still a read
        response("m3", "2026-01-01T00:20:00Z", read=1_000_000),       # 18 min: a rewrite at 5m TTL
    ])
    result = ttl_whatif.analyse([[str(path)]])
    assert result["responses"] == 3
    # actual: 1M x $8 write + 2M x $0.20 reads
    assert result["actual"] == pytest.approx(8.0 + 0.4)
    # 5m TTL: first write at $5, one read at $0.20, one read turned into a $5 write
    assert result["whatif"] == pytest.approx(5.0 + 0.2 + 5.0)
    assert result["buckets"]["<5m"]["responses"] == 1
    assert result["buckets"]["15-30m"]["responses"] == 1


def test_streamed_lines_and_repeated_uuids_count_once(ttl_whatif, tmp_path):
    a = response("m1", "2026-01-01T00:00:00Z", write5=100)
    b = response("m1", "2026-01-01T00:00:01Z", write5=100, uuid="other")
    c = response("m2", "2026-01-01T00:01:00Z", read=100)
    path = write_jsonl(tmp_path / "s.jsonl", [a, b, c, c])
    assert ttl_whatif.analyse([[str(path)]])["responses"] == 2


def test_each_stream_has_its_own_gaps(ttl_whatif, tmp_path):
    main = write_jsonl(tmp_path / "main.jsonl", [response("m1", "2026-01-01T00:00:00Z", write5=10)])
    sub = write_jsonl(tmp_path / "sub.jsonl", [response("s1", "2026-01-01T03:00:00Z", write5=10)])
    result = ttl_whatif.analyse([[str(main)], [str(sub)]])
    assert sum(b["responses"] for b in result["buckets"].values()) == 0     # no stream has a second response


def test_bust_causes(ttl_whatif, tmp_path):
    path = write_jsonl(tmp_path / "s.jsonl", [
        response("m1", "2026-01-01T00:00:00Z", write5=100_000),
        response("m2", "2026-01-01T00:30:00Z", write5=100_000),                       # 5m write, 30 min later
        response("m3", "2026-01-01T00:30:30Z", write5=30_000),                        # context shrank: compaction
        response("m4", "2026-01-01T00:31:00Z", read=30_000, write5=20_000),           # normal growth
        response("m5", "2026-01-01T00:31:30Z", write5=60_000),                        # none of the above
    ])
    busts = ttl_whatif.analyse([[str(path)]])["busts"]
    assert busts == {"gap over TTL": 1, "compaction": 1, "other": 1}


def test_report_and_dollar_caveat(ttl_whatif, tmp_path, capsys):
    write_jsonl(tmp_path / "s.jsonl", [
        response("m1", "2026-01-01T00:00:00Z", write1=1000),
        response("m2", "2026-01-01T01:00:00Z", read=1000),
    ])
    assert ttl_whatif.main([str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "1-4h" in out and "plan limits" in out


def test_bad_arguments_and_unreadable_input_are_one_line_errors(ttl_whatif, tmp_path):
    with pytest.raises(SystemExit) as e:
        ttl_whatif.main([])
    assert "usage" in str(e.value)
    with pytest.raises(SystemExit) as e:
        ttl_whatif.main([str(tmp_path)])
    assert "no .jsonl" in str(e.value)
    with pytest.raises(SystemExit) as e:
        ttl_whatif.main([str(tmp_path / "missing")])
    assert "cannot read" in str(e.value)


def test_odd_lines_are_skipped(ttl_whatif, tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_bytes(b'\xff\xfe not json\n[]\n{"type":"assistant","message":5}\n'
                  + json.dumps(response("m1", "not a time", write5=5)).encode() + b"\n"
                  + json.dumps(response("m2", "2026-01-01T00:00:00Z", write5=5)).encode() + b"\n")
    assert ttl_whatif.analyse([[str(p)]])["responses"] == 1     # only the one with a readable time


def test_a_one_hour_stream_keeps_its_ttl_after_a_pure_read(ttl_whatif, tmp_path):
    path = write_jsonl(tmp_path / "s.jsonl", [
        response("m1", "2026-01-01T00:00:00Z", write1=100_000),
        response("m2", "2026-01-01T00:01:00Z", read=100_000),
        response("m3", "2026-01-01T00:20:00Z", write5=100_000),    # 19 min: the 1-hour cache should be live
    ])
    assert ttl_whatif.analyse([[str(path)]])["busts"] == {"other": 1}
