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


def test_space_separated_timestamp_counts_as_present_in_iso_form(keyline_check):
    # The datetime fix accepted a space for the "T" but not a "T" for the space: a source that
    # writes "2026-10-25 14:30" (a date and a time) failed against an ISO-normalising renderer.
    assert keyline_check.check("Deploy at 2026-10-25 14:30.", "Deploy at 2026-10-25T14:30Z.").ok
    assert keyline_check.check("Deploy at 2026-10-25 14:30.", "Deploy at 2026-10-25T15:30Z.").missing == ["14:30"]
    assert keyline_check.check("Deploy at 2026-10-25 14:30.", "Deploy at 2026-10-26T14:30Z.").missing == ["2026-10-25"]
    assert keyline_check.check("Deploy at 2026-10-25 14:30.", "Deploy at 2026-10-25 14:30.").ok


@pytest.mark.parametrize("tok, longer", [
    ("notes/a.txt", "notes/a.txt.bak"), ("notes/a.txt", "notes/a.txt/"), ("report.pdf", "report.pdf.gpg"),
    ("~/.claude", "~/.claude.bak"), ("build.sh", "build.sh.old"), ("Jean-Luc", "Jean-Luc-Picard"),
    ("API", "API.md"), ("sha256", "sha256.txt"), ("Postgres", "Postgres/Prisma"), ("max_conn", "max_conn.py"),
])
def test_a_path_or_name_is_not_found_inside_a_longer_one(keyline_check, tok, longer):
    # Only numbers were looked up by extraction; every other kind used the right boundary R,
    # which lets ".bak", "-Picard" or a trailing "/" follow, so a changed path or name passed.
    src, ren = f"see {tok} at 14:02", f"see {longer} at 14:02"
    assert keyline_check.check(src, ren).missing == [tok]
    assert keyline_check.check(src, src).ok


@pytest.mark.parametrize("src, ren", [
    ("tests sit in __tests__/ next to src", "טסטים יושבים ב-__tests__/ ליד המקור"),
    ("fix billing.spec.ts at 14:02", "לתקן ב-billing.spec.ts ב-14:02"),
    ("see notes/a.txt at 14:02", "ראה בnotes/a.txt ב-14:02"),
    ("db: moved to Postgres at 14:02", "Postgres הוא הבסיס מ-14:02"),
    ("db: moved to Postgres at 14:02", "ב-14:02 עברנו. Postgres נשאר."),
    ("stack: Postgres via Prisma", "Postgres through Prisma"),
])
def test_a_hebrew_prefix_or_a_sentence_start_still_counts_for_a_path_or_name(keyline_check, src, ren):
    # Lookup by extraction must not lose what the boundary lookup had: a Hebrew prefix glued to
    # a path or file ("ב-__tests__/"), and a name the rendering moves to a sentence start.
    result = keyline_check.check(src, ren)
    assert result.ok, result.missing


@pytest.mark.parametrize("digest", ["3b4ca1f2" * 8, "ab4ca1f2" * 8, "3b4ca1f2" * 16])
def test_a_long_hex_digest_is_one_invariant(keyline_check, digest):
    # The hash alternative was capped at 40 hex digits (git SHA-1), so a sha256 or sha512 digest
    # that starts with a digit matched nothing and a changed digest passed.
    source = f"artifact sha256: {digest} at 14:02"
    assert keyline_check.invariants(source)[digest] == "hash"
    changed = source.replace(digest, digest[:-1] + ("0" if digest[-1] != "0" else "1"))
    assert keyline_check.check(source, changed).missing == [digest]
    assert keyline_check.check(source, source).ok


@pytest.mark.parametrize("name", ["Zürich", "Léa", "Øyvind", "São", "Café", "Łukasz"])
def test_a_name_with_a_diacritic_is_a_proper_noun(keyline_check, name):
    # The proper alternative and the boundary R were ASCII-only, so "Zürich" was not a name
    # (and "Café" gave "Caf"); a rendering that swapped the name passed.
    source = f"Meeting at 10:00 in {name} with Bob"
    assert keyline_check.invariants(source)[name] == "proper"
    assert "Caf" not in keyline_check.invariants(source)
    assert keyline_check.check(source, source.replace(name, "Paris")).missing == [name]
    assert keyline_check.check(source, source).ok


