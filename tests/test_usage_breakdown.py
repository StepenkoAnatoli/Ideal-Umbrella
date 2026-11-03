import json
import os

import pytest

from conftest import link_or_skip, loop_or_skip, not_found_at, refuse_listing, refuse_looks_inside, write_jsonl


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
    # A transcript line holding a JSON list or string used to raise AttributeError. Review 35
    # (mutant t8): a line cut off mid-write, as the first line and after a good one, is skipped.
    path = tmp_path / "transcript.jsonl"
    cut = '{"type": "assist\n'
    path.write_text(cut + '[1, 2]\n"text"\nnull\n' + json.dumps({
        "type": "assistant",
        "message": {"id": "m1", "usage": {"input_tokens": 10, "output_tokens": 5}, "content": []},
    }) + "\n" + cut + json.dumps({"type": "assistant", "message": "not an object"}) + "\n", encoding="utf-8")
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


@pytest.mark.parametrize("what", ["folder", "transcript"])
def test_a_folder_or_transcript_that_cannot_be_read_says_cannot_read(usage_breakdown, tmp_path, capsys,
                                                                   monkeypatch, what):
    # Review 26, C2 other hit: glob said nothing for a folder it could not list ("no .jsonl
    # files"), os.path.isfile() passed a transcript it could not look at over, and open()
    # raised a traceback for one it could not read.
    write_jsonl(tmp_path / "t.jsonl", [{
        "type": "assistant",
        "message": {"id": "m1", "usage": {"input_tokens": 10, "output_tokens": 5}, "content": []},
    }])
    if what == "folder":
        refuse_listing(tmp_path, monkeypatch)
    else:
        refuse_looks_inside(tmp_path, monkeypatch)
    with pytest.raises(SystemExit) as e:
        usage_breakdown.main([str(tmp_path)])
    message = str(e.value.code)
    assert "cannot read" in message and "no .jsonl" not in message, message
    assert str(tmp_path if what == "folder" else tmp_path / "t.jsonl") in message, message


def _responses(path, n, start=0):
    write_jsonl(path, [{
        "type": "assistant",
        "message": {"id": f"{path.name}-{i}", "usage": {"input_tokens": 1, "output_tokens": 1}, "content": []},
    } for i in range(start, start + n)])


