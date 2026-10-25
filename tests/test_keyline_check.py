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


@pytest.mark.parametrize("token,changed", [
    ("v2", "v3"),
    ("PRs", "MRs"),
    ("b07b3b6", "b07b3b7"),
    ("sha256", "sha512"),
    ("utf8", "utf16"),
    ("__init__", "__main__"),
])
def test_identifier_shapes_that_fell_through_every_alternative(keyline_check, token, changed):
    # A bare version, a plural acronym, a git hash, a lowercase word with digits and a dunder
    # name matched no alternative, so a rendering that changed them PASSed on the anchor "14:02".
    source = f"deploy: {token} live at 14:02"
    assert token in keyline_check.invariants(source)
    result = keyline_check.check(source, source.replace(token, changed))
    assert not result.ok and result.missing == [token]
    assert keyline_check.check(source, f"פריסה: {token} עלתה ב-14:02").ok


def test_prose_words_are_not_hashes_or_identifiers(keyline_check):
    inv = keyline_check.invariants("The defaced cafe faced a deadbeef deadline on page 2 of 10.")
    assert inv == {"2": "number", "10": "number"}


def test_number_is_not_found_inside_a_time_or_a_grouped_number(keyline_check):
    # "10" used to be found at the start of "10:00" and "2" inside "2,500".
    assert keyline_check.check("max 10 connections at 14:02", "restart at 10:00 at 14:02").missing == ["10"]
    assert keyline_check.check("retry 2 times at 14:02", "retry 2,500 times at 14:02").missing == ["2"]
    assert keyline_check.check("retry 2 times at 14:02", "retry 2 times (2,500 max) at 14:02").ok
    assert keyline_check.check("~1,900 attempts at 14:02", "1,900 ניסיונות ב-14:02").ok


def test_name_after_a_mid_line_separator_is_checked(keyline_check):
    # A dash, ">" or "#" anywhere before a name used to count as a list marker, so the name was
    # skipped as a sentence start and a rendering that dropped it PASSed.
    assert keyline_check.check("db: moved to Postgres - Prisma stays", "db: moved to Postgres").missing == ["Prisma"]
    assert keyline_check.check("compare: size > Postgres limit", "compare: size limit").missing == ["Postgres"]
    inv = keyline_check.invariants("- **Language:** TypeScript\n## Heading here\n> Quoted Name")
    assert "Language" not in inv and "Heading" not in inv and "Quoted" not in inv
    assert "TypeScript" in inv and "Name" in inv


def test_hebrew_hedges_keep_the_class(keyline_check):
    # Hedges were English-only, so every hedged source FAILed against a correct Hebrew rendering.
    source = "risk: pool could be exhausted at 14:02; fix should ship"
    assert keyline_check.check(source, "סיכון: המאגר עלול להתרוקן ב-14:02; התיקון אמור לצאת").ok
    lost = keyline_check.check(source, "סיכון: המאגר יתרוקן ב-14:02; התיקון ייצא")
    assert lost.missing_hedges == ["possibility", "obligation"]
    assert keyline_check.hedges("ייתכן שכן, כנראה; צריך לבדוק; ניתן") == {
        "possibility": ["ייתכן"], "probability": ["כנראה"], "obligation": ["צריך"], "ability": ["ניתן"]}


@pytest.mark.parametrize("english,hebrew", [
    ("Monday", "ביום שני"), ("October", "מאוקטובר"), ("May", "במאי"), ("MAY", "מאי"), ("Sat", "בשבת"),
])
def test_month_and_weekday_names_accept_their_hebrew_form(keyline_check, english, hebrew):
    source = f"due: {english} at 14:02"
    assert english in keyline_check.invariants(source)
    assert keyline_check.check(source, f"יעד: {hebrew} ב-14:02").ok
    assert keyline_check.check(source, "יעד: ב-14:02").missing == [english]
    assert keyline_check.check(source, "יעד: ביום שלישי ב-14:02").missing == [english]


def test_upper_case_may_before_a_number_is_the_month(keyline_check):
    assert keyline_check.hedges("Window: MAY 2026") == {}
    assert keyline_check.hedges("WE MAY FAIL") == {"possibility": ["may"]}


@pytest.mark.parametrize("source, rendering, dropped", [
    ("due: May at 14:02", "יעד: מאיפה ב-14:02 ההגעה", "May"),          # "from where", not the month
    ("deploy: Sat at 14:02", "פריסה: מחשבת ב-14:02", "Sat"),                # "thought", not שבת
    ("cutover: June at 14:02", "מעבר: ב-14:02 עם יוניקוד", "June"),        # "Unicode"
])
def test_a_hebrew_calendar_form_inside_another_word_is_not_the_name(keyline_check, source, rendering, dropped):
    # The Hebrew forms were wrapped in the ASCII-only boundaries, so any Hebrew letters could
    # sit on either side and a dropped month passed.
    result = keyline_check.check(source, rendering)
    assert not result.ok
    assert result.missing == [dropped]
    for ok in ("במאי", "ממאי", "ובמאי"):
        assert keyline_check.check("due: May at 14:02", f"יעד: {ok} ב-14:02").ok
    # "לשבת" is "to sit" and also "to Saturday": a prefix letter plus the name is accepted.
    assert keyline_check.check("deploy: Saturday at 14:02", "פריסה: ב-14:02, לשבת").ok


