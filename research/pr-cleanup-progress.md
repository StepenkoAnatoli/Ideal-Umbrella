# Resume point: keyline_check `_plain` fix (PR #35)

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

## Open items
- Wait for CI on b08ce20. Then mark PR #35 ready and merge it with a merge commit.
- Remote branch `wip-plain-round2` is a WIP backup and must be deleted by the user. The proxy refuses branch deletion (403).
- After the merge, this file is on main. A later task replaces it.
