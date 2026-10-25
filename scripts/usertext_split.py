import collections, json, sys
marks = [("evidence-rule hook", "EVIDENCE RULE"), ("compaction summary", "being continued from a previous conversation"),
         ("pasted content", "<pasted_content"), ("deferred-tool list", "deferred tools are now available"),
         ("MCP auth/failed notice", "require authentication before"), ("other system-reminder", "<system-reminder>")]
c, n = collections.Counter(), collections.Counter()
for path in sys.argv[1:]:
    for line in open(path, encoding="utf-8"):
        try: e = json.loads(line)
        except ValueError: continue
        m = e.get("message")
        if e.get("isSidechain") or not isinstance(m, dict) or m.get("role") != "user": continue
        parts = [m["content"]] if isinstance(m.get("content"), str) else [b.get("text", "") for b in m.get("content") or [] if isinstance(b, dict) and b.get("type") == "text"]
        for t in parts:
            if not t: continue
            k = next((name for name, s in marks if s in t), "typed by user / other")
            c[k] += len(t); n[k] += 1
tot = sum(c.values())
for k, v in c.most_common(): print(f"{k:24} {n[k]:>4} blocks {v:>10,} chars {v/tot:>5.0%}")
