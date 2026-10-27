# Review of branch graphify-ideas at 93ea5f8 (2026-10-27, twenty-fifth pass)

One fresh-context reviewer did a breaker review of the diff `origin/main...93ea5f8`. It ran on the
session's default model because the Fable usage limit was reached again.

Its report and repro scripts are in the session scratchpad, not in the repo: `review25-findings.md` and `review25/`. That folder holds:
- `repro/`: g1-g4, run as uid 65534 for real permission checks;
- `uvpy/`: a real CPython 3.14.6;
- `mut/mutate.py`: mutants b01-b08;
- `ci/`: the CI job logs.

The fuzzers all came back clean:
- review22 `sfuzz` and `rfuzz`, 150 seeds each: 0 problems;
- review21 `mdfuzz`, 100 seeds: 0 problems;
- the review12 sweep: the same as its baseline.

New ground in this pass: the pass-24 gate (`_look`, `_dangling`, `refuse_dangling`, `read_record`) and CI on Python 3.14.

The findings of passes 1 to 24 were checked and are not reported again (`research/review-findings-graphify-5a18f22.md` to `-d5c1570.md`).

**Status:** all findings are fixed class-wide in the next commit on PR #27.

Checks run on the fixed tree, all passing:
- pytest on 3.13, on 3.10, and on a real 3.14.6 (with an 8 MB stack and with an unlimited one);
- keyline, pyflakes and the JSON checks;
- the CRLF copy, and the suite with `write_text` forced to CRLF.

Mutants are in the session scratchpad, `fix25/mut.py`, and all of them are killed:
- **pass-24 CI fixes:**
  - j1-j3: the RecursionError branches;
  - s1, s2: measure;
  - h1: keyline_hook;
  - v1: lint_validate;
  - u1-u3: unused_tools;
  - p1: plugin_cost;
  - t1: verify-tokens.
- **D:**
  - d1: `_absolute` with `exists()`;
  - d2: the `~` home check with `is_dir()`.
- **E:**
  - b01, b02: the verify gate without settings or CLAUDE.md;
  - b04: add_to_repo's link check with `os.path.exists`.
- **info 2:** i2, add_to_repo's repo check with `os.path.isdir`.

**Counts:** 0 high, 2 medium (A, B), 3 low (C, D, E), 2 info (fixed: 1, accepted: 2).

## Medium

### A. Windows CI was red on 93ea5f8: the test's refusal fake never matched on Windows

**Finding:**
- The test helper `_unsearchable` followed a link with `os.readlink`.
- On Windows, `os.readlink` returns an absolute target as `\\?\C:\...`, so the target never started with the refused folder.
- `test_a_link_into_a_folder_that_cannot_be_searched_is_not_called_missing` therefore saw a reachable file, and `main` returned 0.
- The product was right; the Windows run of the test proved nothing.

