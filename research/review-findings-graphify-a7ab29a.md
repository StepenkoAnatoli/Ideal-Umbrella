# Review of branch graphify-ideas at a7ab29a (2026-10-27, twenty-ninth pass)

One fresh-context reviewer did a breaker review of the diff `origin/main...a7ab29a`. It ran on the
session's default model because the Fable usage limit was reached again.

Its report and repro scripts are in the session scratchpad, not in the repo: `review29-findings.md` and
`review29b/`. That folder holds:
- `repro/r1_link_through_a_file.sh`: a `*.jsonl` link whose target goes through a regular file;
- `repro/r2_link_into_locked_folder.sh`: a link into a folder that cannot be searched, real and under mutant k01;
- `mut/mutate.py`: mutants k01-k13.

New ground in this pass: the pass-28 changes (`_listed_file`, `_raise` raising every error, the same rule
in usage_breakdown and measure, `not_found_at`, the measure skip-folder test).

The findings of passes 1 to 28 were checked and are not reported again (`research/review-findings-graphify-5a18f22.md` to `-1ebdbbc.md`).
CI at a7ab29a is green on all five jobs. The reviewer checked `os.path.islink` on Windows 3.12+
(`nt._path_islink`: True for a dangling link, False for a path past MAX_PATH) and found no realistic
case against not re-listing the parent.

**Status:** all findings are fixed in the next commit on PR #27. L1 is a regression from pass 28.

Checks run on the fixed tree, all passing:
- pytest on 3.13, on 3.10, and on a real 3.14.6 (with an 8 MB stack and with an unlimited one);
- keyline, pyflakes and the JSON checks;
- the CRLF copy, and the suite with `write_text` forced to CRLF.

Mutants are in the session scratchpad, `fix29/mut.py`, and all of them are killed:
- **L1:** j04-j06 (`NotADirectoryError` dropped from the "leads nowhere" check in each script);
- **L2:** j01-j03 (the reviewer's k01-k03: any error on a link passed over, or called a missing target);
- **Info 2:** j07, j08 (the reviewer's k07, k09).

**Counts:** 0 high, 0 medium, 2 low (L1 regression, L2 test gap), 3 info (fixed: 2, no action: 1).

## Low

### L1. A `*.jsonl` link whose target goes through a file stopped the run

**Finding:** `b.jsonl -> afile/b.jsonl`, with `afile` a regular file: `os.stat` raises `NotADirectoryError`. Pass 28 passed over only `FileNotFoundError` on a link, so unused_tools and usage_breakdown stopped with "cannot read ... (Not a directory)", exit 1, where main and pass 27 passed it over. measure said "cannot read: Not a directory" instead of "symlink to a missing target".

**Fixed:** a link whose stat raises `FileNotFoundError` or `NotADirectoryError` leads nowhere, in all three scripts (unused_tools `_listed_file`, usage_breakdown `transcripts()`, measure's per-file loop). Tests, failing first: `test_a_link_that_leads_nowhere_is_passed_over` (unused_tools, missing and through a file), `test_a_link_through_a_file_is_passed_over` (usage_breakdown), `test_a_link_is_a_missing_target_only_when_it_leads_nowhere[through a file]` (measure).

**Other hits of the class** (a "leads nowhere" check that names `FileNotFoundError` only): none. install's and add_to_repo's `_look`, `unused_tools._is`, measure's `files_in` handler, lint_validate, plugin_cost and the keyline hook all take both.

### L2. Nothing pinned that a link into a folder that cannot be searched is an error

**Finding:** mutants k01-k03 (any error on a link passed over, or called a missing target) survived; with them a link to a transcript in a folder that cannot be searched would go uncounted.

**Fixed (tests):** `test_a_link_into_a_folder_that_cannot_be_searched_says_cannot_read` (unused_tools and usage_breakdown) and `test_a_link_is_a_missing_target_only_when_it_leads_nowhere[locked]` (measure), with `refuse_looks_inside` and `link_or_skip`.

## Info

1. **CHANGELOG Review 28 line:** "again" was true only for a folder in unused_tools, and "only a link to a missing target" left out loops (and measure names such a link). Fixed.
2. **`unused_tools._is` now only judges the argument, and its loop and not-a-directory branches were untested** (k07, k09 survived). Fixed: `test_an_argument_that_leads_nowhere_is_not_a_folder` (through a file, loop) expects "<dir> is not a folder", exit 2.
3. **Mutant k13** (`_listed_file` true for any link whose stat succeeds) is near-equivalent: os.walk puts a link to a folder in `dirs`, so only a FIFO or device named `*.jsonl` differs, and no test may hold a FIFO. No action.

## Prevention

"A link that leads nowhere" is one rule in all three walks: `os.path.islink` and `FileNotFoundError` or
`NotADirectoryError`, or ELOOP; tests hold both a dangling link and a link into a folder that cannot be
searched in each.
