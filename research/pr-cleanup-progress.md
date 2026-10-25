# Ideal-Umbrella review follow-up — resume point (2026-10-25, done: PR #12 and the leftovers PR #13 merged)

## Request (user)
"Review the repo for correctness, errors and bugs then report in summary", then "fix the two high items and push", then "when finished, work on the medium and low", then "check your work ... then merge", then "fix the two leftover items too".
The earlier sweep (PR #9, #10) is done; its findings are in `research/review-findings-2026-10-25.md`.

## State
- PR #12 merged into main (596614a). Branch `ccr-866ae3a7-ac9ajn` restarted from that main for the leftovers, PR #13; the user asked for it to be reviewed and merged on 2026-10-25.
- Fixed: `config/install.py` hook command ends in `|| exit 0` (same in `config/user-settings.json`), so a synced settings.json on a machine without the hook file or interpreter no longer blocks every prompt. `config/uninstall.py` keeps `CLAUDE.md` and reports it when the recorded backup is missing, instead of deleting it; the record keeps the `claude_md` entry.
- Tests: `test_hook_command_does_not_block_prompts_when_the_hook_file_is_missing` (tests/test_install.py), `test_missing_claude_md_backup_keeps_the_file` (tests/test_uninstall.py). pytest 49 passed, keyline 34/34, pyflakes clean, JSON templates valid.
- CHANGELOG (Unreleased > Fixed) and README (Uninstall paragraph) updated.

## Decisions and why
- `|| exit 0` rather than a wrapper script: works in sh, bash and cmd.exe, and the hook itself already never exits non-zero, so the only cases masked are a missing file or interpreter, which must never block a prompt.
- Missing backup: keep the file and keep the record entry, so a restored backup plus a second uninstall still works.

## Also fixed (third commit): the medium and low findings
- `scripts/usage_breakdown.py`: non-object JSON lines skipped. `config/add_to_repo.py`: repo's own scalar kept with a notice, `--force` replaces; `merge()` returns `(changes, notices)`. `keyline/keyline_check.py`: empty source is INCONCLUSIVE.
- `config/install.py`: `permissions.deny` must be a list; OSError printed as one line; dead `verify_only` branch removed; verify also accepts the quoted hook path (home with a quote in it).
- `hooks/context_check.py`: stdin decoded as UTF-8 via `sys.stdin.buffer`; state files older than 30 days pruned when a new one is written; log trimmed to about half past 1 MB.
- `config/verify-tokens.py`: friendly message when tiktoken is missing.
- Leftovers fixed in the follow-up PR: `scripts/lint_validate.py` and `scripts/plugin_cost.py` take the corpus / Claude app folder as an argument (per-OS default, `CLAUDE_APP_DIR`), use the repo's keyline module and tiktoken cache, have `main(argv)` and usage; `scripts/tokentest.py` names its count function `count_claude` so pyflakes is clean. Tests: tests/test_lint_validate.py, tests/test_plugin_cost.py.
- Checks: pytest 57 passed (all 8 new tests fail on the old code, except the UTF-8 stdin one which only differs on a non-UTF-8 locale), keyline 35/35, pyflakes clean (64 pytest after the leftovers), JSON templates valid.

## Open items
- None. Every review finding is fixed and merged; a new task starts the branch again from main.
