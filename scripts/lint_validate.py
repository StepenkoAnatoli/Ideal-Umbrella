"""Compare old vs new abbreviation rule on real repo text and on known invented abbreviations.

Usage: python -I scripts/lint_validate.py <old keyline_lint.py> [corpus folder]
The new rule is the keyline_lint.py in this repository. The corpus is every *.md file under
the corpus folder (default: the folder that holds this repository, so sibling repos count),
capped at 400 files.
"""
import collections
import glob
import importlib.util
import io
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_FILES = 400


def load_old(path):
    spec = importlib.util.spec_from_file_location("old", path)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    return old


def flags(mod, words, text):
    allow = getattr(mod, "BUILTIN_ALLOW", set())
    return [m.split("'")[1] for _, m in mod.lint_text(text, words, allow) if m.startswith("abbreviation")]


def corpus_files(folder):
    pattern = os.path.join(glob.escape(str(folder)), "**", "*.md")
    files = [f for f in sorted(glob.glob(pattern, recursive=True))
             if "node_modules" not in f and "/.git/" not in f.replace("\\", "/")]
    return files[:MAX_FILES]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")   # -I ignores PYTHONUTF8: set UTF-8 output here
    if not 1 <= len(argv) <= 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    old_path = Path(argv[0])
    folder = Path(argv[1]) if len(argv) == 2 else ROOT.parent
    if not old_path.is_file():
        print(f"Error: {old_path} is not a file", file=sys.stderr)
        return 1
    if not folder.is_dir():
        print(f"Error: {folder} is not a folder", file=sys.stderr)
        return 1

    sys.path.insert(0, str(ROOT / "keyline"))
    import keyline_lint as new
    old = load_old(old_path)
    words = new.load_words()

    # corpus: markdown across the repos next to this one (real human/agent prose)
    files = corpus_files(folder)
    text = []
    for f in files:
        try:
            text.append(open(f, encoding="utf-8", errors="ignore").read())
        except OSError:
            pass
    corpus = "\n".join(text)
    o = collections.Counter(flags(old, words, corpus))
    n = collections.Counter(flags(new, words, corpus))
    print(f"corpus: {len(files)} files, {len(corpus)} chars")
    print(f"old rule: {len(o)} distinct words flagged; new rule: {len(n)} distinct words flagged")
    print("new rule still flags (top 40 by count):", ", ".join(f"{w}({c})" for w, c in n.most_common(40)))
    print("sample of words the old rule flagged and the new rule lets through:",
          ", ".join(w for w, _ in (o - n).most_common(40)))
    real = ("worktree uncommitted unpushed branched harmlessly octopus amends rework reworks rerun asctime "
            "autocollect dryrun countersignature cp1252 sha256 utf8 x2 b07b3b6 d7c00f96a17c35e6c47c5ba1f7e3a9160c966042")
    invented = "alrt rst xh k8s i18n a11y mgmt pkts srvc sref"
    print("\nreal words flagged by new rule:", flags(new, words, real) or "none")
    inv_multi = [w for w in invented.split() if w not in words]
    print("invented abbreviations that are multi-token:", inv_multi)
    print("of those, flagged by new rule:", flags(new, words, " ".join(inv_multi)))
    return 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.exit(main())
