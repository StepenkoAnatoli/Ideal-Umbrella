"""Characters of user-role text by origin (hooks, compaction summaries, pasted content, typed text).

Usage: python -I scripts/usertext_split.py TRANSCRIPT.jsonl [TRANSCRIPT.jsonl ...]
"""
import collections, json, sys

if hasattr(sys.stdout, "reconfigure"):
    # -I ignores PYTHONUTF8: set UTF-8 output here
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

if len(sys.argv) < 2:
    sys.exit("usage: python -I scripts/usertext_split.py <transcript.jsonl> [more transcripts]")
marks = [("evidence-rule hook", "EVIDENCE RULE"), ("compaction summary", "being continued from a previous conversation"),
         ("pasted content", "<pasted_content"), ("deferred-tool list", "deferred tools are now available"),
         ("MCP auth/failed notice", "require authentication before"), ("other system-reminder", "<system-reminder>")]
c, n = collections.Counter(), collections.Counter()
for path in sys.argv[1:]:
    try:
        f = open(path, encoding="utf-8-sig", errors="replace")   # -sig: a BOM would lose line 1
    except OSError as e:
        sys.exit(f"error: {e}")
    for line in f:
        try: e = json.loads(line)
        except (ValueError, RecursionError): continue
        m = e.get("message") if isinstance(e, dict) else None
        if not isinstance(e, dict) or e.get("isSidechain") or not isinstance(m, dict) or m.get("role") != "user": continue
        mc = m.get("content")
        parts = [mc] if isinstance(mc, str) else [b.get("text") for b in mc if isinstance(b, dict) and b.get("type") == "text"] if isinstance(mc, list) else []
        for t in parts:
            if not isinstance(t, str) or not t: continue   # a malformed text field (null, a number)
            k = next((name for name, s in marks if s in t), "typed by user / other")
            c[k] += len(t); n[k] += 1
tot = sum(c.values())
if not tot:
    sys.exit("no user text found in the given transcripts")
for k, v in c.most_common(): print(f"{k:24} {n[k]:>4} blocks {v:>10,} chars {v/tot:>5.0%}")
