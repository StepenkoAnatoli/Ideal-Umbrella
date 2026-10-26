"""keyline_check.py - deterministic fact check between a source note and a rendering of it.

Extracts every date, timestamp, time, version, URL, number, percentage, UPPER_CASE identifier,
file path, CamelCase name, proper noun, file name, snake_case token, hex hash and lowercase
identifier with digits (sha256, utf8) from SOURCE and fails if any is missing from a RENDERING (English prose,
Hebrew, JSON, markdown...). A month or weekday name may appear in its Hebrew form. Also fails if
the rendering drops a hedge class (could/may, likely, should, can; English or Hebrew words) or
has fewer negation words than the source. A source with no extractable invariant and no hedge
is INCONCLUSIVE, never PASS.

Usage:
  python keyline_check.py SOURCE RENDERING [RENDERING ...]
  python keyline_check.py --list SOURCE          print what would be checked
Exit: 0 all renderings pass, 1 any rendering fails or is inconclusive, 2 usage or read error.
"""
import re
import sys
from dataclasses import dataclass

# Latin letters with diacritics (Zürich, Léa, Øyvind, São, Łukasz): part of a name, and a
# token does not end before one ("Caf" is not in "Café").
LATIN = "".join(c for c in map(chr, [*range(0xC0, 0x250), *range(0x1E00, 0x1F00)]) if c.isalpha())
LATIN_UPPER = "".join(c for c in LATIN if c.isupper())
LATIN_LOWER = "".join(c for c in LATIN if c.islower())
HEB = "א-ת"
# A token boundary on ASCII word characters and those Latin letters, so a Hebrew prefix glued to
# an identifier ("בv2.14.0") still counts as present, while "5" never matches inside "503" or
# "2.5" and no token starts inside a word ("COLE" in "ÉCOLE"). L and R take the same letters: a
# start that L lets through after a diacritic would rescan a run from every capital in it.
L = rf"(?<![A-Za-z0-9_{LATIN}])"
R = rf"(?![A-Za-z0-9_{LATIN}]|\.\d)"
# A path or file name may also start at a Hebrew letter ("סיכום.md", "תיקיה/קובץ.txt"), but only
# at the first letter of its word, so a long Hebrew run has one start and not one per letter,
# and only when no Latin letter, digit or dash follows it, so the prefix of "בnotes/a.txt" and
# "ב-__tests__/" stays out of the path. A Hebrew prefix glued to a Hebrew name ("בסיכום.md") is
# one token to the extractor: the source's "סיכום.md" is not in it, and the check fails closed.
HEB_START = rf"(?<![{HEB}])[{HEB}](?![A-Za-z0-9_{LATIN}-])"
# Every kind but a date, a time and a timestamp is looked up by extraction, not by a boundary:
# "10" is present when the rendering's own invariants hold "10" as a token, so it is not found
# inside "10:00", "2,500", "10%", "10/25" or the date "2026-10-25" (each one token to the
# extractor), while both ends of the range "5-10", the year range "2020-2024" and "10" in
# "ב-10" are (each a token of its own); likewise "notes/a.txt" is not in "notes/a.txt.bak" or
# "notes/a.txt/", "Jean-Luc" not in "Jean-Luc-Picard", "API" not in "API.md". Whatever the
# extractor takes from a source line it takes from the same line in a rendering, so a
# rendering holding the source verbatim always passes. A number glued to a path separator
# ("10/", "/10", "10\\") is a path, as "notes/" is: the source's "10" is not in it. A path or
# file name starts at a word character, "." or "~", never at a dash or at a Hebrew letter glued
# to a Latin one, so "ב-__tests__/" and "בnotes/a.txt" hold the source's path. A date, a time
# and a timestamp keep a boundary lookup because they have two spellings: "2026-10-25 14:30"
# is the instant "2026-10-25T14:30", so a date may be followed by "T" and a digit, and a time
# preceded by a date and "T", and followed by fractional seconds and "Z" the rendering adds.
# For a time: "00:30" is not present at the end of "10:00:30".
L_TIME = L + r"(?<!\d:)"
# The parts of a timestamp token, for the lookup: date, clock, fractional seconds, zone.
DATETIME = re.compile(r"(\d{4}-\d{2}-\d{2})T(\d{1,2}:\d{2}(?::\d{2})?)(\.\d+)?(Z|[+-]\d{2}:?\d{2})?")


