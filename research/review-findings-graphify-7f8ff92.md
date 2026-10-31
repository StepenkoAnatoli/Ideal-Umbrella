# Review of branch graphify-ideas at 7f8ff92 (2026-10-31, forty-sixth pass)

One fresh-context reviewer did a breaker review of the diff `origin/main...7f8ff92`. It ran mutants of pass 45's
helpers and reran the earlier install, uninstall and learnings harnesses, the last as uid 65534 under
`unshare -m` on a tmpfs.

Its report and repro scripts are in the session scratchpad, not in the repo: `review46b-findings.md` and
`review46b/`. That folder holds:
- `repro/m1_rule_mutants.py`: mutants of `_reconfigures_stdout` (A1-A6), `_walk` (B1-B6) and C1;
- `repro/m2_shapes_let_through.py`: the shapes mutants A1, A2 and B1 let through and the head refuses;
- `repro/r3_more_mutants_p46.py`: pass 45's reviewer mutants with the two stale anchors skipped.

New ground in this pass: pass 45's stdout-rule receiver check (`_reconfigures_stdout`), the `_walk` nested-try
self-test, the CHANGELOG lines and the records.

The findings of passes 1 to 45 were checked and are not reported again (`research/review-findings-graphify-5a18f22.md` to `-cf4c503.md`).

**Status:** no code defect. The production code (`config/`, `scripts/`, `hooks/`, `keyline/`) is byte-equal to
fe1094d. Two low test gaps (L1, L2), fixed in the next commit on PR #27, tests only.

Checks run on the fixed tree, all passing:
- pytest on 3.13, on 3.10, and on a real 3.14 (with an 8 MB stack and with an unlimited one);
- keyline, pyflakes and the JSON checks;
- the CRLF copy (`crlf-p48`), with and without `write_text` forced to CRLF, and the forced run in the tree.

## L1 (low, test): the stdout rule's loop form was not pinned to the loop's body

**Defect class:** a test that would not catch a regression.

**Evidence:** `_reconfigures_stdout` accepts `.reconfigure(...)` on a loop's name only inside the loop's body.
The refused rows used another name (`log`, `other`), so mutants A1 (the loop's name accepted anywhere in the
module) and A2 (the loop's `else:` block counted as its body) passed every test. A one-line dedent of the call
out of `for stream in (sys.stdout, sys.stderr):` reconfigures only `sys.stderr`, the loop's last value; a script
that prints to stdout then fails on Windows again. That is the regression pass 45's L2 closed.

**Fixed:**
- Two refused rows in `test_the_utf8_stdout_rule_looks_at_the_stream`: the call on the loop's name after the
  loop, and in a `for/else` block.
- Mutants (the reviewer's `m1_rule_mutants.py`, run in scratchpad `fix46/run1`): A1 fails 2 rows, A2 fails 1.
  Both are killed. A3 and A4 stay killed; pass 45's `fix45/mut.py` (E09a, E09b, W1, R1-R5) stays killed
  (`fix46/run45`).
- Failing first does not apply: the code was right; the mutant kills are the proof.

**Other hits:** the three loop forms (`config/add_to_repo.py`, `scripts/ledger.py`, `keyline/keyline_hook.py`)
reconfigure inside the loop body and pass.

## L2 (low, test): the `_walk` nested-try self-test left out a `try`'s `else:` block

**Defect class:** a test that would not catch a regression.

**Evidence:** `_walk` walks a `try`'s `else:` block with the outer `guarded` (an `except RecursionError` does not
cover it), which is right. The self-test's three shapes nest the inner `try` in the outer body, handler or
`finally`, so mutant B1 (`orelse` walked as guarded) passed every test. Under B1 a `json.loads` in an `else:`
block, where the outer `except RecursionError` does not reach, would pass rule 6.

**Fixed:**
- A fourth shape `_INNER_TRY_IN_ELSE` in `test_walk_keeps_the_handled_set_in_nested_trys` (id `else`), now
  12 rows. With the outer `RecursionError` and the inner `ValueError` it expects unguarded.
- Mutant B1 fails the new `else` row and is killed. W1 now fails one more row (2 to 3), E09b three more
  (6 to 9: every `else` row; corrected in pass 47, I3).

**Other hits:** all four regions of a `try` (body, handlers, `else`, `finally`) are now covered. No script at
head reads JSON in an `else:` block.

## Info

- **I1.** CI ran on 7f8ff92 and is green on all five jobs.
- **I2.** Pass 45's mutants stay dead. The reviewer's A5 (a set literal accepted as the loop's iterable) is
  equivalent in effect, B6 (a bare `except:` no longer a guard) is a tightening, and A6 is I5.
- **I3, I4.** Earlier uninstall and learnings harnesses rerun on 7f8ff92 match pass 45's outputs.
- **I5.** The repo-wide wiring of each rule (for example A6, the stdout check turned off) is unpinned by design:
  those rules fail only when a script breaks them. Not changed.
- **I6.** The cf4c503 record said "with the old check, 6 rows failed". That was right when it was written; the
  `proc.stdout` row added afterwards also fails, so 7. Corrected there.
- **I7, I8.** README, CHANGELOG and docstring claims match the code; every script reconfigures stdout (18
  printing scripts: 15 direct calls, 3 loops with the call in the body; corrected in pass 47, I3).

## Prevention

A rule that accepts a name only in a scope needs a refused row with that same name outside the scope. A
self-test over the regions of a statement covers every region, not only the ones the bug was found in.
