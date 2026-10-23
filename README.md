# Ideal-Umbrella
Make me waste less token while we work.

Rules and small tools that cut how many tokens Claude Code re-reads on every call. Working name for the setup: **Ideal-Umbrella**.

## Why
In my own Claude Code transcripts (priced at Opus 5.5 list prices), cost was 58% cache reads, 27% cache writes and 15% output. Visible prose was about 12% of output characters. Every call re-reads the whole context, so the lever is a smaller context per call, not shorter wording.

## Quick Start (3 commands)
```bash
# 1. Clone and install user-level config (idempotent; safe to re-run)
git clone https://github.com/StepenkoAnatoli/Ideal-Umbrella.git
cd Ideal-Umbrella
python -I config/install.py

# 2. Open a NEW Claude Code session and verify
claude -p "Call get_usage and list every context category with its tokens."

# 3. (Optional) Add to a repository for cloud sessions
python -I config/add_to_repo.py /path/to/your/repo
cd /path/to/your/repo && git add .claude && git commit -m "chore: add Ideal-Umbrella cloud config"
```

## What is applied to every session

| Piece | Where | Measured effect |
|---|---|---|
| Compact at 250k instead of ~1M | `autoCompactWindow: 250000` in `~/.claude/settings.json` | window 1,000,000 at 97% → 250,000 at 87% |
| Half-size skills list | `skillListingBudgetFraction: 0.005` in `~/.claude/settings.json` | Skills 9,913 → 4,919 tokens |
| Unused claude.ai connectors off | Settings → Claude Code (app setting, account-wide) | new session 96,690 → 81,423 tokens (-15.8%) |
| Never-used tools dropped: Artifact, ScheduleWakeup, ReportFindings, SearchPlugins, SuggestPluginInstall, SuggestSkills (0 calls in 60 chats) | `permissions.deny` in `~/.claude/settings.json` (via `config/user-settings.json`) | fresh chat first call 65,483 → 49,423 tokens (-25%). **Visualize cannot be denied this way**: the desktop app adds it outside the deny filter (checked 2026-10-19). |
| Prompt suggestions off | Settings → Claude Code (app setting) | one fewer model request after every reply |
| Short reports from side sessions and subagents | `~/.claude/CLAUDE.md` (copy of `config/CLAUDE.md`) | reports from other sessions averaged 5,126 characters |
| Long chats: resume point in a file, then offer a fresh session past 150k tokens | same `~/.claude/CLAUDE.md` | whole file costs 224 tokens per session; a fresh session starts near 71k instead of carrying up to ~217k |
| Restarts: the resume point is updated at the end of each task (replaced, not appended) | same `~/.claude/CLAUDE.md` | a restart loses at most the task in progress; start a fresh chat from the resume point rather than reopening a long chat, because the prompt cache lives 1 hour |
| Finished side sessions are archived once their result is checked | same `~/.claude/CLAUDE.md` | keeps the sidebar clean; archived chats can be reopened |
| Hand-off reminder that does not rely on Claude noticing | `UserPromptSubmit` hook `hooks/context_check.py` (installed to `~/.claude/ballast/`) | reads real context size from transcript; past 150k it tells Claude to offer a fresh session and shows you a notice; repeats only every +25k, resets after compaction; ~1 s per message, 0 tokens below 150k |

## Install (Automated)
Run the install script — it merges settings, copies files, and verifies the result:
```bash
python -I config/install.py           # install or update
python -I config/install.py --verify-only  # verify only
```
The script is **idempotent**: running it again updates only what changed. It uses portable paths (`python3 -I ~/.claude/ballast/context_check.py`) so it works on any machine.

### Manual Install (if you prefer)
1. Merge `config/user-settings.json` into `~/.claude/settings.json`
2. Copy `config/CLAUDE.md` to `~/.claude/CLAUDE.md`
3. Copy `hooks/context_check.py` to `~/.claude/ballast/context_check.py`
4. **Disable connectors manually**: Settings → Claude Code → turn off "Claude.ai connectors" (the `disableClaudeAiConnectors` setting has no effect in the desktop app).
5. **Disable prompt suggestions**: Settings → Claude Code → turn off "Prompt suggestions".

## Cloud Sessions
Cloud sessions don't read `~/.claude/`; they only read the repository's committed `.claude/settings.json`.

### Single-Repository Cloud Sessions
1. Run `python -I config/add_to_repo.py <repo>` in the target repository.
2. Commit the two files it writes: `.claude/settings.json` and `.claude/hooks/context_check.py`.
3. The hook runs only when `CLAUDE_CODE_REMOTE=true` (cloud), so local sessions are unaffected.

### Multi-Repository Cloud Sessions (Limitation)
**The repo-level hook only activates in single-repo cloud sessions.** In multi-repo cloud sessions:
- The compact window (`autoCompactWindow: 250000`) from `.claude/settings.json` is **not applied**.
- The hand-off hook is **not run**.

