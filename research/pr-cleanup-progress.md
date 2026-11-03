# Resume point: PR #38 reviewer rounds; G1-G5, round 2 and rounds 3-4 fixed; review loop finished; known limits and the last two fixed

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
- Round 3 (10 findings: 1 medium, 9 low) fixed in 27262c1; recorded in the report. Checks there: pytest 2142 passed, 17 skipped; run_tests 35/35; pyflakes clean; as `nobody` 31 passed, 1 skipped.
- Round 4 found 1 low (R4-1, על אף across a whitespace run), fixed; the loop has stopped, as asked. Final self-review done; recorded in the report.
- The user then asked to fix the known limits: אף before an unlisted ש-word (clause-negation rule), Friday short spelling, BOM-only file. Fixed and recorded under "Known limits, fixed after the loop". Checks: pytest 2158 passed, 17 skipped; run_tests 35/35; pyflakes clean; as `nobody` 33 passed, 1 skipped.
- Then "fix the remaining two too": an "although" clause with its own negation and a bare "אף שקע." are now ambiguous like "No. 5" (count in a source, in a rendering only as often as the source has one). Recorded under "The last two, fixed" in the report. Checks: pytest 2158 passed, 17 skipped; run_tests 35/35; pyflakes clean; as `nobody` 33 passed, 1 skipped.
- Open: the user deletes remote branch `wip-plain-round2` (the proxy refuses the delete). PR #38 stays open; do not merge.

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
- keyline: אף not counted in "אף על פי" / "אף כי" / "אף ש…" / "על אף" (space, maqaf or hyphen; ש-nouns listed in AF_NOUNS count; any other ש-word whose clause holds a negation of its own, or that stands as a bare answer "אף שקע.", is ambiguous like "No. 5"); calendar names and hedges matched on pointless text with `\s+` between words; אל and verb across any whitespace; niqqud (POINTS) stripped for negations and hedges.
- cloud-setup.sh stays busybox-safe: `stat -c %a` for the mode, a dangling link followed by hand; `set +C` in the subshell; BOM handled on line 1 in both passes.
- Mode-dependent tests skip as root. Verify them as `nobody` on a copy of the tree:
  - `git ls-files -z | xargs -0 cp --parents -t $T`;
  - `chown -R nobody $T`;
  - `runuser -u nobody -- env HOME=$T/home PATH=$PATH python -m pytest -p no:cacheprovider tests/test_cloud_setup.py`.

## Next
- Nothing pending on the loop. Handle PR #38 CI and review events.
- The user merges. Do not merge unasked.

## Open items
- The remote branch `wip-plain-round2` (a WIP backup) is still to be deleted by the user. The proxy refuses branch deletion (403).
