# Ideal-Umbrella: history

How a request for a machine-only language became a set of rules, settings and one hook that cut the tokens Claude Code re-reads on every call. Sources: `research/progress-log.md` (the full work log, ending in the 2026-10-19 14:05 resume point), the git history and `README.md`.

Two measures of a new chat appear below. **get_usage** is the app's own report of a new chat's context, and it also counts deferred MCP schemas. **First call** is the token count of a fresh chat's first request, read from its transcript. The first-call count is lower: it was 65,483 for a fresh side session in the period when get_usage gave 71,396.
Where sources disagree, the later one is used. `README.md` still says a new chat's fixed load is "about 83k tokens", but the later resume point says 71,396. The first side measurement counted "~18" browser tools, and later ones counted 19. Clock times in the log are approximate, and some differ from the git commit times, so most entries give dates only.

## Summary
- **Goal.** Make Claude Code waste fewer tokens. In the user's own transcripts, cost was 58% cache reads, 27% cache writes and 15% output. Every call re-reads the whole context, so the lever is a smaller context per call, not shorter wording.
- **A new language does not help.** For the same report, terse English uses 0.50x the tokens of prose and loses nothing. Invented glyphs cost more than one token per character. gzip+base64 costs 2.83x prose.
- **A new chat got smaller (get_usage).** It was 96,690 tokens at the start and 81,423 after unused connectors were switched off. It then stayed between 82,504 and 83,080 while plugin and browser switches were tried. It is 71,396 since Settings -> Claude Code -> Browser was switched off.
- **The first call got smaller.** Denying six built-in tools that 60 past chats never called cut a fresh chat's first call from 65,483 to 49,423 tokens (-16,060, -25%).
- **Smaller fixed load and earlier compaction.** The skills list went from 9,913 to 4,919 tokens (-50%). Chats now compact in a 250,000-token window at 87% (near 217,500) instead of a 1,000,000-token window at 97%.
- **Long chats.** CLAUDE.md rules (224 tokens) and a UserPromptSubmit hook ask Claude to write a resume point and offer a fresh chat past 150k tokens. The hook fired live at 161k, 180k and 156k.
- **Applied now on this PC.** `~/.claude/settings.json` holds the two keys, the hook and the six deny rules. `~/.claude/CLAUDE.md` holds the rules. In the app, unused connectors, the Code Browser and prompt suggestions are off.
- **Cloud.** `config/cloud-setup.sh` is pasted into the cloud environment, and the repo's `.claude/settings.json` gives cloud chats the hook and the two keys. A new cloud chat confirmed the setup on 2026-10-19 (see the last timeline entry); only the hook firing live past 150k is still unseen.

## Timeline

### 2026-10-17 to 2026-10-18: Main chat 57c9c8f0 (research and the first setup)
- **Request (2026-10-17).** Design a language LLMs write in instead of prose, which they translate back to a human language on request.
- **Token benchmark** on one incident report, counted with o200k:
  - English prose: 121 tokens.
  - Terse English: 61 (0.50x). S-expression: 62 (0.51x). JSON: 72 (0.60x).
  - Invented glyphs: 49 (0.40x). Emoji: 57 (0.47x). Both are shorter only because they drop information.
  - gzip+base64: 342 (2.83x).
  - Hebrew prose: 167 (1.38x). It is 3.3x English on cl100k.
- **Prior art.** LLMLingua, gist tokens, ICAE, AutoCompressors and CacheGen all need model training or access to the model's internals, so an API user cannot use them.
- **13-agent panel.** Six angles, one refuter per angle, then a synthesis. 0 errors, 10 ideas survived and 14 were refuted. The chat paused for a usage reset, and the panel finished on 2026-10-18.
- **Keyline pilot.** A lint fix cut 3,774 distinct flags to 87 on 400 markdown files, and the lint still caught 8 of 9 invented abbreviations. The suite passed 30/30. Converting a progress file to Keyline went from 2,114 to 2,067 tokens (-2%), with 169/169 invariants kept.
- **Usage study** of the 3 largest transcripts:
  - Share of cost: cache reads 58%, cache writes 27%, output 15%.
  - Output characters: 84% tool calls, 12% visible text.
  - One session re-read a median 425,166 tokens per call, which is 693 tokens read for every token written.
