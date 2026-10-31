# Review of branch graphify-ideas at 34cca4d (2026-10-27, fourteenth pass)

A breaker review of the diff `origin/main...34cca4d` by one fresh-context reviewer. It ran on the
session's default model because the Fable usage limit was reached again. Its report and repro
scripts are in the session scratchpad, not in the repo: `review14-findings.md` and `review14/`
(`repro/` e1, e1b, e2, e3, e4, e5, e7; `mut/` with mutants z01-z22 of pass 13's changes and w01-w06
of older untested guards; `sweep/`, the failure sweep run again, which shows only the accepted
notes; `cov/`, a stdlib line-coverage run used to find E5 and E6). New ground in this pass: the
folder walk in `refuse_dangling`, `_absolute`, `_holds`, the D3 guard, the UTF-32 BE BOM.

The findings of passes 1 to 13 were checked and not reported again
(`research/review-findings-graphify-5a18f22.md` to `-7ee698e.md`).

Status: every finding is fixed class-wide in the next commit on PR #27.
- pytest (3.11 and 3.10, 885 passed), keyline, pyflakes, the JSON checks and the CRLF copy pass.
- 15 mutants of the new code (session scratchpad `fix14/mut.py`, v01-v09 and w01-w06) are all
  killed. They cover the linked and legacy-linked decision at the top of `_undo_section`, the
  `if linked` and `legacy_linked` branches, the try around `target()` in both mains, the empty
  `--home` check, the no-record guards for an edited or non-UTF-8 section, and the dry-run lines.

Every test named below failed before its fix, except where marked coverage.
Counts: 0 high, 0 medium, 3 low (E1, E2, E5), 4 info (E3, E4, E6, E7).

Pattern across the pass: pass 13 guarded one use of "a backup that is the file itself" (the first
check in `_undo_section`), as pass 11 had guarded another; the notices, the restore and the legacy
backup each asked the same question again, or did not ask. The fix answers it once.

## Low

E1. Finding: with `CLAUDE.md` a link to a backup, uninstall treated the link's target as a copy.
    - Linked to the record's safety backup (the D3 state): after removing the section it said
      "your CLAUDE.md from before the install is kept in CLAUDE.md.bak-...; it differs ... delete
      it once you no longer need it". Following that left a dangling link and lost the file.
    - Linked to the legacy backup (`ln -s` restore, then install again): it named that file as
      "your CLAUDE.md from before the first install is still in ...", which is the file itself.

    Fixed: decided once at the top of `_undo_section`. A safety or legacy backup that
    `CLAUDE.md` links to is the file, not a backup: it is never compared with the file, restored
    from, deleted or named as kept. A linked legacy file holding nothing but the section is left
    as is with a note naming it (removing the section would empty the user's own file).

    Tests: `test_a_claude_md_linked_to_its_own_backup_keeps_the_backup` (no note names the backup),
    the D3 test (no note names the backup),
    `test_a_claude_md_linked_to_the_legacy_backup_and_installed_again_has_the_section_removed[own-text|blank]`.

    Other hits: the `hand_section`, `differs` and `finish()` notes and `restore()` each had their
    own `_is_target` guard or none; all now read the one decision, and the guards are gone.

    Prevention: premortem row 71. README "Undo" says a linked backup is the file.

E2. Finding: `target()` ran outside `main()`'s try in install and uninstall. A
    `CLAUDE_CONFIG_DIR` or `--home` through a folder the user may not look in gave a traceback
    from `_absolute`'s `exists()` (a regression from pass 13; 7ee698e gave a one-line error).

    Fixed: both mains report `target()` errors (`ValueError`, `OSError`) in one line through
    `report_error(..., before_writes=True)`.

    Tests: `test_a_config_dir_that_cannot_be_looked_at_is_a_one_line_error[env|home x install|uninstall]`.

    Other hits: none; `target()` is the only call before the try in either main.

    Prevention: premortem row 72.

E5. Finding: no test reached the no-record guards that leave `CLAUDE.md` as is when the section
    differs from the template or the file is not UTF-8 (mutants w01, w02 survived; under them the
    section was removed and undecodable bytes became U+FFFD).

    Fixed: tests only; the code was right.

    Tests: `test_without_a_record_a_section_of_the_users_is_left_as_is[edited|not-utf-8]`
    (coverage).

    Prevention: premortem row 73.

## Info

E3. Finding: the documented `ln -s` way back (CLAUDE.md linked to the unchanged safety backup,
    no section) got a new "CLAUDE.md has no Ideal-Umbrella section; left as is" note, a side
    effect of pass 13's D3 fix.

    Fixed: the `if linked` branch finishes without a note.

    Tests: `test_a_claude_md_linked_to_its_own_backup_keeps_the_backup` asserts no "no
    Ideal-Umbrella section" note.

E4. Finding: mutant z14 (`not install._is_link(claude_md)` for `not _is_target(...)` on the D3
    guard) survived.

    Fixed: the guard is gone (E1); `test_a_failed_write_over_a_section_added_by_hand_leaves_nothing`
    gains a `linked` kind (CLAUDE.md a link to a dotfiles file), which kills v01, the analogue of
    z14 on the new decision. z04 (`return path` for `abspath`), z05 (never resolve; changes only
    the hook path through a symlinked home) and z22 (`_absolute(Path.home())`) are equivalent or
    near-equivalent.

    Follow-up: the `linked` kind first wrote the dotfiles file with `write_text`, which writes
    CRLF on Windows, and compared bytes (Windows CI red on 4bbd9d2). It writes bytes now; the
    whole suite passes with `write_text` forced to CRLF, so no other test depends on it.

E6. Finding: the dry-run change lines were not tested (w03-w05), and `test_dry_run_writes_nothing`
    saw only regular files, so a dry run that removed the state link passed (w06).

    Fixed: tests only.

    Tests: `test_a_dry_run_lists_what_the_real_run_does_and_writes_nothing[no-record-section|no-record-rules|whole-file-restore]`;
    `test_dry_run_writes_nothing` compares a `tree()` that records links as links.

E7. Finding: `--home ""` (a script's unset variable) fell back to the real config folder. It
    predates this PR.

    Fixed: `target()` raises `ValueError("--home is empty")`, reported in one line (E2).

    Tests: `test_an_empty_home_argument_is_refused[install|uninstall]`.

    Prevention: premortem row 72.
