# Review of branch graphify-ideas at e5a61a7 (2026-10-28, thirty-sixth pass)

One fresh-context reviewer did a breaker review of the diff `origin/main...e5a61a7`. It ran on the
session's default model because the Fable usage limit was reached again.

Its report and repro scripts are in the session scratchpad, not in the repo: `review36b-findings.md` and
`review36b/`. That folder holds:
- `repro/r1_crlf_line_on_bare_cr.py` (L1), `r3_h4_deleted_blank_then_crlf.py` (T1) and
  `r2_crlf_blank_in_lf_file.py` (I3), each taking a source tree;
- `repro/h1_histories.py`: a user text, the installer's separator, then up to two edits or
  conversions; the expected result is the same edits applied to the text alone;
- `repro/equiv_diff.py` and `repro/classify_r1c.py` (a strict classifier of the r1c rows);
- `old/`, a copy of f62ab8d, to compare against the real code before pass 35.

New ground in this pass: the pass-35 rule against the real f62ab8d code, and edit histories.

The findings of passes 1 to 35 were checked and are not reported again (`research/review-findings-graphify-5a18f22.md` to `-f62ab8d.md`).

**Status:** one wrong result in the code (L1, a pass-35 regression) and one test gap (T1), both fixed in
the next commit on PR #27; the pass-35 records corrected.

What the reviewer confirmed:
- CI at e5a61a7 is green on all five jobs, and none of the new tests is skipped on Windows.
- Every earlier harness gives the same rows on e5a61a7 as on the pass-35 prototype; the strict
  classifier accepts all 401 r1c rows.
- `fix35/mut.py` g1-g6, f10, f11 and t1-t10 are killed, also in the CRLF `write_text` copy.

Checks run on the fixed tree, all passing:
- pytest on 3.13, on 3.10, and on a real 3.14 (with an 8 MB stack and with an unlimited one);
- keyline, pyflakes and the JSON checks;
- the CRLF copy, and the suite with `write_text` forced to CRLF, in the tree and in a CRLF copy.

The harnesses `review35b/repro` r1, r1b, r1c, r2, r3, r4, r4b, r5 and r6 and `review36b/repro` r2 and
r3 give the same rows as on e5a61a7 (apart from backup timestamps and run times); `review36b/repro`
r1 goes from 10 bad rows to none.

Mutants are in the session scratchpad, `fix36/mut.py` (j1, j3-j9, h4); all are killed except j9, which is
equivalent.

**Counts:** 0 high, 0 medium, 2 low (L1: code defect; T1: test gap), 3 info (no action).

## Low

### L1. A line added with CRLF above a text ending in a bare CR cost that CR (a pass-35 regression)

**Finding:** take `mine\rmore\r` (no CRLF in it), install (`joined` is `\n\n`), then add `note\r\n` at the
top with a CRLF tool. Uninstall gave `note\r\nmine\rmore`. The CRLF the user added read as a
conversion of the whole file to CRLF, so the text's own CR and the installer's first LF were cut as one
CRLF. f62ab8d got this right with the recorded-bytes branch that pass 35 removed. README line 122 says
your own text stays byte for byte.

The pass-35 record said a brute force showed the count gives the same result as that branch wherever
the branch was right. That was false: `fix35/equiv.py` compared against the reviewer's guarded
prototype, not against f62ab8d. Against f62ab8d, over 262,215 edit histories (6 pieces, 2 edits),
e5a61a7 was right in 376 cases where f62ab8d was wrong, and wrong in 1,392 where f62ab8d was right.

**Fixed (code):** `_rest_without_section` reads a bare CR followed by two LF, with no CRLF just before
it (`own_cr`), as the text's own CR; it does not count as a sign of a conversion. Over the same
histories, the fix is right in 376 cases where f62ab8d is wrong and wrong in 10 where it is right. The
10 are one file shape, `\n\r` with a CRLF line added on top, which a text ending in a bare CR followed by
a CRLF and an LF blank line also gives.

The reviewer's prototype also had `joined == "\n\n"` and excluded `\n\n` before the CR. The first term is
left out: with one break recorded, the first cut is an LF either way (mutant j2 changes no result in
the brute force). The exclusion is `\r\n\n` instead, which is right in 127 more histories, a text ending
in blank lines and a bare CR, and wrong in none. The CRLF in `\r\n\n` is a CRLF blank line the user
added, and reading its CR as the text's would leave half of it (mutant j5).

**Test (failing first):** `test_a_crlf_line_added_above_a_text_ending_in_a_bare_cr_keeps_that_cr`
(`mine\rmore\r` and `a\nb\r`), and `test_a_crlf_blank_line_added_after_a_bare_cr_is_not_split` (kills j5).
Mutants j1 (old rule), j3, j4, j6, j7 and j8 (each term changed) are killed. j9 (`\n\n` for `\r\n\n`) is
equivalent: an LF before the two LF makes both cuts LF either way.

**Other hits:** `joined` is read nowhere else. Install's "ends in a line break" test (`endswith("\n")`) and
the update path's line ends (pass 34) do not read the separator back.

### T1. No test deleted the blank line and then converted the file to CRLF

**Finding:** mutant h4 (`cut.endswith(("\n", "\r"))` in the single-break guard) survived the suite. Take
`a\n`, install (`joined` is `\n`), delete the blank line, turn the file to CRLF, uninstall: the result
must be `a\r\n`, and h4 gave `a\r`.

**Fixed (test):** `test_a_deleted_blank_line_then_a_crlf_conversion_keeps_the_users_line_break` (`a\n` and
`x\ny\n`). h4 is killed.

## Info (no action)

- I1: the reviewer's own mutants over uninstall.py lines 177-201 are all killed except an offset-0
  near-equivalent and two equivalents.
- I2: every harness on e5a61a7 matches the pass-35 prototype; CI and the Windows reach were checked.
- I3: a CRLF blank line just above the section of an LF file keeps the installer's LF breaks (`mine`
  gives `mine\n\n\r\n`). f62ab8d, e5a61a7 and the fix agree; the case is contrived, nothing is lost.

## Prevention

Pass 35's equivalence claim compared against a prototype, so it could not fail where the prototype
and the real code differed. A comparison with older behaviour now runs against a checkout of the
older head (`review36b/old/`), and the next pass's brief asks the reviewer to do the same.