- **autoCompactWindow 250000.** A new chat showed a 250,000-token window that compacts at 87%. A fresh chat then started near 96k tokens.
- **Connectors.** The `disableClaudeAiConnectors` setting had no effect and was removed. The user then switched off 13 claude.ai connectors account-wide: a new chat went from 96,690 to 81,423 tokens (-15,267, -15.8%). MCP server instructions went from 6,261 to 1,384.
- **skillListingBudgetFraction 0.005.** Skills went from 9,913 to 4,919 tokens after a PC restart. In the same restart, System tools rose from 34,627 to 40,693 for an unknown reason, so the total was 82,504.
- **Plugins.** The user disabled 16 claude.ai plugins. There was no measurable change: a new chat measured after that was 82,965.
- **What fills the context.** Tool results were only 30% of context characters in two long sessions. One skill load was 15%, and 55 reports from other sessions were also 15% (averaging 5,126 characters each). This led to the short-report rule (50 tokens).
- **Ballast.** The setup was named Ballast. The two keys and the rule moved to user level, and everything was pushed to the public repo (5cbb066). The last measure in this chat was a new chat of 83,080 tokens. The chat itself reached 202,866 tokens (81%).
- **Still in this chat:**
  - The long-chat rule (CLAUDE.md grew to 118 tokens).
  - The hand-off hook: past 150k it tells Claude to offer a fresh chat, then repeats every +25k. It takes about 1 s per run and was tested on copies of this transcript (7cb7513).
  - The cloud setup script, 144 tokens at first (c628696).
  - The rename to Ideal-Umbrella (49ef934). The `~/.claude/ballast/` folder kept its name.

### 2026-10-18: "Build the Keyline notes checker and hook" (side chat)
- **Built `keyline/`:** a fact checker, a lint, a token measure script, a PostToolUse hook, a settings example, a CLAUDE.md snippet and tests.
- **Checked in the main chat:** 22/22 tests passed, and every token count was within 2 of the panel's numbers.

### 2026-10-18: "Continue Ideal-Umbrella from the resume point" (fresh chat)
- **Cloud settings.** A cloud chat reads neither `~/.claude/` file, only the repo's committed `.claude/settings.json` (and only in single-repo sessions). This chat added that file with the two keys and the hook, which runs only when `CLAUDE_CODE_REMOTE` is true. It also added `config/add_to_repo.py` for other repos (8287185). All of this was tested by simulation only.
- **Plugins and browser.** pwp and codacy-skills were already gone. get_settings still reported the browser tools as on.
- **Hook seen live.** The hook fired live for the first time in this chat at 161k, then again at 180k (the +25k repeat).
- **Cloud check.** The user started a cloud chat, which said it had pushed. No branch or result file reached GitHub.

### 2026-10-18: "Measure new chat starting tokens" (side chat)
- **Result.** A new chat came to 82,845 tokens (-235 vs 83,080).
- **Browser.** The built-in browser tools still loaded, although the user had switched a browser toggle off.

### 2026-10-18 to 2026-10-19: "Finish Ideal-Umbrella item 3 and re-measure" (fresh chat)
- **Cloud check.** This chat checked GitHub several times. On 2026-10-19 it marked the cloud check FAIL: there were no create or push events after 19:30 local on 2026-10-18, and no PRs. The rules and the hook remain unverified in a real cloud chat.
- **Browser.** It found that get_settings still showed the browser tools on and that the app had not been restarted. It ran the three measurement side chats below.

### 2026-10-18: "Measure new-chat context after app restart" (side chat)
- **Result.** 82,764 tokens (-81), with every category unchanged. The 19 browser tools were still loaded in full.
- **Cause.** The app had not actually been restarted: its main process had been running since 17:19:16.

