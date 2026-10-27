import json
import subprocess
import sys

import pytest

from conftest import ROOT, load_module

SCRIPT = ROOT / "scripts" / "ledger.py"


@pytest.fixture
def ledger():
    return load_module("ledger", "scripts/ledger.py")


def lines(path):
    return [json.loads(line) for line in path.read_bytes().decode("utf-8").split("\n") if line]


def test_first_run_creates_the_file_and_says_there_is_nothing_to_compare(ledger, tmp_path, capsys):
    path = tmp_path / "new folder" / "m.jsonl"
    assert ledger.main(["--file", str(path), "--fixed-tokens", "71396", "--date", "2026-10-19"]) == 0
    assert lines(path) == [{"date": "2026-10-19", "fixed_tokens": 71396}]
    assert "first line" in capsys.readouterr().out


def test_second_run_prints_the_delta_to_the_previous_line(ledger, tmp_path, capsys):
    path = tmp_path / "m.jsonl"
    ledger.main(["--file", str(path), "--fixed-tokens", "71396", "--tools", "40",
                 "--deny-applied", "no", "--cc-version", "2.1.0", "--date", "2026-10-19"])
    capsys.readouterr()
    assert ledger.main(["--file", str(path), "--fixed-tokens", "70000", "--tools", "40",
                        "--deny-applied", "yes", "--cc-version", "2.2.0", "--date", "2026-10-27"]) == 0
    out = capsys.readouterr().out
    assert "fixed_tokens: 71,396 -> 70,000 (-1,396, -2.0%)" in out
    assert "tools: 40 -> 40 (0)" in out
    assert "deny_applied: False -> True" in out
    assert "cc_version: 2.1.0 -> 2.2.0" in out
    assert "2026-10-19" in out
    assert lines(path)[-1] == {"date": "2026-10-27", "cc_version": "2.2.0", "fixed_tokens": 70000,
                               "tools": 40, "deny_applied": True}


def test_a_field_only_one_line_has_is_shown_as_new_or_not_measured(ledger, tmp_path, capsys):
    path = tmp_path / "m.jsonl"
    ledger.main(["--file", str(path), "--fixed-tokens", "71396"])
    capsys.readouterr()
    ledger.main(["--file", str(path), "--first-call-cache-write", "49423"])
    out = capsys.readouterr().out
    assert "first_call_cache_write: (none) -> 49,423" in out
    assert "fixed_tokens: 71,396 -> (not measured)" in out


def test_unreadable_lines_are_skipped_and_counted(ledger, tmp_path, capsys):
    # A torn last line (a crash during an append) or a hand edit must not stop the next run,
    # and the delta compares with the last line that is a JSON object.
    path = tmp_path / "m.jsonl"
    path.write_bytes(b'{"date": "2026-10-19", "fixed_tokens": 71396}\n[1, 2]\n{"date": "2026-10-2\n')
    assert ledger.main(["--file", str(path), "--fixed-tokens", "72000"]) == 0
    out = capsys.readouterr().out
    assert "fixed_tokens: 71,396 -> 72,000 (+604, +0.8%)" in out
    assert "2 unreadable line(s) skipped" in out


def test_a_file_without_a_final_newline_is_not_glued_to(ledger, tmp_path):
    path = tmp_path / "m.jsonl"
    path.write_bytes(b'{"fixed_tokens": 71396}')
    ledger.main(["--file", str(path), "--fixed-tokens", "70000", "--date", "2026-10-27"])
    assert path.read_bytes() == b'{"fixed_tokens": 71396}\n{"date": "2026-10-27", "fixed_tokens": 70000}\n'


def test_crlf_and_non_utf8_bytes_in_the_file_do_not_stop_the_run(ledger, tmp_path, capsys):
    path = tmp_path / "m.jsonl"
    path.write_bytes(b'{"fixed_tokens": 71396, "note": "caf\xe9"}\r\n')
    assert ledger.main(["--file", str(path), "--fixed-tokens", "71000"]) == 0
    assert "fixed_tokens: 71,396 -> 71,000" in capsys.readouterr().out
    assert path.read_bytes().startswith(b'{"fixed_tokens": 71396, "note": "caf\xe9"}\r\n{')


