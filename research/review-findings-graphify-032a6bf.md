# Review of branch graphify-ideas at 032a6bf (2026-10-27, fourth pass)

A breaker review of the diff `origin/main...032a6bf` by one fresh-context reviewer. It ran on the
session's default model because the Fable usage limit was reached. Its report and repro scripts are
in the session scratchpad, not in the repo: `review4-findings.md` and `review4/s1`-`s5`, `mutate.py`.
The reviewer failed every write of install (11 kinds of run) and of uninstall (11 kinds) in turn, and
ran 26 mutants against the full suite.

The baseline at 032a6bf was:
- pytest: 473 passed, 4 skipped.
- keyline: 35/35.
- pyflakes: clean.

The findings of passes 1 to 3 were checked and not reported again
(`research/review-findings-graphify-5a18f22.md`, `-db5cd0c.md`, `-f6ca6ef.md`).

Status: every finding is fixed class-wide in the next commit on PR #27.
- pytest: 490 passed, 4 skipped on 3.13 and on 3.10.
- keyline: 35/35.
- pyflakes: clean.
- Every review-4 repro script now gives the expected result (s3 and s4: 0 mismatches).

Every test named below failed before its fix, except where marked coverage.
Counts: 0 high, 0 medium, 3 low, 1 info finding (6 surviving mutants), 5 info notes.

Pattern across the pass: all three low findings are ends of the record-first order of pass 3 that a
test did not reach. Pass 3 covered a failure at each write but checked only the files left behind,
not the record, and it did not convert the file between install and uninstall.

## Low

A. Finding: uninstall stripped the separator the installer added (`joined`) only when the file ended
   with exactly the bytes recorded. After an editor or git changed the line endings, LF to CRLF left a
   lone CR (`b'mine\r\n\r'`) and CRLF to LF left an extra blank line. The README said the user's text
   stays byte for byte. The safety backup then differed from the result, so it was kept, and nothing
   named it.
   Fixed: `_rest_without_section` reads `joined` as a number of line breaks and strips that many,
   each `\r\n` or `\n`, only when all of them are there. A kept safety backup is now named in a
   notice (info E1).
   Tests:
   - `test_line_endings_changed_after_install_leave_no_trace_on_uninstall` (four cases: LF to CRLF
     and back, with and without a final newline).
   - `test_a_safety_backup_kept_after_the_user_edited_their_own_text_is_named` (E1).
   Other hits:
   - `plan_claude_md` carries `joined` over unchanged; only uninstall reads it.
   - The section itself is found by its marker lines with trailing whitespace ignored, so CR is no
     problem there, and `_lf` normalises before every hash.
   - E4 (a file mixing LF and CRLF holding an unmarked copy of the rules) is the same class. It is
     left as is: the copy is added once more as a new section, which uninstall removes again; no
     user text is lost.
   Prevention: premortem row 31.

B. Finding: when only the last write of a run (the record without `pending`) failed, a rerun had
   nothing to change and never wrote the record, so `pending` stayed for good. A value the user
   later set by hand that equalled the earlier install's was then taken for the installer's: install
   replaced it without `--force`, and uninstall deleted it.
   Fixed: install keeps the record as read. When it held `pending` and the run has nothing to
   change, it writes the settled record without `pending`.
   Tests:
   - `tests/test_failed_writes.py` `test_a_rerun_settles_a_record_left_pending_by_its_last_write`.
   - `test_a_completed_run_leaves_nothing_pending`, for each of the five kinds of run (kills M1).
   Other hits: uninstall always writes its leftover record, which is built without `pending`.
   `config/add_to_repo.py` keeps no record.
   Prevention: premortem row 32.

D. Finding: the user edits the section and reruns install. The backup of the edited file is
   made, then the CLAUDE.md write fails. No record named that backup, so an uninstall right away
   left it. The README said such a run is undone completely.
   Fixed: the entry names the backup as `edited_backup`. When uninstall leaves an edited section as
   is, it deletes that backup if it holds the same bytes as CLAUDE.md. After a run that landed, the
   file differs from the backup, which then holds the user's edits and is kept, as the install said.
   Test: `test_an_edited_backup_left_by_a_failed_write_goes_with_uninstall` (with and without a
   template change).
   Other hits:
   - The backup made before a section is added is named as `safety_backup` before any write (pass 3).
   - Settings backups are never deleted by uninstall; each run names its own in its output, and
     the progress lines name it when a later write fails.
   - A rerun reuses the edited backup by bytes (`_backup_name`).
   Prevention: premortem row 33.

## Info

C. Finding: six mutants survived the full suite.
   - M1 (the final record write dropped): killed by `test_a_completed_run_leaves_nothing_pending`.
   - M6 (`shutil.copystat` dropped): killed by `test_a_backup_keeps_the_time_of_the_file_it_copies`.
   - M8 (`fullmatch` to `match`): killed by the `CLAUDE.md.bak-20250101-000000-mine` case of
     `test_a_backup_the_user_named_is_never_taken_for_ours`.
   - M22 (`settle_record` dropped in verify): killed by `test_verify_reads_a_record_that_is_still_pending`.
   - M15 (the end-before-begin check in the hash fallback): not tested. The reviewer found no input
     through the public paths that tells it apart; the check stays as a guard.
   - M23 (`allow_nan=False`): not tested. `_check_json` rejects a non-finite float first; the
     argument stays as a second guard.

   The four tests are coverage only. Each kills its mutant; this was checked with the mutants applied
   one at a time, as were the B and D fixes.

E1. A safety backup kept because the user changed their own text was not named. Fixed under A.

E2. An OSError before any step of uninstall (settings.json replaced by a folder) said the undo
    "stopped part way". Fixed: with no step done the message only says to fix the cause and run
    uninstall again. It does not say "nothing written": an `rmtree` cut short is not a step done.
    Test: `test_an_os_error_before_any_step_does_not_say_part_way` (tests/test_uninstall.py).

E3. `add_to_repo --handoff-at` needs `--force` to change an existing value, which also replaces
    the repo's `autoCompactWindow`. This is documented; it is left as is.

E4. A mixed LF/CRLF file with an unmarked copy of the rules gets the section added (see A, other
    hits). Left as is.

E5. `config/add_to_repo.py` `_write_json` escapes non-ASCII as `\uXXXX`. This predates the branch,
    is valid JSON, and is outside this PR.

Still open, outside this PR: `keyline/keyline_lint.py:197` numbers lines with
`str.splitlines()` (from pass 1).
