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
- Round 3, in progress and uncommitted: G1-G3 from the second self-review.
  - G1 (medium, from the F4 index): tokens starting with a non-word character are quadratic in time and memory. 30 s and 1.4 GB at 200 kB, past the hook's 30 s timeout.
  - G2 (medium): tokens with a shared first run but different lengths are still quadratic.
  - G3 (low): a nested `> >` quote doesn't reset emphasis pairing.
  - G4 (low): fail-closed; a README note only.
  - Plan: per token, use the cheaper of the index walk and `text.find`; memory O(input); results identical to d27ac81.
- Left on purpose, as documented design limits: L2, C2, C3 (CJK) and C5.

## Decisions
- Structural fix (edge-free scan) instead of per-case regex patches. Earlier rounds kept producing neighbours.
- Code spans are compared verbatim. Accepted cost: a rendering that drops backticks around code with marks fails a little more often (fail-closed).
- Self-review rounds stop when only lows remain. The lows are recorded in the review report.

## Open items
- After round 3:
  - verify with `python -I` repros (M1-M3, F1-F4, G1-G3, and scratchpad rep2.py, which must be unchanged);
  - run pytest (1905/14 at 038739b), `python -I keyline/tests/run_tests.py` (35/35), pyflakes, and self-pass.
- Then add a CHANGELOG line and a report section, commit, push, and update the PR body.
- Run another fresh self-review of the round-3 diff if round 3 changed non-trivial code.
- Merge PR #35 with a merge commit.
- Remote branch `wip-plain-round2` (backup) must be deleted by the user. The proxy refuses branch deletion (403).
- Scratch details in the session scratchpad `plain/`: FIX.md, SELFREVIEW.md and SELFREVIEW2.md. They are lost if the container goes; the summaries are in the review report.
