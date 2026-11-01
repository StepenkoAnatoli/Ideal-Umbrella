# Review of branch graphify-ideas at 67f2a7b (2026-10-27, twenty-third pass)

A breaker review of the diff `origin/main...67f2a7b` by one fresh-context reviewer. It ran on the
session's default model because the Fable usage limit was reached again. Its report and repro
scripts are in the session scratchpad, not in the repo: `review23-findings.md` and `review23/`
(`repro/` r1.sh, r2.sh; `probe/p_offset.py`; `src` = 67f2a7b and `old` = 3eae041 for comparison;
`fuzz/rfuzz.py` 0 tracebacks in 300 seeds, `fuzz/sfuzz.py` 0 of 400 seeds with problems). New
ground in this pass: the pass-22 fixes (the BOM-aware byte offset, the advice tests, the
older-record delete test).

The findings of passes 1 to 22 were checked and not reported again
(`research/review-findings-graphify-5a18f22.md` to `-3eae041.md`).

Status: both findings are fixed class-wide in the next commit on PR #27.
- pytest (3.13 and 3.10), keyline, pyflakes, the JSON checks, the CRLF copy and the suite with
  `write_text` forced to CRLF pass.
- Mutants (session scratchpad `fix23/mut.py`): o1-o3 (drop the `except OSError` in each reader),
  c1-c3 (read bytes instead of text in each reader) and b1, b2 (`_bad_byte` without the BOM) are
  killed.

Counts: 0 high, 1 medium (F1), 0 low, 1 info (I1).

## Medium

F1. Finding: a regression from the pass-22 fix. `install.read_record` opened and read the record
    before its `try`, so the `except OSError` that gives "cannot read <record> (<reason>)" was
    dead. A record that cannot be opened (a 0600 file left by a `sudo` run, a folder in its
    place) gave a bare `Error: [Errno 13] ...` without "nothing written" in install, the
    generic OSError message in uninstall, and `--verify-only` stopped with exit 1 and no report
    (its `except ValueError` treats a bad record as checked elsewhere). README line 70 promises
    that such a record stops install and uninstall before anything is written; the stop still
    happened, the notice did not. No test opened an unreadable record.

    Fixed: `read_record` and both `_read_json` (install.py, add_to_repo.py) read the file in
    text mode with `utf-8-sig` inside one `try`, which has an `except OSError` giving
    "cannot read <path> (<reason>)" as a ValueError; `_bad_byte(path, e)` reopens the file to
    see whether it starts with a BOM. The docstrings say a file that cannot be read is one of
    the ValueErrors.

    Tests: `test_a_record_that_cannot_be_read_stops_before_anything_is_written` (install and
    uninstall; a folder, and an `open` refused with PermissionError, the Windows and EACCES
    case) and `test_verify_only_does_not_stop_on_a_record_that_cannot_be_read`; all failed
    before the fix.

    Other hits: `install._read_json` and `add_to_repo._read_json` never caught OSError (before
    or after pass 22), so an unreadable `settings.json` gave `Error: [Errno ...]` without
    "nothing written" in install, uninstall and add_to_repo. Fixed the same way;
    `test_a_settings_file_that_cannot_be_read_stops_before_anything_is_written` (install and
    uninstall, folder and denied) and its add_to_repo twin failed before. The review-4 test
    `test_an_os_error_before_any_step_does_not_say_part_way` now expects this message
    ("cannot read ...; nothing written") instead of the generic "run uninstall again". The
    keyline readers and verify-tokens reopen the file only inside their `UnicodeDecodeError`
    handler and their callers catch OSError: unchanged.

## Info

I1. Finding: reading bytes (pass 22) kept bare CR line ends (classic Mac), so a JSON error on
    line 3 was reported on line 1; text mode had read them as line ends.

    Fixed: by the same change (text mode again).

    Tests: `test_a_json_error_in_a_file_with_bare_cr_line_ends_names_the_line` for install
    (settings and record) and add_to_repo; all failed before the fix.

## Prevention

Premortem row 84: a change to a reader keeps every I/O call inside the handler that names the
file, and a test opens each file a run reads as a folder and as a refused open.
