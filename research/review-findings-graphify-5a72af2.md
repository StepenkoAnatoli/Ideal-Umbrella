# Review of branch graphify-ideas at 5a72af2 (2026-10-27, thirty-first pass)

One fresh-context reviewer did a breaker review of the diff `origin/main...5a72af2`. It ran on the
session's default model because the Fable usage limit was reached again.

Its report and repro scripts are in the session scratchpad, not in the repo: `review31b-findings.md` and
`review31b/`. That folder holds:
- `repro/r1_claims.py` (output in `r1.out`), which takes a source tree;
- `mut/mutate.py`: mutants a01-a09, b01-b06 and c01-c08;
- `fuzz/`: re-runs of the settings, record and CLAUDE.md fuzzers;
- the CI job logs at 5a72af2.

New ground in this pass: the pass-30 changes (tests for the link rules kept from main, `-rs` in
`pytest.ini`).

The findings of passes 1 to 30 were checked and are not reported again (`research/review-findings-graphify-5a18f22.md` to `-5eff3be.md`).

**Status:** no code defect. All findings are fixed in the next commit on PR #27.

What the reviewer confirmed:
- CI at 5a72af2 is green on all five jobs. On Windows 1052 passed and 30 skipped, and its `-rs` list shows that both pass-30 link tests ran.
- The pass-30 tests reach their branches.
- The fuzzers came back clean.
- The suite also passes as a non-root user and on 3.10 and 3.14.

Checks run on the fixed tree, all passing:
- pytest on 3.13, on 3.10, and on a real 3.14.6 (with an 8 MB stack and with an unlimited one);
- keyline, pyflakes and the JSON checks;
- the CRLF copy, and the suite with `write_text` forced to CRLF.

Mutants are in the session scratchpad, `fix31/mut.py`, and all of them are killed:
- b05 (the reviewer's survivor: the "no .jsonl files" check dropped);
- s1 (a missing folder read as an empty one);
- s2 (subfolders read).

**Counts:** 0 high, 0 medium, 1 low (L1: test gap), 2 info (fixed: 1, no action: 1).

## Low

### L1. usage_breakdown's "no transcripts" error was not pinned

**Finding:** README line 149 says usage_breakdown exits with an error for a folder that holds no
transcripts. The PR moved that check into `main`'s new `try`. Mutant b05 drops the check and survives the
suite: the script then prints a zero report and exits 0.

**Fixed (test):** `test_a_folder_without_transcripts_is_a_one_line_error`, in two cases:
- **no transcripts:** the folder holds a folder named `x.jsonl`, a `.d.jsonl`, a `notes.txt`, and transcripts in `sub/` and `.hidden/`. The run must say "no .jsonl files in <folder>" with nothing on stdout. This also pins "only the top folder is read".
- **missing:** "cannot read <folder>".

**Other hits:** unused_tools pins its own error (`test_folder_without_transcripts_is_an_error`). measure
has no such error: it prints a table, or names what it skips.

## Info

1. **The CHANGELOG Review 27 line,** as corrected in pass 30, still listed "links to folders not followed, hidden folders read" under both scripts. usage_breakdown reads only the top folder. Fixed: the line names each script's own rules.
2. **Rules from main that the PR did not touch have no tests. No action.** The reviewer's mutants a01-a06 (measure's output order, BOM drop, change line, total row, FIFO argument), c03 and c04 (`--top` in unused_tools) and b03 (`COUNT` 0) survive. The code is unchanged from main, so it is outside this PR.

## Prevention

Each error that README promises for the transcript scripts is now pinned by a test.
