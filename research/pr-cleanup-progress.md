# Ideal-Umbrella review follow-up: resume point

Updated 2026-11-01. The eighth full review of main bcc441c is reported in draft PR #32 (branch `ccr-review8-bcc441c`). On "yes, fix all of them then check your work and merge" the fixes are in progress on that branch.

## Request (user)

Earlier rounds, in order:

1. "Review the repo for correctness, errors and bugs then report in summary". Reviews 1-6 followed, each fixed and merged (PRs #12-#22).
2. Review 7 on main b46792d (PR #25). It was left unfinished, and the user closed it.
3. Latest request (2026-11-01): "Run a fresh full review ... at the current main (record the sha)". Use #25's report as a checklist only, change no code, and open a draft PR with the report and this resume point.

## State

- **main:** `bcc441cd36c6008fe44bbf3b1b8295de5c127841`, the merge of PR #29. PRs #26, #27, #29 and #30 are merged. #25 is closed and not merged.
- **Report:** `research/review-findings-main-bcc441c.md`.
- **Counts:** 0 high, 4 medium, 42 low, plus 3 informational notes.
- **Mediums:** old #1-#4, all in `keyline/keyline_check.py`, all reproduced with `python -I`:
  - the space datetime fails against the ISO form (fails closed);
  - an extended path or name passes;
  - a sha256 is not extracted;
  - a non-ASCII name is not extracted.
- **Old checklist (#25's report):**
  - Main findings: 28 of 35 still hold. These no longer hold: #5, #7, #8, #16, #17, #19 and #30.
  - Self-check items: 9 still hold in current main; the rest concern code that never landed.
- **Fresh lows:** N1-N9. The main one is N1, `measure.py` printing a change line between the wrong pair of files.
- **Baseline:** pytest 1297 passed, 14 skipped (as root); keyline 35/35; pyflakes clean; the JSON files parse.
- **Reviewer notes:** reviewer A's report and probes are in the session scratchpad `review8/a/`, and reviewer B's are in `review8/b/report.md`. Neither is in the repo; the session scratchpad is discarded with the session.

## Decisions and why

- **#25's fixes were not ported.** The user asked for a fresh review, so each old finding was re-run on current main, and only the ones that still hold are reported, with their old number.
- **Self-check items from #25 are reported only when their defect exists in main.** Most of them are about fix commits that never merged.
- **Earlier decisions still stand:**
  - `|| exit 0` stays in the hook command.
  - A missing uninstall backup keeps the file and the record entry.
  - The `quote()` escape stays documented.
  - A record without a `claude_md` entry keeps the user's file.
  - Merges use a merge commit.

## Fix progress (in progress)

- **Done:** config findings 23-28 and 44-46 (37 = 24) are committed as 74a3343. A new record field, `settings_created`, lets uninstall delete a settings.json the install created; a record without the field keeps today's `{}`. The per-finding Fixed/Test/Other hits/Prevention notes are in the session scratchpad `review8/fix-config-notes.md`; they still need copying into the report.
- **Not fixed on purpose:**
  - S45, a read-only `~/.claude` folder: `os.access` on folders is unreliable, and a check would change install and add_to_repo too.
  - A missing CLAUDE.md drops its record entry: this is the documented design, and a notice names the backups.
- **Running:** a fixer agent on keyline/ and scripts/: mediums 1-4 and lows 5-22, 29-35 and 38-43. Its work is uncommitted in the working tree.
- **Next:**
  1. Commit the keyline fixes.
  2. Add Fixed/Other hits/Prevention to each finding in the report, and update CHANGELOG.md.
  3. Run a fresh-context self-review of the fix diff (`git diff bcc441c..HEAD -- . ':!research'`), and fix what it finds.
  4. Merge PR #32 with a merge commit once CI is green.

## Open items

- **The user decides whether to fix.** The suggested order is in the report:
  1. the four mediums in `keyline_check`;
  2. uninstall state loss: old #14, #6, #18 and N7;
  3. the remaining lows, class by class.
  When fixing, use the fix-the-class routine: a failing test first, the class named, a whole-repo search for other hits, and a prevention line. Then run a fresh-context self-review of the diff before any merge.
- **Recurring classes to watch:**
  - "neighbour of a previous fix": mediums 2-4, N3;
  - "absent is not empty": old #14, N7;
  - "halfway state": old #6, N1;
  - "fix without test": old #9, #13, N8.
