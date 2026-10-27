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