# The path and file alternatives look ahead for a "/" or "." through the dash-joined words that
# follow; the bound on that look-ahead (200 characters) keeps a long run ("ab-cd-ab-cd-...")
# from costing a rescan of the whole rest of the run from every word in it. A path component or
# file name longer than that is not extracted as one token. A time does not start after "N:",
# so "3:1:30" is the numbers 3, 1 and 30, not the time "1:30" (which the lookup, bounded the
# same way, would never find). A URL keeps its scheme (at most 31 characters, so a dash-joined
# run is not rescanned for "://" from every word) and runs to whitespace or a closing quote,
# bracket or separator. A hash is 7 to 128 hex digits (git SHA-1 to sha512) with at
# least one letter and one digit. The CamelCase, snake_case, hash and identifier rules stay
# ASCII: the CamelCase rule rescans a letter run from every lower-upper pair, which a run of
# diacritics would make quadratic ("ZürichAirport" is not extracted; neither is "richAirport").
INVARIANT = re.compile(
    L
    + r"""(?:
      (?P<datetime>\d{4}-\d{2}-\d{2}T\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)
    | (?P<date>\d{4}-\d{2}-\d{2})
    | (?P<time>(?<!\d:)\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?Z?)
    | (?P<version>v\d+(?:\.\d+)*|\d+\.\d+\.\d+(?:\.\d+)*)
    | (?P<url>[A-Za-z][A-Za-z0-9+.-]{0,30}://[^\s<>"'`()\[\]{},;|*]+)
    | (?P<path>(?:[A-Za-z]:)?(?:(?:[A-Za-z0-9_.~""" + LATIN + r"""]|""" + HEB_START + r""")[\w.~-]{0,199})?[/\\][\w.~/\\-]*)
    | (?P<file>(?:[A-Za-z0-9_""" + LATIN + r"""]|""" + HEB_START + r""")[\w-]{1,199}(?:\.[A-Za-z][A-Za-z0-9]*)+)
    | (?P<upper>[A-Z""" + LATIN_UPPER + r"""][A-Z0-9""" + LATIN_UPPER + r"""]*(?:_[A-Z0-9""" + LATIN_UPPER + r"""]+)*s?)
    | (?P<camel>[A-Za-z]*[a-z][A-Z][A-Za-z0-9]*)
    | (?P<proper>[A-Z""" + LATIN_UPPER + r"""][a-z""" + LATIN_LOWER + r"""][A-Za-z0-9""" + LATIN + r"""]*
                 (?:-[A-Za-z0-9""" + LATIN + r"""]+|'(?!s(?![A-Za-z0-9""" + LATIN + r"""]))[A-Za-z0-9""" + LATIN + r"""]+)*)
    | (?P<snake>_*[A-Za-z0-9]+(?:_+[A-Za-z0-9]+)+_*|__[a-z0-9]+__)
    | (?P<hash>(?=[0-9a-f]*[a-f])(?=[0-9a-f]*\d)[0-9a-f]{7,128})
    | (?P<number>0[xX][0-9a-fA-F]+|\d+(?:[.,]\d+)*(?:[eE][-+]?\d+)?(?:%|[A-Za-z]+)?)
    | (?P<ident>[a-z]+\d[A-Za-z0-9]*)
)"""
    + R,
    re.X,
)
# "A", "I", "As", "É", "Ó": a letter, not an identifier ("S3", "A1" are).
LONE_LETTER = re.compile(rf"[A-Z{LATIN_UPPER}]s?")

# Capitalized words that are sentence furniture or ordinary prose, not names. The proper-noun
# rule deliberately skips the first word of a line/sentence and these words everywhere else.
PROPER_STOP = {
    "a", "about", "add", "after", "alert", "all", "an", "and", "as", "at", "before", "by",
    "call", "check", "checkout", "commit", "conventions", "database", "delete", "deployment",
    "during", "each", "error", "every", "fix", "for", "framework", "fresh", "from", "get",
    "impact", "in", "incident", "it", "its", "keep", "language", "last", "long", "make",
    "migrate", "missing", "more", "most", "new", "next", "no", "note", "notes", "on", "on-call", "one",
    "open", "or", "project", "read", "remove", "replace", "report", "rollback", "root",
    "roughly", "run", "set", "short", "side", "stack", "start", "stop", "summary", "tests",
    "that", "the", "these", "this", "those", "three", "timeline", "to", "two", "update",
    "use", "verify", "when", "while", "with", "without", "write", "yes",
    # label values ("**Status:** Done", "Priority: High") a rendering translates
    "active", "blocked", "closed", "done", "high", "low", "medium", "none", "pending", "ready",
}

