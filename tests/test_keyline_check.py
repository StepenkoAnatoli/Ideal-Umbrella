import pytest

from conftest import load_module


@pytest.fixture(scope="module")
def keyline_check():
    # One load per module: the module builds its word classes from Unicode on import (~0.2 s),
    # and no test changes it.
    return load_module("keyline_check", "keyline/keyline_check.py")


def _ratio(fn, small, big, runs=3):
    """Best-of-runs time of fn(big) over fn(small): a machine-independent measure of growth.
    The two are timed in turn, so a burst of load on the machine slows both alike."""
    import time
    best = [float("inf"), float("inf")]
    for _ in range(runs):
        for i, arg in enumerate((small, big)):
            start = time.perf_counter()
            fn(arg)
            best[i] = min(best[i], time.perf_counter() - start)
    return best[1] / max(best[0], 1e-4)


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


def test_a_number_alone_on_a_line_is_not_a_list_marker(keyline_check):
    # LIST_MARKER's "\s+" after "10." matched the newline, so a rendering that answers with the
    # number on a line of its own had it stripped as a marker and the number went missing.
    assert keyline_check.invariants("the answer\n10.\n") == {"10": "number"}
    assert keyline_check.check("value 10", "the answer\n10.\n").ok
    assert keyline_check.invariants("1. first\n2) second\n- third\n") == {}


def test_a_number_glued_to_a_separator_is_a_path(keyline_check):
    # Documented boundary of the lookup by extraction: "10/" is a path to the extractor (as
    # "notes/" is), on both sides, so a bare "10" is not found in it and "10/" passes against
    # itself.
    assert keyline_check.check("value 10", "scored 10/ 20").missing == ["10"]
    assert keyline_check.check("scored 10/ 20", "scored 10/ 20").ok


@pytest.mark.parametrize("tok", ["S3", "A100", "P0", "Q4", "H264", "A1"])
def test_a_one_letter_acronym_with_digits_is_an_identifier(keyline_check, tok):
    # The upper rule needed two capital letters, so S3, A100 and P0 were not invariants and a
    # rendering could drop or change them unnoticed.
    source = f"Moved the logs to {tok} last week."
    assert keyline_check.invariants(source) == {tok: "upper"}
    assert keyline_check.check(source, source).ok
    assert not keyline_check.check(source, source.replace(tok, "the bucket")).ok


@pytest.mark.parametrize("tok", ["A", "I", "As"])
def test_a_lone_capital_letter_is_still_not_an_identifier(keyline_check, tok):
    assert keyline_check.invariants(f"Then {tok} went home.") == {}


@pytest.mark.parametrize("tok", ["1e10", "2.5e-3", "0x1f", "0xDEADBEEF"])
def test_an_exponent_or_hex_number_is_one_invariant(keyline_check, tok):
    # "1e10" and "0x1f" fell through every rule (the number rule stopped at the letter), so a
    # rendering with the exponent or the hex value changed passed.
    source = f"The job took {tok} steps."
    assert keyline_check.invariants(source) == {tok: "number"}
    assert keyline_check.check(source, source).ok
    assert not keyline_check.check(source, source.replace(tok, "9")).ok


@pytest.mark.parametrize("bom", [b"", b"\xef\xbb\xbf"], ids=["no-bom", "bom"])
def test_the_offset_of_a_byte_that_is_not_utf8_counts_a_bom(keyline_check, tmp_path, bom):
    # Review 22, I1: utf-8-sig counts from after a BOM, so the offset was 3 bytes too low.
    note = tmp_path / "latin.txt"
    note.write_bytes(bom + b"caf\xe9 503\n")
    with pytest.raises(OSError, match=rf"at byte {len(bom) + 3}\)"):
        keyline_check.read(note)


# ---- review 8 (main bcc441c) ----

def test_a_date_and_time_written_with_a_space_pass_against_the_iso_form(keyline_check):
    # Review 8, medium 1: "2026-10-25 14:30" is a date and a time; the date's right boundary
    # refused the "T" after it and the time's left boundary the "T" before it.
    source = "Deploy at 2026-10-25 14:30."
    assert keyline_check.check(source, "Deploy at 2026-10-25T14:30Z.").ok
    assert keyline_check.check(source, "פריסה ב-2026-10-25T14:30").ok
    assert keyline_check.check(source, "Deploy at 2026-10-25T15:30Z.").missing == ["14:30"]
    assert keyline_check.check(source, "Deploy at 2026-10-26T14:30Z.").missing == ["2026-10-25"]


@pytest.mark.parametrize("source, rendering", [
    ("See notes/a.txt now.", "See notes/a.txt.bak now."),
    ("Sign report.pdf now.", "Sign report.pdf.gpg now."),
    ("Edit ~/.claude now.", "Edit ~/.claude.bak now."),
    ("Run build.sh now.", "Run build.sh.old now."),
    ("Read API.md now.", "Read API.md.bak now."),
    ("Ask Jean-Luc today.", "Ask Jean-Luc-Picard today."),
    ("See notes/a.txt now.", "See notes/a.txt/ now."),
    ("Moved to S3 today.", "Moved to S3-backup today."),
    ("Bump to v2 today.", "Bump to v2-beta today."),
    ("Set max_retries today.", "Set max_retries.bak today."),
    ("Fetch https://example.com/a now.", "Fetch https://example.com/a/b now."),
])
def test_a_rendering_that_only_extends_a_token_fails(keyline_check, source, rendering):
    # Review 8, medium 2: the right boundary let ".x", "-X" and "/" follow a path, file or
    # name, so a changed file name passed.
    result = keyline_check.check(source, rendering)
    assert not result.ok and result.missing, result
    assert keyline_check.check(source, source).ok
    assert keyline_check.check(rendering, rendering).ok


