# Review of branch graphify-ideas at fe1094d (2026-10-31, forty-third pass)

One fresh-context reviewer did a breaker review of the diff `origin/main...fe1094d`. It ran real installs on
locked folders (another user via `setpriv`) and mutant trees.

Its report and repro scripts are in the session scratchpad, not in the repo: `review43-findings.md` and
`review43/`. That folder holds:
- `repro/s1_mutant.sh` (L1): the loosened rule with `errors="strict"` on POSIX;
- `repro/r2_notes_dir_locked.sh`: `notes` as a real folder only root may search, with and without a
  `learnings.md`.

New ground in this pass: pass 42's source rule, the `notes` look in `config/add_to_repo.py`, and the README
and CHANGELOG lines.

The findings of passes 1 to 42 were checked and are not reported again (`research/review-findings-graphify-5a18f22.md` to `-881e367.md`).

**Status:** no code defect. One low test gap (L1), fixed in the next commit on PR #27.

Checks run on the fixed tree, all passing:
- pytest on 3.13, on 3.10, and on a real 3.14 (with an 8 MB stack and with an unlimited one);
- keyline, pyflakes and the JSON checks;
- the CRLF copy (`crlf-p45`), with and without `write_text` forced to CRLF, and the forced run in the tree.

## L1 (low, test gap): the rule's own test never checked the non-Windows branch

**Defect class:** a test that would not catch a regression.

**Evidence:** `test_the_encode_rule_wants_backslashreplace_on_windows` had no row with a value other than
`backslashreplace` or `surrogateescape` on the non-Windows branch. A rule that dropped the check on that branch
passed all its rows. With `errors="strict"` there, a POSIX print of a file name that is not UTF-8 would end in
a traceback.

**Fixed:**
- The row `"strict" if os.name != "nt" else "backslashreplace"` must be refused.
- Mutant S1 (scratchpad `fix43/mut.py`) drops the non-Windows check. It passes the rest of the suite and fails
  only the new row, so it is killed.

**Other hits:** none. Each other clause of the rule has a row that fails when that clause is dropped
(pass 42's R2 and R3).

## Info

- **I1.** CI ran on fe1094d and is green on all five jobs.
- **I2.** Pass 42's L3 fix holds with real permissions, as well as under `refuse_looks_inside`:
  - a locked `notes` link gives "cannot look at …/notes (Permission denied)", with exit 0;
  - a locked `notes` folder gives "cannot look at …/notes/learnings.md", with exit 0.
- **I3.** Every earlier learnings case behaves and is reported as before: a dangling link, a link loop, `notes`
  as a file, an existing file kept, and a `notes/` that git ignores.
- **I4.** Mutants N3 and N7 on the pass-42 block are equivalent: they drop the `_look(p) is not None` guard, or
  drop `follow=True` on the second look.
- **I5.** README lines 99 and 137 and the CHANGELOG Review 42 line match the code.
- **I6 to I8.** Every earlier harness rerun matches its record.

## Prevention

A self-test of a rule needs one refused row per clause: drop any one clause, and some row must fail.
