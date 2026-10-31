# Review of branch graphify-ideas at db5cd0c (2026-10-27, second pass)

Breaker review of the diff `origin/main...db5cd0c` (the review started at ed72fda; db5cd0c
changes only the resume point). One fresh-context reviewer, on the session's default model
because the Fable usage limit was reached; its report and repro scripts are in the session
scratchpad (`review2-findings.md`, `review2/s*.py`, not in the repo). Baseline: pytest 352
passed, 4 skipped; keyline 35/35; pyflakes clean. The 9 findings of pass 1
(`research/review-findings-graphify-5a18f22.md`) were checked and not reported again.

Status: all fixed class-wide in the next commit on PR #27 (pytest 382 passed, 4 skipped on
3.13 and 3.10; keyline 35/35; pyflakes clean; every review-2 repro script and the 1500-file
fuzz now pass). Every test named below failed before its fix, except where marked coverage.
Counts: 0 high, 1 medium, 7 low, 5 info.

Pattern across the pass: a rule fixed in one function (fences in `find_section`, the field list
of the record) was not applied to the other code doing the same job (the wrap path, the copy of
`wrapped`). Writes were ordered so that the last one to land named the earlier ones; any failure
in between stranded them. And "read it" was taken to mean "can write it back": JSON that loads
can still fail to dump.

## Medium

1. Finding: a copy of the rules inside a code fence got a new marker pair on every install. The
   wrap path in `plan_claude_md` searched with `current.find(copy)` and no fence check, so the
   user's fenced example was wrapped, `--verify-only` then reported no section, and every rerun
   added another pair inside the fence.
   Fixed: `_unfenced_copy` wraps only a copy that starts a line and has no line in the fence map
   `find_section` uses (`_fenced`, over the same BOM-stripped lines from `_lines`), and only when
   exactly one such copy exists; otherwise the section is appended. The search counts lines
   incrementally (200000 one-line matches: 0.03 s; the first version took 25 s).
   Tests: `tests/test_claude_md_section.py` `test_a_fenced_copy_of_the_rules_is_an_example_not_wrapped`
   (rules alone, and rules with marker lines, in a fence).
   Other hits: `find_section` and the wrap path are the only searches of CLAUDE.md; uninstall
   and verify go through `find_section`.
   Prevention: premortem row 21; README says a fenced copy is an example.

## Low

2. Finding: the fence rule depended on text far away. (a) A stray ``` line before the section
   paired with a code block the user added below it, so the section looked fenced: every
   install appended another, uninstall found none. (b) An unclosed ``` made `_fenced` skip a
   closed ~~~ fence after it, so a fenced example was taken for the section again (pass-1
   finding 1 by another route).
   Fixed: (b) an opening fence line that is never closed is ordinary text and the scan goes on
   at the next line (a table of the longest closer after each fence keeps it linear). (a)
   `find_section(text, recorded)`: when every marker line is fenced, a single begin/end pair
   (fences ignored) whose body hashes to the record's section sha256 is the section. Install,
   uninstall and `--verify-only` pass the recorded hash (verify reads the record leniently).
   Tests: the `a-fence-never-closed-before-a-fenced-example` case of
   `test_marker_lines_inside_a_code_fence_are_an_example_not_the_section`,
   `test_a_fence_closed_only_after_the_section_does_not_hide_it`.
   Other hits: none; one fence map serves all three tools.
   Prevention: premortem row 22; README states the unclosed-fence rule.

3. Finding: `wrapped` was lost when the template changed (the record update copied `created`,
   `legacy_backup` and `safety_backup` only), so uninstall removed the user's own copy of the
   rules and no message named the backup holding it.
   Fixed: `wrapped` is carried over; updating a wrapped section adds a notice that the section
   was the user's copy, now holds the new rules, which uninstall leaves, and names the backup of
   the file from before the first install. A new section (appended, or a file created) drops a
   stale `wrapped`.
   Test: `test_a_wrapped_copy_stays_the_users_after_the_template_changes`.
   Other hits: the record fields are now copied in one place; `joined` is copied per path, as
   before.
   Prevention: premortem row 23.

4. Finding: CLAUDE.md was written before the record, so a failed record write left a section
   that no record named: the rerun saw it as present, uninstall as "not written by this install".
