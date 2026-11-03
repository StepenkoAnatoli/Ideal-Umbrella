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
import collections
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


# The letters of the scripts that write no space between a word and the next (Chinese, Japanese,
# Thai) or glue particles to a word (Korean): like a Hebrew letter, one is no word character
# here, so "会议在Paris举行" holds "Paris", "パリv2.1で" holds "v2.1", and a "*" run glued to one
# opens or closes an emphasis ("会议在**Paris**举行"), as in CommonMark.
CJK = ("\u0e00-\u0e7f\u2e80-\u2fff\u3040-\u30ff\u3100-\u312f\u3190-\u31ff\u3400-\u4dbf"
       "\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af\U00020000-\U0003134f")


def _word_classes():
    """(letter, alnum, mark): the insides of [...] classes for a letter, a letter or digit, and
    a combining mark, of any script but Hebrew and those of CJK. A mark NFC cannot fold into its letter (U+0331
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
    text = re.sub(f"[\u0590-\u05ff\ufb1d-\ufb4f{CJK}]", " ", text)

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
    walls = sorted(walls + [0x20000, 0x3134F])     # the CJK of plane 2 and 3 is no word: a wall
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
NEG_EN = re.compile(EN_L + r"(?:no|not|never|without|none|cannot|[A-Za-z]+n['’ʼ]t)" + EN_R, re.I)
NUMBER_SIGN = re.compile(r"\.[ \t]*\d")
# Hebrew: the specified list (לא, אין, ללא, אף, מעולם) plus the conjunction prefixes ו/ש/וש/כש on
# לא/אין/ללא/בלי and the inflected forms of אין, which Hebrew prose uses constantly (שלא, ולא, אינו,
# שאינו), and the imperative אל ("don't"), only before a second-person future verb (אל תפרסו):
# elsewhere אל is "to" (אל הבית), and so it is before the ת-words in AL_TO, which are not verbs:
# תוך ("into"), תחת ("under"), תל (Tel Aviv) and the nouns docs put after "to" (אל תיקיית הפרויקט,
# אל תפריט ההגדרות). Any other ת-noun after אל is still taken for the verb, which the check cannot
# tell apart; such a count in a rendering can hide a lost negation, so add common ones here.
# A word listed here that is also a verb (תפריט, "privatize") then fails closed, never open.
AL_TO = ("תוך תוכו תוכה תוכם תוכן תחת תל "
         "תיקייה תיקיית תיקיה תיקית תיקיות תבנית תבניות תצורה תצורת תוכנה תוכנת תוכנית תכנית "
         "תכונה תכונת תמונה תמונת תיבה תיבת תחנה תחנת תפריט תג תגית תהליך תור תא תאריך תיק "
         "תיעוד").split()
HEB = "א-ת"
NEG_HE = re.compile(
    rf"(?<![{HEB}])(?:"
    rf"(?:ו|ש|וש|כש)?(?:לא|אין|ללא|בלי|אינו|אינה|אינם|אינן|אינני|איננו|אינך)"
    rf"|(?:ו)?אל(?=[ \t]+ת[{HEB}])(?![ \t]+(?:{'|'.join(AL_TO)})(?![{HEB}]))"
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
            # A joiner that extends alone ("v2.1*") and one glued onward ("v2.1*-rc") differ.
            if joiner in EXT_ALWAYS_RIGHT and (WORD_CHAR.match(text, e + 1)
                                              or EXT_RIGHT.match(text, e + 1)):
                right += "+"
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
# ("ab.txt*", see JOIN). Two scans read them, and a token either finds is checked:
#
# 1. The strict scan (_plain): an opening run of one to three "_" or "*" (before a non-space)
# is paired with the next closing run of the same marks in the block (after a non-space), and
# both are dropped from source and rendering alike; a blank line, a line that starts a list
# item, heading, quote or code fence (a quote's own continuation lines aside), and a table cell
# separator "|" end the block. An "_" run between two punctuation marks ("_27%_,") closes an
# open "_" run, as in CommonMark. Code is verbatim: a mark inside an inline code span is no
# emphasis and pairs with nothing ("`*.o`" and a later "ab.txt*" are no pair; "**use `x`**" is
# emphasis). A mark run inside a URL (URL_SPAN, all of it but the marks and punctuation that end
# it: "?_k_=1", "#_frag_"), path or identifier is no emphasis: an opening run does not follow a
# letter or digit, an "_" glued to one, or one of "*/\\.:~@=", or a "-" glued to a word
# ("/srv/_data_/x", "a-_b_", "x_**a**"; "ל-_Paris_" and "ב**Paris**" are emphasis, a Hebrew
# letter is no word character here); a closing run does not follow "/" or "\\" ("**/*.py and
# docs/**") nor come before a letter or digit, "/" or "\\", or an "_" run glued to one; and a "*"
# run has no "*" on either side ("_**Paris**_" is two emphases). A lone edge mark ("_private",
# "snake_case_", "ab.txt*") has no partner and stays, and so does an "_" run glued to word
# characters that hold a "_" ("_private_var_"; of "_v2.1 adds max_retries_" only the closing
# "_") and a dunder pair ("__init__", "__init_subclass__"; "__12__" is bold).
#
# 2. The edge-free scan (_edge_free) catches what the strict one keeps: every "*" or "_" run at
# a word edge (a letter or digit, Hebrew aside, missing on one side) is dropped outside URLs
# and code, so "~_20_", "14:30-_15:00_", "measured=__True__" and "ב_Paris_" give 20, 15:00, True
# and Paris. A token only this scan finds is looked up in the rendering's edge-free copy, so a
# mark the strict scan misreads hides no token, whatever the mark, and identical text passes as
# both sides go through the same functions. The copy cannot tell "_private" from "private" or
# "ab.txt*" from "ab.txt"; a token the strict scan finds is judged by it. Inside a code span the
# runs are kept: a token glued to them is taken with its marks ("`__FILE__`" is checked as
# "__FILE__", "`_Config_`" as "_Config_"), so a rendering that drops them fails.
_GLUED_DASH = rf"(?<![^\W֐-׿יִ-ﭏ{CJK}]-)"
_NO_OPEN = rf"[{_ALNUMS}*/\\.:~@=]"             # what an opening run may not follow
# After a lone "/" (no non-space before it) a run may close: "**Class: v2.1 /**".
_AFTER_LONE_SLASH = r"(?<=(?<!\S)/)"
EMPHASIS = re.compile(
    rf"(?P<open>(?<!{_NO_OPEN})(?<!{_NO_OPEN}_)(?<!{_NO_OPEN}__)(?<!{_NO_OPEN}___)(?<!____)"
    rf"{_GLUED_DASH}\*{{1,3}}(?=[^\s*])"
    rf"|(?<![{_ALNUMS}{CJK}_/\\.:~@=]){_GLUED_DASH}_{{1,3}}(?=[^\s_]))"
    rf"|(?P<close>(?:(?<=[^\s*/\\])|{_AFTER_LONE_SLASH})\*{{1,3}}(?!\*|_*[{_ALNUMS}/\\])"
    rf"|(?:(?<=[^\s_/\\])|{_AFTER_LONE_SLASH})_{{1,3}}(?![{_ALNUMS}{CJK}_/\\]))"
    r"|\n[ \t\r]*\n|\n(?=[ \t]*(?:(?:[-*+]|\d{1,2}[.)])[ \t]|#{1,6}[ \t]|```|~~~))|(?P<quote>\n(?=[ \t]*>))"
    r"|(?P<pipe>\|)|(?P<nl>\n)")
# An "_" run that may close (after a non-space, before no word character): one that EMPHASIS
# reads as opening ("%_," after punctuation) closes an open run of the same marks.
UNDERSCORE_CLOSE = re.compile(rf"(?:(?<=[^\s_/\\])|{_AFTER_LONE_SLASH})_{{1,3}}(?![{_ALNUMS}{CJK}_/\\])")
# A single "*" that starts a glob ("*.log", "*.tar.gz"): a "." and a letter or digit follow, and
# no "*" ends the word ("*.NET*" is emphasis). The look-ahead and back-reference stand in for an
# atomic group, so the word is read once.
GLOB = re.compile(rf"\.{ALNUM}(?=(?P<rest>[^\s*]*))(?P=rest)(?!\*)")
# A GFM table's delimiter row ("--|--", "| :-: | --- |"), quote marks allowed before it.
TABLE_DELIM = re.compile(r"^[ \t>]*(?:\|[ \t]*)?:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)*(?:\|[ \t]*)?\r?$", re.M)
TABLE_ROW = re.compile(r"^[ \t>]*\|", re.M)
# The ">" marks that start a quote line, nested ones too ("> >", ">>").
QUOTE_MARKS = re.compile(r"(?:[ \t]*>)+")
# After its marks, a quote line that starts a block of its own inside the quote: a blank quote
# line (">", "> >"), a list item, heading or fence, as EMPHASIS resets outside a quote.
QUOTE_BREAK = re.compile(r"[ \t]*(?:\r?(?:\n|\Z)|(?:[-*+]|\d{1,2}[.)])[ \t]|#{1,6}[ \t]|```|~~~)")


def _same_quote(text, end):
    """Whether the quote line at end (after its newline) goes on the paragraph of the line
    before: that line is a quote line of the same depth, and this one starts no block. A line
    one level deeper starts a nested quote; one level less is taken as a new block too."""
    before = QUOTE_MARKS.match(text, text.rfind("\n", 0, end - 1) + 1)
    here = QUOTE_MARKS.match(text, end)
    return (before is not None and here is not None
            and before.group().count(">") == here.group().count(">")
            and not QUOTE_BREAK.match(text, here.end()))
DUNDER_BODY = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")
# A URL as _plain() masks it: its marks are no emphasis. The scheme and the characters are as
# in INVARIANT's url, so a URL ends where its token does ("https://x.io/a—_Paris_").
URL_SPAN = re.compile(rf"[A-Za-z][A-Za-z0-9+.-]{{0,30}}://(?:{WORD}|[-.~:/?\#\[\]@!$&()*+,;=%])+")
# What ends a URL span but is not masked: sentence punctuation, closing brackets and the closing
# marks of an emphasis around the URL ("**https://x.io/a**,").
URL_TAIL = "*_.,;:!?)]}"
BACKTICKS, BLANK_LINE = re.compile("`+"), re.compile(r"\n[ \t\r]*\n")
# A run of marks at a word edge (see _edge_free): the whole run, no letter or digit before it or
# none after it.
EDGE_RUN = re.compile(rf"(?<![*_])(?:(?<!{ALNUM})[*_]+|[*_]+(?![*_]|{ALNUM}))")
CODE_MARK = "\0"     # marks, in the mask of the edge-free copy, a mark of an edge run in code


def _url_spans(text):
    """The (start, end) of each URL of text, the marks and punctuation that end it aside."""
    return [(u.start(), u.start() + len(u.group().rstrip(URL_TAIL))) for u in URL_SPAN.finditer(text)]


INDENT = re.compile(r"[ \t]*")
LIST_ITEM = re.compile(r"(?:[-*+]|\d{1,9}[.)])(?:[ \t]|\r?$)")
HTML_CODE = re.compile(r"<(code|pre)(?=[\s>/])[^<>]*>", re.I)
HTML_CLOSE = {"code": re.compile(r"</code\s*>", re.I), "pre": re.compile(r"</pre\s*>", re.I)}


def _indented_code_spans(text):
    """The (start, end) of each indented code block of text: lines indented by four columns or
    more (a tab to the next multiple of four), the first after a blank line or at the start and
    not inside a list (a list item's lines go on after a blank line, up to a line indented less
    than four that is no list item), and the next ones up to a line indented less (blank lines
    inside go with the block). An indented line that goes on a paragraph or list item is no code:
    a mark there stays emphasis, as before."""
    spans, pos, n = [], 0, len(text)
    after_blank, in_list, block = True, False, None
    while pos <= n:
        nl = text.find("\n", pos)
        end = n if nl < 0 else nl
        ws = INDENT.match(text, pos, end).end()
        if text[ws:end] in ("", "\r"):
            after_blank = True
        else:
            width = 0
            for c in text[pos:ws]:
                width = width + 4 - width % 4 if c == "\t" else width + 1
            if width >= 4 and (block is not None or after_blank and not in_list):
                block = (pos if block is None else block[0], end)
            else:
                if block is not None:
                    spans.append(block)
                    block = None
                if width < 4:
                    if LIST_ITEM.match(text, ws, end):
                        in_list = True
                    elif after_blank:
                        in_list = False
            after_blank = False
        if nl < 0:
            break
        pos = nl + 1
    if block is not None:
        spans.append(block)
    return spans


def _html_code_spans(text):
    """The (start, end) of each "<code>...</code>" (within one paragraph) and "<pre>...</pre>"
    of text, tag names in any case. Linear: the next closing tag of each name is searched for
    once and kept until an opening tag comes after it."""
    spans, next_close, end = [], {}, 0
    blanks = None
    for m in HTML_CODE.finditer(text):
        if m.start() < end:
            continue
        name = m.group(1).lower()
        close = next_close.get(name, False)
        if close is not False and close is not None and close.start() < m.end():
            close = False
        if close is False:
            close = next_close[name] = HTML_CLOSE[name].search(text, m.end())
        if close is None:
            continue
        if name == "code":
            if blanks is None:
                blanks = [x.start() for x in BLANK_LINE.finditer(text)]
            if bisect.bisect_left(blanks, m.end()) != bisect.bisect_left(blanks, close.start()):
                continue
        spans.append((m.start(), close.end()))
        end = close.end()
    return spans


def _code_spans(text):
    """The sorted, disjoint (start, end) of the code of text: indented code blocks, "<code>" and
    "<pre>" elements (see _indented_code_spans and _html_code_spans) and each inline code span,
    a run of backticks up to the next run of as many, within one paragraph (an unclosed run is a
    literal; a run inside a block is code, not a delimiter). Linear: the next run of each length
    is found once, from the right."""
    blocks = sorted(_indented_code_spans(text) + _html_code_spans(text))
    inside = _Spans(blocks, True)
    runs = [(m.start(), m.end()) for m in BACKTICKS.finditer(text) if not inside.holds(m.start())]
    spans = []
    if len(runs) >= 2:
        blanks = [m.start() for m in BLANK_LINE.finditer(text)]
        after, last = [None] * len(runs), {}
        for i in range(len(runs) - 1, -1, -1):
            n = runs[i][1] - runs[i][0]
            after[i], last[n] = last.get(n), i
        i = 0
        while i < len(runs):
            j = after[i]
            if j is not None and bisect.bisect_left(blanks, runs[i][1]) == bisect.bisect_left(blanks, runs[j][0]):
                spans.append((runs[i][0], runs[j][1]))
                i = j + 1
            else:
                i += 1
    merged = []
    for a, b in sorted(blocks + spans):
        if merged and a < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def _table_spans(text):
    """The (start, end) of the table lines of text, each with its newline: a line that starts
    with "|" (after quote marks), and a GFM table, from its header line (the line before a
    delimiter row that holds a "|") up to a blank line. A "|" or a line end there ends a block
    of emphasis; a "|" elsewhere is text."""
    spans = []
    for m in TABLE_ROW.finditer(text):
        nl = text.find("\n", m.end())
        spans.append((m.start(), len(text) if nl < 0 else nl + 1))
    blanks = None
    for m in TABLE_DELIM.finditer(text):
        if "|" not in m.group() or m.start() == 0:
            continue
        if blanks is None:
            blanks = [x.start() for x in BLANK_LINE.finditer(text)]
        k = bisect.bisect_left(blanks, m.end())
        stop = len(text) if k == len(blanks) else blanks[k] + 1
        spans.append((text.rfind("\n", 0, m.start() - 1) + 1, stop))
    merged = []
    for a, b in sorted(spans):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


class _Spans:
    """Whether positions, asked in increasing order, fall inside sorted (start, end) spans."""

    def __init__(self, spans, edge):
        self.spans, self.i, self.edge = spans, 0, edge   # edge: a span's start counts as inside

    def holds(self, pos):
        spans = self.spans
        while self.i < len(spans) and spans[self.i][1] <= pos:
            self.i += 1
        return self.i < len(spans) and (spans[self.i][0] < pos or self.edge and spans[self.i][0] == pos)


def _plain(text):
    """text without the marks of emphasis (see EMPHASIS). Linear: each run is pushed and popped
    at most once, whether a word glued to a mark holds a "_" is counted, not scanned (nested
    pairs would scan the same text again), and a quote line looks back over one line only."""
    drop, opened, edges = [], {}, None
    urls, codes = _Spans(_url_spans(text), False), _Spans(_code_spans(text), True)
    tables = None

    def glued_identifier(a, b, forward):
        """Whether the word characters glued to a (forward) or to b (backward) within text[a:b]
        hold a "_": the mark there is part of an identifier ("_private_key", "api_key_")."""
        nonlocal edges
        if edges is None:
            edges = ([m.start() for m in re.finditer(r"\W", text)], [m.start() for m in re.finditer("_", text)])
        others, unders = edges
        if forward:
            k = bisect.bisect_left(others, a)
            b = min(others[k], b) if k < len(others) else b
        else:
            k = bisect.bisect_left(others, b)
            a = max(others[k - 1] + 1, a) if k else a
        return bisect.bisect_left(unders, b) > bisect.bisect_left(unders, a)

    for m in EMPHASIS.finditer(text):
        if urls.holds(m.start()) or codes.holds(m.start()):
            continue                          # a mark inside a URL ("?_k_=1") or code is no emphasis
        kind, run = m.lastgroup, m.group()
        if kind in ("pipe", "nl", "quote"):
            if tables is None:
                tables = _Spans(_table_spans(text), True)
            if tables.holds(m.start()):
                kind = None                   # a cell or row of a table ends the block
            elif kind != "quote":
                continue                      # a "|" or line end of prose is text
        if kind == "open" and run == "*" and GLOB.match(text, m.end()):
            continue                          # "*.log": a glob, no emphasis
        if kind == "open" and run[0] == "_" and opened.get(run) and UNDERSCORE_CLOSE.match(text, m.start()):
            kind = "close"                    # "_27%_,": between punctuation, it closes (an opening
                                              # run is a whole run of at most three, so is the match)
        if kind == "open":
            opened.setdefault(run, []).append(m)
        elif kind == "close":
            stack = opened.get(run)
            if stack:
                o = stack.pop()
                if run[0] != "_":
                    drop += [o.span(), m.span()]
                elif not (run == "__" and DUNDER_BODY.fullmatch(text, o.end(), m.start())):
                    if not glued_identifier(o.end(), m.start(), True):
                        drop.append(o.span())
                    if not glued_identifier(o.end(), m.start(), False):
                        drop.append(m.span())
        elif kind == "quote" and _same_quote(text, m.end()):
            continue                          # the next line of the same quote paragraph
        else:
            opened.clear()                    # emphasis does not run past a blank line, into a
                                              # list item, heading, quote or fence, or out of a
                                              # table cell or row
    if not drop:
        return text
    drop.sort()
    out, pos = [], 0
    for a, b in drop:
        out.append(text[pos:a])
        pos = b
    out.append(text[pos:])
    return "".join(out)


def _edge_free(text):
    """(scan, raw, mask): text without the mark runs at a word edge (see EMPHASIS, scan 2),
    outside URLs and code spans. Inside a code span raw keeps them, scan has a NUL (no word
    character) for each mark and mask has CODE_MARK there and a space elsewhere, so the three
    are as long as each other and _scan(scan, raw, mask) can take a token glued to them with
    its marks. A NUL of text itself is no code mark: the mask, not the character, tells."""
    urls, codes = _Spans(_url_spans(text), False), _Spans(_code_spans(text), True)
    scan, raw, mask, pos = [], [], [], 0
    for m in EDGE_RUN.finditer(text):
        a, b = m.span()
        if urls.holds(a):
            continue
        scan.append(text[pos:a])
        raw.append(text[pos:a])
        mask.append(" " * (a - pos))
        if codes.holds(a):
            scan.append("\0" * (b - a))
            raw.append(m.group())
            mask.append(CODE_MARK * (b - a))
        pos = b
    scan.append(text[pos:])
    raw.append(text[pos:])
    mask.append(" " * (len(text) - pos))
    return "".join(scan), "".join(raw), "".join(mask)


def _cut(text, spans):
    """text without the sorted, disjoint spans."""
    out, pos = [], 0
    for a, b in spans:
        out.append(text[pos:a])
        pos = b
    out.append(text[pos:])
    return "".join(out)


def _scan(text, raw=None, mask=None):
    """Return ({token: kind}, {token: extensions}): the fact-bearing tokens of text in order of
    appearance, and for each token but a URL or a number the set of the ways text writes it
    (see _extension); NOT_EXTENDED in it means the text writes the token on its own at least
    once (see EXT_RIGHT). text has been through _plain(), or is the scan copy of _edge_free()
    and raw and mask its raw copy and mask: then a token glued to a code mark is taken from raw
    with the marks glued to it, of kind "code", and every extension is read in raw, where
    present() looks."""
    code = raw is not None
    if not code:
        text = raw = LIST_MARKER.sub("", text)
    else:
        markers = [m.span() for m in LIST_MARKER.finditer(text)]
        text, raw, mask = _cut(text, markers), _cut(raw, markers), _cut(mask, markers)
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
            end, how = start + len(part), kind
            if code and (mask.startswith(CODE_MARK, end) or start and mask[start - 1] == CODE_MARK):
                while start and mask[start - 1] == CODE_MARK:
                    start -= 1
                while mask.startswith(CODE_MARK, end):
                    end += 1
                if not (LEFT_AT.match(raw, start) and RIGHT_AT.match(raw, end)):
                    continue        # "`__tests__/`": the "/" in "\0\0/" is no token of its own
                part, how = raw[start:end], "code"      # "`__FILE__`": the marks are code
            if how not in ("url", "number"):
                extensions.setdefault(part, set()).add(_extension(raw, start, end, how, part))
            if part not in found:
                found[part] = how
    return found, extensions


def _hidden(strict, edge_free):
    """[(token, kind)] of the edge-free scan's tokens (see EMPHASIS) the strict scan does not
    find, nor finds with marks at its edges ("_private_key", "https://x.io/a_" are judged by
    the strict scan, and their edge-free forms are no other token)."""
    known = set(strict).union(t.strip("*_") for t in strict)
    return [(t, k) for t, k in edge_free.items() if t not in known]


def invariants(text):
    """Return {token: kind} for every fact-bearing token in text, in order of appearance: those
    of the strict scan, then those only the edge-free scan finds (see EMPHASIS)."""
    found = _scan(_plain(text))[0]
    found.update(_hidden(found, _scan(*_edge_free(text))[0]))
    return found


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
# present() tries a token at each start of its first run, or at each place text.find() finds
# it, whichever costs less: a Python step per start, or a C scan of the text. FIND_COST is how
# many characters the scan passes in the time of one step. With many distinct tokens sharing a
# run (paths under one "src/", at many depths or lengths), a run that repeats is scanned for
# instead of walked once per token. Both try every place a match can start, so the result is
# the same; neither keeps anything per token.
FIND_COST = 1024


def word_index(text):
    """{run: [start, ...]} for every maximal run of word characters in text."""
    index = {}
    for m in WORD_RUN.finditer(text):
        index.setdefault(m.group(), []).append(m.start())
    return index


def _forms(tok, kind):
    """(forms, left, right): the forms of the token in the order a pattern would try them (an
    optional part present first), so the first that fits at a position is the match there, and
    the boundaries before and after it."""
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
    return forms, left, right


def _counts(text, start, end, kind, tok, alone, extensions):
    """Whether the match text[start:end] of tok counts (see present())."""
    if not alone and extensions is None:
        return True
    how = _extension(text, start, end, kind, tok)
    return how == NOT_EXTENDED or not alone and how in extensions


def _in_calendar(tok, kind, text):
    """Whether text holds a Hebrew form of the month or weekday name tok. A Hebrew form stands
    between Hebrew-letter boundaries, with up to three prefix letters (במאי, ממאי, ובמאי);
    "מאיפה" or "לשבת" is another word, not the month or the day. Only a capitalised name or a
    full name in capitals is a month or weekday: "DEC" and "SAT" are acronyms, not דצמבר and
    שבת."""
    if kind == "proper" or tok.lower() in CALENDAR_FULL:
        forms = [rf"(?<![{HEB}])[ובלמהשכ]{{0,3}}" + re.escape(form) + rf"(?![{HEB}])"
                 for form in CALENDAR.get(tok.lower(), ())]
        if forms and re.search("(?:" + "|".join(forms) + ")", text):
            return True
    return False


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
    forms, left, right = _forms(tok, kind)

    def found(pos):
        """Whether the token is at pos: the first form that fits there, if it counts."""
        if left.match(text, pos):
            for form in forms:
                if text.startswith(form, pos) and right.match(text, pos + len(form)):
                    return _counts(text, pos, pos + len(form), kind, tok, alone, extensions)
        return False

    first = WORD_RUN.match(tok)
    positions = None
    if kind != "time" and first:
        # left is L here: a match starts where a run of word characters starts, and that run
        # is the token's own first run (the token goes on with a non-word character or ends,
        # and R refuses a word character after it).
        if index is None:
            index = word_index(text)
        positions = index.get(first.group(), ())
        if len(positions) * FIND_COST > len(text):
            positions = None                    # a scan for the token costs less (FIND_COST)
    if positions is not None:
        if any(found(pos) for pos in positions):
            return True
    else:
        prefix, pos = os.path.commonprefix(forms), 0
        while True:                         # every match, overlapping ones too
            pos = text.find(prefix, pos)
            if pos < 0:
                break
            if found(pos):
                return True
            pos += 1
    return _in_calendar(tok, kind, text)


def present_all(items, text, tokens=None, index=None):
    """[present(tok, kind, text, tokens, alone, index, extensions) for each (tok, kind, alone,
    extensions) of items], the same results. Many tokens of one length that share a first run
    ("__/a1" ... "__/a9999"), or that start with the same mark ("*a1" ... "*a9999" in code), are
    looked up in one walk over that run's starts (or the mark's places), each start
    reading one slice per length: a walk costs a step per start, present() a step per start or
    FIND_COST characters per token, so the tokens of a length are walked together when that
    costs less than looking each up alone. Linear in the starts times the lengths walked."""
    result, groups = [None] * len(items), {}
    for i, (tok, kind, alone, extensions) in enumerate(items):
        first = WORD_RUN.match(tok)
        if tok and kind not in ("number", "url", "time", "datetime"):    # one form: tok
            # a token that starts with a mark ("*a1" in code) by its first character
            key = first.group() if first else (tok[0],)
            groups.setdefault(key, {}).setdefault(len(tok), []).append(i)
    if index is None and any(type(run) is str for run in groups):
        index = word_index(text)
    for run, by_length in groups.items():
        if type(run) is str:
            positions = index.get(run, ())
        else:                                   # every place present()'s scan would try
            positions = [m.start() for m in re.finditer(re.escape(run[0]), text)]
        # what present() costs a token: its walk, or its scan when that costs less
        alone_cost = len(positions) if len(positions) * FIND_COST <= len(text) else len(text) / FIND_COST
        walked = {n: members for n, members in by_length.items()
                  if len(members) > 1 and len(positions) < len(members) * alone_cost}
        if not walked:
            continue
        by_form, waiting = {}, 0
        for members in walked.values():
            for i in members:
                by_form.setdefault(items[i][0], []).append(i)
                result[i], waiting = False, waiting + 1
        for pos in positions:
            if not LEFT_AT.match(text, pos):
                continue
            for n in walked:
                for i in by_form.get(text[pos:pos + n], ()):
                    tok, kind, alone, extensions = items[i]
                    if (not result[i] and (RIGHT_DATE_AT if kind == "date" else RIGHT_AT).match(text, pos + n)
                            and _counts(text, pos, pos + n, kind, tok, alone, extensions)):
                        result[i], waiting = True, waiting - 1
            if not waiting:
                break
        for members in walked.values():
            for i in members:
                if not result[i]:
                    result[i] = _in_calendar(items[i][0], items[i][1], text)
    return [present(tok, kind, text, tokens, alone, index, extensions) if r is None else r
            for r, (tok, kind, alone, extensions) in zip(result, items)]


def _after_word(text, start, digit=False):
    """True when the last character before start on its line, spaces, tabs and emphasis marks
    aside ("Ticket **No. 5**", "ticket_no. 5"), is a letter or a digit (a digit only, with
    digit)."""
    i = start - 1
    while i >= 0 and text[i] in " \t*_":
        i -= 1
    return i >= 0 and (text[i].isdigit() if digit else text[i].isalnum())


def _negation_counts(text):
    """(definite, ambiguous): the negations of text but a "No. N" that is a number sign, and of
    them those that may be one ("no. N" before a number, read as the answer "no": "ticket no. 5",
    "(No. 5)", "A: No. 5")."""
    n, ambiguous = len(NEG_HE.findall(text)), 0
    for m in NEG_EN.finditer(text):
        word = m.group()
        if word.lower() == "no" and NUMBER_SIGN.match(text, m.end()):
            if not _after_word(text, m.start(), digit=word not in ("No", "NO")):
                ambiguous += 1              # "(No. 5)", "ticket no. 5"
            continue                        # "Ticket No. 5", "Item 3 no. 5": a number sign
        n += 1
    return n, ambiguous


def negations(text, rendering_of=None):
    """The number of negations in text. For a rendering of the source rendering_of, an
    ambiguous "No. N" (see _negation_counts) counts only as often as the source has one, so it
    cannot stand in for a negation the rendering dropped ("Do not deploy. Ticket No. 5." ->
    "Deploy. ticket no. 5.", "Deploy. Ticket: No. 5.", "Deploy (No. 5).")."""
    n, ambiguous = _negation_counts(text)
    if rendering_of is not None:
        ambiguous = min(ambiguous, _negation_counts(rendering_of)[1])
    return n + ambiguous


# C2: a dunder ("__init__") is kept whole by the strict scan, though CommonMark shows "__word__"
# in prose as a bold "word". A dunder token is also present where the rendering holds its word
# alone ("__tools__" as "tools" or "**tools**"), when the word holds no "_", is no name that
# Python, C or JavaScript tooling gives a dunder (KNOWN_DUNDERS: "__init__", "__pycache__",
# "__mocks__" stay strict), and every source occurrence reads as emphasis: in no code span, and
# not glued to a path, call or member ("x.__tools__", "__tools__()", "src/__tools__/"). Code is
# verbatim, so "`__tools__`" anywhere in the source keeps "__tools__" strict.
KNOWN_DUNDERS = frozenset("""
    abs add aenter aexit aiter all and anext annotations args await base bases bool buffer
    builtins bytes cached call cause ceil class classcell closure cmp code coerce complex
    contains context copy deepcopy defaults del delattr delete delitem dict dir div divmod doc
    enter eq exit file float floor floordiv format fspath func future ge get getattr
    getattribute getitem getnewargs getslice getstate globals gt hash hex iadd iand idiv
    ifloordiv ilshift imatmul imod import imul index init instancecheck int invert ior ipow
    irshift isub iter itruediv ixor kwdefaults le len loader long lshift lt main matmul members
    metaclass missing mod module mro mul name ne neg new next nonzero notes oct or orig origin
    package parameters path pos pow prepare qualname radd rand rdiv rdivmod reduce repr reversed
    rfloordiv rlshift rmatmul rmod rmul ror round rpow rrshift rshift rsub rtruediv rxor self
    set setattr setitem setstate signature sizeof slots spec str sub subclasses subclasshook
    traceback truediv trunc unicode version weakref wrapped xor
    author copyright credits email license maintainer status title summary uri url
    pycache pypackages tests test mocks snapshots fixtures generated
    attribute asm inline restrict volatile typeof extension builtin cplusplus stdc gnuc
    linux unix i386 x86 arm aarch64 clang llvm apple mips
    proto dirname filename esmodule webpack
