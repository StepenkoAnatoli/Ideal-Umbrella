# Review of branch graphify-ideas at 5a18f22 (2026-10-27, first pass)

Breaker review of the diff `origin/main...5a18f22` (PR #27: marker section in
`~/.claude/CLAUDE.md`, `scripts/ledger.py`, `add_to_repo.py --handoff-at`, drift tests, CI,
CONTRIBUTING). One fresh-context reviewer; its report and repro scripts are in the session
scratchpad (`review1-findings.md`, `review1/s*.py`, not in the repo). Baseline: pytest 326
passed, 4 skipped; keyline suite 35/35; pyflakes clean; CI green on all four cells.

Status: all 9 fixed class-wide in the next commit on PR #27 (pytest 352 passed, 4 skipped on
3.13 and 3.10; keyline suite 35/35; pyflakes clean). Every test named below failed before its
fix. Counts: 0 high, 2 medium, 6 low, 1 info.

Pattern across the pass: the marker section was specified line by line ("a whole line is a
marker") but not by what surrounds a line (a code fence, a BOM before line 1), and the record
format change was handled on the paths that write CLAUDE.md but not on the path that writes
nothing. The ledger relied on `splitlines()` and `except ValueError` as if they matched what
`json.dumps` writes and what `json.loads` raises; neither does.

## Medium

1. A marker pair inside a code fence in the user's own text was taken for the section.
   `config/install.py` `find_section` matched whole lines with no notion of fences, so a
   fenced example of the managed block was "updated" (backed up as edited, its lines replaced
   by the rules) and then removed by uninstall, losing the example lines from the live file.
   Fixed: `find_section` ignores marker lines inside a closed ``` or ~~~ fence (CommonMark:
   up to 3 spaces of indent, a closing fence of the same character at least as long, no
   backtick in a backtick fence's info string). A fence never closed hides nothing, so the
   section install appends after a stray fence line is still found on the next run. One
   function serves install, `--verify-only` and uninstall, so all three changed together.
   Tests: `tests/test_claude_md_section.py`
   `test_marker_lines_inside_a_code_fence_are_an_example_not_the_section` (backticks, tildes,
   a longer fence holding a shorter one, a lone begin marker in a fence; install, verify,
   reinstall, uninstall all byte-exact) and `test_a_fence_never_closed_does_not_hide_the_section`.
   Other hits: none; `find_section` is the only marker parser (`config/cloud-setup.sh` writes
   the whole file). Prevention: README states that a marker line inside a code fence is an
   example, and the premortem has the story (row 16).

2. An old whole-file record was never migrated when the file already held the section.
   `plan_claude_md` returned None as soon as the section equalled the template, before looking
   at the record's format, so a user who put the markers around the whole-file install by hand
   kept a whole-file record; uninstall then compared the whole file, refused, and never gave
   back the file the old install had moved aside.
   Fixed: with an old-format record and the section already equal, the plan has no text and a
   migrated entry (`legacy_backup`, `created` = the old install had no backup); `install()`
   writes only the record and reports "CLAUDE.md section recorded".
   Tests: `test_a_hand_wrapped_old_install_is_migrated_and_undone` (legacy file restored,
   second install changes nothing) and `test_a_hand_wrapped_old_install_that_created_the_file_is_deleted`.
   Other hits: class "a stale record survives a run that writes nothing". `_merge_record`
   keeps the old `claude_md` entry only when the new run has none, which is now only the case
   for a record that is already in the section format. The settings part of the record
   (`installed`) has one format. Prevention: premortem row 17.

## Low

3. A UTF-8 BOM was dropped when the begin marker was line 1: the section's start offset was 0,
   so the BOM went with the section on update and on uninstall.
   Fixed: the BOM stays outside the section (start offset 1). Uninstall treats a rest that is
   only a BOM and whitespace as empty (`_blank`), so a created file the user re-saved with a
   BOM is still deleted and a legacy backup still restored. The same BOM stopped an unmarked
   copy of the rules at the start of the file from being wrapped (it was appended a second
   time); the copy may now start after a BOM.
   Tests: `test_a_bom_before_the_section_is_kept`,
   `test_a_created_file_holding_a_bom_and_the_section_is_deleted`,
   `test_a_hand_copy_after_a_bom_is_wrapped_not_added_again`,
   `test_an_old_install_saved_with_a_bom_is_migrated_and_undone`.
   Other hits: both `.strip()` emptiness checks in `config/uninstall.py` now use `_blank`; no
   other emptiness check reads CLAUDE.md.

4. `scripts/ledger.py` read lines with `str.splitlines()`, which also splits on U+2028,
   U+2029, NEL, form feed and vertical tab; `json.dumps(ensure_ascii=False)` leaves those raw.
   A note holding one made the next run skip two "unreadable" lines and lose the delta, and
   shifted the line numbers the README cites.
   Fixed: lines end at `\n` only, in `ledger.py` and in `fixed_load_drift`
   (`tests/test_docs_match_source.py`); the test helper reads the same way.
   Tests: `tests/test_ledger.py` `test_a_line_separator_in_a_note_does_not_split_the_line`,
   `tests/test_docs_match_source.py` `test_fixed_load_line_numbers_count_newlines_only`.
   Other hits: `hooks/context_check.py` splits bytes (`bytes.splitlines()` splits only on
   `\n`, `\r\n` and `\r`, and JSON escapes a raw `\r`), so it is not affected.
   `keyline/keyline_lint.py:197` numbers lines with `str.splitlines()` for its findings, so a
   U+2028 in a linted file shifts the reported line; left as is (keyline is outside this PR,
   and the lint reads prose files, not JSON lines).

5. Three tracebacks in `scripts/ledger.py`, whose docstring says a bad file or argument is a
   one-line error: a `--note` holding a byte that is not UTF-8 (a lone surrogate) raised
   UnicodeEncodeError; a `--file` path with such a byte raised UnicodeEncodeError when printed,
   after the line was written; a line nested 100000 levels deep raised RecursionError, which
   `except ValueError` does not catch.
   Fixed: `--note` and `--cc-version` that are not valid UTF-8 are a usage error (exit 2,
   nothing written); stdout and stderr print with `errors="backslashreplace"`; RecursionError
   is skipped like any unreadable line.
   Tests: `test_text_that_is_not_unicode_is_a_usage_error` (both options),
   `test_a_file_name_that_is_not_utf8_is_printed_not_a_traceback` (Linux only),
   `test_a_deeply_nested_hand_edit_is_skipped_not_a_traceback`.
   Other hits (RecursionError, fixed): `config/install.py` `_read_json` and `read_record`,
   `config/add_to_repo.py` `_read_json` (now the one-line "nested too deeply" error before
   any write), `hooks/context_check.py` `context_tokens` (the line is skipped; it used to end
   the hook run in its catch-all, so no reminder), and the transcript readers
   `scripts/toolresult_share.py`, `unused_tools.py` (two), `usage_breakdown.py`,
   `usertext_split.py`, `usertext_top.py`, `plugin_cost.py` (two). The hook's stdin read in
   `run()` is left to `main()`'s catch-all. Tests: `tests/test_install.py`
   `test_json_nested_too_deep_is_a_one_line_error` (settings and record),
   `tests/test_add_to_repo.py` `test_json_nested_too_deep_is_rejected_without_writing`,
   `tests/test_context_check.py` `test_a_transcript_line_nested_too_deep_is_skipped`.
   Prevention: `tests/test_source_rules.py` rule 6, every `json.load`/`json.loads` runs under
   a `try` that handles RecursionError (or Exception); it listed the 12 sites above before the
   fix.

6. Deleting only the two marker lines turned the installed rules into the user's own: the
   next install wrapped them with `wrapped: true` (because a section-format record existed),
   so uninstall removed only the marker lines and left the rules; it also made a second backup
   and kept recording the first.
   Fixed: an unmarked copy is the user's (`wrapped`, backed up) only when there is no record;
   with a record it is the installer's, gets no backup (only marker lines are added) and keeps
   the recorded `joined` separator. When a new "before the section" backup is made, the record
   now names it instead of keeping the earlier name, since uninstall compares that backup with
   the file it gives back.
   Tests: `test_removing_only_the_marker_lines_keeps_the_rules_ours` (uninstall gives back
   `mine\n`, no backup left), `test_a_new_backup_before_the_section_is_added_again_is_the_one_recorded`.
   Other hits: the old-format wrap (`test_old_install_edited_by_the_user_is_wrapped_not_duplicated`)
   used to make a backup that no uninstall removes; it is a record case too and now makes none.

7. A CLAUDE.md write that failed after its backup left an orphan: the rerun made a second
   backup and recorded only that one.
   Fixed: `_backup` returns an existing `<name>.bak-*` beside the file with the same bytes
   instead of making another (regular files only, not symlinks). It serves every backup
   (settings.json, CLAUDE.md, the uninstall's copies), so a run repeated after any failure
   adds no duplicate.
   Test: `test_a_failed_write_after_the_backup_leaves_no_orphan_backup` (disk-full on the
   CLAUDE.md write, rerun, uninstall: no backup left).
   Other hits: settings.json backups are never removed by uninstall, so a failed run used to
   leave identical copies there too; covered by the same change.

8. Uninstall was silent about a section that differs from the template when the record has no
   CLAUDE.md entry (the section was there before the install). The equal case had a notice.
   Fixed: a notice says the section differs from `config/CLAUDE.md`, was not written by this
   install, and is left as is.
   Test: `test_uninstall_reports_an_edited_section_this_install_did_not_write`.
   Other hits: the no-record branch below it already reports both cases.

## Info

9. `research/premortem-marker-section.md` said "about 16 tokens" for the marker lines (README
   and tiktoken: about 18) and named `tests/test_install.py` / `tests/test_uninstall.py` as
   the home of the guards (they are in `tests/test_claude_md_section.py`).
   Fixed: both corrected; rows 16-20 added for findings 1, 2, 3, 6 and 7.
