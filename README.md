# Ideal-Umbrella

Make me waste fewer tokens while we work.

Rules and small tools that cut how many tokens Claude Code re-reads on every call. Working name for the setup: **Ideal-Umbrella**.

## Why

In the three largest Claude Code transcripts for this project (2,226 API responses, read 2026-10-23), list-price cost at Opus 5.5 rates was **43% cache reads, 37% cache writes and 20% output**. The cache writes were 100% 1-hour writes (`$8/MTok`), not 5-minute writes (`$5/MTok`). Every call re-reads the whole context, so the lever is a smaller context per call, not shorter wording.

Earlier versions of this README said 58% cache reads / 27% cache writes / 15% output. That was wrong: `scripts/usage_breakdown.py` priced every cache write at the 5-minute rate. The script now splits the two TTLs and prices each separately; the command to reproduce the split is under [Measured numbers](#measured-numbers).

## Quick start

Needs Python 3.10 or later and nothing outside the standard library (CI runs 3.10, 3.12 and 3.13 on Ubuntu and 3.12 on Windows; the keyline tools also need `tiktoken`).

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
| Short reports from side sessions and subagents | `~/.claude/CLAUDE.md` (`config/CLAUDE.md` as a marked section; your own text in the file stays) | reports from other sessions averaged **5,126 characters (baseline; no after-size measured yet)** |
| Long chats: resume point in a file, then offer a fresh session past 150k tokens | same `~/.claude/CLAUDE.md` | the rules cost 224 tokens per session, and the two marker lines around them about 18 more (counted with tiktoken `cl100k_base`, not measured in a session); a fresh session starts near 71k instead of carrying up to ~217k |
| Restarts: the resume point is updated at the end of each task (replaced, not appended) | same `~/.claude/CLAUDE.md` | a restart loses at most the task in progress; start a fresh chat from the resume point rather than reopening a long chat, because the prompt cache lives 1 hour |
| Finished side sessions are archived once their result is checked | same `~/.claude/CLAUDE.md` | keeps the sidebar clean; archived chats can be reopened |
| Hand-off reminder that does not rely on Claude noticing | `UserPromptSubmit` hook `hooks/context_check.py` (installed to `~/.claude/ballast/`) | reads real context size from transcript; past 150k it tells Claude to offer a fresh session and shows you a notice; repeats only every +25k, resets after compaction; ~1 s per message, 0 tokens below 150k |

The install steps below reproduce the settings, `CLAUDE.md` and hook rows. The connectors, Browser and prompt-suggestion rows are app switches and must be set by hand; the table says which measured state each switch produced.

### Security model of the hook

`hooks/context_check.py` runs on every prompt you send, so it does as little as it can. It runs under `python -I` (no `PYTHON*` variables, no script folder on `sys.path`), uses the standard library only, starts no process and opens no network connection. It reads the hook event Claude Code sends on stdin and the last 4 MB of the transcript file that event names (`IDEAL_UMBRELLA_TAIL_BYTES`); the session id becomes a file name only after everything but letters, digits and `-` is dropped. It writes only a small state file per session under `~/.claude/ballast/state/` (removed after 30 days) and an error log, `~/.claude/ballast/context_check.log`, capped at about 1 MB (both follow `CLAUDE_CONFIG_DIR`). It never blocks a prompt: every error is caught and logged and the script exits 0, the installed command adds `|| exit 0` for a missing file or interpreter, and the hook entry has a 15 s timeout. The cloud copy written by `add_to_repo.py` exits at once unless `CLAUDE_CODE_REMOTE=true`.

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
- An existing Ideal-Umbrella hook is updated in place; sibling hooks in the same entry stay. The installer, the uninstaller and `add_to_repo.py` recognise the hook by its file name: any hook command that names `context_check.py` is treated as Ideal-Umbrella's.
- The hook command records the Python executable that ran the installer, so it does not depend on `python3` being on `PATH` (the Windows Store alias is often broken).
- In `~/.claude/CLAUDE.md` the installer owns only the lines between `<!-- Ideal-Umbrella rules: begin -->` and `<!-- Ideal-Umbrella rules: end -->`; your own text above or below them is never changed. A file without the markers gets the section added at the end (after a backup). A section you edited is backed up before it is replaced. Marker lines inside a code fence (``` or ~~~), and a copy of the rules inside one, are an example, not the section; an opening fence line that is never closed is ordinary text. If you later close a stray fence line below the section, the installer still finds the section, because it holds exactly the rules the install record names; since that is also what a fenced example of the section looks like after you delete the live one, no tool changes such a section: install leaves it (and stops, before any write, when the rules have changed), `--verify-only` warns, and uninstall leaves it and asks you to close the fence above it if it is the installed section. Marker lines that are broken (a begin without an end, two sections, an end before the begin) stop the install before anything is written. A file the earlier whole-file installer wrote is turned into the section, and an unmarked copy of the rules (left by that installer or copied by hand) is wrapped in the markers rather than added twice. When the rules change, a copy you made by hand is updated in place and the installer says so; uninstall then leaves the new rules there, and your file from before the first install is in the backup it names. A marked section you added by hand before the first install ("Manual install" step 2) stays yours the same way: the installer updates its rules when they change and names the backup of your file, and uninstall leaves the section whole. Line endings (LF or CRLF) and a BOM are kept. Backups are named `<file>.bak-YYYYMMDD-HHMMSS`; a run repeated after a failure reuses one of those that already holds the same bytes (one it cannot read is skipped), and never a `.bak-` file you named yourself; a backup name in the install record is used only when it has that form, so uninstall never deletes another file the record names. The install record is written before the other files and keeps the record it replaces until the last write is done, so an install or update stopped by a failed write (a full disk) is still undone completely by the uninstaller or by running the installer again: for a change that never landed, the earlier record, which still describes the files, is used. A record that cannot be read (a hand edit that broke it, or a file only root may open after a `sudo` run) stops install and uninstall before anything is written (`--verify-only` does not check the record); fix it rather than delete it, since it holds what uninstall puts back (a UTF-8 BOM added by an editor is fine; a file saved as UTF-16, as PowerShell 5's `>` and `Out-File` do, is refused as not UTF-8). A rerun with nothing left to change still writes the record once without the one it kept, and the backup of an edited section made just before a failed `CLAUDE.md` write is deleted by uninstall (`CLAUDE.md` still holds the same edits). A `settings.json` that cannot be opened (no read permission, a folder in its place), nested more than 100 levels deep, holding a lone surrogate such as `\ud800` (valid JSON that UTF-8 cannot encode), or a number such as `1e400` that Python would write back as `Infinity` (not JSON), stops the installers before anything is written, and so does a home folder whose path is not UTF-8 (possible on Linux), which the hook command in `settings.json` could not hold. Verification compares only the section.
- A differing `settings.json` is backed up before it is replaced.
- Existing scalar settings are kept unless you pass `--force`. A value an earlier install wrote and you have not changed is updated when the template changes (for example after a `git pull`), without `--force`. Verification compares against the current template and prints a warning for each kept value, but still passes. A missing value fails verification.
- Everything is read and checked before anything is written, and `settings.json` is written after the hook file and `CLAUDE.md` (the install record comes first, naming every change the run makes, as described above), so an install that fails while reading or checking (for example a `CLAUDE.md` that is not UTF-8, or any of the four files, or a folder above one of them such as `~/.claude`, `~/.claude/ballast` or a `CLAUDE_CONFIG_DIR`, being a symlink to a missing target) changes nothing; so does a read-only file the run would write (it is refused before the first write, not at its own). A backup keeps the file's dates but not a read-only bit, so uninstall can delete it later. Every file is written whole or not at all (to a temp file beside it, then renamed over it), so a write that fails part way (disk full, a folder in the way) leaves the old file as it was and no hook entry in `settings.json`; the error message lists the backups and files written before it.
- A symlinked `settings.json`, `CLAUDE.md` or hook file (dotfiles, stow) is written through; the link stays a link. A link to a read-only file (home-manager's Nix store) stops install and uninstall at that file with "read-only" and the path it points at: take the section out in the source, or replace the link with a file, then run again. A hard-linked file becomes a new file: the other links keep the old content. A file linked to one of the installer's own backups (put back with `ln -s`) gets a backup of its own, so the rules are never written into the only copy of your file.
- `CLAUDE_CONFIG_DIR`, when set, is where the files go (it is where Claude Code reads them), and no home folder is needed then; `--home` overrides it. It must be an absolute path: Claude Code takes the value as it is (it does not expand `~`, an empty value is not unset, and a relative one is read from each project folder), so any other value stops the run. If you installed with a `~` or a relative value before, set it to the absolute path it was taken for (the expanded `~`, or the relative path from the folder you installed from) to uninstall.
- Verification also checks that the Python the hook command names still exists (a deleted venv or a pyenv bump leaves a command that `|| exit 0` silences); run `install.py` again to point it at the current Python.
- `--home` may be relative or `~`; it is turned into an absolute path, because Claude Code runs the hook from the project folder. An empty `--home`, a `~` or `~name` whose home folder is not there (on Windows `~name` is the folder beside your own home), no home folder at all, or a `HOME` (`USERPROFILE` on Windows) that is empty or not an absolute path (also behind `--home ~`), or, with no `HOME`, an empty home in your passwd entry, stops the run with a one-line error before anything is written; a `HOME` that is a symlink to a missing folder stops it as `--home` does. Only a leading `~` is expanded: `./~name` is a folder named `~name` in the current folder.

### Manual install

1. Merge `config/user-settings.json` into `~/.claude/settings.json`. Replace `python3` in the hook command with the Python executable on your machine, or use the automated installer.
2. Add `config/CLAUDE.md` to `~/.claude/CLAUDE.md` between a line `<!-- Ideal-Umbrella rules: begin -->` and a line `<!-- Ideal-Umbrella rules: end -->` (create the file if there is none). The installer and the uninstaller recognise the section by those two lines.
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

`add_to_repo.py` preserves other keys and hooks, updates an existing Ideal-Umbrella hook in place, and changes nothing on a second run. A scalar value the repository already sets (its own `autoCompactWindow`, say) is kept and reported; pass `--force` to replace it.

To give one repository its own hand-off threshold, add `--handoff-at 120000` (tokens, a whole number above 0). It writes `"env": {"IDEAL_UMBRELLA_HANDOFF_AT": "120000"}` into `.claude/settings.json`; Claude Code passes `env` to the session and its hooks, and the hook reads that variable instead of the default 150,000. Other `env` keys stay. A different value already there is kept and reported unless you pass `--force`; running without `--handoff-at` leaves an existing value alone.

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

Run `python -I config/uninstall.py` (add `--dry-run` to preview). The installer records what it changed in `~/.claude/ballast/install-record.json`; the uninstaller uses that to put back values that were there before (including ones replaced with `--force`), remove only the `permissions.deny` tools it added, remove its hook entry (sibling hooks stay), delete the copied hook, and remove the Ideal-Umbrella section from `CLAUDE.md`. It compares against the values the install wrote, so a `git pull` that changes the templates in between does not get in the way. Values you changed after installing are left alone and reported, and a key you deleted by hand stays deleted, even after another install put it back (also one a `--force` install had replaced). In `CLAUDE.md` only the marked section goes; the blank line the installer put before it goes too when nothing follows the section (also when an editor or git changed the file's line endings since), and stays when you added text after it. Your own text stays byte for byte. A section you edited is left in place and reported. A file the install created and that holds nothing else is deleted; a symlinked one (dotfiles, stow) is emptied through the link instead, so the file the link points at does not keep the rules. After an upgrade from the whole-file installer, a file holding nothing but the section is replaced by the backup that installer made; if that backup has been deleted, `CLAUDE.md` is left in place and reported. The backup the installer made before adding the section, and the whole-file installer's backup, are deleted once the file is back to the same bytes; one that differs (you changed your own text since) is kept and named, also by the rerun of an uninstall that stopped part way, when `CLAUDE.md` is gone, and next to the note on a section you edited. A backup that `CLAUDE.md` is a link to (put back with `ln -s`) is the file itself: it is never deleted or named as a copy to delete, the section is taken out of it through the link, and one from before the first install that holds nothing but the section is left as is with a note; and a folder or link with a backup's name is not taken for a backup. A section you added by hand before the first install is left whole. A `settings.json`, `CLAUDE.md`, hook file or install record that is a symlink to a missing target, or sits in a folder that is (a dotfiles folder moved or not mounted), stops uninstall with a one-line error before anything is written, as it stops install: put the folder back and run it again, since a missing file would lose its undo for good. `settings.json` is backed up before it is rewritten. An uninstall stopped by a failed write or delete (a full disk) is finished by running it again, also for an install from before the record existed (`settings.json` is written after the `CLAUDE.md` step and the hook file is deleted last, so a rerun still finds the install); a backup of the installer's, the hook or the log that is read-only (set by an earlier version, by you or by a sync tool) is deleted, its read-only bit cleared first only where the delete is refused (Windows), so a log another user owns (left by `sudo claude`) is deleted on Linux and macOS without a change of mode; a delete that is still refused (often because the folder is not writable) is the error shown, not the failed change of mode. Afterwards the record stays as a marker, so running the uninstaller again changes nothing and says "Nothing to undo.", plus a note for anything it leaves as is (a value you changed, a section it did not write). A record field of the wrong type (hand-edited) stops the installer and the uninstaller with a one-line error before anything is written. Installs made before the record existed: the two keys are removed only if they still hold the template values and the Ideal-Umbrella hook is installed, `CLAUDE.md` is backed up before the section (or the whole file, from a whole-file install) is removed, the hook is removed, and `permissions.deny` is left for you; a `CLAUDE.md` with no section that is not the rules is left as is, with a note when an install is found.

By hand: delete the two keys (`autoCompactWindow`, `skillListingBudgetFraction`), remove the Ideal-Umbrella `hooks.UserPromptSubmit` entry, remove the six `permissions.deny` tools, remove the lines from `<!-- Ideal-Umbrella rules: begin -->` to `<!-- Ideal-Umbrella rules: end -->` in `~/.claude/CLAUDE.md`, and delete `~/.claude/ballast/context_check.py`, `~/.claude/ballast/install-record.json` and what the hook wrote while it ran: `~/.claude/ballast/state/` and `~/.claude/ballast/context_check.log`. Backups written by the installer are named `*.bak-YYYYMMDD-HHMMSS`.

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
- Fixed load of a new session is **71,396 tokens** (get_usage, Code Browser off, 2026-10-19; `research/measurements.jsonl` line 1), mostly the app's own tools (System tools ~39.6k, MCP tools ~15.0k). A Claude Code update can move it: measure again in a new session and record it with `python -I scripts/ledger.py --fixed-tokens N --cc-version V`, which appends a line and prints the change since the last one.

## Contents

- `config/` - settings snippet (`user-settings.json`, `repo-settings.json`), `CLAUDE.md` rule, cloud setup script (`cloud-setup.sh`), repo installer (`add_to_repo.py`), user installer and undo (`install.py`, `uninstall.py`), token calibration (`verify-tokens.py`)
- `.claude/settings.json` - this repo's cloud settings (the hook runs only in cloud sessions)
- `hooks/` - the long-chat hand-off reminder (stdlib Python)
- `keyline/` - Keyline note format: fact checker, lint, PostToolUse hook, tests (`python -I keyline/tests/run_tests.py`, needs `tiktoken`)
- `research/` - the full progress log, the 13-agent panel results, and the resume point for the PR clean-up (`pr-cleanup-progress.md`)
- `scripts/` - measurement scripts (token counts, transcript breakdowns). `lint_validate.py` and `plugin_cost.py` take their input folder as an argument (defaults: the folder holding this repo, and the Claude app folder for your OS or `CLAUDE_APP_DIR`). `unused_tools.py` counts tool calls in transcripts and flags denied tools that were used; it exits with an error when the folder is missing or holds no transcripts. `ledger.py` appends a measurement to `research/measurements.jsonl` (run by hand; nothing runs it for you).
- `CONTRIBUTING.md` and `.github/PULL_REQUEST_TEMPLATE.md` - the rules every change follows and the PR checklist
- `tests/` - pytest coverage for the hook, installers, cost model and calibration path

## Measured numbers

The cost split comes from the three largest transcripts of one project folder under `~/.claude/projects/` on 2026-10-23:

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

- **Fact checker** (`keyline_check.py`): verifies that dates, numbers, identifiers, proper nouns, hedges and negations survive a rendering (Hebrew, prose, etc.). A source with no extractable invariant and no hedge is `INCONCLUSIVE`, not `PASS`.
- **Style linter** (`keyline_lint.py`): flags markdown furniture and *invented* abbreviations; real tech terms are allowed via `keyline-allow.txt`.
- **Token measure** (`measure.py`): o200k_base/cl100k_base counts.
- **PostToolUse hook** (`keyline_hook.py`): runs lint + check on write/edit in `notes/` or `plans/` of the project (a file outside the project is ignored); `--print-config` generates a ready-to-paste hook entry.

Run tests: `python -I keyline/tests/run_tests.py` (needs `tiktoken`: `python -m pip install -r keyline/requirements.txt`). The suite has 36 checks on Windows and 35 elsewhere (one path check is Windows only); see `keyline/README.md` for details and honest limits.

## Tests

```bash
python -m pip install -r keyline/requirements.txt -r requirements-dev.txt
python -m pyflakes $(git ls-files '*.py')
python -m pytest -q
python -I keyline/tests/run_tests.py
python -m json.tool config/user-settings.json
python -m json.tool config/repo-settings.json
python -m json.tool .claude/settings.json
```

The pytest suite covers the cost model, the installers and uninstaller, the hand-off hook, the calibration fixture path, and the docs that repeat a source file (`tests/test_docs_match_source.py`: the cloud setup script against `config/CLAUDE.md`, the README settings table against `config/user-settings.json`, the "Contents" paths, and these commands against CI). GitHub Actions (`.github/workflows/ci.yml`) runs every command above for every pull request and push to `main`, on Ubuntu with Python 3.10, 3.12 and 3.13 and on Windows with 3.12. Run them before opening a pull request; `CONTRIBUTING.md` has the rest of the checklist.

## Research

`research/panel-results.md` - 13-agent panel (tokenizer, information, systems, linguist, skeptic, wildcard) stress-tested 24 ideas; 10 survived with measured token savings. `research/progress-log.md` - full progress log.