@pytest.mark.parametrize("english, hebrew", [("OCTOBER", "באוקטובר"), ("MONDAY", "ביום שני"), ("SATURDAY", "בשבת")])
def test_an_all_caps_month_or_weekday_accepts_its_hebrew_form(keyline_check, english, hebrew):
    # The Hebrew form was accepted for a capitalised name or "MAY" only; "DEC" and "SAT" are
    # acronyms, but a full name in capitals is the month or the day.
    source = f"Due {english} 3 at 14:02"
    assert keyline_check.check(source, f"יעד {hebrew} 3 ב-14:02").ok
    assert keyline_check.check(source, "יעד 3 ב-14:02").missing == [english]
    assert keyline_check.check("code: DEC at 14:02", "קוד: דצמבר ב-14:02").missing == ["DEC"]


def test_a_year_that_starts_a_sentence_is_a_number(keyline_check):
    # LIST_MARKER stripped "2024. " as a numbered item, so the year went missing.
    assert keyline_check.invariants("2024. Migration done") == {"2024": "number"}
    assert keyline_check.check("2024. Migration done", "2025. Migration done").missing == ["2024"]
    assert keyline_check.invariants("1. first\n12. twelfth\n123. last\n") == {}


def test_a_url_keeps_its_scheme(keyline_check):
    # A URL was extracted as the path "//example.com/a/b", so "https" -> "http" passed.
    source = "see https://example.com/a/b?x=1 at 14:02"
    assert keyline_check.invariants(source)["https://example.com/a/b?x=1"] == "url"
    assert keyline_check.check(source, source.replace("https", "http")).missing == ["https://example.com/a/b?x=1"]
    assert keyline_check.check(source, "ראה https://example.com/a/b?x=1 ב-14:02").ok
    assert keyline_check.check(source, "ראה (https://example.com/a/b?x=1), ב-14:02").ok
    assert keyline_check.check(source, source).ok
    # Sentence punctuation after a URL is not part of it: a rendering that drops the colon, the
    # question mark or the exclamation mark after "https://x.y/z" used to fail with the URL missing.
    for src, ren in (("see https://x.y/z: the docs", "ראה https://x.y/z - המסמכים"),
                     ("did you read https://x.y/z?", "האם קראת את https://x.y/z"),
                     ("read https://x.y/z!", "קרא https://x.y/z")):
        assert keyline_check.invariants(src) == {"https://x.y/z": "url"}, src
        assert keyline_check.check(src, ren).ok, src


def test_number_sign_no_is_not_a_negation(keyline_check):
    # "No. 5" counted as a negation, so a Hebrew rendering "מס' 5" failed with "1 lost".
    assert keyline_check.negations("ticket No. 5") == 0
    assert keyline_check.negations("ticket no.5 and No.  7") == 0
    assert keyline_check.negations("no 5xx errors, no data lost. No.") == 3
    assert keyline_check.check("ticket No. 5 at 14:02", "כרטיס מס' 5 ב-14:02").ok
    # "no." ends the sentence; a numbered item, a date or a time on the next line is not "No. 5".
    assert keyline_check.negations("Data lost: no.\n1. Restart") == 1
    assert keyline_check.negations("Rollback needed: no.\n2026-10-25 follow-up") == 1
    assert keyline_check.negations("Answer: no.\n10:00 standup") == 1
    assert not keyline_check.check("Data lost: no.\n1. Restart the pod at 14:02",
                                   "נתונים אבדו: כן.\n1. הפעל מחדש את הפוד ב-14:02").ok


def test_month_label_may_is_not_a_hedge(keyline_check):
    # A line-leading label "May:" was a possibility hedge while "מאי:" is not.
    assert keyline_check.hedges("May: ship v2") == {}
    assert keyline_check.hedges("MAY: SHIP V2") == {}
    assert keyline_check.check("May: ship v2", "מאי: לשלוח v2").ok
    assert keyline_check.hedges("May we proceed?") == {"possibility": ["may"]}


