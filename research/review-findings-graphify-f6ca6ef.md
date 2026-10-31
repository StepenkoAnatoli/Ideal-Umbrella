# Review of branch graphify-ideas at f6ca6ef (2026-10-27, third pass)

A breaker review of the diff `origin/main...f6ca6ef` by one fresh-context reviewer. It ran on the session's
default model because the Fable usage limit was reached. Its report and repro scripts are in the
session scratchpad, not in the repo: `review3-findings.md` and `review3b/s1`-`s10`, `mutate.py`.

The baseline at f6ca6ef was:
- pytest: 382 passed, 4 skipped.
- keyline: 35/35.
- pyflakes: clean.

The findings of passes 1 and 2 were checked and not reported again. Those are
`research/review-findings-graphify-5a18f22.md` and `research/review-findings-graphify-db5cd0c.md`.

Status: every finding is fixed class-wide in the next commit on PR #27.
- pytest: 473 passed, 4 skipped on 3.13 and on 3.10.
- keyline: 35/35.
- pyflakes: clean.
- Every review-3 repro script now gives the expected result.

Every test named below failed before its fix, except where marked coverage.
Counts: 0 high, 2 medium, 5 low, 3 info.

Pattern across the pass: four of the findings were regressions from the pass-2 fix that writes
the record first. That order was checked only against a first install that adds a section, the
one case the failed-write test seeded. In every other run, the record written first
overwrote the earlier record's description of what is on disk, so a failed write left both the
rerun and uninstall working from changes that never landed. The other findings extend classes
that pass 2 had declared closed:
- a fenced example (finding 3).
- JSON that loads but cannot be written back (finding 5).
- a path that cannot be printed or written (finding 4).

## Medium

1. Finding: `wrapped: true` was lost on the wrap path whenever a record existed. The wrap path
   set `entry["wrapped"] = old is None`, overriding the value copied from the record.
   - Scenario A: the user deletes only the marker lines of a wrapped hand copy, then reinstalls.
   - Scenario B: the first install fails on the CLAUDE.md write, then the user reruns it.

   In both, the next uninstall removed the user's own copy of the rules.
   Fixed: `wrapped` is `old is None or` the record's `wrapped`.
   Tests:
   - `tests/test_claude_md_section.py` `test_a_hand_copy_wrapped_again_after_its_marker_lines_were_deleted_stays_the_users` (scenario A).
   - `tests/test_failed_writes.py` `a_hand_copy_of_the_rules` (scenario B).

   Other hits: the update path already carries `wrapped` over (pass 2, finding 3). The two paths
   that write a new section drop it. Those are now covered by
   `test_a_new_section_after_a_wrapped_copy_is_the_installers` (see I2).
   Prevention: premortem row 26.

2. Finding: a failed write in an update run left a record that made both the rerun and
   uninstall wrong:
   - (a) After a settings template change: the rerun said "left unchanged (use --force)" on
     every run, and uninstall said "not the installed value" and kept the key.
   - (b) After a CLAUDE.md template change: uninstall left the section, and the rerun printed a
     false "had edits" notice with a backup no record names.
   - (c) When moving from the whole-file installer: uninstall did not restore the user's file.

   Fixed: the record written first keeps the record it replaces under `pending`. The last write
   of the run writes the record without it. `settle_record(record, settings, claude_md_text)`
   resolves `pending` against the files, and install, uninstall and `--verify-only` call it:
   - For each installed key whose earlier value is still in settings.json, the earlier value is used.
   - For CLAUDE.md, the earlier entry is used when it describes the file and the new one does
     not. For a whole-file entry that means its whole-file hash; for a section entry, the hash
     of the section `find_section` finds.

   In a first install no earlier record exists, so nothing is kept. An uninstall stopped before
   its CLAUDE.md backup was made (the backup the record names does not exist) leaves no notice.
   Tests: `tests/test_failed_writes.py` was rewritten. It fails each of the run's writes in turn
   (backups included), for five kinds of run:
   - a first install
   - a settings template change
   - a CLAUDE.md template change
   - the move from the whole-file installer
   - a hand copy of the rules

   After each failure it uninstalls, both directly and after a rerun, and requires:
   - the files from before, with no backup left;
   - no notice of a value or section the user changed;
   - a rerun with no "had edits" or "left unchanged" notices, then an up-to-date install and a passing verify.

   This is 90 cases; 15 of them failed on f6ca6ef. Settings start without the template's keys,
   and the runs are made without `--force`, so a replaced value is not hidden.
   Other hits: `config/uninstall.py` writes settings.json before its leftover record, and a
   second uninstall skips keys already undone (checked in pass 2). `config/add_to_repo.py`
   keeps no record.
   Prevention: premortem row 27. README describes `pending`.

## Low

