# Review of branch graphify-ideas at 341f303 (2026-10-27, twelfth pass)

A breaker review of the diff `origin/main...341f303` by one fresh-context reviewer. It ran on the
session's default model because the Fable usage limit was reached again. Its report and repro
scripts are in the session scratchpad, not in the repo: `review12-findings.md` and `review12/`
(`repro/` c1, c1_control, c1b, c2, c3, c4, c5; `mut/` with 12 mutants of pass 11's changes;
`sweep/`, pass 11's failure sweep run again, which is clean; `fixcheck/`, with the fixes it
suggested). New ground in this pass: pass 11's `_is_target`, `_is_file` and gone-branch changes,
and the ledger's check after a BOM.

The findings of passes 1 to 11 were checked and not reported again
(`research/review-findings-graphify-5a18f22.md` to `-b9b2a9b.md`).

Status: every finding is fixed class-wide in the next commit on PR #27.
- pytest (3.11 and 3.10), keyline, pyflakes, the JSON checks and the CRLF copy pass.
- 13 mutants of the new code (session scratchpad `fix12/mut.py`) are all killed. They cover:
  - each `same_file` use and its "cannot tell" answer;
  - the uninstall dangling check;
  - each ledger layout, the length check, the BOM offset and the BOM check after it;
  - each two-role skip and the gone-branch dedupe.

Every test named below failed before its fix, except where marked coverage.
Counts: 0 high, 1 medium (C5), 2 low (C1, C2), 2 info (C3, C4).

Pattern across the pass: each half of a pair was guarded where a finding showed it, and the
other half was not.
- Install refused a dangling link; uninstall did not.
- Uninstall kept a backup that `CLAUDE.md` links to; install's own backup reuse did not check it.

The ledger check was fixed one case at a time (rows 54, 61). Both are now decided by one shared
rule: `install.refuse_dangling()` and `install.same_file()`, used by both scripts, and a
structural check in the ledger.

## Medium

C5. Finding:
    - The trigger: `settings.json`, `CLAUDE.md`, the hook or the record is a symlink to a missing
      target, because a dotfiles folder was moved or is not mounted.
    - Uninstall read it as a missing file:
      - it dropped the settings undo and the `CLAUDE.md` entry, with the false "CLAUDE.md is
        gone" note;
      - it deleted the hook;
      - it wrote the record as `{"uninstalled": true}`.
    - Once the folder was back, the settings and the section could never be undone.

    Fixed: `install.refuse_dangling()`. Install already had this check inline; uninstall now
    runs the same function before it reads the record. The error is one line, and nothing is
    written.

    Tests: `test_a_dangling_symlink_stops_uninstall_before_anything_is_written[settings|claude_md|hook|record]`.
    Each case then puts the folder back, checks that one uninstall undoes everything, and checks
    that the second run is clean.

    Other hits: `config/add_to_repo.py` has the same check (its own copy: it does not import
    install). The ledger writes only its own file, and a dangling `--file` link is created by
    the append, which is right for a file that does not exist.

    Prevention: premortem row 63. README "Undo" says so.

## Low

C1. Finding: install trusted a backup's name over what the file is. With `CLAUDE.md` linked to
    one of the installer's backups (`ln -s`, the case pass 11 made uninstall keep):
    - `_backup_name()` reused the link's target as the copy, and the section was written into it.
      - The next uninstall then took the file for its own copy and left the section.
      - Each run after that said "matches the template but was not written by this install".
    - Install's check for "an earlier run backed the file up" took that file for the copy, so
      edits to the section were replaced with no backup.
    - The same applied to `settings.json` linked to its own backup: no copy from before the run
      was left. The record still held the values.

    Fixed: `install.same_file(a, b)`. It uses `os.path.samefile`, which also handles a name
    that differs only in case on macOS or Windows, and it returns True when it cannot tell. It
    is used:
    - in `_backup_name()`, which skips a backup that is the file itself;
    - in install's kept-backup check;
    - in uninstall's `_is_target()`, which replaces pass 11's `resolve()` compare.

    Tests:
    - `test_a_claude_md_linked_to_an_earlier_backup_gets_a_backup_of_its_own`.
    - `test_edits_in_a_section_whose_recorded_backup_is_the_file_itself_are_backed_up`.
    - `test_a_settings_file_linked_to_an_earlier_backup_gets_a_backup_of_its_own`.
    - `test_a_backup_is_kept_when_it_cannot_be_told_whether_claude_md_links_to_it`: it now
      patches `os.path.samefile`; coverage.

    Other hits:
    - `_backup()` itself compares bytes only after `_backup_name()` has chosen the path, so the
      fix covers it.
    - Uninstall's every same-bytes delete already went through `_is_target()`.
    - A hard link to a backup is now also "the same file". The write breaks a hard link (temp
      file and rename), so this only makes one extra backup.

    Prevention: premortem row 64.