@pytest.mark.parametrize("source, rendering", [
    ("See notes/a.txt now.", "ראה את notes/a.txt."),
    ("See notes/a.txt now.", "ראה ב-notes/a.txt עכשיו"),
    ("Ask Jean-Luc today.", "שאל את Jean-Luc's team"),
    ("Ask Jean-Luc today.", "שאל את Jean-Luc-ים"),
    ("Sign report.pdf now.", "חתום על report.pdf, עכשיו"),
])
def test_a_token_followed_by_punctuation_or_hebrew_is_still_present(keyline_check, source, rendering):
    assert keyline_check.check(source, rendering).ok


@pytest.mark.parametrize("line", [
    "Use API-v2 today.", "Read report.pdf-old now.", "Ship v2-rc1 at 14:02.", "Call at 14:30-15:00.",
    "See notes/a.txt.bak and notes/a.txt now.", "Mail Jean-Luc's team today.",
])
def test_a_token_glued_to_more_text_in_the_source_passes_against_itself(keyline_check, line):
    result = keyline_check.check(line, line)
    assert result.ok, result


def test_a_sha256_digest_is_one_invariant(keyline_check):
    # Review 8, medium 3: the hash rule stopped at 40 hex digits (SHA-1).
    digest = "3b4ca1f2" * 8
    source = f"sha256 {digest} at 14:02."
    assert keyline_check.invariants(source)[digest] == "hash"
    assert keyline_check.check(source, f"sha256 {digest[:-1]}3 at 14:02.").missing == [digest]
    sha512 = "3b4ca1f2" * 16
    assert keyline_check.invariants(f"sha512 {sha512} at 14:02")[sha512] == "hash"


@pytest.mark.parametrize("name", ["Zürich", "Léa", "Ørsted", "Saint-Étienne", "Москва"])
def test_a_capitalised_name_with_a_non_ascii_letter_is_extracted(keyline_check, name):
    # Review 8, medium 4: the proper-noun rule was ASCII-only.
    source = f"Meeting at 10:00 with {name} today."
    assert keyline_check.invariants(source)[name] == "proper"
    assert keyline_check.check(source, "Meeting at 10:00 with Bob today.").missing == [name]
    assert keyline_check.check(source, f"פגישה ב-10:00 עם {name} היום").ok
    assert keyline_check.check(source, f"פגישה ב-10:00 עם ב{name} היום").ok


def test_an_upper_case_word_with_a_non_ascii_letter_is_one_identifier(keyline_check):
    # Review 8, low 29: "ÉCOLE" extracted "COLE", and a rendering with "COLE" passed.
    assert keyline_check.invariants("Visit ÉCOLE at 14:02.") == {"ÉCOLE": "upper", "14:02": "time"}
    assert keyline_check.check("Visit ÉCOLE at 14:02.", "Visit COLE at 14:02.").missing == ["ÉCOLE"]
    assert keyline_check.check("Visit ÉCOLE at 14:02.", "בקר ב-ÉCOLE ב-14:02").ok


@pytest.mark.parametrize("english,hebrew", [("OCTOBER", "באוקטובר"), ("MONDAY", "ביום שני")])
def test_an_upper_case_month_or_weekday_accepts_its_hebrew_form(keyline_check, english, hebrew):
    # Review 8, low 6: the Hebrew forms were tried only for a capitalised name or MAY.
    source = f"Due {english} 3 at 14:02."
    assert keyline_check.check(source, f"יעד {hebrew} 3 ב-14:02").ok
    assert keyline_check.check(source, "יעד 3 ב-14:02").missing == [english]


@pytest.mark.parametrize("source, changed", [
    ("2024. Migration done.", "2025. Migration done."),
    ("503. Gateway timed out.", "Gateway timed out."),
])
def test_a_leading_number_of_three_or_more_digits_is_not_a_list_marker(keyline_check, source, changed):
    # Review 8, low 9: any "N." at a line start was a list marker, so a year was skipped.
    assert keyline_check.invariants(source)
    assert not keyline_check.check(source, changed).ok
    assert keyline_check.invariants("1. first\n12) twelfth\n") == {}


def test_a_url_keeps_its_scheme(keyline_check):
    # Review 8, low 10: "https://example.com/a/b?x=1" was the path "//example.com/a/b" and "1".
    source = "Fetch https://example.com/a/b?x=1 at 14:02."
    inv = keyline_check.invariants(source)
    assert inv["https://example.com/a/b?x=1"] == "url"
    assert keyline_check.check(source, source.replace("https", "http")).missing == ["https://example.com/a/b?x=1"]
    assert keyline_check.check(source, "הורד את https://example.com/a/b?x=1 ב-14:02.").ok
    assert keyline_check.check("See (https://example.com/a).", "ראה https://example.com/a").ok


def test_ticket_no_is_not_a_negation(keyline_check):
    # Review 8, low 15: "No. 5" counted as a negation, so "מס' 5" lost one.
    assert keyline_check.negations("Ticket No. 5 and NO. 7") == 0   # SA8: lowercase "no. 7" after a word is "no"
    assert keyline_check.check("Ticket No. 5 at 14:02.", "כרטיס מס' 5 ב-14:02").ok
    assert keyline_check.negations("No, it is not.") == 2


@pytest.mark.parametrize("text", ["May: ship v2", "## May", "**May**: 3", "**May** 5", "Plan\nMay\n", "MAY: ship"])
def test_may_as_a_label_or_header_is_the_month(keyline_check, text):
    # Review 8, low 15: "May:" and "## May" at a line start were read as the modal verb.
    assert keyline_check.hedges(text) == {}


def test_may_as_a_modal_at_a_sentence_start_is_still_a_hedge(keyline_check):
    assert keyline_check.hedges("May I help?") == {"possibility": ["may"]}
    assert keyline_check.hedges("May we ship: yes") == {"possibility": ["may"]}


@pytest.mark.parametrize("source, rendering", [
    ("Starts 14:30Z.", "Starts 14:30:00Z."),
    ("Starts 14:30:00Z.", "Starts 14:30Z."),
    ("Starts 2026-10-25T14:30Z.", "Starts 2026-10-25T14:30:00Z."),
    ("Starts 2026-10-25T14:30:00Z.", "Starts 2026-10-25 14:30Z."),
])
def test_a_time_without_seconds_matches_the_same_time_with_zero_seconds(keyline_check, source, rendering):
    # Review 8, low 30 (fails closed).
    assert keyline_check.check(source, rendering).ok


