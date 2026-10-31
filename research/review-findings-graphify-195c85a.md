# Review of branch graphify-ideas at 195c85a (2026-10-27, twenty-first pass)

A breaker review of the diff `origin/main...195c85a` by one fresh-context reviewer. It ran on the
session's default model because the Fable usage limit was reached again. Its report and repro
scripts are in the session scratchpad, not in the repo: `review21-findings.md` and `review21/`
(`repro/` s1-s3; `fuzz/sfuzz.py`, a settings fuzzer with hand edits and deletes; `fuzz/mdfuzz.py`,
the CLAUDE.md fuzzer, 0 of 2000 seeds with problems; `mut/m_bom`). New ground in this pass: the
pass-20 fixes (the record read with `utf-8-sig`, `RECORD_ADVICE`, the verify-only tests, the
add_to_repo link and mode tests).

The findings of passes 1 to 20 were checked and not reported again
(`research/review-findings-graphify-5a18f22.md` to `-989169b.md`).

Status: all four findings are fixed class-wide in the next commit on PR #27.
- pytest (3.13 and 3.10), keyline, pyflakes, the JSON checks, the CRLF copy and the suite with
  `write_text` forced to CRLF pass.
- Mutants (session scratchpad `fix21/mut.py`): l1, l2, l3i, l3a and i1 are killed.
- The reviewer's settings fuzzer with hand deletes: 0 of 2000 seeds with problems (146 before).

Counts: 0 high, 0 medium, 3 low (L1, L2, L3), 1 info (I1).

## Low

L1. Finding: settings had `autoCompactWindow: 100000`; `install --force` recorded it as replaced;
    the user deleted the key by hand; a second install added the key again (no `--force` needed);
    uninstall restored 100000. `_merge_record` kept the first run's `replaced` entry and skipped
    the key in the new run's `added_keys`. README "Undo" says values changed after installing are
    left alone; a delete is such a change. Present on origin/main too.

    Fixed: in `_merge_record`, a key the new run adds was absent from settings, so it is dropped
    from `replaced` and listed in `added_keys`; uninstall removes it. The docstring says so.

    Tests: `test_a_key_deleted_by_hand_after_a_forced_install_stays_deleted` failed before the fix.

    Other hits: `deny_added` and the hook entry already merge this way (a tool the new run adds is
    one the user removed, and uninstall removes it); uninstall skips a recorded key that is absent,
    so a delete without a second install already stayed deleted. `add_to_repo.py` keeps no record.

L2. Finding: a record saved as UTF-16 (PowerShell 5 `>` or `Out-File`, Notepad "Unicode") stopped
    install and uninstall with "is not valid JSON ('utf-8' codec can't decode ...)". The JSON is
    valid; the encoding is wrong. `read_record`'s `except ValueError` also caught
    `UnicodeDecodeError`. README "(a BOM added by an editor is fine)" and the Review 20 CHANGELOG
    line "(Notepad, PowerShell 5)" held only for a UTF-8 BOM.

    Fixed: `read_record` catches `UnicodeDecodeError` first: "is not UTF-8 (<reason> at byte N);
    save it as UTF-8 first (deleting it loses what uninstall puts back)". README and CHANGELOG
    say UTF-8 BOM and name the PowerShell 5 commands that save each.

    Tests: `test_a_record_saved_as_utf16_is_said_to_be_not_utf8` (install and uninstall) failed
    before the fix.

    Other hits: install's `_read_json` and `_read_text` and add_to_repo's `_read_json` already
    catch `UnicodeDecodeError` before the JSON error.

L3. Finding: `refuse_dangling` said "is a symlink to a missing target; fix or remove it first" for
    every path. For a record linked into an unmounted dotfiles folder, removing the link made
    uninstall run in no-record mode and drop the user's replaced value for good, against README
    "Undo" and premortem row 81.

    Fixed: the message is "put the target back (a moved or unmounted folder) or point the link at
    it, then run again", in install.py and in add_to_repo.py's own copy.

    Tests: every dangling-link test (5 in test_install.py, 1 in test_uninstall.py, 2 in
    test_add_to_repo.py) asserts "remove it" is not in the error.

    Other hits: no other error in config/, scripts/ or hooks/ advises removing or deleting a file;
    uninstall's "delete it once you no longer need it" is about a backup it keeps on purpose.

## Info

I1. Finding: `test_a_record_saved_with_a_bom_is_read` passed with a mutant that takes a BOM record
    for no record (`m_bom`): uninstall in no-record mode still removes the hook, which was all the
    test asserted.

    Fixed: the test installs with `--force` over `autoCompactWindow: 100000` and adds the BOM; the
    install leg asserts the record still holds the replaced value, the uninstall leg asserts it is
    restored. Mutant i1 (the same as `m_bom`) is killed.

## Prevention

Premortem row 82: a key a run adds was absent, so it overrides whatever the record kept for it; a
decode error is reported as an encoding error before any JSON catch; the advice in an error is
checked against every path it covers, the ones holding undo data first; a test for a read path
asserts the data read is used, not only that the run succeeds.
