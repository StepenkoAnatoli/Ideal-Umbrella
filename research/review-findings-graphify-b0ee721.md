# Review of branch graphify-ideas at b0ee721 (2026-10-28, thirty-fourth pass)

One fresh-context reviewer did a breaker review of the diff `origin/main...b0ee721`. It ran on the
session's default model because the Fable usage limit was reached again.

Its report and repro scripts are in the session scratchpad, not in the repo: `review34b-findings.md` and
`review34b/`. That folder holds:
- `repro/r1b_reclass.py`: pass 33's round trip with its classifier fixed (it hid the L1 rows);
- `repro/r2_extended.py`: 1635 texts of {a, LF, CRLF, CR} up to length 5 (plus BOM and trailing-space
  variants), each in 8 scenarios (install twice, uninstall twice, text after the section, a rules
  update, a failed write in install or uninstall and a rerun, a BOM added, CRLF and an update): 13080 runs;
- `repro/r3_cr_update.py` (I1) and `repro/r4_cr_deleted_blank.py` (L1);
- `mut/`: AST mutants over every line the PR changed in `config/uninstall.py` (386; the 18 survivors
  are the ones triaged in passes 32 and 33) and hand mutants of the pass-33 branch.

New ground in this pass: the pass-33 branch, and the round trip in reruns, updates and failed writes.

The findings of passes 1 to 33 were checked and are not reported again (`research/review-findings-graphify-5a18f22.md` to `-0b76cb4.md`).

**Status:** one wrong result in the code (L1), one test gap (T1) and one line-ending slip on update (I1),
all fixed in the next commit on PR #27; the record of pass 33 corrected (I2).

What the reviewer confirmed:
- CI at b0ee721 is green on all five jobs.
- The pass-33 branch takes nothing the count did not take, except the user's own CR it was made for.
- The extended round trip gives no wrong bytes, no marker left and no exception; its only rows are
  backups kept because the user changed the bytes (documented).

Checks run on the fixed tree, all passing:
- pytest on 3.13, on 3.10, and on a real 3.14 (with an 8 MB stack and with an unlimited one);
- keyline, pyflakes and the JSON checks;
- the CRLF copy, and the suite with `write_text` forced to CRLF;
- the reviewer's `r1b_reclass.py` (same output as on its prototype fix: the 19 L1 rows gone, none new),
  `r2_extended.py` (same rows as on the prototype, apart from backup timestamps), `r3` and `r4`.

Mutants are in the session scratchpad, `fix34/mut.py` (e1 to e8), and all of them are killed.

**Counts:** 0 high, 0 medium, 2 low (L1: code defect; T1: test gap), 2 info (I1: fixed; I2: record).

## Low

### L1. A text ending in LF and a bare CR lost two of its bytes when the blank line above the section was deleted

**Finding:** `rules\nmine\n\r` has no final LF, so install puts `\n\n` before the section. With one of
them deleted, `...\n\r\n` is left; uninstall counted the user's CR and the installer's LF as one CRLF
and then took the user's own LF: the file became `rules\nmine`. README line 122 says the line break your
text ended with stays.

**Fixed (code):** `_rest_without_section` reads a CR before an LF as half of a CRLF only when the file can
have been turned to CRLF since: `joined` holds a CR (the file had CRLF at install), or no bare LF is left
above the section. Otherwise each LF is one break, and the user's CR stays, with one LF of the
installer's after it (as for `mine` with the blank line deleted).

**Test (failing first):** `test_a_deleted_blank_line_after_a_bare_cr_costs_none_of_the_users_text`
(`rules\nmine\n\r` and `mine\n\n\r`). Mutants e1 (always CRLF), e2 (the `joined` term dropped), e3 (the
bare-LF term dropped) and e4 (the guard dropped from the cut) are killed.

**Other hits:** the count loop is the only place that reads line breaks back; install decides "ends in a
line break" by `endswith("\n")`, which the fixed rule now matches for files that never had a CRLF.

### T1. No test round-tripped an unconverted CRLF file without a final line break

**Finding:** mutant `before[:-len(joined)]` to `before[:-2]` survived the full suite.

**Fixed (test):** `test_a_file_ending_in_a_bare_cr_is_given_back_byte_for_byte` now also runs `mine`,
`first\r\nmine`, `a\r\nb\r` and `a\nb\r\n` (the last one kills e2). Mutant e8 is killed.

## Info

### I1. A rules update wrote the section with CRLF into an LF or CR-only file ending in a bare CR (fixed)

**Finding:** the user's CR and the LF install put after it make a CRLF at the join, so the next update
chose CRLF for the whole file and rewrote the section with CRLF. Uninstall still round-tripped; README
line 70 says line endings are kept.

**Fixed (code):** `plan_claude_md` takes the line ends of the section it replaces, not of the whole file.

**Test (failing first):** `test_a_rules_update_keeps_the_line_ends_of_the_section` (`mine\rmore\r` and
`rules\nmine\r`). Mutants e5 (old rule), e6 (whole file) and e7 (the file up to the section's end) are
killed.

**Other hits:** the wrap and append paths have no section to take line ends from; they keep the file's.

### I2. The pass-33 record's "Other hits" missed two lines

`-0b76cb4.md` now names every line of install.py that sets `joined` (721, 754, 795, 803).

## Prevention

The pass-33 harness filed the L1 rows under a class it did not print. A classifier that hides rows is
a test that cannot fail: the next pass prints every row its classifier does not mark as accepted.
