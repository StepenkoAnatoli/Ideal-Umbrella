"""Where does the context go? Tool results by tool, Bash result sizes, and repeated Bash commands.

Usage:
  python -I scripts/top_waste.py TRANSCRIPT_DIR [COUNT]

Reads the COUNT largest sessions (default 10), subagent transcripts included, as
usage_breakdown.py does. Sizes are characters of tool_result content, not tokens. "Bash" here
means the shell tools, Bash and PowerShell. A command is shown cut to 60 characters.
toolresult_share.py counts the same results for single files; its parsing runs at import, so
this script keeps its own small copy of the size rule (text counts its characters, an image
nothing, other blocks their JSON length).
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # -I leaves the script folder off
import usage_breakdown as ub                                      # noqa: E402

SHELL_TOOLS = ("Bash", "PowerShell")
BUCKETS = (("<2k", 2000), ("2-8k", 8000), ("8-12k", 12000), ("12-30k", 30000))
LAST_BUCKET = ">30k"
TOP = 10
KEY_LIMIT = 2000      # a command is one repeat only when all of it (up to here) matches


def size_bucket(n):
    for name, limit in BUCKETS:
        if n < limit:
            return name
    return LAST_BUCKET


def result_size(content):
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        n = 0
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                n += ub._len(block.get("text"))
            elif block.get("type") != "image":
                n += len(json.dumps(block))
        return n
    return len(json.dumps(content)) if content is not None else 0


def tool_label(name):
    if not isinstance(name, str) or not name:
        return "?"
    return "mcp:" + name.split("__")[-1] if name.startswith("mcp__") else name


def analyse(files):
    by_tool = collections.Counter()
    calls = collections.Counter()
    buckets = {name: [0, 0] for name, _ in BUCKETS}
    buckets[LAST_BUCKET] = [0, 0]
    repeats = {}
    seen = set()
    for path in files:
        pending = {}                      # tool_use id -> (label, command) within this file
        with open(path, encoding="utf-8-sig", errors="ignore") as f:
            for line in f:
                event = ub.parse_line(line)
                if event is None:
                    continue
                uuid = event.get("uuid")
                if isinstance(uuid, str) and uuid:
                    if uuid in seen:
                        continue
                    seen.add(uuid)
                message = event.get("message")
                content = message.get("content") if isinstance(message, dict) else None
                for block in content if isinstance(content, list) else []:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_use" and isinstance(block.get("id"), str):
                        command = block.get("input")
                        command = command.get("command") if isinstance(command, dict) else None
                        pending[block["id"]] = (tool_label(block.get("name")),
                                                command if isinstance(command, str) else None)
                    elif block.get("type") == "tool_result":
                        tool_id = block.get("tool_use_id")
                        label, command = pending.get(tool_id if isinstance(tool_id, str) else None, ("?", None))
                        n = result_size(block.get("content"))
                        by_tool[label] += n
                        calls[label] += 1
                        if label in SHELL_TOOLS:
                            row = buckets[size_bucket(n)]
                            row[0] += 1
                            row[1] += n
                            if command:
                                key = " ".join(command.split())[:KEY_LIMIT]
                                count, chars = repeats.get(key, (0, 0))
                                repeats[key] = (count + 1, chars + n)
    ranked = sorted(((k, c, ch) for k, (c, ch) in repeats.items() if c > 1), key=lambda r: -r[2])[:TOP]
    return {"by_tool": by_tool, "calls": calls,
            "bash_buckets": {k: tuple(v) for k, v in buckets.items()}, "repeats": ranked}


def print_report(data, files):
    total = sum(data["by_tool"].values())
    print(f"{len(files)} transcripts, {sum(data['calls'].values()):,} tool results, {total:,} characters")
    print(f"{'tool':24} {'calls':>7} {'characters':>13} {'share':>6}")
    for name, chars in data["by_tool"].most_common(12):
        print(f"{name:24} {data['calls'][name]:>7,} {chars:>13,} {chars / total if total else 0:>6.0%}")
    shell_total = sum(c for _, c in data["bash_buckets"].values())
    shell_calls = sum(n for n, _ in data["bash_buckets"].values())
    print(f"shell result sizes ({shell_calls:,} results, {shell_total:,} characters)")
    for name, (n, chars) in data["bash_buckets"].items():
        print(f"  {name:8} {n:>7,} results {chars:>13,} characters {chars / shell_total if shell_total else 0:>6.0%}")
    print("most repeated shell commands (by result characters)")
    for command, n, chars in data["repeats"]:
        print(f"  {n:>5}x {chars:>11,} chars  {command[:60]}")
    if not data["repeats"]:
        print("  none repeated")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if hasattr(sys.stdout, "reconfigure"):
        # -I ignores PYTHONUTF8: set UTF-8 output here
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    if len(argv) not in (1, 2):
        sys.exit("usage: python -I scripts/top_waste.py <transcript folder> [count]")
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
        files = [p for p, _, _ in picked] + [p for _, _, subs in picked for p in subs]
        data = analyse(files)
    except OSError as e:
        sys.exit(f"cannot read {e.filename or folder} ({e.strerror or e})")
    print_report(data, files)
    return 0


if __name__ == "__main__":
    sys.exit(main())
