# Review of branch graphify-ideas at b9b2a9b (2026-10-27, eleventh pass)

A breaker review of the diff `origin/main...b9b2a9b` (code last changed in 9666225) by one
fresh-context reviewer. It ran on the session's default model because the Fable usage limit was
reached again. Its report and repro scripts are in the session scratchpad, not in the repo:
`review11-findings.md` and `review11/`:
- `repro/` b1 (with `b1_control`), b2 to b7;
- `mut/` with 25 mutants;
- `sweep/`: every write, unlink and rmtree of an uninstall failed in turn with ENOSPC. It covered
  14 scenarios, each with a plain and a symlinked `CLAUDE.md`, and each was followed by a rerun.

New ground in this pass: `leave()` and `finish()`, `_empty()`, the gone branch and the ledger's
`_wide()`.

The findings of passes 1 to 10 were checked and not reported again
(`research/review-findings-graphify-5a18f22.md`, `-db5cd0c.md`, `-f6ca6ef.md`, `-032a6bf.md`,
`-3d9c4e8.md`, `-1e9664a.md`, `-59fb4c9.md`, `-ded6960.md`, `-5584721.md`, `-d48df3e.md`).

Status: every finding is fixed class-wide in the next commit on PR #27.
- pytest (3.11 and 3.10), keyline, pyflakes, the JSON checks and the CRLF copy pass.
- The reviewer's repros were rerun on the fixed tree:
  - b1: runs 2 to 4 are `([], [])`, the link is kept and the record entry is gone.
  - b2 exits 0.
  - b3 keeps the backup, and the link still reads.
  - b5 names no folder; the restore gives the "missing" note, and the CLI exits 0.
  - b6 (a) and (b) name the backup; the third run is `([], [])`.
  - b7 names the copy.
- 21 mutants of the new code (session scratchpad `fix11/mut.py`): 20 are killed and n16 is
  equivalent. Six survived the first run (n02, n16 to n21) and got coverage tests.
  - n16 drops the `_is_target` guard in `finish()`. It is equivalent: a `CLAUDE.md` linked to the
    copy from before the section holds that copy's bytes, so the first check in `_undo_section`
    returns `leave()` before `finish()` is reached. The guard stays, for the day that check moves.
- The reviewer's surviving mutants:
  - t09 (`_is_file` without the symlink check) and t24 (`exists()` in `leave()`) are killed by
    the I1 tests.
  - t20 no longer applies: the dead BOM entry it changed is gone (I2).

Every test named below failed before its fix, except where marked coverage.
Counts: 0 high, 0 medium, 5 low (B1, B2, B3, B4, B6), 5 info (B5, B7, I1, I2, I3).

Pattern across the pass: a backup was trusted by its name. The code assumed a path with a
backup's name is a plain file, is not what `CLAUDE.md` points at, and is named by some other
branch. Each assumption failed somewhere:
- a link (B3);
- a folder (B5);
- the gone branch (B6);
- the edited branch (B7).

The fix puts the checks in two helpers:
- `_is_file()` before any read or note;
- `_is_target()` before any delete.

## Low

B1. Finding: a whole-file record with no backup (the install created the file) and a symlinked
    `CLAUDE.md`.
    - Since pass 10, `_empty()` empties the file through the link and keeps the link.
    - When a later step then failed, every rerun found an empty file. That is not the rules, so
      the rerun said "CLAUDE.md differs from what was installed; left as is" and kept the record
      entry. The rerun never converged.
    - A plain file was gone, so it converged.

    Fixed: in the whole-file branch, a blank file with a record and no backup is the finished
    step. There is no note, and the record entry goes.

    Tests: `test_a_symlinked_claude_md_emptied_by_an_uninstall_that_failed_part_way_is_finished`
    fails each later step in turn.
    - The whole-file cases 1 to 4 failed before the fix.
    - The created-section cases are coverage. That branch already ended in `leave()`.

    Other hits: the three other `_empty()` callers:
    - A created section reruns into "no section", which ends in `leave()` and drops the entry.
    - The two no-record branches find no evidence once the hook entry is gone, and with it
      still there they take the "no section and not the rules" path.

    Prevention: premortem row 59.

B2. Finding: `scripts/ledger.py` `_wide()` looked at the first 4 bytes, so a UTF-8 BOM followed by
    a torn append of NULs counted as "a NUL beside a non-NUL byte". Every run, `--dry-run`
    included, stopped with "not UTF-8 text (UTF-16 or UTF-32)".

    Fixed: after a UTF-8 BOM the check looks at the next 4 bytes.

    Tests: the `bom-then-nul` case of `test_a_torn_append_filled_with_nul_bytes_is_an_unreadable_line`.

    Other hits: no other code reads a BOM and then looks at bytes (grep `xef\\xbb\\xbf`). The
    installers decode with `utf-8-sig`.

    Prevention: premortem row 61.