def test_a_time_is_not_present_inside_a_time_with_other_seconds(keyline_check):
    assert keyline_check.check("Starts 14:30Z.", "Starts 14:30:15Z.").missing == ["14:30Z"]


def test_a_yes_no_pair_before_a_period_is_prose_not_a_path(keyline_check):
    # Review 8, low 31: "yes/no." was a path because the period was stripped after the check.
    assert keyline_check.invariants("Answer: yes/no.") == {}
    assert keyline_check.check("Answer yes/no at 14:02.", "תשובה כן/לא ב-14:02.").ok


def test_underscore_emphasis_does_not_hide_a_hedge_or_a_negation(keyline_check):
    # Review 8, low 34: "\b" saw "_could_" as one word.
    assert keyline_check.hedges("it _could_ fail") == {"possibility": ["could"]}
    assert keyline_check.negations("it is _not_ done") == 1


def test_every_snake_token_has_an_inner_underscore_or_is_a_dunder(keyline_check):
    # Review 8, low 35: invariants() had a snake filter no match could reach; the regex itself
    # guarantees this, and the test pins it so the filter is not needed back.
    import random
    rng = random.Random(8)
    for _ in range(3000):
        text = "".join(rng.choice("ab_A1 _") for _ in range(rng.randint(1, 16)))
        for tok, kind in keyline_check.invariants(text).items():
            if kind == "snake":
                assert "_" in tok.strip("_") or tok.startswith("__"), (text, tok)


@pytest.mark.parametrize("text", [
    "aA" * 50000 + "_",                     # camel-case run (review 8, low 32)
    "MAY " * 25000,                         # all-caps MAY line (review 8, low 33)
    "- May " * 17000,                       # a sentence-start look-back on one long line
    "May " * 25000 + "5",
    "Aa-" * 33000 + "_",
    "a." * 50000,                           # URL scheme look-ahead
    "x/" * 50000,
    "ÉA" * 50000 + "_",
    "1:" * 50000,
    "see http://x/" + ")" * 100000,         # URL trim (self-review S6)
])
def test_extraction_and_hedges_are_linear_on_100_kb(keyline_check, text):
    # Self-review S8: an absolute limit (1 s) failed on a slow machine for linear code. The
    # time of the whole text against its first quarter is ~4 for linear code and ~16 for
    # quadratic (the first half, ~2 against ~4 with a limit of 3.2, failed under CPU load):
    # a limit of 8 leaves linear code twice its ratio, and catches a quadratic part that
    # takes 2/3 of the time where the old limit needed 3/4. A load spike can only slow one
    # measurement, so the best of three measurements is taken; quadratic code never gets
    # under the limit.
    def run(t):
        keyline_check.invariants(t)
        keyline_check.hedges(t)
        keyline_check.check(t, t)
    ratios = []
    for _ in range(3):
        ratios.append(_ratio(run, text[: len(text) // 4], text))
        if ratios[-1] < 8:
            break
    assert min(ratios) < 8, ratios


def test_random_sources_pass_against_themselves(keyline_check):
    # Every new boundary is checked against the rule that a rendering holding the source
    # verbatim always passes.
    import random
    rng = random.Random(88)
    alphabet = ["a", "Z", "é", "É", "1", "0", ".", "-", "/", "\\", "_", " ", "'", ":", "T", "ב",
                "x.txt", "API", "v2", "2026-10-25", "14:30", "https://", "Jean-Luc", "May", "No. "]
    for _ in range(4000):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 12)))
        result = keyline_check.check(text, text)
        assert not result.missing and not result.missing_hedges, (text, result)


# ---- self-review of the review 8 fixes (S1-S13) ----

@pytest.mark.parametrize("source, rendering", [
    ("See notes/a.txt now.", "See old/notes/a.txt now."),
    ("Sign report.pdf now.", "Sign old-report.pdf now."),
    ("Sign report.pdf now.", "Sign old.report.pdf now."),
    ("Ask Jean-Luc today.", "Ask Marie-Jean-Luc today."),
    ("See notes/a.txt now.", "See /notes/a.txt now."),
    ("See notes/a.txt now.", "See notes/a.txt~ now."),
    ("Bump API today.", "Bump API# today."),
    ("Bump API today.", "Bump API@v3 today."),
])
def test_a_rendering_that_extends_a_token_on_either_side_fails(keyline_check, source, rendering):
    # S1: the boundary guarded only the right side, and not against "~", "@", "#", "+", "%".
    result = keyline_check.check(source, rendering)
    assert not result.ok and result.missing, result
    assert keyline_check.check(source, source).ok
    assert keyline_check.check(rendering, rendering).ok


@pytest.mark.parametrize("source, rendering", [
    ("Fetch https://example.com now.", "Fetch https://example.com@evil.io now."),
    ("Fetch https://e.com/?x=1 now.", "Fetch https://e.com/?x=1&debug=1 now."),
    ("Fetch https://e.com/a now.", "Fetch https://e.com/a#frag now."),
    ("Fetch https://e.com/a now.", "Fetch https://e.com/a%20b now."),
    ("Fetch https://e.com/a now.", "Fetch https://e.com/a,b now."),
])
def test_a_rendering_that_extends_a_url_fails(keyline_check, source, rendering):
    # S2: a URL is looked up by extraction, so whatever the rendering appends is part of its URL.
    result = keyline_check.check(source, rendering)
    assert not result.ok and result.missing, result
    assert keyline_check.check(source, source).ok
    assert keyline_check.check(rendering, rendering).ok


@pytest.mark.parametrize("source, rendering", [
    ("See https://e.com/a now.", "ראה https://e.com/a עכשיו."),
    ("See https://e.com/a now.", "ראה https://e.com/a, עכשיו."),
    ("See https://e.com/a now.", "ראה ב-https://e.com/a עכשיו."),
    ("See https://en.wikipedia.org/wiki/Foo_(bar) now.", "ראה (https://en.wikipedia.org/wiki/Foo_(bar))."),
])
def test_a_url_with_punctuation_or_hebrew_around_it_is_present(keyline_check, source, rendering):
    assert keyline_check.check(source, rendering).ok


