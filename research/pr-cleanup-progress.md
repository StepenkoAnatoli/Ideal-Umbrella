# Resume point: PR #38 reviewer rounds; G1-G5 and round 2 (R2-1 to R2-9) fixed; round 3 running

Updated 2026-11-03. Replace this file at each task boundary; do not append to it.

## State
- PR #36 and PR #39 are merged; main is at 0e1d027 (the #39 merge).
- The user asked (2026-11-03) for the follow-up to go to **PR #38**, branch `ccr-resume-after-36`.
  - That branch took origin/main in a merge commit (00ccb06), so nothing was force-pushed.
  - Its old resume-point change was superseded by this file.
- Fresh review of the #39 fixes (head 84bfecf): `research/review-findings-fresh-84bfecf.md`.
  - G1-G5 are all low, all in `config/cloud-setup.sh`, all fixed with a failing test first.
  - Report sections: Findings, Fixes, Checks, Review rounds.
- Round 2 (9 findings: 3 medium, 6 low) fixed in 86a492e; recorded under "Review rounds" in the report.
- Checks at 86a492e (temp HOME and CLAUDE_CONFIG_DIR):
  - pytest: 2124 passed, 16 skipped;
  - run_tests: 35/35;
  - pyflakes: clean;
  - the cloud-setup tests as `nobody`: 23 passed, 1 skipped (chown test, root only).
- Round 3 reviewer runs on 86a492e; output in the session scratchpad (round3/findings.md), lost if the session ends: rerun a round instead.

## Standing request from the user (2026-11-03)
- Keep running reviewer rounds until a round finds only 1 low (or nothing), then stop.
- After that, review the work once more.
- Record each round under "Review rounds" in the report above.

## Decisions
- cloud-setup.sh:
  - It makes the temp file with `mktemp` beside the file (TMPDIR as the fallback).
  - An EXIT trap removes the temp file. Only the "may be cut short" path keeps it, and that note names it.
  - The temp file takes the mode only once it is whole.
  - A file that is not a regular file is refused.
  - No `mv -T`: it is GNU-only, and on busybox it would push every run onto the in-place path.
  - Markers found by a two-pass awk mirroring install.py find_section/_fenced (order, fences, trailing whitespace); no recorded-hash fallback (the shell has no install record).
  - The body runs in `( ... ) || true` so a host setup script goes on, under set -e too.
  - A file not owned by the runner's user and group, or hard-linked, is written in place.
- keyline: אף not counted in "אף על פי" / "אף כי"; אל and verb across any whitespace; niqqud (POINTS) stripped for negations and hedges.
- Mode-dependent tests skip as root. Verify them as `nobody` on a copy of the tree:
  - `git ls-files -z | xargs -0 cp --parents -t $T`;
  - `chown -R nobody $T`;
  - `runuser -u nobody -- env HOME=$T/home PATH=$PATH python -m pytest -p no:cacheprovider tests/test_cloud_setup.py`.

## Next
- Fix round 3's findings test-first, record the round, push; repeat until a round finds at most one low; then a final self-review.
- Update the PR #38 body with the rounds (session is subscribed to PR #38).
- The user merges. Do not merge unasked.

## Open items
- The remote branch `wip-plain-round2` (a WIP backup) is still to be deleted by the user. The proxy refuses branch deletion (403).