def test_a_status_value_after_a_bold_label_is_not_a_name(keyline_check):
    # Checking the word after "**Label:**" (so that "- **Stack:** Postgres" keeps Postgres) made
    # "Done" and "High" invariants, and a correct Hebrew rendering failed.
    source = "- **Status:** Done\n- **Priority:** High\n- **Deadline:** 2026-11-01\n- **Stack:** Postgres\n"
    inv = keyline_check.invariants(source)
    assert "Postgres" in inv and "2026-11-01" in inv
    assert "Done" not in inv and "High" not in inv
    hebrew = "- **סטטוס:** בוצע\n- **עדיפות:** גבוהה\n- **יעד:** 2026-11-01\n- **Stack:** Postgres\n"
    assert keyline_check.check(source, hebrew).ok


def test_upper_case_may_beside_an_acronym_is_the_month(keyline_check):
    assert keyline_check.hedges("ship: MAY, 14:02 UTC") == {}
    assert keyline_check.check("window: API freeze in MAY", "חלון: הקפאת API במאי").ok
    assert keyline_check.hedges("WE MAY FAIL") == {"possibility": ["may"]}


def test_hedges_skip_list_markers_like_invariants(keyline_check):
    assert keyline_check.hedges("2) May we proceed?") == {"possibility": ["may"]}
    assert keyline_check.hedges("1. May we proceed?") == {"possibility": ["may"]}


def test_markdown_bold_with_underscores_is_not_a_dunder(keyline_check):
    inv = keyline_check.invariants("__Important__ note at 14:02 in __init__")
    assert "__Important__" not in inv
    assert inv["__init__"] == "snake"


def test_number_is_not_found_inside_a_date_a_percentage_or_a_slash_pair(keyline_check):
    # "10" used to be found as the month of "2026-10-25", in "10%" and in "10/25", so a
    # rendering that dropped the number passed on the anchor "14:02".
    date = "on 2026-10-25 at 14:02"
    for number in ("10", "25", "2026"):
        assert keyline_check.check(f"max {number} at 14:02", date).missing == [number], number
    assert keyline_check.check("max 10 at 14:02", "cap 10% at 14:02").missing == ["10"]
    assert keyline_check.check("max 10 at 14:02", "ratio 10/25 at 14:02").missing == ["10"]
    assert keyline_check.check("max 25 at 14:02", "ratio 10/25 at 14:02").missing == ["25"]
    assert keyline_check.check("max 10 at 14:02", "10 ב-14:02").ok
    assert keyline_check.check("cap 10% at 14:02", "10% ב-14:02").ok
    # Both ends of a range stay findable, and so does a number after a dash.
    assert keyline_check.check("pages 5-10 at 14:02", "עמודים 5-10 ב-14:02").ok
    assert keyline_check.check("max 10 at 14:02", "מקסימום ב-10 ב-14:02").ok


def test_time_is_not_found_at_the_end_of_a_longer_time(keyline_check):
    # "00:30" used to be found inside "10:00:30".
    assert keyline_check.check("at 00:30 and 14:02", "at 10:00:30 and 14:02").missing == ["00:30"]
    assert keyline_check.check("at 00:30 and 14:02", "ב-00:30 וב-14:02").ok


def test_an_upper_case_acronym_is_not_a_hebrew_month_or_day(keyline_check):
    # The Hebrew calendar forms were accepted for every token kind, so "DEC" (an acronym) was
    # present wherever December was, and "SAT" wherever Saturday was.
    for token, hebrew in (("DEC", "דצמבר"), ("SAT", "שבת"), ("MAR", "מרץ")):
        assert keyline_check.check(f"code: {token} at 14:02", f"קוד: {hebrew} ב-14:02").missing == [token]
    assert keyline_check.check("due: Dec at 14:02", "יעד: דצמבר ב-14:02").ok
    assert keyline_check.check("due: MAY at 14:02", "יעד: מאי ב-14:02").ok


def test_a_long_dash_joined_run_is_extracted_in_linear_time(keyline_check):
    # The path and file alternatives rescanned the rest of a dash-joined run from every word in
    # it: 8000 pairs took seconds, and a hook has a 30 s budget.
    import time
    text = "-".join("ab-cd" for _ in range(8000))
    start = time.perf_counter()
    keyline_check.invariants(text)
    assert time.perf_counter() - start < 2.0


@pytest.mark.parametrize("line", [
    "years 2020-2024 at 14:02", "budget 1000-2000 x", "season 2026-27 x", "in 2026-10 x",
    "ticket 2026-1234 x", "FY2024-25 x", "Q4 2025-2026 x", "call 5-12-34 x", "ids 7-10-20 x",
    "ratio 1/10 x", "v1/10 x", "ratio 3:1:30 x", "pages 5-10", "ב-10 ב-14:02",
])
def test_a_source_passes_against_itself(keyline_check, line):
    # The date and slash boundaries of the number lookup fired on any "NNNN-" or "N/" prefix,
    # so a year range or a fraction failed against a rendering holding the source verbatim.
    result = keyline_check.check(line, line)
    assert result.ok, result.missing
