# Review of branch graphify-ideas at 1cef53f (2026-10-31, thirty-ninth pass)

One fresh-context reviewer did a breaker review of the diff `origin/main...1cef53f`. It compared the head
against the real e5a61a7 and f62ab8d code, never a prototype.

Its report and repro scripts are in the session scratchpad, not in the repo: `review39-findings.md` and
`review39/`. That folder holds:
- `repro/r2_crlf_text_lf_cr_to_lf_delblank.py` (L1): real install, conversion to LF, deleted blank line,
  uninstall; it takes a source tree and an optional variant;
- `repro/q1_histories_of_file.py`: every history up to 5 pieces and 3 edits that gives a given file;
- `repro/z4_classify.py` and `repro/cmp_variant.py`: the brute-force classifier and the variant comparison;
- `var/`: candidate fixes v3, v3b, v3c, v3d and v3e;
- `mut/`: mutants over every changed line of the diff.

New ground in this pass: pass 38's conversion-to-LF rule followed by later edits.

The findings of passes 1 to 38 were checked and are not reported again (`research/review-findings-graphify-5a18f22.md` to `-0bf80b9.md`).

**Status:** one wrong result in the code (L1, there since pass 33, and also in e5a61a7 and f62ab8d),
fixed in the next commit on PR #27, with its docs. Five info items, no action beyond the docs.

What the reviewer confirmed:
- CI at 1cef53f is green on all five jobs, and the pass-38 tests run on Windows (they write bytes).
- All 16 earlier harnesses exit 0. Pass 38's r1 has 0 bad rows.
- The `fix36`, `fix37` and `fix38` mutants are killed, except j9, which is equivalent.
- Of 1611 mutants over every changed line, none on the pass-38 lines survived. Every survivor is in the
  sets triaged in passes 32 to 35.

Checks run on the fixed tree, all passing:
- pytest on 3.13, on 3.10, and on a real 3.14 (with an 8 MB stack and with an unlimited one);
- keyline, pyflakes and the JSON checks;
- the CRLF copy (`crlf-p40`), with and without `write_text` forced to CRLF, and the forced run in the tree.

## L1 (low, two lost user bytes): a CRLF text ending in a line break and a bare CR, converted to LF, then its blank line deleted, lost `\n\r`

**Defect class:** wrong result, bytes of the user's text taken, with no notice.

**Evidence:**
- `a\r\nb\r\n\r` is installed, so `joined` is `\r\n\r\n`. The file is converted to LF, which keeps the
  lone CR, and the blank line above the section is deleted. The bytes above the section are then
  `a\nb\n\r\n`: the text, then the one installer LF left.
- `own_cr` needs a `\r\n\n` tail, so it was false, and `crlf` was true from the record. The cut took
  `\r\n` (the user's CR and the installer's LF) and then the user's own `\n`. The result was `a\nb`.
- The repro had 11 of 18 rows bad on the head, and 16 on e5a61a7 and f62ab8d.

| text | edits after install | head wrote | now |
|---|---|---|---|
| `a\r\n\r` | toLF, delete the blank line | `a` | `a\n\r\n` |
| `a\r\nb\r\n\r` | toLF, delete the blank line | `a\nb` | `a\nb\n\r\n` |
| `one\r\ntwo\r\nthree\r\n\r` | toLF, delete the blank line, `note\n` added on top | `note\none\ntwo\nthree` | `note\none\ntwo\nthree\n\r\n` |
| `a\r\nb\r\n\r\n\r` | toLF, delete the blank line | `a\nb\n` | `a\nb\n\n\r\n` |

The reading is unique: over all texts up to 5 pieces and histories up to 3 edits, the file `a\n\r\n` with
`\r\n\r\n` recorded comes only from the text `a\n\r`.

The README sentence on the CR kept after a conversion to LF, and the Review 38 CHANGELOG line, held only
while the blank line was still there.

**Fixed (code):** `one_cr = joined == "\r\n\r\n"`, and `crlf` takes the `own_cr` branch when either is
true. In that branch `crlf` is `recorded and now`, so the cut stays CRLF while another CRLF is left above
the last two characters. With two CRLF breaks recorded, the text had no final line break, so it is the
only kind that can end in a CR. One CRLF at the end that is the only CRLF left is then read as the text's
CR and the installer's LF. This is the reviewer's v3e. Its two end tests turned out to be redundant (see
the mutants), so the record alone decides.