3. Finding: the hash fallback for a section that only looks fenced (pass 2, finding 2a) also took a
   fenced example. The user keeps the installed block as an example inside a code fence and
   deletes the live section. The body hashes to the record, so uninstall deleted the user's example.
   Fixed: `fenced_line(text, found)` says when the section found is inside a fence. No tool can
   tell a stray fence line from an example, so none changes such a section:
   - install leaves it when it is current, and stops before any write when the rules changed.
   - `--verify-only` warns.
   - uninstall leaves it, keeps its record entry, and says to close the fence above it and run
     uninstall again.

   Tests:
   - `test_a_fenced_example_of_the_section_is_never_taken_for_it`.
   - `test_a_template_change_does_not_rewrite_a_fenced_section`.
   - `test_a_fence_closed_only_after_the_section_does_not_hide_it`, updated: uninstall now leaves
     the section with the notice, and finishes once the fence is closed.

   Other hits: the hash fallback is used only through `find_section(text, recorded)`. Its callers
   are `plan_claude_md`, `_describes`, verify and uninstall. `_describes` only compares hashes and
   writes nothing.
   Prevention: premortem row 28. README states it.

4. Finding: a home path that is not UTF-8 (Linux) made the install fail on settings.json after it
   had written the record, the hook and CLAUDE.md, and it failed the same way on every rerun.
   `--verify-only` printed a traceback.
   Fixed: install checks that the hook command (which holds the path) encodes as UTF-8 before
   any write. The 17 other scripts that reconfigure stdout (in `config/`, `scripts/`, `hooks/`
   and `keyline/`) now pass `errors="backslashreplace"`, as `scripts/ledger.py` already did.
   Test: `tests/test_install.py`
   `test_a_home_path_that_is_not_utf8_stops_before_any_write_and_verify_has_no_traceback`
   (Linux only).
   Other hits: `config/add_to_repo.py` writes no path into settings.json (its hook command
   uses `$CLAUDE_PROJECT_DIR`). Uninstall writes back only values it read. `scripts/ledger.py`
   already used `backslashreplace` (pass 1).
   Prevention: `tests/test_source_rules.py` rule 3 now requires `errors="backslashreplace"`
   with the UTF-8 reconfigure. It listed 14 scripts before the change. Premortem row 29.

5. Finding: a number such as `1e400` in settings.json (valid JSON) reads as `inf`. Python's
   `NaN` and `Infinity` literals read as non-finite floats too. Install then wrote them back as
   `Infinity`, which is not JSON, and Claude Code's parser rejects the whole file.
   Fixed:
   - `_check_json` (in `config/install.py`, and its copy in `config/add_to_repo.py`) rejects a
     non-finite float before any write.
   - Both `_write_json` use `allow_nan=False`, so such a value can never be written.

   Tests: the `too-big` and `nan` cases of `test_settings_that_cannot_be_written_back_stop_before_any_write`
   in `tests/test_install.py`, and `too-big` in `tests/test_add_to_repo.py`.
   Other hits:
   - `scripts/ledger.py` dumps an entry of counts parsed by `int()`.
   - `scripts/plugin_cost.py` dumps rows it computed.
   - `hooks/context_check.py` dumps its own output.

   None of the three writes back a float it read.
   Prevention: source rule 7 already sends every JSON read in `config/` through `_check_json`.
   Premortem row 29.

6. Finding: a backup copy that failed part way (`shutil.copy2`) left a truncated backup that no
   record names.
   Fixed: `_backup` writes through `_write_bytes` (temp file, then rename), then copies the
   file's times and mode with `shutil.copystat`.
   Test: `tests/test_failed_writes.py` fails the backup writes as well (see finding 2).
   Other hits: `shutil.copy2` was the only copy in `config/`, `hooks/` and `scripts/`.
   Uninstall's backups go through the same `_backup`.
   Prevention: premortem row 30.

7. Finding: README "Install" still said the record is written last.
   Fixed: the sentence now points to the record-first order described above it.
   Other hits: README line 70 described the record-first order without `pending`; it now names
   it.

## Info

I1. Finding: leading zeros got past the `--handoff-at` digit limit, so Python's own 4300-digit
    message was printed. Fixed: `int()` reads the value with the zeros stripped. Test:
    `test_a_handoff_value_padded_with_zeros_is_read_without_the_digit_limit`. Other hit:
    `scripts/ledger.py` `_count` is reached through argparse, which turns the error into a
    usage line; left as is (pass 2).

I2. Finding: mutation-test gaps; the code was correct.
    - (a) The length check in `_fenced`'s closer table.
    - (b) Dropping `wrapped` when CLAUDE.md is gone.
    - (c) Dropping `wrapped` on the append path.
    - (d) The check for lone surrogates in dict keys.

    Fixed:
    - (a) `test_a_long_fence_with_only_shorter_closers_is_ordinary_text`.
    - (b) and (c) the `file-deleted` and `file-rewritten` cases of `test_a_new_section_after_a_wrapped_copy_is_the_installers`.
    - (d) the `surrogate-key` cases of the cannot-be-written-back tests.

    Each kills its mutant (checked with sed mutants). Coverage only.

I3. Finding: `tests/test_failed_writes.py` covered only a first install. Fixed by its rewrite
    (finding 2).

Still open, outside this PR: `keyline/keyline_lint.py:197` numbers lines with
`str.splitlines()` (from pass 1).
