# Review of branch graphify-ideas at 416b1a8 (2026-10-31, forty-ninth pass)

One fresh-context reviewer did a breaker review of the diff `origin/main...416b1a8`. Its report and repro
scripts are in the session scratchpad, not in the repo: `review49-findings.md` and `review49/`
(`repro/p1_wiring_mutants.py`, `repro/s1_shapes.py`, and reruns of passes 45, 47 and 48's mutants).

New ground in this pass: pass 48's two test rows, the reworded Review 47 CHANGELOG line, the Review 48 line and
the e83f8d5 record.

**Status: clean.** High 0, medium 0, low 0, info 9. The production code is byte-equal to fe1094d. This pass ends
the review loop.

## Info

- **I1.** CI on 416b1a8 is green on all five jobs; locally 1290 passed on 3.13, the source rules pass on 3.10 and
  3.14, the CRLF copy and the forced-CRLF runs are green, and pyflakes, keyline and the JSON checks are clean.
- **I2.** The two new rows kill exactly T4 and T11; T2, T5, T7 and T12 survive as triaged; D1-D12 and pass 45's
  mutants are all killed.
- **I3.** The record counts hold (18 printing scripts: 15 direct, 3 loops; E09b 9 rows, W1 3).
- **I4.** Each CHANGELOG line of passes 47 and 48 names shapes that rows hold.
- **I5.** Pass 33's round trip and pass 44's learnings cases give the same outputs as pass 48.
- **I6.** `_prints_to_stdout` (byte-equal to main) and rule 3's wiring are unpinned: seven wiring mutants survive.
  This is the by-design gap passes 46 (I5) and 47 (I9) recorded; `_prints_to_stdout` joins pass 44's list of older
  helpers left as is.
- **I7.** Wording: the Review 47 line said "on anything but the loop's bare name", which read literally includes
  `sys.stdout.reconfigure(...)` inside the loop (accepted). Reworded with the reviewer's text: "on any other
  receiver inside the loop". Docs only.
- **I8.** Other shapes probed (a set literal, a starred element, a rebound name, a nested tuple, an inner loop, a
  comprehension) behave as the rule intends.
- **I9.** Rule 3's "first" is still not checked (pass 47 I5); unchanged.
