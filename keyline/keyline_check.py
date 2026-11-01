"""keyline_check.py - deterministic fact check between a source note and a rendering of it.

Extracts every URL, date, timestamp, time, version, number, percentage, UPPER_CASE identifier, file
path, CamelCase name, proper noun, file name, snake_case token, git hash and lowercase identifier
with digits (sha256, utf8) from SOURCE and fails if any is missing from a RENDERING (English prose,
Hebrew, JSON, markdown...), or is there only extended (see EXT_RIGHT). A month or weekday name may appear in its Hebrew form. Also fails if
the rendering drops a hedge class (could/may, likely, should, can; English or Hebrew words) or
has fewer negation words than the source. A source with no extractable invariant and no hedge
is INCONCLUSIVE, never PASS.

Usage:
  python keyline_check.py SOURCE RENDERING [RENDERING ...]
  python keyline_check.py --list SOURCE          print what would be checked
Exit: 0 all renderings pass, 1 any rendering fails or is inconclusive, 2 usage or read error.
"""
import bisect
import re
import sys
import unicodedata
from dataclasses import dataclass

# Letters by case, from the Basic Multilingual Plane (the planes above it hold no cased letter a
# note would use). Hebrew has no case, so a Hebrew letter is neither: a name rule never takes one.
def _char_class(pred):
    """The characters of the BMP for which pred holds, as the inside of a [...] class."""
    out, start = [], None
    for cp in range(0x10001):
        if cp < 0x10000 and pred(chr(cp)):
            if start is None:
                start = cp
        elif start is not None:
            a, b = re.escape(chr(start)), re.escape(chr(cp - 1))
            out.append(a if start == cp - 1 else f"{a}-{b}")
            start = None
    return "".join(out)


UPPER = _char_class(str.isupper)
LOWER = _char_class(str.islower)
HEB_RANGE = "֐-׿יִ-ﭏ"
UP, LO = f"[{UPPER}]", f"[{LOWER}]"
LETTER = rf"[^\W\d_{HEB_RANGE}]"          # a letter of any script but Hebrew
ALNUM = rf"[^\W_{HEB_RANGE}]"             # a letter or a digit, Hebrew letters excepted
WORD = rf"[^\W{HEB_RANGE}]"               # ALNUM or "_"

# A token boundary on word characters other than Hebrew letters, so a Hebrew prefix glued to an
# identifier ("בv2.14.0") still counts as present, while "5" never matches inside "503" or "2.5"
# and "COLE" is not a token inside "ÉCOLE".
L = rf"(?<!{WORD})"
R = rf"(?!{WORD}|\.\d)"
# A token the source writes on its own is not present where a rendering only extends it, on
# either side: "notes/a.txt.bak", "report.pdf-old", "Jean-Luc-Picard", "notes/a/", "a.txt~",
# "API#x", "14:30:15" for "14:30" (EXT_RIGHT), and "old/notes/a.txt", "old-report.pdf",
# "Marie-Jean-Luc", "/notes/a.txt" (EXT_LEFT: a "/" or "\\", or ".", "-", "~" after a word
# character). A Hebrew letter is not a word character, so "ב-v2.1" and "בv2.14.0" are not
# extensions. The one exception is a pair or a range of two tokens of one family joined by
# "-" or "/" (PAIR_FAMILY): "14:30-15:00", "2026-10-25-2026-10-27", "v2.1/v2.3",
# "Postgres/MySQL", "API/SDK". A hyphen joins the parts of a name ("Jean-Luc-Picard", "S3-IA",
# "Paris-Nord"), so between names it is a pair only when both are month or weekday names
# ("Monday-Friday", "Mon-Fri"); between times, dates and versions it is a range. A path, file
# name, hash or number never pairs: "a.txt/b.txt" extends "a.txt". A token the source itself
# extends at every occurrence ("API-v2") is looked up with R only, and every source occurrence
# is judged by the same function as the rendering's, so a rendering holding the source verbatim
# always passes.
EXT_RIGHT = re.compile(rf"[.\-/\\:]{WORD}|[/\\~@#+%]")
WORD_CHAR = re.compile(WORD)
PAIR_FAMILY = {"proper": "name", "camel": "name", "upper": "name", "ident": "name", "snake": "name",
               "time": "when", "date": "when", "datetime": "when", "version": "version"}