@pytest.mark.parametrize("source, rendering", [
    ("Maintenance from 14:30 to 15:00.", "תחזוקה 14:30-15:00."),
    ("Maintenance from 14:30 to 15:00.", "תחזוקה 14:30/15:00."),
    ("Use Postgres or MySQL.", "השתמשו ב-Postgres/MySQL."),
    ("Open Monday to Friday.", "פתוח Monday-Friday."),
    ("Open Mon to Fri.", "פתוח Mon-Fri."),
    ("Supports v2.1 and v2.3.", "תומך ב-v2.1/v2.3."),
    ("Supports v2.1 and v2.3.", "תומך ב-v2.1-v2.3."),
    ("From 2026-10-25 to 2026-10-27.", "מ-2026-10-25-2026-10-27."),
    ("Use API and SDK today.", "השתמשו ב-API/SDK היום."),
])
def test_a_range_or_pair_of_tokens_keeps_both_tokens(keyline_check, source, rendering):
    # S3: the right boundary refused "-WORD" and "/" after a token, so a range or a pair of two
    # source tokens false-failed.
    result = keyline_check.check(source, rendering)
    assert result.ok, result


@pytest.mark.parametrize("source, rendering", [
    ("Ask Jean-Luc today.", "Ask Jean-Luc-Picard today."),      # a hyphen extends a name
    ("Ask Luc today.", "Ask Jean-Luc today."),
    ("Ask Paris today.", "Ask Paris-Nord today."),
    ("Moved to S3 today.", "Moved to S3-IA today."),
    ("Bump to v2 today.", "Bump to v2-rc1 today."),
    ("From 2026-10-25 today.", "From 2026-10-25-27 today."),
    ("Edit notes/a.txt today.", "Edit notes/a.txt/notes/b.txt today."),   # a path never pairs
    ("Run build.sh today.", "Run build.sh/run.sh today."),
    ("Use Postgres today.", "Use notes/Postgres today."),
    ("Use Postgres today.", "Use /Postgres today."),
])
def test_a_joiner_that_does_not_join_two_tokens_of_one_family_still_extends(keyline_check, source, rendering):
    result = keyline_check.check(source, rendering)
    assert not result.ok and result.missing, result


@pytest.mark.parametrize("text, count", [
    ("Is it up? No. 5 servers are down.", 1),
    ("No.\n5 of them failed.", 1),
    ("No. 5 of them failed.", 1),
    ("Ticket No. 5 and no. 7", 1),     # SA8: a lowercase "no." after a word is the answer
    ("Ticket No.\t5", 0),
])
def test_no_before_a_number_is_a_negation_at_a_sentence_start(keyline_check, text, count):
    # S4: "No. 5" was a number sign anywhere, also after "?" or across a newline.
    assert keyline_check.negations(text) == count


def test_a_dropped_no_at_a_sentence_start_fails(keyline_check):
    assert not keyline_check.check("Is it up? No. 5 servers are down.", "Is it up? 5 servers are down.").ok


@pytest.mark.parametrize("text", ["**May** we ship v2?", "## Risks. May we ship v2?", "## May we ship v2?",
                                  "WE _MAY_ FAIL", "_MAY_ FAIL"])
def test_may_in_bold_or_on_a_header_line_before_a_clause_is_a_hedge(keyline_check, text):
    # S5: any "**" after "May", and any "#" line, made it the month; "_MAY_" was not all-caps.
    assert keyline_check.hedges(text) == {"possibility": ["may"]}


@pytest.mark.parametrize("text", ["## **May**", "**May**\nship", "## May"])
def test_may_alone_in_bold_or_on_a_header_is_still_the_month(keyline_check, text):
    assert keyline_check.hedges(text) == {}


def test_trimming_a_url_is_linear(keyline_check):
    # S6: _trim_url counted the parentheses again for every character it removed.
    import time
    text = "see http://x/" + ")" * 100000
    start = time.perf_counter()
    inv = keyline_check.invariants(text)
    assert time.perf_counter() - start < 1.0
    assert inv == {"http://x/": "url"}


def test_many_distinct_tokens_are_checked_in_linear_time(keyline_check):
    # S7: present() searched the whole rendering once per distinct source token.
    def text(n):
        return " ".join(f"tok{i}x" for i in range(n))
    ratio = _ratio(lambda t: keyline_check.check(t, t), text(2000), text(8000))
    assert ratio < 8, ratio          # quadratic gives ~16


def test_a_url_scheme_alone_is_not_an_invariant(keyline_check):
    # S9: the "://" skip had no test.
    assert keyline_check.invariants("Links start with https://. At 14:02.") == {"14:02": "time"}


def test_a_url_keeps_a_parenthesis_it_opened(keyline_check):
    # S9: the balance check in _trim_url had no test.
    url = "https://en.wikipedia.org/wiki/Foo_(bar)"
    assert keyline_check.invariants(f"See {url} now.") == {url: "url"}
    assert keyline_check.invariants(f"(see {url})") == {url: "url"}


def test_a_time_with_a_zone_is_not_present_without_it(keyline_check):
    # S9: "Z?" for a source zone let "14:30" pass for "14:30Z".
    assert keyline_check.check("Starts 14:30Z.", "Starts 14:30.").missing == ["14:30Z"]


def test_a_time_is_not_present_inside_a_time_with_seconds(keyline_check):
    # S9: ":" in the extension guard had no test ("14:30:15" for "14:30").
    assert keyline_check.check("Starts 14:30 today.", "Starts 14:30:15 today.").missing == ["14:30"]


