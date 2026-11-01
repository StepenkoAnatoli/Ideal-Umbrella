"""keyline_hook.py - Claude Code PostToolUse hook for Write/Edit on machine notes.

Usage:
  pipe a PostToolUse event on stdin, or
  python keyline_hook.py --print-config   print a ready-to-paste hook entry for this install

Reads the hook event JSON on stdin. Acts only on .txt, .md, .keyline or extension-less files
inside a notes/ or plans/ folder of the project (a file outside the project, and a dotfile or a
file in a dotted folder below notes/ or plans/, is ignored), or, when one or more --watch PATTERN
arguments are given, only on files matching those patterns instead (fnmatch, case-insensitive; an
absolute pattern is matched against the absolute path, a relative one against the path relative to
the project dir; the suffix rule still applies, so a watched .py file is passed over).
Example: keyline_hook.py --watch /path/to/project/PROGRESS.md
A rendering is the note's name with .he.txt, .he.md or .he.keyline in place of its extension
(any case: c.HE.TXT counts).
  - a note (incident.txt, notes.md): run keyline_lint.py on it, and run keyline_check.py
    note -> rendering for every sibling rendering (incident.he.txt, incident.he.md ...);
  - a rendering (incident.he.txt): run keyline_check.py against every note with its stem
    (incident.txt / .md / .keyline / no extension); a rendering is not linted.
Exit 0 when clean or not applicable. Exit 2 with the findings on stderr when anything fails:
for PostToolUse the file is already written, and Claude Code shows stderr to Claude so it fixes it.
Exit 1 (non-blocking, one line on stderr) when a file cannot be read, tiktoken is missing, or an
argument is wrong (a --watch without a pattern, or anything else besides --print-config).
"""
import fnmatch
import io
import json
import os
import stat
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import keyline_check  # noqa: E402
import keyline_lint  # noqa: E402

WATCHED_DIRS = {"notes", "plans"}
NOTE_SUFFIXES = {".txt", ".md", ".keyline", ""}
# A rendering is a note's name with .he before one of these; matched without regard to case.
HE_SUFFIXES = (".he.txt", ".he.md", ".he.keyline")


def _quote(value):
    if os.name == "nt":
        return '"' + str(value).replace('"', '\\"') + '"'
    import shlex

    return shlex.quote(str(value))


def print_config():
    """Print a hook entry that points at this interpreter and this keyline folder."""
    command = f"{_quote(sys.executable)} -I {_quote(HERE / 'keyline_hook.py')}"
    print(json.dumps({
        "hooks": {
            "PostToolUse": [{
                "matcher": "Write|Edit",
                "hooks": [{"type": "command", "command": command, "timeout": 30}],
            }]
        }
    }, indent=2))



def _norm(p):
    return str(p).replace("\\", "/").lower()


def watched(path, root, patterns=()):
    if patterns:
        absolute = _norm(path.resolve())
        try:
            rel = _norm(path.resolve().relative_to(Path(root).resolve()).as_posix())
        except (ValueError, OSError):
            rel = None
        for pat in patterns:
            pat_n = _norm(pat)
            if Path(pat).is_absolute():
                if fnmatch.fnmatchcase(absolute, pat_n):
                    return True
            elif rel is not None and fnmatch.fnmatchcase(rel, pat_n):
                return True
        return False
    # The path as written first (a notes/ folder that is a symlink to Dropbox stays inside the
    # project), then with symlinks resolved; a file outside the project by both readings
    # (~/notes/todo.md) is not a project note.
    for candidate, base in ((Path(os.path.abspath(path)), Path(os.path.abspath(root))),
                            (path.resolve(), Path(root).resolve())):
        try:
            rel = candidate.relative_to(base)
            break
        except (ValueError, OSError):
            continue
    else:
        return False
    # Below the watched folder, a dotfile or a dotted folder (.gitignore, .DS_Store, .obsidian/)
    # is tool state, not a note.
    for i, part in enumerate(rel.parent.parts):
        if part.lower() in WATCHED_DIRS:
            return not any(p.startswith(".") for p in rel.parts[i + 1:])
    return False


def he_suffix(path):
    """The rendering suffix of path (any case), or None when it is not a rendering."""
    low = path.name.lower()
    return next((h for h in HE_SUFFIXES if low.endswith(h) and len(low) > len(h)), None)