### 2026-10-19: "Measure new chat after real app restart" (side chat)
- **Result.** 82,504 tokens (-260). The system prompt went to 9,709 (-396) because the `<browsers>` section was gone.
- **Browser still loaded.** The switch the user had turned off was Claude in Chrome, not Settings -> Claude Code -> Browser.

### 2026-10-19: "Measure new chat with Code Browser off" (side chat)
- **Result.** 71,396 tokens (-11,108, -13.5%). MCP tools went from 25,847 to 15,023: the 19 browser tools, about 570 tokens each, had been loaded in full rather than deferred. The system prompt went down by 284. No restart was needed.
- **Trade-off.** Code chats have no built-in browser or dev-server preview.
- **Largest block left.** System tools at 39,579 tokens (55% of the start context).

### 2026-10-19: "Continue Ideal-Umbrella from the 2026-10-19 resume point" (fresh chat)
- **Two new rules (4c9f1b7).** Archive a side session once its result is checked, and replace the task's resume point at the end of every task.
- **Rules check in a fresh chat.** The archive, short-report and 150k-hook rules worked. The hook was simulated on a 214k transcript: one note, then silence.
- **Briefs.** Briefs now ask side sessions to update the resume point too (a4fa221). CLAUDE.md grew from 211 to 224 tokens.
- **Tool cuts, chosen by the user (66df7f7).** `permissions.deny` now blocks Artifact, ScheduleWakeup, ReportFindings, SearchPlugins, SuggestPluginInstall and SuggestSkills, none of which had been called in 60 past chats. Prompt suggestions were switched off. The user kept Workflow and Firecrawl scrape/search.

### 2026-10-19: "Rule test: count .md files" (side chat)
- **Result.** This Sonnet side session did its task but skipped its resume-point update, because its brief limited where it could write. That led to the brief-rule change above.

### 2026-10-19: "Measure a fresh chat after the tool cuts" (side chat)
- **Result.** The first call went from 65,483 to 49,423 tokens (-16,060, -25%), and the six built-in tools were gone.
- **Visualize.** A server-wide `mcp__visualize` deny rule did not remove the visualize tools.

### 2026-10-19: "Continue Ideal-Umbrella from the 13:25 resume point" (fresh chat)
- **Visualize check.** Exact-name deny rules for visualize were checked in a further fresh side session around 13:50, and visualize still loaded: the app adds it outside the deny filter. All three visualize rules were dropped with the user's OK (b2e22e6).
- **Settings edits.** The auto-mode classifier blocks edits to `~/.claude/settings.json` unless the user approves them in words.
- **Brief rule seen working.** At 13:55, the visualize-check side session updated the resume point as its brief asked.
- **Resume point.** It was updated at 14:05, ending in the open items below.

### 2026-10-19: Cloud check, redone (cloud chat)
- **Setup.** The user made a new cloud environment with env `CLAUDE_CODE_AUTO_COMPACT_WINDOW=250000` and the current `config/cloud-setup.sh` as its setup script.
- **Result: passed.** The cloud chat wrote `cloud-check.md`, pushed branch `claude/cloud-check` and opened PR #2. Its `~/.claude/CLAUDE.md` matched `config/cloud-setup.sh` line for line, `CLAUDE_CODE_REMOTE` was `true`, the compact window was 250000, Python was 3.13.16, and the repo's `.claude/settings.json` matched main.
- **PR #2** was closed without merging: `cloud-check.md` was only a test file.