def test_nfd_text_is_read_as_nfc(keyline_check, tmp_path):
    # S13: "Zürich" written with a combining diaeresis extracted "Zu".
    import unicodedata
    nfc = "Meeting with Zürich at 10:00."
    nfd = unicodedata.normalize("NFD", nfc)
    assert keyline_check.check(nfc, nfd).ok
    assert keyline_check.check(nfd, nfc).ok
    note = tmp_path / "n.txt"
    note.write_text(nfd, encoding="utf-8")
    assert keyline_check.read(note) == nfc


# ---- review 9 (main 7adc485) ----

URL_A1 = "https://x.io/a"


@pytest.mark.parametrize("rendering", [
    f"ראו **{URL_A1}** עכשיו",
    f"See *{URL_A1}* now",
    f"See “{URL_A1}” now",
    f"See ‘{URL_A1}’ now",
    f"See {URL_A1}—now",
    f"See {URL_A1}… now",
    f"| {URL_A1}| now |",
    f"|{URL_A1}|now|",
    f"ראו {URL_A1}‏ עכשיו",
    f"ראו {URL_A1}‎ עכשיו",
    f"See {URL_A1}​ now",
    f"See ‪{URL_A1}‬ now",
    f"See ⁦{URL_A1}⁩ now",
    f"See «{URL_A1}» now",
    f"See _{URL_A1}_ now",
    f"See __{URL_A1}__ now",
])
def test_markup_or_a_mark_glued_after_a_url_is_not_part_of_it(keyline_check, rendering):
    # Review 9, A1: the URL body refused a short list of characters, so "**", "”", "—", "…",
    # "|", RLM and the like became part of the rendering's URL. Both directions, and each
    # text against itself.
    source = f"See {URL_A1} now"
    assert keyline_check.check(source, rendering).ok, keyline_check.invariants(rendering)
    assert keyline_check.check(rendering, source).ok, keyline_check.invariants(rendering)
    assert keyline_check.check(rendering, rendering).ok


@pytest.mark.parametrize("url", [
    "https://x.io/a?b=1&c=2#f", "https://x.io/a(b)", "https://x.io/~u/a_b-c.d", "https://x.io/a%20b",
    "https://x.io/a;p=1", "https://user@x.io/a", "https://x.io/a*b", "https://x.io/a,b", "https://x.io/a!b",
    "https://x.io/a+b$c", "https://x.io/[x]", "https://x.io/Zürich", "https://x.io/a_",
])
def test_a_url_keeps_every_character_a_url_may_hold(keyline_check, url):
    assert keyline_check.invariants(f"See {url} now") == {url: "url"}


def test_a_url_with_a_glued_change_still_fails(keyline_check):
    # The allow-list must not let a rendering cut the URL short at a character a URL holds.
    assert not keyline_check.check(f"See {URL_A1} now", f"See {URL_A1}*b now").ok
    assert not keyline_check.check(f"See {URL_A1}b now", f"See **{URL_A1}** now").ok


@pytest.mark.parametrize("source, rendering", [
    ("Q: Fixed? A: No. 5 tests still fail.", "Q: Fixed? A: 5 tests still fail."),
    ("**Fixed?** No. 5 tests fail.", "**Fixed?** 5 tests fail."),
    ("Fixed? — No. 5 tests fail.", "Fixed? — 5 tests fail."),
    ('He asked "fixed?" No. 5 tests fail.', 'He asked "fixed?" 5 tests fail.'),
    ("Status (no. 3 tables remain).", "Status (3 tables remain)."),
    ("- No. 5 servers are down", "- 5 servers are down"),
    ("## No. 5 is down", "## 5 is down"),
    ("Done? Not yet, no. 3 tables remain.", "Done? Not yet, 3 tables remain."),
    ("Up?\n> No. 5 are down", "Up?\n> 5 are down"),
    ("Up? _No._ 5 are down", "Up? 5 are down"),
])
def test_a_dropped_no_before_a_number_fails_after_any_non_word(keyline_check, source, rendering):
    # Review 9, A2: "No." was a number sign everywhere but after a listed sentence boundary.
    result = keyline_check.check(source, rendering)
    assert not result.ok and result.neg_source == result.neg_rendering + 1, result


@pytest.mark.parametrize("text, count", [
    ("Ticket No. 5", 0), ("See ticket no. 7", 1), ("Item 3 No. 5", 0), ("Ticket No.\n5", 1),
    ("Ticket\nNo. 5", 1), ("Ticket No.  5", 0), ("Ticket: No. 5", 1),
])
def test_no_is_a_number_sign_only_after_a_word_on_the_same_line(keyline_check, text, count):
    # Review 9, A2 and A9 (4): "[ \t]*", not "\s*", between "No." and its number.
    assert keyline_check.negations(text) == count


@pytest.mark.parametrize("source, rendering", [
    ("Deploy to _Paris_ at _14:30_ with _v2.1_ and _5_ hosts, ticket API-7",
     "Deploy to _Berlin_ at _16:00_ with _v9.9_ and _7_ hosts, ticket API-7"),
    ("Deploy to __Paris__ at __14:30__", "Deploy to __Berlin__ at __16:00__"),
    ("Deploy to _Paris_ at _14:30_", "Deploy to Berlin at 16:00"),
    ("Deploy to Paris at 14:30", "Deploy to _Berlin_ at _16:00_"),
    ("See _https://x.io/a_ now", "See _http://x.io/a_ now"),
    ("Edit _notes/a.txt_ now", "Edit _notes/b.txt_ now"),
    ("Ship _v2.1_ to _API_", "שלחו את _v2.2_ ל-_API_"),
])
def test_underscore_emphasis_does_not_hide_an_invariant(keyline_check, source, rendering):
    # Review 9, A3 and the old #10 neighbour: "_" is a word character, so "_Paris_" hid "Paris".
    result = keyline_check.check(source, rendering)
    assert not result.ok and result.missing, result


@pytest.mark.parametrize("source, rendering", [
    ("Deploy to _Paris_ at _14:30_ with _v2.1_", "Deploy to Paris at 14:30 with v2.1"),
    ("Deploy to Paris at 14:30 with v2.1", "פריסה ל-_Paris_ ב-_14:30_ עם _v2.1_"),
    ("See _https://x.io/a_ now", "See https://x.io/a now"),
    ("Call __init__ and _private_name now", "Call __init__ and _private_name now"),
])
def test_underscore_emphasis_around_an_invariant_keeps_it_present(keyline_check, source, rendering):
    assert keyline_check.check(source, rendering).ok


