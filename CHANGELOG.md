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
- Keyline test "absolute pattern matches backslash, other-case path" runs only on Windows; it failed on Linux and macOS, where backslashes and case are significant in paths.

## 2026-10-25 - audit fixes (#4)
- Cache-aware cost model, safe idempotent `config/install.py`, fail-closed keyline checks, `config/verify-tokens.py`, pytest suite.

## 2026-10-19 - first release
- Settings, CLAUDE.md rules, `hooks/context_check.py`, `keyline/` tools, cloud setup, `config/add_to_repo.py`, measurement scripts, research log.