# A number is looked up by extraction, not by a boundary: "10" is present when the rendering's
# own invariants hold "10" as a token, so it is not found inside "10:00", "2,500", "10%",
# "10/25" or the date "2026-10-25" (each one token to the extractor), while both ends of the
# range "5-10", the year range "2020-2024" and "10" in "ב-10" are (each a token of its own).
# Whatever the extractor takes from a source line it takes from the same line in a rendering,
# so a rendering holding the source verbatim always passes. A number glued to a path
# separator ("10/", "/10", "10\\") is a path, as "notes/" is: the source's "10" is not in it.
# For a time: "00:30" is not present at the end of "10:00:30"; a time is present inside an ISO
# date and time ("14:30" in "2026-10-25T14:30Z", the same instant written with a space).
L_TIME = rf"(?:(?<=\d{{4}}-\d{{2}}-\d{{2}}T)|{L}(?<!\d:))"


# The path and file alternatives look ahead for a "/" or "." through the dash-joined words that
# follow; the bound on that look-ahead (200 characters) keeps a long run ("ab-cd-ab-cd-...")
# from costing a rescan of the whole rest of the run from every word in it. A path component or
# file name longer than that is not extracted as one token. A time does not start after "N:",
# so "3:1:30" is the numbers 3, 1 and 30, not the time "1:30" (which the lookup, bounded the
# same way, would never find). The URL scheme is bounded the same way. A CamelCase name is taken
# whole or not at all: the look-ahead and back-reference stand in for an atomic group (Python
# 3.10 has none), so a long run that is not a name is given up in one pass, not rescanned.
INVARIANT = re.compile(
    L
    + rf"""(?:
      (?P<url>[A-Za-z][A-Za-z0-9+.-]{{0,30}}://[^\s<>"'`{HEB_RANGE}]+)
    | (?P<datetime>\d{{4}}-\d{{2}}-\d{{2}}T\d{{1,2}}:\d{{2}}(?::\d{{2}})?(?:\.\d+)?(?:Z|[+-]\d{{2}}:?\d{{2}})?)
    | (?P<date>\d{{4}}-\d{{2}}-\d{{2}})
    | (?P<time>(?<!\d:)\d{{1,2}}:\d{{2}}(?::\d{{2}})?Z?)
    | (?P<version>v\d+(?:\.\d+)*|\d+\.\d+\.\d+(?:\.\d+)*)
    | (?P<path>(?:[A-Za-z]:)?[\w.~-]{{0,200}}[/\\][\w.~/\\-]*)
    | (?P<file>[\w-]{{2,200}}(?:\.[A-Za-z][A-Za-z0-9]*)+)
    | (?P<upper>{UP}[{UPPER}0-9]*(?:_[{UPPER}0-9]+)*s?)
    | (?P<camel>(?={LETTER}*{LO}{UP})(?=(?P<_camel_run>{ALNUM}+))(?P=_camel_run))
    | (?P<proper>{UP}{LO}{ALNUM}*(?:-{ALNUM}+|'(?!s(?!{ALNUM})){ALNUM}+)*)
    | (?P<snake>_*{ALNUM}+(?:_+{ALNUM}+)+_*|__[a-z0-9]+__)
    | (?P<hash>(?=[0-9a-f]*[a-f])(?=[0-9a-f]*\d)[0-9a-f]{{7,128}})
    | (?P<number>0[xX][0-9a-fA-F]+|\d+(?:[.,]\d+)*(?:[eE][-+]?\d+)?(?:%|[A-Za-z]+)?)
    | (?P<ident>{LO}+\d{ALNUM}*)
)"""
    + R,
    re.X,
)
LONE_LETTER = re.compile(rf"{UP}s?")


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
# A marker has one or two digits: "2024. Migration done" and "503. Gateway" start with a fact.
LIST_MARKER = re.compile(r"^[ \t]*(?:\d{1,2}[.)]|[-*+])[ \t]+", re.M)

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
# A full name in capitals ("OCTOBER", "MONDAY") is the month or the day too; an abbreviation in
# capitals ("DEC", "SAT", "MAR") is an acronym ("MAY" is both, see hedges()).
CALENDAR_FULL = {"january", "february", "march", "april", "may", "june", "july", "august",
                 "september", "october", "november", "december", "sunday", "monday", "tuesday",
                 "wednesday", "thursday", "friday", "saturday"}

