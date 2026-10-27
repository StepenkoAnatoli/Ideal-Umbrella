# Review of branch graphify-ideas at d5c1570 (2026-10-27, twenty-fourth pass)

A breaker review of the diff `origin/main...d5c1570` by one fresh-context reviewer. It ran on the
session's default model because the Fable usage limit was reached again. Its report and repro
scripts are in the session scratchpad, not in the repo: `review24-findings.md` and `review24/`
(`repro/` f1-f7, run as uid 65534 for real permission checks; `py314.py`, a shim that gives
pathlib 3.14 behaviour; `uvpy/`, a real CPython 3.14.6, and `venv314/`; `mut/mutate.py`
a01-a09; `fuzz/rfuzz.py` 0 tracebacks in 200 seeds, `fuzz/sfuzz.py` 0 of 200 seeds with
problems; `probe/p_offset.py` 0 wrong offsets in 1440 checks). New ground in this pass: the
pass-23 readers (text-mode reads inside one `except OSError`, `_bad_byte`).

The findings of passes 1 to 23 were checked and not reported again
(`research/review-findings-graphify-5a18f22.md` to `-67f2a7b.md`).

Status: all three findings are fixed class-wide in the next commit on PR #27.
- pytest (3.13, 3.10 and a real 3.14.6), keyline, pyflakes, the JSON checks, the CRLF copy and
  the suite with `write_text` forced to CRLF pass. The reviewer's repros f1, f3, f4, f6 and f7
  run on the fixed tree (real permissions, 3.13 and 3.14.6) all give "cannot look at <path>"
  or "cannot read <path>" with "nothing written" and leave the files as they were.
- Mutants (session scratchpad `fix24/mut.py`), all killed: a05 (`read_record` checks
  `os.path.exists` first), a01 and a02 (uninstall's no-progress error says "part way" or
  nothing), l1 and l4 (`_look` swallows other OSErrors), l2 and l5 (`_dangling` without one of
  its looks), l3 (`verify` without the gate), r1 (`read_record` without NotADirectoryError),
  m1-m4 (add_to_repo's `_look`, `_read_bytes` for the repo hook and the shipped hook, and the
  link check), v1 and v2 (F3 other hits).
- CI now also runs Python 3.14 on Ubuntu.

Counts: 0 high, 1 medium (F1), 2 low (F2, F3).

## Medium

F1. Finding: from Python 3.14, pathlib's `exists()`, `is_file()`, `is_dir()` and
    `is_symlink()` return False on any OSError, not only on "not there". With `~/.claude` or
    `~/.claude/ballast` left 0700 by a `sudo` install, `read_record` took the record for none;
    uninstall ran in no-record mode, exited 0, kept our deny tools and dropped the user's own
    value that only the record held (`autoCompactWindow` 100000). `--verify-only` said
    "Missing:", uninstall could say "Nothing to undo.", and a `settings.json` linked into a
    folder that cannot be searched was called "a symlink to a missing target" with the advice
    to put the target back. Up to 3.13 the same cases were a bare `[Errno 13]` with no
    "nothing written".

    Fixed: `_look(path, follow=False)` in install.py lstat()s (or stat()s) a path and returns
    None only for FileNotFoundError, NotADirectoryError or a symlink loop; any other OSError
    is `ValueError("cannot look at <path> (<reason>)")`, so install and uninstall say "nothing
    written". `_dangling(paths)` looks at each path and every folder above it, and
    `refuse_dangling` (run by install and uninstall before any write, on settings, CLAUDE.md,
    hook and record) raises for the first dangling link. `verify` runs the same gate before its
    `exists()` checks. After the gate every later `exists()` on those paths and their siblings
    in the same folders is reliable on 3.13 and 3.14. `read_record` no longer checks
    `exists()` first: it opens the file and returns None on FileNotFoundError or
    NotADirectoryError.

    Tests: `test_a_folder_that_cannot_be_searched_stops_before_anything_is_written` (install,
    uninstall, verify × ballast, .claude × pathlib 3.13 and 3.14 behaviour),
    `test_a_record_is_read_whatever_exists_says`,
    `test_a_link_into_a_folder_that_cannot_be_searched_is_not_called_missing` (3.13, 3.14). The
    helper `_unsearchable` patches `os.stat`, `lstat`, `open`, `scandir`, `listdir` and
    `builtins.open`, and refuses a look that follows a link into the folder too. All failed
    before the fix.

    Other hits: add_to_repo's link check used `os.path.exists()` the same way; it now uses its
    own `_look` (test in `tests/test_add_to_repo.py`). `install.target()`'s link handling runs
    after the gate. The `exists()` calls in `install`, `uninstall` and `verify` now come after
    the gate. `hooks/context_check.py` treats any OSError as "no state" by design (a hook must
    never block a prompt).

## Low

F2. Finding: no test covered an uninstall OSError raised before any step was done; mutants
    a01 and a02 (the no-progress suffix changed to "part way" or dropped) survived. The code
    was right.

    Fixed: `test_an_os_error_at_the_first_write_does_not_say_part_way` makes the first write
    fail with ENOSPC and asserts "run uninstall again", without "part way", "Done before the
    error" or "nothing written".

F3. Finding: add_to_repo read the repo's hook and the shipped hook outside any handler, so a
    folder in the hook's place gave a bare `[Errno 21]` without "nothing written".

    Fixed: both reads go through `_read_bytes`, which turns an OSError into "cannot read <path>
    (<reason>)". Tests: `test_a_hook_file_that_cannot_be_read_stops_before_anything_is_written`,
    `test_a_source_hook_that_cannot_be_read_stops_before_anything_is_written`.

    Other hits, fixed the same way with failing-first tests: `verify` read the installed hook
    and `CLAUDE.md` with `read_bytes()` outside any handler (a folder in their place gave a bare
    `[Errno 21]` in `--verify-only`); they now go through `install._read_bytes`
    (`test_verify_names_a_file_it_cannot_read`). Mutants v1 and v2 killed.
    Not changed: install's kept-backup check still stops on a backup it cannot read (accepted
    earlier: the backups hold the undo); `_backup` reads only a backup `_backup_name` already
    read, or a new name; install's other reads go through `_read_text`, `_read_bytes` or
    `_read_json`; uninstall reads `CLAUDE.md` inside a handler, and an OSError on a backup during
    the undo gives "fix the cause and run uninstall again", which is right (it cannot tell
    whether the backup is a copy).

## Prevention

Premortem row 85: never decide "missing" with `exists()`, `is_file()` or `os.path.exists()` on
a path the run has not looked at; `_look` gates every path and its folders, and tests run with
pathlib in both 3.13 and 3.14 behaviour. CI runs 3.14.
