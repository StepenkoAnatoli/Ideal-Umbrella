import pytest

from conftest import load_module


@pytest.fixture
def keyline_check():
    return load_module("keyline_check", "keyline/keyline_check.py")


def test_iso_timestamp_is_one_invariant(keyline_check):
    # "2026-10-25T10:00:00Z" used to split into the numbers 2026 and 10 and the time 00:00Z, so
    # a rendering with the day changed passed.
    source = "Outage began at 2026-10-25T10:00:00Z and ended 2026-10-25T11:30:00Z."
    inv = keyline_check.invariants(source)
    assert inv["2026-10-25T10:00:00Z"] == "datetime"
    assert inv["2026-10-25T11:30:00Z"] == "datetime"
    assert "2026" not in inv and "10" not in inv

    changed_day = source.replace("2026-10-25T10", "2026-10-26T10")
    result = keyline_check.check(source, changed_day)
    assert not result.ok
    assert result.missing == ["2026-10-25T10:00:00Z"]

    changed_minute = source.replace("11:30", "11:31")
    assert not keyline_check.check(source, changed_minute).ok
    assert keyline_check.check(source, source).ok


@pytest.mark.parametrize("stamp", [
    "2026-10-25T10:00",
    "2026-10-25T10:00:00.123Z",
    "2026-10-25T10:00:00+02:00",
    "2026-10-25T10:00:00-0500",
])
def test_timestamp_forms(keyline_check, stamp):
    inv = keyline_check.invariants(f"At {stamp} the job ran.")
    assert inv == {stamp: "datetime"}


def test_timestamp_with_a_space_counts_as_present(keyline_check):
    # The same instant written "2026-10-25 10:00:00Z" (Hebrew renderings often drop the T).
    result = keyline_check.check("Began 2026-10-25T10:00:00Z.", "התחיל 2026-10-25 10:00:00Z")
    assert result.ok


def test_possessive_is_not_part_of_a_name(keyline_check):
    # "Claude's" used to be the invariant, so "של Claude" (Hebrew for "of Claude") failed.
    inv = keyline_check.invariants("Run Claude's hook on Jean-Luc's laptop.")
    assert inv == {"Claude": "proper", "Jean-Luc": "proper"}
    assert keyline_check.check("Run Claude's hook now.", "הרץ את ה-hook של Claude").ok
    assert not keyline_check.check("Run Claude's hook now.", "הרץ את ה-hook").ok


def test_month_may_is_not_a_hedge(keyline_check):
    assert keyline_check.hedges("Release: May 2026 rollout; it may slip.") == {"possibility": ["may"]}
    assert keyline_check.hedges("May 14 is the date.") == {}
    assert keyline_check.hedges("May I help?") == {"possibility": ["may"]}


def test_non_utf8_note_is_a_read_error_not_a_traceback(tmp_path):
    import subprocess
    import sys
    from conftest import ROOT
    note = tmp_path / "latin.txt"
    note.write_bytes(b"caf\xe9 503\n")
    other = tmp_path / "other.txt"
    other.write_text("503\n", encoding="utf-8")
    for args in ([note, other], [other, note], ["--list", note]):
        result = subprocess.run([sys.executable, "-I", str(ROOT / "keyline" / "keyline_check.py"), *map(str, args)],
                                capture_output=True, text=True, encoding="utf-8")
        assert result.returncode == 2, result.stderr
        assert "not UTF-8" in result.stderr and "Traceback" not in result.stderr


def test_month_may_mid_sentence_is_not_a_hedge(keyline_check):
    # A capitalised "May" inside a sentence is the month ("in May because"); only the modal is
    # capitalised at a sentence start ("May I help?"). A Hebrew rendering that writes the month
    # as מאי used to be reported as a lost possibility hedge.
    assert keyline_check.hedges("It shipped in May because the fix landed.") == {}
    assert keyline_check.hedges("Shipped in May; it may slip.") == {"possibility": ["may"]}
    assert keyline_check.hedges("- May we proceed?") == {"possibility": ["may"]}
    assert keyline_check.hedges("Plan.\nMay I help?") == {"possibility": ["may"]}
