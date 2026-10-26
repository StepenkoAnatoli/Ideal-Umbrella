"""keyline_hook.py - Claude Code PostToolUse hook for Write/Edit on machine notes.

Usage:
  pipe a PostToolUse event on stdin, or
  python keyline_hook.py --print-config   print a ready-to-paste hook entry for this install

Reads the hook event JSON on stdin. Acts only on .txt, .md, .keyline or extension-less files
inside a notes/ or plans/ folder of the project (a file outside the project is ignored, and so is
a dotfile such as notes/.gitignore), or, when one or more --watch PATTERN arguments
are given, only on files matching those patterns instead (fnmatch, case-insensitive; an absolute
pattern is matched against the absolute path, a relative one against the path relative to the
project dir; the suffix rule still applies, so a watched .py file is passed over, while the
dotfile rule does not when the pattern spells the dot: notes/.todo.md or notes/.* means
the dotfile, notes/* does not, as in a shell). A --watch
without a pattern, or any other flag, is an error (exit 1, one line).
Example: keyline_hook.py --watch /path/to/project/PROGRESS.md
  - a note (incident.txt, notes.md): run keyline_lint.py on it, and when a sibling rendering
    incident.he.txt or incident.he.md exists, run keyline_check.py note -> rendering;
  - a rendering (incident.he.txt, incident.he.md): run keyline_check.py against its note
    (incident.txt / .md / .keyline / no extension); more than one note beside one rendering is
    a finding of its own, from whichever of the files is written, and the check waits until one
    note is left.
Exit 0 when clean or not applicable. Exit 2 with the findings on stderr when anything fails:
for PostToolUse the file is already written, and Claude Code shows stderr to Claude so it fixes it.
The first line says which file to fix: the note when the lint found something, the rendering when
it no longer matches, or, with more than one note beside it, the note to keep. A file name is
printed as is; a byte in it that is no UTF-8 is shown as a backslash escape, not as a traceback.
Exit 1 (non-blocking, one line on stderr) when the file cannot be read or tiktoken is missing.
"""
import fnmatch
import io
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import keyline_check  # noqa: E402
import keyline_lint  # noqa: E402

WATCHED_DIRS = {"notes", "plans"}
NOTE_SUFFIXES = (".txt", ".md", ".keyline", "")
HE_SUFFIXES = (".he.txt", ".he.md")
NOTE_HEADER = "keyline: this machine note breaks the Keyline rules; fix the file."
RENDERING_HEADER = "keyline: this rendering no longer matches its machine note; fix the rendering."
TWO_NOTES_HEADER = ("keyline: more than one note beside this rendering; keep the one it renders, "
                    "then write it again.")


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
    if path.name.startswith("."):
        # notes/.gitignore, .DS_Store: not a note, unless a pattern spells the dot itself
        # (notes/.todo.md, notes/.*). fnmatch's `*` matches a leading dot; a shell glob such as
        # notes/* does not, and that is how a --watch glob is read.
        patterns = [p for p in patterns if _norm(p).rsplit("/", 1)[-1].startswith(".")]
        if not patterns:
            return False
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
    return bool({p.lower() for p in rel.parent.parts} & WATCHED_DIRS)


def rendering_suffix(path):
    """The rendering suffix of path's name (".he.txt", ".he.md"), or None for a note."""
    name = path.name.lower()
    return next((he for he in HE_SUFFIXES if name.endswith(he)), None)


def renderings_for(note):
    """The existing renderings beside a note: notes/a.txt -> notes/a.he.txt, notes/a.he.md."""
    stem = note.name[: -len(note.suffix)] if note.suffix else note.name
    return [he for he in (note.with_name(stem + suffix) for suffix in HE_SUFFIXES) if he.is_file()]