# Each case has a short id: pytest puts the id in an environment variable, which Windows caps at
# 32767 characters, and the 32000-character inputs themselves broke the run there.
@pytest.mark.parametrize("unit, count, tail", [
    ("Zé", 16000, "_"), ("Zé", 16000, ".5"), ("Éé", 16000, ".5"), ("ÉÉ", 8000, ".5"),
    ("ÉCOLE", 4000, "_"), ("ס", 16000, "_"), ("ס", 16000, ".5"), ("סZ", 8000, "_"), ("Zס", 8000, "_"),
    ("ÉCOLE", 4000, "/x"), ("ס", 16000, "/x"),
    ("1.", 16000, "1_"), ("1.", 16000, "1é"), ("aA", 16000, "_"), ("aA", 16000, "é"),
], ids=lambda v: str(v))
def test_a_long_diacritic_or_hebrew_run_is_extracted_in_linear_time(keyline_check, unit, count, tail):
    text = unit * count + tail
    # The left boundary L stayed ASCII when the name rule and R took Latin diacritics, so every
    # capital after a diacritic was a start and each start rescanned to the end of the run:
    # 16000 "Zé" pairs before "_" took 24 s against the hook's 30 s budget. A Hebrew letter
    # opens a file name or path only when no Hebrew letter precedes it, for the same reason.
    # A dotted digit run before "_" or "é" ("1.1.1...1_") was rescanned by the version and
    # number rules from every digit after a ".", and a lower-upper letter run ("aAaA...aA_") by
    # the CamelCase rule from every pair: 16000 pairs took 54 s and 9.7 s.
    import time
    start = time.perf_counter()
    keyline_check.invariants(text)
    assert time.perf_counter() - start < 2.0


def test_a_token_does_not_start_after_a_diacritic(keyline_check):
    # "the ÉCOLE" gave the identifier "COLE" and "école/notes.txt" the path "cole/notes.txt", so
    # a rendering holding the cut token passed.
    assert "COLE" not in keyline_check.invariants("the ÉCOLE at 14:02")
    assert keyline_check.check("the ÉCOLE at 14:02", "the COLE at 14:02").missing == ["ÉCOLE"]
    assert keyline_check.invariants("file école/notes.txt at 14:02") == {"école/notes.txt": "path", "14:02": "time"}
    assert keyline_check.check("file école/notes.txt at 14:02", "file cole/notes.txt at 14:02").missing == ["école/notes.txt"]
    assert keyline_check.invariants("at ZürichAirport by 14:02") == {"ZürichAirport": "proper", "14:02": "time"}
    assert keyline_check.invariants("at xZürichAirport by 14:02") == {"14:02": "time"}   # not "richAirport"


@pytest.mark.parametrize("src, ren, kind", [
    ("see סיכום.md at 14:02", "see טיוטה.md at 14:02", "file"),
    ("see תיקיה/קובץ.txt at 14:02", "see אחר/קובץ.txt at 14:02", "path"),
    ("see Übersicht.md at 14:02", "see Übersicht.txt at 14:02", "file"),
    ("see école/notes.txt at 14:02", "see lycée/notes.txt at 14:02", "path"),
    ("see Łódź/plan.md at 14:02", "see Łódź/plan.txt at 14:02", "path"),
])
def test_a_file_name_or_path_may_start_with_a_hebrew_or_latin_letter(keyline_check, src, ren, kind):
    # The first-character class of a path or file name went ASCII with the linear-time fix, so
    # "סיכום.md" was not extracted and "תיקיה/קובץ.txt" became "/קובץ.txt": a swapped name passed.
    tok = src.split()[1]
    assert keyline_check.invariants(src)[tok] == kind
    assert keyline_check.check(src, ren).missing == [tok]
    assert keyline_check.check(src, src).ok


def test_a_hebrew_prefix_glued_to_a_latin_name_or_path_still_yields_it(keyline_check):
    # A Hebrew letter opens a name only when it is not glued to a Latin letter or digit: the
    # prefix ב in "בnotes/a.txt" and "בZürich" is not part of the token.
    assert keyline_check.invariants("ראה בnotes/a.txt ב-14:02")["notes/a.txt"] == "path"
    assert keyline_check.invariants("ראה בÜbersicht.md ב-14:02")["Übersicht.md"] == "file"
    assert keyline_check.invariants("נפגשנו בZürich ב-14:02", names_at_sentence_start=True)["Zürich"] == "proper"
    assert keyline_check.check("see notes/a.txt at 14:02", "ראה בnotes/a.txt ב-14:02").ok
    assert keyline_check.invariants("טסטים ב-__tests__/ ו-billing.spec.ts") == {"__tests__/": "path", "billing.spec.ts": "file"}
    assert keyline_check.invariants("ראה תיקיה-ישנה/קובץ.txt")["תיקיה-ישנה/קובץ.txt"] == "path"
    # A Hebrew prefix glued to a Hebrew name is one token to the extractor (documented limit):
    # the source's "סיכום.md" is not in "בסיכום.md", so the check fails closed.
    assert keyline_check.invariants("ראה בסיכום.md ב-14:02")["בסיכום.md"] == "file"
    assert keyline_check.check("see סיכום.md at 14:02", "ראה בסיכום.md ב-14:02").missing == ["סיכום.md"]


