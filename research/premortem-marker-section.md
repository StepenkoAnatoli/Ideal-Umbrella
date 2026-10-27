# Premortem: marker-delimited section in ~/.claude/CLAUDE.md (2026-10-27)

Change: `config/install.py` stops replacing `~/.claude/CLAUDE.md` wholesale and manages only a
section between two exact marker lines; `config/uninstall.py` removes only that section;
`--verify-only` compares only that section. Written before the code, as the brief asks
(`first-pass:premortem` is not installed in this session, so this is done by hand).

"It is a month later and the change hurt someone. What happened?"

| # | Failure story | Likelihood | Guard (test name in tests/test_claude_md_section.py) |
|---|---|---|---|
| 1 | The section boundary is the next `# ` heading (graphify's design); `config/CLAUDE.md` itself has two H1 headings, so install found half a section and appended a second copy every run. | certain with heading markers | Explicit begin/end comment lines, not headings. `test_reinstall_is_idempotent_with_user_text` |
| 2 | A user line that merely contains the marker text (a note quoting it) was taken as the marker and their text between was deleted (graphify issue #2062: substring match). | medium | Whole-line match only. `test_a_line_that_mentions_the_marker_is_not_one` |
| 3 | A file with a begin marker and no end marker (user deleted a line) made install delete from the marker to EOF. | medium | Unbalanced, repeated or reversed markers are an error before anything is written; verify reports it. `test_broken_markers_stop_install_before_any_write`, uninstall twin |
| 4 | Users of the old whole-file install re-ran install: the file had no markers, so install appended a second copy of the rules under the first. | high (every existing user) | Old-format record whose sha256 equals the file: the whole file is ours, replaced by the section, and the old backup is kept as `legacy_backup`. `test_old_whole_file_install_is_migrated` |
| 5 | After migration, uninstall no longer restored the backup the old install made, so the user's original CLAUDE.md stayed in a `.bak` file forever. | high | Uninstall restores `legacy_backup` when nothing but the section is left. `test_uninstall_after_migration_restores_the_old_backup` |
| 6 | Install appended with a blank line; uninstall removed the section but not the blank line, so every install/uninstall cycle grew the file. | high | The separator added is recorded (`joined`) and removed. `test_install_then_uninstall_restores_user_text_byte_for_byte` |
| 7 | A CRLF file got LF section lines, then compared as "edited" on the next run (backup every run). | medium (Windows) | Section written with the file's line ending; comparisons and hashes on LF-normalised text. `test_crlf_file_keeps_crlf_and_stays_idempotent` |
| 8 | A user edited inside the section; install silently overwrote their edit. | medium | Edited section (hash differs from the record) is backed up before it is replaced, with a notice. `test_edited_section_is_backed_up_before_replace` |
| 9 | Uninstall removed a section the user had edited. | medium | Section whose hash differs from the record is left with a notice. `test_uninstall_leaves_an_edited_section` |
| 10 | Uninstall deleted a CLAUDE.md that existed before install and was empty, or deleted user text. | low | Delete only when the install created the file (`created`) and nothing but whitespace is left. `test_uninstall_deletes_only_a_file_install_created` |
| 11 | Halfway state: CLAUDE.md written, settings.json write failed, record not written; the next install saw the section as present and unrecorded, and uninstall left it as "not ours". | medium | The full record is written first, before the hook, CLAUDE.md and settings.json (review 2, findings 4 and 5: written after CLAUDE.md it still left gaps). Undoing a change that never landed is harmless. `tests/test_failed_writes.py` fails each write in turn; `test_a_failed_settings_write_after_claude_md_still_lets_uninstall_restore_it` |
| 12 | `--verify-only` passed on an old whole-file install, so users never migrated; or failed on any user line. | medium | Verify needs the section; text outside it is ignored. `test_verify_ignores_user_text_outside_the_section`, `test_verify_fails_without_a_section` |
| 13 | Section at EOF without a trailing newline was seen as edited. | low | Canonical form adds the final newline before comparing. `test_section_without_final_newline_is_ours` |
| 14 | A marker line with trailing spaces (editor) stopped matching. | low | Trailing whitespace ignored on marker lines. Covered by #2 test |
| 15 | The marker lines cost tokens in every session. | certain, small | Two short HTML comment lines, about 18 tokens (tiktoken `cl100k_base`); stated in the README. |
| 16 | A fenced example of the marker lines in the user's own text was taken for the section, replaced, and removed by uninstall (review 1, finding 1). | low | Marker lines inside a closed ``` or ~~~ fence are ignored; a fence never closed hides nothing. `test_marker_lines_inside_a_code_fence_are_an_example_not_the_section`, `test_a_fence_never_closed_does_not_hide_the_section` |
| 17 | A whole-file install the user wrapped in the markers by hand kept its old record, so uninstall refused and never restored the old backup (finding 2). | low | The record is migrated even when CLAUDE.md needs no write. `test_a_hand_wrapped_old_install_is_migrated_and_undone` |
| 18 | A BOM before a begin marker on line 1 was dropped on update and uninstall (finding 3). | low | The BOM stays outside the section; a rest of only a BOM counts as empty. `test_a_bom_before_the_section_is_kept` |
| 19 | The user deleted only the marker lines; the next install wrapped the rules as the user's own, so uninstall left them (finding 6). | low | With a record, an unmarked copy is the installer's. `test_removing_only_the_marker_lines_keeps_the_rules_ours` |
| 20 | A write that failed after the backup left a backup no record names (finding 7). | low | A backup with the same bytes is reused. `test_a_failed_write_after_the_backup_leaves_no_orphan_backup` |
| 21 | A copy of the rules inside a code fence was wrapped in markers on every install (review 2, finding 1). | low | The wrap path uses the same fence map as `find_section`. `test_a_fenced_copy_of_the_rules_is_an_example_not_wrapped` |
| 22 | A fence never closed hid a later fence, or a stray fence closed below the section hid the section (finding 2). | low | An unclosed opener is ordinary text; a fenced pair holding exactly the recorded section is still the section. `test_a_fence_closed_only_after_the_section_does_not_hide_it`, `a-fence-never-closed-before-a-fenced-example` |
| 23 | A template change made the user's wrapped copy the installer's, and uninstall removed it (finding 3). | low | `wrapped` is carried over and the update names the backup. `test_a_wrapped_copy_stays_the_users_after_the_template_changes` |
| 24 | settings.json that reads but cannot be written back (too deep, lone surrogate) failed after other writes (findings 6, 7). | low | Checked right after the read; source rule 7. `test_settings_that_cannot_be_written_back_stop_before_any_write` |
| 25 | A `.bak-` file the user named was reused as ours and deleted (finding 8). | low | Only `.bak-YYYYMMDD-HHMMSS[-N]` names are reused. `test_a_backup_the_user_named_is_never_taken_for_ours` |

Not changed on purpose: `config/cloud-setup.sh` still writes the whole file with `cat >`, because
a cloud machine starts empty and is discarded; the drift test keeps it equal to the template.
