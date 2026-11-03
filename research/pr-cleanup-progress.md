# Resume point: keyline_check `_plain` fix (PR #35, merged)

Updated 2026-11-02. This file is replaced at each task boundary, not appended to.

## Task
User: "review the emphasis stripper in keyline_check", then "fix all of them then check your work and merge".
- Branch: `ccr-review-plain`, draft PR #35.
- Merge with a merge commit (repo convention) once CI is green and a fresh self-review finds nothing medium or worse.

## State
- 4d57131: review report `research/review-findings-plain-2829343.md` (M1-M3, lows L1-L4 and C1-C5).
- d27ac81: round 1 fix. Edge-free second scan, code spans verbatim. Fixes M1-M3, L1, L3, L4, C1, C3 (Hebrew) and C4.
- 038739b: round 2. Fixes F1-F4 from the first self-review: the code-token extension check, blockquote resets, the NUL marker, and the linear token index in `present()`. CI green.
- b08ce20: round 3. Fixes G1-G4 from the second self-review.
  - `present()` uses whichever is cheaper per token, the first-run walk or `str.find`; memory is O(input).
  - Nested quotes pair only at the same `>` depth.
  - pytest 1912/14, run_tests 35/35, pyflakes clean, self-pass 0 failures.
  - Self-review rounds are stopped: only lows remain, recorded in the review report.
- Left on purpose, as documented design limits: L2, C2, C3 (CJK) and C5.

## Decisions
- Structural fix (edge-free scan) instead of per-case regex patches. Earlier rounds kept producing neighbours.
- Code spans are compared verbatim. Accepted cost: a rendering that drops backticks around code with marks fails a little more often (fail-closed).
- Self-review rounds stop when only lows remain. The lows are recorded in the review report.

## Current task (2026-11-03)
User: "fix all stay in pr 36 and when done open new chat for new review".
- Fix the remaining lows on branch `ccr-resume-after-35` (PR #36): L2, C2, C3 (CJK), C5, G4, and the adversarial F4 timing (about 4 s).
- Constraints:
  - no new fail-open, so a fail-closed is not traded for a fail-open (for example, `__init__` must stay protected);
  - self-pass stays at 0;
  - the earlier repros are unchanged;
  - a failing test first for each fix.
- Then verify, commit, push, and get CI green on #36.
- Then open a new cloud session (create_session) for a fresh review of keyline_check at the new head. Brief it from this file.

## Open items
- Round 4 is in progress with the fixer subagent.
- Remote branch `wip-plain-round2` (a WIP backup) is still to be deleted by the user. The proxy refuses branch deletion (403).
