# Changelog

Notable changes to Ideal-Umbrella. HISTORY.md holds the narrative research log; this file is the short summary.

## [Unreleased]
### Added
- `config/uninstall.py` (with `--dry-run`): undoes `config/install.py` from the install record, restoring earlier values and the CLAUDE.md backup.
- `config/install.py` writes `~/.claude/ballast/install-record.json` with what it added or replaced.
- `IDEAL_UMBRELLA_TAIL_BYTES` for how much of the transcript end `hooks/context_check.py` reads.
- `scripts/unused_tools.py`: tool-call counts from transcripts, flags denied tools that were used.
- GitHub Actions: pytest, the keyline suite and a JSON check on Ubuntu and Windows.

### Fixed
- `config/install.py` verification no longer fails when you keep your own `autoCompactWindow` or `skillListingBudgetFraction` (left as is without `--force`); it prints a warning. A missing value still fails.
- `config/install.py` reads and checks everything before writing and writes `settings.json` last. A failed install (for example a non-UTF-8 `CLAUDE.md`) used to leave a hook entry pointing at a missing file, which blocked every prompt.
- `config/uninstall.py` run a second time no longer deletes your own values that match the template, or an identical `CLAUDE.md`: the record stays as an "uninstalled" marker. Without a record, keys are removed only when the Ideal-Umbrella hook is installed, and `CLAUDE.md` is backed up before it is deleted.
- `config/uninstall.py` compares against the values the install wrote (now kept in the record, with a hash of `CLAUDE.md`), not the current templates, so a `git pull` between install and uninstall no longer strands installed values or the `CLAUDE.md` backup. Anything left as is stays in the record.
- `config/install.py` and `config/uninstall.py` resolve `--home`, so `--home .` or a literal `~` no longer writes a relative hook path.
- `config/install.py`, `config/uninstall.py` and `config/add_to_repo.py` write through a symlinked `settings.json` or `CLAUDE.md` instead of replacing the link.
- A malformed hook entry (a hook that is not an object) no longer crashes install, uninstall or verify.
- Uninstall and verify no longer fail on a `CLAUDE.md` that is not UTF-8; uninstall leaves it as is.
- Reinstalling after editing `CLAUDE.md` or a setting by hand: uninstall now restores those edits, not the state before the first install.
- `scripts/unused_tools.py` exits with an error when the folder is missing or holds no transcripts, instead of reporting that no denied tool was used.
- Keyline test "absolute pattern matches backslash, other-case path" runs only on Windows; it failed on Linux and macOS, where backslashes and case are significant in paths.

## 2026-10-25 - audit fixes (#4)
- Cache-aware cost model, safe idempotent `config/install.py`, fail-closed keyline checks, `config/verify-tokens.py`, pytest suite.

## 2026-10-19 - first release
- Settings, CLAUDE.md rules, `hooks/context_check.py`, `keyline/` tools, cloud setup, `config/add_to_repo.py`, measurement scripts, research log.
