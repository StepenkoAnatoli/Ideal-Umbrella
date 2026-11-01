# Review of branch graphify-ideas at 9029b94 (2026-10-31, forty-seventh pass)

One fresh-context reviewer did a breaker review of the diff `origin/main...9029b94`. It ran mutants of the
source-rule helpers and reran pass 33's round trip and pass 44's learnings cases, the latter as uid 65534 under
`unshare -m` on a tmpfs.

Its report and repro scripts are in the session scratchpad, not in the repo: `review47-findings.md` and
`review47/`. That folder holds:
- `repro/c3_more_mutants.py`: twelve mutants (D1-D12) of `_reconfigures_stdout`, `_walk` and the json rule;
- `repro/c4_shapes_let_through.py`: the shapes D2 lets through and the head refuses;
- `repro/c1_i6_count.py` and `repro/c2_reconfigure_placement.py`: the record counts (I3, I4).

New ground in this pass: pass 46's two test rows, the fourth nested-try shape, the Review 46 CHANGELOG line,
the 7f8ff92 record and the corrected count in the cf4c503 record.

The findings of passes 1 to 46 were checked and are not reported again (`research/review-findings-graphify-5a18f22.md` to `-7f8ff92.md`).

**Status:** no code defect. The production code is byte-equal to fe1094d. One low test gap (L1), fixed in the
next commit on PR #27, tests only.

Checks run on the fixed tree, all passing:
- pytest on 3.13, on 3.10, and on a real 3.14 (with an 8 MB stack and with an unlimited one);
- keyline, pyflakes and the JSON checks;
- the CRLF copy (`crlf-p49`), with and without `write_text` forced to CRLF, and the forced run in the tree.

## L1 (low, test): the loop form's iterable and receiver clauses were not pinned

**Defect class:** a test that would not catch a regression (pass 46's L1 class: a clause of the rule's own
checker that no row pins).

**Evidence:** `_reconfigures_stdout` accepts the loop form only when the iterable is a tuple or list literal
holding `sys.stdout`, and only for a call on the loop's bare name. Every refused row used a literal iterable and
a bare-name or other-name receiver. So mutant D2 (a loop over anything that is not a literal accepted without a
look) and D11 (`proc.stream.reconfigure(...)` counted as the loop's name) passed every test. Under D2,
`LOGS = (sys.stderr,)` then `for s in LOGS: s.reconfigure(...)` passes rule 3 while stdout is left on the ANSI
code page.

**Fixed:**
- Three refused rows (and a fourth, see Other hits) in `test_the_utf8_stdout_rule_looks_at_the_stream`: a loop over a module name holding the
  streams, a loop over a call, and `proc.stream.reconfigure(...)` inside the loop. One per clause, as the
  reviewer's Prevention line asks (the call row is the name row's twin; it costs one line).
- Mutants (the reviewer's `c3_more_mutants.py`, run in scratchpad `fix47/c3`): D2 fails 2 rows, D11 fails 1;
  D1-D12 are all killed. Pass 46's `m1_rule_mutants.py` (`fix47/m1`) and pass 45's `fix45/mut.py`
  (`fix47/f45`) stay killed except the triaged A5 (equivalent), A6 (I9) and B6 (a tightening).
- Failing first does not apply: the code was right; the mutant kills are the proof.

**Other hits:** the loop form's remaining clauses are now each pinned: the target must be a name (a fourth row, a tuple
target, pins it: a mutant that drops the check raises on `.id`, checked in scratchpad `fix47/t1`), the body is the only scope (pass 46), the receiver is
the bare loop name (this pass), the iterable is a literal holding `sys.stdout` (passes 45 and 47). The three loops
in the tree iterate a literal tuple holding `sys.stdout`.

## Info

- **I1.** CI ran on 9029b94 and is green on all five jobs.
- **I2.** Pass 46's rows and shape reach their branches; D12 (the self-test expecting the `else` region guarded)
  is killed by exactly the `else` row, and that matches Python.
- **I3.** Two numbers in the 7f8ff92 record were off: E09b went from 6 to 9 failing rows, not one more; 18
  printing scripts reconfigure stdout, 15 directly and 3 in a loop, not 14 direct calls. Corrected there.
- **I4.** The cf4c503 record's "7" holds for the tree it describes; at 9029b94 the old check fails 9 rows. The
  record is a snapshot, left as is.
- **I5.** Rule 3 says "first" and the checker does not check order. The only script that prints before its
  reconfigure is `keyline/keyline_hook.py --print-config`, which prints ASCII-only JSON. Not changed.
- **I6.** `except*` (`ast.TryStar`) is walked as unguarded: a tightening, unused in the tree, absent on 3.10.
- **I7.** Pass 33's round trip and pass 44's learnings cases give the same outputs as pass 46.
- **I8.** README and CHANGELOG claims match the code.
- **I9.** The repo-wide wiring of each rule stays unpinned by design (A6).

## Prevention

A rule with a clause on the kind of an AST node (a literal iterable, a Name target, a Name receiver) needs one
refused row per clause where that node is of another kind.
