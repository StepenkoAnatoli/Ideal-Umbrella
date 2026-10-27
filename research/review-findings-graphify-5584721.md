# Review of branch graphify-ideas at 5584721 (2026-10-27, ninth pass)

A breaker review of the diff `origin/main...5584721` by one fresh-context reviewer. It ran on the
session's default model because the Fable usage limit was reached again. Its report and repro
scripts are in the session scratchpad, not in the repo: `review9-findings.md` and `review9/`
(r2 run as uid 65534 with `setpriv`, r3, `run_r1.sh` with `test_r1_hook_file_only.py`, and
`mut/` with 10 mutants aimed at pass 8's changes). New ground in this pass: what a run that
stops after the `CLAUDE.md` step leaves unsaid, now that `settings.json` is written after it;
the hook file as the only evidence; and a ledger file in UTF-16.

The findings of passes 1 to 8 were checked and not reported again
(`research/review-findings-graphify-5a18f22.md`, `-db5cd0c.md`, `-f6ca6ef.md`, `-032a6bf.md`,
`-3d9c4e8.md`, `-1e9664a.md`, `-59fb4c9.md`, `-ded6960.md`).

Status: every finding is fixed class-wide in the next commit on PR #27.
- pytest (3.11 and 3.10), keyline, pyflakes and the JSON checks pass.
- The 10 mutants were rerun against the fixed code: r01 to r09 are killed, and r06, r07 and r08
  now by the no-record tests themselves. r10 (`raise first from None` to `raise first`) is
  equivalent: only the chained traceback differs, and main prints one line.
- The reviewer's repros r2 and r3 were rerun on the fixed tree: r2's rerun names the kept copy,
  and r3 ends in a one-line error with the file unchanged.

Every test named below failed before its fix, except where marked coverage.
Counts: 0 high, 0 medium, 3 low (L1 to L3), 2 info notes (I1, I2).

Pattern across the pass: pass 8 moved a write after the `CLAUDE.md` step, which made "a run
that stops after that step" common (a read-only `settings.json`). A note that only the step
itself gives is lost when a later step fails, so a rerun has to be able to give it again.

## Low

L1. Finding: the user changed their own text after the install, so uninstall keeps the copy from
    before the install and says so in a note. A run that stopped after its `CLAUDE.md` step (at
    the `settings.json` backup or write, the hook delete, or the record write) never printed that
    note, because notices are printed only on success. The rerun found no section, said only
    "CLAUDE.md has no Ideal-Umbrella section; left as is" and dropped the record entry. The copy
    stayed with nothing ever naming it. Since pass 8 a read-only `settings.json` leads there.
    Fixed: with no section in `CLAUDE.md` and a kept copy from before the install that differs
    from the file, uninstall names the copy ("your CLAUDE.md from before the install is kept in
    ...; it differs from the file now, so delete it once you no longer need it"). This also
    covers a section the user took out by hand.
    Considered and not done: printing the notices gathered so far on an error. The rerun the
    error asks for now gives every note, so a second channel adds nothing.
    Tests: `test_a_kept_backup_is_named_when_an_uninstall_that_failed_part_way_is_finished`
    fails each write and delete in turn. The two runs together must name the kept copy. 4 cases
    failed before the fix.
    Other hits:
    - The legacy (whole-file installer) backup is already named in the same branch. Corrected by
      review 10 (L1): only when that branch is reached; after an upgrade with a rewritten file the
      rerun took another branch and named nothing.
    - The `hand_section` branch names its copy.
    - An edited section keeps the record entry, so the rerun gives the same note again.
    - Settings notices are worked out again from the record, which is written last.
    Prevention: premortem row 50.

L2. Finding: no test held the no-record order (the hook file deleted last) or the hook file as
    evidence. Since pass 8 every no-record kind still had the hook entry in `settings.json` at the
    `CLAUDE.md` step, so the hook file was never the only evidence. Mutant r08 (the hook file
    not counted) survived. r06 and r07 (the hook file deleted earlier) were killed only by an
    unrelated record-mode test. Premortem row 44 named a test that did not guard it.
    Fixed (test only; the code was right): `without_the_hook_entry` kinds in `NO_RECORD`, for a
    section and for the whole file, take our entry out of `settings.json`. Premortem row 44 is
    corrected.
    Tests: `test_a_rerun_of_an_uninstall_without_a_record_finishes_it[..._or_hook_entry-*]`
    (coverage; it kills r06, r07 and r08).
    Other hits: the `_or_hook_file` kinds kill r01 and r09, the hook entry as evidence.
    Prevention: premortem row 51.

L3. Finding: Windows PowerShell 5 saves UTF-16 with a BOM by default (`Out-File`, `>`, `>>`), as
    does Notepad's "Unicode". `scripts/ledger.py` read such a measurements file as two unreadable
    lines, appended a UTF-8 line and exited 0. The file was then neither UTF-8 nor UTF-16.
    Fixed: a file that starts with a UTF-16 BOM or holds a NUL byte (UTF-16 without a BOM,
    UTF-32) stops the run, `--dry-run` included, with "error: FILE: not UTF-8 text (UTF-16 or
    UTF-32); save it as UTF-8 first" and exit 1. Nothing is written. `json.dumps` never writes a
    raw NUL, so a ledger line never holds one.
    Tests: `test_a_file_that_is_not_utf8_text_is_an_error_and_is_not_appended_to[utf-16-bom|utf-16-be|utf-32]`.
    Other hits: a UTF-16 `settings.json` or `CLAUDE.md` already stops `install.py`,
    `uninstall.py` and `add_to_repo.py` before any write ("is not UTF-8 ...; save it as UTF-8
    first; nothing written"). This was checked by running each on such a file.
    Prevention: premortem row 52.

## Info

I1. Finding: README "Undo" said "`settings.json` is backed up first". Since pass 8 the backup
    comes after the `CLAUDE.md` step.
    Fixed: "is backed up before it is rewritten".

I2. Finding: README said a delete refused because the folder is not writable "is reported as
    such". The error names the file, not the folder.
    Fixed: the README says the refused delete is the error shown, not the failed change of mode.
    The message itself is the OS's.

Still open, outside this PR: `keyline/keyline_lint.py:197` numbers lines with
`str.splitlines()` (from pass 1).
