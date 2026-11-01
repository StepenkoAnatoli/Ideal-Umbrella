# Review of branch graphify-ideas at 1e9664a (2026-10-27, sixth pass)

A breaker review of the diff `origin/main...1e9664a` by one fresh-context reviewer. It ran on the
session's default model because the Fable usage limit was reached again. Its report and repro
scripts are in the session scratchpad, not in the repo: `review6-findings.md` and `review6/`
(s2 to s4, f1, `mutants.py`, `mutate.py`). New ground in this pass: read-only files under Windows
semantics (simulated, as the sandbox runs as root), 40 mutants against the full suite, and 594
wrong-typed record fields across install, uninstall and verify.

The findings of passes 1 to 5 were checked and not reported again
(`research/review-findings-graphify-5a18f22.md`, `-db5cd0c.md`, `-f6ca6ef.md`, `-032a6bf.md`,
`-3d9c4e8.md`); the pass 5 repros were rerun and still hold.

Status: every finding is fixed class-wide in the next commit on PR #27.
- pytest, keyline, pyflakes and the JSON checks: see the commit's PR checklist.
- Every surviving mutant named below is now killed (checked one at a time on a copy).

Every test named below failed before its fix, except where marked coverage.
Counts: 0 high, 0 medium, 3 low (L1 to L3), 5 info notes (I1 to I5).

Pattern across the pass: Windows semantics the Linux CI cannot show (a read-only file cannot be
deleted there), and tests that pinned a result but not the evidence it rests on.

## Low

L1. Finding: install refused a read-only `CLAUDE.md` only at its own write, after it had written
    the record and the hook and made a backup. `_backup` copied the mode with `shutil.copystat`,
    so the backup was read-only too; once the user made `CLAUDE.md` writable and installed again,
    that backup was the record's `safety_backup`, and on Windows, where a read-only file cannot be
    deleted, every uninstall stopped at deleting it (after rewriting `settings.json`, deleting the
    hook and restoring `CLAUDE.md`). README said an install that fails while checking changes
    nothing and that a stopped uninstall is finished by a rerun; neither held.
    Fixed:
    - `install.refuse_read_only(path)`: `install()` checks every file it will write (record, hook,
      `CLAUDE.md`, `settings.json`) before the first write; `_write_bytes` uses the same check.
    - `_backup` makes the backup owner-writable after `copystat` (dates kept, read-only bit not).
    - `install.remove(path)`: clears a read-only bit, then deletes; uninstall deletes every backup,
      the hook and the log through it (a symlink is removed, its target left).
    - `add_to_repo.py` checks the repository's hook and `settings.json` the same way before its
      first write.
    Tests (`tests/test_read_only.py`, Windows semantics simulated by patching `os.access` and
    `Path.unlink`, so they run as root on CI too):
    - `test_a_read_only_file_stops_install_before_any_write` (4 files; 3 failed on the old code,
      the record case is coverage: it was already refused first).
    - `test_a_read_only_file_with_nothing_to_write_does_not_stop_install` (coverage).
    - `test_a_backup_of_a_read_only_file_can_be_deleted`.
    - `test_uninstall_deletes_a_read_only_backup_of_its_own[safety|legacy]`.
    - `test_a_read_only_settings_file_stops_add_to_repo_before_any_write`.
    - `test_an_uninstall_stopped_by_a_read_only_file_is_finished_once_it_is_writable` (3 files,
      coverage).
    Other hits:
    - Uninstall does not check write access up front: which files it leaves as they are depends
      on what it finds as it works through them, and refusing a read-only `CLAUDE.md` it would
      leave alone would block the undo for nothing. A stop part way is finished by a rerun once
      the file is writable (the last test above).
    - `claude_md.unlink()` in uninstall is left as is: `CLAUDE.md` is the user's file, and a
      read-only bit on it is their choice; the error names it.
    - `ballast/state` is unlinked as a link or removed with `shutil.rmtree`; the hook's own state
      files are written by the hook, never made read-only.
    - The install record was already refused before any other write (it is written first).
    Prevention: premortem row 40; the read-only tests no longer depend on a non-root user.

L2. Finding: four mutants survived, each hiding a data loss, a broken undo or a traceback:
    n01 (uninstall deletes the whole-file installer's backup without the bytes check, in the
    no-section branch), n12 and n13 (`plan_claude_md` keeps a stale `hand_section` on an append or
    a create, so uninstall leaves the section, or the created file), n32 (`ledger.py` divides by a
    previous value of 0, after the line was appended).
    Fixed (coverage):
    - `test_the_old_installers_backup_stays_when_the_user_rewrote_the_file` (n01).
    - `test_a_section_the_installer_adds_after_a_hand_section_is_gone_is_its_own[mine\n|None]`
      (n12, n13).
    - `test_a_count_after_a_zero_is_compared_without_a_percentage` (n32).
    Other hits: the other 36 of 40 mutants were killed; the minor survivors are I1.
    Prevention: premortem row 41.

L3. Finding: README said a second uninstall "only says 'Nothing to undo.'"; it also prints a note
    for anything it leaves as is (a value the user changed, a section it did not write).
    Fixed: README "Undo" says "Nothing to undo." plus such notes. Nothing in the code changed.
    Other hits: README "Undo" and the install bullet on checks were reread against L1's fix and
    updated (a read-only file is refused before the first write; a read-only backup no longer
    blocks uninstall).

## Info

I1. Minor survivors, now killed by coverage tests: n24 (`add_to_repo.py --handoff-at` digit bound
    15 changed to 16: `test_the_handoff_value_takes_at_most_fifteen_digits`), n31 (ledger's
    `isascii` check dropped: the Arabic-digit bad-args case in
    `test_bad_arguments_exit_2_and_write_nothing`). n08 only loses a note; no test.

I2. `\d` in `_BACKUP_NAME` matched digits of other scripts, so `CLAUDE.md.bak-` with Arabic digits
    passed `backup_of`. Fixed: `[0-9]`. Test: the Arabic-digit case in
    `test_a_record_naming_a_backup_outside_the_folder_names_none`. Other hits: `ledger.py` and
    `add_to_repo.py` already require `isascii()`; the keyline `\d` patterns match text in prose,
    not names of files to delete, and are left. Premortem row 42.

I3. When a later install names a new `safety_backup`, the record drops the earlier one; that
    backup is never named on uninstall. It is not deleted, only unreported. Left as is.

I4. 594 wrong-typed record fields across install, uninstall and verify: each a one-line error or
    a correct result, no traceback. No change.

I5. `ledger.py`, `add_to_repo.py` and the hand-off docs matched the README and CHANGELOG. No change.

Still open, outside this PR: `keyline/keyline_lint.py:197` numbers lines with
`str.splitlines()` (from pass 1).