**Fixed:**
- One helper, `refuse_looks_inside(folder, monkeypatch)` in `tests/conftest.py`, now replaces the copies in test_uninstall and test_add_to_repo.
- It strips `\\?\` and `\\?\UNC\` from a link target and compares `normcase(normpath(path))`.
- It refuses `os.stat`, `lstat`, `open`, `scandir`, `listdir`, `builtins.open` and `io.open`; `io.open` is what pathlib's `read_text` and `read_bytes` use.
- On 3.10 it also refuses pathlib's own `_NormalAccessor` references.
- `python_314_pathlib(monkeypatch)` moved to conftest too.

### B. ubuntu/3.14 CI was red: the nested-too-deep tests depended on the stack size

**Finding:**
- The tests wrote `"[" * 100000`.
- On 3.14 the json C scanner's recursion limit follows the real stack size. With a large stack it reached the end of the input and raised `JSONDecodeError`, so the RecursionError branch the tests are named for was never hit.
- The product's message was a correct one-line error for that input.

**Fixed:**
- The tests now use closed nesting inside an object. They accept "nested too deeply" (RecursionError) or "nested more than 100 levels deep" (`_check_json`), with exit 1 and nothing written.
- New deterministic tests make `json.load`/`loads` raise RecursionError and assert "nested too deeply": `test_json_nested_too_deep_is_a_one_line_error` (install) and `test_a_recursion_error_while_reading_is_a_one_line_error` (add_to_repo).
- The suite passes on 3.14.6 with an 8 MB stack and with `ulimit -s unlimited`.

## Low

### C. keyline/measure.py misreported unreadable files on Python 3.14

**Finding:** `files_in` and the per-file loop decided with `is_file()`/`is_dir()`/`is_symlink()`. For a file in a folder that cannot be searched, 3.14 said:
- for a file passed directly: "no such file or folder";
- for a walked file: "skip (not a regular file)".

3.13 said "cannot read" in both cases. This predates the PR, which added the 3.14 CI that exposed it.

**Fixed:**
- Both places use `os.stat`. `FileNotFoundError`/`NotADirectoryError` mean "not there", and any other OSError is "cannot read".
- Tests: `test_a_file_in_a_folder_that_cannot_be_searched_says_cannot_read` (argument and walked × pathlib 3.13 and 3.14).

**Other hits of the class** (a pathlib `is_*()`/`exists()` deciding "missing" on a user path):
- **Fixed the same way**, each with a failing-first test in 3.13 and 3.14 behaviour:
  - `keyline/keyline_hook.py`, the watched-file check;
  - `scripts/lint_validate.py`, the file and folder arguments ("cannot read");
  - `scripts/unused_tools.py`, the folder argument and the walked transcripts ("cannot read", exit 1; a transcript left out would undercount);
  - `scripts/plugin_cost.py`, the app folder;
  - `config/verify-tokens.py`, which now opens the file and says "not found" only on `FileNotFoundError`.
- **Not changed:**
  - **`keyline_hook` `note_for` and the `he.is_file()` check:** both are in a folder whose file the hook has just stat'ed, so they are unreachable for this class.
  - **`keyline_lint` ancestors:** already resolved, so they are searchable.
  - **`keyline_lint` `WORDS_CACHE`:** inside the checkout. A miss rebuilds the cache, and the write error is reported.
  - **`usage_breakdown` and `plugin_cost`'s `os.path.isfile` calls:** say False on errors on every Python version, so behaviour is unchanged.
  - **`hooks/context_check.py`:** treats any OSError as "no state" by design.
  - **uninstall's `paths["log"].is_file()`:** under the gated ballast folder.

### D. `install._absolute()` ran before the gate and used `exists()` and `is_dir()`

**Finding:** `target()` calls `_absolute()` before `refuse_dangling`, and `_absolute()` decided "dangling" with `_is_link(p) and not p.exists()`.
- **3.13:** a `--home` or `CLAUDE_CONFIG_DIR` that is a link into a folder that cannot be searched got a bare `Error: [Errno 13] ...; nothing written`.
- **3.14:** it was right only by luck.
- **The `~` check:** `home.is_dir()` gave the bare `[Errno 13]` on 3.13, and the false "cannot find the home folder" on 3.14.

This also contradicts the pass-24 record, which said "install.target()'s link handling runs after the gate", and the rule in premortem row 85.

**Fixed:**
- `_absolute()` decides "dangling" with `_dangling([path])`, which uses `_look`.
- It checks the `~` home with `_look(home, follow=True)` and `S_ISDIR`.
- A path it cannot look at is "cannot look at <path>; nothing written".
- Test: `test_a_home_that_cannot_be_looked_at_says_cannot_look_at` (`--home` link and `~` × 3.13 and 3.14 × install and uninstall). The 3.13 cases and the `~` 3.14 case failed before the fix.

**Other hits:** none. Every other `exists()`/`is_*()` in install, uninstall and add_to_repo runs after the gate on gated paths (listed in the pass-24 record). The pass-24 record and premortem row 85 are corrected.

### E. Pass-24 gate branches had no tests

**Finding:** mutants b01-b03 (the verify gate without settings and/or CLAUDE.md) and b04 (add_to_repo's link check using `os.path.exists`) survived. The code was right.

**Fixed (tests):**
- `test_verify_says_cannot_look_at_for_a_link_into_a_folder_that_cannot_be_searched` covers settings and CLAUDE.md × 3.13 and 3.14.
- `test_a_settings_link_into_a_folder_that_cannot_be_searched_is_not_called_missing` covers add_to_repo.
- b01, b02 and b04 are killed. b03 is b01 and b02 together.
- b05-b08 are equivalent, as the reviewer said.

## Info

1. **Windows "bypass traverse checking":**
   - `_dangling` lstats every ancestor, so a user with bypass-traverse rights but no read-attributes right on an ancestor could be refused for a path that works.
   - Accepted: it cannot be tested here, and refusing is the safe side (nothing written, the reason named).
2. **add_to_repo's repo argument:**
   - `os.path.isdir(argv[0])` gave the usage line for a repo inside a folder that cannot be searched.
   - Fixed: the repo is looked at with `_look(..., follow=True)`, and a refusal is "cannot look at <repo>; nothing written". Test: `test_a_repo_that_cannot_be_looked_at_says_so_not_usage`.
3. **uninstall's `paths["log"].is_file()`:** on 3.14 it skips a log linked into a locked folder. Accepted: contrived, since the log sits under the gated ballast folder.

## Prevention

Premortem row 85 now also covers code that runs before the gate. `_absolute()` looks only through `_look`, and the test fakes live in one shared helper, `tests/conftest.py`, that handles Windows link targets. CI runs 3.14, and the deep-JSON tests no longer depend on the stack size.
