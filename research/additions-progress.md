# Additions from the six-repo review: progress

Branch: `add-ttl-whatif-and-waste-measurements` (one PR for everything below). Sources: two outside reviews of comparable tools, held outside the repo at `E:\Claude\ideal-umbrella-additions.md` and `E:\Claude\opus-review.md`; the second is the one to follow where they differ. **Rule from the user (2026-11-03): borrow the ideas, but never name where they came from in shipped text (README, CHANGELOG, docstrings, tests, PR body, commit messages).** Facts in them marked [V] were read from docs by a model, not re-checked: verify against the cited source before you rely on one in shipped text.

## Plan (do in this order; measurement first, each step gated by the one before)

### Step A: measurement scripts (read-only, stdlib only, `python -I`)
1. `scripts/ttl_whatif.py`: same transcript input as `usage_breakdown.py` (dedupe by message id, main chain and each subagent stream). Per response: gap since the previous response in the same stream, plus cache_creation and cache_read. Bucket gaps (<5m, 5-15m, 15-30m, 30-60m, 1-4h, >4h). Price (A) actual and (B) what-if 5-minute TTL (writes at 1.25x input instead of 2x; every response whose gap is over 5 minutes becomes a full rewrite of its prefix instead of a read). List "cache busts" (cache_read drops sharply, cache_creation near the whole context) with a likely cause (gap over TTL, compaction, other). Output in list-price terms and say plan limits are not dollars. Write the logic fresh; do not name or credit another project.
2. `scripts/top_waste.py`: rank where context goes per tool and per command from transcripts: share of tool_result characters by tool name, a histogram of Bash result sizes (buckets: <2k, 2-8k, 8-12k, 12-30k, >30k characters), and the top repeated Bash commands. Reuse `toolresult_share.py` / `usage_breakdown.py` helpers; do not duplicate their parsing if a shared helper exists.
3. `scripts/skill_bill.py`: for each skill folder (default: the Claude app's plugin and `~/.claude/skills` folders, input folder as an argument like `plugin_cost.py`) report always-on cost (frontmatter name+description tokens) and per-invocation cost (SKILL.md body plus referenced files), sorted, flagging a skill whose frontmatter sets `model` (invoking it switches model and breaks the cache; verify this in the prompt-caching docs at code.claude.com first). Token counts: use the same proxy and honesty note as the other scripts (no tiktoken in `scripts/` unless an existing script already does).
Each script: tests first (see CONTRIBUTING.md), one-line errors never tracebacks, `sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")`, `glob.escape` where globbing, covered by `tests/test_source_rules.py` and `tests/test_read_only.py` if those enumerate scripts. README "Contents" and "Measured numbers" updated; CHANGELOG `[Unreleased]`.
Then RUN all three on the real transcripts under `~/.claude/projects` (read-only) and record only aggregate numbers (no file contents, no paths of private projects) in this file under "Results".

### Step B: settings and rules gated by Step A's numbers
4. `bashOutputMaxChars`: first verify the setting name, minimum Claude Code version and behaviour in the current docs (code.claude.com settings reference). If it exists and the Step A histogram shows Bash results over ~8k characters hold a meaningful share, add it to `config/user-settings.json` (value 8000-12000, justified by the histogram), keep `tests/test_docs_match_source.py` green (README settings table), say the version needed. If not supported or not justified, document the decision in README "What did not work" with the numbers instead.
5. `promptCacheTtl`: do NOT turn on by default. Document the `ttl_whatif.py` result and, only if the numbers favour 5m and the setting is verified, document it as an opt-in in README.
6. `scripts/ledger.py --tag` (or an equivalent small addition) plus a README paragraph on holdout/A-B measurement and the `/usage` "Prompt cache" line; label the savings line honestly as an estimate against a hand-set baseline.
7. Rules in `config/CLAUDE.md` (and the identical copy in `config/cloud-setup.sh`, which `tests/test_docs_match_source.py` compares): at most two short lines: stop after 3 failed fix attempts and write the cause to `notes/learnings.md`; size the process to the change (small change goes straight to build). Check the existing text first; do not add what is already there. Keep the rule file small: every line costs tokens on every call.
8. `hooks/bash_trim.py`: ONLY if the Step A histogram shows many 3-10k-character test/build logs that item 4 would not catch. Otherwise record "not built, histogram says no" in README "What did not work". If built: Bash only, narrow matcher, never touches Read/Edit input, fails open (returns original), keeps error lines and head/tail, writes the full output to a file under `~/.claude/ballast/`, installed and uninstalled by `config/install.py`/`uninstall.py` with the same care as `context_check.py`.
9. Progressive-disclosure layout for `notes/learnings.md` (index of one-line entries): only describe it in `config/learnings.md` if the file template stays smaller; skip if it does not.

### Step C: review, push, PR
Own review against CONTRIBUTING.md ("fix the class", the three recurring classes). Push the branch and open ONE draft PR (template: `.github/PULL_REQUEST_TEMPLATE.md`; all steps stay in this PR). After everything is done, the final reviewer runs on Opus 5.5 (an Agent with model "opus", fresh context, given the diff against main, the intent and this file; it must not see the author's conclusions first). Fix what it finds that is real, push to the same PR, then report.

## How to work
Use sub-agents for each step if useful (one writer at a time on the checkout). The user asked for this to run in its own chat: report to the user in at most 5 lines plus file paths.

## Rules for whoever works on this
- CONTRIBUTING.md governs. Run every command in README "Tests" before each commit; CI is Windows 3.12 and Ubuntu 3.10-3.14.
- Replace the resume point below at the end of each task; do not append.
- Commit messages end with the attribution line given by the session.

## Results
Step A run on 2026-11-03 with `python -I scripts/<name>.py <project folder> 60` on the two largest project folders under `~/.claude/projects` (Windows, subscription, 1-hour cache writes in use). Aggregates only.
- ttl_whatif: 15,115 and 9,761 API responses; 94% and 96% followed a gap under 5 minutes. List-price cache cost with a 5-minute TTL what-if: +20% ($1,133 -> $1,358) and +21% ($532 -> $644). Busts: 352 and 117 "gap over TTL", 3 compaction, ~10 other. Verdict: do not switch to 5m.
- top_waste: 71.9M tool-result characters over 3 folders; Bash+PowerShell 66%, Read 30%, everything else under 1% each. Shell results (20,034): <2k 17.6% of shell chars (13,569 results), 2-8k 41.8% (5,011), 8-12k 15.5% (758), 12-30k 25.1% (696), >30k 0 (output already capped at 30k). Gate for item 4 passes (results over 12k are a quarter of shell characters); item 8 (3-10k logs): 2-8k holds 42% but that is mostly small outputs a hook would not shrink much; decide at item 8.
- skill_bill (corrected after review: the first run also counted desktop-session copies and missed linked folders): 49 skills in ~/.claude/skills plus installed plugins, always-on listing about 5,800 tokens (o200k proxy), largest per-use bodies 21-29k tokens (memory-architecture, auto-build).

## Verified facts (code.claude.com, 2026-11-03)
- `bashOutputMaxChars` (settings, any file, v2.1.261+, up to 128,000): sizes the inline ceiling and read-back window together; default inline ~30,000 for a valid result (past it: file path plus 2,000-char preview); failure results inline ~10,000 (head+tail). Env `BASH_MAX_OUTPUT_LENGTH` is ignored when the setting is set.
- `promptCacheTtl` setting ("5m"|"1h", env CLAUDE_CODE_PROMPT_CACHE_TTL, v2.1.242+): subscription users within included usage get 1h on the main conversation automatically; API-key/cloud users default to 5m; 1h writes cost more. `FORCE_PROMPT_CACHING_5M=1` forces 5m.
- Skill `model` frontmatter: override applies for the rest of the turn, not saved; docs on prompt caching say switching models recomputes the whole request. `/usage` shows a "Prompt cache (main)" line (v2.1.251+).

## Resume point
State (2026-11-03): PR 40 (draft) holds the work plus the fixes for the first Opus review (E:\Temp\opus-review-pr40.md; findings 1-4 and 6-9 fixed with tests, 5 documented in CONTRIBUTING). Full README "Tests" run before the fix commit: only tests/test_keyline_check.py fails (1 timing, 20 env-var errors), identical on origin/main (checked by a real run). A second Opus review of the updated diff was requested by the user.
Left: push, wait for CI, update the PR body, run the second Opus review (fresh context), fix real findings, push, replace this resume point.
