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
import os
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


def _mark_outside_words(c, category):
    """A mark that is no part of a word: a variation selector (U+FE00-FE0F, U+E0100-E01EF:
    the emoji form of "✔️") and an enclosing mark (the keycap U+20E3 of "5️⃣"), which follow
    a symbol or a digit, not a letter, so "✔️v2.1" holds "v2.1" and "5️⃣" holds "5"."""
    return category == "Me" or "\ufe00" <= c <= "\ufe0f" or "\U000e0100" <= c <= "\U000e01ef"


def _word_classes():
    """(letter, alnum, mark): the insides of [...] classes for a letter, a letter or digit, and
    a combining mark, of any script but Hebrew. A mark NFC cannot fold into its letter (U+0331
    after the "a" of a name) is part of the word, as the letter is; a Hebrew point is not (a
    Hebrew letter is no word character here), nor a variation selector or an enclosing mark
    (see _mark_outside_words). A mark is no word character to re ("\\W"), so the
    classes are spelled out: a group "(?:[^\\W...]|[marks])" in a repeat is not linear in sre on
    a 100 kB run, and Python 3.10 has no possessive repeat. No letter, digit or mark lies in
    planes 4 to 13, 15 or 16, and no mark in the surrogates, the private use area or planes 2
    and 3 (test_the_word_classes_match_unicode). Above the BMP an unassigned gap between two
    ranges is joined into one range, so the classes stay short and quick to compile; a gap is
    never joined across a digit (for the letter class) or an assigned non-word character."""
    top = 0x40000                                     # planes 0 to 3, then plane 14 after a " "
    text = "".join(map(chr, range(top))) + " " + "".join(map(chr, range(0xE0000, 0xF0000)))
    text = re.sub("[\u0590-\u05ff\ufb1d-\ufb4f]", " ", text)

    def spans(pattern):
        """The [first, last] code points of each run of pattern."""
        return [[i if i < top else i - top - 1 + 0xE0000 for i in (m.start(), m.end() - 1)]
                for m in re.finditer(pattern, text)]

    nonword = re.compile(r"[^\w\s\ud800-\uf8ff]+")
    marks, walls = [], []           # walls: the assigned characters above the BMP that are no part
    for m in [*nonword.finditer(text, 0, 0x20000), *nonword.finditer(text, top + 1)]:  # of a word
        for c in m.group():
            category = unicodedata.category(c)
            if category[0] == "M" and not _mark_outside_words(c, category):
                marks.append(ord(c))
            elif category != "Cn" and c > "\uffff":
                walls.append(ord(c))
    mark_spans = []
    for cp in marks:
        if mark_spans and mark_spans[-1][1] == cp - 1:
            mark_spans[-1][1] = cp
        else:
            mark_spans.append([cp, cp])

    def merged(pattern, walls):
        """The runs of pattern and of marks, adjacent runs joined, as the inside of [...]."""
        out = []
        for a, b in sorted(spans(pattern) + mark_spans):
            # Above the BMP, where re tests each range of a class in turn, a gap of unassigned
            # code points only is closed: half the ranges, so a character that is no part of a
            # word is refused about twice as fast.
            if out and (a <= out[-1][1] + 1 or a > 0xFFFF and out[-1][1] > 0xFFFF and
                        bisect.bisect(walls, out[-1][1]) == bisect.bisect(walls, a)):
                out[-1][1] = max(out[-1][1], b)
            else:
                out.append([a, b])
        return _ranges(out)

    digits = [cp for a, b in spans(r"\d+") if b > 0xFFFF for cp in range(max(a, 0x10000), b + 1)]
    return (merged(r"[^\W\d_]+", sorted(walls + digits)), merged(r"[^\W_]+", walls),
            _ranges(mark_spans))


def _ranges(spans):
    out = []
    for a, b in spans:
        ea, eb = re.escape(chr(a)), re.escape(chr(b))
        out.append(ea if a == b else f"{ea}-{eb}")
    return "".join(out)


UPPER = _char_class(str.isupper)
LOWER = _char_class(str.islower)
HEB_RANGE = "֐-׿יִ-ﭏ"
_LETTERS, _ALNUMS, MARK = _word_classes()
UP, LO = f"[{UPPER}]", f"[{LOWER}]"
LETTER = f"[{_LETTERS}]"          # a letter of any script but Hebrew, or a combining mark
ALNUM = f"[{_ALNUMS}]"            # a letter, a digit or a mark, Hebrew excepted
WORD = f"[_{_ALNUMS}]"            # ALNUM or "_"

