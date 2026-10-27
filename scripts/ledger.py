"""Append one measurement line to research/measurements.jsonl and print the change since the last.

The README's fixed-load number is one dated observation. A Claude Code update that adds tools
or grows the skill listing moves it, and nothing notices unless someone measures again. Run
this by hand after such a measurement (get_usage in a new session, or the first call of a
fresh transcript); the hook never runs it.

Usage: python -I scripts/ledger.py --fixed-tokens 71396 [--first-call-cache-write N]
       [--tools N] [--deny-applied yes|no] [--cc-version V] [--note TEXT] [--date YYYY-MM-DD]
       [--file PATH] [--dry-run]

Each run appends one JSON object per line. Lines that are not a JSON object (a torn append, a
hand edit) are skipped and counted, never fatal. Exit 0 when the line is written, 1 when the
file cannot be read or written, 2 for bad arguments.
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

DEFAULT_FILE = Path(__file__).resolve().parents[1] / "research" / "measurements.jsonl"
MEASURES = ("fixed_tokens", "first_call_cache_write", "tools", "deny_applied")
COMPARED = ("cc_version",) + MEASURES
MAX_DIGITS = 15   # as --handoff-at in config/add_to_repo.py and hooks/context_check.py


def _count(text):
    if not (text.isascii() and text.isdigit()):
        raise argparse.ArgumentTypeError(f"{text!r} is not a whole number of 0 or more")
    digits = text.lstrip("0") or "0"
    if len(digits) > MAX_DIGITS:
        # A longer count is no token count; and the change from the previous line is a
        # division, which overflows a float well before int() refuses the digits.
        raise argparse.ArgumentTypeError(f"{text!r} has more than {MAX_DIGITS} digits")
    return int(digits)


def _yes_no(text):
    if text not in ("yes", "no"):
        raise argparse.ArgumentTypeError(f"{text!r} is not yes or no")
    return text == "yes"


def _date(text):
    try:
        return datetime.date.fromisoformat(text).isoformat()
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a date like 2026-10-27") from None


def _text(text):
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        # A command-line byte that is not UTF-8 arrives as a lone surrogate: it cannot be written.
        raise argparse.ArgumentTypeError(f"{text!r} is not valid UTF-8 text") from None
    return text


def previous_entry(path):
    """Return (line number, entry, skipped) for the last line that is a JSON object.
    A missing file is (None, None, 0); a file that cannot be read raises OSError, and one in
    UTF-16 or UTF-32 raises ValueError."""
    try:
        data = Path(path).read_bytes()
    except FileNotFoundError:
        return None, None, 0
    if data.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in data:
        # UTF-16 or UTF-32 (PowerShell 5's default for Out-File, > and >>): a UTF-8 line
        # appended to it would leave a file no encoding reads. json.dumps never writes a NUL.
        raise ValueError("not UTF-8 text (UTF-16 or UTF-32); save it as UTF-8 first")
    found, number, skipped = None, None, 0
    # Lines end at "\n" only: str.splitlines() also splits on U+2028, form feed and others,
    # which json.dumps(ensure_ascii=False) leaves raw inside a string. A BOM (Notepad, PowerShell
    # 5) is dropped: json.loads refuses one.
    for index, raw in enumerate(data.decode("utf-8-sig", errors="replace").split("\n"), 1):
        if not raw.strip():
            continue
        try:
            entry = json.loads(raw)
        except (ValueError, RecursionError):   # RecursionError: a hand edit nested too deep
            entry = None
        if isinstance(entry, dict):
            found, number = entry, index
        else:
            skipped += 1
    return number, found, skipped


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _show(value):
    return f"{value:,}" if _is_number(value) else str(value)


def delta_lines(old, new):
    """One line per compared field either entry holds."""
    out = []
    for key in COMPARED:
        if key not in old and key not in new:
            continue
        if key not in old:
            out.append(f"{key}: (none) -> {_show(new[key])}")
        elif key not in new:
            out.append(f"{key}: {_show(old[key])} -> (not measured)")
        elif _is_number(old[key]) and _is_number(new[key]):
            change = new[key] - old[key]
            text = f"{change:+,}" if change else "0"
            if change and old[key]:
                text += f", {change / old[key]:+.1%}"
            out.append(f"{key}: {_show(old[key])} -> {_show(new[key])} ({text})")
        else:
            out.append(f"{key}: {_show(old[key])} -> {_show(new[key])}")
    return out


def append(path, entry):
    """Append `entry` as one line, starting a new line if the file does not end with one."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False).encode("utf-8") + b"\n"
    with open(path, "a+b") as f:   # reads may seek; every write still goes to the end
        if f.seek(0, 2) > 0:
            f.seek(-1, 2)
            if f.read(1) != b"\n":
                line = b"\n" + line
        f.write(line)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.strip(),
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fixed-tokens", type=_count, help="new-session total from get_usage")
    parser.add_argument("--first-call-cache-write", type=_count,
                        help="cache write of the first API call in a fresh transcript")
    parser.add_argument("--tools", type=_count, help="number of tools a new session loads")
    parser.add_argument("--deny-applied", type=_yes_no, help="yes when permissions.deny was in place")
    parser.add_argument("--cc-version", type=_text, help="Claude Code version (claude --version)")
    parser.add_argument("--note", type=_text, help="free text kept with the line")
    parser.add_argument("--date", type=_date, default=datetime.date.today().isoformat())
    parser.add_argument("--file", default=str(DEFAULT_FILE))
    parser.add_argument("--dry-run", action="store_true", help="print, write nothing")
    args = parser.parse_args(argv)
    if all(getattr(args, key) is None for key in MEASURES):
        parser.error("give at least one of --fixed-tokens, --first-call-cache-write, --tools, --deny-applied")
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            # -I ignores PYTHONUTF8: set UTF-8 output here. A file name that is not UTF-8 holds
            # lone surrogates, printed as escapes rather than raising after the line is written.
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")

    entry = {"date": args.date}
    for key in ("cc_version",) + MEASURES + ("note",):
        if getattr(args, key) is not None:
            entry[key] = getattr(args, key)
    try:
        number, old, skipped = previous_entry(args.file)
        if not args.dry_run:
            append(args.file, entry)
    except OSError as error:
        print(f"error: {args.file}: {error.strerror or error}", file=sys.stderr)
        return 1
    except ValueError as error:
        print(f"error: {args.file}: {error}", file=sys.stderr)
        return 1

    line = json.dumps(entry, ensure_ascii=False)
    print(f"dry run, not written: {line}" if args.dry_run else f"appended to {args.file}: {line}")
    if skipped:
        print(f"{skipped} unreadable line(s) skipped")
    if old is None:
        print("first line: nothing to compare with")
        return 0
    print(f"change since line {number} ({old.get('date', 'no date')}):")
    for text in delta_lines(old, entry):
        print(f"  {text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