""".split())
BOLD_DUNDER = re.compile(rf"{L}__([a-z][a-z0-9]*)__(?!{WORD})")
BOLD_WORD = re.compile(rf"{L}(__|)([a-z][a-z0-9]*)\1(?!{WORD})")


def _word_counts(text):
    """How often each lowercase word stands in text, alone or as a dunder: the rendering must
    hold the word of a bold dunder as often as the source does ("__tools__" changed into
    "__bools__" is no pass for "tools" written elsewhere in it). One pass."""
    return collections.Counter(m.group(2) for m in BOLD_WORD.finditer(text))


def _bold_dunders(text):
    """The dunder tokens of text (through _plain()) that CommonMark shows as a bold word (see
    KNOWN_DUNDERS). Linear: one pass, the code spans asked in order."""
    codes, ok = _Spans(_code_spans(text), True), {}
    for m in BOLD_DUNDER.finditer(text):
        a, b = m.span()
        before, after = text[a - 1:a], text[b:b + 2]
        prose = (m.group(1) not in KNOWN_DUNDERS and not codes.holds(a)
                 and before not in tuple("/\\.:~@=-") and not after.startswith(("/", "\\", "(", "["))
                 and not (after[:1] == "." and WORD_CHAR.match(after, 1)))
        ok[m.group()] = ok.get(m.group(), True) and prose
    return {t for t, prose in ok.items() if prose}


# G4: code with "_" marks on its left only ("`_Config`", "`__Init`") may be put in "*"
# emphasis whole ("**_Config**"): CommonMark shows the "_" as written, as the "_" run cannot
# pair inside. STAR_WRAPPED finds such a wrapping (whitespace, an opening bracket or quote, or
# nothing before it; no "*" glued on either side) for check() to look the code up in a copy
# without it. Code with "_" on both sides is not taken: CommonMark shows "**__FILE__**" as a
# bold "FILE", so the rendering lost the marks. A wrapping inside code is shown as written.
STAR_WRAPPED = re.compile(r"""(?<![^\s(\[{"'])(\*{1,3})(?=_)(?P<body>[^\s*]*)(?<=[^\W_])\1(?!\*)""")


def _unwrap_stars(text):
    """text with each STAR_WRAPPED wrapping outside code replaced by its body: in code the "*"
    are shown as written ("`*_Paris*`" is no "_Paris"). Linear: the code spans are asked in
    order."""
    codes = _Spans(_code_spans(text), True)

    def body(m):
        if codes.holds(m.start()) or codes.holds(m.end() - 1) or "`" in m.group("body"):
            return m.group()
        return m.group("body")
    return STAR_WRAPPED.sub(body, text)


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
    items = [(t, k, NOT_EXTENDED in extensions.get(t, (NOT_EXTENDED,)), extensions.get(t)) for t, k in inv.items()]
    missing, bold, words = [], None, None
    for (t, k, alone, ext), found in zip(items, present_all(items, plain, rendered, index)):
        if found:
            continue
        if t.startswith("__") and k == "snake":
            bold = _bold_dunders(_plain(source)) if bold is None else bold
            if t in bold and present(t[2:-2], k, plain, rendered, alone, index, ext):
                if words is None:
                    words = (_word_counts(_plain(source)), _word_counts(plain))
                if words[1][t[2:-2]] >= words[0][t[2:-2]]:
                    continue                  # "__tools__" shown bold as "tools" (see KNOWN_DUNDERS)
        missing.append(t)
    # The edge-free scan (see EMPHASIS): a token a mark hid from the strict one is looked up in
    # the rendering's edge-free copy, through the same functions.
    inv2, extensions2 = _scan(*_edge_free(source))
    extra = _hidden(inv, inv2)
    if extra:
        scan, raw, mask = _edge_free(rendering)
        rendered2, index2, unwrapped = _scan(scan, raw, mask)[0], word_index(raw), None
        items = [(t, k, NOT_EXTENDED in extensions2.get(t, (NOT_EXTENDED,)), extensions2.get(t)) for t, k in extra]
        code = [item for item in items if item[1] == "code"]
        # Code is compared as written: "__FILE__" anywhere in the rendering, in code or not, and
        # not extended ("/x/__FILE__") but as the source extends it.
        found_code = iter(present_all(code, rendering, None, word_index(rendering)) if code else ())
        found_other = iter(present_all([item for item in items if item[1] != "code"], raw, rendered2, index2))
        for t, k, alone, ext in items:
            found = next(found_code) if k == "code" else next(found_other)
            if not found and k == "code" and t[0] == "_" and t[-1] != "_" and "*" not in t:
                if unwrapped is None:         # "`_Config`" as "**_Config**" (see STAR_WRAPPED)
                    copy = _unwrap_stars(rendering)
                    unwrapped = (copy, word_index(copy))
                found = present(t, k, unwrapped[0], None, alone, unwrapped[1], ext)
            if not found:
                missing.append(t)
    source_hedges, rendering_hedges = hedges(source), hedges(rendering)
    missing_hedges = [group for group in source_hedges if group not in rendering_hedges]
    ns, nr = negations(source), negations(rendering, rendering_of=source)
    # An empty source has nothing to check either: INCONCLUSIVE, never a vacuous PASS.
    inconclusive = not inv and not extra and not source_hedges
    ok = not missing and not missing_hedges and nr >= ns and not inconclusive
    return CheckResult(ok, missing, missing_hedges, ns, nr, len(inv) + len(extra), inconclusive)


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
