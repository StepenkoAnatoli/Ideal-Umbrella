"""The ten largest kinds of user-role text, keyed by how each block starts.

Usage: python -I scripts/usertext_top.py TRANSCRIPT.jsonl [TRANSCRIPT.jsonl ...]
"""
import collections, json, re, sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")   # -I ignores PYTHONUTF8: set UTF-8 output here

if len(sys.argv) < 2:
    sys.exit("usage: python -I scripts/usertext_top.py <transcript.jsonl> [more transcripts]")
c, n = collections.Counter(), collections.Counter()
for path in sys.argv[1:]:
    try:
        f = open(path, encoding="utf-8-sig", errors="replace")   # -sig: a BOM would drop line 1
    except OSError as e:
        sys.exit(f"error: {e}")
    for line in f:
        try: e = json.loads(line)
        except ValueError: continue
        m = e.get("message") if isinstance(e, dict) else None
        if not isinstance(e, dict) or e.get("isSidechain") or not isinstance(m, dict) or m.get("role") != "user": continue
        parts = [m["content"]] if isinstance(m.get("content"), str) else [b.get("text", "") for b in m.get("content") or [] if isinstance(b, dict) and b.get("type") == "text"]
        for t in parts:
            if not isinstance(t, str) or not t: continue
            head = re.sub(r"\s+", " ", t.strip())[:40]
            key = re.match(r"<[a-z_-]+>|Base directory for this skill|\S+ \S+ \S+", head)
            k = key.group(0) if key else head
            c[k] += len(t); n[k] += 1
tot = sum(c.values())
if not tot:
    sys.exit("no user text found in the given transcripts")
for k, v in c.most_common(10): print(f"{k[:40]:42} {n[k]:>4} {v:>10,} {v/tot:>5.0%}")