# Markdown list markers carry no fact; "1. Add ..." must not make "1" an invariant.
# The marker's item follows on the same line: "10." alone on a line is the number 10, not a marker.
# A marker has at most three digits: "2024. Migration done" starts with the year.
LIST_MARKER = re.compile(r"^[ \t]*(?:\d{1,3}[.)]|[-*+])[ \t]+", re.M)

# A month or weekday name is an invariant like any proper noun, and a Hebrew rendering may write
# it in Hebrew: either the English token or one of these forms counts as present.
CALENDAR = {
    "january": ("ינואר",), "february": ("פברואר",), "march": ("מרץ", "מארס"), "april": ("אפריל",),
    "may": ("מאי",), "june": ("יוני",), "july": ("יולי",), "august": ("אוגוסט",),
    "september": ("ספטמבר",), "october": ("אוקטובר",), "november": ("נובמבר",), "december": ("דצמבר",),
    "sunday": ("יום ראשון",), "monday": ("יום שני",), "tuesday": ("יום שלישי",),
    "wednesday": ("יום רביעי",), "thursday": ("יום חמישי",), "friday": ("יום שישי",), "saturday": ("שבת",),
}
for _abbr, _full in (("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"),
                     ("jun", "june"), ("jul", "july"), ("aug", "august"), ("sep", "september"),
                     ("sept", "september"), ("oct", "october"), ("nov", "november"), ("dec", "december"),
                     ("sun", "sunday"), ("mon", "monday"), ("tue", "tuesday"), ("tues", "tuesday"),
                     ("wed", "wednesday"), ("thu", "thursday"), ("thur", "thursday"), ("thurs", "thursday"),
                     ("fri", "friday"), ("sat", "saturday")):
    CALENDAR[_abbr] = CALENDAR[_full]

# English: the specified list (no, not, never, without, none) plus "cannot" and n't contractions,
# so a prose rendering that writes "doesn't" for "does not" is not reported as a lost negation.
# "No. 5" is a number sign (מס' 5 in Hebrew), not a negation; "no 5xx errors" still is one, and
# so is "no." at the end of a line, whatever number the next line starts with.
NEG_EN = re.compile(r"\b(?:no(?!\.[ \t]*\d)|not|never|without|none|cannot)\b|\b[A-Za-z]+n't\b", re.I)
# Hebrew: the specified list (לא, אין, ללא, אף, מעולם) plus the conjunction prefixes ו/ש/וש/כש on
# לא/אין/ללא and the inflected forms of אין, which Hebrew prose uses constantly (שלא, ולא, אינו).
NEG_HE = re.compile(
    rf"(?<![{HEB}])(?:"
    rf"(?:ו|ש|וש|כש)?(?:לא|אין|ללא)"
    rf"|אינו|אינה|אינם|אינן|אינני|איננו|אינך"
    rf"|אף|מעולם"
    rf")(?![{HEB}])"
)

# A hedge must survive as a class, not word-for-word: "could" may become "may", but not "will".
# A Hebrew rendering keeps the class with the Hebrew words of the same group.
HEDGE_GROUPS = {
    "possibility": ("could", "may", "might", "possibly", "perhaps", "maybe"),
    "probability": ("likely", "probably", "presumably"),
    "obligation": ("should", "ought", "must"),
    "ability": ("can", "cannot", "able"),
}
HEDGE_GROUPS_HE = {
    "possibility": ("עלול", "עלולה", "עלולים", "עלולות", "עשוי", "עשויה", "עשויים", "עשויות",
                    "ייתכן", "יתכן", "אולי", "אפשרי"),
    "probability": ("כנראה", "סביר", "ככל הנראה", "מן הסתם"),
    "obligation": ("צריך", "צריכה", "צריכים", "צריכות", "חייב", "חייבת", "חייבים", "חייבות",
                   "אמור", "אמורה", "אמורים", "אמורות", "מוכרח"),
    "ability": ("יכול", "יכולה", "יכולים", "יכולות", "ניתן", "אפשר", "מסוגל", "מסוגלת"),
}
HEDGE = re.compile(r"\b(?:" + "|".join(w for words in HEDGE_GROUPS.values() for w in words) + r")\b", re.I)
HEDGE_HE = {
    group: re.compile(rf"(?<![{HEB}])(?:ו|ש|וש|כש)?(?P<word>" + "|".join(map(re.escape, words)) + rf")(?![{HEB}])")
    for group, words in HEDGE_GROUPS_HE.items()
}

BOUNDARY = ".?!\n"