def test_a_month_at_a_line_end_before_a_number_on_the_next_line(keyline_check):
    # "May" followed by a digit is the month only on the same line; a line break ends the
    # sentence, as it does for "no." (the \s+ crossed it).
    assert keyline_check.hedges("May 5 is the date.") == {}
    assert keyline_check.hedges("Costs may\n5 items") == {"possibility": ["may"]}
    assert keyline_check.hedges("May\n5 items be removed?") == {"possibility": ["may"]}


def test_added_fractional_seconds_and_a_kept_zone_in_the_iso_form(keyline_check):
    # A time written as two tokens is present in an ISO timestamp that adds milliseconds
    # (JavaScript's toISOString), as it already was in one that adds "Z"; a dropped zone suffix
    # is a lost fact and stays a miss.
    assert keyline_check.check("Deploy at 2026-10-25 14:30:00.", "Deploy at 2026-10-25T14:30:00.000Z.").ok
    assert keyline_check.check("Deploy at 2026-10-25 14:30.", "Deploy at 2026-10-25T14:30:00.000Z.").ok
    assert keyline_check.check("Deploy at 2026-10-25T14:30Z.", "Deploy at 2026-10-25 14:30.").missing == ["2026-10-25T14:30Z"]
    assert keyline_check.check("Deploy at 2026-10-25T14:30.", "Deploy at 2026-10-25 14:30.").ok
    assert keyline_check.check("at 2026-10-25T14:30:00Z.", "at 2026-10-25T14:30:00.000Z.").ok
    assert keyline_check.check("at 2026-10-25T14:30.", "at 2026-10-25T14:30Z.").ok
    assert keyline_check.check("at 2026-10-25T14:30:00.250Z", "at 2026-10-25T14:30:00Z").missing == ["2026-10-25T14:30:00.250Z"]
    assert keyline_check.check("at 2026-10-25T14:30+02:00", "at 2026-10-25 14:30Z").missing == ["2026-10-25T14:30+02:00"]
    assert keyline_check.invariants("at 14:30:00.250Z") == {"14:30:00.250Z": "time"}
    assert keyline_check.check("at 14:30:00.250Z", "at 14:30:00Z").missing == ["14:30:00.250Z"]


@pytest.mark.parametrize("name", ["ÉCOLE", "NGUYỄN", "ZÜRICH", "SÃO_PAULO"])
def test_an_all_caps_name_with_a_diacritic_is_an_identifier(keyline_check, name):
    # The upper rule was ASCII-only and the name rule wants a lowercase tail, so "ÉCOLE" and
    # "NGUYỄN" were nothing (or the cut "COLE"); a rendering that swapped them passed.
    source = f"Meeting at 10:00 at {name} with Bob"
    assert keyline_check.invariants(source)[name] == "upper"
    assert keyline_check.check(source, source.replace(name, "PARIS")).missing == [name]
    assert keyline_check.check(source, source).ok


@pytest.mark.parametrize("tok", ["É", "Ó", "Ås"])
def test_a_lone_capital_letter_with_a_diacritic_is_not_an_identifier(keyline_check, tok):
    assert keyline_check.invariants(f"Then {tok} went home.") == {}


def test_an_all_caps_line_may_hold_a_diacritic_word(keyline_check):
    # "MAY PARIS" is a modal in an all-caps line; so is "MAY ÉCOLE" (and "May école" is the month).
    assert keyline_check.hedges("WE MAY PARIS") == {"possibility": ["may"]}
    assert keyline_check.hedges("MAY ÉCOLE") == {"possibility": ["may"]}
    assert keyline_check.hedges("MAY école") == {}


