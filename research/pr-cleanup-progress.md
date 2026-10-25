# Ideal-Umbrella review follow-up — resume point (2026-10-25; third full review of main done, findings await a decision)

## Request (user)
"Review the repo for correctness, errors and bugs then report in summary", then "fix the two high items and push", then "when finished, work on the medium and low", then "check your work ... then merge", then "fix the two leftover items too", then "Run the full review again on main", then "Fix the two medium and the low items and merge once CI is green", then "merge it", then "Run the full review again on main" (third pass).

## State
- main is 99edcda (merge of PR #15, the resume point after PR #14). PRs #9, #10, #12, #13, #14 and #15 are merged.
- First sweep: findings in `research/review-findings-2026-10-25.md`, fixed in PR #12 and #13.
- Second full review of main 913ab0c: `research/review-findings-main-913ab0c.md` (no high, 2 medium, 8 low), all fixed in PR #14 (commit ee1dfee).
- Third full review of main 99edcda: `research/review-findings-main-99edcda.md` (no high, 1 medium, 6 low). Read-only pass; nothing in the code was changed. Each finding was reproduced with the command recorded in the report. Baseline on Linux: pytest 76 passed, keyline suite 35/35, pyflakes clean, the JSON templates parse. A second, fresh-context reviewer is running over the same tree; its confirmed findings go into the report by a follow-up commit.

## Decisions and why
- `|| exit 0` rather than a wrapper script: works in sh, bash and cmd.exe; the only cases masked are a missing file or interpreter, which must never block a prompt.
- Missing uninstall backup: keep the file and the record entry, so a restored backup plus a second uninstall still works.
- The `quote()` escape in install.py stays documented, not changed (a double quote cannot occur in a Windows path). The file-name match in `_is_ours` stays because tests and README define it.
- Compact boundary: the earlier rationale ("Claude Code records preTokens only") was wrong. Real `compact_boundary` events carry `postTokens` and `hooks/context_check.py` already uses it; only the comment at lines 120-123 is stale (finding 5 of the third review). The 0 fallback is still right when the field is absent.
- Merges use a merge commit (repo convention).

## Open items
- The seven findings of the third review (1 medium: ISO 8601 `T` timestamps are not a keyline date invariant; 6 low) await the user's decision on what to fix. Suggested fixes are in the report.
- Branch `ccr-866ae3a7-ac9ajn` carries the report and this resume point on top of main 99edcda.