def _is_sentence_start(text, start):
    """True when only whitespace, a sentence end or a line-leading marker ("## ", "> ", "**")
    separates this token from a line or sentence edge. A dash or ">" mid-line is a separator
    ("Postgres - Prisma"), not a marker: the word after it is checked."""
    i = start - 1
    while i >= 0 and text[i] in " \t":
        i -= 1
    if i < 0:
        return True
    if text[i] in BOUNDARY:
        return True
    if text[i] in "-*+#>":
        line_start = text.rfind("\n", 0, i) + 1
        return all(c in "-*+#> \t" for c in text[line_start:i])
    return False


def _is_path(tok):
    # "and/or", "initiated/completed": one slash between two plain lowercase words is prose.
    parts = re.split(r"[/\\]", tok)
    if len(parts) == 2 and all(re.fullmatch(r"[a-z]+", p) for p in parts):
        return False
    return True


def invariants(text, names_at_sentence_start=False):
    """Return {token: kind} for every fact-bearing token in text, in order of appearance.
    With names_at_sentence_start, a capitalised word that opens a line or sentence is kept
    too: what a rendering is looked up in, not what a source is held to."""
    text = LIST_MARKER.sub("", text)
    found = {}
    for m in INVARIANT.finditer(text):
        kind = m.lastgroup
        tok = m.group(kind)
        if kind == "path" and not _is_path(tok):
            continue
        if kind == "upper" and LONE_LETTER.fullmatch(tok):
            continue
        if kind == "snake" and "_" not in tok.strip("_") and not re.fullmatch(r"__[a-z0-9]+__", tok):
            continue
        if kind == "proper":
            if tok.lower() in PROPER_STOP:
                continue
            if not names_at_sentence_start and _is_sentence_start(text, m.start()):
                continue
        # Sentence punctuation after a token is not part of it: "notes/foo." and "https://x.y/z:".
        tok = tok.rstrip(".:!?") if kind == "url" else tok.rstrip(".")
        if tok in found:
            continue
        found[tok] = kind
    return found


def _all_caps_line(text, start, end):
    """True when the rest of the line has no lowercase letter and holds another all-caps word
    of two or more letters ("WE MAY FAIL"); "ship: MAY, 14:02 UTC" is a mixed-case line."""
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    line = text[line_start:start] + " " + text[end:line_end if line_end >= 0 else len(text)]
    return LOWER_LETTER.search(line) is None and CAPS_WORD.search(line) is not None


LOWER_LETTER = re.compile(rf"[a-z{LATIN_LOWER}]")
CAPS_WORD = re.compile(rf"\b[A-Z{LATIN_UPPER}]{{2,}}\b")


def hedges(text):
    """Return {group: [words]} for hedge words found in text."""
    text = LIST_MARKER.sub("", text)      # "2) May we proceed?": the marker is not a sentence
    found = {}
    for m in HEDGE.finditer(text):
        if m.group(0) in ("May", "MAY") and (re.match(r"[ \t]+\d|:", text[m.end():])
                                             or (m.group(0) == "May"
                                                 and not _is_sentence_start(text, m.start()))
                                             or (m.group(0) == "MAY"
                                                 and not _all_caps_line(text, m.start(), m.end()))):
            # "May 2026", "MAY 14", "May:", "in May because", "due: MAY": the month. The modal
            # verb is capitalised only at a sentence start ("May I help?") or in an all-caps
            # line ("WE MAY FAIL"), where another all-caps word stands beside it; a label
            # colon right after it ("May: ship") names the month, as "מאי:" does. A number on
            # the next line is not the day: the line break ends the sentence, as for "no.".
            continue
        word = m.group(0).lower()
        for group, words in HEDGE_GROUPS.items():
            if word in words:
                found.setdefault(group, []).append(word)
                break
    for group, pattern in HEDGE_HE.items():
        for m in pattern.finditer(text):
            found.setdefault(group, []).append(m.group("word"))
    return found


