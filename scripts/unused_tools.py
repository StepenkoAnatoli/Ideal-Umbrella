"""Count tool calls across Claude Code transcripts and flag denied tools that were used.

Keeps permissions.deny honest: tools get added and renamed, and denying one you actually
call breaks sessions quietly. The deny list is read from config/user-settings.json.

Usage: python -I scripts/unused_tools.py <transcripts dir> [--top N]
Transcripts are the *.jsonl files Claude Code writes under ~/.claude/projects.
"""
import argparse
import collections
import errno
import json
import os
import stat
import sys
from pathlib import Path

USER_SETTINGS = Path(__file__).resolve().parents[1] / "config" / "user-settings.json"


def _is(path, kind):
    """kind(mode) for a path that is there, False for one that is not; any other OSError (a
    folder that cannot be searched) is raised: on Python 3.14 is_file() and is_dir() say False."""
    try:
        return kind(os.stat(path).st_mode)
    except (FileNotFoundError, NotADirectoryError):
        return False
    except OSError as e:
        if e.errno == errno.ELOOP:
            return False   # a symlink loop leads nowhere, like a link to a missing target
        raise


def _listed_file(path):
    """True for a regular file, False for a link that leads nowhere (to a missing target, a
    target through a file, or a loop). Not found otherwise is raised, not passed over: the walk has just listed the name,
    and on Windows a path past MAX_PATH says "not found" while it is there."""
    try:
        return stat.S_ISREG(os.stat(path).st_mode)
    except OSError as e:
        if e.errno == errno.ELOOP or (isinstance(e, (FileNotFoundError, NotADirectoryError)) and os.path.islink(path)):
            return False
        raise


def _raise(error):
    raise error   # a folder that is not found is raised too: see _listed_file


def transcripts(folder):
    """The *.jsonl files under folder. os.walk with onerror, not rglob: rglob passes over a
    folder it cannot list, and the transcripts in it would go uncounted."""
    for root, _, names in os.walk(folder, onerror=_raise):
        for name in names:
            path = Path(root) / name
            if os.path.normcase(name).endswith(".jsonl") and _listed_file(path):   # as rglob
                yield path


def tool_calls(folder):
    """Return (number of transcripts, Counter of tool names)."""
    called = collections.Counter()
    files = sorted(transcripts(folder))
    for path in files:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    event = json.loads(line)
                except (ValueError, RecursionError):
                    continue
                message = event.get("message") if isinstance(event, dict) else None
                content = message.get("content") if isinstance(message, dict) else None
                for block in content if isinstance(content, list) else []:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        name = block.get("name")
                        if isinstance(name, str) and name:
                            called[name] += 1
    return len(files), called


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.strip(),
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dir")
    parser.add_argument("--top", type=int, default=40)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        # -I ignores PYTHONUTF8: set UTF-8 output here
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

    try:
        if not _is(args.dir, stat.S_ISDIR):
            print(f"error: {args.dir} is not a folder", file=sys.stderr)
            return 2
        sessions, called = tool_calls(args.dir)
    except OSError as e:
        # A transcript or folder that cannot be read would leave its tool calls out of the count.
        print(f"error: cannot read {e.filename or args.dir} ({e.strerror or e})", file=sys.stderr)
        return 1
    if not sessions:
        print(f"error: no *.jsonl transcripts under {args.dir}", file=sys.stderr)
        return 1
    print(f"{sessions} transcripts, {sum(called.values())} tool calls, {len(called)} distinct tools\n")
    for name, n in called.most_common(args.top):
        print(f"  {name}: {n}")
    if len(called) > args.top:
        print(f"  ... and {len(called) - args.top} more")

    try:
        with open(USER_SETTINGS, encoding="utf-8") as f:
            denied = json.load(f).get("permissions", {}).get("deny", [])
    except (OSError, ValueError, RecursionError) as e:
        print(f"error: cannot read {USER_SETTINGS}: {e}", file=sys.stderr)
        return 1
    print("\nDenied in config/user-settings.json:")
    for tool in denied:
        n = called.get(tool, 0)
        print(f"  {tool}: called {n} time(s)" + ("  <- review: it was used" if n else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
