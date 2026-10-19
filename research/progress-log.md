# Machine-only compressed language — progress (saved 2026-10-18)

Session paused at the user's request to wait for usage reset. This file is the resume point.

## The request (user, 2026-10-17)
Design a language that LLMs (Claude/GPT) write in instead of long human prose, so output is much shorter, files are light, and only machines read it. On request the machine must translate it to the user's language (English/Hebrew/...). Be honest, creative, less deterministic.

## Established facts (measured this session)
Benchmark script: `C:\Users\PC\AppData\Local\Temp\claude\C--Users-PC-Desktop-gittoken\57c9c8f0-2bc8-44d2-b435-a74480b9b591\scratchpad\tokentest.py`
Venv with tiktoken 0.14.0: `...\scratchpad\tokenv\Scripts\python.exe`
Same incident report, same meaning, token counts (o200k_base / cl100k_base):

| Notation | chars | o200k | cl100k | ratio vs prose (o200k) |
|---|---|---|---|---|
| English prose | 596 | 121 | 122 | 1.00 |
| Terse English | 184 | 61 | 61 | 0.50 |
| JSON | 223 | 72 | 72 | 0.60 |
| S-expression | 163 | 62 | 62 | 0.51 |
| ASCII abbreviation codes (lossy) | 90 | 43 | 44 | 0.36 |
| Invented Unicode glyphs (lossy) | 40 | 49 | 58 | 0.40 |
| Emoji mix (lossy) | 51 | 57 | 67 | 0.47 |
| Hebrew prose | 423 | 167 | 397 | 1.38 |
| Chinese prose | 160 | 109 | 147 | 0.90 |
| gzip+base64 of prose | 492 | 342 | 354 | 2.83 |

Key observations:
- Invented glyphs cost MORE than 1 token per character (each glyph splits into byte fragments). They only "won" by dropping information.
- ASCII abbreviation codes fragment into sub-word tokens (R|CA, PO|OL) — not single tokens.
- Compressing on disk (gzip/base64) makes the model's read ~2.8x MORE expensive.
- Terse English / S-expr / JSON ≈ half the tokens of prose, lossless. That is the honest floor for a text-based scheme.
- Hebrew is 1.4x (o200k) to 3.3x (cl100k) more expensive than English for the same content → machine notes should be in English; translate to Hebrew only on request.

## Verified prior art (web search 2026-10-17)
LLMLingua / LongLLMLingua (2x–6x prompt compression), LLMLingua-2, gist tokens (Mu et al. 2023), In-context Autoencoder (ICAE), AutoCompressors, CacheGen (KV-cache compression). All need model training or internals; not usable by an API user on Claude/GPT today.

## Pricing facts (claude-api skill, cached 2026-10-06)
Opus 5.5: $4 in / $20 out per MTok, cache reads $0.20. Fable 5.1: $10 / $50, cache reads $0.25. Haiku 5.5: $0.10 / $0.50. Output tokens ≈ 5x input; cached input ≈ 20x cheaper than fresh. Caching is prefix-based.

## Ideation panel (Workflow tool)
Run ID: `wf_6361f28d-f77`
Script: `C:\Users\PC\.claude\projects\C--Users-PC-Desktop-gittoken\57c9c8f0-2bc8-44d2-b435-a74480b9b591\workflows\scripts\machine-language-ideation-wf_6361f28d-f77.js`
Transcript/journal: `C:\Users\PC\.claude\projects\C--Users-PC-Desktop-gittoken\57c9c8f0-2bc8-44d2-b435-a74480b9b591\subagents\workflows\wf_6361f28d-f77\journal.jsonl`
Design: 6 angles (tokenizer, information theory, systems/cost, linguist/notation history, safety skeptic, wildcard) → one adversarial refuter per angle (measures tokens) → one synthesis agent producing a spec with measured examples.
Status: COMPLETE (resumed 2026-10-18 02:04 local, finished ~02:40). 13 agents, 0 errors, 10 ideas survived refutation, 14 refuted. Full extracted results: `machine-language-panel-results.md` next to this file. To re-run:
`Workflow({scriptPath: "<script path above>", resumeFromRunId: "wf_6361f28d-f77"})` — completed agents return cached results.

