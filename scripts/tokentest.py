# -*- coding: utf-8 -*-
"""Measure token cost of the SAME incident report in different notations."""
import sys, gzip, base64
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

A = ("I've completed the investigation into the outage. The authentication service began failing at 15:00 UTC "
     "shortly after the deployment of version 2.4.1. The root cause was that the database connection pool, which "
     "was configured with a maximum of 10 connections, became exhausted under the increased load introduced by the "
     "new session-refresh feature. To resolve this, I increased the pool size from 10 to 50 connections and restarted "
     "the service. The service has been stable for the last 40 minutes. I recommend adding an alert on pool "
     "utilization above 80% so that we catch this earlier next time.")

SAMPLES = {
 "A_english_prose":   A,
 "B_english_terse":   "Outage RCA: auth-svc failed 15:00Z after deploy v2.4.1. Cause: DB pool (max 10) exhausted by new session-refresh load. Fix: pool 10->50, restart. Stable 40m. Rec: alert pool util >80%.",
 "C_json":            '{"type":"rca","svc":"auth","start":"15:00Z","trigger":"deploy v2.4.1","cause":"db_pool_exhausted","pool_max":10,"load_src":"session-refresh","fix":{"pool":[10,50],"restart":true},"stable_min":40,"rec":"alert pool_util>80%"}',
 "D_sexpr":           "(rca auth (fail 15:00Z) (after deploy 2.4.1) (cause db-pool-exhausted max 10 by session-refresh) (fix (pool 10 50) restart) (stable 40m) (rec alert pool-util>80%))",
 "E_ascii_codebook":  "RCA AUTH F@1500Z DEP 2.4.1 CZ DBPOOL10 XH LD SREF FX POOL 10>50 RST OK40M REC ALRT POOL>80",
 "F_invented_glyphs": "⟁⚿↯15:00Z⇐⟐2.4.1∵⌸10⊘⇐⟳⚒⌸10→50↻✓40⚠⌸>80%",
 "G_emoji_mix":       "🔐💥15:00Z⬅️🚀2.4.1 ❓🗄️🏊10🪫⬅️🔄 🔧🏊10➡️50♻️ ✅40m ⚠️🏊>80%",
 "H_hebrew_prose":    "סיימתי את חקירת התקלה. שירות האימות התחיל להיכשל בשעה 15:00 זמן אוניברסלי, זמן קצר אחרי פריסת גרסה 2.4.1. שורש הבעיה היה שמאגר חיבורי מסד הנתונים, שהוגדר למקסימום 10 חיבורים, התרוקן תחת העומס המוגבר שהכניס פיצ'ר רענון ההפעלה החדש. כדי לפתור זאת, הגדלתי את גודל המאגר מ-10 ל-50 חיבורים והפעלתי מחדש את השירות. השירות יציב ב-40 הדקות האחרונות. אני ממליץ להוסיף התראה על ניצול מאגר מעל 80% כדי שנתפוס זאת מוקדם יותר בפעם הבאה.",
 "I_chinese_prose":   "我已完成对故障的调查。认证服务在15:00 UTC开始失败，就在部署2.4.1版本后不久。根本原因是数据库连接池（最大配置为10个连接）在新的会话刷新功能带来的负载增加下耗尽。为解决此问题，我将连接池大小从10增加到50并重启了服务。服务在过去40分钟内保持稳定。建议添加连接池使用率超过80%的告警，以便下次更早发现。",
 "J_gzip_base64_of_A": base64.b64encode(gzip.compress(A.encode())).decode(),
}

encs = {}
try:
    import tiktoken
    for name in ("o200k_base", "cl100k_base"):
        encs[name] = tiktoken.get_encoding(name)
except Exception as e:
    print("tiktoken unavailable:", e)

def count_claude(text):
    return c.messages.count_tokens(model="claude-opus-5-5", messages=[{"role":"user","content":text}]).input_tokens

claude = None
try:
    import anthropic
    c = anthropic.Anthropic()
    count_claude("ping")
    claude = count_claude
    print("Claude count_tokens: available (claude-opus-5-5)")
except Exception as e:
    print("Claude count_tokens unavailable:", type(e).__name__)

cols = ["sample","chars","bytes"] + list(encs) + (["claude-opus-5-5"] if claude else [])
print("\t".join(cols))
base = {}
for k, t in SAMPLES.items():
    row = [k, len(t), len(t.encode("utf-8"))]
    for n, e in encs.items():
        row.append(len(e.encode(t)))
    if claude:
        row.append(claude(t))
    base[k] = row
    print("\t".join(str(x) for x in row))

print("\nRatio vs A (tokens / tokens of A), per tokenizer:")
for k, row in base.items():
    ratios = []
    for i in range(3, len(row)):
        ratios.append(f"{cols[i]}={row[i]/base['A_english_prose'][i]:.2f}")
    print(f"  {k:22s} " + "  ".join(ratios))

if encs:
    e = encs["o200k_base"]
    print("\nHow o200k_base splits the glyph sample (each piece = 1 token):")
    print([e.decode([t]) for t in e.encode(SAMPLES["F_invented_glyphs"])][:40])
    print("How it splits the ASCII codebook sample:")
    print([e.decode([t]) for t in e.encode(SAMPLES["E_ascii_codebook"])])
