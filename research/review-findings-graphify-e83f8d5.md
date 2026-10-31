# Review of branch graphify-ideas at e83f8d5 (2026-10-31, forty-eighth pass)

One fresh-context reviewer did a breaker review of the diff `origin/main...e83f8d5`. It ran mutants of the
stdout rule's loop form and reran pass 33's round trip and pass 44's learnings cases, the latter as uid 65534
under `unshare -m` on a tmpfs.

Its report and repro scripts are in the session scratchpad, not in the repo: `review48-findings.md` and
`review48/`. That folder holds:
- `repro/t1_row_mutants.py`: twelve mutants (T1-T12) of `_reconfigures_stdout` and `_sets_utf8_stdout`;
- `repro/t2_shapes.py`: what T4, T5 and T11 accept and the head refuses.

New ground in this pass: pass 47's four test rows, the Review 47 CHANGELOG line, the 9029b94 record and the
corrected counts in the 7f8ff92 record.

The findings of passes 1 to 47 were checked and are not reported again (`research/review-findings-graphify-5a18f22.md` to `-9029b94.md`).

**Status:** no code defect. The production code is byte-equal to fe1094d. One low (L1, docs), fixed in the next
commit on PR #27 with two test rows and a reworded CHANGELOG line.

Checks run on the fixed tree, all passing:
- pytest on 3.13, on 3.10, and on a real 3.14 (with an 8 MB stack and with an unlimited one);
- keyline, pyflakes and the JSON checks;
- the CRLF copy (`crlf-p50`), with and without `write_text` forced to CRLF, and the forced run in the tree.

## L1 (low, docs): the Review 47 CHANGELOG line named a refused shape that no row held

**Defect class:** docs that claim more than the tests pin.

**Evidence:** the Review 47 line said the self-test refuses "`.reconfigure(...)` on an attribute of the loop's
name", that is `stream.buffer.reconfigure(...)`. The row pass 47 added is `proc.stream.reconfigure(...)`, an
attribute named like the loop's name on another object. The head refuses both, but mutant T4 (an attribute of
the loop's name accepted) passed every test. The line also left out the tuple-target row.

**Fixed:**
- Two refused rows in `test_the_utf8_stdout_rule_looks_at_the_stream`: `stream.buffer.reconfigure(...)` inside
  the loop (kills T4), and `proc.stdout.reconfigure(...)` inside the loop (kills T11, the loop-form twin of the
  argument test's `proc.stdout` row; the reviewer called it contrived, one row pins it).
- The Review 47 CHANGELOG line now names the tuple target and every refused receiver (`proc.stream`,
  `stream.buffer`, `proc.stdout`), quoting the rows rather than paraphrasing them.
- Mutants (`t1_row_mutants.py`, run in scratchpad `fix48/t1b`): T1, T3, T4, T6, T8-T11 killed. T5 (only the
  literal's first element looked at) is a tightening; T2, T7 and T12 are equivalent (a safe read of a tuple
  target or a non-literal iterable still finds no stream; `async for` is not used).
- Failing first does not apply: the code was right; the mutant kills are the proof.

**Other hits:** the other CHANGELOG lines of passes 44 to 47 were checked against their rows: each names a shape
a row holds.

## Info

- **I1.** CI ran on e83f8d5 and is green on all five jobs.
- **I2.** Pass 47's rows reach their branches: D2 fails the two iterable rows, D11 the `proc.stream` row, T1 and
  T3 the tuple-target row. Pass 46's and 45's mutants are as recorded.
- **I3.** The survivors T2, T5, T7 and T12 are triaged above.
- **I4, I5.** The record counts hold: 18 printing scripts (15 direct, 3 loops); E09b 9 rows, W1 3.
- **I6.** Pass 33's round trip and pass 44's learnings cases give the same outputs as pass 47.
- **I7.** The rest of the Review 47 line, the record and the progress file match the code.
- **I8.** Rule 3's "first" is still not checked; unchanged (pass 47 I5).

## Prevention

A CHANGELOG line about what a self-test refuses quotes the row's shape, not a paraphrase.
