# Open PR clean-up — resume point (2026-10-25)

## State: done
- #4 merged (test fixed: the hook command must not start with a bare `python3 `).
- #5 closed: an older, incomplete copy of #4; its CI file had a wrong `Ideal-Umbrella/` path prefix.
- #3 closed. Its useful parts were ported to #6, and its uninstall, which deleted the user's own values, was rewritten.
- #6 merged (3911e79), CI green on ubuntu-latest and windows-latest. It added:
  - `.github/workflows/ci.yml`: pytest, keyline tests and a JSON check on Linux and Windows.
  - `config/uninstall.py` plus `ballast/install-record.json`, written by `config/install.py`. This makes the install reversible: replaced values are restored, and only the deny entries and hooks we added are removed.
  - `IDEAL_UMBRELLA_TAIL_BYTES` for `hooks/context_check.py`.
  - `scripts/unused_tools.py`.
  - `CHANGELOG.md`.
  - The keyline backslash/case watch test now runs on Windows only (34 checks on Linux, 35 on Windows).

## Decisions and why
- When install is run more than once, the first-seen value wins in the record, so a later `--force` cannot make uninstall forget the original value.
- Uninstall leaves any value the user changed after installing as it is and prints a note, because it never overwrites user edits.
- If there is no record (an older install), uninstall leaves permissions.deny alone, because it cannot tell which entries were ours.

## Follow-up (user approved, 2026-10-25)
- `config/install.py` verify: when the user keeps their own autoCompactWindow or skillListingBudgetFraction, it now prints a warning and passes (exit 0). A missing value still fails. Why: install keeps these by design unless --force, so failing on them was wrong.

## Open items
- None.