# English: the specified list (no, not, never, without, none) plus "cannot" and n't contractions,
# so a prose rendering that writes "doesn't" for "does not" is not reported as a lost negation.
# "No. 5" is a number sign, not a negation, except at a sentence start ("Up? No. 5 are down.",
# see negations()); the number follows on the same line. The word edges are letters and digits,
# not "\b": "\b" counts "_" as a letter, so underscore emphasis ("_not_") hid the word.
EN_L, EN_R = r"(?<![^\W_])", r"(?![^\W_])"
NEG_EN = re.compile(EN_L + r"(?:no|not|never|without|none|cannot|[A-Za-z]+n't)" + EN_R, re.I)
NUMBER_SIGN = re.compile(r"\.[ \t]*\d")
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
HEDGE = re.compile(EN_L + "(?:" + "|".join(w for words in HEDGE_GROUPS.values() for w in words) + ")" + EN_R, re.I)
HEDGE_HE = {
    group: re.compile(rf"(?<![{HEB}])(?:ו|ש|וש|כש)?(?P<word>" + "|".join(map(re.escape, words)) + rf")(?![{HEB}])")
    for group, words in HEDGE_GROUPS_HE.items()
}

BOUNDARY = ".?!\n"


def _is_sentence_start(text, start):
    """True when only whitespace, a sentence end or a line-leading marker ("## ", "> ", "**")
    separates this token from a line or sentence edge. A dash or ">" mid-line is a separator
    ("Postgres - Prisma"), not a marker: the word after it is checked. The look-back stops at
    the first character that settles it, so a long line costs no rescan per token."""
    i = start - 1
    while i >= 0 and text[i] in " \t":
        i -= 1
    if i < 0 or text[i] in BOUNDARY:
        return True
    if text[i] in "-*+#>":
        while i >= 0 and text[i] in "-*+#> \t":
            i -= 1
        return i < 0 or text[i] == "\n"
    return False


def _is_path(tok):
    # "and/or", "initiated/completed": one slash between two plain lowercase words is prose.
    parts = re.split(r"[/\\]", tok)
    if len(parts) == 2 and all(re.fullmatch(r"[a-z]+", p) for p in parts):
        return False
    return True


def _trim_url(tok):
    """A URL without the sentence punctuation after it; a ")" stays when the URL opened one.
    The brackets are counted once, so a long run of ")" is trimmed in linear time."""
    opened = {")": tok.count("("), "]": tok.count("["), "}": tok.count("{")}
    closed = {c: tok.count(c) for c in opened}
    end = len(tok)
    while end:
        c = tok[end - 1]
        if c in ".,;:!?":
            end -= 1
        elif c in closed and closed[c] > opened[c]:
            closed[c] -= 1
            end -= 1
        else:
            break
    return tok[:end]


def _token_at(text, pos):
    """(kind, token) of the token that starts at pos, or None."""
    m = INVARIANT.match(text, pos)
    return (m.lastgroup, m.group(m.lastgroup)) if m else None


def _token_before(text, end):
    """(kind, token) of a token that ends at end (one of at most 64 characters), or None."""
    for p in range(max(0, end - 64), end):
        m = INVARIANT.match(text, p, end)
        if m and m.end() == end:
            return m.lastgroup, m.group(m.lastgroup)
    return None


def _pairs(kind, tok, joiner, other):
    """Whether tok and the token other on the far side of joiner are a pair (see EXT_RIGHT)."""
    if other is None or PAIR_FAMILY.get(kind) is None:
        return False
    family = PAIR_FAMILY[kind]
    if family != PAIR_FAMILY.get(other[0]):
        return False
    if joiner == "/" or family != "name":
        return True
    return tok.lower() in CALENDAR and other[1].lower() in CALENDAR


def _unextended(text, s, e, kind, tok):
    """Whether the occurrence text[s:e] of tok is not extended on either side (see EXT_RIGHT)."""
    if kind == "date" and re.match(r"T\d", text[e:e + 2]):
        pass                                # the date of an ISO date and time
    elif EXT_RIGHT.match(text, e):
        joiner = text[e]
        if joiner not in "-/" or not _pairs(kind, tok, joiner, _token_at(text, e + 1)):
            return False
    if s:
        c = text[s - 1]
        glued = s > 1 and WORD_CHAR.match(text, s - 2) is not None
        if c in "/\\" or (c in ".-~" and glued):
            if not (glued and c in "-/" and _pairs(kind, tok, c, _token_before(text, s - 1))):
                return False
    return True


def _scan(text):
    """Return ({token: kind}, alone): the fact-bearing tokens of text in order of appearance, and
    the set of those the text writes on their own at least once (see EXT_RIGHT)."""
    text = LIST_MARKER.sub("", text)
    found, alone = {}, set()
    for m in INVARIANT.finditer(text):
        kind = m.lastgroup
        tok = m.group(kind)
        # The period is a sentence end, so it goes before the shape checks: "yes/no." is prose.
        tok = _trim_url(tok) if kind == "url" else tok.rstrip(".")
        if kind == "url" and tok.endswith("://"):
            continue
        if kind == "path" and not _is_path(tok):
            continue
        if kind == "upper" and LONE_LETTER.fullmatch(tok):
            continue          # "A", "I", "As": a letter, not an identifier ("S3", "A1" are)
        if kind == "proper":
            if tok.lower() in PROPER_STOP or _is_sentence_start(text, m.start()):
                continue
        if kind not in ("url", "number") and _unextended(text, m.start(kind), m.start(kind) + len(tok), kind, tok):
            alone.add(tok)
        if tok not in found:
            found[tok] = kind
    return found, alone