@pytest.mark.parametrize("source, rendering", [
    ("Call __init__ now", "Call init now"),               # a dunder is not emphasis
    ("Call _private_name now", "Call private_name now"),  # a lone edge "_" is part of the name
    ("Call snake_case_ now", "Call snake_case now"),
])
def test_an_underscore_that_is_not_emphasis_stays_part_of_the_token(keyline_check, source, rendering):
    assert not keyline_check.check(source, rendering).ok


def test_a_long_dash_joined_run_is_checked_in_linear_time(keyline_check):
    # Review 9, A4: _token_at matched the whole rest of the run from every token in it.
    import time
    start = time.perf_counter()
    result = keyline_check.check("Meet Ab today.", "Meet " + "Ab-" * 20000 + "Ab today.")
    assert time.perf_counter() - start < 3, "quadratic"
    assert not result.ok
    fn = lambda n: keyline_check.check("Meet Ab today.", "Meet " + "Ab-" * n + "Ab today.")  # noqa: E731
    assert _ratio(fn, 2000, 16000) < 25


@pytest.mark.parametrize("source, rendering", [
    ("Errors last week:\n12.  \nAll in API.", "Errors last week:\n13.  \nAll in API."),
    ("Errors last week:\n12.\t\nAll in API.", "Errors last week:\n13.\t\nAll in API."),
    ("Errors last week:\n12)  \nAll in API.", "Errors last week:\n13)  \nAll in API."),
])
def test_a_list_marker_with_only_trailing_space_is_a_number(keyline_check, source, rendering):
    # Review 9, A5: a markdown hard break leaves spaces after "12." and the marker was stripped.
    assert keyline_check.check(source, rendering).missing == ["12"]


@pytest.mark.parametrize("source, rendering", [
    ("Open ab.txt now", "Open ab.txt=1 now"),
    ("Open ab.txt now", "Open ab.txt&x now"),
    ("Call API now", "Call API(x) now"),
    ("Open ab.txt now", "Open ab.txt,v now"),
    ("Call API now", "Call API$x now"),
    ("Call API now", "Call API*x now"),
    ("Open ab.txt now", "Open x@ab.txt now"),
    ("Call API now", "Call #API now"),
    ("Call API now", "Call x#API now"),
    ("Ship v2.1 now", "Ship +v2.1 now"),
    ("Call API now", "Call $API now"),
    ("Open notes/a.txt now", "Open C:notes/a.txt now"),
    ("Call API now", "Call x=API now"),
    ("Call API now", "Call x&API now"),
    ("Call API now", "Call x,API now"),
    ("Call API now", "Call x*API now"),
    ("Call API now", "Call %API now"),
])
def test_a_joiner_extends_a_token_on_both_sides_alike(keyline_check, source, rendering):
    # Review 9, A6: the two sides refused different sets, so "API#x" failed and "#API" passed.
    result = keyline_check.check(source, rendering)
    assert not result.ok and result.missing, result
    assert keyline_check.check(rendering, rendering).ok


@pytest.mark.parametrize("source, rendering", [
    ("Call API now", "Call **API** now"),
    ("Call API now", "Call *API*, now"),
    ("Call API now", "Call (API) now"),
    ("Call API now", "Call API: now"),
    ("Call API now", "Call API, then SDK"),
    ("Call API now", "Call `API` now"),
    ("Call API now", "Call [API](https://x.io) now"),
    ("Call API now", "קראו ל-API עכשיו"),
    ("Call API now", "Call API's client now"),
])
def test_markup_or_punctuation_beside_a_token_does_not_extend_it(keyline_check, source, rendering):
    assert keyline_check.check(source, rendering).ok


@pytest.mark.parametrize("source, rendering", [
    ("Mon open Monday-Friday", "Mon open Monday to Friday"),
    ("Mon open Monday-Friday", "Mon open יום שני עד יום שישי"),
    ("Mon open Monday-Wednesday-Friday", "Mon open Monday, Wednesday and Friday"),
    ("Mon open Monday-Friday", "Mon open Monday-Friday"),
])
def test_a_pair_of_calendar_names_in_the_source_is_two_tokens(keyline_check, source, rendering):
    # Review 9, A7: the calendar pair rule was applied on the rendering side only.
    assert keyline_check.check(source, rendering).ok


@pytest.mark.parametrize("source, rendering", [
    ("Mon open Monday-Friday", "Mon open Monday to Thursday"),
    ("Mon open Monday-Paris", "Mon open Monday to Paris"),
])
def test_a_calendar_pair_still_needs_both_names(keyline_check, source, rendering):
    assert not keyline_check.check(source, rendering).ok


@pytest.mark.parametrize("source, rendering", [
    ("Due 2026-10-25 today.", "Due 2026-10-25T99 today."),
    ("Due 2026-10-25 today.", "Due 2026-10-25T10:00.bak today."),
    ("Due 2026-10-25 today.", "Due 2026-10-25T10:00/x today."),
])
def test_a_date_inside_a_bad_or_extended_iso_timestamp_is_not_present(keyline_check, source, rendering):
    # Review 9, A9 (2) and A10: the ISO "T" pass skipped the extension check.
    assert keyline_check.check(source, rendering).missing == ["2026-10-25"]


@pytest.mark.parametrize("source, rendering", [
    ("Due 2026-10-25 today.", "Due 2026-10-25T10:00Z today."),
    ("Due 2026-10-25 today.", "Due 2026-10-25T10:00:00+02:00 today."),
    ("Due 2026-10-25 today.", "Due 2026-10-25T10:00Z-2026-10-26T10:00Z today."),
])
def test_a_date_inside_an_iso_timestamp_is_present(keyline_check, source, rendering):
    assert keyline_check.check(source, rendering).ok


