"""measure.py - print o200k_base and cl100k_base token counts for files, to compare before/after.

Usage:
  python measure.py FILE_OR_FOLDER [FILE_OR_FOLDER ...]
A folder is walked recursively (hidden folders, cache/, __pycache__/ and symlinked folders, on
Windows junctions too, are skipped, each with a line on stderr). With exactly two files, a change
line is printed. Files are counted exactly as stored (a UTF-8 BOM is dropped; line endings and a trailing newline are
counted). These are OpenAI tokenizers: a proxy for Claude's tokenizer, which is not public.
Exit 2 when an argument is missing, is a file that cannot be counted, or is a folder in which
nothing was counted; a file skipped inside a walked folder is one stderr line and not an error.
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(HERE / "cache" / "tiktoken"))
try:
    import tiktoken
except ImportError:
    sys.exit("tiktoken is not installed; run: python -m pip install -r keyline/requirements.txt")

SKIP_DIRS = {"cache", "__pycache__", "node_modules"}


def _is_link(path):
    """A symlink, or on Windows a junction: os.path.islink does not see a junction, and os.walk
    does not enter one either."""
    isjunction = getattr(os.path, "isjunction", None)   # Python 3.12+, Windows only
    return os.path.islink(path) or bool(isjunction and isjunction(path))


def files_in(arg):
    p = Path(arg)
    if p.is_file():
        return [p]
    if p.is_dir():
        out = []
        for root, dirs, names in os.walk(p):
            # os.walk does not follow a symlinked folder (a loop would never end); say so,
            # as a skipped file is said, instead of leaving its files out in silence.
            for d in sorted(dirs):
                if _is_link(os.path.join(root, d)):
                    print(f"skip (symlinked folder): {Path(root) / d}", file=sys.stderr)
            dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS
                             and not _is_link(os.path.join(root, d)))
            out += [Path(root) / n for n in sorted(names)]
        return out
    raise FileNotFoundError(arg)


def count(text, encs):
    return [len(e.encode(text, disallowed_special=())) for e in encs]


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        # errors= too: reconfigure(encoding=...) alone resets it to strict, and a file name
        # from a walked folder can hold a byte that is no UTF-8 (a surrogate escape).
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    if not argv or argv[0].startswith("-"):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    try:
        encs = [tiktoken.get_encoding("o200k_base"), tiktoken.get_encoding("cl100k_base")]
    except Exception as e:
        # tiktoken installed but its data not loadable: offline on first use, a proxy, a
        # corrupt TIKTOKEN_CACHE_DIR entry.
        print(f"error: tiktoken could not load its encodings: {e}", file=sys.stderr)
        return 1
    rows = []
    failed = []                                    # arguments that yielded nothing to count
    for arg in argv:
        try:
            paths = files_in(arg)
        except FileNotFoundError:
            print(f"error: no such file or folder: {arg}", file=sys.stderr)
            return 2
        except OSError as e:
            # The argument itself cannot be stat'ed (a file in a folder that cannot be searched).
            print(f"error: cannot read {arg}: {e.strerror or e}", file=sys.stderr)
            return 2
        counted = 0
        for p in paths:
            try:
                # A named pipe or socket in a walked folder would block the read; a symlink to
                # a missing target would fail it. The stat itself fails in a folder that lists
                # its names but cannot be searched (mode 0444).
                regular = p.is_file()
                why = None if regular else ("symlink to a missing target" if p.is_symlink()
                                            else "not a regular file")
            except OSError as e:
                why = f"cannot read: {e.strerror or e}"
            if why:
                print(f"skip ({why}): {p}", file=sys.stderr)
                continue
            try:
                text = p.read_bytes().decode("utf-8-sig")
            except UnicodeDecodeError:
                print(f"skip (not UTF-8 text): {p}", file=sys.stderr)
                continue
            except OSError as e:
                print(f"skip (cannot read: {e.strerror or e}): {p}", file=sys.stderr)
                continue
            rows.append((p, len(text), *count(text, encs)))
            counted += 1
        if not counted:
            # A file named on the command line that was skipped, or a folder with nothing to
            # count: the skip lines were written for a walked folder; for an argument this
            # is an error, and the change line below is not printed for it.
            what = "nothing counted in folder" if len(paths) != 1 or paths[0] != Path(arg) \
                else "the file named could not be counted (see the skip line)"
            print(f"error: {what}: {arg}", file=sys.stderr)
            failed.append(arg)
    print(f"{'o200k':>7} {'cl100k':>7} {'chars':>7}  file")
    for p, chars, o, c in rows:
        print(f"{o:>7} {c:>7} {chars:>7}  {p}")
    if len(rows) > 1:
        print(f"{sum(r[2] for r in rows):>7} {sum(r[3] for r in rows):>7} "
              f"{sum(r[1] for r in rows):>7}  total ({len(rows)} files)")
    if len(argv) == 2 and len(rows) == 2:
        (_, _, o1, c1), (_, _, o2, c2) = rows

        def pct(a, b):
            return f"{(b - a) / a * 100:+.0f}%" if a else "n/a"
        print(f"change: o200k {o1} -> {o2} ({pct(o1, o2)}), cl100k {c1} -> {c2} ({pct(c1, c2)})")
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
