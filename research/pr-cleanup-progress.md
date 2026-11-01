# Ideal-Umbrella review follow-up: resume point

Updated 2026-11-01. Review 8 of main bcc441c, its fixes and a self-review of those fixes are all in PR #32 (branch `ccr-review8-bcc441c`). The PR is merged on the user's "yes, fix all of them then check your work and merge".

## Request (user)

1. "Review the repo for correctness, errors and bugs then report in summary". Reviews 1-6 followed, each fixed and merged (PRs #12-#22). Review 7 (PR #25) was closed unfinished.
2. 2026-11-01: a fresh full review at current main (bcc441c), reported in `research/review-findings-main-bcc441c.md`.
3. "yes, fix all of them then check your work and merge", then "stay in this session and finish".

## State

- **Review 8:** 4 medium and 42 low findings, plus 3 informational notes, all fixed except those listed below. Commits: 74a3343 (config) and 51f97b8 (keyline/scripts).
- **Self-review of the fix diff:** two fresh-context reviewers found 6 medium and 15 low defects, all fixed:
  - config C1-C4, commit fa46c9a;
  - keyline/scripts S1-S13, commit ccad14c.
  The report section "Self-review of the PR diff" has the details.
- **Main merged into the branch** (6f616be): PRs #31, #24 and #21. README.md merged cleanly.
- **Final runs:** pyflakes clean; pytest 1512 passed, 14 skipped; keyline 35/35. The CI matrix runs on the head.

## Decisions and why

- **Not fixed on purpose:**
  - 36, a Windows junction: Windows-only, and documented.
  - S45, a read-only `~/.claude` folder: `os.access` on folders is unreliable.
  - A missing CLAUDE.md drops its record entry: this is the documented design.
  - keyline_lint's cache-header `int()` digit limit: it needs a corrupt cache the tool wrote itself.
- **settings.json lifecycle:** the new record field `settings_created` lets uninstall delete a file the install created. A missing settings.json that the record holds changes to is "away", not new. A created file that is gone drops its part of the record.
- **keyline:** one function (`_unextended`) decides whether a token stands alone, for both the source and the rendering, so a note always passes against itself. Pairs are a closed allow-list (`PAIR_FAMILY`). URLs and numbers are looked up by extraction.
- **Earlier decisions still stand:**
  - `|| exit 0` stays in the hook command.
  - A missing uninstall backup keeps the file and the record entry.
  - The `quote()` escape stays documented.
  - Merges use a merge commit.

## Open items

- None for review 8. The next review starts from main after PR #32's merge.
- **Recurring classes to watch:**
  - neighbour of a previous fix (S1 after medium 2);
  - absent is not empty (C2);
  - halfway state (C1);
  - fix without test (S9).
- **Routine:** after any fix, run a fresh-context self-review of the diff before merging. This round, the self-review found 6 more mediums.