def notes_for(rendering):
    """The existing notes beside a rendering: notes/a.he.txt -> notes/a.txt, .md, .keyline, a.
    More than one is a finding (the hook cannot tell which the rendering renders)."""
    stem = rendering.name[: -len(rendering_suffix(rendering))]
    return [cand for cand in (rendering.with_name(stem + ext) for ext in NOTE_SUFFIXES) if cand.is_file()]


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
    """The --watch patterns of argv. A --watch without a pattern or any other argument is a
    ValueError: a hook command that is wrong in settings.json would otherwise fall back to
    the notes/plans rule in silence (keyline_lint's main() refuses the same shapes)."""
    patterns, it = [], iter(argv)
    for a in it:
        if a == "--watch":
            nxt = next(it, None)
            if not nxt:
                raise ValueError("--watch needs a pattern (--watch PATTERN)")
            patterns.append(nxt)
        else:
            raise ValueError(f"unknown argument {a!r} (only --watch PATTERN is accepted)")
    return patterns


def main():
    if sys.argv[1:] == ["--print-config"]:
        print_config()
        return 0
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            # errors= too: reconfigure(encoding=...) alone resets it to strict, and a file
            # name that is no UTF-8 (a surrogate escape, from the event or a listing) then
            # turned every message into a UnicodeEncodeError traceback.
            s.reconfigure(encoding="utf-8", errors="backslashreplace")
    try:
        patterns = parse_watch(sys.argv[1:])
    except ValueError as e:
        print(f"keyline hook: {e}; fix the hook command in settings.json", file=sys.stderr)
        return 1                                   # non-blocking: the hook itself is misconfigured
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
        if not path.is_file() or not watched(path, root, patterns):
            return 0
    except OSError as e:
        # A file in a folder that cannot be searched: the stat itself fails.
        print(f"keyline hook: cannot read {path}: {e.strerror or e}", file=sys.stderr)
        return 1                                   # non-blocking error
    he = rendering_suffix(path)
    is_rendering = he is not None
    is_note = not is_rendering and path.suffix.lower() in NOTE_SUFFIXES
    if is_note:
        # The lint's word list comes from keyline/cache/, not from the note: an error there
        # (a folder in the way, tiktoken missing on a fresh clone) is reported as its own.
        try:
            words = keyline_lint.load_words()
        except (OSError, keyline_lint.TiktokenMissing) as e:
            print(f"keyline hook: {e}", file=sys.stderr)
            return 1                               # non-blocking: the note cannot be linted yet
    lint_problems, problems, too_many = [], [], False
    try:
        if is_rendering:
            notes = notes_for(path)
            if len(notes) > 1:
                # Not a rendering fault: checking it against each note would show one FAIL
                # per note it does not render. Say which notes, and check once one is left.
                too_many = True
                problems.append(f"{shown(path, root)}: notes beside it: "
                                + ", ".join(shown(n, root) for n in notes))
            else:
                for note in notes:
                    run_check(note, path, problems, root)
        elif is_note:
            for no, msg in keyline_lint.lint_file(path, words):
                lint_problems.append(f"{shown(path, root)}:{no}: {msg}")
            for rendering in renderings_for(path):
                notes = notes_for(rendering)
                if len(notes) > 1:
                    # The same finding as from the rendering side: not a check against this
                    # note, which may be the one the rendering does not render.
                    too_many = True
                    problems.append(f"{shown(rendering, root)}: notes beside it: "
                                    + ", ".join(shown(n, root) for n in notes))
                else:
                    run_check(path, rendering, problems, root)
    except OSError as e:
        # The note, its rendering or a keyline-allow.txt beside it. A system error names its
        # file in e.filename; the not-UTF-8 error of keyline_check.read / keyline_lint.read has
        # no errno and its message already names the file ("<file> is not UTF-8 ...").
        if e.filename:
            print(f"keyline hook: cannot read {e.filename}: {e.strerror or e}", file=sys.stderr)
        elif e.errno is None:
            print(f"keyline hook: {e}", file=sys.stderr)
        else:
            print(f"keyline hook: cannot read {path}: {e}", file=sys.stderr)
        return 1                                   # non-blocking error
    if lint_problems or problems:
        # The first line names the file to fix: the note when the lint found something, else
        # the rendering (a note write that leaves its rendering stale is fixed in the rendering).
        print(NOTE_HEADER if lint_problems else TWO_NOTES_HEADER if too_many else RENDERING_HEADER,
              file=sys.stderr)
        print("\n".join(lint_problems + problems), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
