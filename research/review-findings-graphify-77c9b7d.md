# Review of branch graphify-ideas at 77c9b7d (2026-10-27, twenty-sixth pass)

One fresh-context reviewer did a breaker review of the diff `origin/main...71ad696`. It ran on the
session's default model because the Fable usage limit was reached again. The branch moved to 77c9b7d
during the review, and the reviewer checked every finding again there.

Its report and repro scripts are in the session scratchpad, not in the repo: `review26-findings.md` and
`review26b/`. That folder holds:
- `repro/`: c1-c3, run as uid 65534 on real CPython 3.13.17 and 3.14.6;
- `mut/mutate.py`: mutants n01-n21;
- `ci/`: the CI job logs.

New ground in this pass: the pass-25 changes (`_absolute()`, add_to_repo's repo check, the `os.stat`
checks in measure, the keyline hook, lint_validate, unused_tools, plugin_cost and verify-tokens, and
the shared test helpers).

The findings of passes 1 to 25 were checked and are not reported again (`research/review-findings-graphify-5a18f22.md` to `-93ea5f8.md`).

**Status:** all findings are fixed class-wide in the next commit on PR #27.

Checks run on the fixed tree, all passing:
- pytest on 3.13, on 3.10, and on a real 3.14.6 (with an 8 MB stack and with an unlimited one);
- keyline, pyflakes and the JSON checks;
- the CRLF copy, and the suite with `write_text` forced to CRLF.

Mutants are in the session scratchpad, `fix26/mut.py`, and all of them are killed:
- **C3:** n01-n04, n06, n07, n12, n13, n17 (the reviewer's survivors);
- **C2:** c1 (unused_tools without `onerror`), c2 (measure's `onerror` silent), c3 (usage_breakdown listing through `glob`), c4 (usage_breakdown without the `OSError` handler), c5 (usage_breakdown passing over a transcript it cannot look at);
- **info 2:** i2.

**Counts:** 0 high, 1 medium (C1, already fixed by 77c9b7d), 2 low (C2, C3), 3 info (fixed: 2, no action: 1).

## Medium

### C1. Windows CI was red on 71ad696 (fixed by 77c9b7d)

The review-14 test `test_a_config_dir_that_cannot_be_looked_at_is_a_one_line_error` patched `Path.exists`, which `_absolute()` no longer calls. On Linux it passed for the wrong reason: the fake fired after the gate. 77c9b7d rewrote it with `refuse_looks_inside` (recorded under A in `-93ea5f8.md`). CI is green on 77c9b7d.

## Low

### C2. unused_tools and measure passed over a folder they could not list

**Finding:**
- `scripts/unused_tools.py` walked with `Path.rglob`, and `keyline/measure.py` with `os.walk` without `onerror`. Both pass over a folder they cannot list (mode 0311 or 0300).
- unused_tools then counted fewer transcripts with exit 0, so a denied tool used only there could read as unused. A top folder it could not list gave the false reason "no *.jsonl transcripts".
- measure left the folder's files out of the table without a word (an empty table for the top folder).
- README line 149 said unused_tools "exits with an error when the folder ... holds one it cannot read".

**Fixed:**
- unused_tools walks with `os.walk(folder, onerror=_raise)`; the existing handler prints "error: cannot read <folder> (<reason>)" and exits 1.
- measure prints "skip (cannot read: <reason>): <folder>", as it does for a file it cannot read (exit 0, as for files).
- `.jsonl` is matched with `os.path.normcase`, as rglob and glob match it on Windows.
- New test helper `refuse_listing(folder, monkeypatch)` in `tests/conftest.py` refuses `os.scandir`/`os.listdir` of one folder (and 3.10's `_NormalAccessor`).
- Tests: `test_a_folder_that_cannot_be_listed_says_cannot_read` (unused_tools, top and sub), `test_a_folder_that_cannot_be_listed_is_named_not_passed_over` (measure, top and sub), both failing first; `test_a_subfolder_that_cannot_be_listed_is_an_error_for_real` (unused_tools, mode 0311, non-root only; runs on the CI runners).

**Other hits of the class** (a walk or listing that says nothing for a folder or file it cannot look at):
- **Fixed:** `scripts/usage_breakdown.py` listed with `glob` and filtered with `os.path.isfile`: a folder it could not list read as "no .jsonl files", a transcript it could not look at was passed over, and one it could not open raised a traceback. It now lists with `os.listdir` and `os.stat` (not there: skipped; anything else: "cannot read <path> (<reason>)"), and keeps glob's rules (no dot files). Test: `test_a_folder_or_transcript_that_cannot_be_read_says_cannot_read` (folder, transcript), failing first.
- **Not changed:**
  - **`scripts/plugin_cost.py`'s `glob("**/.claude-plugin/plugin.json")`:** it walks the Claude app folder, which is your own. A walk that reports errors would have to copy glob's rules (hidden folders skipped, links to folders followed, loops); the code it adds outweighs an undercount in a folder you would have to lock yourself.
  - **`scripts/lint_validate.py` `corpus_files`:** the corpus is a sample, capped at `MAX_FILES`, and files it cannot read are skipped by design.
  - **`install._backup_name`'s `glob`:** runs in a folder the gate has already looked at.
  - **`hooks/context_check.py` `prune_state`:** treats any OSError as "nothing to prune" by design.

### C3. Pass-25 branches that no test reached

**Finding:** mutants n01-n04, n06, n07, n12, n13 and n17 survived. The code was right.

**Fixed (tests):**
- n01, n02: `test_a_home_that_is_a_file_is_not_found` and `test_a_home_that_is_a_link_to_a_folder_is_followed` (install and uninstall, `--home ~`).
- n03, n04: `test_a_repo_that_is_a_file_is_the_usage_line` and `test_a_repo_that_is_a_link_to_a_folder_is_followed` (add_to_repo).
- n06, n12, n13, n17: a path through a file (`a_file/x`) in measure, lint_validate, plugin_cost and the keyline hook.
- n07: `test_a_file_gone_during_the_walk_is_no_longer_there` (measure).
- n20 is equivalent, as the reviewer said.

## Info

1. **`python_314_pathlib` did not simulate 3.14 on Windows:** on Windows `os.path.exists()` and the like are C functions that a patched `os.stat` does not reach. Fixed: the fake now looks through `os.stat`/`os.lstat` and catches `OSError` and `ValueError`, as 3.14 does.
2. **The keyline hook raised a traceback for a path holding a NUL byte** (`os.stat` raises `ValueError`; `is_file()` said False before pass 25). Fixed: `ValueError` means "not a file". Test: `test_a_path_holding_a_nul_byte_passes_silently`, failing first. Other hits: `hooks/context_check.py` uses `os.path.isfile`, which says False for it; every other script takes its paths from the command line, which cannot hold a NUL.
3. **CHANGELOG wording at 71ad696** described Windows CI as fixed while it was red. True since 77c9b7d; no action.

## Prevention

Each walk over a folder now reports a folder it cannot list (`onerror`, or a listing inside a handler), and `refuse_listing` tests that path the same way `refuse_looks_inside` tests a path inside a folder that cannot be searched. The 3.14 pathlib fake works on Windows.
