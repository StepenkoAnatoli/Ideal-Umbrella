# Resume point: general review done (report on `ccr-review-general`); next: user picks fixes

Updated 2026-11-03. Replace this file at each task boundary; do not append to it.

## History
- **PR #35** (merged as 1cd10bb) contains the `_plain` emphasis-stripper fix:
  - the review is in `research/review-findings-plain-2829343.md` (M1-M3, L1-L4, C1-C5);
  - fixes ran in 3 rounds, followed by 2 self-reviews.
- **PR #36**, branch `ccr-resume-after-35`. The user asked: "fix all stay in pr 36 and when done open new chat for new review".
  - Round 4 is commit 17c17c4. It fixes these:
    - L2: globs, indented code and HTML `<code>`/`<pre>` pair with nothing;
    - C3: CJK, Kana, Hangul and Thai count as non-word characters;
    - C5: `|` resets emphasis only inside tables, and a run after a lone `/` may close;
    - speed: F4 at 200 kB takes about 1.3 s.
  - Two findings are narrowed, not removed:
    - C2: an unknown bold `__word__` may render as `word`, but known dunders, code, and words glued to a path or call stay strict;
    - G4: `*_Code*` is unwrapped only outside the rendering's own code; `**__FILE__**` still fails, matching CommonMark.
  - Checks:
    - pytest 1985 passed, 14 skipped; run_tests 35/35; pyflakes is clean;
    - self-pass 0;
    - the fail-open fuzz matches 1cd10bb;
    - the differential fuzz against markdown-it was classified;
    - 15 of 15 mutants were killed.
  - The details are in the review report's "Round 4" section.
- The user merges #36. Do not merge it unasked.

## Decisions
- **No trade of fail-closed for fail-open.** Known dunders such as `__init__` stay strict.
- **CJK is non-word**, as Hebrew already was.
- **Indented-code detection is a heuristic.** When it misreads prose as code, the text is compared as written, which is the stricter choice.

## Done: general fresh review (branch `ccr-review-general`, stacked on #36)
- Report: `research/review-findings-general-44170ca.md`. 1 high, 7 medium, 14 low, 7 notes. Every high and medium finding has a `python -I` repro; I re-ran all of them except A2, which only the review agent ran.
- Top items:
  - A1 (high): add_to_repo writes through a committed file symlink to any target.
  - A3: install/uninstall take over or delete any hook naming `context_check.py`.
  - C1: an absolute `--watch` pattern through a symlinked path never matches.
  - B1/B2: curly-apostrophe and Hebrew negation gaps in keyline_check.
- The review branch is stacked on #36 because both change this file. Merge #36 first.

## Next task
- None started. The user decides which findings to fix. The report ends with a suggested order: A1, A3 and C1 first, then B1/B2, then A2 and B3/B4, then the lows.
- Report only so far. Do not fix anything unless the user asks.

## Open items
- Remote branch `wip-plain-round2` (a WIP backup) is still to be deleted by the user. The proxy refuses branch deletion (403).
