# Review of branch graphify-ideas at 50990a4 (2026-10-31, thirty-seventh pass)

One fresh-context reviewer did a breaker review of the diff `origin/main...50990a4`. It ran on the
session's default model, because Fable was rate-limited, and it was paused once by the weekly usage limit.

Its report and repro scripts are in the session scratchpad, not in the repo: `review37b-findings.md` and
`review37b/`. That folder holds:
- `repro/t1_unpinned_own_cr_terms.py` (T1) and `repro/r1_bare_cr_left.py` (L1), each taking a source tree;
- `repro/x1_histories.py`: review36b's h1 extended with a line typed at the end of the text, up to 3 edits;
- `repro/x4_amb_check.py`: checks that each row where the head is worse also fits another history;
- `repro/x2_nocr.py` and `x3_sort.py`: texts with no bare CR;
- `mut/mut.py`: fix36's mutants plus k1-k5.

New ground in this pass: edit histories of depth 3, with the head compared against the real e5a61a7 and
f62ab8d code.

The findings of passes 1 to 36 were checked and are not reported again (`research/review-findings-graphify-5a18f22.md` to `-e5a61a7.md`).

**Status:** no code defect. One test gap (T1) and one gap in the records and docs (L1), both fixed in the
next commit on PR #27.

What the reviewer confirmed:
- CI at 50990a4 is green on all five jobs, and none of the pass-36 tests is skipped on Windows.
- Every earlier harness gives the same rows as on e5a61a7, with backup timestamps normalised.
- `review36b/repro/r1_crlf_line_on_bare_cr.py` now has 0 bad rows.
- `fix36/mut.py` j1, j3-j8 and h4 are killed, and j9 is equivalent.
- Leaving out `joined == "\n\n"` changes no result at 6 pieces and 2 edits or at 4 pieces and 3 edits.
- No user byte is lost in a text with no bare CR, at 4 pieces and 3 edits.

Checks run on the fixed tree, all passing:
- pytest on 3.13, on 3.10, and on a real 3.14 (with an 8 MB stack and with an unlimited one);
- keyline, pyflakes and the JSON checks;
- the CRLF copy (`crlf-p38`), with and without `write_text` forced to CRLF, and the forced run in the tree.

## T1 (low, test gap): three terms of the `own_cr` exclusion were not pinned

**Defect class:** a test would not catch a regression.

**Evidence:** four mutants of the `own_cr` line survived the suite:
- k1 excludes `\n\n` instead of `\r\n\n` (the pass-36 choice reversed);
- k2 adds `\n\n` to the excluded endings;
- k4 adds `\r`;
- k5 excludes only `\n`.

Each one changes a real result: with `note\r\n` added at the top, `a\n\n\r` (k1, k5), `a\r\r` (k4) or
`a\n\r` (k5) loses its last CR.

**Fixed (test):** those three texts were added to the parametrize of
`test_a_crlf_line_added_above_a_text_ending_in_a_bare_cr_keeps_that_cr`. The head passes all three.
The mutant kill is the failing-first proof: scratchpad `fix37/mut.py` kills k1, k2, k4 and k5.

## L1 (low, records and docs): the trade `own_cr` makes was not stated, and the pass-36 counts were not scoped

**Defect class:** a record or doc claims more than the code does.

**Evidence:** at 4 pieces and 3 edits, the head leaves a bare CR in 663 histories that e5a61a7 got right.
For example: `x\ny` is installed (two LF recorded), the file is converted to CRLF, the blank line above
the section is deleted, and a blank LF line is added. That gives `x\r\ny\r\n\n` above the section, and
uninstall leaves `x\r\ny\r`.

The reviewer showed this is not a code defect. All 663 files are also what another history gives: a text
ending in a bare CR (here `y\r`), with whole CRLF lines inserted (here `x` at the top). For that history
the head's result is the right one. A narrower rule it tried (k6) is still a trade at depth 3.

The pass-36 counts (376/10 against f62ab8d; `\r\n\n` "right in 127 more histories and wrong in none")
hold at 6 pieces and 2 edits only. At depth 3 the `\n\n` exclusion beats `\r\n\n`, 330 to 109; all
those rows are the same ambiguous shapes.

**Fixed (docs and test):**
- The README sentence "Your own text stays byte for byte" now names the exception.
- The CHANGELOG Review 36 entry says which reading is chosen.
- `-e5a61a7.md` scopes its counts to 6 pieces and 2 edits.
- `test_a_crlf_conversion_then_a_deleted_and_an_lf_blank_line_is_read_as_a_bare_cr_text` pins the chosen
  reading, so a later change to it is deliberate. Mutant m1 (`own_cr = False`, the e5a61a7 reading) fails it.

## Info (no action)

- I1. `\r\n\n` against `\n\n`: the head wins at 2 edits (127 to 0) and loses at 3 edits (330 to 109).
  Neither is better everywhere. Excluding a CR (k4) or any LF (k5) is worse.
- I2. At 6 pieces and 2 edits the head is strictly better than e5a61a7. The 10 rows where f62ab8d is
  right are ambiguous, as recorded.
- I3. A CRLF blank line plus an LF blank line above the section of an LF file leaves a bare CR in all
  three heads. These are also the bytes of a bare-CR text with no edits.
- I4. Harness note: h1 with a print limit of 0 prints no rows. Use `fix36/cmp.py` or a limit of 1.

## Prevention

A count from a brute force holds at the depth it ran at. State the pieces and edits next to every count,
and before claiming a rule is "wrong in none", rerun it one edit deeper.
