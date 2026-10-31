# Review of branch graphify-ideas at 2735a08 (2026-10-31, forty-first pass)

One fresh-context reviewer did a breaker review of the diff `origin/main...2735a08`. It used real installs and
uninstalls of the head, never a prototype.

Its report and repro scripts are in the session scratchpad, not in the repo: `review41-findings.md` and
`review41/`. That folder holds:
- `repro/w1_real.py`: real install and uninstall of one text, with edits in between (`topCRLF`, `delblank`,
  `toLF`, ...); it takes a source tree and a text;
- `repro/c1_clauses.py`: a model check of each README clause over histories of up to 5 pieces.

New ground in this pass: pass 40's README and CHANGELOG wording and its new test.

The findings of passes 1 to 40 were checked and are not reported again (`research/review-findings-graphify-5a18f22.md` to `-f6079da.md`).

**Status:** no code defect (`config/install.py` and `config/uninstall.py` are byte-equal to f6079da's). Two low
findings (L1, L2) and one info item (I2) in the docs; all three are fixed in the next commit on PR #27, with tests.

Checks run on the fixed tree, all passing:
- pytest on 3.13, on 3.10, and on a real 3.14 (with an 8 MB stack and with an unlimited one);
- keyline, pyflakes and the JSON checks;
- the CRLF copy, with and without `write_text` forced to CRLF, and the forced run in the tree.

## L1 (low, docs): the Review 40 loss holds only for a text with LF line ends

**Defect class:** a doc claims more than the code does.

**Evidence:** README line 122 said a text ending in a line break and a bare CR, with a CRLF line added above and
the blank line deleted, loses those two bytes. That holds for `a\n\r` (record `\n\n`, result `note\r\na`). It
fails for `a\r\n\r`, `x\r\ny\n\r` and `x\r\ny\r\n\r`: the install wrote CRLF (record `\r\n\r\n`), and uninstall
gives `note\r\na\r\n\r\r\n`. Nothing is lost; one installer CRLF is left. The model check found the same split for
every text of up to 5 pieces. The CHANGELOG Review 40 line had the same wording.

**Fixed (docs and test):**
- README: "a text with LF line ends ends in a line break and that CR ... (a text the install wrote with CRLF keeps
  them, with one of the installer's CRLF left)"; the CHANGELOG Review 40 line says "a text with LF line ends".
- `test_a_crlf_text_with_a_crlf_line_added_above_and_the_blank_line_deleted_keeps_its_end` pins the CRLF half.
  Mutant T1 (`$SP/fix41/mut.py`: a record of `\r\n\r\n` and a file ending `\r\n\r\r\n` cut as the LF reading)
  passes the rest of `tests/test_uninstall.py` and fails this test (and one L2 row).

## L2 (low, docs): what a CR CR LF text loses with the blank line deleted

**Defect class:** a doc claims more and less than the code does.

**Evidence:** README said such a text, converted to LF, loses its last CR, "(with the blank line then deleted,
also the line break before that CR)". With the blank line deleted:
- `a\r\n\r\r\n\r` gives `a\n` and `a\r\r\n\r\n\r` gives `a\r\n`: the line break and the CR go, as written;
- `a\r\r\nb\r` gives `a\r\nb\r\n` and `a\r\r\n\r\r` gives `a\r\n\r\r\n`: the CR stays, with one installer LF left.
  The cut loop stops at the first byte that is not an LF, so nothing is cut.

**Fixed (docs and test):**
- README: "with the blank line then deleted it also loses the line break before that CR when the text ends in a line
  break and that CR, and keeps the CR (with one of the installer's LF left) when it does not".
- `test_a_cr_cr_lf_text_converted_to_lf_with_the_blank_line_deleted` pins the four rows. Mutant T3 (on a stopped
  cut, a `\r\n\r\n` record with CR CR LF in the file still takes the cut) passes the rest of the uninstall tests and
  fails 2 rows.

**Other hits:** none. `joined` is written only in `config/install.py` and read only by `_rest_without_section`.

## Info

- **I1.** No CI run was triggered for f6079da or 2735a08. The cause was a merge conflict with main (PR #26):
  GitHub does not run `pull_request` workflows while the PR cannot be merged. The merge commit 379d00c was green on
  all five jobs (Ubuntu 3.10, 3.12, 3.13, 3.14 and Windows 3.12), so the pass-39 and pass-40 tests have now run on
  Windows.
- **I2.** `\r` and `\n\r` with a CRLF line added above lose the CR (`note\r\n` and `note\r\n\n`), against the
  README's "keeps that CR". This is pass 36's recorded trade: the bytes are also `note` with CRLF blank lines typed.
  **Fixed (docs and test):** the README sentence has the parenthetical "(a text that is only that CR, or a line
  break and that CR, reads as blank lines you typed and loses it)", and
  `test_a_text_that_is_only_a_bare_cr_reads_as_blank_lines_under_a_crlf_line_added_above` pins both. Mutant T6 (keep
  the CR when only `note` and line breaks are above the section) passes the rest of the uninstall tests and fails
  both rows.
- **I3 to I6.** The pass-40 numbers (v4: 139/5346 at 4p3e, 110/3248 at 6p2e, 354/20340 at 3p4e), the pass-40 test's
  kill proof, the q1 to q7 mutants and every earlier harness match the record. No other README clause has a lost
  byte outside the stated exceptions and trades.

## Mutants that did not prove the new tests

Mutants A to I, M and N in `$SP/fix41/mut.py` (looser forms of `crlf`, `one_cr`, `own_cr` and the cut loop) are all
killed by the rest of the suite or change no new-test result, so they prove nothing about the new tests. T1, T3 and
T6 are the proofs above.

Mutant H (cut a CRLF when the record is `\r\n\r\n` and the file ends in `\r\n\r\n`) survives every test and is
equivalent: there `recorded` and `now` are both true, so `crlf` is already true in both branches.

## Prevention

When a doc sentence states a loss, name the record (LF or CRLF install) and the shape before the last CR; the same
bytes on a CRLF install often read the other way.
