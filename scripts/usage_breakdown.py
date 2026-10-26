"""Sum billed token usage per API response, split cache writes by TTL, and price them.

Usage:
  python -I scripts/usage_breakdown.py TRANSCRIPT_DIR [COUNT]

The COUNT largest .jsonl files in TRANSCRIPT_DIR are read (default 10). Claude Code
records 5-minute and 1-hour cache writes separately; they cost $5/MTok and $8/MTok
on Opus 5.5, so pricing every write at the 5-minute rate understates the bill.
"""
import collections
import glob
import json
import os
import sys

# Opus 5.5 list prices per MTok: input 4, 5m cache write 5, 1h cache write 8,
# cache read 0.20, output 20.
RATES = {
    "cache reads": 0.20,
    "cache writes (5m)": 5.0,
    "cache writes (1h)": 8.0,
    "fresh input": 4.0,
    "output": 20.0,
}

TOKEN_KEYS = (
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "cache_creation_5m_input_tokens",
    "cache_creation_1h_input_tokens",
    "input_tokens",
    "output_tokens",
)


def _int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _len(value):
    """Length of a text field; a field that is null or not a string counts 0."""
    return len(value) if isinstance(value, str) else 0


def _cache_writes(usage):
    """Return (5m, 1h) cache-write tokens, including any unpriced remainder."""
    total = _int(usage.get("cache_creation_input_tokens"))
    nested = usage.get("cache_creation")
    if isinstance(nested, dict):
        five = _int(nested.get("ephemeral_5m_input_tokens"))
        one = _int(nested.get("ephemeral_1h_input_tokens"))
    else:
        five = _int(usage.get("ephemeral_5m_input_tokens"))
        one = _int(usage.get("ephemeral_1h_input_tokens"))
    if total > five + one:
        # Older records may have only the total. Price the unclassified part as 5m.
        five += total - (five + one)
    return five, one


def summarize(files):
    """Return (totals, output_characters, api_responses) for the given files."""
    tot = collections.Counter()
    out_chars = collections.Counter()
    seen = set()
    turns = 0
    for path in files:
        try:
            # utf-8-sig: a transcript saved with a BOM would otherwise lose its first line.
            f = open(path, encoding="utf-8-sig", errors="ignore")
        except OSError as e:
            # Unreadable between the glob and the read: one line, the others are still summed.
            print(f"error: cannot read {path}: {e.strerror or e}", file=sys.stderr)
            continue
        with f:
            for line in f:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(event, dict) or event.get("type") != "assistant":
                    continue
                message = event.get("message")
                if not isinstance(message, dict):
                    continue
                message_id = message.get("id")
                usage = message.get("usage")
                if not isinstance(usage, dict):
                    usage = {}
                if isinstance(message_id, str) and message_id and message_id not in seen and usage:
                    seen.add(message_id)
                    turns += 1
                    five, one = _cache_writes(usage)
                    tot["cache_creation_5m_input_tokens"] += five
                    tot["cache_creation_1h_input_tokens"] += one
                    tot["cache_creation_input_tokens"] += five + one
                    for key in ("input_tokens", "cache_read_input_tokens", "output_tokens"):
                        tot[key] += _int(usage.get(key))
                content = message.get("content")
                for block in content if isinstance(content, list) else []:
                    if not isinstance(block, dict):
                        continue
                    kind = block.get("type")
                    if kind == "text":
                        out_chars["visible text"] += _len(block.get("text"))
                    elif kind == "tool_use":
                        out_chars["tool calls (incl. file contents written)"] += len(
                            json.dumps(block.get("input", {}))
                        )
                    elif kind == "thinking":
                        out_chars["thinking (visible part)"] += _len(block.get("thinking"))
    return tot, out_chars, turns


def costs(tot):
    return {
        "cache reads": tot["cache_read_input_tokens"] * RATES["cache reads"],
        "cache writes (5m)": tot["cache_creation_5m_input_tokens"] * RATES["cache writes (5m)"],
        "cache writes (1h)": tot["cache_creation_1h_input_tokens"] * RATES["cache writes (1h)"],
        "fresh input": tot["input_tokens"] * RATES["fresh input"],
        "output": tot["output_tokens"] * RATES["output"],
    }


def print_report(files, tot, out_chars, turns):
    print(f"{len(files)} transcripts, {turns} API responses")
    for key in TOKEN_KEYS:
        print(f"{key:38} {tot[key]:>14,}")
    cost = costs(tot)
    total_cost = sum(cost.values())
    if total_cost:
        print(
            "share of list-price cost at Opus 5.5 rates: "
            + ", ".join(f"{name} {value / total_cost:.0%}" for name, value in cost.items())
        )
    chars = sum(out_chars.values()) or 1
    print(
        "output characters by kind: "
        + ", ".join(f"{name} {value / chars:.0%}" for name, value in out_chars.most_common())
    )


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")   # -I ignores PYTHONUTF8: set UTF-8 output here
    if len(argv) not in (1, 2):
        sys.exit("usage: python -I scripts/usage_breakdown.py <transcript folder> [count]")
    folder = argv[0]
    try:
        count = int(argv[1]) if len(argv) == 2 else 10
    except ValueError:
        sys.exit("count must be an integer")
    if count <= 0:
        sys.exit("count must be positive")
    files = [f for f in glob.glob(os.path.join(glob.escape(folder), "*.jsonl")) if os.path.isfile(f)]
    files = sorted(files, key=os.path.getsize, reverse=True)[:count]
    if not files:
        sys.exit(f"no .jsonl files in {folder}")
    tot, out_chars, turns = summarize(files)
    print_report(files, tot, out_chars, turns)
    return 0


if __name__ == "__main__":
    sys.exit(main())
