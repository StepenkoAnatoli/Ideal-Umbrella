# Ideal-Umbrella

Make me waste fewer tokens while we work.

Rules and small tools that cut how many tokens Claude Code re-reads on every call. Working name for the setup: **Ideal-Umbrella**.

## Why

In the three largest Claude Code transcripts for this project (2,226 API responses, read 2026-10-23), list-price cost at Opus 5.5 rates was **43% cache reads, 37% cache writes and 20% output**. The cache writes were 100% 1-hour writes (`$8/MTok`), not 5-minute writes (`$5/MTok`). Every call re-reads the whole context, so the lever is a smaller context per call, not shorter wording.

Earlier versions of this README said 58% cache reads / 27% cache writes / 15% output. That was wrong: `scripts/usage_breakdown.py` priced every cache write at the 5-minute rate. The script now splits the two TTLs and prices each separately; the command to reproduce the split is under [Measured numbers](#measured-numbers).

## Quick start

```bash
# 1. Clone and install user-level config. The installer is idempotent and backs up files it replaces.
git clone https://github.com/StepenkoAnatoli/Ideal-Umbrella.git
cd Ideal-Umbrella
python -I config/install.py

# 2. Open a NEW Claude Code session and verify.
claude -p "Call get_usage and list every context category with its tokens."

# 3. Optional: give a repository's cloud sessions the hook and the two keys.
python -I config/add_to_repo.py /path/to/your/repo
cd /path/to/your/repo && git add .claude && git commit -m "chore: add Ideal-Umbrella cloud config"
```

Then turn off the three app switches by hand: **Settings -> Claude Code -> Browser**, **Claude.ai connectors**, and **Prompt suggestions**. These are account/app settings, not JSON keys; the installer cannot change them. The Browser switch is the largest measured win in the table below.

## What is applied to every session

| Piece | Where | Measured effect |
|---|---|---|
| Compact at 250k instead of ~1M | `autoCompactWindow: 250000` in `~/.claude/settings.json` | window 1,000,000 at 97% -> 250,000 at 87% |
| Half-size skills list | `skillListingBudgetFraction: 0.005` in `~/.claude/settings.json` | Skills 9,913 -> 4,919 tokens |
| Unused claude.ai connectors off | Settings -> Claude Code (app setting, account-wide) | new session 96,690 -> 81,423 tokens (-15.8%) |
| Code Browser off | Settings -> Claude Code -> Browser (app setting) | new session 82,504 -> 71,396 tokens (-11,108, -13.5%); no built-in browser or dev-server preview |
| Never-used tools dropped: Artifact, ScheduleWakeup, ReportFindings, SearchPlugins, SuggestPluginInstall, SuggestSkills (0 calls in 60 chats) | `permissions.deny` in `~/.claude/settings.json` (via `config/user-settings.json`) | fresh chat first call 65,483 -> 49,423 tokens (-25%). **Visualize cannot be denied this way**: the desktop app adds it outside the deny filter (checked 2026-10-19). |
| Prompt suggestions off | Settings -> Claude Code (app setting) | one fewer model request after every reply |
| Short reports from side sessions and subagents | `~/.claude/CLAUDE.md` (copy of `config/CLAUDE.md`) | reports from other sessions averaged **5,126 characters (baseline; no after-size measured yet)** |
| Long chats: resume point in a file, then offer a fresh session past 150k tokens | same `~/.claude/CLAUDE.md` | whole file costs 224 tokens per session; a fresh session starts near 71k instead of carrying up to ~217k |
| Restarts: the resume point is updated at the end of each task (replaced, not appended) | same `~/.claude/CLAUDE.md` | a restart loses at most the task in progress; start a fresh chat from the resume point rather than reopening a long chat, because the prompt cache lives 1 hour |
| Finished side sessions are archived once their result is checked | same `~/.claude/CLAUDE.md` | keeps the sidebar clean; archived chats can be reopened |
| Hand-off reminder that does not rely on Claude noticing | `UserPromptSubmit` hook `hooks/context_check.py` (installed to `~/.claude/ballast/`) | reads real context size from transcript; past 150k it tells Claude to offer a fresh session and shows you a notice; repeats only every +25k, resets after compaction; ~1 s per message, 0 tokens below 150k |

The install steps below reproduce the settings, `CLAUDE.md` and hook rows. The connectors, Browser and prompt-suggestion rows are app switches and must be set by hand; the table says which measured state each switch produced.

## Install (automated)

```bash
python -I config/install.py              # install or update
python -I config/install.py --verify-only  # check only
python -I config/install.py --force        # also replace values you set yourself
python -I config/uninstall.py --dry-run    # preview the undo
python -I config/uninstall.py              # undo
```

The installer is **idempotent** and merges instead of replacing:

- Existing keys, `permissions.allow`, `permissions.ask`, custom `deny` rules and unrelated hooks are kept.
- An existing Ideal-Umbrella hook is updated in place; sibling hooks in the same entry stay.
- The hook command records the Python executable that ran the installer, so it does not depend on `python3` being on `PATH` (the Windows Store alias is often broken).
- A differing `~/.claude/CLAUDE.md` and `settings.json` are backed up before they are replaced.
- Existing scalar settings are kept unless you pass `--force`; verification then prints a warning for each kept value and still passes. A missing value fails verification.
- Everything is read and checked before anything is written, and `settings.json` is written last, so a failed install (for example a `CLAUDE.md` that is not UTF-8) changes nothing.
- A symlinked `settings.json` or `CLAUDE.md` (dotfiles, stow, home-manager) is written through; the link stays a link.
- `--home` may be relative or `~`; it is turned into an absolute path, because Claude Code runs the hook from the project folder.

### Manual install

1. Merge `config/user-settings.json` into `~/.claude/settings.json`. Replace `python3` in the hook command with the Python executable on your machine, or use the automated installer.
2. Copy `config/CLAUDE.md` to `~/.claude/CLAUDE.md` (back up an existing file first).
3. Copy `hooks/context_check.py` to `~/.claude/ballast/context_check.py`.
4. Settings -> Claude Code -> turn off **Browser**.
5. Settings -> Claude Code -> turn off **Claude.ai connectors**. The `disableClaudeAiConnectors` setting has no effect in the desktop app.
6. Settings -> Claude Code -> turn off **Prompt suggestions**.

## Cloud sessions

Cloud sessions don't read `~/.claude/`; they only read the repository's committed `.claude/settings.json`, and the repo-level hook only runs in single-repository cloud sessions.

### Single-repository cloud sessions

1. Run `python -I config/add_to_repo.py <repo>`.
2. Commit the two files it writes: `.claude/settings.json` and `.claude/hooks/context_check.py`.
3. The hook runs only when `CLAUDE_CODE_REMOTE=true` (cloud), so local sessions are unaffected.

`add_to_repo.py` preserves other keys and hooks, updates an existing Ideal-Umbrella hook in place, and changes nothing on a second run.

### Multi-repository cloud sessions (limitation)

In multi-repo cloud sessions the repo-level compact window and hook are not applied. Workaround: set `CLAUDE_CODE_AUTO_COMPACT_WINDOW=250000` in the cloud environment's environment variables (claude.ai/code -> environment selector -> settings icon -> Environment variables). That applies the compact window to all cloud sessions regardless of repository count.

### Cloud setup script

`config/cloud-setup.sh` writes `~/.claude/CLAUDE.md` inside the cloud session (cloud sessions don't read your local one). It holds the rules from `config/CLAUDE.md` plus one cloud-only line: commit and push the progress file before offering a fresh session, because the cloud machine is discarded. Paste it into the cloud environment's setup script.

## Verify

Open a **new** Claude Code session and run:

```text
Call get_usage and list every context category with its tokens.
```

Expected: context categories include `cache_read`, `cache_creation`, `input`, `output` with totals reflecting the 250k compact window and reduced skill listing.

## Undo

Run `python -I config/uninstall.py` (add `--dry-run` to preview). The installer records what it changed in `~/.claude/ballast/install-record.json`; the uninstaller uses that to put back values that were there before (including ones replaced with `--force`), remove only the `permissions.deny` tools it added, remove its hook entry (sibling hooks stay), delete the copied hook, and restore the `CLAUDE.md` backup. It compares against the values the install wrote, so a `git pull` that changes the templates in between does not get in the way. Values you changed after installing are left alone and reported. If you edited `CLAUDE.md` after installing and then reinstalled, the backup holding those edits is the one restored. `settings.json` is backed up first. Afterwards the record stays as a marker, so running the uninstaller again changes nothing. Installs made before the record existed: the two keys are removed only if they still hold the template values and the Ideal-Umbrella hook is installed, `CLAUDE.md` is backed up before it is deleted, the hook is removed, and `permissions.deny` is left for you.

By hand: delete the two keys (`autoCompactWindow`, `skillListingBudgetFraction`), remove the Ideal-Umbrella `hooks.UserPromptSubmit` entry, remove the six `permissions.deny` tools, and delete `~/.claude/CLAUDE.md`, `~/.claude/ballast/context_check.py` and `~/.claude/ballast/install-record.json`. Backups written by the installer are named `*.bak-YYYYMMDD-HHMMSS`.

Thresholds can be tuned with `IDEAL_UMBRELLA_HANDOFF_AT` (default 150000) and `IDEAL_UMBRELLA_HANDOFF_STEP` (default 25000); `IDEAL_UMBRELLA_TAIL_BYTES` (default 4 MB) sets how much of the transcript end the hook reads. Folder-level `.claude/settings.local.json` files override user settings.

## What did not work

- **Invented machine-only language**: Glyphs and emoji cost more tokens than English words; gzip+base64 costs 2.8x prose. Terse English is ~0.5x prose and lossless. Hebrew costs 1.4x-3.3x English for the same content.
- **Keyline note format on an already terse progress file**: -2%.
- **`disableClaudeAiConnectors` setting**: No effect in the Claude desktop app. Use the app UI: Settings -> Claude Code -> turn off "Claude.ai connectors".
- **Disabling unused plugins**: No measurable change so far (the skills list is capped anyway).
- **Gist tokens**: Need the model itself trained. LLMLingua-2 could plug in through a PostToolUse hook (`updatedToolOutput`), but tool results are only 30% of context and file reads must stay exact for Edit; estimated gain ~7%.
- **Visualize tool**: Cannot be denied via `permissions.deny`; the desktop app adds it outside the deny filter. No workaround currently; track upstream or file a feature request with Anthropic.

## Biggest costs still left

- In two long sessions: one large skill load 15% of context characters, 55 reports from other sessions 15%, another skill load 6%, Bash output 15%.
- Fixed load of a new session is **71,396 tokens** (get_usage, Code Browser off), mostly the app's own tools (System tools ~39.6k, MCP tools ~15.0k).

## Contents

- `config/` - settings snippet (`user-settings.json`, `repo-settings.json`), `CLAUDE.md` rule, cloud setup script (`cloud-setup.sh`), repo installer (`add_to_repo.py`), user installer and undo (`install.py`, `uninstall.py`), token calibration (`verify-tokens.py`)
- `.claude/settings.json` - this repo's cloud settings (the hook runs only in cloud sessions)
- `hooks/` - the long-chat hand-off reminder (stdlib Python)
- `keyline/` - Keyline note format: fact checker, lint, PostToolUse hook, tests (`python -I keyline/tests/run_tests.py`, needs `tiktoken`)
- `research/` - the full progress log, the 13-agent panel results, and the resume point for the PR clean-up (`pr-cleanup-progress.md`)
- `scripts/` - measurement scripts (token counts, transcript breakdowns); paths inside point at my machine. `unused_tools.py` counts tool calls in transcripts and flags denied tools that were used; it exits with an error when the folder is missing or holds no transcripts.
- `tests/` - pytest coverage for the hook, installers, cost model and calibration path

## Measured numbers

The cost split comes from the three largest transcripts in `~/.claude/projects/C--Users-PC-Desktop-gittoken` on 2026-10-23:

```bash
python -I scripts/usage_breakdown.py ~/.claude/projects/<project-folder> 3
```

It reports 2,226 API responses, `cache_creation_5m_input_tokens: 0`, `cache_creation_1h_input_tokens: 8,674,673`, and the 43/37/20 split. The old script printed 50/27/23 because it priced all 8.67M 1-hour writes at $5/MTok instead of $8/MTok.

Token counts use tiktoken `o200k_base` / `cl100k_base` as a proxy; **Claude's tokenizer is not public**, so treat token and percentage counts as directional. See `config/verify-tokens.py` to calibrate against Anthropic's `count_tokens` endpoint.

## Calibrating token counts

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python -I config/verify-tokens.py --model <current-model-id>
```

`--model` (or `ANTHROPIC_MODEL`) is required because `count_tokens` is model-specific and model ids change. With no files, the script uses the keyline test fixtures. It prints the ratio between each tiktoken proxy and Claude's count so you can convert proxy counts to estimates.

## Keyline (machine notes)

`keyline/` provides a terse `key: item; item` note format with:

- **Fact checker** (`keyline_check.py`): verifies that dates, numbers, identifiers, proper nouns, hedges and negations survive a rendering (Hebrew, prose, etc.). A source with no extractable invariants is `INCONCLUSIVE`, not `PASS`.
- **Style linter** (`keyline_lint.py`): flags markdown furniture and *invented* abbreviations; real tech terms are allowed via `keyline-allow.txt`.
- **Token measure** (`measure.py`): o200k_base/cl100k_base counts.
- **PostToolUse hook** (`keyline_hook.py`): runs lint + check on write/edit in `notes/` or `plans/`; `--print-config` generates a ready-to-paste hook entry.

Run tests: `python -I keyline/tests/run_tests.py` (needs `tiktoken`; venv in `keyline/.venv/`). The suite has 35 checks on Windows and 34 elsewhere (one path check is Windows only); see `keyline/README.md` for details and honest limits.

## Tests

```bash
python -m pytest -q
python -I keyline/tests/run_tests.py
```

The pytest suite covers the cost model, the installers and uninstaller, the hand-off hook, and the calibration fixture path. GitHub Actions (`.github/workflows/ci.yml`) runs both on Ubuntu and Windows for every pull request and push to `main`. Run both commands above before opening a pull request.

## Research

`research/panel-results.md` - 13-agent panel (tokenizer, information, systems, linguist, skeptic, wildcard) stress-tested 24 ideas; 10 survived with measured token savings. `research/progress-log.md` - full progress log.