def invariants(text):
    """Return {token: kind} for every fact-bearing token in text, in order of appearance."""
    return _scan(text)[0]


class _Lines:
    """Line edges and per-line facts of one text, found once: hedges() asks for them per word,
    and a fresh scan of the line each time made a long line quadratic."""

    def __init__(self, text):
        self.text = text
        self.starts = [0] + [m.end() for m in re.finditer("\n", text)]
        self._caps = {}

    def bounds(self, pos):
        i = bisect.bisect_right(self.starts, pos) - 1
        end = self.starts[i + 1] - 1 if i + 1 < len(self.starts) else len(self.text)
        return self.starts[i], end

    def all_caps(self, start, end):
        """True when the rest of the line has no lowercase letter and holds another all-caps word
        of two or more letters ("WE MAY FAIL"); "ship: MAY, 14:02 UTC" is a mixed-case line.
        start, end are the edges of an all-caps word that counts itself among those words."""
        line_start, line_end = self.bounds(start)
        if line_start not in self._caps:
            line = self.text[line_start:line_end]
            self._caps[line_start] = (re.search(r"[a-z]", line) is None,
                                      len(CAPS_WORD.findall(line)))
        no_lower, caps = self._caps[line_start]
        return no_lower and caps >= 2


# "May 2026", "May: ship", "**May**: 3", "**May** 5", "**May**" or "May" at a line end. A
# header line is no exception of its own: "## May" ends the line, "## May we ship?" is a modal.
MONTH_AFTER = re.compile(r"\s+\d|[ \t]*:|\*\*[ \t]*(?::|\d|\n|$)|[ \t]*(?:\n|$)")
# An all-caps word between letter-or-digit edges, so "_MAY_" (emphasis) is one.
CAPS_WORD = re.compile(r"(?<![^\W_])[A-Z]{2,}(?![^\W_])")


def hedges(text):
    """Return {group: [words]} for hedge words found in text."""
    text = LIST_MARKER.sub("", text)      # "2) May we proceed?": the marker is not a sentence
    lines = _Lines(text)
    found = {}
    for m in HEDGE.finditer(text):
        word = m.group(0)
        if word in ("May", "MAY"):
            if (MONTH_AFTER.match(text, m.end())
                    or (word == "May" and not _is_sentence_start(text, m.start()))
                    or (word == "MAY" and not lines.all_caps(m.start(), m.end()))):
                # "May 2026", "MAY 14", "May: ship v2", "**May** 5", "## May", "May" alone at a
                # line end, "in May because", "due: MAY": the month. The modal verb is
                # capitalised only at a sentence start ("May I help?") or in an all-caps line
                # ("WE MAY FAIL"), where another all-caps word stands beside it.
                continue
        word = word.lower()
        for group, words in HEDGE_GROUPS.items():
            if word in words:
                found.setdefault(group, []).append(word)
                break
    for group, pattern in HEDGE_HE.items():
        for m in pattern.finditer(text):
            found.setdefault(group, []).append(m.group("word"))
    return found


TIME_PARTS = re.compile(r"(\d{1,2}:\d{2})(:\d{2})?(\.\d+)?(.*)", re.S)


def _clock(rest):
    """The pattern of "HH:MM[:SS][.f][zone]": seconds ":00" may be written or left out."""
    hm, sec, frac, zone = TIME_PARTS.fullmatch(rest).groups()
    if sec in (None, ":00") and not frac:
        return re.escape(hm) + r"(?::00)?", zone
    return re.escape(hm + (sec or "") + (frac or "")), zone


# The runs of word characters of a rendering, by text, so present() tries a token only where
# its first run starts instead of searching the whole rendering once per distinct token.
WORD_RUN = re.compile(rf"{L}{WORD}+")


def word_index(text):
    """{run: [start, ...]} for every maximal run of word characters in text."""
    index = {}
    for m in WORD_RUN.finditer(text):
        index.setdefault(m.group(), []).append(m.start())
    return index