def _siblings(path, names):
    """Regular files beside path whose lower-cased name is in names, in listing order."""
    found = []
    for name in sorted(os.listdir(path.parent)):
        cand = path.with_name(name)
        if name.lower() in names and cand != path and cand.is_file():
            found.append(cand)
    return found


def renderings_for(note):
    stem = (note.name[: -len(note.suffix)] if note.suffix else note.name).lower()
    return _siblings(note, {stem + h for h in HE_SUFFIXES})


def notes_for(rendering):
    stem = rendering.name[: -len(he_suffix(rendering))].lower()
    return _siblings(rendering, {stem + ext for ext in NOTE_SUFFIXES})


def shown(path, root):
    try:
        return path.resolve().relative_to(Path(root).resolve()).as_posix()
    except (ValueError, OSError):
        return str(path)


def run_check(note, rendering, problems, root):
    ok, msg = keyline_check.report(shown(note, root), shown(rendering, root),
                                   keyline_check.read(note), keyline_check.read(rendering))
    if not ok:
        problems.append(msg)


def parse_watch(argv):
    """The --watch patterns in argv; ValueError for a missing or empty pattern or another argument."""
    patterns, it = [], iter(argv)
    for a in it:
        if a != "--watch":
            raise ValueError(f"unknown argument {a!r} (expected --watch PATTERN or --print-config)")
        nxt = next(it, None)
        if not nxt:
            raise ValueError("--watch needs a non-empty PATTERN")
        patterns.append(nxt)
    return patterns


def main():
    if sys.argv[1:] == ["--print-config"]:
        print_config()
        return 0
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="backslashreplace")
    try:
        patterns = parse_watch(sys.argv[1:])
    except ValueError as e:
        print(f"keyline hook: {e}", file=sys.stderr)
        return 1                                   # non-blocking: the hook entry needs fixing
    try:
        event = json.load(io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8"))
        path = Path(event["tool_input"]["file_path"])
    except Exception:
        return 0                                   # not an event this hook understands
    cwd = event.get("cwd")
    if not isinstance(cwd, str) or not cwd:       # a malformed event is not this hook's problem
        cwd = "."
    root = os.environ.get("CLAUDE_PROJECT_DIR") or cwd
    if not path.is_absolute():
        path = Path(cwd) / path
    try:
        # os.stat, not is_file(): on Python 3.14 is_file() says False for a file it cannot look at.
        try:
            regular = stat.S_ISREG(os.stat(path).st_mode)
        except (FileNotFoundError, NotADirectoryError, ValueError):   # ValueError: a NUL in the name
            regular = False
        if not regular or not watched(path, root, patterns):
            return 0
    except OSError as e:
        # A file in a folder that cannot be searched: the stat itself fails.
        print(f"keyline hook: cannot read {path}: {e.strerror or e}", file=sys.stderr)
        return 1                                   # non-blocking error
    is_rendering = he_suffix(path) is not None
    is_note = not is_rendering and path.suffix.lower() in NOTE_SUFFIXES
    if is_note:
        # The lint's word list comes from keyline/cache/, not from the note: an error there
        # (a folder in the way, tiktoken missing on a fresh clone) is reported as its own.
        try:
            words = keyline_lint.load_words()
        except (OSError, keyline_lint.TiktokenMissing) as e:
            print(f"keyline hook: {e}", file=sys.stderr)
            return 1                               # non-blocking: the note cannot be linted yet
    problems = []
    try:
        if is_rendering:
            for note in notes_for(path):
                run_check(note, path, problems, root)
        elif is_note:
            for no, msg in keyline_lint.lint_file(path, words):
                problems.append(f"{shown(path, root)}:{no}: {msg}")
            for he in renderings_for(path):
                run_check(path, he, problems, root)
    except OSError as e:
        # The note, a rendering, the folder listing or a keyline-allow.txt. An error from open()
        # carries the file name; one from read() ("<file> is not UTF-8 ...") already names it.
        msg = f"cannot read {e.filename}: {e.strerror or e}" if e.filename else str(e)
        print(f"keyline hook: {msg}", file=sys.stderr)
        return 1                                   # non-blocking error
    if problems:
        if all(p.startswith("INCONCLUSIVE") for p in problems):
            header = "keyline: the rendering could not be checked against the note; this is not a pass."
        else:
            header = "keyline: this machine note breaks the Keyline rules; fix the file."
        print(header, file=sys.stderr)
        print("\n".join(problems), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
