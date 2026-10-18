"""Sum the billed token usage Claude Code recorded per assistant message, and split output by block type."""
import json, sys, glob, os, collections
files = sorted(glob.glob(os.path.join(sys.argv[1], "*.jsonl")), key=os.path.getsize, reverse=True)[: int(sys.argv[2])]
tot = collections.Counter(); out_chars = collections.Counter(); seen = set(); turns = 0
for f in files:
    for line in open(f, encoding="utf-8", errors="ignore"):
        try: e = json.loads(line)
        except ValueError: continue
        m = e.get("message") or {}
        if e.get("type") != "assistant" or not isinstance(m, dict): continue
        mid = m.get("id")
        u = m.get("usage") or {}
        if mid and mid not in seen and u:
            seen.add(mid); turns += 1
            for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"):
                tot[k] += u.get(k) or 0
        for b in m.get("content") or []:
            if not isinstance(b, dict): continue
            t = b.get("type")
            if t == "text": out_chars["visible text"] += len(b.get("text", ""))
            elif t == "tool_use": out_chars["tool calls (incl. file contents written)"] += len(json.dumps(b.get("input", {})))
            elif t == "thinking": out_chars["thinking (visible part)"] += len(b.get("thinking", ""))
print(f"{len(files)} transcripts, {turns} API responses")
allin = tot["input_tokens"] + tot["cache_creation_input_tokens"] + tot["cache_read_input_tokens"]
for k in ("cache_read_input_tokens", "cache_creation_input_tokens", "input_tokens", "output_tokens"):
    print(f"{k:30} {tot[k]:>14,}")
# Opus 5.5 list prices per MTok: input 4, cache write 1.25x input (5m), cache read 0.20, output 20
cost = {"cache reads": tot["cache_read_input_tokens"]*0.20, "cache writes": tot["cache_creation_input_tokens"]*5.0,
        "fresh input": tot["input_tokens"]*4.0, "output": tot["output_tokens"]*20.0}
s = sum(cost.values())
print("share of list-price cost at Opus 5.5 rates:", ", ".join(f"{k} {v/s:.0%}" for k, v in cost.items()))
c = sum(out_chars.values()) or 1
print("output characters by kind:", ", ".join(f"{k} {v/c:.0%}" for k, v in out_chars.most_common()))
