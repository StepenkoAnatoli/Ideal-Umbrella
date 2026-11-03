"""What would the cache bill look like with a 5-minute cache TTL instead of the actual one?

Usage:
  python -I scripts/ttl_whatif.py TRANSCRIPT_DIR [COUNT]

Reads the COUNT largest sessions (default 10) the way usage_breakdown.py does: the session's
.jsonl file and each subagent transcript are separate streams, and each stream has its own gaps.
For every API response it takes the gap since the previous response in the same stream and
prices the cache part of the bill twice, in list-price terms (Opus 5.5 rates from
usage_breakdown.py):
  actual   cache reads at the read rate, 5-minute and 1-hour writes at their own rates;
  what-if  a 5-minute TTL for everything: every write at the 5-minute rate, and every response
           whose gap is over 5 minutes rewrites its whole prefix (reads become writes).
It also lists cache busts (nearly the whole context written fresh) with a likely cause.
The causes are guesses from the gap and the context size. Input and output tokens are the same
in both and are left out. Plan limits are not dollars: these figures are list prices.
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # -I leaves the script folder off
import usage_breakdown as ub                                      # noqa: E402

TTL_SECONDS = 300
LONG_TTL_SECONDS = 3600
BUCKETS = (("<5m", 300), ("5-15m", 900), ("15-30m", 1800), ("30-60m", 3600), ("1-4h", 4 * 3600))
LAST_BUCKET = ">4h"
BUST_MIN_TOKENS = 20_000        # a smaller context is not worth calling a bust
BUST_WRITE_SHARE = 0.8


def bucket(gap):
    for name, limit in BUCKETS:
        if gap < limit:
            return name
    return LAST_BUCKET


def _time(value):
    """Seconds since the epoch of an ISO-8601 timestamp, or None."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    try:
        return parsed.timestamp()
    except (OverflowError, OSError, ValueError):
        return None


def read_stream(path, seen_uuids, seen_messages):
    """Responses of one file in order: [(time, read, write5m, write1h)], one per message id
    (the largest of each count across its streamed lines, the first line's time). A response
    without a readable time is left out: it has no gap."""
    order, found = [], {}
    with open(path, encoding="utf-8-sig", errors="ignore") as f:
        for line in f:
            event = ub.parse_line(line)
            if event is None or event.get("type") != "assistant":
                continue
            uuid = event.get("uuid")
            if isinstance(uuid, str) and uuid:
                if uuid in seen_uuids:
                    continue
                seen_uuids.add(uuid)
            message = event.get("message")
            if not isinstance(message, dict):
                continue
            mid, usage = message.get("id"), message.get("usage")
            if not (isinstance(mid, str) and mid and isinstance(usage, dict) and usage) or mid in seen_messages:
                continue
            five, one = ub._cache_writes(usage)
            counts = [ub._int(usage.get("cache_read_input_tokens")), five, one]
            if mid in found:
                known = found[mid]
                known[1:] = [max(a, b) for a, b in zip(known[1:], counts)]
                continue
            when = _time(event.get("timestamp"))
            if when is None:
                continue
            found[mid] = [when] + counts
            order.append(mid)
    seen_messages.update(order)
    return [tuple(found[m]) for m in order]


def analyse(streams):
    """streams: a list of lists of files; each inner list is one stream (a session's main
    file, or one subagent file)."""
    seen_uuids, seen_messages = set(), set()
    names = [name for name, _ in BUCKETS] + [LAST_BUCKET]
    buckets = {n: {"responses": 0, "read": 0, "write": 0} for n in names}
    actual = whatif = 0.0
    busts = {}
    responses = 0
    price = ub.RATES
    for files in streams:
        previous = None
        for path in files:
            for when, read, w5, w1 in read_stream(path, seen_uuids, seen_messages):
                responses += 1
                writes = w5 + w1
                cost_a = (read * price["cache reads"] + w5 * price["cache writes (5m)"]
                          + w1 * price["cache writes (1h)"]) / 1e6
                gap = None if previous is None else max(0.0, when - previous["when"])
                if gap is not None and gap > TTL_SECONDS:
                    cost_b = (read + writes) * price["cache writes (5m)"] / 1e6
                else:
                    cost_b = (read * price["cache reads"] + writes * price["cache writes (5m)"]) / 1e6
                actual += cost_a
                whatif += cost_b
                if gap is not None:
                    row = buckets[bucket(gap)]
                    row["responses"] += 1
                    row["read"] += read
                    row["write"] += writes
                    total = read + writes
                    if total >= BUST_MIN_TOKENS and writes >= BUST_WRITE_SHARE * total:
                        ttl = LONG_TTL_SECONDS if previous["w1"] else TTL_SECONDS
                        if gap > ttl:
                            cause = "gap over TTL"
                        elif total < previous["total"] / 2:
                            cause = "compaction"
                        else:
                            cause = "other"
                        busts[cause] = busts.get(cause, 0) + 1
                previous = {"when": when, "w1": w1, "total": read + writes}
    return {"responses": responses, "actual": actual, "whatif": whatif, "buckets": buckets, "busts": busts}


def print_report(result, sessions_read):
    print(f"{sessions_read} sessions, {result['responses']} API responses with a readable time")
    print(f"{'gap since previous response':28} {'responses':>9} {'cache read tok':>15} {'cache write tok':>16}")
    for name, row in result["buckets"].items():
        print(f"{name:28} {row['responses']:>9,} {row['read']:>15,} {row['write']:>16,}")
    a, b = result["actual"], result["whatif"]
    print(f"cache cost, actual (list price): ${a:,.2f}")
    print(f"cache cost, 5-minute TTL what-if: ${b:,.2f}" + (f" ({b / a - 1:+.0%})" if a else ""))
    busts = result["busts"]
    print("cache busts: " + (", ".join(f"{k} {v}" for k, v in sorted(busts.items())) if busts else "none")
          + " (causes are guesses from the gap and the context size)")
    print("List-price terms only: plan limits are not dollars, and input and output tokens are left out.")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if hasattr(sys.stdout, "reconfigure"):
        # -I ignores PYTHONUTF8: set UTF-8 output here
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    if len(argv) not in (1, 2):
        sys.exit("usage: python -I scripts/ttl_whatif.py <transcript folder> [count]")
    folder = argv[0]
    try:
        count = int(argv[1]) if len(argv) == 2 else 10
    except ValueError:
        sys.exit("count must be an integer")
    if count <= 0:
        sys.exit("count must be positive")
    try:
        picked = sorted(ub.sessions(folder), key=lambda s: s[1], reverse=True)[:count]
        if not picked:
            sys.exit(f"no .jsonl files in {folder}")
        streams = [[path] for path, _, _ in picked] + [[p] for _, _, subs in picked for p in subs]
        result = analyse(streams)
    except OSError as e:
        sys.exit(f"cannot read {e.filename or folder} ({e.strerror or e})")
    print_report(result, len(picked))
    return 0


if __name__ == "__main__":
    sys.exit(main())