C2. Finding: `scripts/ledger.py` took NULs that follow fewer than 4 readable bytes for UTF-16.
    - Examples: a first line of `\n`, `\r\n`, a BOM then `\n`, or `{}\n`.
    - Every run, the dry run included, stopped.
    - This is the third case of one class. Pass 10 fixed NULs after a full line, and pass 11
      fixed NULs after a BOM.

    Fixed: the check is structural.
    - A byte order mark means UTF-16 or UTF-32.
    - Otherwise the first two characters, with their NULs, must match x0y0, 0x0y, x000y000 or
      000x000y, where x and y are not NUL.
    - Both checks apply after an optional UTF-8 BOM, which covers PowerShell 5 appending to an
      empty file Notepad made.
    - A file shorter than two wide characters is UTF-8.

    Tests:
    - The `lf-then-nul`, `crlf-then-nul`, `bom-lf-then-nul` and `short-line-then-nul` cases.
    - `utf-16-le` with no BOM: coverage, which kills a mutant.
    - `utf8-bom-then-utf-16-bom` and `utf8-bom-then-utf-16-le`: they kill two mutants, and the
      first failed under the reviewer's suggested fix.
    - `test_a_file_shorter_than_two_wide_characters_is_read`: coverage of the length check.

    Other hits: no other code tells an encoding by NULs (as pass 10 found).

    Prevention: premortem row 65.

## Info

C3. Finding: mutants of pass 11's code survived the suite.
    - m01 and m02: a condition of the whole-file blank branch dropped.
    - m06 and m07: `_is_file` changed to `exists()` in `finish()`.

    Fixed, coverage only:
    - `test_a_whole_file_record_without_a_backup_on_a_changed_file_is_left_and_kept`.
    - `test_a_whole_file_record_with_a_backup_on_an_emptied_file_names_the_backup`.
    - `test_a_folder_named_as_the_safety_backup_is_no_backup_when_the_section_is_removed`, which
      runs uninstall twice.

    m03 and m04 are near equivalent. m04 is gone with C2's fix.

C4. Finding: after a section was taken out by hand and installed again, `_backup_name()` reused
    the whole-file installer's backup as the copy from before the section. One file then had two
    roles in the record.
    - It was named twice when `CLAUDE.md` was gone.
    - A dry run said "still in" for the backup that the real run deletes.

    Fixed:
    - The legacy delete in `leave()` and the legacy note after `finish()` are skipped when the
      legacy backup is the same file as the copy.
    - The gone branch names each file once.

    Tests:
    - `test_one_backup_in_two_roles_is_named_once_when_claude_md_is_gone`.
    - `test_a_dry_run_of_one_backup_in_two_roles_says_what_the_real_run_does`.
    - `test_a_dry_run_of_one_backup_in_two_roles_lists_the_real_run_changes_once`: the `leave()`
      path, which kills a mutant.

    Prevention: premortem row 66.

Not reproduced, and covered anyway: a link whose target differs from the backup's name only in
case, on a file system that ignores case. `os.path.samefile` compares the file itself.

Still open, outside this PR: `keyline/keyline_lint.py:197` numbers lines with
`str.splitlines()` (from pass 1).