5. Finding: settings.json was written before the final record; a failed record write left the
   keys and deny tools with no record of them, and the rerun wrote nothing.
   Fixed (4 and 5, one class): the full merged record is written first (hook, CLAUDE.md and
   settings changes, backup names decided by `_backup_name` before the copy), then the hook,
   the CLAUDE.md backup and file, the settings backup and file. A change the record names that
   never landed is harmless to undo: a replaced key that still holds its old value is skipped
   without a notice, an added key that is missing is skipped, and a CLAUDE.md with no section
   whose bytes equal the recorded backup has that backup deleted. "install record written" is
   in the progress list an error prints.
   Tests: `tests/test_failed_writes.py` fails each write in turn, then uninstalls (directly, and
   after a rerun) and requires the files from before, no backup left and no "not the installed
   value" notice; `tests/test_install.py`
   `test_a_record_written_before_a_failed_settings_write_undoes_cleanly` replaces
   `test_record_is_written_after_settings`, which asserted the old order.
   Other hits: `config/uninstall.py` writes settings.json before its leftover record; a failed
   record write there leaves the old record, and a second uninstall skips keys already undone,
   so it finishes. `config/add_to_repo.py` writes no record.
   Prevention: premortem row 11 rewritten.

6. Finding: settings.json nested 1000+ levels loads on Python 3.12 but `json.dumps(indent=2)`
   raises RecursionError; install, uninstall and add_to_repo printed a traceback after writing
   the hook (and CLAUDE.md, and backups).
7. Finding: a lone surrogate (`"\ud800"`, valid JSON) made the settings write raise
   UnicodeEncodeError after the other writes, and `main()` printed "nothing written" for it.
   Fixed (6 and 7): `_check_json` walks the data iteratively right after every JSON read in
   `config/` (`install._read_json`, `read_record`, `add_to_repo._read_json`) and raises the
   one-line error for more than 100 levels or a string or key UTF-8 cannot encode, before any
   write. The class "nothing written after writes": all three `main()` functions say "nothing
   written" only for a ValueError with an empty progress list; otherwise they print what was
   done before the error (`install.report_error`, shared by uninstall).
   Tests: `tests/test_install.py` `test_settings_that_cannot_be_written_back_stop_before_any_write`
   and `test_an_error_after_a_write_does_not_say_nothing_was_written`; `tests/test_uninstall.py`
   `test_settings_that_cannot_be_written_back_stop_the_undo_before_any_write`;
   `tests/test_add_to_repo.py` `test_settings_that_cannot_be_written_back_stop_before_any_write`.
   Other hits: `scripts/ledger.py` dumps only the entry built from its arguments (surrogates
   already rejected); the transcript scripts and the hook do not write back what they read.
   `merge_settings` copies template values only.
   Prevention: `tests/test_source_rules.py` rule 7, every function in `config/` that calls
   `json.load`/`json.loads` also calls `_check_json` (it lists `install._read_json`,
   `install.read_record` and `add_to_repo._read_json` on the code before the fix). Premortem
   row 24.

8. Finding: `_backup` reused any `<name>.bak-*` with the same bytes, including a file the user
   named, which uninstall then deleted.
   Fixed: only names the installer gives (`<name>.bak-YYYYMMDD-HHMMSS` with an optional `-N`)
   are reused.
   Test: `test_a_backup_the_user_named_is_never_taken_for_ours`.
   Other hits: the same function serves the settings.json backups, covered by the same change.
   Prevention: premortem row 25; README names the backup pattern.

## Info

I1. Finding: uninstall said nothing when CLAUDE.md was gone but the record named the old
    whole-file backup. Fixed: a notice names it. Test:
    `test_uninstall_names_the_legacy_backup_when_claude_md_is_gone`.
I2. Finding: README Undo said the blank line before the section always goes; it goes only when
    nothing follows the section. Fixed: the sentence says so (behaviour unchanged, tested by
    `test_text_added_after_the_section_is_kept_and_not_glued`).
I3. Finding: `test_failed_restore_never_leaves_a_truncated_claude_md` patched a copy that no
    longer happens. Fixed: renamed `test_a_failed_section_removal_never_leaves_a_truncated_claude_md`
    without the dead patch; coverage for the legacy restore failing:
    `test_a_failed_restore_of_the_legacy_backup_keeps_both_files` (passes; coverage only).
I4. Finding: CONTRIBUTING.md put resume points in `notes/` or `plans/`, which do not exist.
    Fixed: resume points live in `research/*-progress.md`; the keyline folders are named as such.
I5. (a) `--handoff-at` with 5000 digits printed Python's digit-limit message. Fixed: more than 15
    significant digits is "--handoff-at ... is too large". Test:
    `test_a_huge_handoff_value_is_a_plain_usage_error`. Other hit: `scripts/ledger.py` `_count`
    has the same `int()` on digits and is reached through argparse, which reports the error as
    a usage line; left as is. (b) The old-format wrap path set `created=False` whatever the old
    record said. Fixed: every old-format path sets `created` from the old record (no backup
    means the old install created the file). Test:
    `test_an_old_install_that_created_the_file_and_was_wrapped_is_deleted`.

Still open, outside this PR: `keyline/keyline_lint.py:197` numbers lines with
`str.splitlines()` (from pass 1).
