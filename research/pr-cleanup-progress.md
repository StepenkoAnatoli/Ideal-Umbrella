# Resume point: PR #39 fixes reviewed again; G1-G5 fixed on PR #38; reviewer rounds run until one finds at most one low

Updated 2026-11-03. Replace this file at each task boundary; do not append to it.

## State
- PR #36 and PR #39 are merged; main is at 0e1d027 (the #39 merge).
- The user asked (2026-11-03) for the follow-up to go to **PR #38**, branch `ccr-resume-after-36`.
  - That branch took origin/main in a merge commit (00ccb06), so nothing was force-pushed.
  - Its old resume-point change was superseded by this file.
- Fresh review of the #39 fixes (head 84bfecf): `research/review-findings-fresh-84bfecf.md`.
  - G1-G5 are all low, all in `config/cloud-setup.sh`, all fixed with a failing test first.
  - Report sections: Findings, Fixes, Checks, Review rounds.
- Checks at the G1-G5 commit (temp HOME and CLAUDE_CONFIG_DIR):
  - pytest: 2097 passed, 16 skipped;
  - run_tests: 35/35;
  - pyflakes: clean;
  - the cloud-setup tests as `nobody`: 14 passed.

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
- Mode-dependent tests skip as root. Verify them as `nobody` on a copy of the tree:
  - `git ls-files -z | xargs -0 cp --parents -t $T`;
  - `chown -R nobody $T`;
  - `runuser -u nobody -- env HOME=$T/home PATH=$PATH python -m pytest -p no:cacheprovider tests/test_cloud_setup.py`.

## Next
- Reviewer rounds on PR #38 (see the standing request above). Then push, update the PR #38 body, and subscribe to PR #38.
- The user merges. Do not merge unasked.

## Open items
- The remote branch `wip-plain-round2` (a WIP backup) is still to be deleted by the user. The proxy refuses branch deletion (403).
