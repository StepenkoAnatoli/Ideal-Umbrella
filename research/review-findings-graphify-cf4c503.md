# Review of branch graphify-ideas at cf4c503 (2026-10-31, forty-fifth pass)

One fresh-context reviewer did a breaker review of the diff `origin/main...cf4c503`. It ran mutants of the
source-rule helpers and reran the earlier install, uninstall and learnings harnesses, the last as uid 65534.

Its report and repro scripts are in the session scratchpad, not in the repo: `review45-findings.md` and
`review45/`. That folder holds:
- `repro/r3_more_mutants.py`: mutants of `_walk`, `_handles`, `_named_handlers` and the json and stdout rules;
- `repro/r4_walk_nested.py` (L1): what a `_walk` that drops `handled` lets through;
- `repro/r1_row_clauses.py` (L2): the receiver probe of `_sets_utf8_stdout`.

New ground in this pass: pass 44's test rows and self-tests, the rule-3 docstring, the CHANGELOG line and the
records.

The findings of passes 1 to 44 were checked and are not reported again (`research/review-findings-graphify-5a18f22.md` to `-2785b94.md`).

**Status:** no code defect (the code is byte-equal to pass 44's). Two low test gaps (L1, L2), fixed in the next
commit on PR #27, tests only.

Checks run on the fixed tree, all passing:
- pytest on 3.13, on 3.10, and on a real 3.14 (with an 8 MB stack and with an unlimited one);
- keyline, pyflakes and the JSON checks;
- the CRLF copy (`crlf-p47`), with and without `write_text` forced to CRLF, and the forced run in the tree.

## L1 (low, test): `_walk` could drop its set of handled exceptions in a nested `try`

**Defect class:** a test that would not catch a regression.

**Evidence:** the merge of main made `_walk` take `handled` and pass it down three recursive calls. Mutants
E09a (the `try` body walked without `handled`) and E09b (the same for handlers, `else` and `finally`) passed
the whole of `tests/test_source_rules.py`: no script has a json read under an inner `except ValueError` inside
another `try`. With either mutant, the inner body falls back to the decode handlers, where `ValueError` counts.
So `json.load` under `except ValueError`, in the ordinary open-then-parse shape, passed the RecursionError
rule. That is the regression rule 6 exists for.

**Fixed:**
- New `test_walk_keeps_the_handled_set_in_nested_trys`: 3 shapes (an inner `try` in the outer body, handler or
  `finally`) by 3 handler pairs. An inner `ValueError` is never a depth guard. An inner `RecursionError` always
  is. An outer `RecursionError` guards only the outer body.
- Mutants (scratchpad `fix45/mut.py`): E09a fails 2 rows, E09b fails 6, and W1 (handlers walked as guarded)
  fails 2. All three are killed. The reviewer's E09a to E09d, E08, E11 and E12 are all killed on the fixed tree
  (`fix45/r3run2`).

## L2 (low, test and doc): the stdout rule took `.reconfigure` on any object

**Defect class:** a test that would not catch a regression; a docstring and an assertion message that claim
more than the check makes.

**Evidence:** `_sets_utf8_stdout` never looked at what `.reconfigure` was called on. The reason is that three
scripts reconfigure through a loop variable (`for stream in (sys.stdout, sys.stderr)`). So these were all
accepted: `sys.stderr.reconfigure(...)`, `log.reconfigure(...)`, and a script that set up only `sys.stderr`
while printing to stdout. That script would again end in `UnicodeEncodeError` on Windows.

**Fixed:**
- `_sets_utf8_stdout(node, stream=None)` wants the receiver to be `sys.stdout`, or the name `stream`.
- New `_reconfigures_stdout(tree)` accepts a direct call, or a call on the target of a `for` over a tuple or
  list that holds `sys.stdout`, inside that loop's body. The repo-wide rule uses it.
- New `test_the_utf8_stdout_rule_looks_at_the_stream`, with 7 module rows. The argument test also refuses
  `sys.stderr`, `log` and `proc.stdout` receivers.
- Failing first: with the old check, 6 rows failed.
- Mutants (`fix45/mut.py`): R1 (any receiver), R2 (any name), R3 (any loop), R4 (`.stdout` of any object) and
  R5 (any loop name) are all killed.
- The rule-3 docstring and the assertion message name the loop form. The docstring also says the `os.name`
  test goes in that order (the reviewer's I5 nit).

**Other hits:**
- The three loop forms (`config/add_to_repo.py`, `scripts/ledger.py`, `keyline/keyline_hook.py`) all hold
  `sys.stdout` and pass. Every other script calls `sys.stdout.reconfigure` directly.
- Reviewer mutants E07 (a non-Name target in `_named_handlers`), E10 (a bare `except:` not a guard) and E13
  (any `.load` call) still survive. They are tightenings, or raise on odd code instead of accepting it (the
  reviewer's I3). They are left as is.

## Info

- **I1.** CI ran on cf4c503 and is green on all five jobs.
- **I2.** Pass 44's 16 clause mutants and N1 to N4 are still killed, and each new row reaches its clause.
- **I3.** The reviewer's survivors E01 to E03, E07, E10, E13 and E14 are not loosenings (see Other hits).
- **I4.** Earlier harnesses rerun on cf4c503 match pass 44's outputs. `/tmp/claude-0` is mode 0700 now, so the
  uid-65534 run used `unshare -m` with the tree on a tmpfs.
- **I5.** Wording nits in the Review 44 CHANGELOG line ("not a `reconfigure` call", "a nested tuple") are
  reworded.
- **I6, I7.** Every script reconfigures stdout. `_named_handlers` is exercised by `hooks/context_check.py`.

## Prevention

A checker that takes its context as a parameter needs a self-test where that parameter matters at every
recursion. A rule named after an object (`sys.stdout`) must check that object, not only the method name.