@pytest.mark.parametrize("src, ren", [
    ("at 2026-10-25T14:30Z", "at 2026-10-25T14:30:00Z"),
    ("at 2026-10-25T14:30Z", "at 2026-10-25T14:30:00.000Z"),
    ("at 2026-10-25T14:30+02:00", "at 2026-10-25T14:30:00+02:00"),
    ("at 2026-10-25T14:30:00Z", "at 2026-10-25 14:30:00.000Z"),
    ("at 14:30:00Z", "at 14:30:00.000Z"),
    ("at 14:30Z", "at 14:30:00Z"),
    ("at 14:30Z", "at 14:30:00.000Z"),
    ("at 14:30Z", "at 2026-10-25T14:30:00.000Z"),
    ("window 14:30:00Z", "חלון 14:30:00.000Z"),
])
def test_a_rendering_may_add_seconds_or_a_fraction_before_a_zone_the_source_has(keyline_check, src, ren):
    # The lookup appended the source's zone straight after its clock, so "14:30Z" was not found
    # in "14:30:00Z", and the time kind took a fraction only when the token had no zone, so
    # "14:30:00Z" was not found in "14:30:00.000Z" (the datetime kind already did).
    result = keyline_check.check(src, ren)
    assert result.ok, result.missing


@pytest.mark.parametrize("src, ren", [
    ("at 14:30Z", "at 14:30:00"),
    ("at 14:30Z", "at 14:30:00.000+02:00"),
    ("at 14:30:00Z", "at 14:30:00.000"),
    ("at 14:30:00.250Z", "at 14:30:00Z"),
    ("at 14:30:00.250", "at 14:30:00"),
    ("at 2026-10-25T14:30Z", "at 2026-10-25T14:30:00"),
    ("at 2026-10-25T14:30Z", "at 2026-10-25T14:30:00.000+02:00"),
    ("at 2026-10-25T14:30:00.250Z", "at 2026-10-25T14:30:00Z"),
    ("at 2026-10-25T14:30+02:00", "at 2026-10-25T14:30:00Z"),
])
def test_a_dropped_or_changed_zone_or_fraction_is_still_a_miss(keyline_check, src, ren):
    tok = src.split()[1]
    assert keyline_check.check(src, ren).missing == [tok]


@pytest.mark.parametrize("pair", ["yes/no", "and/or", "él/ella", "sim/não", "כן/לא", "oui/non", "sí/no"])
def test_a_slash_between_two_plain_words_in_any_script_is_prose(keyline_check, pair):
    # The prose exception of the path rule ("and/or" is not a path) matched ASCII lowercase
    # only while the path start took Latin letters with diacritics and Hebrew, so "él/ella",
    # "sim/não" and "כן/לא" were paths that a translated rendering could not hold.
    src = f"answer: {pair} at 14:02"
    assert keyline_check.invariants(src) == {"14:02": "time"}
    assert keyline_check.check(src, "תשובה: כן/לא ב-14:02").ok      # "לא" keeps the negation count
    assert keyline_check.check(src, "answer: yes/no at 14:02").ok


@pytest.mark.parametrize("path", [
    "notes/a.txt", "תיקיה/קובץ.txt", "école/notes.txt", "כן/לא.txt", "a1/b", "a_b/c", "a-b/c",
    "a/b/c", "src/lib.rs", "él/ella1", "sim/não_x", "כן/לא/x", "Yes/No",
])
def test_a_real_path_is_still_a_path(keyline_check, path):
    # The exception is one slash between two plain words: a dot, a digit, an underscore, a dash,
    # a capital or a second slash keeps the token a path.
    src = f"see {path} at 14:02"
    assert keyline_check.invariants(src)[path] == "path"
    assert keyline_check.check(src, src.replace(path, "x/y.z")).missing == [path]
    assert keyline_check.check(src, src).ok
    # A two-word lowercase path with no dot ("src/lib") is prose to the extractor, as documented.
    assert keyline_check.invariants("see src/lib at 14:02") == {"14:02": "time"}


