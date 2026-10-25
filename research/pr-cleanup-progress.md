# Ideal-Umbrella review follow-up — resume point (2026-10-25; fourth review of main 51da01e in draft PR #18, 15 findings fixed, not merged)

## Request (user)
"Review the repo for correctness, errors and bugs then report in summary", then "fix the two high items and push", then "when finished, work on the medium and low", then "check your work ... then merge", then "fix the two leftover items too", then "Run the full review again on main", then "Fix the two medium and the low items and merge once CI is green", then "merge it", then "Run the full review again on main" (third pass), then "When finished the review, fix all issues(high/medium/low) and then check your work for possible bugs/errors and then if all good merge", then "Run the full review again on main, fix the class each time" (fourth pass; no merge asked).

## State
- main is 51da01e (merge of PR #17, docs only). PRs #9, #10, #12, #13, #14, #15, #16 and #17 are merged. Branch `ccr-866ae3a7-ac9ajn` was restarted from that main and carries the fourth review in draft PR #18 (not merged: the user did not ask for a merge this time).
- Fourth full review of main 51da01e: `research/review-findings-main-51da01e.md`, 15 findings (no high; 7 medium, 8 low), findings 1-5 from the first reviewer and 6-15 from a fresh-context second reviewer (its report: scratchpad `breaker2/report.md`, not in the repo). Each fixed class-wide with failing-first tests, every hit listed with file:line, and a prevention. Fixes: keyline_check (new extractions `PRs`/`v2`/hashes/`sha256`/`__init__`, strict number boundary in `present()`, mid-line markers, Hebrew hedges, calendar aliases, all-caps `MAY`), keyline_hook (outside-project notes ignored), install (interpreter check in verify, `_write_bytes` atomic writes, four-path symlink check, "Done before the error" listing), uninstall (non-list deny notice and kept `deny_added`, atomic restore, progress listing), add_to_repo (symlink check, atomic writes), tests/test_source_rules.py (exit and decode-handler scans), docs and CHANGELOG. After the fixes: pytest 143 passed, keyline 35/35, pyflakes clean, JSON parses. CI on PR #18 was green for 6cff84a (findings 1-15). The pre-merge self-review ("Review the work and if good merge") found one regression of the fixes, finding 16 in the report: `_write_bytes` gave a new file mode 0600; fixed with `_umask()` in both helpers and two failing-first tests.
- First sweep: findings in `research/review-findings-2026-10-25.md`, fixed in PR #12 and #13.
- Second full review of main 913ab0c: `research/review-findings-main-913ab0c.md` (no high, 2 medium, 8 low), all fixed in PR #14 (commit ee1dfee).
- Third full review of main 99edcda: `research/review-findings-main-99edcda.md` (no high, 1 medium, 14 low), all 15 fixed in PR #16 (merged 2026-10-25).

## Decisions and why
- `|| exit 0` rather than a wrapper script: works in sh, bash and cmd.exe; the only cases masked are a missing file or interpreter, which must never block a prompt.
- Missing uninstall backup: keep the file and the record entry, so a restored backup plus a second uninstall still works.
- The `quote()` escape in install.py stays documented, not changed (a double quote cannot occur in a Windows path). The file-name match in `_is_ours` stays because tests and README define it.
- Compact boundary: the earlier rationale ("Claude Code records preTokens only") was wrong. Real `compact_boundary` events carry `postTokens` and `hooks/context_check.py` already uses it; only the comment at lines 120-123 is stale (finding 5 of the third review). The 0 fallback is still right when the field is absent.
- Merges use a merge commit (repo convention).

- Finding 11 (record without a `claude_md` entry): the second reviewer's suggested deletion was rejected; a missing entry means the install never wrote CLAUDE.md, so the file is the user's own. A notice is printed instead. Pinned by `test_second_uninstall_keeps_the_users_own_values` and `test_record_without_claude_md_entry_keeps_the_file_and_says_so`.

## Open items
- PR #18 (fourth review) is a draft with CI green on 6cff84a, not merged (not asked); merge it when told, then restart the branch from main.
- The `send_later` check-in on PR #18 fired at 20:35 UTC and found nothing new (CI green, mergeable, no review threads); check-ins stopped. The next GitHub event or a message from the user resumes work.
