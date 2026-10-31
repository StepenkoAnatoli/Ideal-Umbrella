# Review of branch graphify-ideas at 0bf80b9 (2026-10-31, thirty-eighth pass)

One fresh-context reviewer did a breaker review of the diff `origin/main...0bf80b9`. It compared the head
against the real e5a61a7 and f62ab8d code, never a prototype.

Its report and repro scripts are in the session scratchpad, not in the repo: `review38-findings.md` and
`review38/`. That folder holds:
- `repro/r1_crlf_text_bare_cr_to_lf.py` (L1): real install, conversion to LF, uninstall; it takes a source tree;
- `repro/y1_allwrong.py` and `repro/y2_class.py`: edit histories over `a`, LF, CRLF and CR, with the
  edits toCRLF, toLF, topLF, topCRLF, endLF, endCRLF, delblank, blankLF, blankCRLF and bom;
- `var/v1.py` and `var/v2.py`: candidate fixes;
- `gitprobe/`: what git's line-end settings do to a lone CR.

New ground in this pass: separators recorded with CRLF, and conversions to LF.

The findings of passes 1 to 37 were checked and are not reported again (`research/review-findings-graphify-5a18f22.md` to `-50990a4.md`).

**Status:** one wrong result in the code (L1, there since pass 33) and one test gap (T1), both fixed in
the next commit on PR #27. One record claim corrected (I1).

What the reviewer confirmed:
- CI at 0bf80b9 is green on all five jobs.
- All 15 harnesses of passes 33-37 exit 0, with the same rows as in pass 37.
- The `fix36` and `fix37` mutants are killed, except j9, which is equivalent.
- BOMs, a rerun and an update change nothing here. `joined` is recorded once, and uninstall is its only reader.

Checks run on the fixed tree, all passing:
- pytest on 3.13, on 3.10, and on a real 3.14 (with an 8 MB stack and with an unlimited one);
- keyline, pyflakes and the JSON checks;
- the CRLF copy (`crlf-p39`), with and without `write_text` forced to CRLF, and the forced run in the tree.

## L1 (low, a lost user byte): a CRLF text ending in a bare CR, converted to LF, lost that CR

**Defect class:** wrong result, a byte of the user's text taken.

**Evidence:**
- Install writes the separator with CRLF for a text holding a CRLF. `a\r\nb\r` gives
  `a\r\nb\r\r\n\r\n<section>`, with `joined` `\r\n\r\n`.
- A conversion to LF (dos2unix, or git with `text` or `eol=lf`) keeps a lone CR and gives `a\nb\r\n\n<section>`.
- `own_cr` was true, but `crlf = "\r" in joined or ...` overrode it. So the user's CR went with the
  installer's second LF, and the result was `a\nb`.
- The repro had 8 of 12 rows bad. The bug was in the code since 0b76cb4, and in e5a61a7 and f62ab8d too.

**Fixed (code):** `crlf = (recorded and now) if own_cr else (recorded or now)`, where `recorded` is
`"\r" in joined` and `now` is `"\r\n" in before[:-2]`. A CR that `own_cr` marks as the text's own is
read as the installer's only when the install wrote CRLF and the file still holds a CRLF above. In that
case the file was not converted: the user deleted the blank line and typed one with LF. This is the
reviewer's v2, written as a conditional (the two are the same for both values of `own_cr`).

**The trade, by the reviewer's brute force:**
- v2 changes no result at 6 pieces and 2 edits for the worse.
- At 4 pieces and 3 edits it is worse in 136 histories, and at 3 pieces and 4 edits in 519. In all of
  them the file was converted to LF and then had a CRLF typed into it. Head's result there was accepted
  only by the lenient deleted-blank rule, or left a bare CR among the user's blank lines (the pass-36 I3 class).
- v2 fixes 1530 histories at 4p/3e, 3913 at 6p/2e, and 2009 at 3p/4e.
- The simpler v1 (`(recorded or now) and not own_cr`) fixes more, but costs 1591, 1666 and 3800
  histories at the same depths, mostly leaving the installer's CR. So v2 was chosen.

**Test (failing first):** `test_a_crlf_text_ending_in_a_bare_cr_converted_to_lf_keeps_that_cr`, for
`a\r\nb\r`, `one\r\ntwo\r\nthree\r`, and `a\r\nb\r` with a line added at the top with LF. All three
failed before the fix.

**Other hits:** none. `joined` is written in `config/install.py` (`plan_claude_md`) and read only by
`_rest_without_section`.

**Mutants** (scratchpad `fix38/mut.py`):
- n1 (head's line), n2 (v1), n3, n4, n6 and n7 (one side of the conditional changed) and n5 (`own_cr`
  ignored) are killed.
- fix37's k1, k2, k4, k5 and m1 are still killed.

## T1 (low, test gap): no test pinned either reading with a CRLF-recorded separator

**Defect class:** a test would not catch a regression. v1 and v2 both passed the suite unchanged.

**Fixed (test):** `test_a_crlf_file_with_its_blank_line_replaced_by_an_lf_one_keeps_no_installer_cr` pins
the other reading. `a\r\nb` is installed, the blank line is deleted and an LF one typed, and the result
is `a\r\nb`. It kills n2 (v1). The L1 test kills n1.

## Info

- **I1.** The pass-36 record's "strict classifier accepts all 401 r1c rows" was wrong in part. 79 of the
  175 rows it labelled "lf mergedCR" were not merged: the lone CR survived the conversion, and uninstall
  took it (L1). A note was added to `-e5a61a7.md`, and the README's "one exception" now names the rule
  that decides.
- **I2.** Depth-3 and deeper classes, other texts, a BOM, a rerun and an update show nothing beyond L1 and
  the documented trades. The x1 rerun gives pass 37's tallies exactly.
- **I3.** The reruns, CI and mutants are clean (see above).

## Prevention

When a rule reasons about line-end conversions, check both directions. The pass-36 comment named only
LF to CRLF, while the README claims both.
