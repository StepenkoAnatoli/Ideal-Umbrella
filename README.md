# Ideal-Umbrella
Make me waste less token while we work.

Rules and small tools that cut how many tokens Claude Code re-reads on every call. Working name for the setup: **Ideal-Umbrella**.

## Why
In my own Claude Code transcripts (priced at Opus 5.5 list prices), cost was 58% cache reads, 27% cache writes and 15% output. Visible prose was about 12% of output characters. Every call re-reads the whole context, so the lever is a smaller context per call, not shorter wording.

## What is applied to every session
| Piece | Where | Measured effect |
|---|---|---|
| Compact at 250k instead of ~1M | `autoCompactWindow: 250000` in `~/.claude/settings.json` | window 1,000,000 at 97% -> 250,000 at 87% |
| Half-size skills list | `skillListingBudgetFraction: 0.005` in `~/.claude/settings.json` | Skills 9,913 -> 4,919 tokens |
| Unused claude.ai connectors off | the app's connector switch (account-wide) | new session 96,690 -> 81,423 tokens (-15.8%) |
| Short reports from side sessions and subagents | `~/.claude/CLAUDE.md` (copy of `config/CLAUDE.md`) | reports from other sessions averaged 5,126 characters |
| Long chats: resume point in a file, then offer a fresh session past 150k tokens | same `~/.claude/CLAUDE.md` | whole file costs 118 tokens per session; a fresh session starts near 83k instead of carrying up to ~217k |
| Hand-off reminder that does not rely on Claude noticing | `UserPromptSubmit` hook `hooks/context_check.py` (copy to `~/.claude/ballast/`, the folder's first name) | reads the real context size from the transcript; past 150k it tells Claude to offer a fresh session and shows you a notice; repeats only every +25k, resets after compaction; about 1 s per message, 0 tokens below 150k |

Install: merge `config/user-settings.json` into `~/.claude/settings.json`, copy `config/CLAUDE.md` to `~/.claude/CLAUDE.md` and `hooks/context_check.py` to `~/.claude/ballast/` (fix the Python path in the hook command).
Cloud sessions don't read `~/.claude/`: paste `config/cloud-setup.sh` into the cloud environment's setup script (claude.ai/code, environment selector under the message box, settings icon on the environment's row). It writes the same rules plus one line about pushing the progress file; 144 tokens.
The hook and the two keys reach a cloud session only through the repo's committed `.claude/settings.json`, and only in sessions with one repository. This repo has its own. For another repo, run `python -I config/add_to_repo.py <repo>` and commit the two files it writes. It merges `config/repo-settings.json` into the file, keeps other keys and hooks, and changes nothing on a second run. The hook exits at once unless `CLAUDE_CODE_REMOTE` is `true`, so local sessions still run only the user-level hook. For the compact window in every cloud session, including those with several repositories, you can instead set env `CLAUDE_CODE_AUTO_COMPACT_WINDOW=250000` on the cloud environment.
Check: open a new session and send `Call get_usage and list every context category with its tokens.`
Undo: delete the two keys, the `hooks` entry and `~/.claude/CLAUDE.md`. Thresholds: env `IDEAL_UMBRELLA_HANDOFF_AT`, `IDEAL_UMBRELLA_HANDOFF_STEP`. Folder-level `.claude/settings.local.json` files override user settings.

## What did not work
- An invented machine-only language. Glyphs and emoji cost more tokens than English words; gzip+base64 costs 2.8x prose. Terse English is about 0.5x prose and lossless. Hebrew costs 1.4x to 3.3x English for the same content.
- Keyline note format on an already terse progress file: -2%.
- The `disableClaudeAiConnectors` setting: no effect in the Claude desktop app.
- Disabling unused plugins: no measurable change so far (the skills list is capped anyway).
- Gist tokens need the model itself trained. LLMLingua-2 could plug in through a PostToolUse hook (`updatedToolOutput`), but tool results are only 30% of context and file reads must stay exact for Edit; estimated gain about 7%.

## Biggest costs still left
- In two long sessions: one large skill load was 15% of context characters, 55 reports from other sessions 15%, another skill load 6%, Bash output 15%.
- Fixed load of a new session is about 83k tokens, mostly the app's own tools (System tools ~39.6k, MCP tools ~25.9k).

## Contents
- `config/` - the settings snippet, the CLAUDE.md rule, the cloud setup script, and `add_to_repo.py` for repo-level cloud settings
- `.claude/settings.json` - this repo's cloud settings (the hook runs only in cloud sessions)
- `hooks/` - the long-chat hand-off reminder (stdlib Python)
- `keyline/` - Keyline note format: fact checker, lint, PostToolUse hook, tests (`python -I tests/run_tests.py`, needs `tiktoken`)
- `research/` - the full progress log and the 13-agent panel results
- `scripts/` - measurement scripts (token counts, transcript breakdowns); paths inside point at my machine

Token counts use tiktoken `o200k_base` / `cl100k_base` as a proxy; Claude's tokenizer is not public.