@pytest.mark.parametrize("source, rendering", [
    ("Open Monday now", "Open Monday-Paris now"),     # A9 (3): both names must be calendar names
    ("Open Paris now", "Open Monday-Paris now"),
    ("Open Monday now", "Open Paris-Monday now"),
])
def test_a_hyphen_pair_needs_two_calendar_names(keyline_check, source, rendering):
    assert not keyline_check.check(source, rendering).ok


@pytest.mark.parametrize("source, rendering", [
    ("Use sha256 now", "Use sha256/sha512 now"),       # A9 (5): an identifier pairs
    ("Use sha512 now", "Use sha256/sha512 now"),
    ("Use foo_bar now", "Use foo_bar/baz_qux now"),    # A9 (6): a snake_case token pairs
    ("Use baz_qux now", "Use foo_bar/baz_qux now"),
])
def test_identifiers_and_snake_case_tokens_pair(keyline_check, source, rendering):
    assert keyline_check.check(source, rendering).ok


@pytest.mark.parametrize("text", [
    "May, June and July are busy.", "May and June are busy.", "May or June works.",
    "May was busy.", "May is busy.", "May has 31 days.", "May.", "MAY, JUNE AND JULY ARE BUSY.",
    "May to July is busy.",
])
def test_may_as_a_sentence_start_subject_is_the_month(keyline_check, text):
    # Review 9, old #15 neighbour.
    assert keyline_check.hedges(text) == {}, text


@pytest.mark.parametrize("text", ["May I help?", "May we ship?", "May, I ask, we ship?",
                                  "May the tests pass.", "May and should are modals."])
def test_may_as_a_modal_stays_a_hedge(keyline_check, text):
    assert "possibility" in keyline_check.hedges(text), text


@pytest.mark.parametrize("source, rendering", [
    ("Meet Ra̱ndi today", "Meet Ra̱ndo today"),
    ("Meet Ra̱ndi today", "Meet Ra today"),
    ("Ask Q\u0331uinn today", "Ask Q\u0331uinne today"),
    ("Edit fa̱.txt today", "Edit fa̱b.txt today"),
])
def test_a_combining_mark_is_part_of_its_word(keyline_check, source, rendering):
    # Review 9, old #4 residue: a combining mark NFC cannot compose ended the token.
    assert not keyline_check.check(source, rendering).ok
    assert keyline_check.check(source, source).ok


def test_a_hebrew_point_is_still_not_a_word_character(keyline_check):
    assert keyline_check.check("Ship v2.1 today", "שִׁלחו v2.1 הַיום").ok
    assert keyline_check.check("Ship v2.1 today", "בְּv2.1").ok


def test_the_word_classes_match_unicode(keyline_check):
    # The classes are built from part of Unicode only (see _word_classes). A letter, a digit or
    # "_" as re reads them, plus every combining mark that is no word character to re, and no
    # Hebrew letter or point: exactly these, over all assigned characters of Unicode.
    import re
    import unicodedata
    classes = {name: re.compile(getattr(keyline_check, name)) for name in ("LETTER", "ALNUM", "WORD")}
    mark = re.compile(f"[{keyline_check.MARK}]")
    letter, alnum, word = re.compile(r"[^\W\d_]"), re.compile(r"[^\W_]"), re.compile(r"\w")
    for cp in range(0x110000):
        c = chr(cp)
        if cp > 0xFFFF and unicodedata.category(c) == "Cn":
            # An unassigned gap above the BMP may be joined into a range (it keeps the class
            # short); it is no character yet, so it is never a mark.
            assert not mark.match(c), hex(cp)
            continue
        hebrew = "\u0590" <= c <= "\u05ff" or "\ufb1d" <= c <= "\ufb4f"
        # SA3: a variation selector and an enclosing mark (U+20E3) are no part of a word.
        selector = "\ufe00" <= c <= "\ufe0f" or "\U000e0100" <= c <= "\U000e01ef"
        is_mark = (unicodedata.category(c)[0] == "M" and not c.isalnum() and not hebrew
                   and not selector and unicodedata.category(c) != "Me")
        want = {"LETTER": bool(letter.match(c)), "ALNUM": bool(alnum.match(c)), "WORD": bool(word.match(c))}
        for name, pattern in classes.items():
            assert bool(pattern.match(c)) == ((want[name] and not hebrew) or is_mark), (name, hex(cp))
        assert bool(mark.match(c)) == is_mark, hex(cp)


# ---- self-review of the review 9 fixes (SA1-SA9) ----

@pytest.mark.parametrize("source, rendering", [
    ("Ship v2.1,v2.2 now", "Ship v2.1-rc,v2.2 now"),
    ("Set MODE=fast now", "Set MODE-X=fast now"),
    ("Visit Paris,London now", "Visit Paris-Nord,London now"),
    ("Call at 14:30,15:00 now", "Call at 14:30-ish,15:00 now"),
    ("Ship v2.1* now", "Ship v2.1-rc now"),
    ("Call API(x) now", "Call API-v2 now"),
    ("Call **at\n14:30** now", "Call at 14:30:15 now"),
    ("Ship v2.1,v2.2 now", "Ship x-v2.1,v2.2 now"),
])
def test_a_source_token_glued_by_a_joiner_does_not_let_any_extension_pass(keyline_check, source, rendering):
    # SA1: a source token glued by a joiner ("," "=" "*" "(") was "not alone", so any
    # extended rendering of it passed.
    result = keyline_check.check(source, rendering)
    assert not result.ok and result.missing, result
    assert keyline_check.check(source, source).ok
    assert keyline_check.check(rendering, rendering).ok


@pytest.mark.parametrize("source, rendering", [
    ("Ship v2.1,v2.2 now", "Ship v2.1, v2.2 now"),
    ("Ship v2.1,v2.2 now", "שלחו v2.1,v2.2 עכשיו"),
    ("Set MODE=fast now", "הגדירו MODE=fast עכשיו"),
    ("Set MODE=fast now", "Set MODE to fast now"),
    ("Call API(x) now", "Call API (x) now"),
])
def test_a_source_token_glued_by_a_joiner_passes_alone_or_in_the_same_context(keyline_check, source, rendering):
    assert keyline_check.check(source, rendering).ok