def present(tok, kind, text, tokens=None):
    """Whether the source token tok of kind is in the rendering text. tokens is
    invariants(text, names_at_sentence_start=True) when the caller already has it."""
    if kind not in ("date", "time", "datetime"):
        if tokens is None:
            tokens = invariants(text, names_at_sentence_start=True)
        if tok in tokens:
            return True
        # A Hebrew form stands between Hebrew-letter boundaries, with up to three prefix
        # letters (במאי, ממאי, ובמאי); "מאיפה" or "לשבת" is another word, not the month or the
        # day. A capitalised name or a full name in capitals (OCTOBER, MONDAY) is a month or
        # weekday; "DEC" and "SAT" are acronyms, not דצמבר and שבת ("MAY" is the one all-caps
        # short form that is the month, see hedges()).
        if kind == "proper" or (kind == "upper" and (tok == "MAY" or len(tok) > 3)):
            forms = [rf"(?<![{HEB}])[ובלמהשכ]{{0,3}}" + re.escape(form) + rf"(?![{HEB}])"
                     for form in CALENDAR.get(tok.lower(), ())]
            return bool(forms) and re.search("(?:" + "|".join(forms) + ")", text) is not None
        return False
    # "2026-10-25T10:00Z", "2026-10-25 10:00Z" and the date "2026-10-25" with the time "10:00Z"
    # are the same instant, written as one token or two; so are "10:00:30" and "10:00:30.000Z"
    # (JavaScript's toISOString). A zone suffix the rendering drops is a lost fact.
    tail, left, right = "", L, R
    body = re.escape(tok)
    if kind == "datetime":
        date, clock, frac, zone = DATETIME.fullmatch(tok).groups()
        body = re.escape(date) + r"[T ]" + re.escape(clock) + re.escape(frac or "")
        if frac is None and len(clock) > 5:
            body += r"(?:\.\d+)?"
        body += re.escape(zone) if zone else r"Z?"
    elif kind == "date":
        right = r"(?:(?=T\d)|" + R + ")"
    else:
        tail = r"(?:\.\d+)?Z?" if re.fullmatch(r"\d{1,2}:\d{2}:\d{2}", tok) else r"Z?"
        left = r"(?:(?<=\d{4}-\d{2}-\d{2}T)|" + L_TIME + ")"
    return re.search(left + body + tail + right, text) is not None


def negations(text):
    return len(NEG_EN.findall(text)) + len(NEG_HE.findall(text))


@dataclass
class CheckResult:
    ok: bool
    missing: list
    missing_hedges: list
    neg_source: int
    neg_rendering: int
    n_invariants: int
    inconclusive: bool


def check(source, rendering):
    """Return a CheckResult for one source/rendering pair."""
    inv = invariants(source)
    rendered = invariants(rendering, names_at_sentence_start=True)
    missing = [t for t, k in inv.items() if not present(t, k, rendering, rendered)]
    source_hedges, rendering_hedges = hedges(source), hedges(rendering)
    missing_hedges = [group for group in source_hedges if group not in rendering_hedges]
    ns, nr = negations(source), negations(rendering)
    # An empty source has nothing to check either: INCONCLUSIVE, never a vacuous PASS.
    inconclusive = not inv and not source_hedges
    ok = not missing and not missing_hedges and nr >= ns and not inconclusive
    return CheckResult(ok, missing, missing_hedges, ns, nr, len(inv), inconclusive)


def read(path):
    """Read a UTF-8 (optionally BOM-marked) text file; any other encoding is a read error."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            return f.read()
    except UnicodeDecodeError as e:
        raise OSError(f"{path} is not UTF-8 ({e.reason} at byte {e.start}); save it as UTF-8") from None


def report(src_path, out_path, source, rendering):
    result = check(source, rendering)
    if result.inconclusive:
        return False, (
            f"INCONCLUSIVE {out_path}  (checked against {src_path}; no extractable invariants, "
            "so this is not a pass)"
        )
    if result.ok:
        return True, (
            f"PASS {out_path}  ({result.n_invariants} invariants present, "
            f"negations {result.neg_source} -> {result.neg_rendering})"
        )
    lines = [f"FAIL {out_path}  (checked against {src_path})"]
    if result.missing:
        lines.append(f"  missing ({len(result.missing)}): " + ", ".join(result.missing))
    if result.missing_hedges:
        lines.append(
            "  hedges lost: "
            + "; ".join(
                f"{group} ({', '.join(hedges(source).get(group, []))})"
                for group in result.missing_hedges
            )
        )
    if result.neg_rendering < result.neg_source:
        lost = result.neg_source - result.neg_rendering
        lines.append(f"  negations: source {result.neg_source}, rendering {result.neg_rendering} ({lost} lost)")
    return False, "\n".join(lines)


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    if len(argv) == 2 and argv[0] == "--list":
        try:
            src = read(argv[1])
        except OSError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        for tok, kind in invariants(src).items():
            print(f"{kind:8} {tok}")
        for group, words in hedges(src).items():
            print(f"hedge    {group}: {', '.join(words)}")
        print(f"negations: {negations(src)}")
        return 0
    if len(argv) < 2 or argv[0].startswith("-"):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    try:
        source = read(argv[0])
        renders = [(p, read(p)) for p in argv[1:]]
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    all_ok = True
    for path, text in renders:
        ok, msg = report(argv[0], path, source, text)
        print(msg)
        all_ok &= ok
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
