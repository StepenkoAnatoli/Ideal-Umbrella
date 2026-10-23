# Changelog

All notable changes to Ideal-Umbrella. Format loosely follows Keep a Changelog.
HISTORY.md holds the narrative research log; this file is the scannable summary.

## [Unreleased]
### Added
- `install.py` / `uninstall.py`: one-command user-level install and undo, with `--dry-run`.
- `config/add_to_repo.py --dry-run`.
- `scripts/smoke_hooks.py`: simulated Claude Code events through both hooks.
- `scripts/unused_tools.py`: scan transcripts to keep `permissions.deny` honest.
- `IDEAL_UMBRELLA_TAIL_BYTES` env var for the transcript tail read in `hooks/context_check.py`.
- GitHub Actions workflow running the keyline suite and smoke tests.
- `CHANGELOG.md`.

### Changed
- README headline fixed-load figure corrected to 71,396 tokens (measured 2026-10-19, Code Browser off); old 83k figure retained as context.
- Install instructions now point at `install.py`.

### Fixed
- `hooks/context_check.py` tail size is now configurable instead of a hard-coded 4 MB.

## [0.1.0] - 2026-10-19
### Added
- Initial public release: settings, CLAUDE.md rules, `hooks/context_check.py`, `keyline/` tools, cloud setup, `config/add_to_repo.py`, measurement scripts, research log.