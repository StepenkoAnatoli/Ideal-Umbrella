# Review of branch graphify-ideas at 2785b94 (2026-10-31, forty-fourth pass)

One fresh-context reviewer did a breaker review of the diff `origin/main...2785b94`, with real-permission runs
of `add_to_repo.py` (another user via `setpriv`) and one mutant tree per clause of the source-rule helpers.

Its report and repro scripts are in the session scratchpad, not in the repo: `review44-findings.md` and
`review44/`. That folder holds:
- `repro/c1_clause_mutants.py` (L1): 16 mutants, one per clause of `_never_fails_to_encode` and
  `_sets_utf8_stdout`, each run against `tests/test_source_rules.py`;
- `repro/l1_learnings_cases.sh`: every learnings case of the merged `add_to_repo.py`, as uid 65534.

New ground in this pass: pass 43's test row, CHANGELOG line and record.

The findings of passes 1 to 43 were checked and are not reported again (`research/review-findings-graphify-5a18f22.md` to `-fe1094d.md`).

**Status:** no code defect (`config/install.py`, `config/uninstall.py`, `config/add_to_repo.py` and
`scripts/ledger.py` are byte-equal to pass 43's). One low (L1): a test gap and a record claim, fixed in the next
commit on PR #27, tests only.

Checks run on the fixed tree, all passing:
- pytest on 3.13, on 3.10, and on a real 3.14 (with an 8 MB stack and with an unlimited one);
- keyline, pyflakes and the JSON checks;
- the CRLF copy (`crlf-p46`), with and without `write_text` forced to CRLF, and the forced run in the tree.

## L1 (low, test): the source rules' helpers had clauses no row pinned, and the fe1094d record said none had

**Defect class:** a test that would not catch a regression; a record claim the tests contradict.

**Evidence:** of the reviewer's 16 mutants, these passed every row of `tests/test_source_rules.py`:
- in `_never_fails_to_encode`: C01 (a chained compare accepted), C02 (any compare operator, read as `!=`), C03
  (any attribute of `os`), C04 (`.name` of any module), C11 (a non-constant, non-conditional value accepted);
- in `_sets_utf8_stdout`, which had no self-test: D01 (no `errors=` check), D02 (any `errors=` value), D03 (no
  `encoding=` check), D04 (any method call). The repo-wide rule fails only when a script also breaks it, and none
  does, so a loosened checker went unseen.

The fe1094d record said each other clause had a failing row. The scripts at head print safely on every OS;
only the rule's guard was weaker than recorded.

**Fixed:**
- `test_the_encode_rule_wants_backslashreplace_on_windows` refuses five more rows: `os.name != "nt" != x`,
  `os.name in "nt"`, `os.sep != "nt"`, `sys.name != "nt"`, and the bare name `ERRORS`.
- New `test_the_utf8_stdout_rule_wants_both_arguments` (8 rows): the full call is accepted; no `errors=`,
  `errors="strict"`, `encoding="cp1252"`, no `encoding=`, `encoding=ENC`, `sys.stdout.write(...)` and a bare
  `reconfigure(...)` are refused.
- Mutant proof: the reviewer's script on the fixed tree (scratchpad `fix44/run1`) kills all 16 mutants,
  C01-C11, S1 and D01-D04. Before the fix C01-C04, C11 and D01-D04 survived.
- The rule-3 docstring now names the `os.name` choice the rule accepts (I5).
- The fe1094d record's Other hits and Prevention lines are corrected.

**Other hits:**
- `_named_handlers` came in with the merge of main and had no self-test either. New
  `test_named_handlers_reads_module_level_tuples` (5 rows). Mutants (scratchpad `fix44/nh_mut.py`): N1 (a list
  accepted), N2 (any nesting level), N3 (only the first of `A = B = ...`) and N4 (any tuple) each fail one row,
  so all four are killed.
- Rule 5's `_isolated` already has its own self-test (`test_rule_five_reads_the_leading_flags`).
- The older helpers `_is_exit`, `_is_text_read`, `_glob_call` and `unchecked_json_reads` are older than this
  branch's merge and were not changed by it. Each is pinned only by the repo-wide rule over the tree. They are
  left as is: outside the PR.

## Info

- **I1.** CI ran on 2785b94 and is green on all five jobs.
- **I2.** Pass 43's row reaches its branch; mutant S1 still fails only that row.
- **I3.** Every learnings case of the merged `add_to_repo.py` (dangling and looped links, `notes` a file, an
  existing or read-only `learnings.md`, a git-ignored `notes/`, a locked target) gives the note the README
  states, exit 0, as uid 65534 on real permissions.
- **I4.** Earlier uninstall harnesses rerun on the head match pass 43's outputs: no lost user byte outside the stated
  exceptions and trades.
- **I5.** README and CHANGELOG lines match the code. The stale rule-3 docstring in `tests/test_source_rules.py`
  (it said no encoding prints a lone surrogate) now says what the rule accepts and why.
- **I6.** `surrogateescape` on POSIX cannot raise in `add_to_repo.py`: every printed string is a path, an OS message,
  a `repr()` or a constant, and `_check_json` refuses a lone surrogate in `settings.json`.

## Prevention

For a self-test of a rule, run one mutant per clause (drop it, or loosen it) and keep a refused row for each one
that survives. Do this for every helper a rule calls, not only the one that changed. A record claims a clause is
pinned only after its mutant was run.
