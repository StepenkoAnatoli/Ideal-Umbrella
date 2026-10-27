# Review of branch graphify-ideas at f72f830 (2026-10-27, twenty-seventh pass)

One fresh-context reviewer did a breaker review of the diff `origin/main...f72f830`. It ran on the
session's default model because the Fable usage limit was reached again.

Its report and repro scripts are in the session scratchpad, not in the repo: `review27-findings.md` and
`review27b/`. That folder holds:
- `repro/`: the old and new transcript listings compared on Python 3.10 to 3.14, real modes as uid 65534, mutant effects on a real folder, and a folder removed during the walk;
- `mut/`: mutants a01-a07, b01-b10, m01-m03, k01, c01-c04 and p01-p05.

New ground in this pass: the pass-26 changes (the `os.walk`/`os.listdir` listings in unused_tools,
usage_breakdown and measure, `refuse_listing`, the 3.14 pathlib fake, and the keyline hook's NUL check).

The findings of passes 1 to 26 were checked and are not reported again (`research/review-findings-graphify-5a18f22.md` to `-77c9b7d.md`).

**Status:** no code defect. All findings are fixed in the next commit on PR #27.

The new listings give the same files, in the same order, as the old rglob and glob code on Python 3.10 to
3.14. CI at f72f830 is green on all five jobs.

Checks run on the fixed tree, all passing:
- pytest on 3.13, on 3.10, and on a real 3.14.6 (with an 8 MB stack and with an unlimited one);
- keyline, pyflakes and the JSON checks;
- the CRLF copy, and the suite with `write_text` forced to CRLF.

Mutants are in the session scratchpad, `fix27/mut.py`, and all of them are killed:
- **L1:** a03-a06;
- **L2:** b01, b04-b06;
- **I1:** f1, f2;
- **I2:** e1, e2;
- **pass 26 again:** c1, c2.

a02 and b02 (no `normcase`) can only be killed on Windows. The L1 and L2 tests hold an upper-case
`*.JSONL` that counts on Windows only, so Windows CI kills them. A run with `normcase` lowercasing
showed that both scripts count it.

**Counts:** 0 high, 0 medium, 2 low (L1, L2: test gaps), 3 info (all fixed).

## Low

### L1. unused_tools: the regular-file filter and rglob's other rules were untested

**Finding:**
- `os.walk` never puts a folder in `names`, so `test_a_folder_named_like_a_transcript_is_skipped` no longer reached the `S_ISREG` filter.
- No test pinned rglob's other rules: links to folders are not followed, hidden folders are read, and the name must end in `.jsonl`.
- Mutants a03 (no filter), a04 (`".jsonl" in name`), a05 (`followlinks=True`) and a06 (hidden folders skipped) survived.

**Fixed (tests):**
- `test_the_walk_keeps_rglobs_rules`: a hidden folder, `notes.jsonl.bak`, and an upper-case `U.JSONL` (counted on Windows only). It asserts the exact counts.
- `test_a_linked_folder_and_a_dangling_link_are_not_counted`: a link to a folder holding a transcript (counted once) and a dangling `gone.jsonl` (passed over).
- A FIFO named `p.jsonl` was tried and dropped. Under mutant a03 the script opens it and the suite hangs, and a test that hangs on a regression is worse than none. The dangling link kills a03.
- New shared helpers `link_or_skip` and `loop_or_skip` in `tests/conftest.py`.

### L2. usage_breakdown: "the COUNT largest" and the no-dot-files rule were untested

**Finding:** no test passed a COUNT or held transcripts of different sizes. Mutants b05 (smallest first), b06 (by name), b01 (dot files read) and b04 (`lstat`, which drops linked transcripts) survived.

**Fixed (tests):**
- `test_the_count_largest_transcripts_are_read_and_dot_files_are_not`: four sizes and a `.d.jsonl`, run with COUNT 2. It holds an `E.JSONL` that is one of the two largest on Windows.
- `test_a_link_to_a_transcript_is_read`.

## Info

1. **A folder removed during the walk** (Claude Code cleaning up old sessions while the script runs):
   - unused_tools stopped with "cannot read <sub> (No such file or directory)". A folder that is gone holds no transcripts, so `_raise` now passes over `FileNotFoundError`.
   - measure said "skip (cannot read: No such file or directory)". It now says "skip (no longer there)", as it does for a file, in a named `_unlisted` onerror.
   - Tests: `test_a_folder_gone_during_the_walk_holds_no_transcripts` (unused_tools) and `test_a_folder_gone_during_the_walk_is_no_longer_there` (measure), both failing first.
2. **A symlink loop named `*.jsonl`** stopped unused_tools and usage_breakdown with "cannot read ... (Too many levels of symbolic links)". A loop holds no transcript, so both now pass over `ELOOP`, as install's `_look` does.
   - Tests: `test_a_symlink_loop_named_like_a_transcript_is_passed_over` in both, failing first. They skip where links cannot be made or a loop is not `ELOOP` (Windows).
   - **Other hits, not changed:**
     - measure names a looped file in a skip line, exit 0, which is right for a table of files.
     - lint_validate and the folder arguments of the scripts get a one-line "cannot read" for a path the user typed.
     - The keyline hook runs only after a successful write to a real file.
3. **README line 149** said measure "names each file or folder it skips", but it passes over hidden folders, `cache/`, `__pycache__/` and `node_modules/` by design. It now says "names each file or folder it cannot read". measure's docstring now lists `node_modules/`.

## Prevention

The listing rules each script keeps (rglob's for unused_tools, glob's for usage_breakdown) are now
pinned by tests, including the Windows case rule, so a rewrite of either listing has to keep them. A
folder or link that holds no transcript (gone, or a loop) is passed over the same way in every walk.
