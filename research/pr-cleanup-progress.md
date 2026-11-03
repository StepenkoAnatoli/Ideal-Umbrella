# Resume point: fresh review of PR #39 and its self-check fixed (cd56bb2); next: a second fresh review of PR #39 in a new session

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

## Done: fresh review of PR #39 (head 4c3992c), fixed in fa13143, self-checked in cd56bb2
- Report: `research/review-findings-fresh-4c3992c.md` (Findings, Fixes, Self-check tables).
- F1-F5 (2 medium, 3 low) are fixed in fa13143:
  - F1: install's verify judged a user's own context_check hook;
  - F2: keyline counted אל תוך/תחת/תל as negations;
  - F3: uninstall said nothing about a hand-wired ballast hook;
  - F4: add_to_repo gave symlink advice for a repo inside the config folder;
  - F5: cloud-setup could leave half a section.
- S1-S3 are fixed in cd56bb2:
  - S1: the cloud-setup temp file began at 0644 (the A8 class);
  - S2: a file that cannot be renamed over got no rules;
  - S3: the F2 exclusion was too narrow; the ת-nouns docs put after אל are now in `AL_TO`.
- Checks at cd56bb2 (temp HOME and CLAUDE_CONFIG_DIR): pytest 2094 passed, 14 skipped; run_tests 35/35; pyflakes clean.
- PR #39 body updated. This session is subscribed to PR #39.
- Decisions:
  - F1: verify checks our hooks first and falls back to the others only when none is ours;
  - F2/S3: AL_TO lists words, it does not guess from word shape (an ending in ת would also take verbs such as תשבית); a listed verb only fails closed;
  - F3: a note rather than removal;
  - F5/S1/S2: build at 0600 beside the file and mv it over; when there is no rename, write in place and keep the temp file if that write stops short; always exit 0.

## Next
- A second fresh review of PR #39 at cd56bb2 or later runs in a new session (asked by the user 2026-11-03): report to `research/review-findings-fresh-<head sha>.md`, then fix on ccr-fix-general.
- The user reviews and merges #36, #37, #39 in order. Do not merge unasked.
- Handle PR #39 events (CI, review comments); this session is subscribed. Confirm CI is green at the latest head, Windows included.
- Windows CI on #39 was red from 89d0bc5 to 7c7c676: the 4 cases of the A1 test `test_a_file_link_to_an_unrelated_file_is_refused_before_anything_is_written` looked for a `/` path in stderr. b389cac compares with `os.path.normpath`; confirm the Windows job is green at b389cac or later. The new tests pass or skip on Windows (seen in the 9d0c3ca run).
- Run the suite with a temp HOME and CLAUDE_CONFIG_DIR exported in the same Bash call, and commit in a call without them (git's identity lives in the real HOME).

## Open items
- Remote branch `wip-plain-round2` (a WIP backup) is still to be deleted by the user. The proxy refuses branch deletion (403).
