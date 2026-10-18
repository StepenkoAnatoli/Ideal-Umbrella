import collections, json, re, sys
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
            head = re.sub(r"\s+", " ", t.strip())[:40]
            key = re.match(r"<[a-z_-]+>|Base directory for this skill|\S+ \S+ \S+", head)
            k = key.group(0) if key else head
            c[k] += len(t); n[k] += 1
tot = sum(c.values())
for k, v in c.most_common(10): print(f"{k[:40]:42} {n[k]:>4} {v:>10,} {v/tot:>5.0%}")