**The trade, by the reviewer's brute force:**
- v3e fixes 546 histories at 6 pieces and 2 edits, and is worse in 559. At 4 pieces and 3 edits it fixes
  400 and is worse in 790. At 3 pieces and 4 edits it fixes 740 and is worse in 2405.
- The worse rows all have one shape: a CRLF install of a text with no final line break, converted to LF,
  then a CRLF blank line typed above the section. v3e keeps the installer's two LF and the user's CRLF
  blank line there. Nothing of the user's is lost in any of them.
- This is the direction passes 38 and 39 chose: no user byte lost, even if an installer byte is left.
  The fixed rows lose user bytes on the head; the worse rows lose none on v3e.

**Tests (failing first):**
- `test_a_crlf_text_ending_in_a_break_and_a_bare_cr_converted_to_lf_keeps_them_without_the_blank_line`,
  for `a\r\n\r`, `a\r\nb\r\n\r`, and `one\r\ntwo\r\nthree\r\n\r` with `note\n` added on top. All three
  failed before the fix.
- `test_a_crlf_blank_line_typed_after_a_conversion_to_lf_keeps_every_line_break` pins the trade:
  `a\r\nb` is installed, converted to LF, and a CRLF blank line is typed above the section. The result is
  `a\nb\n\n\r\n`.

**Docs:** README line 122 now says the CR is kept also with the blank line then deleted, that one of the
installer's LF may stay, and that a CRLF blank line typed after such a conversion is kept too. It also
names the `\r\r\n` exception (I2). The CHANGELOG has a Review 39 line.

**Other hits:** none. `joined` is written in `config/install.py` (`plan_claude_md`) and read only by
`_rest_without_section`.

**Mutants** (scratchpad `fix39/mut.py` on the v3e form, then `fix39/mut2.py` on the final line):
- On v3e, p4 and p5 survived. Each dropped one of the end tests, `before.endswith("\r\n")` and
  `not before.endswith("\r\n\r\n")`. Both are equivalent: a file ending `\r\n\r\n` holds another CRLF, so
  `now` is true and both branches agree; for a file not ending in `\r\n`, the first cut is one character
  either way, and the second cut differs only when `own_cr` or `now` is true. So both terms were removed.
- p6 (`joined.count("\n") > 1`, v3d) also survived on v3e: with both end tests in place, it fired only on
  files the loop leaves alone. On the final line it is q3, below.
- On the final line, q1 (`one_cr` left out), q2 (`recorded`, v3c), q3 (`joined.count("\n") > 1`, v3d),
  q4 (`True`), q5 and q6 (one side of the conditional changed) and q7 (an end test put back that changes
  results) are killed.
- fix37's k1, k2, k4, k5 and m1 are still killed.
- Pass 38's r1 repro has 0 bad rows on the fixed tree. The r2 repro has only the `\r\r\n` rows bad (I2).

## Info

- **I1.** Pass 38's change works as described, in both directions and with later edits. The head against
  e5a61a7 at 4 pieces and 3 edits differs in 799 histories: pass 37's 663 and pass 38's 136, as recorded.
- **I2.** The `\r\r\n` reading is kept: `a\r\n\r\r\n\r` converted to LF still loses its last CR, since the
  conversion leaves a CRLF. The README and CHANGELOG did not say so; README line 122 now does.
- **I3.** Mutation testing over every changed line found no untriaged survivor (see above).
- **I4.** Rejected candidates, so they are not retried: v3 (`not before.endswith("\n\n")`, worse in 22284
  at 4p3e, 3 tests fail), v3b (no record condition, worse in 9120 at 4p3e, 1 test fails), v3c
  (`recorded`, breaks `test_a_crlf_separator_goes_when_the_lines_above_it_were_rewritten_with_lf`, worse in
  2094 at 4p3e), v3d (`joined.count("\n") > 1`, worse in 6136 at 4p3e).
- **I5.** Reruns, CI and the Windows reach are clean (see above). README line 122 and the CHANGELOG lines
  of Reviews 33 to 38 matched the code apart from L1 and I2.

## Prevention

When a rule handles a file after a conversion, also test it after each edit that can follow: a deleted
blank line, a typed blank line, a line added on top. Pass 38 tested the conversion alone.
