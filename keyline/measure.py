"""measure.py - print o200k_base and cl100k_base token counts for files, to compare before/after.

Usage:
  python measure.py FILE_OR_FOLDER [FILE_OR_FOLDER ...]
A folder is walked recursively. Hidden files and folders, cache/, __pycache__/ and node_modules/
are skipped, and a symlinked sub-folder is not followed (its files would be counted twice); a
symlinked file in the folder, and a symlink named as an argument, are followed.
With exactly two file arguments that were both counted, a change line is printed. Files are
counted exactly as stored (a UTF-8 BOM is dropped; line endings and a trailing newline are
counted). These are OpenAI tokenizers: a proxy for Claude's tokenizer, which is not public.
Exit: 0 every argument was counted; 1 an argument produced no row (a skipped file, an empty
folder); 2 usage error, an encoding tiktoken cannot load, or an argument that is missing,
cannot be read or is not a regular file or folder.
"""
import os
import stat
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(HERE / "cache" / "tiktoken"))
try:
    import tiktoken
except ImportError:
    sys.exit("tiktoken is not installed; run: python -m pip install -r keyline/requirements.txt")

SKIP_DIRS = {"cache", "__pycache__", "node_modules"}


def _unlisted(e):
    """os.walk's onerror: a folder the walk cannot list is named, as a file it cannot read is."""
    print(f"skip (cannot read: {e.strerror or e}): {e.filename}", file=sys.stderr)


class NotRegular(OSError):
    """An argument that exists but is neither a regular file nor a folder (a FIFO, a socket)."""


class Unlistable(OSError):
    """A folder argument that cannot be listed: an argument that cannot be read, exit 2. Not
    "no such file or folder" when the listing says "not found": the stat has just found it (on
    Windows a path past MAX_PATH says "not found" while it is there)."""


def files_in(arg):
    # os.stat, not is_file()/is_dir(): on Python 3.14 those say False for a path that cannot be
    # looked at (in a folder that cannot be searched), which read as "no such file or folder".
    p = Path(arg)
    mode = os.stat(p).st_mode
    if stat.S_ISREG(mode):
        return [p]
    if stat.S_ISDIR(mode):
        # The walk's onerror names a folder it cannot list and goes on, which is right below the
        # argument; the argument itself is listed here first, so it is an error, not a skip.
        try:
            with os.scandir(p):
                pass
        except OSError as e:
            raise Unlistable(e.errno, e.strerror, e.filename) from e
        out = []
        for root, dirs, names in os.walk(p, onerror=_unlisted):
            dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS)
            out += [Path(root) / n for n in sorted(names) if not n.startswith(".")]
        return out
    raise NotRegular(arg)



def count(text, encs):
    return [len(e.encode(text, disallowed_special=())) for e in encs]


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    if not argv or argv[0].startswith("-"):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    encs = []
    for name in ("o200k_base", "cl100k_base"):
        try:
            encs.append(tiktoken.get_encoding(name))
        except Exception as e:   # offline on first use, a proxy, a corrupt cache: any of them
            print(f"error: tiktoken could not load {name}: {e}", file=sys.stderr)
            return 2
    rows, counted, file_args = [], [], 0      # counted: per argument, the number of rows it produced
    for arg in argv:
        try:
            paths = files_in(arg)
        except Unlistable as e:
            print(f"error: cannot read {arg}: {e.strerror or e}", file=sys.stderr)
            return 2
        except (FileNotFoundError, NotADirectoryError):
            print(f"error: no such file or folder: {arg}", file=sys.stderr)
            return 2
        except NotRegular:
            print(f"error: not a regular file or folder: {arg}", file=sys.stderr)
            return 2
        except OSError as e:
            # The argument itself cannot be stat'ed (a file in a folder that cannot be searched).
            print(f"error: cannot read {arg}: {e.strerror or e}", file=sys.stderr)
            return 2
        before = len(rows)
        file_args += paths == [Path(arg)]          # a walked folder's paths are below it
        for p in paths:
            try:
                # A named pipe or socket in a walked folder would block the read; a symlink to
                # a missing target would fail it. The stat itself fails in a folder that lists
                # its names but cannot be searched (mode 0444); os.stat, as in files_in.
                why = None if stat.S_ISREG(os.stat(p).st_mode) else "not a regular file"
            except OSError as e:
                # Not "no longer there" for a name the walk has just listed: on Windows a path
                # past MAX_PATH says "not found" while it is there.
                if isinstance(e, (FileNotFoundError, NotADirectoryError)) and os.path.islink(p):
                    why = "symlink to a missing target"
                else:
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
        counted.append(len(rows) - before)
    print(f"{'o200k':>7} {'cl100k':>7} {'chars':>7}  file")
    for p, chars, o, c in rows:
        print(f"{o:>7} {c:>7} {chars:>7}  {p}")
    if len(rows) > 1:
        print(f"{sum(r[2] for r in rows):>7} {sum(r[3] for r in rows):>7} "
              f"{sum(r[1] for r in rows):>7}  total ({len(rows)} files)")
    # Two file arguments, each counted: a folder holding two files, or a skipped second file,
    # is not a before/after pair.
    if len(argv) == 2 and counted == [1, 1] and file_args == 2:
        (_, _, o1, c1), (_, _, o2, c2) = rows

        def pct(a, b):
            return f"{(b - a) / a * 100:+.0f}%" if a else "n/a"
        print(f"change: o200k {o1} -> {o2} ({pct(o1, o2)}), cl100k {c1} -> {c2} ({pct(c1, c2)})")
    empty = [a for a, n in zip(argv, counted) if not n]
    for arg in empty:
        print(f"nothing counted for {arg}", file=sys.stderr)
    return 1 if empty else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