@pytest.mark.parametrize("source, rendering", [
    ("Get https://x.io/_api_/v1 now", "Get https://x.io/api/v1 now"),
    ("Get https://x.io/api/v1 now", "Get https://x.io/_api_/v1 now"),
    ("Get https://x.io/*a*/v1 now", "Get https://x.io/a/v1 now"),
    ("Read /srv/_data_/x.txt now", "Read /srv/data/x.txt now"),
    ("Call __init_subclass__ now", "Call init_subclass now"),
    ("Call _private_var_ now", "Call private_var now"),
])
def test_emphasis_marks_inside_a_url_path_or_identifier_are_kept(keyline_check, source, rendering):
    # SA2: _plain() dropped emphasis marks inside URLs, paths and identifiers.
    result = keyline_check.check(source, rendering)
    assert not result.ok and result.missing, result
    assert keyline_check.check(source, source).ok


@pytest.mark.parametrize("source, rendering", [
    ("Got 12 errors", "Got __12__ errors"),                      # SA5: "__12__" is bold
    ("Deploy to Paris now", "Deploy to **_Paris_** now"),
    ("Deploy to Paris now", "פריסה ל-_Paris_ עכשיו"),
])
def test_emphasis_beside_a_token_is_still_dropped(keyline_check, source, rendering):
    assert keyline_check.check(source, rendering).ok, keyline_check.check(source, rendering)


def test_a_dunder_still_starts_with_a_letter(keyline_check):
    assert keyline_check._plain("Call __init_subclass__ and __12__") == "Call __init_subclass__ and 12"


@pytest.mark.parametrize("rendering", ["✅ שוחרר ✔️v2.1 ב-14:30 ל-5️⃣ שרתים", "✔️v2.1 at 14:30 to 5️⃣ hosts"])
def test_a_variation_selector_or_keycap_is_not_part_of_a_word(keyline_check, rendering):
    # SA3: U+FE0F and U+20E3 were in MARK, so "✔️v2.1" and "5️⃣" hid the token.
    assert keyline_check.check("Ship v2.1 at 14:30 to 5 hosts", rendering).ok


def test_emphasis_pairs_across_a_line_but_not_across_a_blank_line(keyline_check):
    # SA4: the pairing was reset at every newline, so multi-line bold kept its marks.
    assert keyline_check._plain("**a\nb**") == "a\nb"
    assert keyline_check._plain("_a\n\nb_") == "_a\n\nb_"
    assert keyline_check._plain("_a\n \t\nb_") == "_a\n \t\nb_"
    assert keyline_check.check("Deploy at 14:30", "**פריסה\nב-14:30**").ok


@pytest.mark.parametrize("text, count", [
    ("I'd say no. 3 fail", 1), ("Fixed? Still no. 5 fail", 1), ("Honestly no. 3", 1),
    ("Ticket no. 5", 1), ("Ticket No. 5", 0), ("TICKET NO. 5", 0), ("Item 3 no. 5", 0),
])
def test_a_lowercase_no_after_a_word_is_a_negation(keyline_check, text, count):
    # SA8: only "No."/"NO." after a word, or "no." after a digit, is a number sign.
    assert keyline_check.negations(text) == count


def test_a_long_calendar_run_is_checked_in_linear_time(keyline_check):
    # SA9: the A4 test used "Ab-", which _pairs short-circuits, so dropping TOKEN_REACH
    # survived; "Monday-" reaches _token_at on every word (226 s unbounded at 20000).
    import time
    start = time.perf_counter()
    keyline_check.check("Open Monday now", "Open " + "Monday-" * 10000 + "Monday now")
    assert time.perf_counter() - start < 15, "quadratic"


@pytest.mark.parametrize("source, rendering", [
    ("Call at 14:30 now", "Call at 14:30:00 now"),
    ("Call at 14:30:00 now", "Call at 14:30 now"),
])
def test_a_time_with_or_without_zero_seconds_is_present(keyline_check, source, rendering):
    # SA9: the order of the forms (with ":00" first) had no test.
    assert keyline_check.check(source, rendering).ok


@pytest.mark.parametrize("source, rendering", [
    ("Due 2026-10-25 today.", "Due 2026-10-25T10:00abc today."),   # SA9: the ISO word check
    ("Open ab.txt now", "Open ab.txt* now"),                         # SA9: "*" always extends
    ("Read /srv/a̱/x now", "Read /srv/a/x now"),                # SA9: a mark in a path
    ("Read /srv/a/x now", "Read /srv/a̱/x now"),
])
def test_guards_without_a_test_of_their_own(keyline_check, source, rendering):
    result = keyline_check.check(source, rendering)
    assert not result.ok and result.missing, result
    assert keyline_check.check(source, source).ok


@pytest.mark.parametrize("text", [
    "/srv/_data_ now", "/srv/*data* now", "x._a_ y", "x:_a_ y", "~_a_ y", "x@_a_ y", "x=_a_ y",
    "x\\_a_ y", "a-_b_ y", "a-*b* y",                      # an opening run glued after these
    "y _data_/x", "y *data*/x", "y _data_\\x", "y *data*\\x",  # a closing run before these
])
def test_a_mark_run_on_one_side_of_a_path_or_word_is_no_emphasis(keyline_check, text):
    # SA2: each guard alone, so a URL or path with emphasis-like marks on one side keeps them.
    assert keyline_check._plain(text) == text


def test_a_mark_run_on_one_side_of_a_path_changes_the_token(keyline_check):
    assert not keyline_check.check("Read /srv/_data_ now", "Read /srv/data now").ok
    assert not keyline_check.check("Read _data_/x.txt now", "Read data/x.txt now").ok


def test_emphasis_after_a_hebrew_prefix_and_dash_is_dropped(keyline_check):
    assert keyline_check._plain("ל-_Paris_ ו-*API*") == "ל-Paris ו-API"