def present(tok, kind, text, tokens=None, alone=True, index=None):
    """Whether the source token tok of kind is in the rendering text. tokens is
    invariants(text) and index is word_index(text) when the caller already has them. alone:
    the source writes tok on its own, so a rendering that only extends it ("a.txt" as
    "a.txt.bak", "old/a.txt") does not count (see EXT_RIGHT)."""
    if kind in ("number", "url"):
        # A URL is looked up by extraction too: whatever a rendering glues to it ("@evil.io",
        # "&debug=1", "#frag") is part of the rendering's URL, so the source's is not there.
        return tok in (invariants(text) if tokens is None else tokens)
    left, right = L, R
    if kind == "time":
        clock, zone = _clock(tok)
        body = clock + ("Z" if zone else "Z?")
        left = L_TIME
    elif kind == "datetime":
        # "2026-10-25T10:00Z" and "2026-10-25 10:00Z" are the same instant.
        clock, zone = _clock(tok[11:])
        body = re.escape(tok[:10]) + r"[T ]" + clock + re.escape(zone)
    else:
        body = re.escape(tok)
    if kind == "date":
        right = rf"(?:(?=T\d)|{right})"     # the date of an ISO date and time
    pattern = re.compile(left + body + right)

    def found(m):
        return m is not None and (not alone or _unextended(text, m.start(), m.end(), kind, tok))

    first = WORD_RUN.match(tok)
    if kind != "time" and first:
        # left is L here: a match starts where a run of word characters starts, and that run
        # is the token's own first run (the token goes on with a non-word character or ends,
        # and R refuses a word character after it).
        if index is None:
            index = word_index(text)
        if any(found(pattern.match(text, pos)) for pos in index.get(first.group(), ())):
            return True
    else:
        pos = 0
        while True:                         # every match, overlapping ones too
            m = pattern.search(text, pos)
            if m is None:
                break
            if found(m):
                return True
            pos = m.start() + 1
    # A Hebrew form stands between Hebrew-letter boundaries, with up to three prefix letters
    # (במאי, ממאי, ובמאי); "מאיפה" or "לשבת" is another word, not the month or the day. Only
    # a capitalised name or a full name in capitals is a month or weekday: "DEC" and "SAT" are
    # acronyms, not דצמבר and שבת.
    if kind == "proper" or tok.lower() in CALENDAR_FULL:
        forms = [rf"(?<![{HEB}])[ובלמהשכ]{{0,3}}" + re.escape(form) + rf"(?![{HEB}])"
                 for form in CALENDAR.get(tok.lower(), ())]
        if forms and re.search("(?:" + "|".join(forms) + ")", text):
            return True
    return False


def _after_sentence_end(text, start):
    """True when only spaces or tabs separate start from the text start, a line start or a
    sentence end (".", "?", "!")."""
    i = start - 1
    while i >= 0 and text[i] in " \t":
        i -= 1
    return i < 0 or text[i] in BOUNDARY


def negations(text):
    n = len(NEG_HE.findall(text))
    for m in NEG_EN.finditer(text):
        if (m.group().lower() == "no" and NUMBER_SIGN.match(text, m.end())
                and not _after_sentence_end(text, m.start())):
            continue                        # "Ticket No. 5": a number sign
        n += 1
    return n


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
    # NFC: "Zürich" with a combining diaeresis (NFD, as some editors save it) is "Zürich".
    source, rendering = unicodedata.normalize("NFC", source), unicodedata.normalize("NFC", rendering)
    inv, alone = _scan(source)
    rendered, index = invariants(rendering), word_index(rendering)
    missing = [t for t, k in inv.items() if not present(t, k, rendering, rendered, t in alone, index)]
    source_hedges, rendering_hedges = hedges(source), hedges(rendering)
    missing_hedges = [group for group in source_hedges if group not in rendering_hedges]
    ns, nr = negations(source), negations(rendering)
    # An empty source has nothing to check either: INCONCLUSIVE, never a vacuous PASS.
    inconclusive = not inv and not source_hedges
    ok = not missing and not missing_hedges and nr >= ns and not inconclusive
    return CheckResult(ok, missing, missing_hedges, ns, nr, len(inv), inconclusive)


def read(path):
    """Read a UTF-8 (optionally BOM-marked) text file, NFC-normalized; any other encoding is a
    read error."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            return unicodedata.normalize("NFC", f.read())
    except UnicodeDecodeError as e:
        # utf-8-sig counts from after a BOM; the offset names the byte in the file.
        with open(path, "rb") as f:
            bom = 3 if f.read(3) == b"\xef\xbb\xbf" else 0
        raise OSError(f"{path} is not UTF-8 ({e.reason} at byte {e.start + bom}); save it as UTF-8") from None


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