## Draft verdict to deliver (my own, before panel results)
1. The premise is half right. Cost is per token, not per word. A *new* symbol language tokenizes worse, not better. The real lever is "fewer tokens per unit of meaning using tokens the model already has cheaply": terse English, code-like/structured notation, references instead of repetition, deltas instead of full rewrites.
2. The biggest waste is not the data, it is the prose around it (explanations, narration, pleasantries) and re-reading the same files every turn. Both are fixable today with instructions + prompt caching, no new language needed.
3. A machine-only language is dangerous if the *translator* is the LLM (hallucinated decompression, model drift, cross-model disagreement). Make the language a lossless formal notation with a deterministic decoder (a program), and let the LLM only read/write it. Then "translate on request" is guaranteed, in any human language, via templates.
4. Concrete proposal: plain-ASCII, line-oriented fact/delta notation with a tiny versioned header; codebook lives once in a cached prefix; files store data + pointers, not prose; renderer program expands to English/Hebrew. Expected: ~2x on structured content, much less on nuanced prose, near-zero on code.
5. The truly "machine-native" language is not text at all: KV-cache / gist tokens. Only the provider can do that; prompt caching is the form available today.

## Build (2026-10-18)
Tool folder built by a separate session: `C:\Users\PC\Desktop\gittoken\keyline\` (keyline_check.py, keyline_lint.py, measure.py, keyline_hook.py, hooks-example.json, CLAUDE-snippet.md, README.md, tests/). Verified here: `.venv/Scripts/python.exe -I tests/run_tests.py` -> 22/22 passed, all token counts within 2 of the panel. Not yet wired into any repo; hook tested with simulated events only.

## Next steps when resuming
1. Read journal.jsonl; if the run finished, pull `spec`, `survivors`, `dead`, `premise_verdicts` from the final result.
2. If not finished, resume the workflow with the command above.
3. Write the final answer to the user (honest verdict + proposal + measured table + what to build first), tagging claims per the evidence rule.

## Pilot (2026-10-18 ~15:00)
Lint fix: abbreviation rule now flags only abbreviation-shaped multi-token words; 3,774 -> 87 distinct flags on 400 gittoken markdown files; 8 of 9 invented test abbreviations still caught (pkts passes). Suite 30/30.
Converted rk-wt/PROGRESS.md to Keyline: 2,114 -> 2,067 o200k tokens (-2%); 169/169 invariants present; backup rk-wt/.keyline-backup/PROGRESS.md.orig.
Hook wired via settings.local.json in gittoken/.claude and rk-wt/.claude, --watch on that one file; active from the next new session only.
Finding: an agent-written terse file saves ~2%; Keyline's gains come from padded prose and markdown-heavy notes, not already-terse logs.

## Usage measurement and compaction change (2026-10-18 ~15:15)
Billed usage in the 3 largest gittoken transcripts: cache reads 58%, cache writes 27%, output 15% of cost at Opus 5.5 list prices; output chars 84% tool calls, 12% visible text. Research-Kit sweep session: median 425,166 tokens re-read per call, 693 tokens read per token written. Conclusion: context size per call, not output wording, drives usage.
Set autoCompactWindow=250000 in gittoken/.claude/settings.local.json and rk-wt/.claude/settings.local.json (hook entries kept; a session reads only its own folder's project settings). Not active in the session that set it (still 97%); verify in a new gittoken session with get_usage.
VERIFIED 2026-10-18: a new session opened in gittoken reported contextWindow 250,000 and autoCompactsAtPercent 87 (compaction near 217,500 tokens); a fresh session already starts near 96k tokens of fixed overhead (system tools, MCP tools, prompt, skills).
CONNECTORS 2026-10-18: set disableClaudeAiConnectors=true in gittoken/.claude/settings.local.json and rk-wt/.claude/settings.local.json. Baseline from fresh gittoken session local_63ff22b9 (started before the change): total 96,690; MCP tools 26,428; MCP server instructions 6,261; system tools 34,627; skills 9,913; system prompt 9,389. Compare a NEW gittoken session's get_usage categories against these. Undo: delete the key from both files.
CONNECTOR RESULT 2026-10-18: disableClaudeAiConnectors had NO effect in the Claude desktop app (new session 15:51 still loaded all connectors; MCP tools 26,428 and instructions 6,261 unchanged), so the key was removed again from both files. The app's own connector switch (set_session_connector_enabled) is account-wide. Measured cost of connector tool-name lists: 8,948 tokens per call (Figma 1,243, Webflow 1,092, wawesome 1,072, Gmail 952, Slack 826...). Most of the 26,428 MCP-tools tokens are app-internal tools, not connectors.
CONNECTORS OFF 2026-10-18 ~16:05 (account-wide default, user's choice): Figma, Webflow, api.wawesome.io, Slides AI, Gmail, Slack, Google Drive, Google Calendar, Zapier, Supermetrics, Semrush, Bigdata.com, Claude Docs. Kept: Firecrawl (18 calls since 2026-10-10, the only one used), GitHits, Composio, Hugging Face, visualize. Expected: about 7,714 fewer tool-name tokens per call, plus their server instructions. Verify in a new session against the baseline (total 96,690; MCP tools 26,428; MCP server instructions 6,261). Re-enable from the composer + menu > Connectors.
MEASURED AFTER CONNECTORS OFF 2026-10-18: new gittoken session total 81,423 (before 96,690, -15,267, -15.8%); MCP server instructions 1,384 (before 6,261); MCP tools 25,818 (before 26,428); Messages no longer among the largest categories (before 9,780). Remaining fixed load: system tools 34,627, MCP tools 25,818 (mostly app-internal), skills 9,913, system prompt 9,389. Next candidate lever: unused plugins and the skills list.
PLUGINS 2026-10-18: user chose to disable 16 claude.ai account plugins (must be switched off in the app's plugin settings; no tool can do it): legal, marketing, product-management, operations, data, design, engineering, advisorppc (plugin_012R3FKrUy8izmKxWHDL94dm), zizi-skills (plugin_01J4b9tFUHrKDvWpAPiziYAf), pwp (plugin_013BWAiAf6WpZhjju71ngsSS), codacy-skills (plugin_01AUyTaarX3ZHmZTdnyUtWyC), jointjs-claude-playground (plugin_01NpC3i4LYpeNSKbjWBkUun7), browser-use (plugin_01Cng2GP1yhRBivmDfvFVbB8), desktop-commander (plugin_01Y2NkU2XtxLmeitTyCQSgMB), github (plugin_01UZByMPnV7hP67cma9DLbSR), pdf-viewer (plugin_011v5h6QUzBZvas64y44XLhy). Kept: lesslop (evidence-rule hook, 394 tokens per prompt), anthropic-skills (xlsx used), figma, gitbook, tavily, qt-development-skills, first-pass, altimate-code, small extras. Skills list is capped near 9,913 tokens (full demand 21,642), so the list may not shrink; notices (needs-auth ~331, failed ~184 tokens) should mostly disappear. Next lever: skillListingBudgetFraction.
SKILL BUDGET 2026-10-18: skillListingBudgetFraction=0.005 set in gittoken and rk-wt local settings (default 0.01). Baseline Skills category 9,913 tokens in every session measured today. Expect about half in a NEW session if the app honors it; if Skills stays 9,913 the app ignores it like disableClaudeAiConnectors, so remove the key. Undo: delete the key from both files.
SKILL BUDGET RESULT 2026-10-18 ~17:25 (after PC restart): skillListingBudgetFraction WORKS. Skills 9,913 -> 4,919 (-4,994, -50%) in a new gittoken session and in this one. But System tools rose 34,627 -> 40,693 (new session) / 39,621 (this session), cause not found, so the new-session total was 82,504 vs 81,423 before. The 16 plugins were still enabled after the restart (their needs-auth/failed notices still appeared). Keep the key.
PENDING 2026-10-18 ~17:35: user is disabling the 16 plugins and turning off the built-in browser tools (Settings > Claude Code > Browser), then measuring in a NEW gittoken session after the Research-Kit commit queue (started 17:23) finishes. Compare against post-restart baseline: total 82,504; System tools 40,693; MCP tools 25,818; System prompt 9,389; Skills 4,919; MCP server instructions 1,384. Browser tools as the cause of the +6k System tools is unconfirmed.
LLMLINGUA CHECK 2026-10-18 ~18:00: gist tokens need the model itself trained (arXiv 2304.08467) -> unusable. LLMLingua-2 (small XLM-RoBERTa/mBERT model, 2-5x, arXiv 2403.12968) could plug in via a PostToolUse hook updatedToolOutput (docs/hooks), but in sessions 9ee97c33+57c9c8f0 tool results are only 30% of context chars (Bash 15%, Read 5%; Read must stay exact for Edit). Bigger buckets: one update-config skill load 290,435 chars (15%), 55 messages from other sessions 281,961 (15%), another skill load 104,391 (6%), task notifications 45,416 (2%). Lever: short reports from side sessions/subagents (details to a file), no huge skill loads in long sessions. New-session measure after plugin changes: total 82,965 (System tools 39,581, MCP tools 25,856, Skills 4,959, MCP instr 2,879); pwp + codacy-skills still enabled; browser_tools still On.
CLAUDE.md 2026-10-18 ~18:10: created gittoken/CLAUDE.md (204 chars, 50 tokens o200k/cl100k): side sessions and subagents write details to a file and reply with a gist of at most 5 lines plus the path; briefs must ask for that. Loaded at launch by every new session opened in gittoken or any subfolder (docs/memory); not by sessions already running. Baseline to beat: 55 reports from other sessions averaged 5,126 chars across sessions 9ee97c33 and 57c9c8f0. Undo: delete the file.
BALLAST 2026-10-18 ~18:20: user named the system (proposed name Ballast). Applied to all Claude Code sessions: autoCompactWindow 250000 + skillListingBudgetFraction 0.005 added to ~/.claude/settings.json (backup scratchpad/user-settings.before-ballast.json); report rule moved from gittoken/CLAUDE.md (deleted) to ~/.claude/CLAUDE.md. Project local settings in gittoken and rk-wt still repeat both keys. New sessions get all of it at launch; running sessions read CLAUDE.md only at launch.
REPO 2026-10-18 ~18:35: everything pushed to https://github.com/StepenkoAnatoli/Ideal-Umbrella (PUBLIC) on branch claude/save-progress, commit 5cbb066 (main untouched). Local clone gittoken/Ideal-Umbrella. Layout: README, config/ (settings snippet + CLAUDE.md rule), keyline/, research/ (progress-log = this file, panel-results), scripts/. Re-copy this file to research/progress-log.md when it changes.
REPO MERGED 2026-10-18: main on Ideal-Umbrella fast-forwarded to 5cbb066 and pushed (user asked); branch claude/save-progress still exists at the same commit.

## Old resume point (2026-10-18 18:22)
State: Ballast applied to all Claude Code sessions (~/.claude/settings.json: autoCompactWindow 250000, skillListingBudgetFraction 0.005; ~/.claude/CLAUDE.md short-report rule, 50 tokens). Backed up publicly at https://github.com/StepenkoAnatoli/Ideal-Umbrella (main), local clone gittoken/Ideal-Umbrella; research/progress-log.md there is a copy of this file.
Last measures: fresh session 83,080 tokens (System tools 39,579; MCP tools 25,856; System prompt 9,389; Skills 4,961; MCP server instructions 2,879; Memory files 226). This chat (57c9c8f0) reached 202,866 tokens (81%) and should be retired; continue in a NEW chat.
Open items:
1. User to switch off the remaining plugins pwp and codacy-skills and the built-in browser (Settings > Claude Code > Browser), then measure a new session; open question: System tools rose ~6k after the 17:19 restart, cause unknown.
2. Confirm the user-level settings in a session opened OUTSIDE gittoken (window 250,000, Skills ~5k).
3. Watch whether side-session/subagent reports get short under the CLAUDE.md rule.
4. Re-copy this file to Ideal-Umbrella/research/progress-log.md and push after changes.
Not ours: Research-Kit commit queue (another session, started 17:23): misc-a a8f923c 18:05 and gate a83ce6a 18:06 committed (~42 min each); transport, autocollect, cli-args, machine-config still staged; keep the machine quiet until it ends.
LONG-CHAT RULE 2026-10-18 ~18:35: added to ~/.claude/CLAUDE.md (file now 118 tokens): past 150k tokens at a step boundary, write a resume point to the progress file and offer a fresh session pointing to it; keep decisions in files. Synced to Ideal-Umbrella config/CLAUDE.md and README.
HANDOFF HOOK 2026-10-18 ~18:55: UserPromptSubmit hook ~/.claude/ballast/context_check.py added to ~/.claude/settings.json (backup: session 57c9c8f0 scratchpad user-settings.before-handoff-hook.json). Reads context size from the transcript (last main-chain usage; compact_boundary postTokens after compaction); past 150k it injects a hand-off note for Claude + a systemMessage for the user; repeats every +25k; state in ~/.claude/ballast/state/. Tested on copies of this transcript (217k fires once, repeat silent, boundary silent, bad input silent); ~1 s per run (bare python ~0.63 s). Not added to PostToolUse: ~1 s per tool call. Not yet seen live in a chat past 150k. Repo commit 7cb7513.
CLOUD 2026-10-18 ~19:10: cloud sessions read neither ~/.claude/settings.json nor ~/.claude/CLAUDE.md (docs: settings#settings-in-cloud-sessions, cloud-environments). Wrote Ideal-Umbrella/config/cloud-setup.sh (writes ~/.claude/CLAUDE.md in the session: same rules + "commit and push the progress file"; 144 tokens; tested twice in a temp HOME, exit 0). User pastes it into the cloud environment setup script. Hook/settings for cloud not done (would need committing .claude/settings.json per repo). Commit c628696.
RENAME 2026-10-18 ~19:25: the user renamed the system from Ballast to Ideal-Umbrella (README edit on GitHub, 24b31d4). Renamed in hook messages, env vars (now IDEAL_UMBRELLA_HANDOFF_AT / _STEP), script comments, README and memory (ballast-setup.md -> ideal-umbrella-setup.md). Kept on purpose: the ~/.claude/ballast/ folder (hooks in open chats point there). Older lines above keep the old name as history.

## Items 1-4 log (from the 2026-10-18 19:30 resume point)
State: Ideal-Umbrella (first called Ballast) applies on this PC to every chat:
- ~/.claude/settings.json: autoCompactWindow 250000, skillListingBudgetFraction 0.005, UserPromptSubmit hook ~/.claude/ballast/context_check.py (past 150k: tells Claude to offer a fresh session + notice to the user; again every +25k; env IDEAL_UMBRELLA_HANDOFF_AT/_STEP).
- ~/.claude/CLAUDE.md: short-report rule + long-chat rule (118 tokens).
- Cloud: config/cloud-setup.sh in the repo writes the same rules (+ push the progress file) inside cloud sessions; the user pastes it into the cloud environment's setup script. Hook/settings not in cloud (would need .claude/settings.json committed per repo).
- Backup repo github.com/StepenkoAnatoli/Ideal-Umbrella, main = claude/save-progress (commit 49ef934 or later). The user also edits it on GitHub: fetch before pushing.
Decisions and why: ~/.claude/ballast/ folder kept (open chats' hooks point there; python exits 2 on a missing script). Hook only on UserPromptSubmit (~1 s per run; PostToolUse would add that to every tool call). Old log lines keep the old name as history.
Open items:
1. User: turn off pwp, codacy-skills and the built-in browser, then measure a new chat with get_usage (last: 83,080).
2. Watch the hook fire live the first time a chat passes 150k (systemMessage "Ideal-Umbrella: context about ...").
3. User: paste config/cloud-setup.sh into the cloud environment; check a cloud chat loads the rules.
4. DONE 2026-10-18 (session f4c53204, commit 8287185 on Ideal-Umbrella main): hook + two keys for cloud via committed .claude/settings.json.
   - Docs (code.claude.com cloud-environments, settings#settings-in-cloud-sessions): an Anthropic-hosted cloud session reads hooks only from the repo's .claude/settings.json (single-repo sessions only) and from server-managed settings; ~/.claude/settings.json is never read; CLAUDE_CODE_REMOTE=true only in the cloud; both keys are "Any file" scope; env CLAUDE_CODE_AUTO_COMPACT_WINDOW on the cloud environment also sets the window, multi-repo sessions included.
   - Ideal-Umbrella/.claude/settings.json: the two keys + UserPromptSubmit hook, shell bash: `[ "$CLAUDE_CODE_REMOTE" = true ] || exit 0; python3 -I "$CLAUDE_PROJECT_DIR/hooks/context_check.py"; exit 0`. Guard = locally only the user-level hook runs (no double notice, no python3 lookup). Trailing exit 0 = a missing script can't exit 2 and block the prompt.
   - Other repos: `python -I config/add_to_repo.py <repo>` merges config/repo-settings.json (path .claude/hooks/context_check.py) and copies the script; keeps other keys/hooks; second run "already up to date"; refuses broken JSON. Then commit the two files in that repo.
   - Tested by simulation only (Git Bash, fake USERPROFILE): local silent; cloud sim notice at threshold 1000; repeat silent; missing script exit 0; installer cases A/B/C. Not yet seen in a real cloud session.
   User's choice: only Ideal-Umbrella for now; the user runs add_to_repo.py on other repos when needed. Open: check one real cloud chat on Ideal-Umbrella (/hooks or a low IDEAL_UMBRELLA_HANDOFF_AT env on the environment).
Items 1-3 started 2026-10-18 in session f4c53204 (context ~150k):
- pwp and codacy-skills are already gone: not in ListPlugins (claude.ai), not in ~/.claude/plugins or settings, not in that session's skills/MCP list. Browser tools still On (get_settings); only the user can switch them off (Settings -> Claude Code -> Browser).
- User did both (browser off, cloud-setup.sh pasted).
- Item 2 DONE: the +25k repeat also fired live (180k, next band). First firing: in f4c53204 on the user's prompt at 161k ("Ideal-Umbrella: this chat's context is about 161k tokens (over 150k)..." arrived as additional context).
- Item 1 measured (side session local_d3ddee82, details in side-session-notes/local_6e7eb65e-.../usage-measure.md): new chat 82,845 tokens vs 83,080 (-235). System tools 39,579; MCP tools 25,856; system prompt 10,105; skills 4,961; MCP instructions 1,700; memory 373. pwp/codacy gone. But the built-in browser's ~18 tools were still loaded although the toggle was off. Open: restart the app, then measure again (same brief: get_usage first, nothing else).
- Item 3: start_session can't open a cloud session from f4c53204 (its project folder gittoken has no git remote). User starts it: New session -> Cloud -> StepenkoAnatoli/Ideal-Umbrella, first message = gittoken/cloud-check-prompt.md. Result lands on that session's branch as research/cloud-check-2026-10-18.md; fetch and read it, then note pass/fail here. Also covers a real-cloud check of item 4's hook.
  Status 2026-10-18: user started it; the cloud chat said it pushed, but `git ls-remote` shows only main (33844c4) and claude/save-progress: no new branch, no result file. Cloud chats are not in list_sessions, so f4c53204 can't read it. Item 3 UNCONFIRMED. Next: get the cloud chat's own reply (pass/fail lines, branch name, repo) from the user, or ask the cloud chat to run `git push -u origin HEAD` and show `git remote -v` and the output.
  Recheck 19:38 and 19:41 (side session local_e1da3c0e's parent): ls-remote still only main (c176078) + claude/save-progress. Still UNCONFIRMED; waiting for the cloud chat's reply or a new push.
- Item 1 re-measured 19:41 (side session local_e1da3c0e, details in side-session-notes/local_4990c8dd-.../usage-after-restart.md): new chat 82,764 (-81 vs 82,845). All categories identical (System tools 39,579; MCP tools 25,856; system prompt 10,105; skills 4,961; MCP instr 1,700; memory 373); only the unlisted remainder changed (shorter brief). 19 mcp__Claude_Browser__* tools still loaded in full, plus the <browsers> system-prompt sections.
  Why: get_settings reports browser_tools = On, so the Browser switch is not off (or didn't save). Also the app was NOT restarted: the desktop Claude.exe main process has run since 17:19:16. Next: user turns Settings -> Claude Code -> Browser off, confirms get_settings shows Off, quits from the tray, then a new chat is measured again.
  Recheck 19:48 after the user said they did it: get_settings still browser_tools = On; app main process still from 17:19:16; ls-remote unchanged. claude_desktop_config.json and mcp-user-tool-toggles.json were written at 19:47 (something was toggled), but no Code-browser key in them (only coworkBrowserToolsEnabled: true, the Cowork browser). Side session NOT started (it would repeat 82,764).
- Item 1 RESULT 2026-10-19 ~08:57 (app really restarted 08:43:15; side session local_db5be1a5, details in side-session-notes/local_4990c8dd-.../usage-browser-off.md): new chat 82,504 (-260 vs 82,764). System tools 39,579 (0); MCP tools 25,847 (-9); system prompt 9,709 (-396: the <browsers> section is gone); skills 4,961; MCP instr 1,700; memory 518 (+145, MEMORY.md grew). FAIL for the browser: the 19 mcp__Claude_Browser__* tools and the <built_in_browser> prompt section are still loaded.
  Why: get_settings still reports browser_tools = On after the restart. The switch that was turned off was Claude in Chrome (its MCP server disconnected at the restart, which removed the <browsers> section), not Settings -> Claude Code -> Browser. Next (user): switch that one off; expected saving is part of the 25,847 MCP tools, plus the <built_in_browser> section.
- Item 3 RESULT 2026-10-19 08:55: FAIL (nothing arrived). ls-remote still only main (c176078) + claude/save-progress; GitHub's events API for the repo shows no CreateEvent or PushEvent after 16:30Z (19:30 local) on 2026-10-18 and no PRs, so the cloud chat's push never reached this repo. Rules, CLAUDE_CODE_REMOTE/python3 and the hook stay UNVERIFIED in a real cloud chat. Next (user): paste that chat's reply, or have it run `git push -u origin HEAD` and show `git remote -v` and the output.
- Item 1 DONE 2026-10-19 ~09:05 (side session local_ae76770b, details in side-session-notes/local_4990c8dd-.../usage-code-browser-off.md): user switched off Settings -> Claude Code -> Browser; get_settings browser_tools = Off. New chat 71,396 (-11,108 vs 82,504, -13.5%). MCP tools 15,023 (-10,824: the 19 mcp__Claude_Browser__* tools gone, ~570 each, not even deferred); system prompt 9,425 (-284: <built_in_browser> section gone); everything else identical (System tools 39,579; skills 4,961; MCP instr 1,700; memory 518). No app restart was needed: the desktop process still dated from 08:43:15, so the switch reaches new chats directly.
  Trade-off: no built-in browser or dev-server preview (preview_start) in Code chats; undo = switch it back on. Next saving targets: System tools 39,579 (55% of the start context, 20 built-in tools); optional MCP tools still loaded in full: visualize (2) and firecrawl scrape/search (2).
Research-Kit commit queue belongs to another session: do not touch.

## RESUME POINT (updated 2026-10-19 13:25 local = 10:25Z; replace this section, don't append)
State: Ideal-Umbrella applies on this PC to every chat:
- ~/.claude/settings.json: autoCompactWindow 250000, skillListingBudgetFraction 0.005, UserPromptSubmit hook ~/.claude/ballast/context_check.py (seen firing live at 161k, 180k and 156k).
- ~/.claude/CLAUDE.md (224 tokens): short reports from side sessions; briefs ask for that and for a resume-point update; archive a finished side session after checking its result (user's standing request 2026-10-19); resume point + fresh-chat offer past 150k; update this resume point at the end of each task that changed something; decisions in files.
- Settings -> Claude Code -> Browser is off: a new chat starts at 71,396 tokens (was 83,080). Ground truth from a transcript's first call is lower: 65,483 for a fresh side session before the cuts below. get_usage also counts deferred MCP schemas.
- Tool cuts, 2026-10-19, chosen by the user: ~/.claude/settings.json permissions.deny = Artifact, ScheduleWakeup, ReportFindings, SearchPlugins, SuggestPluginInstall, SuggestSkills (0 calls in 60 past chats), plus mcp__visualize, mcp__visualize__show_widget, mcp__visualize__read_me. Measured in a fresh side session: first call 65,483 -> 49,423 tokens (-16,060, -25%); the six built-ins are gone. The server-wide rule mcp__visualize did NOT remove visualize; the two exact names were added afterwards, not yet checked. Backup: ~/.claude/ballast/settings.before-deny.json (undo: copy it back). Prompt suggestions are off (one fewer request per reply). The user kept Workflow and Firecrawl scrape/search. Cuts take effect in new chats only; an open chat keeps its tools, so its cache isn't rewritten.
- Cloud: config/cloud-setup.sh (same rules + push the progress file, 250 tokens) is pasted into the cloud environment; Ideal-Umbrella/.claude/settings.json gives cloud chats the hook and keys (other repos: config/add_to_repo.py).
- Repo github.com/StepenkoAnatoli/Ideal-Umbrella, main. The user also edits it on GitHub: fetch before pushing; scan for secrets (public).
- Rules check, 2026-10-19, fresh chat local_bc18b3ca: the archive, short-report and 150k-hook rules work in a fresh chat (the hook was simulated on a 214k transcript: one note, then silent). A fresh side session (Sonnet) did its task but skipped its resume-point update, because its brief limited where it could write. So the brief rule now asks for that update too (CLAUDE.md, config/CLAUDE.md, config/cloud-setup.sh, pushed to main).
Decisions and why:
- ~/.claude/ballast/ keeps its first name: hooks in open chats point there.
- Hook only on UserPromptSubmit: ~1 s per run, too slow for every tool call.
- After a restart, start a fresh chat from this section instead of reopening a long one: the prompt cache lives 1 hour, so a reopened chat re-writes its whole context.
- Briefs ask the side session to update the task's resume point: a side session follows its brief's limits over CLAUDE.md (seen in the rules check).
Open items:
1. Cloud check unconfirmed: the cloud chat's push never reached GitHub (Items 1-4 log above). Needs the user: paste that chat's reply, or run `git push -u origin HEAD` there.
2. Re-paste config/cloud-setup.sh into the cloud environment's setup script (claude.ai/code -> environment settings, done by the user): the pasted copy predates the brief-rule change.
3. In the next fresh chat, check that mcp__visualize__show_widget and read_me are gone from the tool list (the exact-name deny rules). If they are still there, the desktop app adds them outside the deny filter: drop the three visualize rules. Remaining ideas: computer-use server instructions (~1.2k tokens per chat, 0 uses; the user can switch computer use off in the app's settings), duplicate skill listings (plain and anthropic-skills: copies), altimate-code plugin start-up text.
4. The new brief line has not yet been seen working in a side session.
Linked sessions local_1ef499f0 (waits on the user for the cloud check) and local_4990c8dd (waits on it): keep until the cloud check is settled, then archive both.
Never touch gittoken/research-kit (the user's own checkout).