## What worked
- **Code Browser off:** a new chat went from 82,504 to 71,396 tokens (-11,108, -13.5%). Why: its 19 tools were loaded in full in every chat, not deferred.
- **Deny six never-used tools:** the first call went from 65,483 to 49,423 tokens (-25%). Why: 0 calls in 60 past chats, and a denied tool leaves the tool list.
- **Unused connectors off (account-wide):** a new chat went from 96,690 to 81,423 tokens (-15.8%). Why: connector tools and server instructions load on every call.
- **skillListingBudgetFraction 0.005:** Skills went from 9,913 to 4,919 tokens (-50%). Why: the app honors this key and lists half as much.
- **autoCompactWindow 250000:** the window is 250,000 and compacts at 87% (near 217,500). Why: a smaller context per call is the main lever, since cache reads were 58% of cost.
- **Hand-off hook:** it fired live at 161k, 180k and 156k. Why: it reads the real size from the transcript instead of relying on Claude to notice. It costs about 1 s per message and 0 tokens below 150k.
- **CLAUDE.md rules (224 tokens):** they worked in the 2026-10-19 rules check. Why: they are loaded at launch in every new chat. Reports from other sessions had averaged 5,126 characters, but no after-size has been measured yet.
- **Brief asks for the resume-point update:** it was seen working once (13:55). Why: a side session follows its brief's limits over CLAUDE.md.

## What did not work
- **Invented machine language:** glyphs cost 49 tokens for 40 characters, and gzip+base64 costs 2.83x prose. Why: new symbols split into byte fragments, while terse English (0.50x) is lossless.
- **Keyline on an already terse file:** -2% (2,114 to 2,067 tokens). Why: agent-written logs have no padded prose to remove.
- **`disableClaudeAiConnectors`:** MCP tools stayed at 26,428 and instructions at 6,261. Why: the desktop app ignores this setting.
- **Disabling 16 plugins:** no measurable change (82,965 tokens). Why: the skills list is capped near 9,913 tokens anyway (full demand is 21,642).
- **Claude in Chrome switch:** -260 tokens, and the 19 browser tools still loaded. Why: it was the wrong switch. Only Settings -> Claude Code -> Browser removes them.
- **Visualize deny rules:** both visualize tools stayed loaded. Why: the desktop app adds visualize outside the deny filter.
- **LLMLingua-2 and gist tokens:** tool results are only 30% of context, and the README puts the gain at about 7%. Why: gist tokens need the model itself trained, and file reads must stay exact for Edit.
- **First cloud check:** no branch or push from that cloud chat reached GitHub, and the chat itself was later lost. Why: a problem in that one chat; a new cloud chat's push worked on 2026-10-19.

## Open items (from the 2026-10-19 resume point, updated after the cloud check)
1. Cloud check passed on 2026-10-19 (PR #2, closed unmerged). Still unseen: the hook firing live in a cloud chat, which needs a cloud chat past 150k tokens.
2. Done: the new cloud environment uses the current `config/cloud-setup.sh`.
3. Visualize check done (see the tool cuts). Remaining ideas:
   - computer-use server instructions: ~1.2k tokens per chat and 0 uses. The user can switch computer use off in the app's settings.
   - Duplicate skill listings: plain and `anthropic-skills:` copies.
   - The altimate-code plugin's start-up text.
4. Seen working once (2026-10-19 13:55): the visualize-check side session was briefed per the rule and updated the resume point.

## When a fresh chat pays off
On Opus 5.5 a 1-hour cache write costs 2x the base input price and a cache read 0.05x (Anthropic's prompt-caching docs, checked 2026-10-19). A fresh chat writes its ~49k start load once (about 99k base-input tokens), then re-reads ~50k per call; staying re-reads the whole chat per call.
- At 60k, staying costs 3k per call against 2.5k: a fresh chat pays off only after ~200 calls, so stay.
- At 150k: 7.5k against 2.5k, so it pays off after ~20 calls. That is why the rule and the hook fire at 150k.
- After a break of more than 1 hour the long chat's cache has expired and its whole context is written again at 2x, so start fresh from the resume point at once.
- A fresh chat for every message wastes tokens: each one pays the ~99k write.
These break-even counts ignore what the fresh chat re-reads (the resume point, files it needs), so the real break-even comes somewhat later.
