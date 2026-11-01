# Review of branch graphify-ideas at 59fb4c9 (2026-10-27, seventh pass)

A breaker review of the diff `origin/main...59fb4c9` by one fresh-context reviewer. It ran on the
session's default model because the Fable usage limit was reached again. Its report and repro
scripts are in the session scratchpad, not in the repo: `review7-findings.md` and `review7/`
(s1 run as a non-root user with real file ownership, s2, c1, `mutants.py`, `mutate.py`). New
ground in this pass: real POSIX ownership (a file another user owns), failed writes in an
uninstall without a record, and 22 mutants aimed at pass 6's read-only fix.

The findings of passes 1 to 6 were checked and not reported again
(`research/review-findings-graphify-5a18f22.md`, `-db5cd0c.md`, `-f6ca6ef.md`, `-032a6bf.md`,
`-3d9c4e8.md`, `-1e9664a.md`).

Status: every finding is fixed class-wide in the next commit on PR #27.
- pytest (3.11 and 3.10), keyline, pyflakes and the JSON checks pass.
- The 22 mutants were rerun against the fixed code: 18 are killed. The other 4 (p06, p10, p11,
  p22) are equivalent, as the reviewer found.

Every test named below failed before its fix, except where marked coverage.
Counts: 0 high, 0 medium, 3 low (L1 to L3), 1 info note (I1).

Pattern across the pass: a fix made for Windows (clear the read-only bit, then delete) was wrong
for POSIX, and the simulated-Windows tests could not show it.

## Low

L1. Finding: pass 6's `install.remove()` cleared the read-only bit before the delete. On Linux and
    macOS a delete needs write access to the folder only, but a chmod needs the file's owner.
    A `~/.claude/ballast/context_check.log` owned by root (the hook once ran under `sudo claude`
    with HOME kept) made every uninstall stop with EPERM. By then `settings.json` was rewritten and
    the hook deleted, and every rerun stopped the same way. This is a regression from pass 6.
    Fixed:
    - `install.remove(path)` deletes first.
    - Only when the delete is refused with `PermissionError`, for a file that is not a symlink and
      that `os.access` reports as read-only, does it clear the bit and try once more.
    - If that second delete fails too, the mode is set back.
    Tests:
    - `test_a_file_another_user_owns_is_deleted_without_a_chmod`: `os.chmod` raises EPERM and
      `os.access` says not writable.
    - `test_a_read_only_file_that_still_cannot_be_deleted_keeps_its_mode`.
    Other hits:
    - `_backup` chmods only the new backup, which is the running user's own file.
    - `_write_bytes` and `add_to_repo._write_bytes` chmod only their own temp files.
    - `ballast/state` is unlinked or removed with `rmtree`, and the hook writes it, so it never
      gets a read-only bit.
    - `claude_md.unlink()` stays as is. `CLAUDE.md` is the user's file, and the error names it.
    Prevention: premortem row 43.

L2. Finding: an uninstall without a record (an install from before records existed) used
    `hook.exists() or has_our_hook(settings)` as its evidence of an install. It rewrote
    `settings.json` and deleted the hook file before its `CLAUDE.md` step. When that step failed
    (a full disk), the rerun found no evidence and said "Nothing to undo.", so the section, or the
    whole-file rules, stayed for good. This contradicted README "Undo". The `CLAUDE.md` backup that
    the failed run made was not named either.
    Fixed:
    - The hook file is deleted last, after the `CLAUDE.md` step, so evidence survives any earlier
      failure.
    - The no-record backup is added to the progress as soon as it exists.
    Tests: `test_a_rerun_of_an_uninstall_without_a_record_finishes_it` covers a section, with
    each of the run's writes and deletes failing in turn. (Correction from review 8, L3: its
    "whole file" kind was a wrapped section too, because the install wraps an unmarked copy of the
    rules; the true whole-file kind was added in `-ded6960.md`.) It checks that every
    new backup is named and that the rerun leaves no section, no hook file and no hook entry.
    4 cases failed before the fix; all 24 pass now.
    Other hits:
    - The record-based kinds were already covered by `test_a_rerun_of_an_uninstall_that_failed_part_way_finishes_it`.
    - With a record, the record itself is the evidence, and it is written last.
    Prevention: premortem row 44.

L3. Finding: 12 of 22 mutants of pass 6's fix survived the suite:
    - p01, p02, p12, p14, p15, p17, p18: a call site goes back to a plain `unlink`.
    - p03: the symlink check is dropped.
    - p05, p07, p08, p09: a file the run does not write is refused.
    Fixed (coverage; no code change):
    - `test_uninstall_deletes_read_only_files_of_its_own_in_every_branch[...]` covers five
      states (safety same bytes, converted whole file, converted and restored, whole-file
      restored, edited same bytes). In each, every backup, the hook and the log are read-only under
      Windows semantics. This kills p01, p02, p12, p14, p15, p17 and p18.
    - `test_a_symlink_whose_delete_is_refused_never_has_its_target_chmodded` (p03).
    - `test_a_symlinked_read_only_hook_is_removed_and_its_target_left_read_only`.
    - `test_a_read_only_file_with_nothing_to_write_does_not_stop_install[CLAUDE.md|settings.json|ballast/context_check.py]`
      (p07, p08).
    - `test_a_read_only_claude_md_does_not_stop_install_when_only_the_record_changes` (p05, the
      "CLAUDE.md section recorded" plan).
    - `test_a_read_only_file_with_nothing_to_write_does_not_stop_add_to_repo` (p09).
    Other hits: p06, p10, p11 and p22 are equivalent and need no test:
    - p06: the record is the first write anyway.
    - p10: the hook is add_to_repo's first write.
    - p11: `os.access` follows a symlink.
    - p22: the up-front check covers `_write_bytes`.
    Prevention: premortem row 45.

## Info

I1. Finding: mutant p19 (`(-[0-9]+)?` changed to `(-[0-9]*)?`) survived, so a name with a
    trailing dash would have passed `backup_of`.
    Fixed: the `CLAUDE.md.bak-20250101-000000-` case in
    `test_a_record_naming_a_backup_outside_the_folder_names_none` (coverage).
    Other hits: none. The pattern is used only by `backup_of`.
    Prevention: premortem row 45.

Also fixed: a test comment read `\\d`, where `\d` was meant.

Still open, outside this PR: `keyline/keyline_lint.py:197` numbers lines with
`str.splitlines()` (from pass 1).
