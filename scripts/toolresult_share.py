"""Share of a transcript's context characters that are tool results, by tool.

Usage: python -I scripts/toolresult_share.py TRANSCRIPT.jsonl [TRANSCRIPT.jsonl ...]
"""
import collections, json, sys

if len(sys.argv) < 2:
    sys.exit("usage: python -I scripts/toolresult_share.py <transcript.jsonl> [more transcripts]")

def size(c):
    if isinstance(c, str):
        return len(c)
    if isinstance(c, list):
        n = 0
        for b in c:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text":
                n += len(b.get("text", ""))
            elif b.get("type") != "image":
                n += len(json.dumps(b))
        return n
    return len(json.dumps(c)) if c is not None else 0

def short(name):
    if name and name.startswith("mcp__"):
        return "mcp:" + name.split("__")[-1]
    return name or "?"

names, res, cnt, other = {}, collections.Counter(), collections.Counter(), collections.Counter()
big = collections.Counter()
for path in sys.argv[1:]:
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if not isinstance(e, dict) or e.get("isSidechain"):
                continue
            m = e.get("message")
            if not isinstance(m, dict):
                continue
            role, c = m.get("role", "?"), m.get("content")
            if isinstance(c, str):
                other[role + "_text"] += len(c)
                continue
            if not isinstance(c, list):
                continue
            for b in c:
                if not isinstance(b, dict):
                    continue
                t = b.get("type")
                if t == "tool_use":
                    names[b.get("id")] = b.get("name")
                    other["tool_use_input"] += len(json.dumps(b.get("input")))
                elif t == "tool_result":
                    n = short(names.get(b.get("tool_use_id")))
                    s = size(b.get("content"))
                    res[n] += s
                    cnt[n] += 1
                    if s > 10000:
                        big[n] += s
                elif t == "text":
                    other[role + "_text"] += len(b.get("text", ""))
                elif t == "thinking":
                    other["thinking(not counted)"] += len(b.get("thinking", ""))

tr = sum(res.values())
total = tr + sum(v for k, v in other.items() if not k.startswith("thinking"))
if not total:
    sys.exit("no messages found in the given transcripts")
print(f"total context chars {total:,}; tool results {tr:,} = {tr / total:.0%}")
for k, v in other.most_common():
    print(f"  {k:24} {v:>12,}")
if not tr:
    sys.exit(0)
print(f"results over 10k chars: {sum(big.values()):,} = {sum(big.values()) / tr:.0%} of tool results")
print("tool          calls    result chars  share  avg   >10k chars")
for n, v in res.most_common(12):
    print(f"  {n:22} {cnt[n]:>5} {v:>12,} {v / tr:>5.0%} {v // cnt[n]:>7,} {big[n]:>10,}")
