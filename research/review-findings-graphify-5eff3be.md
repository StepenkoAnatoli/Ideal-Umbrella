# Review of branch graphify-ideas at 5eff3be (2026-10-27, thirtieth pass)

One fresh-context reviewer did a breaker review of the diff `origin/main...5eff3be`. It ran on the
session's default model because the Fable usage limit was reached again.

Its report and repro scripts are in the session scratchpad, not in the repo: `review30b-findings.md` and
`review30b/`. That folder holds:
- `repro/r1_link_rules_unpinned.py` (output in `r1.out`): HEAD and each surviving mutant on one tree holding a linked argument, a link to a transcript, a link to a file and a link to a folder;
- `mut/mutate.py`: mutants n01-n23, with the suite runs in `mut/results.txt`.

New ground in this pass: the pass-29 changes (a link whose target goes through a file leads nowhere, in
unused_tools, usage_breakdown and measure, and the tests for a link into a folder that cannot be searched).

The findings of passes 1 to 29 were checked and are not reported again (`research/review-findings-graphify-5a18f22.md` to `-a7ab29a.md`).

**Status:** no code defect. All findings are fixed in the next commit on PR #27.

The pass-29 fixes hold:
- CI at 5eff3be is green on all five jobs. On Windows 1050 passed and 30 skipped, so links were made there and the link tests ran.
- The install and uninstall fuzzers re-ran clean (review21 `sfuzz.py`, 150 seeds; review22 `rfuzz.py`, 300 seeds).

Checks run on the fixed tree, all passing:
- pytest on 3.13, on 3.10, and on a real 3.14.6 (with an 8 MB stack and with an unlimited one);
- keyline, pyflakes and the JSON checks;
- the CRLF copy, and the suite with `write_text` forced to CRLF.

Mutants are in the session scratchpad, `fix30/mut.py` (the reviewer's survivors n02, n16, n19, n20, n21
and n23), and all of them are killed.

**Counts:** 0 high, 0 medium, 1 low (L1: test gap), 3 info (fixed: 2, no action: 1).

## Low

### L1. The link rules kept from main were not pinned for unused_tools' argument and for measure

**Finding:** the PR replaced pathlib's `is_dir()`/`is_file()`, which follow links, with `os.stat` checks.
Six mutants passed the full suite but changed the output in a realistic setup (`~/.claude/projects`
linked to another disk, or dotfiles links):
- n02 (`_is` with `lstat`): a linked transcript folder argument became "is not a folder", exit 2;
- n16 (`files_in` with `lstat`): an argument that is a link became "no such file or folder";
- n20 (`_listed_file` refusing links): a walked `*.jsonl` link to a transcript was not counted;
- n21 (measure refusing links): a walked link to a file was "not a regular file";
- n19 (`followlinks=True` in measure): a linked folder was walked, so its files could be counted twice;
- n23 (unused_tools skipping dot files): a dot-named `*.jsonl` was no longer counted, though rglob counted it.

**Fixed (tests):**
- `test_a_linked_folder_argument_and_a_linked_transcript_are_followed` (unused_tools): kills n02 and n20.
- `test_the_walk_keeps_rglobs_rules` now holds a `.d.jsonl` that is counted: kills n23.
- `test_links_are_followed_except_a_walked_link_to_a_folder` (measure): a linked folder argument, a linked file argument, a walked link to a file, and a walked link to a folder that is not walked. It kills n16, n19 and n21.

**Other hits:** usage_breakdown already pins a linked transcript (`test_a_link_to_a_transcript_is_read`)
and its argument goes straight to `os.listdir`, which follows links. Install, uninstall and add_to_repo
follow or refuse links by design, and earlier passes pinned that.

## Info

1. **The CHANGELOG Review 27 line** said "dot files skipped" for both transcript scripts. That holds for usage_breakdown only. Fixed: the line names the rules per script.
2. **CI did not list its skipped tests** (`pytest -q`), so the Windows link tests could only be told to have run from the skip count. Fixed: `pytest.ini` adds `-rs`, so CI and local runs list them.
3. **Equivalent or near-equivalent mutants, no action:**
   - n01: differs only for a FIFO, like k13;
   - n09: ENAMETOOLONG, which needs a link target past PATH_MAX;
   - n10: a looped link called a missing target, which is accepted wording;
   - n14, n15: reachable only when a folder turns into a file mid-walk.

## Prevention

Each listing rule the PR carried over from main is now pinned by a test, including the link rules. A
rewrite that stops following links, or starts following linked folders, fails the suite.
