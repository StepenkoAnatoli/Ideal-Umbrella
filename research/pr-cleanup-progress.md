# Ideal-Umbrella review follow-up — resume point (2026-10-25; third review's findings fixed in PR #16)

## Request (user)
"Review the repo for correctness, errors and bugs then report in summary", then "fix the two high items and push", then "when finished, work on the medium and low", then "check your work ... then merge", then "fix the two leftover items too", then "Run the full review again on main", then "Fix the two medium and the low items and merge once CI is green", then "merge it", then "Run the full review again on main" (third pass), then "When finished the review, fix all issues(high/medium/low) and then check your work for possible bugs/errors and then if all good merge".

## State
- main is 99edcda (merge of PR #15, the resume point after PR #14). PRs #9, #10, #12, #13, #14 and #15 are merged.
- First sweep: findings in `research/review-findings-2026-10-25.md`, fixed in PR #12 and #13.
- Second full review of main 913ab0c: `research/review-findings-main-913ab0c.md` (no high, 2 medium, 8 low), all fixed in PR #14 (commit ee1dfee).
- Third full review of main 99edcda: `research/review-findings-main-99edcda.md` (no high, 1 medium, 14 low after merging a fresh-context second reviewer's additions). All 15 fixed in PR #16 (branch `ccr-866ae3a7-ac9ajn`): keyline_check (ISO timestamps, possessives, month May, non-UTF-8 input), keyline_lint (tiktoken hint, non-UTF-8), install/uninstall (corrupt record refused, OSError reported, dangling symlinks, non-string backup, notice for an unwritten CLAUDE.md, UTF-8 stdout), context_check (band reset after a compaction above threshold, comment), CI comment, docs, CHANGELOG. Tests: `tests/test_keyline_check.py` and `tests/test_keyline_lint.py` new; cases added to test_install, test_uninstall, test_context_check. After the fixes: pytest 97 passed, keyline 35/35, pyflakes clean, JSON parses.

## Decisions and why
- `|| exit 0` rather than a wrapper script: works in sh, bash and cmd.exe; the only cases masked are a missing file or interpreter, which must never block a prompt.
- Missing uninstall backup: keep the file and the record entry, so a restored backup plus a second uninstall still works.
- The `quote()` escape in install.py stays documented, not changed (a double quote cannot occur in a Windows path). The file-name match in `_is_ours` stays because tests and README define it.
- Compact boundary: the earlier rationale ("Claude Code records preTokens only") was wrong. Real `compact_boundary` events carry `postTokens` and `hooks/context_check.py` already uses it; only the comment at lines 120-123 is stale (finding 5 of the third review). The 0 fallback is still right when the field is absent.
- Merges use a merge commit (repo convention).

- Finding 11 (record without a `claude_md` entry): the second reviewer's suggested deletion was rejected; a missing entry means the install never wrote CLAUDE.md, so the file is the user's own. A notice is printed instead. Pinned by `test_second_uninstall_keeps_the_users_own_values` and `test_record_without_claude_md_entry_keeps_the_file_and_says_so`.

## Open items
- PR #16 awaits green CI on ubuntu and windows, then merge (user's instruction: merge if all good). After the merge, restart branch `ccr-866ae3a7-ac9ajn` from main.
