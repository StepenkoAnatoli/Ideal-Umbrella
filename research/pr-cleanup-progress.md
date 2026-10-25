# Ideal-Umbrella review follow-up — resume point (2026-10-25, PR #12 in review)

## Request (user)
"Review the repo for correctness, errors and bugs then report in summary", then "fix the two high items and push".
The earlier sweep (PR #9, #10) is done; its findings are in `research/review-findings-2026-10-25.md`.

## State
- Branch `ccr-866ae3a7-ac9ajn`, one commit (8730756) on top of main 8866310, draft PR #12 open and watched.
- Fixed: `config/install.py` hook command ends in `|| exit 0` (same in `config/user-settings.json`), so a synced settings.json on a machine without the hook file or interpreter no longer blocks every prompt. `config/uninstall.py` keeps `CLAUDE.md` and reports it when the recorded backup is missing, instead of deleting it; the record keeps the `claude_md` entry.
- Tests: `test_hook_command_does_not_block_prompts_when_the_hook_file_is_missing` (tests/test_install.py), `test_missing_claude_md_backup_keeps_the_file` (tests/test_uninstall.py). pytest 49 passed, keyline 34/34, pyflakes clean, JSON templates valid.
- CHANGELOG (Unreleased > Fixed) and README (Uninstall paragraph) updated.

## Decisions and why
- `|| exit 0` rather than a wrapper script: works in sh, bash and cmd.exe, and the hook itself already never exits non-zero, so the only cases masked are a missing file or interpreter, which must never block a prompt.
- Missing backup: keep the file and keep the record entry, so a restored backup plus a second uninstall still works.

## Open items (review findings not fixed; none requested)
- MED `scripts/usage_breakdown.py:72`: `event.get("message")` crashes on a JSON list/string line (guard with isinstance like unused_tools.py).
- MED `config/add_to_repo.py:70`: scalar keys overwrite a repo's own value silently (keep unless --force, like install.py).
- MED `keyline/keyline_check.py:165`: an empty source returns PASS; drop the `bool(source.strip())` term so it is INCONCLUSIVE.
- LOW `config/install.py:371`: verify accepts `permissions.deny` as a string (substring match).
- LOW `config/install.py:421`: only ValueError is caught; OSError prints a traceback.
- LOW `config/install.py:305`: dead `verify_only` branch in `install()`.
- LOW `hooks/context_check.py:114`: stdin decoded with locale encoding (keyline_hook uses UTF-8); state dir and log grow without bound.
- Merge PR #12 once CI is green on Ubuntu and Windows, after the user says OK.