@pytest.mark.parametrize("what", ["no transcripts", "missing"])
def test_a_folder_without_transcripts_is_a_one_line_error(usage_breakdown, tmp_path, capsys, what):
    # Review 31, L1: nothing failed when the "no .jsonl files" check was dropped (a zero report,
    # exit 0). Only the top folder is read: transcripts in a subfolder or hidden folder are not.
    folder = tmp_path / "gone" if what == "missing" else tmp_path
    if what == "no transcripts":
        (tmp_path / "x.jsonl").mkdir()
        _responses(tmp_path / ".d.jsonl", 1)
        (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
        for sub in ("sub", ".hidden"):
            (tmp_path / sub).mkdir()
            _responses(tmp_path / sub / "t.jsonl", 1)
    with pytest.raises(SystemExit) as e:
        usage_breakdown.main([str(folder)])
    message = str(e.value.code)
    want = f"no .jsonl files in {folder}" if what == "no transcripts" else f"cannot read {folder}"
    assert message.startswith(want), message
    assert capsys.readouterr().out == ""


def test_the_count_largest_transcripts_are_read_and_dot_files_are_not(usage_breakdown, tmp_path, capsys):
    # Review 27, L2: no test passed a COUNT or held transcripts of different sizes, so reading
    # the smallest first, or reading dot files, went unnoticed.
    _responses(tmp_path / "a.jsonl", 1)
    _responses(tmp_path / "b.jsonl", 50)
    _responses(tmp_path / "c.jsonl", 20)
    _responses(tmp_path / ".d.jsonl", 100)                          # glob's *.jsonl skips dot files
    _responses(tmp_path / "E.JSONL", 30)                            # *.jsonl on Windows only
    assert usage_breakdown.main([str(tmp_path), "2"]) == 0
    assert f"2 transcripts, {80 if os.name == 'nt' else 70} API responses" in capsys.readouterr().out


def test_a_link_to_a_transcript_is_read(usage_breakdown, tmp_path, capsys):
    # Review 27, L2: an lstat in place of the stat would drop every linked transcript.
    _responses(tmp_path / "real.txt", 3)
    link_or_skip(tmp_path / "t.jsonl", tmp_path / "real.txt")
    assert usage_breakdown.main([str(tmp_path)]) == 0
    assert "1 transcripts, 3 API responses" in capsys.readouterr().out


def test_a_symlink_loop_named_like_a_transcript_is_passed_over(usage_breakdown, tmp_path, capsys):
    # Review 27, I2: os.stat raised ELOOP and the run stopped with "cannot read"; os.path.isfile
    # passed over it before pass 26.
    _responses(tmp_path / "t.jsonl", 2)
    loop_or_skip(tmp_path / "loop.jsonl")
    assert usage_breakdown.main([str(tmp_path)]) == 0
    assert "1 transcripts, 2 API responses" in capsys.readouterr().out


def test_a_listed_transcript_that_is_not_found_says_cannot_read(usage_breakdown, tmp_path, capsys, monkeypatch):
    # Review 28, L1: pass 27 passed over a listed transcript that os.stat said was not found,
    # as one removed after the listing. On Windows a path past MAX_PATH says the same while it
    # is there, and its usage was left out of the report.
    _responses(tmp_path / "a.jsonl", 1)
    _responses(tmp_path / "b.jsonl", 2)
    not_found_at(tmp_path / "b.jsonl", monkeypatch)
    with pytest.raises(SystemExit) as exit_:
        usage_breakdown.main([str(tmp_path)])
    assert f"cannot read {tmp_path / 'b.jsonl'}" in str(exit_.value.code), exit_.value.code
    assert capsys.readouterr().out == ""


def test_a_link_to_a_missing_transcript_is_passed_over(usage_breakdown, tmp_path, capsys):
    # Review 28, L1: a listed name that is not found is "cannot read" unless it is a link to
    # a missing target, which holds no usage; nothing pinned that exception.
    _responses(tmp_path / "a.jsonl", 1)
    link_or_skip(tmp_path / "b.jsonl", tmp_path / "missing.jsonl")
    assert usage_breakdown.main([str(tmp_path)]) == 0
    assert capsys.readouterr().out.startswith("1 transcripts, 1 API responses")


def test_a_link_through_a_file_is_passed_over(usage_breakdown, tmp_path, capsys):
    # Review 29, L1: its stat gives NotADirectoryError, and pass 28 stopped with "cannot read".
    _responses(tmp_path / "a.jsonl", 1)
    (tmp_path / "afile").write_text("x", encoding="utf-8")
    link_or_skip(tmp_path / "b.jsonl", tmp_path / "afile" / "b.jsonl")
    assert usage_breakdown.main([str(tmp_path)]) == 0
    assert capsys.readouterr().out.startswith("1 transcripts, 1 API responses")


def test_a_link_into_a_folder_that_cannot_be_searched_says_cannot_read(usage_breakdown, tmp_path, capsys,
                                                                       monkeypatch):
    # Review 29, L2: nothing failed when every error on a link was passed over.
    _responses(tmp_path / "a.jsonl", 1)
    locked = tmp_path / "locked"
    locked.mkdir()
    _responses(locked / "x.jsonl", 2)
    link_or_skip(tmp_path / "b.jsonl", locked / "x.jsonl")
    refuse_looks_inside(locked, monkeypatch)
    with pytest.raises(SystemExit) as exit_:
        usage_breakdown.main([str(tmp_path)])
    assert f"cannot read {tmp_path / 'b.jsonl'}" in str(exit_.value.code), exit_.value.code


# ---- review 8 (main bcc441c) ----

def test_malformed_usage_fields_and_a_bom_neither_crash_nor_lose_the_first_line(usage_breakdown, tmp_path):
    # Review 8, low 18: usage as a list or "x", a list message id, text null raised
    # AttributeError or TypeError; a BOM dropped the first line.
    path = write_jsonl(tmp_path / "t.jsonl", [
        {"type": "assistant", "message": {"id": "m1", "usage": {"output_tokens": 7},
                                          "content": [{"type": "text", "text": "hi"}]}},
        {"type": "assistant", "message": {"id": "m2", "usage": [1, 2]}},
        {"type": "assistant", "message": {"id": "m3", "usage": "x"}},
        {"type": "assistant", "message": {"id": ["m4"], "usage": {"output_tokens": 1}}},
        {"type": "assistant", "message": {"id": "m5", "usage": {"output_tokens": 2}, "content": [
            {"type": "text", "text": None}, {"type": "thinking", "thinking": 5}]}},
        {"type": "assistant", "message": {"id": "m6", "content": 5}},
    ])
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    tot, out_chars, turns = usage_breakdown.summarize([str(path)])
    assert turns == 2 and tot["output_tokens"] == 9
    assert out_chars["visible text"] == 2


@pytest.mark.parametrize("raw", ["Infinity", "-Infinity", "NaN", "1e400"])
def test_a_token_count_of_infinity_counts_zero_not_a_traceback(usage_breakdown, tmp_path, raw):
    # Self-review S12: int(float("inf")) raises OverflowError, which _int did not catch.
    path = tmp_path / "t.jsonl"
    path.write_text('{"type":"assistant","message":{"id":"m1","usage":{"input_tokens":%s,'
                    '"output_tokens":7},"content":[]}}\n' % raw, encoding="utf-8")
    totals, _chars, turns = usage_breakdown.summarize([path])
    assert totals["input_tokens"] == 0 and totals["output_tokens"] == 7 and turns == 1


@pytest.mark.parametrize("raw, counted", [
    ('"12"', 0), ('" 12 "', 0), ('"1_000"', 0), ("true", 0), ("null", 0), ('{"n":1}', 0),
    ("12", 12), ("12.0", 12),
])
def test_only_a_json_number_is_a_token_count(usage_breakdown, tmp_path, raw, counted):
    # Review 9, A10: int("12") made the text "12" a count, though _int's docstring says text
    # counts 0; int(True) made true a 1.
    path = tmp_path / "t.jsonl"
    path.write_text('{"type":"assistant","message":{"id":"m1","usage":{"input_tokens":%s,'
                    '"output_tokens":7},"content":[]}}\n' % raw, encoding="utf-8")
    totals, _chars, turns = usage_breakdown.summarize([path])
    assert totals["input_tokens"] == counted and totals["output_tokens"] == 7 and turns == 1


@pytest.mark.parametrize("raw, counted", [
    ("-5", 0), ("-0.0", 0), ("12.9", 0), ("1e308", 0), ("1" + "0" * 400, 0), (str(2 ** 63), 0),
    (str(2 ** 63 - 1), 2 ** 63 - 1), ("0", 0), ("12.0", 12), ("1e3", 1000),
])
def test_a_token_count_is_a_whole_number_from_0_to_2_63(usage_breakdown, tmp_path, raw, counted):
    # SA7: -5 gave a "-17%" share, 1e308 "nan%", a 401-digit count an OverflowError.
    path = tmp_path / "t.jsonl"
    path.write_text('{"type":"assistant","message":{"id":"m1","usage":{"input_tokens":%s,'
                    '"output_tokens":7},"content":[]}}\n' % raw, encoding="utf-8")
    totals, _chars, turns = usage_breakdown.summarize([path])
    assert totals["input_tokens"] == counted and totals["output_tokens"] == 7 and turns == 1


def test_a_huge_token_count_is_no_traceback_in_the_report(usage_breakdown, tmp_path, capsys):
    (tmp_path / "t.jsonl").write_text(
        '{"type":"assistant","message":{"id":"m1","usage":{"input_tokens":1%s,'
        '"output_tokens":7},"content":[]}}\n' % ("0" * 400), encoding="utf-8")
    usage_breakdown.main([str(tmp_path)])
    out = capsys.readouterr().out
    assert "nan" not in out and " -" not in out, out


def test_a_sessions_subagent_transcripts_are_counted_with_it(usage_breakdown, tmp_path, capsys):
    # General review 44170ca, B4: only the project folder was listed, so a session's
    # <session>/subagents/*.jsonl (their cache writes and output) were left out of the totals.
    _responses(tmp_path / "s1.jsonl", 1)
    (tmp_path / "s1" / "subagents").mkdir(parents=True)
    _responses(tmp_path / "s1" / "subagents" / "agent-a.jsonl", 40)
    _responses(tmp_path / "s1" / "subagents" / "agent-b.jsonl", 9)
    _responses(tmp_path / "s2.jsonl", 20)
    (tmp_path / "s2" / "subagents").mkdir(parents=True)
    _responses(tmp_path / "s2" / "subagents" / "agent-c.jsonl", 2)
    (tmp_path / "other").mkdir()
    _responses(tmp_path / "other" / "t.jsonl", 100)               # not a session's subagents
    assert usage_breakdown.main([str(tmp_path), "1"]) == 0
    # The count is of sessions: s1 with its subagents is the largest; s2 is left out.
    assert "3 transcripts, 50 API responses, 2 of them subagent transcripts" in capsys.readouterr().out
    assert usage_breakdown.main([str(tmp_path)]) == 0
    assert "5 transcripts, 72 API responses, 3 of them subagent transcripts" in capsys.readouterr().out


def test_streamed_lines_of_one_response_take_the_largest_count_of_each_field(usage_breakdown, tmp_path):
    # Review general-44170ca, N1: the lines of one streamed response share a message id. An
    # early line can hold a partial output count; the largest of each field is the response's.
    def line(uuid, output, cache_read, text):
        return {"type": "assistant", "uuid": uuid, "message": {
            "id": "m1", "usage": {"input_tokens": 3, "cache_read_input_tokens": cache_read,
                                  "output_tokens": output},
            "content": [{"type": "text", "text": text}]}}
    path = write_jsonl(tmp_path / "t.jsonl", [line("u1", 1, 100, "ab"), line("u2", 40, 0, "cde")])
    totals, chars, turns = usage_breakdown.summarize([path])
    assert turns == 1
    assert totals["output_tokens"] == 40
    assert totals["cache_read_input_tokens"] == 100
    assert totals["input_tokens"] == 3
    assert chars["visible text"] == 5


def test_a_resumed_session_that_repeats_earlier_lines_counts_their_content_once(usage_breakdown, tmp_path):
    # Review general-44170ca, N2: the same event (same uuid) in two files is counted once.
    event = {"type": "assistant", "uuid": "u1", "message": {
        "id": "m1", "usage": {"output_tokens": 5}, "content": [{"type": "text", "text": "abc"}]}}
    a = write_jsonl(tmp_path / "a.jsonl", [event])
    b = write_jsonl(tmp_path / "b.jsonl", [event])
    totals, chars, turns = usage_breakdown.summarize([a, b])
    assert (turns, totals["output_tokens"], chars["visible text"]) == (1, 5, 3)
