# Ideal-Umbrella bug sweep — resume point (2026-10-25, template-update follow-up in review)

## Request (user)
"fix the git pull template update gap too". This follows the bug sweep: all 8 findings in `research/review-findings-2026-10-25.md` and a self-review bug were fixed and merged in PR #9 (64b0e53).

## State
- Branch `ccr-da04ab7d-6rorpx` was restarted from main 64b0e53. It holds one commit for the gap and has a new draft PR. Merging needs the user's OK.
- The fix: `merge_settings(..., previous=old_record["installed"])`. If a key still holds the value an earlier install wrote, it is updated to a changed template value without `--force`. The change is listed as "(template changed)". Values the user set are still kept, with a notice.
- `verify` reads the expected `autoCompactWindow` and `skillListingBudgetFraction` from `config/user-settings.json` instead of hardcoded values.
- Tests: `test_reinstall_updates_a_value_an_earlier_install_wrote` (fails on the old code) and `test_reinstall_keeps_a_value_the_user_set_after_install`, both in `tests/test_uninstall.py`.
- Local checks: pytest 47 passed; keyline 34/34; pyflakes clean.
- CHANGELOG (Unreleased > Fixed) and README (Install bullet) are updated.

## Decisions and why
- An updated key is not added to `record["replaced"]`. It is already tracked (in `added_keys` or `replaced`), and `_merge_record`'s `installed.update` stores the new value, so uninstall compares against it and still removes or restores it correctly.
- Earlier decisions for findings #1–#8 are in git history (this file at 64b0e53) and in the CHANGELOG.

## Open items
- Merge the new PR once CI is green on Ubuntu and Windows, after the user says OK.
- Not checked: real Claude Code hook behavior on Windows, and the read-only CLAUDE.md variant of #1 (the sandbox runs as root).