# A token boundary on word characters other than Hebrew letters, so a Hebrew prefix glued to an
# identifier ("בv2.14.0") still counts as present, while "5" never matches inside "503" or "2.5"
# and "COLE" is not a token inside "ÉCOLE".
L = rf"(?<!{WORD})"
R = rf"(?!{WORD}|\.\d)"
# A token the source writes on its own is not present where a rendering only extends it, on
# either side: "notes/a.txt.bak", "report.pdf-old", "Jean-Luc-Picard", "notes/a/", "ab.txt~",
# "API#x", "14:30:15" for "14:30", "ab.txt=1", "API(x)" (EXT_RIGHT), and "old/notes/a.txt",
# "old-report.pdf", "Marie-Jean-Luc", "/notes/a.txt", "#API", "x@a.txt" (the left side). Both
# sides share one set of joiners (JOIN): a joiner glued between the token and a word character
# extends it, and a few (EXT_ALWAYS_RIGHT, EXT_ALWAYS_LEFT) extend it on their own ("ab.txt~",
# "C#", "50%", "ab.txt*", "+v2.1", "$PATH"). A Hebrew letter is not a word character, so "ב-v2.1"
# and "בv2.14.0" are not extensions. Markup is not a joiner: "(API)", and emphasis ("**API**",
# "_API_"), whose marks are dropped before the scan (see EMPHASIS). The one exception is a pair or a range of two tokens of one family joined by
# "-" or "/" (PAIR_FAMILY): "14:30-15:00", "2026-10-25-2026-10-27", "v2.1/v2.3",
# "Postgres/MySQL", "API/SDK". A hyphen joins the parts of a name ("Jean-Luc-Picard", "S3-IA",
# "Paris-Nord"), so between names it is a pair only when both are month or weekday names
# ("Monday-Friday", "Mon-Fri"); between times, dates and versions it is a range. A path, file
# name, hash or number never pairs: "ab.txt/cd.txt" extends "ab.txt". A token the source itself
# extends at every occurrence ("API-v2", "v2.1,v2.2", "MODE=fast") is present on its own or
# extended the way the source extends it (the same joiner on the same side, see _extension),
# so "v2.1-rc,v2.2" does not hold the "v2.1" of "v2.1,v2.2". Every source occurrence is judged
# by the same function as the rendering's, so a rendering holding the source verbatim always
# passes.
JOIN = ".-/\\:~@#+%=&*$,"
EXT_ALWAYS_RIGHT, EXT_ALWAYS_LEFT = "/\\~@#+%*", "/\\@#+$%"
EXT_RIGHT = re.compile(rf"[{re.escape(JOIN)}(]{WORD}|[{re.escape(EXT_ALWAYS_RIGHT)}]")
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
      (?P<url>[A-Za-z][A-Za-z0-9+.-]{{0,30}}://(?:{WORD}|[-.~:/?\#\[\]@!$&()*+,;=%])+)
    | (?P<datetime>\d{{4}}-\d{{2}}-\d{{2}}T\d{{1,2}}:\d{{2}}(?::\d{{2}})?(?:\.\d+)?(?:Z|[+-]\d{{2}}:?\d{{2}})?)
    | (?P<date>\d{{4}}-\d{{2}}-\d{{2}})
    | (?P<time>(?<!\d:)\d{{1,2}}:\d{{2}}(?::\d{{2}})?Z?)
    | (?P<version>v\d+(?:\.\d+)*|\d+\.\d+\.\d+(?:\.\d+)*)
    | (?P<path>(?:[A-Za-z]:)?[\w{MARK}.~-]{{0,200}}[/\\][\w{MARK}.~/\\-]*)
    | (?P<file>[\w{MARK}-]{{2,200}}(?:\.[A-Za-z][A-Za-z0-9]*)+)
    | (?P<upper>{UP}[{UPPER}{MARK}0-9]*(?:_[{UPPER}{MARK}0-9]+)*s?)
    | (?P<camel>(?={LETTER}*{LO}{UP})(?=(?P<_camel_run>{ALNUM}+))(?P=_camel_run))
    | (?P<proper>{UP}[{MARK}]*{LO}{ALNUM}*(?:-{ALNUM}+|'(?!s(?!{ALNUM})){ALNUM}+)*)
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
# Spaces alone after it are no item: "12.  " (a markdown hard break) is the number 12.
LIST_MARKER = re.compile(r"^[ \t]*(?:\d{1,2}[.)]|[-*+])[ \t]+(?=\S)", re.M)

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
# "No. 5" is a number sign, not a negation, only right after a word on the same line ("Ticket
# No. 5", see negations()); after anything else ("A: No. 5", "**Fixed?** No. 5", "(no. 3",
# "- No. 5", "yet, no. 3") it is the answer "no". A lowercase "no." is a number sign only
# after a digit ("Item 3 no. 5"): after a word it is the answer ("I'd say no. 3 fail"), so
# "ticket no. 5" counts as a negation (fails closed). The number follows on the same line. The word edges are letters and digits,
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


# The token beside a joiner is matched within this many characters on either side: a long
# dash-joined run ("Ab-Ab-Ab-...") is not matched to its end again from every token in it. A
# longer token is judged by its first (or last) TOKEN_REACH characters.
TOKEN_REACH = 64


def _token_at(text, pos):
    """(kind, token) of the token that starts at pos (one of at most TOKEN_REACH characters), or
    None."""
    m = INVARIANT.match(text, pos, pos + TOKEN_REACH)
    return (m.lastgroup, m.group(m.lastgroup)) if m else None


def _token_before(text, end):
    """(kind, token) of a token that ends at end (one of at most TOKEN_REACH characters), or
    None."""
    for p in range(max(0, end - TOKEN_REACH), end):
        m = INVARIANT.match(text, p, end)
        if m and m.end() == end:
            return m.lastgroup, m.group(m.lastgroup)
    return None


def _pairs(kind, tok, joiner, other):
    """Whether tok and the token on the far side of joiner are a pair (see EXT_RIGHT). other is a
    function that finds that token, called only when tok can pair at all."""
    family = PAIR_FAMILY.get(kind)
    if joiner not in "-/" or family is None:
        return False
    hyphen_names = joiner == "-" and family == "name"
    if hyphen_names and tok.lower() not in CALENDAR:
        return False
    other = other()
    if other is None or family != PAIR_FAMILY.get(other[0]):
        return False
    return not hyphen_names or other[1].lower() in CALENDAR


# The time of an ISO date and time after a date ("2026-10-25" in "2026-10-25T14:30Z"), as the
# datetime token writes it; "T99" is no time, so "2026-10-25T99" does not hold the date.
ISO_TIME = re.compile(r"T\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?")


def _extension(text, s, e, kind, tok):
    """How the occurrence text[s:e] of tok is extended (see EXT_RIGHT): (left, right), each
    the joiner glued on that side or None; NOT_EXTENDED is neither."""
    right = left = None
    if kind == "date":
        t = ISO_TIME.match(text, e)
        if t:                               # the date of an ISO date and time: what follows
            if WORD_CHAR.match(text, t.end()):    # the time is checked as if it followed the date
                right = "T"                       # "2026-10-25T10:00abc"
            e = t.end()
    if right is None and EXT_RIGHT.match(text, e):
        joiner = text[e]
        if not _pairs(kind, tok, joiner, lambda: _token_at(text, e + 1)):
            right = joiner
    if s:
        c = text[s - 1]
        glued = s > 1 and WORD_CHAR.match(text, s - 2) is not None
        # A token of tok's family that ends right before a "/" ends in a word character, so
        # the pair test needs no glued check of its own.
        if c in EXT_ALWAYS_LEFT or (c in JOIN and glued):
            if not _pairs(kind, tok, c, lambda: _token_before(text, s - 1)):
                left = c
    return left, right


NOT_EXTENDED = (None, None)


# Emphasis marks ("_Paris_", "__14:30__", "*API*", "**https://x.io/a**"): "_" is a word
# character, so it would hide the token inside it, and a "*" glued after a token is a joiner
# ("ab.txt*", see JOIN). An opening run of one or two "_" or one to three "*" (before a
# non-space) is paired with the next closing run of the same marks in the paragraph (after a
# non-space), and both are dropped from source and rendering alike. A mark run inside a URL,
# path or identifier is no emphasis: an opening run does not follow a word character or one of
# "*/\\.:~@=" or a "-" glued to a word ("https://x.io/_api_/v1", "/srv/_data_/x", "a-_b_";
# "ל-_Paris_" is emphasis, a Hebrew letter is no word character here), a closing run does not
# come before a word character, "/" or "\\", and a "*" run no "*" on either side ("**_Paris_**"
# is two emphases). A lone edge mark ("_private", "snake_case_", "ab.txt*") has no partner and
# stays, and so does a pair of "_" or "__" around one word that holds a "_" itself
# ("_private_var_") and a dunder ("__init__", "__init_subclass__"; "__12__" is bold).
_GLUED_DASH = r"(?<![^\W\u0590-\u05ff\ufb1d-\ufb4f]-)"
EMPHASIS = re.compile(rf"(?P<open>(?<![\w*/\\.:~@=]){_GLUED_DASH}\*{{1,3}}(?=[^\s*])"
                      rf"|(?<![\w/\\.:~@=]){_GLUED_DASH}_{{1,2}}(?=[^\s_]))"
                      r"|(?P<close>(?<=[^\s*])\*{1,3}(?![\w*/\\])|(?<=[^\s_])_{1,2}(?![\w/\\]))"
                      r"|\n[ \t]*\n")
DUNDER_BODY = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")


def _plain(text):
    """text without the marks of emphasis (see EMPHASIS). Linear: each run is pushed and popped
    at most once, and whether a body is one word holding a "_" is counted, not scanned (nested
    pairs would scan the same text again)."""
    drop, opened, edges = [], {}, None

    def one_word_with_underscore(a, b):
        nonlocal edges
        if edges is None:
            edges = ([m.start() for m in re.finditer(r"\s", text)], [m.start() for m in re.finditer("_", text)])
        spaces, unders = edges
        return (bisect.bisect_left(spaces, b) == bisect.bisect_left(spaces, a)
                and bisect.bisect_left(unders, b) > bisect.bisect_left(unders, a))

    for m in EMPHASIS.finditer(text):
        if m.lastgroup == "open":
            opened.setdefault(m.group(), []).append(m)
        elif m.lastgroup == "close":
            stack = opened.get(m.group())
            if stack:
                o = stack.pop()
                if not (m.group()[0] == "_" and (
                        one_word_with_underscore(o.end(), m.start())
                        or m.group() == "__" and DUNDER_BODY.fullmatch(text, o.end(), m.start()))):
                    drop += [o.span(), m.span()]
        else:
            opened = {}                       # emphasis does not run past a blank line
    if not drop:
        return text
    drop.sort()
    out, pos = [], 0
    for a, b in drop:
        out.append(text[pos:a])
        pos = b
    out.append(text[pos:])
    return "".join(out)


def _scan(text):
    """Return ({token: kind}, {token: extensions}): the fact-bearing tokens of text in order of
    appearance, and for each token but a URL or a number the set of the ways text writes it
    (see _extension); NOT_EXTENDED in it means the text writes the token on its own at least
    once (see EXT_RIGHT). text has been through _plain()."""
    text = LIST_MARKER.sub("", text)
    found, extensions = {}, {}
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
        parts = [(m.start(kind), tok)]
        if kind == "proper":
            if tok.lower() in PROPER_STOP or _is_sentence_start(text, m.start()):
                continue
            names = tok.split("-")
            if len(names) > 1 and all(n.lower() in CALENDAR for n in names):
                # "Monday-Friday", "Mon-Fri": a range of two calendar names, each a token of
                # its own, as a rendering's "Monday-Friday" is (see _pairs).
                parts, at = [], m.start(kind)
                for n in names:
                    parts.append((at, n))
                    at += len(n) + 1
        for start, part in parts:
            if kind not in ("url", "number"):
                extensions.setdefault(part, set()).add(_extension(text, start, start + len(part), kind, part))
            if part not in found:
                found[part] = kind
    return found, extensions


def invariants(text):
    """Return {token: kind} for every fact-bearing token in text, in order of appearance."""
    return _scan(_plain(text))[0]


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
# A sentence-start subject is the month too: "May, June and July", "May and June", "May to
# July", "May was busy", "May." ("May, I ask, ..." and "May the tests pass" stay modals).
MONTHS = ("january|february|march|april|may|june|july|august|september|october|november|december"
          "|jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec")
MONTH_AFTER = re.compile(
    r"\s+\d|[ \t]*:|\*\*[ \t]*(?::|\d|\n|$)|[ \t]*(?:\n|$)|[ \t]*\.(?![^\W_])"
    rf"|[ \t]*(?:,|&|[ \t](?:and|or|to|through|until|till))[ \t]+(?:{MONTHS})(?![^\W_])"
    r"|[ \t]+(?:is|was|has|had|will)(?![^\W_])",
    re.I)
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
    """The forms of "HH:MM[:SS][.f]", longest first, and the zone: seconds ":00" may be written
    or left out."""
    hm, sec, frac, zone = TIME_PARTS.fullmatch(rest).groups()
    if sec in (None, ":00") and not frac:
        return [hm + ":00", hm], zone
    return [hm + (sec or "") + (frac or "")], zone


# The boundaries of a token, matched at a position (a look-behind sees the text before it).
# present() looks a token up as plain text between these, not through a pattern of its own:
# the word classes are thousands of characters long, and compiling them once per token cost
# more than the whole check.
LEFT_AT, LEFT_TIME_AT, RIGHT_AT = re.compile(L), re.compile(L_TIME), re.compile(R)
RIGHT_DATE_AT = re.compile(rf"(?=T\d{{1,2}}:\d{{2}})|{R}")   # the date of an ISO date and time


# The runs of word characters of a rendering, by text, so present() tries a token only where
# its first run starts instead of searching the whole rendering once per distinct token.
WORD_RUN = re.compile(rf"{L}{WORD}+")


def word_index(text):
    """{run: [start, ...]} for every maximal run of word characters in text."""
    index = {}
    for m in WORD_RUN.finditer(text):
        index.setdefault(m.group(), []).append(m.start())
    return index


def present(tok, kind, text, tokens=None, alone=True, index=None, extensions=None):
    """Whether the source token tok of kind is in the rendering text (through _plain()). tokens is
    invariants(text) and index is word_index(text) when the caller already has them. alone:
    the source writes tok on its own, so a rendering that only extends it ("ab.txt" as
    "ab.txt.bak", "old/ab.txt") does not count (see EXT_RIGHT). Otherwise extensions, when
    given, is the set of ways the source extends tok (see _scan): a rendering occurrence counts
    on its own or extended in one of those ways ("v2.1,v2.2" holds the "v2.1" of "v2.1,v2.2",
    "v2.1-rc,v2.2" does not), so a joiner beside tok in the source lets no other extension
    pass."""
    if kind in ("number", "url"):
        # A URL is looked up by extraction too: whatever a rendering glues to it ("@evil.io",
        # "&debug=1", "#frag") is part of the rendering's URL, so the source's is not there.
        return tok in (invariants(text) if tokens is None else tokens)
    # The forms of the token in the order a pattern would try them (an optional part present
    # first), so the first that fits at a position is the match there.
    left, right = LEFT_AT, RIGHT_AT
    if kind == "time":
        clocks, zone = _clock(tok)
        forms = [c + z for c in clocks for z in (["Z"] if zone else ["Z", ""])]
        left = LEFT_TIME_AT
    elif kind == "datetime":
        # "2026-10-25T10:00Z" and "2026-10-25 10:00Z" are the same instant.
        clocks, zone = _clock(tok[11:])
        forms = [tok[:10] + sep + c + zone for sep in "T " for c in clocks]
    else:
        forms = [tok]
    if kind == "date":
        right = RIGHT_DATE_AT

    def match(pos):
        """(start, end) of the token at pos, or None."""
        if left.match(text, pos):
            for form in forms:
                if text.startswith(form, pos) and right.match(text, pos + len(form)):
                    return pos, pos + len(form)
        return None

    def found(m):
        if m is None:
            return False
        if not alone and extensions is None:
            return True
        how = _extension(text, m[0], m[1], kind, tok)
        return how == NOT_EXTENDED or not alone and how in extensions

    first = WORD_RUN.match(tok)
    if kind != "time" and first:
        # left is L here: a match starts where a run of word characters starts, and that run
        # is the token's own first run (the token goes on with a non-word character or ends,
        # and R refuses a word character after it).
        if index is None:
            index = word_index(text)
        if any(found(match(pos)) for pos in index.get(first.group(), ())):
            return True
    else:
        prefix, pos = os.path.commonprefix(forms), 0
        while True:                         # every match, overlapping ones too
            pos = text.find(prefix, pos)
            if pos < 0:
                break
            if found(match(pos)):
                return True
            pos += 1
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


def _after_word(text, start, digit=False):
    """True when the last character before start on its line, spaces and tabs aside, is a
    letter or a digit (a digit only, with digit)."""
    i = start - 1
    while i >= 0 and text[i] in " \t":
        i -= 1
    return i >= 0 and (text[i].isdigit() if digit else text[i].isalnum())


def negations(text):
    n = len(NEG_HE.findall(text))
    for m in NEG_EN.finditer(text):
        word = m.group()
        if (word.lower() == "no" and NUMBER_SIGN.match(text, m.end())
                and _after_word(text, m.start(), digit=word not in ("No", "NO"))):
            continue                        # "Ticket No. 5", "Item 3 no. 5": a number sign
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
    inv, extensions = _scan(_plain(source))
    plain = _plain(rendering)
    rendered, index = _scan(plain)[0], word_index(plain)
    missing = [t for t, k in inv.items()
               if not present(t, k, plain, rendered, NOT_EXTENDED in extensions.get(t, (NOT_EXTENDED,)),
                              index, extensions.get(t))]
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
