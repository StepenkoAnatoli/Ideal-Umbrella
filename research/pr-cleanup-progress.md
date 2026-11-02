# Ideal-Umbrella review follow-up: resume point

Updated 2026-11-01. Review 9 of main 7adc485 (the merge of PR #32) is reported in `research/review-findings-main-7adc485.md`; all findings and three rounds of self-review findings are fixed and merged (PR #33, merge cd9ea0e).

## Request (user)

1. "Review the repo for correctness, errors and bugs then report in summary". Reviews 1-6 followed, each fixed and merged (PRs #12-#22). Review 7 (PR #25) was closed unfinished. Review 8 (PR #32) was fixed, self-reviewed and merged.
2. 2026-11-01, scheduled task: a fresh full review at main 7adc485, report only, change no code, open a draft PR, never merge.

## State

- **Main:** cd9ea0e. Baseline: pytest 1838 passed, 14 skipped; keyline 35/35.
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

- **Done (2026-11-01):** the user said "yes, fix all of them then check your work and merge". PR #33 merged as cd9ea0e: review 9 fixes, then three fresh self-reviews (SA/SB, M1-M3, third round), each medium reproduced and fixed with a test. Final: pytest 1838 passed, 14 skipped; keyline 35/35; pyflakes clean; CI green on all 5 jobs.
- **For the next review:** the emphasis stripper in keyline_check (`_plain`) produced new neighbours in each self-review round, each smaller; review it first. Accepted fail-closed leftovers are listed in the report's "Third self-review" section.
- If restarting: re-run `python -m pytest -q`, `python -I keyline/tests/run_tests.py` and pyflakes before committing.
- **Recurring classes:** every medium this round is a *neighbour of a previous fix*; mutation runs found *fixes without tests* (6 in keyline_check.py, 8 in install/uninstall). Other classes to watch: absent is not empty (B3, A8), halfway state (B2, A7), stale record field (B1).
- **Routine:** after any fix, run a fresh-context self-review of the diff before merging, and a mutation pass over the changed guards.
