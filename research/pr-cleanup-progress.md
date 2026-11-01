# Ideal-Umbrella review follow-up: resume point

Updated 2026-11-01. Review 9 of main 7adc485 (the merge of PR #32) is done and reported in `research/review-findings-main-7adc485.md`, on branch `ccr-review9-7adc485` (draft PR). No code was changed: the user decides whether to fix.

## Request (user)

1. "Review the repo for correctness, errors and bugs then report in summary". Reviews 1-6 followed, each fixed and merged (PRs #12-#22). Review 7 (PR #25) was closed unfinished. Review 8 (PR #32) was fixed, self-reviewed and merged.
2. 2026-11-01, scheduled task: a fresh full review at main 7adc485, report only, change no code, open a draft PR, never merge.

## State

- **Review 9:** 0 high, 4 medium, 12 low, 7 informational.
  - Mediums: A1 (URL token swallows glued `**`, quotes, bidi marks; fails closed; regression), A2 ("No. 5" after ":", "**", "-", "#" loses the negation; fails open; regression of S4), A3 (`_x_` underscore emphasis hides invariants; fails open; predates review 8), B1 (stale `settings_created` survives `_merge_record`, so uninstall deletes a settings.json the user wrote).
  - All four reproduced in the main session with `python -I`; keyline ones also run against bcc441c to confirm which are regressions.
- **Baseline at 7adc485:** pytest 1512 passed, 14 skipped; keyline 35/35; pyflakes clean; JSON parses.
- **Probes:** session scratchpad `review9/a/` and `review9/b/` (lost with the container; the repros are written out in the report).

## Decisions and why

- **B1 graded medium** (reviewer B said low): it deletes a user-written file with a message claiming the installer created it; recoverable only from an install-time backup that uninstall does not mention.
- **Not fixed on purpose (still stand):** 36 (Windows junction), S45 (read-only `~/.claude` folder), a missing CLAUDE.md drops its record entry, keyline_lint's cache-header `int()` limit.
- **Earlier decisions still stand:** `|| exit 0` stays in the hook command; a missing uninstall backup keeps the file and the record entry; the `quote()` escape stays documented; merges use a merge commit; `settings_created` lets uninstall delete a file the install created; keyline's `_unextended` decides standalone tokens for both sides; `PAIR_FAMILY` is a closed allow-list.

## Open items

- **User decision:** whether to fix review 9's findings. Suggested order is in the report (B1-B3 first, then A2, A3, A1, A4, the lows, the mutation tests).
- **Recurring classes:** every medium this round is a *neighbour of a previous fix*; mutation runs found *fixes without tests* (6 in keyline_check.py, 8 in install/uninstall). Other classes to watch: absent is not empty (B3, A8), halfway state (B2, A7), stale record field (B1).
- **Routine:** after any fix, run a fresh-context self-review of the diff before merging, and a mutation pass over the changed guards.
