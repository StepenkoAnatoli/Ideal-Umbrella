# Review of branch graphify-ideas at 1ebdbbc (2026-10-27, twenty-eighth pass)

One fresh-context reviewer did a breaker review of the diff `origin/main...1ebdbbc`. It ran on the
session's default model because the Fable usage limit was reached again.

Its report and repro scripts are in the session scratchpad, not in the repo: `review28-findings.md` and
`review28b/`. That folder holds:
- `repro/r1_long_path.py`: a path past Windows' MAX_PATH, simulated (`os.scandir` and `os.stat` raise `FileNotFoundError` for a folder or file that is there);
- `repro/r2_file_gone_before_read.py`: a transcript removed between the listing and its read;
- `mut/mutate.py`: mutants g01-g15;
- `fixtry/`: the reviewer's sketch of an L1 fix.

New ground in this pass: the pass-27 changes (the listing-rule tests, `_raise` passing over a vanished
folder, measure's `_unlisted`, ELOOP passed over, `link_or_skip`/`loop_or_skip`).

The findings of passes 1 to 27 were checked and are not reported again (`research/review-findings-graphify-5a18f22.md` to `-f72f830.md`).
CI at 1ebdbbc is green on all five jobs.

**Status:** all findings are fixed in the next commit on PR #27. L1 is a regression from pass 27, and
the fix reverts pass 27's Info 1 (recorded there as superseded).

Checks run on the fixed tree, all passing:
- pytest on 3.13, on 3.10, and on a real 3.14.6 (with an 8 MB stack and with an unlimited one);
- keyline, pyflakes and the JSON checks;
- the CRLF copy, and the suite with `write_text` forced to CRLF;
- the reviewer's `r1_long_path.py` on the fixed tree: unused_tools exits 1 with "cannot read" for the long folder and the long file, measure prints "skip (cannot read: ...)", usage_breakdown exits with "cannot read".

Mutants are in the session scratchpad, `fix28/mut.py`, and all of them are killed:
- **L1:** h01-h10 (each script's "link to a missing target" and loop exceptions dropped or widened, `_raise` passing over not-found again, measure's old wording);
- **L2:** h11-h14 (hidden folders walked; `node_modules`, `cache`, `__pycache__` each dropped from `SKIP_DIRS`);
- **pass 26 again:** h15, h16 (the walks without `onerror`).

h06 and h10 survived the first run: no test held a dangling `*.jsonl` link in usage_breakdown, and
measure's dangling-link test did not check the wording. Both tests were added and kill them.

**Counts:** 0 high, 0 medium, 2 low (L1 regression, L2 test gap), 1 info (resolved by L1's fix).

## Low

### L1. On Windows a listed folder or file past MAX_PATH was taken for "gone"

**Finding:**
- Windows without `LongPathsEnabled` (the default) raises `FileNotFoundError` (WinError 3) for a path past MAX_PATH. Claude Code (Node) writes such paths: a long project folder name plus `<session>\subagents\` passes the limit.
- Pass 27 made unused_tools' `_raise` pass over every `FileNotFoundError` and measure's `_unlisted` call it "no longer there". unused_tools then left a session's subagent transcripts out with exit 0; measure named a folder that is there "no longer there".
- Older, same cause: a listed file whose own path is past the limit failed its `os.stat` with `FileNotFoundError`, and unused_tools' `_is` and usage_breakdown's `transcripts()` passed it over without a word. measure called it "no longer there".

**Fixed:**
- A name a listing has just given that then reads as "not found" is an error ("cannot read <path> (<reason>)", exit 1) in unused_tools (`_listed_file`, and `_raise` raises every error again) and in usage_breakdown; measure prints "skip (cannot read: <reason>)" for it, file or folder.
- Only a link to a missing target (checked with `os.path.islink`) and a symlink loop (ELOOP) are passed over: they hold no transcript. measure keeps "symlink to a missing target" for the first.
- The reviewer suggested telling "gone" from "too long" by listing the parent again. Not done: it adds a second listing (with its own race) to every not-found, and the only case it helps is a file or folder removed while the script runs, which a rerun clears. A loud error in doubt matches README line 149.
- New test helper `not_found_at(path, monkeypatch)` in `tests/conftest.py`: every `os.stat`, `os.scandir` and `os.listdir` of a path that is there raises `FileNotFoundError`.
- Tests, all failing first: `test_a_listed_name_that_is_not_found_says_cannot_read` (unused_tools, file and folder), `test_a_listed_transcript_that_is_not_found_says_cannot_read` (usage_breakdown), `test_a_walked_file_that_is_not_found_says_cannot_read` (measure, removed and too long), `test_a_folder_that_is_not_found_during_the_walk_says_cannot_read` (measure). They replace pass 27's two "folder gone" tests. Added for surviving mutants: `test_a_link_to_a_missing_transcript_is_passed_over` (usage_breakdown) and the wording check in measure's `test_unreadable_file_is_skipped_not_a_traceback`.

**Other hits of the class** (a "not found" read as "nothing there"):
- **Not changed**, because the path is one the user typed or a fixed target, not a name a listing has just given, and "not found" there is reported, not passed over: install's and add_to_repo's `_look`, install's record read, `config/verify-tokens.py` (a warning per file), `scripts/lint_validate.py` and `scripts/plugin_cost.py` (their arguments), `scripts/ledger.py` (a missing ledger is a first entry).
- **Not changed:** the keyline hook passes silently over a path it cannot stat, by design (it is not the hook's job to report the write it follows; a file it cannot stat it could not read either).

### L2. measure's folder-skip rules were not pinned by any test

**Finding:** mutants g13-g15 (hidden folders walked, `node_modules` dropped from `SKIP_DIRS`, `SKIP_DIRS` empty) survived.

**Fixed:** `test_hidden_cache_and_dependency_folders_are_not_walked` holds `.git/`, `cache/`, `__pycache__/` and `node_modules/` with a file each and `sub/y.txt`; only `y.txt` is in the table and stderr is empty. It kills h11-h14 (g13-g15).

## Info

1. **A transcript removed between the listing and its read still stopped the run**, while pass 27 passed over a removed folder. Resolved by L1's fix: every "not found" for a listed name is now an error, so the two agree; a rerun clears a race.

## Prevention

A walk never reads "not found" for a name it has just listed as "nothing there", because on Windows
that is also what a path past MAX_PATH says. `not_found_at` tests that case on every OS.