@pytest.mark.parametrize("src, ren", [
    ("## May\n5 PRs merged at 14:02", "## מאי\n5 PRs מוזגו ב-14:02"),
    ("May\n5 PRs merged at 14:02", "מאי\n5 PRs מוזגו ב-14:02"),
    ("**May**\n5 PRs merged at 14:02", "**מאי**\n5 PRs מוזגו ב-14:02"),
    ("- May\n5 PRs merged at 14:02", "- מאי\n5 PRs מוזגו ב-14:02"),
    ("> May\n5 PRs merged at 14:02", "> מאי\n5 PRs מוזגו ב-14:02"),
    ("## May\nnothing shipped at 14:02", "## מאי\nכלום לא נשלח ב-14:02"),
    ("# MAY\n5 PRs merged at 14:02", "# מאי\n5 PRs מוזגו ב-14:02"),
    ("## May\n5 PRs merged?\nYes, at 14:02.", "## מאי\n5 PRs מוזגו?\nכן, ב-14:02."),
    ("Q3\n\nMay\n5 PRs merged at 14:02", "Q3\n\nמאי\n5 PRs מוזגו ב-14:02"),
])
def test_a_may_that_is_the_whole_content_of_its_line_is_the_month(keyline_check, src, ren):
    # A heading "## May" (or "May" alone on a line) before a line that starts with a digit was
    # a possibility hedge once a digit on the next line no longer named the day, so a monthly
    # notes file failed against its Hebrew rendering with "hedges lost".
    assert keyline_check.hedges(src) == {}, src
    result = keyline_check.check(src, ren)
    assert result.ok, (result.missing, result.missing_hedges)


def test_a_bare_may_line_that_opens_a_question_is_the_modal(keyline_check):
    # Without heading or label furniture a "May" line is the modal when the sentence it opens
    # ends in a question mark ("May\n5 items be removed?"); with furniture it is the month.
    assert keyline_check.hedges("May\n5 items be removed?") == {"possibility": ["may"]}
    assert keyline_check.hedges("May\nwe proceed?") == {"possibility": ["may"]}
    assert keyline_check.hedges("May\n5 PRs merged? Yes.") == {"possibility": ["may"]}
    assert keyline_check.hedges("May\n5 PRs merged. Yes?") == {}
    assert keyline_check.hedges("May\n\nWhy?") == {}
    assert keyline_check.hedges("## May\n5 PRs merged?") == {}
    assert keyline_check.hedges("May:\n5 PRs merged?") == {}


@pytest.mark.parametrize("tok, kind", [
    ("fooBar", "camel"), ("FooBar", "camel"), ("ABcD", "camel"), ("getHTTP2", "camel"), ("aB", "camel"),
    ("aAaAaA", "camel"), ("ABc", None), ("Abc", "proper"), ("ABC", "upper"), ("ab1", "ident"),
])
def test_camel_case_shapes_after_the_linear_rule(keyline_check, tok, kind):
    # The CamelCase rule now tries one split per letter run (leading capitals, one lowercase
    # run, a capital) instead of one per lower-upper pair; it takes the same tokens ("ABc",
    # with no lower-upper pair, is nothing, as before).
    assert keyline_check.invariants(f"use {tok} at 14:02").get(tok) == kind
    assert keyline_check.invariants("use aAaA_ at 14:02") == {"14:02": "time"}


@pytest.mark.parametrize("tok, kind, changed", [
    ("Python3.12", "proper", "Python3.11"), ("python3.12", "ident", "python3.11"),
    ("GPT4.5", "upper", "GPT4.1"), ("getHTTP2.1", "camel", "getHTTP2.2"),
    ("my_lib1.5", "snake", "my_lib1.6"), ("abcdef1.5", "hash", "abcdef1.6"), ("Fig.3", "proper", "Fig.4"),
])
def test_a_name_glued_to_a_dotted_number_is_one_token(keyline_check, tok, kind, changed):
    # A name ending in a digit may continue with ".<digits>" ("Python3.12", "python3.12",
    # "GPT4.5"): the whole is one token, as "v2.14.0" is. Before the version and number rules
    # stopped starting after "<digit>." (the linear-time fix), only the part after the dot was
    # extracted, by accident; after it, nothing was, so a swapped "Python3.12" passed.
    source = f"use {tok} at 14:02"      # not at a sentence start, where a proper noun is furniture
    assert keyline_check.invariants(source).get(tok) == kind
    result = keyline_check.check(source, source.replace(tok, changed))
    assert not result.ok and result.missing == [tok]
    # A name before sentence punctuation or a spaced number is unchanged.
    assert keyline_check.invariants("use Python3. 5 users") == {"Python3": "proper", "5": "number"}
    # The dotted tail is scanned once per name, not once per dot.
    import time
    start = time.perf_counter()
    assert keyline_check.invariants("Python3" + ".1" * 16000 + "_") == {}
    assert time.perf_counter() - start < 2.0