B3. Finding: a user who put `CLAUDE.md` back with `ln -sf CLAUDE.md.bak-... CLAUDE.md` had the
    backup deleted as "CLAUDE.md holds the same bytes". The bytes were read through the link.
    `CLAUDE.md` was then a dangling link, and the user's text was gone.

    Fixed: `_is_target(backup, claude_md)` compares the resolved paths and guards every
    same-bytes delete. When the paths cannot be resolved, it says yes, and the backup is kept.
    The guarded deletes:
    - the copy from before the section and the legacy backup in `leave()`;
    - the edited-section copy;
    - the whole-file backup;
    - the legacy backup after a restore;
    - the copy after `finish()`.

    Tests:
    - `test_a_claude_md_linked_to_its_own_backup_keeps_the_backup`, with 5 kinds. The first 4
      failed before the fix. `a_legacy_backup_holding_the_section` is coverage and kills n17.
    - `test_a_backup_is_kept_when_it_cannot_be_told_whether_claude_md_links_to_it` (coverage,
      n02).

    Other hits: uninstall deletes no other file by comparing bytes. The hook file and the log are
    the installer's own.

    Prevention: premortem row 57.

B4. Finding: README line 74 and two docstrings said a `CLAUDE.md` symlinked by home-manager is
    written through. Home-manager links into the read-only Nix store, so install and uninstall
    stop at that file with "the file is read-only; make it writable first", every run.

    Fixed (docs): "home-manager" is gone from the README and both docstrings. The README says what
    such a link does and what to do: take the section out in the source, or replace the link with
    a file, then run again.

    Considered and not done: uninstall leaving such a link and going on with `settings.json` and
    the hook. A file is then left that the record no longer names. The error already names the
    path, and a rerun after the fix finishes the undo.

    Tests: `test_a_claude_md_linked_to_a_read_only_file_stops_uninstall_at_its_step_with_the_path`
    (coverage). The error's `filename` is the link's target, and the rerun finishes.

    Other hits: `settings.json` and the hook file go through the same `_write_bytes` and
    `refuse_read_only`, so the README sentence covers all three.

    Prevention: premortem row 62.

B6. Finding: with `CLAUDE.md` gone, uninstall named only the legacy backup, and only by
    `exists()`. The copy from before the section, and the whole-file record's backup, were kept
    with no word, and the record entry that named them went.
    - The user deleted `CLAUDE.md` after the install.
    - Or a pass-10 `finish()` delete stopped at a later step. The note was given only in the run
      that failed, and notices are not printed on an error.

    This contradicted README "Undo".

    Fixed: the gone branch names every backup the entry holds:
    - a section entry: the copy from before the section and the legacy backup;
    - a whole-file entry: its backup.

    Each is named "CLAUDE.md is gone; your file from before ... is still in ...", and only when it
    is a file.

    Tests:
    - `test_a_backup_is_named_when_claude_md_is_gone[a_section_install|a_whole_file_record]`.
      The `a_legacy_backup` kind passed already and is coverage.
    - `test_a_kept_backup_is_named_when_a_rerun_finds_claude_md_gone`, where 4 cases failed
      before the fix.
    - Each test checks that a third run is `([], [])`.

    Other hits: every other branch that drops the record entry ends in `leave()` or names its
    backup (pass 10).

    Prevention: premortem row 58.

## Info

B5. Finding: a folder with the legacy backup's name had two effects:
    - it was named "your CLAUDE.md from before the first install is still in ...";
    - the restore read it and stopped every run with "Is a directory".

    Pass 10's record said `_is_file()` held the check for every backup. It held only for the
    notes pass 10 added.

    Fixed: `_is_file()` is used wherever a backup is read, restored from or named:
    - the restore and its "missing" check;
    - the final legacy note;
    - the whole-file first check, its "differs" note and its restore;
    - the hand-section and edited notes;
    - the gone branch.

    The remaining `exists()` calls ask whether a backup is gone, and they stay on purpose.

    Tests:
    - `test_a_folder_named_as_the_legacy_backup_is_no_backup[section-removed|restored]`.
    - `test_a_folder_named_as_the_whole_file_backup_is_no_backup`.
    - `test_a_folder_named_as_a_backup_is_neither_read_nor_named` (6 kinds, coverage; it kills
      n18 to n21).

    Prevention: premortem row 60.

B7. Finding: on an edited section, the copy from before the install was kept, but the note did
    not name it. The hand-section note a few lines above did.

    Fixed: the same suffix, "(your file from before the install is in ...)".

    Tests: `test_an_edited_section_names_the_copy_made_before_the_install`.

    Prevention: premortem row 58.

I1. Finding: mutants t09 (`_is_file` without the symlink check) and t24 (`exists()` in the
    `leave()` legacy check) survived.

    Fixed (tests only):
    - `test_a_symlink_named_as_the_safety_backup_is_neither_deleted_nor_named`;
    - `test_a_folder_named_as_the_legacy_backup_is_not_named_when_the_section_was_taken_out`.

I2. Finding: the UTF-32 BE BOM entry in `_wide()` was dead code. Its leading NULs beside
    `FE FF` are caught by the NUL check (mutant t20).

    Fixed: the entry is removed, and the docstring says the second check finds UTF-32 BE.

I3. Finding: the reviewer confirmed that pass 10's test kinds reach their branches, and found no
    defect in the `add_to_repo.py` changes. Nothing to do.

Still open, outside this PR: `keyline/keyline_lint.py:197` numbers lines with
`str.splitlines()` (from pass 1).
