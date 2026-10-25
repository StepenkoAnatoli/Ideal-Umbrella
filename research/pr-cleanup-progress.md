# Ideal-Umbrella review follow-up — resume point (2026-10-25; all review findings fixed and merged)

## Request (user)
"Review the repo for correctness, errors and bugs then report in summary", then "fix the two high items and push", then "when finished, work on the medium and low", then "check your work ... then merge", then "fix the two leftover items too", then "Run the full review again on main", then "Fix the two medium and the low items and merge once CI is green".

## State
- Done. main is bd982df (merge of PR #14). PRs #9, #10, #12, #13 and #14 are merged; nothing is open.
- First sweep: findings in `research/review-findings-2026-10-25.md`, fixed in PR #12 and #13 (hook command `|| exit 0`, uninstall keeps CLAUDE.md when the backup is missing, transcript and add_to_repo robustness, install.py checks, context_check.py stdin/pruning/log trim, verify-tokens hint, lint_validate and plugin_cost arguments and tests).
- Second full review of main 913ab0c: report in `research/review-findings-main-913ab0c.md` (no high, 2 medium, 8 low). All fixed in PR #14 (commit ee1dfee):
  - Medium: `scripts/toolresult_share.py`, `scripts/usertext_split.py`, `scripts/usertext_top.py` skip non-object JSONL lines, print usage without arguments and exit with a message on empty input (no ZeroDivisionError).
  - Low: `scripts/unused_tools.py` ignores a tool_use without a string name; `config/install.py` writes settings.json before the install record and documents the `quote()` escape; `hooks/context_check.py` documents the 0 after a compact boundary; `keyline/measure.py` gives an install hint when tiktoken is missing; README, keyline/README, hook and run_tests docstrings and CHANGELOG corrected (suite is 35 checks on Linux/macOS, 36 on Windows).
  - Tests: `tests/test_transcript_scripts.py`, `tests/test_measure.py` new; one check added to `tests/test_unused_tools.py` and `tests/test_install.py`. pytest 76 passed, keyline 35/35, pyflakes clean, JSON templates valid. CI green on ubuntu and windows before the merge.

## Decisions and why
- `|| exit 0` rather than a wrapper script: works in sh, bash and cmd.exe; the only cases masked are a missing file or interpreter, which must never block a prompt.
- Missing uninstall backup: keep the file and the record entry, so a restored backup plus a second uninstall still works.
- Two low findings were documented rather than changed: the `quote()` escape (a double quote cannot occur in a Windows path) and the compact-boundary 0 (Claude Code records preTokens only; 0 is honest and clears the band state). The file-name match in `_is_ours` stays because tests and README define it; the README now says so.
- Merges use a merge commit (repo convention).

## Open items
- None. Branch `ccr-866ae3a7-ac9ajn` sits on main bd982df; the next task starts from there.
