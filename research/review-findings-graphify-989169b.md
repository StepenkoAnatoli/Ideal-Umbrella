# Review of branch graphify-ideas at 989169b (2026-10-27, twentieth pass)

A breaker review of the diff `origin/main...989169b` by one fresh-context reviewer. It ran on the
session's default model because the Fable usage limit was reached again. Its report and repro
scripts are in the session scratchpad, not in the repo: `review20-findings.md` and `review20/`
(`repro/` b1, b2, d; `mut/mutate.py` with mutants o01-o13, j01-j09, v01-v20, i01-i10, u01-u07;
`cov/` line coverage; the pass-15 fuzzer run again on 1500 new seeds with no problems). New
ground in this pass: the pass-19 docs and passwd tests, `verify()`, add_to_repo's writer and the
ledger.

The findings of passes 1 to 19 were checked and not reported again
(`research/review-findings-graphify-5a18f22.md` to `-4e19841.md`).

Status: all five findings are fixed class-wide in the next commit on PR #27.
- pytest (3.13 and 3.10), keyline, pyflakes, the JSON checks, the CRLF copy and the suite with
  `write_text` forced to CRLF pass.
- Mutants (session scratchpad `fix20/mut.py`, the reviewer's set plus b01 and b02): v01, v06,
  v07, v10, v12, v13, v16-v19, o08, o12, u07, b01 and b02 are killed.

Counts: 0 high, 0 medium, 3 low (B1, T1, T2), 2 info (B2, D).

## Low

B1. Finding: `read_record` read the install record as plain UTF-8, while settings.json is read
    with `utf-8-sig`. A record saved by an editor that adds a BOM (Notepad before 2019,
    PowerShell 5 `Set-Content -Encoding UTF8`) stopped install and uninstall with "not valid
    JSON ... fix it or delete it first". Deleting the record, as advised, loses the undo data
    (`pending`, backup names, replaced values).

    Fixed: the record is read with `utf-8-sig`. Every error about the record now says
    `RECORD_ADVICE`, "fix it first (deleting it loses what uninstall puts back)": the bad JSON,
    too-deep, not-an-object, invalid-Unicode and wrong-field-type errors. README says the same.

    Tests: `test_a_record_saved_with_a_bom_is_read[install|uninstall]` and
    `test_the_error_for_a_bad_record_does_not_advise_deleting_it` (5 kinds) failed before the fix.

    Other hits: every other JSON file the installers read uses `utf-8-sig` (install
    `_read_json`, add_to_repo, verify-tokens; the ledger strips a BOM itself). Not changed:
    `hooks/context_check.py` reads only its own state file; `scripts/unused_tools.py` reads the
    repo's own `config/user-settings.json`; `scripts/plugin_cost.py` reads plugin manifests,
    which Claude Code itself does not read with a BOM.

T1. Finding: no test reached ten `issues.append` branches of `verify()` (mutants v01, v06, v07,
    v10, v12, v13, v16-v19 survived), so a regression could make `--verify-only` print OK for a
    broken install.

    Fixed: `test_verify_only_names_each_kind_of_broken_install` installs, breaks one thing per
    case (no settings, permissions or hooks not an object, a required deny tool gone, no hook
    entry, a hook command pointing elsewhere, an edited section, no CLAUDE.md, no hook, other
    hook content), runs `--verify-only`, and requires exit 1 and the exact line.

T2. Finding: add_to_repo's `_write_bytes` writing through a symlink (mutant o12) and keeping an
    existing file's mode (o08) were untested; install.py's own copies are tested.

    Fixed: `test_a_symlinked_settings_file_stays_a_link_and_its_target_is_updated` and
    `test_an_existing_file_keeps_its_mode` (0640 settings, 0750 hook: modes a new file never
    gets, so the test holds under any umask).

## Info

B2. Finding: add_to_repo refuses a lone surrogate although its own writer (`ensure_ascii` on)
    would write it back as `\ud800`; its docstring said such a file cannot be written back.

    Fixed: the check is kept, so both installers refuse the same files; the docstring says so.
    The error message never claimed the file cannot be written back.

D. Finding: the `scripts/ledger.py` `MAX_DIGITS` comment said `hooks/context_check.py` has the
   same 15-digit cap; it has none (the hook never blocks, so none is needed).

   Fixed: the comment names only add_to_repo's `--handoff-at`.

Also: `test_dry_run_writes_nothing` asserts the "Would change:" heading (mutant u07). The other
survivors are equivalent or need a non-root user: o13, u02, u03, i01.

## Prevention

Premortem row 81: a file the tool writes and the user may hand-edit is read as leniently as the
settings it sits beside, and an error about a file that holds undo data never advises deleting
it. The mutant runner now covers `verify()` line by line.
