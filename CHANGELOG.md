# Changelog

Notable changes to Ideal-Umbrella. `HISTORY.md` is the narrative history and `research/progress-log.md` the full work log; this file is the short summary.

## [Unreleased]
### Added
- `config/uninstall.py` (with `--dry-run`): undoes `config/install.py` from the install record, restoring earlier values and the CLAUDE.md backup.
- `config/install.py` writes `~/.claude/ballast/install-record.json` with what it added or replaced.
- `IDEAL_UMBRELLA_TAIL_BYTES` for how much of the transcript end `hooks/context_check.py` reads.
- `scripts/unused_tools.py`: tool-call counts from transcripts, flags denied tools that were used.
- GitHub Actions: pytest, the keyline suite and a JSON check on Ubuntu and Windows.

### Fixed
- `keyline/keyline_lint.py` with the word cache present and tiktoken missing reports an abbreviation as "not one token" instead of stopping with the install hint (a regression of the hint fix: the exit escaped `token_count()`). A `keyline-allow.txt` or word cache that is not UTF-8 is a one-line read error, not a traceback; so is a cache path that cannot be read.
- `keyline/keyline_check.py` treats a capitalised `May` inside a sentence ("in May because") as the month, not a possibility hedge.
- `config/install.py` reports a file-system error or a bad `settings.json` met during verification (after an install or with `--verify-only`) as one line; `config/add_to_repo.py` does the same for a `.claude` that is a file or a read-only folder. A `settings.json` that is not UTF-8 is reported as such, not as "not valid JSON".
- `scripts/usertext_split.py`, `scripts/usertext_top.py`, `scripts/toolresult_share.py` and `config/verify-tokens.py` no longer crash on a file that is not UTF-8.
- `tests/test_source_rules.py` keeps two rules on every script: `sys.exit` only in `main()`, and every text read either passes `errors=` or handles `UnicodeDecodeError`.
- `keyline/keyline_check.py` extracts an ISO 8601 timestamp (`2026-10-25T10:00:00Z`) as one invariant; it used to split into two numbers and a time, so a rendering that changed the day or hour passed. A possessive (`Claude's`) no longer makes the `'s` part of the name, and `May 2026` is the month, not a hedge. A note that is not UTF-8 is a read error (exit 2, one line) in `keyline_check.py`, `keyline_lint.py` and the hook, not a traceback.
- `keyline/keyline_lint.py` says how to install tiktoken when the word cache has to be built and tiktoken is missing; the hook used to show a traceback on every write of a watched note.
- `config/install.py` and `config/uninstall.py` refuse to run on an `install-record.json` that exists but is not valid JSON, instead of treating it as absent and overwriting it; a `settings.json` or `CLAUDE.md` that is a symlink to a missing target is reported before anything is written; output is UTF-8 so a non-ASCII home path cannot crash the listing on Windows.
- `config/uninstall.py` reports a file-system error during the undo as one line (a second run finishes the undo), tolerates a record whose backup name is not a string, and says why a template-matching `CLAUDE.md` the install never wrote is left in place.
- `hooks/context_check.py` fires again after a compaction that still lands above the threshold (the earlier band kept it silent until the next band), and its comment on `compact_boundary` now matches what Claude Code records (`postTokens`).
- Docs: `keyline/README.md` and `README.md` no longer describe one machine's venv, project folder and settings paths; the CI comment on `PYTHONUTF8` says what it covers (the `-I` children set UTF-8 output themselves).
- `scripts/toolresult_share.py`, `scripts/usertext_split.py` and `scripts/usertext_top.py` no longer crash on a transcript line that is a JSON list or string, print usage when run without arguments, and report an empty transcript instead of dividing by zero.
- `scripts/unused_tools.py` no longer counts a `tool_use` block without a name as a tool called `None`.
- `config/install.py` writes the install record after `settings.json`, so a failed settings write no longer leaves a record of values that were not installed.
- `keyline/measure.py` says how to install tiktoken when it is missing instead of raising ImportError.
- Docs: the keyline suite count (35 checks, 36 on Windows), one-machine paths in the keyline hook and test docstrings, and the CHANGELOG pointer to the history files.
- `scripts/lint_validate.py` and `scripts/plugin_cost.py` no longer hardcode one machine's paths: the keyline module and tiktoken cache come from this repository, and the corpus folder and Claude app folder are arguments (with per-OS defaults and `CLAUDE_APP_DIR`). Both print usage and fail cleanly on a missing folder.
- `scripts/tokentest.py` no longer redefines `claude` (the pyflakes warning is gone).
- The user-level hook command `config/install.py` writes now ends in `|| exit 0`. A `settings.json` synced to a machine without `~/.claude/ballast/context_check.py` (or without that Python) used to exit 2 there, which blocks every prompt.
- `config/add_to_repo.py` keeps a scalar value the repository already sets and reports it, instead of replacing it silently; `--force` replaces it. `merge()` now returns `(changes, notices)`.
- `scripts/usage_breakdown.py` no longer crashes on a transcript line that is a JSON list or string.
- `keyline/keyline_check.py` reports an empty source as `INCONCLUSIVE`; it used to `PASS` with 0 invariants.
- `config/install.py` verification fails when `permissions.deny` is not a list (a string used to pass by substring match), passes when the home path contains a quote, and reports a file-system error (for example `~/.claude/ballast` existing as a file) as one line instead of a traceback. The unused `verify_only` argument of `install()` is gone.
- `hooks/context_check.py` reads its stdin as UTF-8 regardless of the locale (a non-ASCII transcript path on a cp1252 Windows host was never matched), removes per-session state files older than 30 days, and trims its log past 1 MB.
- `config/verify-tokens.py` says how to install tiktoken when it is missing instead of raising ImportError.
- `config/uninstall.py` no longer deletes `CLAUDE.md` when the backup it should restore from is missing; it leaves the file, reports the missing backup, and keeps the record so a later run can still restore it.
- `config/install.py` verification no longer fails when you keep your own `autoCompactWindow` or `skillListingBudgetFraction` (left as is without `--force`); it prints a warning. A missing value still fails.
- `config/install.py` reads and checks everything before writing and writes `settings.json` last. A failed install (for example a non-UTF-8 `CLAUDE.md`) used to leave a hook entry pointing at a missing file, which blocked every prompt.
- `config/uninstall.py` run a second time no longer deletes your own values that match the template, or an identical `CLAUDE.md`: the record stays as an "uninstalled" marker. Without a record, keys are removed only when the Ideal-Umbrella hook is installed, and `CLAUDE.md` is backed up before it is deleted.
- `config/uninstall.py` compares against the values the install wrote (now kept in the record, with a hash of `CLAUDE.md`), not the current templates, so a `git pull` between install and uninstall no longer strands installed values or the `CLAUDE.md` backup. Anything left as is stays in the record.
- `config/install.py` and `config/uninstall.py` resolve `--home`, so `--home .` or a literal `~` no longer writes a relative hook path.
- `config/install.py`, `config/uninstall.py` and `config/add_to_repo.py` write through a symlinked `settings.json` or `CLAUDE.md` instead of replacing the link.
- A malformed hook entry (a hook that is not an object) no longer crashes install, uninstall or verify.
- Uninstall and verify no longer fail on a `CLAUDE.md` that is not UTF-8; uninstall leaves it as is.
- Reinstalling after editing `CLAUDE.md` or a setting by hand: uninstall now restores those edits, not the state before the first install.
- Re-running `config/install.py` after a `git pull` that changes a template value now updates a setting that still holds the value an earlier install wrote; it used to keep the old value unless you passed `--force`. Values you set yourself are still kept. Verification checks against the current template instead of hardcoded values.
- `scripts/unused_tools.py` exits with an error when the folder is missing or holds no transcripts, instead of reporting that no denied tool was used.
- Keyline test "absolute pattern matches backslash, other-case path" runs only on Windows; it failed on Linux and macOS, where backslashes and case are significant in paths.

## 2026-10-25 - audit fixes (#4)
- Cache-aware cost model, safe idempotent `config/install.py`, fail-closed keyline checks, `config/verify-tokens.py`, pytest suite.

## 2026-10-19 - first release
- Settings, CLAUDE.md rules, `hooks/context_check.py`, `keyline/` tools, cloud setup, `config/add_to_repo.py`, measurement scripts, research log.