**Workaround**: Set `CLAUDE_CODE_AUTO_COMPACT_WINDOW=250000` in the cloud environment's environment variables (claude.ai/code → environment selector → settings icon → Environment variables). This applies the compact window to all cloud sessions regardless of repository count.

### Cloud Setup Script
`config/cloud-setup.sh` writes `~/.claude/CLAUDE.md` inside the cloud session (since cloud sessions don't read your local one). Paste it into the cloud environment's setup script.

## Verify
Open a **new** Claude Code session and run:
```
Call get_usage and list every context category with its tokens.
```
Expected: context categories include `cache_read`, `cache_creation`, `input`, `output` with totals reflecting the 250k compact window and reduced skill listing.

## Undo
Delete the two keys (`autoCompactWindow`, `skillListingBudgetFraction`), the `hooks.UserPromptSubmit` entry, and `~/.claude/CLAUDE.md`.
Thresholds can be tuned via env vars: `IDEAL_UMBRELLA_HANDOFF_AT` (default 150000), `IDEAL_UMBRELLA_HANDOFF_STEP` (default 25000).
Folder-level `.claude/settings.local.json` files override user settings.

## What Did Not Work
- **Invented machine-only language**: Glyphs and emoji cost more tokens than English words; gzip+base64 costs 2.8× prose. Terse English is ~0.5× prose and lossless. Hebrew costs 1.4×–3.3× English for the same content.
- **Keyline note format on an already terse progress file**: -2%.
- **`disableClaudeAiConnectors` setting**: No effect in the Claude desktop app. Use the app UI: Settings → Claude Code → turn off "Claude.ai connectors".
- **Disabling unused plugins**: No measurable change so far (the skills list is capped anyway).
- **Gist tokens**: Need the model itself trained. LLMLingua-2 could plug in through a PostToolUse hook (`updatedToolOutput`), but tool results are only 30% of context and file reads must stay exact for Edit; estimated gain ~7%.
- **Visualize tool**: Cannot be denied via `permissions.deny` — the desktop app adds it outside the deny filter. No workaround currently; track upstream or file a feature request with Anthropic.

## Biggest Costs Still Left
- In two long sessions: one large skill load 15% of context characters, 55 reports from other sessions 15%, another skill load 6%, Bash output 15%.
- Fixed load of a new session is ~83k tokens, mostly the app's own tools (System tools ~39.6k, MCP tools ~25.9k).

## Contents
- `config/` — settings snippet (`user-settings.json`, `repo-settings.json`), CLAUDE.md rule (`CLAUDE.md`), cloud setup script (`cloud-setup.sh`), repo installer (`add_to_repo.py`), **user installer (`install.py`), token calibration (`verify-tokens.py`)**
- `.claude/settings.json` — this repo's cloud settings (hook runs only in cloud sessions)
- `hooks/` — long-chat hand-off reminder (stdlib Python)
- `keyline/` — Keyline note format: fact checker, lint, PostToolUse hook, tests (`python -I tests/run_tests.py`, needs `tiktoken`)
- `research/` — full progress log and 13-agent panel results
- `scripts/` — measurement scripts (token counts, transcript breakdowns); paths inside point at my machine
- `.github/workflows/ci.yml` — CI: keyline tests, hook simulations, install script test, config validation

Token counts use tiktoken `o200k_base` / `cl100k_base` as a proxy; **Claude's tokenizer is not public**. See `config/verify-tokens.py` to calibrate against Anthropic's `count_tokens` endpoint.

## Calibrating Token Counts (verify-tokens.py)
```bash
# Requires Anthropic API key
export ANTHROPIC_API_KEY=sk-ant-...
python -I config/verify-tokens.py              # uses keyline test fixtures
python -I config/verify-tokens.py --model claude-3-5-sonnet-20241022 my-notes.txt
```
This calls Anthropic's `count_tokens` endpoint and prints the ratio between tiktoken proxies and actual Claude tokens, so you can convert proxy counts to real estimates.

## Keyline (Machine Notes)
`keyline/` provides a terse `key: item; item` note format with:
- **Fact checker** (`keyline_check.py`): verifies no date, number, identifier, negation lost in a rendering (Hebrew, prose, etc.)
- **Style linter** (`keyline_lint.py`): flags markdown furniture and *invented* abbreviations; real tech terms allowed via `keyline-allow.txt`
- **Token measure** (`measure.py`): o200k_base/cl100k_base counts
- **PostToolUse hook** (`keyline_hook.py`): runs lint + check on write/edit in `notes/` or `plans/`

Run tests: `python -I keyline/tests/run_tests.py` (needs `tiktoken`; venv in `keyline/.venv/`).

## Research
`research/panel-results.md` — 13-agent panel (tokenizer, information, systems, linguist, skeptic, wildcard) stress-tested 24 ideas; 10 survived with measured token savings. `research/progress-log.md` — full progress log.