def test_dry_run_prints_the_line_and_the_delta_and_writes_nothing(ledger, tmp_path, capsys):
    path = tmp_path / "m.jsonl"
    path.write_text('{"fixed_tokens": 71396}\n', encoding="utf-8")
    assert ledger.main(["--file", str(path), "--fixed-tokens", "70000", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert '"fixed_tokens": 70000' in out and "-1,396" in out
    assert path.read_text(encoding="utf-8") == '{"fixed_tokens": 71396}\n'
    assert ledger.main(["--file", str(tmp_path / "none" / "m.jsonl"), "--tools", "3", "--dry-run"]) == 0
    assert not (tmp_path / "none").exists()


def test_a_note_and_a_path_outside_ascii_round_trip(ledger, tmp_path, capsys):
    path = tmp_path / "מדידות" / "m.jsonl"
    assert ledger.main(["--file", str(path), "--tools", "38", "--note", "après la mise à jour"]) == 0
    assert lines(path)[0]["note"] == "après la mise à jour"


@pytest.mark.parametrize("args", [
    [],                                         # nothing measured
    ["--note", "only a note"],                  # a note is not a measurement
    ["--fixed-tokens", "-1"],
    ["--fixed-tokens", "many"],
    # Review 5, info I3: a count of hundreds of digits was taken, and the delta to a smaller
    # earlier value then raised OverflowError after the line was written.
    ["--fixed-tokens", "1" + "0" * 15],
    ["--tools", "1.5"],
    ["--deny-applied", "maybe", "--tools", "3"],
    ["--date", "27/10/2026", "--tools", "3"],
])
def test_bad_arguments_exit_2_and_write_nothing(ledger, tmp_path, capsys, args):
    path = tmp_path / "m.jsonl"
    with pytest.raises(SystemExit) as stop:
        ledger.main(["--file", str(path), *args])
    assert stop.value.code == 2
    assert not path.exists()


def test_a_count_of_fifteen_digits_after_a_small_one_is_compared(ledger, tmp_path, capsys):
    # Review 5, info I3: the largest count taken, padded with zeros, still gives a delta.
    path = tmp_path / "m.jsonl"
    ledger.main(["--file", str(path), "--fixed-tokens", "1", "--date", "2026-10-19"])
    capsys.readouterr()
    assert ledger.main(["--file", str(path), "--fixed-tokens", "000" + "9" * 15, "--date", "2026-10-27"]) == 0
    assert lines(path)[-1]["fixed_tokens"] == int("9" * 15)
    assert "fixed_tokens: 1 -> " in capsys.readouterr().out


def test_a_file_it_cannot_write_is_a_one_line_error_not_a_traceback(tmp_path):
    folder = tmp_path / "m.jsonl"
    folder.mkdir()  # the --file path is a folder: reading and appending both fail
    result = subprocess.run([sys.executable, "-I", str(SCRIPT), "--file", str(folder), "--tools", "3"],
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert result.stderr.startswith("error: ")


def test_the_default_file_is_the_repository_ledger(ledger):
    assert ledger.DEFAULT_FILE == ROOT / "research" / "measurements.jsonl"


def test_the_repository_ledger_is_valid(ledger):
    entries = lines(ledger.DEFAULT_FILE)
    assert entries, "research/measurements.jsonl is empty"
    for entry in entries:
        assert isinstance(entry, dict) and isinstance(entry.get("date"), str)
        assert set(entry) & set(ledger.MEASURES), entry


def test_a_line_separator_in_a_note_does_not_split_the_line(ledger, tmp_path, capsys):
    # Review 1, finding 4: str.splitlines() also splits on U+2028, U+2029, NEL, FF and VT,
    # which json.dumps(ensure_ascii=False) leaves raw; the line read back as two broken ones.
    path = tmp_path / "m.jsonl"
    ledger.main(["--file", str(path), "--fixed-tokens", "71396", "--note", "before after\x0c\x85"])
    ledger.main(["--file", str(path), "--fixed-tokens", "70000", "--note", "second"])
    capsys.readouterr()
    assert ledger.main(["--file", str(path), "--fixed-tokens", "69000"]) == 0
    out = capsys.readouterr().out
    assert "unreadable" not in out
    assert "change since line 2 " in out and "70,000 -> 69,000" in out
    assert lines(path)[0]["note"] == "before after\x0c\x85"


def test_a_deeply_nested_hand_edit_is_skipped_not_a_traceback(ledger, tmp_path, capsys):
    # Review 1, finding 5: json.loads raises RecursionError, not ValueError, for deep nesting.
    path = tmp_path / "m.jsonl"
    path.write_text('{"fixed_tokens": 71396}\n' + "[" * 100000 + "\n", encoding="utf-8")
    assert ledger.main(["--file", str(path), "--fixed-tokens", "70000"]) == 0
    out = capsys.readouterr().out
    assert "1 unreadable line(s) skipped" in out and "71,396 -> 70,000" in out


@pytest.mark.parametrize("option", ["--note", "--cc-version"])
def test_text_that_is_not_unicode_is_a_usage_error(ledger, tmp_path, option):
    # A command-line byte that is not UTF-8 arrives as a lone surrogate, which cannot be written.
    path = tmp_path / "m.jsonl"
    with pytest.raises(SystemExit) as stop:
        ledger.main(["--file", str(path), "--tools", "3", option, "caf\udce9"])
    assert stop.value.code == 2
    assert not path.exists()


@pytest.mark.skipif(sys.platform != "linux", reason="file names that are not UTF-8 are a Linux case")
def test_a_file_name_that_is_not_utf8_is_printed_not_a_traceback(tmp_path):
    folder = tmp_path / "d\udcff"
    result = subprocess.run([sys.executable, "-I", str(SCRIPT), "--file", str(folder / "m.jsonl"), "--tools", "3"],
                            capture_output=True)
    assert result.returncode == 0, result.stderr
    assert b"Traceback" not in result.stderr and b"appended to" in result.stdout
    assert lines(folder / "m.jsonl") == [{"date": lines(folder / "m.jsonl")[0]["date"], "tools": 3}]
