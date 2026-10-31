# Review of branch graphify-ideas at d48df3e (2026-10-27, tenth pass)

A breaker review of the diff `origin/main...d48df3e` by one fresh-context reviewer. It ran on the
session's default model because the Fable usage limit was reached again. Its report and repro
scripts are in the session scratchpad, not in the repo: `review10-findings.md` and `review10/`
(`repro/` a1, a1b, a2, a3, a4, and `mut/` with 10 mutants aimed at pass 9's changes). New ground
in this pass: the note pass 9 added to `_undo_section`, the whole-file installer's backup on a
rerun, and the ledger's UTF-16 check.

The findings of passes 1 to 9 were checked and not reported again
(`research/review-findings-graphify-5a18f22.md`, `-db5cd0c.md`, `-f6ca6ef.md`, `-032a6bf.md`,
`-3d9c4e8.md`, `-1e9664a.md`, `-59fb4c9.md`, `-ded6960.md`, `-5584721.md`).

Status: every finding is fixed class-wide in the next commit on PR #27.
- pytest (3.11 and 3.10), keyline, pyflakes, the JSON checks and the CRLF copy pass.
- The reviewer's repros were rerun on the fixed tree:
  - a1 and a1b name the legacy backup at every failing step.
  - a2 skips the NUL tail and exits 0.
  - a3 names the kept copy, and the second run is `([], [])`.
  - a4 keeps the link and empties the dotfiles file.
- 11 mutants of the new code (session scratchpad `fix10/mut.py`) are all killed. Among them:
  - the `leave()` and `finish()` notes and deletes;
  - `_empty()` always unlinking;
  - `_is_file()` as `exists()`;
  - each half of the ledger's check.
- Pass 10's surviving mutants are dealt with:
  - s01 (BOM check dropped) is killed by the `utf-16-bom-only` case.
  - s04 (`is_file()` changed to `exists()`) is killed by `test_a_folder_named_as_the_kept_backup_is_not_named`.
  - s06 no longer applies: its code is gone, and the legacy note now comes from `leave()`, whose mutant m1 is killed.

Every test named below failed before its fix, except where marked coverage.
Counts: 0 high, 0 medium, 4 low (L1 to L4), 2 info notes (I1, I2).

Pattern across the pass: `_undo_section` had many return points, and each one decided on its own
which backups to delete or name. Pass 9 fixed the note in one of them. The fix this time is
structural: there is one exit for "the file is left and the record entry goes" (`leave()`), and
one for "the file is written, restored or deleted" (`finish()`).

## Low

L1. Finding:
    - Setup: an upgrade from the whole-file installer after the user rewrote `CLAUDE.md`, so the
      record holds both the legacy backup and the copy made before the section was added.
    - An uninstall that stopped after its `CLAUDE.md` step never printed the note naming the
      legacy backup.
    - The rerun then took either the "backup never made" branch or the "file equals the copy"
      branch. Neither named it, and the record entry was dropped.
    - Pass 9's "Other hits" said the legacy backup was named in the same branch. That was true
      only for the else-branch.

    Fixed: every path that leaves the file and drops the record entry ends in `leave()`:
    - a backup that holds the same bytes as the file is deleted;
    - any other backup is named: "kept in" for the copy from before the section, "still in" for
      the legacy backup.

    The else-branch note no longer carries the legacy name in parentheses; `leave()` gives it as
    its own note. The pass-9 doc is corrected.

    Tests: the `a_rewritten_whole_file_install` and `a_wrapped_whole_file_install` kinds of
    `test_a_kept_backup_is_named_when_an_uninstall_that_failed_part_way_is_finished`.
    - 5 cases failed before the fix.
    - The wrapped kind is coverage for the else-branch, where mutant s06 survived.
    - The test now also checks that a third run is `([], [])`.

    Other hits:
    - The whole-file record branch keeps its record entry when it leaves the file
      (`claude_md_left`), so the rerun gives its note again.
    - A no-record backup is named in the progress list as soon as it is made.
    - `CLAUDE.md` being gone names the legacy backup in its own branch.

    Prevention: premortem row 53.

L2. Finding: since pass 9, `scripts/ledger.py` took any NUL byte for UTF-16 or UTF-32.
    - A torn append after a power loss (NTFS, XFS, ext4 with delalloc) reads as NUL bytes.
    - Every run, `--dry-run` included, then stopped with a false cause. Saving the file as
      UTF-8 did not remove the NULs, so the error never went away.

    Fixed: `_wide()` decides by structure:
    - a byte order mark (UTF-16 either way, UTF-32 BE; UTF-32 LE starts like UTF-16 LE);
    - or a NUL among the first four bytes beside a byte that is not NUL. A ledger line starts
      with ASCII `{`, so UTF-16 and UTF-32 always have one there.

    NULs alone are not an encoding: such a line is skipped and counted, as the docstring says.

    Tests:
    - `test_a_torn_append_filled_with_nul_bytes_is_an_unreadable_line[nul-tail|nul-line|torn-then-nul]`.
    - `test_a_file_of_nul_bytes_only_is_an_unreadable_line`.
    - New `utf-32-be` and `utf-16-bom-only` cases in the UTF-16 test (coverage; the second
      kills s01).

    Other hits: no other code tells an encoding by NUL bytes (grep for `x00` outside the tests).
    The installers decode `settings.json` and `CLAUDE.md` strictly as UTF-8, so a file with NUL
    bytes fails there as "not UTF-8" or "not valid JSON". That is a true cause.

    Prevention: premortem row 54. Row 52 is marked as narrowed.

L3. Finding: when only the section was left in `CLAUDE.md`, two branches returned before the
    check on the copy from before the section:
    - restoring the whole-file installer's backup;
    - deleting a file the install created.

    That copy was then kept with no word about it, against what README "Undo" says.

    Fixed: one `finish(change, final, action)` serves the section removal, the restore and the
    delete. It compares the copy with the bytes the file ends with:
    - the same bytes: the copy is deleted after the action;
    - different bytes: the copy is kept and named.

    Tests:
    - `test_the_copy_made_before_the_section_is_named_when_the_file_is_restored_or_deleted[restored|created]`.
    - `test_the_copy_made_before_the_section_is_deleted_when_the_file_is_restored_to_the_same_bytes`
      (coverage).

    Other hits: a restore that stops after its write is finished by `leave()` on the rerun. It
    deletes or names both backups (the old "restored and deleted the backup, then stopped" path
    named neither).

    Prevention: premortem row 55.

L4. Finding: the installer writes through a symlinked `CLAUDE.md` (dotfiles, stow), but four
    branches that delete the file unlinked the link instead:
    - a created section with nothing else;
    - a whole-file record with no backup;
    - a whole-file install without a record;
    - a section without a record with nothing else.

    The dotfiles file kept the rules, and the next stow brought them back for good.

    Fixed: `_empty()` gives "CLAUDE.md emptied (it is a link; the link is kept)" and writes no
    bytes through the link. Without a record, the backup is still made first.

    Tests: `test_a_symlinked_claude_md_that_holds_only_the_rules_is_emptied_through_the_link[4 kinds]`.

    Other hits:
    - Every write and restore of `CLAUDE.md` and `settings.json` already goes through the link.
    - A symlinked hook file is unlinked on purpose: the hook is the installer's own copy, and once
      its entry in `settings.json` is gone, a copy left in dotfiles is never run.
    - The state folder link is unlinked on purpose (review 4).

    Prevention: premortem row 56.

## Info

I1. Ledger mutant s01 (BOM half dropped) survived because every test file also held a NUL.
    Fixed: the `utf-16-bom-only` case (an empty file PowerShell 5 made). Since L2's fix, the BOM
    check is the only check that catches this case.

I2. Mutant s04 (`is_file()` changed to `exists()` in the pass-9 note) survived.
    Fixed: `_is_file()` holds the check for every backup, and
    `test_a_folder_named_as_the_kept_backup_is_not_named` pins it.

Still open, outside this PR: `keyline/keyline_lint.py:197` numbers lines with
`str.splitlines()` (from pass 1).
