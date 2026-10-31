# Review of branch graphify-ideas at f62ab8d (2026-10-28, thirty-fifth pass)

One fresh-context reviewer did a breaker review of the diff `origin/main...f62ab8d`, and also checked
502c37a's test change. It ran on the session's default model because the Fable usage limit was reached
again.

Its report and repro scripts are in the session scratchpad, not in the repo: `review35b-findings.md` and
`review35b/`. That folder holds:
- `repro/r3_mixed_after_crlf.py`, `r4_more_scenarios.py` (583 texts x 9 scenarios), `r4b_blank_lf.py`,
  `r5_split_crlf.py` and `r6_bad_json_line.py`, each taking a source tree;
- `repro/r1c_all.py`, which prints every round-trip row the pass-34 classifier did not show;
- `mut/`, pass 33's mutant generator rerun over the full diff (1607 mutants).

The findings of passes 1 to 34 were checked and are not reported again (`research/review-findings-graphify-5a18f22.md` to `-b0ee721.md`).

**Status:** two wrong results in the code (L1, L2) and one test gap (T1). All are fixed in the next
commit on PR #27, together with a test gap found while fixing (F1).

What the reviewer confirmed:
- CI at f62ab8d was red only on windows-latest 3.12 (the test fixed in 502c37a), and 502c37a is green on all five jobs.
- 502c37a's change is right: mutants e5-e7 are still killed.
- The 401 round-trip rows the classifier had not shown were classified again, more strictly, and all are accepted cases.

Checks run on the fixed tree, all passing:
- pytest on 3.13, on 3.10, and on a real 3.14 (with an 8 MB stack and with an unlimited one);
- keyline, pyflakes and the JSON checks;
- the CRLF copy, and the suite with `write_text` forced to CRLF, in the tree and in a CRLF copy.

The reviewer's harnesses (r1, r1c, r2, r3, r4, r4b, r5) give the same rows on the fixed tree as on its
prototype `review35b/fix2.diff`, apart from backup timestamps; r3, r4 and r4b have no bad rows.

Mutants are in the session scratchpad, `fix35/mut.py` (g1-g6, f10, f11, t1-t10), and all of them are killed.

**Counts:** 0 high, 0 medium, 3 low (L1 and L2: code defects; T1: test gap), 2 info (no action).

## Low

### L1. A file turned to CRLF after the install and then given a line with LF kept the installer's blank line (a pass-34 regression)

**Finding:** take `mine`, install, turn the whole file to CRLF (git autocrlf, unix2dos), then add `note\n`
at the top with an LF tool. Uninstall gave `note\nmine\r\n\r\n`, where b0ee721 gave `note\nmine`. The
record's `joined` is LF, and pass 34 read CR+LF as one break only when no bare LF was left above. The one
bare LF the user added made each CRLF of the separator read as two breaks, so nothing was cut. README
line 122 says the blank line goes also when the line endings changed since.

**Fixed (code):** `_rest_without_section` reads CR+LF as one break when `joined` holds a CR, or when the
text above holds a CRLF other than its last two characters. A file with no CRLF at install can only have
one if it was converted since. The last two characters are left out because they can be the text's own
bare CR plus the installer's LF (pass 34's case). The old `no bare LF above` term is gone: it could only
decide when the text holds no LF but one final CRLF, and there neither reading cuts anything.

**Test (failing first):** `test_a_line_added_with_lf_above_a_file_turned_to_crlf_leaves_no_separator`
(`mine` and `a\nb\n`).

### L2. The recorded-bytes branch split a CRLF and left a bare CR (present since b0ee721)

**Finding:** take `a`, install (`joined` is `\n\n`), turn the file to CRLF, then add one blank line with an
LF tool just above the section, which leaves `a\r\n\r\n\n`. Its tail is the recorded `\n\n`, so cutting
those bytes left `a\r\n\r`: a bare CR the user never had.

**Fixed (code):** the recorded-bytes branch is removed. A brute-force comparison
(`fix35/equiv.py`, every text up to 10 characters over `a`, CR and LF, times every separator install
writes: 354,292 cases) shows the count, with L1's rule, gives the same result as that branch everywhere
the branch was right. The separator is now always a number of line breaks, as its comment says. Result:
`a\r\n` and `x\r\ny\r\n`.

*Corrected in pass 36 (`-e5a61a7.md` L1):* that comparison was wrong. `fix35/equiv.py` compared the
new code with the reviewer's guarded prototype, not with f62ab8d's branch. Against f62ab8d, over
262,215 edit histories, e5a61a7 was right in 376 cases where f62ab8d was wrong, but wrong in 1,392
where f62ab8d was right: a text ending in a bare CR, with a line added at the top with CRLF, lost
its CR. Pass 36 fixed all but 10 of them (one ambiguous file shape).

**Test (failing first):** `test_a_blank_lf_line_above_the_section_of_a_crlf_file_splits_no_crlf`
(`a` and `x\ny`).

**Other hits:** the `-b0ee721.md` L1 line saying the count loop is the only place that reads line breaks
back missed this branch; the branch no longer exists. `joined` is read nowhere else. Install's update
path (`ours`, pass 34) looks only at the section's own line ends and was checked by the reviewer's
r4 over three kinds of conversion.

### T1. No test gave the transcript scripts a line that is not JSON

**Finding:** the PR changed `except ValueError` to `except (ValueError, RecursionError)` in
toolresult_share, usertext_split and usertext_top. Five mutants survived the full suite: dropping
`ValueError` (a line cut off mid-write in a live transcript is a traceback) and `continue` to `pass` (a
bad line counts the previous line twice, or is a NameError as the first line).

**Fixed (test):** `test_a_line_cut_off_mid_write_is_skipped_and_nothing_is_counted_twice` (all three
scripts): a cut-off line first and after every good line gives the same report as the good lines alone.
Mutants t1-t5 are killed.

**Other hits:** the same per-line readers in unused_tools and usage_breakdown also survived the
`ValueError` mutant (t6, t8). Their tests now include a cut-off line first and after a good one
(`test_a_line_cut_off_mid_write_is_skipped_and_not_counted_twice`, and
`test_non_object_lines_are_skipped`), and t6, t8, t9 and t10 are killed. ledger's reader was already
covered (t7 killed).

## Found while fixing

### F1. No test for a CRLF separator below lines rewritten with LF

**Finding:** with the `no bare LF` term gone, the mutant that drops `"\r" in joined` (f8, then g2)
survived. Take `a\r\n`, install (`joined` is `\r\n`), then rewrite the user's line with an LF tool
(`note\n`). The separator is still one CRLF; without the term it is read as two breaks and stays.

**Test:** `test_a_crlf_separator_goes_when_the_lines_above_it_were_rewritten_with_lf`. g2 is killed.

## Info (no action)

- Mutation testing over the full diff: 1607 mutants. The only survivors left besides T1's are identical
  `return None` rewrites and message variants, which were left out on purpose in passes 32 and 33.
- `fix34/mut.py` e1-e8 were all killed on f62ab8d. The pass-34 tests reach their branches on Windows.

## Prevention

Two rules for reading line breaks back had grown up side by side: the recorded bytes, and the count. Each
fixed one case and broke another. There is now one rule. (The brute-force comparison said to show it
matched the old rule wherever that one was right compared against the wrong code; see L2's correction.) The next pass's brief asks the reviewer
to rerun r3, r4, r4b and r5 next to the earlier round-trip harnesses.
