# Review of branch graphify-ideas at 7ee698e (2026-10-27, thirteenth pass)

A breaker review of the diff `origin/main...7ee698e` by one fresh-context reviewer. It ran on the
session's default model because the Fable usage limit was reached again. Its report and repro
scripts are in the session scratchpad, not in the repo: `review13-findings.md` and `review13/`
(`repro/` d1, d2, d3, d5; `mut/` with 25 mutants x01-x25 of pass 12's changes; `sweep/`, the
failure sweep run again, which is clean; `dryreal/`, a dry-run vs real-run differential with only
the known wording differences). New ground in this pass: `refuse_dangling` in uninstall,
`same_file`, the ledger layout check, the two-role backup.

The findings of passes 1 to 12 were checked and not reported again
(`research/review-findings-graphify-5a18f22.md` to `-341f303.md`).

Status: every finding is fixed class-wide in the next commit on PR #27.
- pytest (3.11 and 3.10, 870 passed), keyline, pyflakes, the JSON checks and the CRLF copy pass.
- 9 mutants of the new code (session scratchpad `fix13/mut.py`, y1-y9) are all killed. They
  cover the new BOM entry, the folder walk in `refuse_dangling` and in `_absolute`, the
  `_absolute` call for `CLAUDE_CONFIG_DIR` and `--home`, `_holds`'s OSError answer, the D3 guard,
  the add_to_repo folder checks and the `finish()` guard that D3 made reachable (pass 11's n16).

Every test named below failed before its fix, except where marked coverage.
Counts: 0 high, 0 medium, 3 low (D1, D2, D3), 2 info (D4, D5).

Pattern across the pass: pass 12 added checks at the exact place a finding showed (the leaf of a
path, the install half of a link-to-backup case, the BOMs a test already had) and left the
neighbours: the folders above, the uninstall half, a BOM that an older check used to catch.

## Low

D1. Finding: `scripts/ledger.py` `_wide()` missed UTF-32 BE that starts with a BOM
    (`00 00 fe ff`, what PowerShell 7 writes with `-Encoding bigendianutf32`), also after a UTF-8
    BOM, and appended a UTF-8 line to it. A regression from pass 12: the old NUL check caught it,
    the layout check does not, because the BOM's own bytes fit none of the four layouts.

    Fixed: `00 00 fe ff` is in the BOM tuple (UTF-32 LE `ff fe 00 00` is already caught by
    `ff fe`).

    Tests: `test_ledger.py` cases `utf-32-be-bom`, `utf8-bom-then-utf-32-be-bom`, and
    `utf-16-be-bom` (D4 x16: no test had UTF-16 BE with a BOM).

    Other hits: none; every encoding Python can write with a BOM (UTF-16/32, LE/BE) is now in
    the table, with and without a UTF-8 BOM in front.

    Prevention: premortem row 67.

D2. Finding: `refuse_dangling` checked only the last path component.
    - A dangling `~/.claude/ballast`: uninstall ran in no-record mode and dropped the settings
      undo for good.
    - A dangling `~/.claude`: install created the missing target through the link and wrote
      there; uninstall said "Nothing to undo."
    - A dangling `CLAUDE_CONFIG_DIR`: `target()` resolved it before the check, so install wrote
      into the missing target.

    Fixed: `refuse_dangling` checks each folder above every path. `target()` uses `_absolute()`
    for `--home` and `CLAUDE_CONFIG_DIR`, which keeps a path with a dangling link in it
    unresolved so the check sees the link. `add_to_repo.py` also checks `.claude` and
    `.claude/hooks`.

    Tests:
    - `test_a_dangling_settings_or_folder_link_stops_install_before_anything_is_written[settings|claude|ballast]`
      (`settings` is D4 x01: no test covered the settings path);
    - `test_a_dangling_claude_config_dir_stops_install_before_anything_is_written`;
    - `test_a_config_dir_under_a_dangling_folder_link_stops_install[env|home]` (mutant y3);
    - `test_a_dangling_symlink_stops_uninstall_before_anything_is_written` gains `claude` and
      `ballast`;
    - `test_a_dangling_folder_link_is_reported_before_anything_is_written[.claude|.claude/hooks]`
      (add_to_repo).

    Other hits:
    - The hook writes its runtime state under ballast; it exits 0 on any error, so a dangling
      ballast costs one missed log line, not data.
    - `--verify-only` prints "Missing" for a dangling link; accepted, it writes nothing.
    - A symlink loop gets the same "missing target" message; the run stops safely.

    Prevention: premortem row 68. README install and "Undo" bullets name the folders.

D3. Finding: uninstall left the section in a `CLAUDE.md` that links to the record's own safety
    backup holding the section (the state pass 12's install test leaves): the first check in
    `_undo_section` saw "CLAUDE.md equals the backup" and left the file, dropping the entry; the
    rerun said "not written by this install".

    Fixed: that check skips a backup that is the file itself (`_is_target`, now
    `install.same_file`). The section is taken out through the link; the backup, being the
    target, is kept.

    Tests: `test_a_claude_md_linked_to_its_recorded_backup_holding_the_section_has_the_section_removed`.
    It also reaches pass 11's n16 guard in `finish()` (mutant y9, killed).

    Other hits: the other `_undo_section` checks against a backup already use `_is_target`
    (pass 11).

    Prevention: premortem row 69.

## Info

D4. Finding: test gaps by mutation: x01 (settings path in install's dangling check), x16 (UTF-16
    BE BOM), x23 (`_backup_name` with `not is_symlink()` in place of `same_file`).

    Fixed: tests above for x01 and x16;
    `test_a_symlinked_claude_md_reuses_the_backup_of_a_run_that_failed` for x23 (coverage).
    x12 (pass 11's n16, now killed through D3), x18 (near-equivalent), x19 (a NUL in a path,
    cannot occur), x20 (Windows junctions), x21 (string vs Path compare, same result) are
    equivalent or untestable here.

D5. Finding: one unreadable installer backup (root-owned 0600 from a `sudo` run) stopped every
    install in `_backup_name`'s reuse scan with `Permission denied`.

    Fixed: `install._holds()` answers "no match" for a backup it cannot read.

    Tests: `test_an_unreadable_old_backup_does_not_stop_the_install`.

    Other hits: the kept and recorded backups that install's kept check and uninstall read can
    still raise on an unreadable file. Those are the backups the record names for this install;
    the error is one line naming the file, and skipping it would lose the undo. Accepted.

    Prevention: premortem row 70. README names the skip.
