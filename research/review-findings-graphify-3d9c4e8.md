# Review of branch graphify-ideas at 3d9c4e8 (2026-10-27, fifth pass)

A breaker review of the diff `origin/main...3d9c4e8` by one fresh-context reviewer. It ran on the
session's default model because the Fable usage limit was reached. Its report and repro scripts are
in the session scratchpad, not in the repo: `review5-findings.md` and `review5/run2/` (s1 to s7,
`mutants.py`, `mutate.py`). New ground in this pass: every write and every delete of uninstall
failed in turn (the earlier tests failed only install's writes), 13 more kinds of failed install,
and 55 mutants against the full suite.

The findings of passes 1 to 4 were checked and not reported again
(`research/review-findings-graphify-5a18f22.md`, `-db5cd0c.md`, `-f6ca6ef.md`, `-032a6bf.md`).

Status: every finding is fixed class-wide in the next commit on PR #27.
- pytest: 610 passed, 4 skipped on 3.13 and on 3.10.
- keyline: 35/35.
- pyflakes: clean.
- Every surviving mutant named below except the equivalent ones is now killed (checked one at a
  time with the reviewer's mutants applied to a copy).

Every test named below failed before its fix, except where marked coverage.
Counts: 0 high, 0 medium, 5 low (L1 to L5), 1 low found while fixing (N1), 6 info notes (I1 to I6).

Pattern across the pass: ownership and leftovers at the ends of a run. Three findings (L1, L2, N1)
are uninstall deleting or keeping a backup on the wrong evidence; one (L3) is a section the
installer never wrote taken for its own.

## Low

L1. Finding: uninstall restores CLAUDE.md from the whole-file installer's backup by writing the file,
    then deleting the backup, then writing the record. A failed delete or record write left a backup
    with the same bytes as CLAUDE.md, and every rerun said "no Ideal-Umbrella section" (converted
    record) or "differs from what was installed" (old whole-file record), kept the backup and, in the
    second case, the entry for good.
    Fixed: in the no-section branch a legacy backup that holds the same bytes as CLAUDE.md is deleted
    (the rule already used for the safety backup); in the whole-file branch a backup with the same
    bytes is taken as already restored and deleted; a backup that is gone while CLAUDE.md is not the
    installed file gives one notice and the entry goes.
    Test: `tests/test_failed_writes.py` `test_a_rerun_of_an_uninstall_that_failed_part_way_finishes_it`
    (each write and delete of uninstall failed in turn, for the five kinds of run and an unconverted
    whole-file record; 72 cases).
    Other hits:
    - The safety backup: now deleted when it equals CLAUDE.md whether or not a section is found.
    - The edited backup: already deleted by the same rule (pass 4, D).
    - Settings backups: never deleted by uninstall; each run names its own.
    Prevention: premortem row 34; the test fails deletes as well as writes.

L2. Finding: with a record whose `claude_md` entry is empty (the normal state after an uninstall),
    a second uninstall said "CLAUDE.md differs from what was installed; left as is".
    Fixed: with a record and no entry, the only notice left is "matches the template but was not
    written by this install", given when the file is the template.
    Test: the third run in the L1 test must return `([], [])`.
    Other hits: the same notice after a reinstall whose first write failed; same fix.
    Prevention: premortem row 35.

L3. Finding: a marked section the user added by hand before the first install (README "Manual
    install" step 2) was taken over after a template change: install backed it up as "had edits",
    replaced it and recorded it as its own, and uninstall removed it.
    Fixed: a section found with no record entry is marked `hand_section`. Install updates its rules,
    backs up the user's file and says so; the flag is carried over later runs; uninstall leaves the
    section whole and names the backup. If the user deletes the marker lines, a reinstall wraps the
    copy as the user's (`wrapped`), and uninstall leaves the rules.
    Tests: `test_a_section_added_by_hand_stays_the_users`,
    `test_a_section_added_by_hand_stays_the_users_over_later_runs`,
    `test_a_failed_write_over_a_section_added_by_hand_leaves_nothing`.
    Other hits:
    - `settle_record` falls back to `pending` only when `pending.claude_md` is a dict. An entry for a
      section the install never wrote is now cleared by the safety-equals rule (L1); an entry is not
      dropped on other evidence, because keeping it is the safer error.
    - The wrapped copy (pass 2 finding 3, pass 3 finding 1) is the same class and already handled.
    Prevention: premortem row 36.

L4. Finding: four mutants survived, each hiding a data loss or a broken undo: m07 (edited backup
    deleted without the bytes check), m08 (safety backup deleted without the bytes check), m44 (the
    update path drops `created`), m45 (the update path drops `legacy_backup`).
    Fixed (coverage): `test_a_backup_of_edits_the_user_changed_again_is_kept`,
    `test_the_backup_from_before_the_install_stays_when_the_user_rewrote_the_file`,
    `test_a_created_file_is_still_deleted_after_a_template_change`,
    `test_the_legacy_file_is_restored_after_a_template_change`. Each kills its mutant.
    Other hits: the other fields the update path carries over (`joined`, `wrapped`, `safety_backup`,
    `edited_backup`, `hand_section`) are covered by the pass 2 to 5 tests named in those findings.
    Prevention: the update path lists the carried fields in one tuple.

L5. Finding: a record field of the wrong JSON type (`added_keys` 5 or null, `replaced` null or a
    list, `installed` a list, `deny_added` a string, `created` 5) ended in a TypeError traceback or
    a wrong result (a string `deny_added` matched tools by substring).
    Fixed: `read_record` checks each field's shape, in the record and in `pending`, and stops with
    `"<path>: "<field>" must be <shape>; fix it or delete it first"` before any write.
    Tests: `test_a_record_field_of_the_wrong_type_is_a_one_line_error` (13 cases, tests/test_install.py),
    `test_a_record_field_of_the_wrong_type_stops_uninstall_with_one_line` (tests/test_uninstall.py).
    Other hits: `config/add_to_repo.py` keeps no record; the ledger skips a line it cannot read.
    Prevention: premortem row 37.

N1. Finding (found while killing m50): uninstall turned any name in the record into a path beside
    CLAUDE.md, rejecting only path separators. A record naming `..`, `notes.md`,
    `CLAUDE.md.bak-mine` or `CLAUDE.md.bak-20250101-000000.txt` as the safety, legacy or edited
    backup let uninstall delete that file when it held the same bytes as CLAUDE.md.
    Fixed: `install.backup_of(path, name)` is the only way from a record name to a file and returns
    one only for a name of the installer's form (`<file>.bak-YYYYMMDD-HHMMSS[-N]`); uninstall's
    `_backup_of` calls it.
    Tests: `test_a_file_of_the_users_a_record_names_is_never_deleted` (9 cases; 4 failed on the old
    code), `test_a_record_naming_a_backup_outside_the_folder_names_none`.
    Other hits: install's reuse of a backup and the kept safety backup check go through the same
    function; settings backups are not in the record.
    Prevention: premortem row 38.

## Info

I1. Minor surviving mutants, now killed by coverage tests: m09 (`test_two_copies_of_the_rules_are_not_wrapped`),
    m11 (`test_a_backtick_in_the_info_string_of_a_backtick_fence_opens_none`), m14
    (`test_an_earlier_numbered_backup_with_the_same_bytes_is_reused`), m15
    (`test_a_symlinked_backup_is_never_reused`), m16 (`test_settings_nested_up_to_the_limit_are_read`;
    its old wrapper hid an off-by-one in the test), m33
    (`test_a_whole_file_install_with_crlf_is_still_recognised`), m50 (see N1).

I2. m35: nothing checked that a rewrite keeps the file's mode. Test:
    `test_a_private_settings_file_stays_private`.

I3. `scripts/ledger.py`: a count of hundreds of digits after a small one overflowed the delta after
    the line was appended. Fixed: `MAX_DIGITS = 15` (the `--handoff-at` limit), leading zeros not
    counted. Tests: the 16-digit bad-args case and
    `test_a_count_of_fifteen_digits_after_a_small_one_is_compared`.

I4. `config/CLAUDE.md` holds no fence line; the fence rules assume it. Test:
    `test_the_template_holds_no_fence_line`. Premortem row 39.

I5. If the user copies the edited backup back over CLAUDE.md, uninstall deletes that backup as
    redundant. Its bytes are in CLAUDE.md; nothing is lost. Left as is.

I6. Equivalent or near-equivalent mutants (m04, m06, m29, m32, m41) need no test; m34, m52, m55 were
    invalid.

Still open, outside this PR: `keyline/keyline_lint.py:197` numbers lines with
`str.splitlines()` (from pass 1).
