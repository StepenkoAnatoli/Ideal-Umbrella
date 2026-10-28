# Review of branch graphify-ideas at 0b76cb4 (2026-10-28, thirty-third pass)

One fresh-context reviewer did a breaker review of the diff `origin/main...0b76cb4`. It ran on the
session's default model because the Fable usage limit was reached again.

Its report and repro scripts are in the session scratchpad, not in the repo: `review33b-findings.md` and
`review33b/`. That folder holds:
- `repro/r1_roundtrip.py`: 841 small CLAUDE.md texts built from {a, LF, CRLF, CR, BOM, space}, each
  installed, optionally changed (none, to CRLF, to LF, the separator line deleted) and uninstalled;
- `repro/r2_lone_cr.sh` (finding A) and `repro/r3_copy_variants.py` (hand copies for README line 70);
- `mut/`: mutation testing over every line the PR changed (1577 mutants; 159 survived per-file runs,
  all equivalent, already triaged in `-42344e5.md`, or killed by the full suite).

New ground in this pass: the install/uninstall round trip over every short text of those characters.

The findings of passes 1 to 32 were checked and are not reported again (`research/review-findings-graphify-5a18f22.md` to `-42344e5.md`).

**Status:** one wrong result in the code (A below), fixed in the next commit on PR #27.

What the reviewer confirmed:
- CI at 0b76cb4 is green on all five jobs; every pass-32 test also runs on Windows except I327 (accepted).
- The pass-32 guard in `_rest_without_section` and README lines 70 and 122 match the code, apart from A.

Checks run on the fixed tree, all passing:
- pytest on 3.13, on 3.10, and on a real 3.14 (with an 8 MB stack and with an unlimited one);
- keyline, pyflakes and the JSON checks;
- the CRLF copy, and the suite with `write_text` forced to CRLF;
- the reviewer's `r1_roundtrip.py`: its output equals the output on the reviewer's own prototype fix.

Mutants are in the session scratchpad, `fix33/mut.py` (d1 to d4), and all of them are killed.

**Counts:** 0 high, 0 medium, 1 low (A: code defect), 2 info (no action).

## Low

### A. A CLAUDE.md ending in a bare CR lost that CR on install then uninstall

**Finding:** with classic Mac line ends (`mine\rmore\r`) the text has no final LF, so install puts two LF
before the section and records them as `joined`. Uninstall counts `joined` back as line breaks and takes
`\r\n` as one break, so after the first LF it read the user's last CR and the second LF as one CRLF and
took both: the file became `mine\rmore`, and the safety backup was kept as differing. README line 122
says your own text stays byte for byte.

**Fixed (code):** `_rest_without_section` takes a two-break `joined` as the bytes recorded when the text
above the section still ends in exactly those bytes, and counts line breaks only otherwise (line endings
changed since the install, or a single break). A file converted to CRLF or LF no longer ends in the
recorded bytes, so it falls through to the count as before.

**Test (failing first):** `test_a_file_ending_in_a_bare_cr_is_given_back_byte_for_byte` (round trip, no
backup left). Mutants d1 (branch dropped), d2 (count term dropped), d3 (`endswith` term dropped) and d4
(one byte too many) are killed.

**Other hits:** `joined` is written only by `install.py` (lines 795 to 804) and read only here.

## Info (no action)

- **B.** `mine\n\n` with the blank line above the section deleted has the same bytes as `mine\n` with
  nothing deleted, so uninstall gives `mine\n`. No rule can tell the two apart; README line 122 says
  which way it goes.
- **C.** README line 70 does not mention a hand copy followed by trailing spaces; it is added as a
  section and round-trips cleanly, as the sentence's rule implies.

## Prevention

The exhaustive round trip over short texts found what 32 passes of targeted review had not. The next
pass reruns `r1_roundtrip.py` on the new head.
