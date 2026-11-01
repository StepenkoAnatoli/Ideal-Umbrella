# Review of branch graphify-ideas at f6079da (2026-10-31, fortieth pass)

One fresh-context reviewer did a breaker review of the diff `origin/main...f6079da`. It compared the head
against the real 1cef53f, e5a61a7 and f62ab8d code, never a prototype.

Its report and repro scripts are in the session scratchpad, not in the repo: `review40-findings.md` and
`review40/`. That folder holds:
- `repro/p1_top_crlf_delblank.py` (L1): real install, a CRLF line added on top, the blank line deleted,
  uninstall; it takes a source tree and a text;
- `repro/p0_probe.py` (I2): real install and uninstall of one text and edit list;
- `repro/b1_histories.py`: an independent brute force that also deletes the first or last line.

New ground in this pass: pass 39's `one_cr` change, and the claim that its two end tests were redundant.

The findings of passes 1 to 39 were checked and are not reported again (`research/review-findings-graphify-5a18f22.md` to `-1cef53f.md`).

**Status:** no code defect. One low finding (L1) in docs and tests, and one info item on the docs (I2).
Both are fixed in the next commit on PR #27.

What the reviewer confirmed:
- The pass-39 change only turns `crlf` from true to false, so it cuts fewer bytes. At 6 pieces and 2
  edits it fixes 546 histories and leaves the installer's LF in 559, the chosen trade. It adds no lost byte.
- The claim that v3e's two end tests were redundant holds, by case analysis and by the killed mutants q5 to q7.
- fix36, fix37, fix38 and fix39 mutants are killed, except j9 (equivalent, as recorded). Some old patterns
  no longer match, because f6079da rewrote their line; q1 to q7 cover it.
- Every earlier harness gives the same rows as in pass 39.

Checks run on the fixed tree, all passing:
- pytest on 3.13, on 3.10, and on a real 3.14 (with an 8 MB stack and with an unlimited one);
- keyline, pyflakes and the JSON checks;
- the CRLF copy (`crlf-p41`), with and without `write_text` forced to CRLF, and the forced run in the tree.

## L1 (low, docs and test): a text ending in `\n\r`, a CRLF line added on top, the blank line deleted, loses `\n\r`

**Defect class:** a doc claims more than the code does, and no test pins the reading.

**Evidence:** `a\n\r` is installed, so `joined` is `\n\n`. A line `note` is added at the top with CRLF,
and the blank line above the section is deleted. The bytes above the section are then `note\r\na\n\r\n`,
and uninstall gives `note\r\na`. README line 122 said that a CRLF line added above a text ending in a
bare CR keeps that CR, and that the text's last line break stays when the blank line is deleted. Both
together failed. The code has done this since e5a61a7; f62ab8d left one installer LF.

The bytes read two ways. They are also the text `a` with the same line added, the blank line deleted and
a CRLF blank line typed in its place (3 edits). For that history the head's result is right. This is the
pass-35 rule for a CRLF typed into an LF file, applied to one more shape.

**Code variant measured and rejected:** v4 (scratchpad `fix40/v4.py`) adds, to `one_cr`, a record of
`\n\n` with the file ending in `\n\r\n` but not `\r\n\r\n`. It keeps nothing lost in L1's rows, but over
the pass-39 `cmp_variant.py` histories it fixes 139 and is worse in 5346 at 4 pieces and 3 edits. At 6
pieces and 2 edits it fixes 110 and is worse in 3248; at 3 pieces and 4 edits, 354 against 20340. The
worse rows are a CRLF blank line typed in an LF file, where v4 leaves the installer's LF. That is the
common case, so the head's reading is kept.

**Fixed (docs and test):**
- README line 122 now says the CR is kept unless the blank line was also deleted and the text ends in a
  line break and that CR; those two bytes then go.
- `test_a_crlf_line_added_above_and_the_blank_line_deleted_reads_the_crlf_end_as_typed` pins the reading.
  The head passes it. v4 passed the whole suite before and fails this test, so the mutant kill is the proof.
- The CHANGELOG has a Review 40 line.

**Other hits:** none. `joined` is written only in `config/install.py` (`plan_claude_md`) and read only by
`_rest_without_section`.

## Info

- **I1.** No CI run was triggered for f6079da: the pull request had no check runs, and the latest run was
  on 1cef53f, green on all five jobs. The next push carries the pass-39 tests through CI.
- **I2.** The README understated the `\r\r\n` loss with the blank line deleted. `a\r\n\r\r\n\r` converted
  to LF and with the blank line deleted gives `a\n`: it loses `\r\n\r`, not only the last CR. The README
  sentence now says so.
- **I3.** The pass-39 change is monotone, as above.
- **I4.** The equivalence of the dropped end tests holds, as above.
- **I5.** `a\r\n\n\r\n\n` with `\r\n\r\n` recorded (a CRLF text ending in a bare CR, converted to LF, then a
  CRLF line added on top) loses the CR on every head. The README's general rule already covers it: the
  file still holds a CRLF and the install wrote CRLF.
- **I6, I7, I8.** Mutants, reruns, the CHANGELOG Review 39 line and the 1cef53f record match the code,
  apart from L1 and I2.

## Prevention

When two README clauses each hold, check that they also hold together, on the edit histories that combine
them.
