"""Reproduce the panel's worked examples with the three scripts.

Run from the repository root:   python -I keyline/tests/run_tests.py   (needs tiktoken)
Fixtures: the "before"/"after" strings of the SPEC worked examples in
research/panel-results.md: incident.prose.md, incident.keyline.txt,
incident.keyline.he.txt, incident.glyph.txt, notes.markdown.md, notes.keyline.txt. Two Hebrew
renderings the panel measured but did not print there come from its synth_measure.py:
notes.keyline.he.txt and incident.prose.he.txt. All are stored LF, no BOM, no trailing newline.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

T = Path(__file__).resolve().parent
K = T.parent
sys.path.insert(0, str(K))
import keyline_check  # noqa: E402

# Panel's measured counts (o200k_base, cl100k_base) from research/panel-results.md.
PANEL = {
    "incident.prose.md": (301, 302),
    "incident.keyline.txt": (204, 206),
    "incident.keyline.he.txt": (308, 594),
    "incident.prose.he.txt": (375, 742),
    "incident.glyph.txt": (182, 180),
    "notes.markdown.md": (104, 106),
    "notes.keyline.txt": (66, 68),
    "notes.keyline.he.txt": (89, 162),
}
TOLERANCE = 2

results = []


def run(script, *args):
    r = subprocess.run([sys.executable, "-I", str(K / script), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout + r.stderr


def expect(name, cond, detail=""):
    results.append((name, bool(cond), detail.strip()))


def missing_of(out):
    m = re.search(r"missing \(\d+\): (.*)", out)
    return set(m.group(1).split(", ")) if m else set()


# ---- keyline_check.py ----
code, out = run("keyline_check.py", T / "incident.keyline.txt", T / "incident.keyline.he.txt")
expect("check Keyline -> Hebrew Keyline: PASS", code == 0 and out.startswith("PASS"), out)

code, out = run("keyline_check.py", T / "incident.keyline.txt", T / "incident.glyph.txt")
expect("check Keyline -> glyph: FAIL", code == 1, out)
expect("check Keyline -> glyph: missing exactly HTTP, UTC", missing_of(out) == {"HTTP", "UTC"}, out)
expect("check Keyline -> glyph: 4 negations lost", "source 4, rendering 0 (4 lost)" in out, out)

code, out = run("keyline_check.py", T / "notes.keyline.txt", T / "notes.keyline.he.txt")
expect("check notes Keyline -> Hebrew notes: PASS", code == 0, out)

code, out = run("keyline_check.py", T / "incident.keyline.txt", T / "incident.prose.md")
expect("check Keyline -> verbose prose: PASS", code == 0, out)

# The panel said "checker PASS both directions" for prose <-> Keyline. It does not reproduce:
# the prose says "Checkout API", the Keyline note lowercased it to "checkout-api".
code, out = run("keyline_check.py", T / "incident.prose.md", T / "incident.keyline.txt")
expect("check verbose prose -> Keyline: FAIL on API only (panel claimed PASS)",
       code == 1 and missing_of(out) == {"API"}, out)

code, out = run("keyline_check.py", T / "incident.prose.md", T / "incident.prose.he.txt")
expect("check verbose prose -> Hebrew prose: PASS", code == 0, out)
he_prose = (T / "incident.prose.he.txt").read_text(encoding="utf-8")
base_only = len(re.findall(r"(?<![א-ת])(?:לא|אין|ללא|אף|מעולם)(?![א-ת])", he_prose))
expect("Hebrew prose needs prefixed negations: base list finds 1 of 4",
       base_only == 1 and keyline_check.negations(he_prose) == 4,
       f"base list {base_only}, with prefixes {keyline_check.negations(he_prose)}")

# Regression: this pair used to PASS with "0 invariants present" because the checker did not
# extract proper nouns or hedges. It must fail, and a source with no invariants must be
# INCONCLUSIVE rather than a vacuous pass.
code, out = run("keyline_check.py", T / "false-pass.source.txt", T / "false-pass.rendering.txt")
expect("check proper nouns and hedge: FAIL", code == 1 and out.startswith("FAIL"), out)
expect("check proper nouns: Postgres, Prisma and Lucia are missing",
       {"Postgres", "Prisma", "Lucia"} <= missing_of(out), out)
expect("check hedge: possibility (could) is reported lost",
       "hedges lost: possibility (could)" in out, out)

code, out = run("keyline_check.py", T / "false-pass.source.txt", T / "false-pass.source.txt")
expect("check source against itself: PASS", code == 0, out)

code, out = run("keyline_check.py", T / "no-invariants.source.txt", T / "no-invariants.rendering.txt")
expect("check source with no invariants: INCONCLUSIVE, exit 1",
       code == 1 and out.startswith("INCONCLUSIVE"), out)

# An empty source used to PASS with 0 invariants; it has nothing to check and is INCONCLUSIVE.
empty = keyline_check.check("", "anything at all")
expect("check empty source: INCONCLUSIVE, not PASS", empty.inconclusive and not empty.ok)


# ---- keyline_lint.py ----
for name in ("incident.keyline.txt", "notes.keyline.txt"):
    code, out = run("keyline_lint.py", T / name)
    expect(f"lint {name}: clean", code == 0, out)
code, out = run("keyline_lint.py", "--no-allow", T / "notes.keyline.txt")
expect("lint notes.keyline.txt without keyline-allow.txt: flags pnpm only",
       code == 1 and "'pnpm'" in out and out.count("abbreviation") == 1, out)
for name in ("notes.markdown.md", "incident.prose.md"):
    code, out = run("keyline_lint.py", T / name)
    expect(f"lint {name}: furniture found", code == 1 and "furniture" in out, out)

# Abbreviation rule (fixed 2026-10-18): real words, inflections, identifiers, hashes and common
# tool names pass; short vowel-poor tokens and numeronyms that split into several tokens fail.
import keyline_lint  # noqa: E402
_words = keyline_lint.load_words()


def abbreviations(text):
    return {m.split("'")[1] for _, m in keyline_lint.lint_text(text, _words, keyline_lint.BUILTIN_ALLOW)
            if m.startswith("abbreviation")}


REAL = ("worktree uncommitted unpushed branched harmlessly octopus amends rework reworks rerun "
        "asctime autocollect dryrun countersignature diffs slugs cp1252 sha256 utf8 x2 b07b3b6 "
        "d7c00f96a17c35e6c47c5ba1f7e3a9160c966042 mcp npx venv")
INVENTED = "alrt xh k8s i18n a11y mgmt srvc sref"
got = abbreviations(REAL)
expect("lint abbreviation: real words, identifiers and tool names pass", not got, f"flagged {sorted(got)}")
got = abbreviations(INVENTED)
expect("lint abbreviation: invented abbreviations all flagged", got == set(INVENTED.split()),
       f"flagged {sorted(got)}")

# ---- keyline_hook.py --watch (added 2026-10-18) ----
import json  # noqa: E402
import keyline_hook  # noqa: E402
target = (T / "notes.keyline.txt").resolve()
abs_pat = target.as_posix()
expect("hook --watch: absolute pattern matches forward-slash path",
       keyline_hook.watched(target, K, [abs_pat]))
# Backslash separators and case-insensitive matching are Windows path rules; on Linux and macOS
# a backslash is an ordinary filename character and case matters, so the check is Windows only.
if os.name == "nt":
    expect("hook --watch: absolute pattern matches backslash, other-case path",
           keyline_hook.watched(Path(str(target).replace("/", "\\").upper()), K, [abs_pat]))
expect("hook --watch: relative pattern matches from project dir",
       keyline_hook.watched(target, K, ["tests/notes.keyline.txt"]))
expect("hook --watch: other file in same folder not matched",
       not keyline_hook.watched((T / "notes.markdown.md").resolve(), K, [abs_pat]))


def hook(file_path, *args):
    event = json.dumps({"tool_name": "Write", "cwd": str(K), "tool_input": {"file_path": str(file_path)}})
    r = subprocess.run([sys.executable, "-I", str(K / "keyline_hook.py"), *args], input=event,
                       capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout + r.stderr


code, out = hook(T / "notes.markdown.md", "--watch", (T / "notes.markdown.md").resolve().as_posix())
expect("hook --watch: markdown at watched path exits 2 with findings", code == 2 and "furniture" in out, out)
code, out = hook(T / "notes.markdown.md", "--watch", abs_pat)
expect("hook --watch: markdown at unwatched path exits 0", code == 0, out)

# ---- measure.py ----
code, out = run("measure.py", T)
measured = {}
for line in out.splitlines():
    m = re.match(r"\s*(\d+)\s+(\d+)\s+\d+\s+(.+)$", line)
    if m and not m.group(3).startswith("total"):
        measured[Path(m.group(3)).name] = (int(m.group(1)), int(m.group(2)))
rows = []
for name, (po, pc) in PANEL.items():
    o, c = measured.get(name, (None, None))
    ok = o is not None and abs(o - po) <= TOLERANCE and abs(c - pc) <= TOLERANCE
    expect(f"measure {name}: within {TOLERANCE} of panel", ok, f"{o}/{c} vs {po}/{pc}")
    rows.append((name, po, o, pc, c))

# ---- report ----
print(f"{'file':26} {'panel o200k':>11} {'now':>5} {'panel cl100k':>12} {'now':>5}")
for name, po, o, pc, c in rows:
    print(f"{name:26} {po:>11} {o!s:>5} {pc:>12} {c!s:>5}")
print()
for name, ok, detail in results:
    print(f"{'ok  ' if ok else 'FAIL'} {name}")
    if not ok and detail:
        print("     " + detail.replace("\n", "\n     "))
failed = sum(not ok for _, ok, _ in results)
print(f"\n{len(results) - failed}/{len(results)} passed")
sys.exit(1 if failed else 0)
