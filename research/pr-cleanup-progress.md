# Resume point: all general-review fixes done (PR #39); next: review of PR #39 by the user

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

## Done: high and medium fixes (branch `ccr-fix-general`, draft PR #39, stacked on #36 and #37)
- A1, A3, C1, B1, B2, A2, B3 and B4 are fixed and pushed, with head 04fc025.
- The details and commits are in the "Fixes" section of `research/review-findings-general-44170ca.md`.
- Checks: pytest 2022 passed, 14 skipped; run_tests 35/35; pyflakes clean.
- This session is subscribed to PR #39 activity.
- Decisions:
  - A1 refuses a link to a file with a different name, and any landing in the Claude config folder. A same-name dotfiles link is still allowed; tests 237/255 need it.
  - A3: verify-only keeps its loose match, because it only reports. No record of a replaced command is kept, since the strict match makes one unnecessary.
  - B4: COUNT counts sessions, not files. The README "Why" split is flagged and has not been measured again; that needs the user's local transcripts.

## Done: the lows and notes (branch `ccr-fix-general`, draft PR #39)
- Fixed: A4-A9, B5-B7, C2-C6, N1, N2, N4, N5; N6 was already fixed by B3. N3 and N7 are documented limits.
- Each fix: failing test first, class searched, README and CHANGELOG updated. The commit per ID is in the "Fixes" table of `research/review-findings-general-44170ca.md`.
- Checks at the last code commit, with a temp HOME and CLAUDE_CONFIG_DIR: pytest 2069 passed, 14 skipped; run_tests 35/35; pyflakes clean.
- Tests now clear CLAUDE_CONFIG_DIR (`tests/conftest.py`), since install warns about it beside `--home`.

## Next
- The user reviews and merges #36, #37, #39 in order. Do not merge unasked.
- Handle PR #39 events (CI, review comments); this session is subscribed, with a check-in trigger at about 08:29 UTC.
- Windows CI on #39 was red from 89d0bc5 to 7c7c676: the 4 cases of the A1 test `test_a_file_link_to_an_unrelated_file_is_refused_before_anything_is_written` looked for a `/` path in stderr. b389cac compares with `os.path.normpath`; confirm the Windows job is green at b389cac or later. The new tests pass or skip on Windows (seen in the 9d0c3ca run).
- Run the suite with a temp HOME and CLAUDE_CONFIG_DIR exported in the same Bash call, and commit in a call without them (git's identity lives in the real HOME).

## Open items
- Remote branch `wip-plain-round2` (a WIP backup) is still to be deleted by the user. The proxy refuses branch deletion (403).
