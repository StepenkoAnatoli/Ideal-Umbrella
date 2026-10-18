"""keyline_check.py - deterministic fact check between a source note and a rendering of it.

Extracts every date, time, version, number, percentage, UPPER_CASE identifier, file path,
CamelCase name, file name and snake_case token from SOURCE and fails if any is missing from a
RENDERING (English prose, Hebrew, JSON, markdown...). Also fails if the rendering has fewer
negation words than the source. Grown from the panel's prototype (scratchpad keyline_check.py).

Usage:
  python keyline_check.py SOURCE RENDERING [RENDERING ...]
  python keyline_check.py --list SOURCE          print what would be checked
Exit: 0 all renderings pass, 1 any rendering fails, 2 usage or read error.
"""
import re
import sys

# A token boundary on ASCII word characters only, so a Hebrew prefix glued to an identifier
# ("בv2.14.0") still counts as present, while "5" never matches inside "503" or "2.5".
L = r"(?<![A-Za-z0-9_])"
R = r"(?![A-Za-z0-9_]|\.\d)"

INVARIANT = re.compile(L + r"""(?:
      (?P<date>\d{4}-\d{2}-\d{2})
    | (?P<time>\d{1,2}:\d{2}(?::\d{2})?Z?)
    | (?P<version>v\d+(?:\.\d+)+|\d+\.\d+\.\d+(?:\.\d+)*)
    | (?P<path>(?:[A-Za-z]:)?[\w.~-]*[/\\][\w.~/\\-]*)
    | (?P<file>[\w-]{2,}(?:\.[A-Za-z][A-Za-z0-9]*)+)
    | (?P<upper>[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*)
    | (?P<camel>[A-Za-z]*[a-z][A-Z][A-Za-z0-9]*)
    | (?P<snake>_*[A-Za-z0-9]+(?:_+[A-Za-z0-9]+)+_*)
    | (?P<number>\d+(?:[.,]\d+)*(?:%|[A-Za-z]+)?)
)""" + R, re.X)

# Markdown list markers carry no fact; "1. Add ..." must not make "1" an invariant.
LIST_MARKER = re.compile(r"^\s*(?:\d+[.)]|[-*+])\s+", re.M)

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
        if kind == "snake" and "_" not in tok.strip("_"):
            continue
        tok = tok.rstrip(".")
        found.setdefault(tok, kind)
    return found


def present(tok, kind, text):
    tail = r"Z?" if kind == "time" else ""
    return re.search(L + re.escape(tok) + tail + R, text) is not None


def negations(text):
    return len(NEG_EN.findall(text)) + len(NEG_HE.findall(text))


def check(source, rendering):
    """Return (ok, missing, neg_source, neg_rendering, n_invariants)."""
    inv = invariants(source)
    missing = [t for t, k in inv.items() if not present(t, k, rendering)]
    ns, nr = negations(source), negations(rendering)
    return (not missing and nr >= ns), missing, ns, nr, len(inv)


def read(path):
    with open(path, encoding="utf-8-sig") as f:
        return f.read()


def report(src_path, out_path, source, rendering):
    ok, missing, ns, nr, n = check(source, rendering)
    if ok:
        return True, f"PASS {out_path}  ({n} invariants present, negations {ns} -> {nr})"
    lines = [f"FAIL {out_path}  (checked against {src_path})"]
    if missing:
        lines.append(f"  missing ({len(missing)}): " + ", ".join(missing))
    if nr < ns:
        lines.append(f"  negations: source {ns}, rendering {nr} ({ns - nr} lost)")
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
