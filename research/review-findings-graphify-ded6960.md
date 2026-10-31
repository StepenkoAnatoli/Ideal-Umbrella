# Review of branch graphify-ideas at ded6960 (2026-10-27, eighth pass)

A breaker review of the diff `origin/main...ded6960` by one fresh-context reviewer. It ran on the
session's default model because the Fable usage limit was reached again. Its report and repro
scripts are in the session scratchpad, not in the repo: `review8-findings.md` and `review8/`
(r1 to r6, run as a non-root user with `setpriv` where POSIX ownership matters, and `mut/` with
12 mutants aimed at pass 7's fixes). New ground in this pass: the order of the no-record
uninstall's steps when the hook file is already gone, the notices of a no-record rerun, the test
kinds themselves (does each run the branch it is named for), and a ledger file with a BOM.

The findings of passes 1 to 7 were checked and not reported again
(`research/review-findings-graphify-5a18f22.md`, `-db5cd0c.md`, `-f6ca6ef.md`, `-032a6bf.md`,
`-3d9c4e8.md`, `-1e9664a.md`, `-59fb4c9.md`).

Status: every finding is fixed class-wide in the next commit on PR #27.
- pytest (3.11 and 3.10), keyline, pyflakes and the JSON checks pass.
- The mutants were rerun against the fixed code: q01, q04, q05, q06, q07, q11 and q12 are
  killed. q03 and q10 are equivalent, as the reviewer found. q02, q08 and q09 no longer apply to
  the changed `remove` (their text is gone); q09's kind, a chmod before the delete, is killed by
  `test_a_writable_file_whose_delete_is_refused_is_never_chmodded`.

Every test named below failed before its fix, except where marked coverage.
Counts: 0 high, 0 medium, 4 low (L1 to L4), 1 info note (I1).

Pattern across the pass: pass 7 tested its own fix through a test kind that did not reach the
branch it was named for, and its record said the branch was covered. A test kind's name is a
claim to check, by asserting the state it sets up.

## Low

L1. Finding: without a record, a `CLAUDE.md` that held no section and was not the rules fell into
    the whole-file branch and got "CLAUDE.md differs from what was installed; left as is". The
    reviewer saw it on the rerun of an uninstall that stopped at the hook delete (the section was
    already gone). The root cause is wider: the same note came in a home with no install at all,
    where nothing was installed to differ from.
    Fixed:
    - A no-record uninstall no longer says "what was installed": nothing says what that was.
    - It says "CLAUDE.md has no Ideal-Umbrella section and is not the rules file; left as is",
      and only when an install is found (the hook file or our hook entry).
    - Rejected: writing a marker record before the hook delete, as the reviewer suggested. It
      would change what a rerun does with `settings.json`, and its own write could fail too.
    Tests:
    - `test_without_a_record_a_claude_md_of_the_users_is_not_said_to_differ[False|True]`, with
      and without an install found.
    - `test_a_rerun_of_an_uninstall_without_a_record_finishes_it` checks that no rerun note says
      "what was installed".
    Other hits: the record-based branch already says nothing when the record has no `CLAUDE.md`
    entry (pass 5, L2).
    Prevention: premortem row 47.

L2. Finding: an uninstall without a record whose hook file was already gone had the hook entry in
    `settings.json` as its only evidence. It wrote `settings.json` (removing that entry) before
    its `CLAUDE.md` step. When that step failed (a full disk), the rerun said "Nothing to undo."
    and the section stayed for good. This is the case pass 7's L2 fix left open, and README
    "Undo" was wrong for it.
    Fixed: `settings.json` is computed early but written after the `CLAUDE.md` step, in every
    mode. With a record, the record is the evidence and is written last, so the order does not
    matter there. The hook file is still deleted last.
    Tests: every no-record kind of `test_a_rerun_of_an_uninstall_without_a_record_finishes_it`
    also runs without the hook file (`..._or_hook_file`), with each write and delete failing in
    turn. The rerun must leave no section, no hook file, no hook entry and no
    `autoCompactWindow`. 20 cases failed before the fix.
    Other hits: the record-based kinds in `test_a_rerun_of_an_uninstall_that_failed_part_way_finishes_it`
    pass with the new order unchanged.
    Prevention: premortem row 46.

L3. Finding: the "whole file without a record" kind in `tests/test_failed_writes.py` wrote the rules
    as `CLAUDE.md` and then ran the install, which wraps an unmarked copy of the rules in marker
    lines. So the kind ran the section branch. The real whole-file no-record branch (back up
    `CLAUDE.md`, then delete it) had no test, and mutants q06 (backup not named), q11 (no backup
    before the delete: data loss) and q12 (branch disabled) survived. Pass 7's record said the
    branch was covered.
    Fixed (test only; the code was right):
    - The kind installs, deletes the record and backups, then writes the rules without marker
      lines as `CLAUDE.md`.
    - The test asserts the marker lines are present only for the section kinds.
    - In the whole-file case it checks that `CLAUDE.md` is gone and a backup equals the rules.
    - `-59fb4c9.md` L2 is corrected.
    Tests: the parametrized test above; q06, q11 and q12 are killed.
    Other hits: the other kinds in `tests/test_failed_writes.py` were read against their names.
    The record-based ones build their state by hand where it matters
    (`from_the_whole_file_installer` writes the rules, the old backup and the record entry
    itself), or are an ordinary install, so each reaches the branch it is named for.
    Prevention: premortem row 48.

L4. Finding: `scripts/ledger.py` read `research/measurements.jsonl` as plain UTF-8. A file saved
    with a byte order mark (older Notepad, PowerShell 5 `Out-File -Encoding utf8`) had its first
    line counted as unreadable, every run, so the earliest measurement was never compared.
    Fixed: `previous_entry` decodes with `utf-8-sig`.
    Tests: `test_a_byte_order_mark_before_the_first_line_is_not_an_unreadable_line`.
    Other hits:
    - The installers already read `settings.json` and the record with `utf-8-sig`.
    - The ledger is the only hand-edited JSON Lines file a script reads. Transcripts are written
      by Claude Code.
    Prevention: premortem row 49.

## Info

I1. Finding: `install.remove` on a read-only file another user owns, in a folder that is not
    writable: the delete was refused because of the folder, the chmod then failed with EPERM, and
    that EPERM was the error shown. It pointed at the file's owner when the fix was the folder.
    Mutant q04 (the `os.access` check dropped) survived because its only effect was a chmod with
    no visible result.
    Fixed:
    - When the chmod fails, `remove` re-raises the refused delete.
    - A writable file whose delete is refused is never chmodded.
    Tests:
    - `test_a_refused_delete_is_reported_when_the_chmod_fails_too`.
    - `test_a_writable_file_whose_delete_is_refused_is_never_chmodded` (coverage; it kills q04).
    Other hits: `remove` is the only place that chmods a file it did not make.
    Prevention: premortem row 49.

Still open, outside this PR: `keyline/keyline_lint.py:197` numbers lines with
`str.splitlines()` (from pass 1).
