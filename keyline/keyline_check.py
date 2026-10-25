"""keyline_check.py - deterministic fact check between a source note and a rendering of it.

Extracts every date, timestamp, time, version, number, percentage, UPPER_CASE identifier, file path,
CamelCase name, proper noun, file name, snake_case token, git hash and lowercase identifier with
digits (sha256, utf8) from SOURCE and fails if any is missing from a RENDERING (English prose,
Hebrew, JSON, markdown...). A month or weekday name may appear in its Hebrew form. Also fails if
the rendering drops a hedge class (could/may, likely, should, can; English or Hebrew words) or
has fewer negation words than the source. A source with no extractable invariant is
INCONCLUSIVE, never PASS.

Usage:
  python keyline_check.py SOURCE RENDERING [RENDERING ...]
  python keyline_check.py --list SOURCE          print what would be checked
Exit: 0 all renderings pass, 1 any rendering fails or is inconclusive, 2 usage or read error.
"""
import re
import sys
from dataclasses import dataclass

# A token boundary on ASCII word characters only, so a Hebrew prefix glued to an identifier
# ("בv2.14.0") still counts as present, while "5" never matches inside "503" or "2.5".
L = r"(?<![A-Za-z0-9_])"
R = r"(?![A-Za-z0-9_]|\.\d)"
# For a number looked up in a rendering: "10" is not present in "10:00", nor "2" in "2,500".
L_NUMBER = r"(?<![A-Za-z0-9_])(?<!\d[.,:])"
R_NUMBER = r"(?![A-Za-z0-9_]|[.,:]\d)"


INVARIANT = re.compile(
    L
    + r"""(?:
      (?P<datetime>\d{4}-\d{2}-\d{2}T\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)
    | (?P<date>\d{4}-\d{2}-\d{2})
    | (?P<time>\d{1,2}:\d{2}(?::\d{2})?Z?)
    | (?P<version>v\d+(?:\.\d+)*|\d+\.\d+\.\d+(?:\.\d+)*)
    | (?P<path>(?:[A-Za-z]:)?[\w.~-]*[/\\][\w.~/\\-]*)
    | (?P<file>[\w-]{2,}(?:\.[A-Za-z][A-Za-z0-9]*)+)
    | (?P<upper>[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*s?)
    | (?P<camel>[A-Za-z]*[a-z][A-Z][A-Za-z0-9]*)
    | (?P<proper>[A-Z][a-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+|'(?!s(?![A-Za-z0-9]))[A-Za-z0-9]+)*)
    | (?P<snake>_*[A-Za-z0-9]+(?:_+[A-Za-z0-9]+)+_*|__[A-Za-z0-9]+__)
    | (?P<hash>(?=[0-9a-f]*[a-f])(?=[0-9a-f]*\d)[0-9a-f]{7,40})
    | (?P<number>\d+(?:[.,]\d+)*(?:%|[A-Za-z]+)?)
    | (?P<ident>[a-z]+\d[A-Za-z0-9]*)
)"""
    + R,
    re.X,
)

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
}

# Markdown list markers carry no fact; "1. Add ..." must not make "1" an invariant.
LIST_MARKER = re.compile(r"^\s*(?:\d+[.)]|[-*+])\s+", re.M)

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
NEG_EN = re.compile(r"\b(?:no|not|never|without|none|cannot)\b|\b[A-Za-z]+n't\b", re.I)
# Hebrew: the specified list (לא, אין, ללא, אף, מעולם) plus the conjunction prefixes ו/ש/וש/כש on
# לא/אין/ללא and the inflected forms of אין, which Hebrew prose uses constantly (שלא, ולא, אינו).
HEB = "א-ת"
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


def invariants(text):
    """Return {token: kind} for every fact-bearing token in text, in order of appearance."""
    text = LIST_MARKER.sub("", text)
    found = {}
    for m in INVARIANT.finditer(text):
        kind = m.lastgroup
        tok = m.group(kind)
        if kind == "path" and not _is_path(tok):
            continue
        if kind == "upper" and len(re.findall(r"[A-Z]", tok)) < 2:
            continue          # "A", "I", "A1": not identifiers
        if kind == "snake" and "_" not in tok.strip("_") and not re.fullmatch(r"__[A-Za-z0-9]+__", tok):
            continue
        if kind == "proper":
            if tok.lower() in PROPER_STOP or _is_sentence_start(text, m.start()):
                continue
        tok = tok.rstrip(".")
        if tok in found:
            continue
        found[tok] = kind
    return found


def _all_caps_line(text, start, end):
    """True when another all-caps word of two or more letters stands on the same line."""
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    line = text[line_start:start] + " " + text[end:line_end if line_end >= 0 else len(text)]
    return re.search(r"\b[A-Z]{2,}\b", line) is not None


def hedges(text):
    """Return {group: [words]} for hedge words found in text."""
    found = {}
    for m in HEDGE.finditer(text):
        if m.group(0) in ("May", "MAY") and (re.match(r"\s+\d", text[m.end():])
                                             or (m.group(0) == "May"
                                                 and not _is_sentence_start(text, m.start()))
                                             or (m.group(0) == "MAY"
                                                 and not _all_caps_line(text, m.start(), m.end()))):
            # "May 2026", "MAY 14", "in May because", "due: MAY": the month. The modal verb is
            # capitalised only at a sentence start ("May I help?") or in an all-caps line
            # ("WE MAY FAIL"), where another all-caps word stands beside it.
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


def present(tok, kind, text):
    tail = r"Z?" if kind == "time" else ""
    body = re.escape(tok)
    if kind == "datetime":
        # "2026-10-25T10:00Z" and "2026-10-25 10:00Z" are the same instant.
        body = re.escape(tok[:10]) + r"[T ]" + re.escape(tok[11:])
    forms = [body] + [re.escape(form) for form in CALENDAR.get(tok.lower(), ())]
    left, right = (L_NUMBER, R_NUMBER) if kind == "number" else (L, R)
    return re.search(left + "(?:" + "|".join(forms) + ")" + tail + right, text) is not None


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
    missing = [t for t, k in inv.items() if not present(t, k, rendering)]
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
        sys.stdout.reconfigure(encoding="utf-8")
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
