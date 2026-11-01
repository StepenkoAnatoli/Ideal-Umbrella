# Review of branch graphify-ideas at 4bbd9d2 (2026-10-27, fifteenth pass)

A breaker review of the diff `origin/main...4bbd9d2` by one fresh-context reviewer. It ran on the
session's default model because the Fable usage limit was reached again. Its report and repro
scripts are in the session scratchpad, not in the repo: `review15-findings.md` and `review15/`
(`repro/` f1 and f2_f3_mutant_gaps; `mut/` with mutants t01-t22 of pass 14's changes; `sweep/`,
the old failure sweep, which shows only the accepted notes, and a new linked-backup sweep with no
problems; `fuzz/`, 400 random install/uninstall/edit/link sequences with no problems). New ground in
this pass: the linked and legacy-linked decision in `_undo_section`, the try around `target()`,
the empty `--home` check, the pass-14 tests.

The findings of passes 1 to 14 were checked and not reported again
(`research/review-findings-graphify-5a18f22.md` to `-34cca4d.md`).

Status: every finding is fixed class-wide in the next commit on PR #27.
- pytest (3.11 and 3.10, 894 passed), keyline, pyflakes, the JSON checks and the CRLF copy pass.
- 6 mutants (session scratchpad `fix15/mut.py`) are all killed: t02, t12, t14, t15 and u01, u02
  (the two `RuntimeError` catches of the F1 fix).

Every test named below failed before its fix, except where marked coverage.
Counts: 0 high, 0 medium, 1 low (F1), 3 info (F2, F3, F4).

Pattern across the pass: pass 14 caught the errors `target()` was seen to raise (`ValueError`,
`OSError`) and not the one the standard library documents for a missing home (`RuntimeError`).

## Low

F1. Finding: `--home '~nosuchuser'` (bash leaves `~name` as typed when there is no such user),
    `CLAUDE_CONFIG_DIR='~nosuchuser/cfg'`, or a user with no `HOME` and no passwd entry made
    `Path.expanduser()` or `Path.home()` raise `RuntimeError`; neither main caught it, so the run
    ended in a traceback, against the CHANGELOG's pass-14 line. Nothing was written first.

    Fixed: `_absolute()` and `target()` turn `RuntimeError` into a `ValueError` naming the path
    ("cannot find the home folder in ~nosuchuser") or saying to give `--home`; both mains print it
    in one line with "nothing written".

    Tests: `test_a_home_that_cannot_be_found_is_a_one_line_error[home|env|no-home x install|uninstall]`.

    Other hits:
    - `os.path.expanduser` (install.py hook command, `hooks/context_check.py`) returns the path
      unchanged instead of raising; no change needed.
    - `scripts/plugin_cost.py` `default_app_dir()` calls `Path.home()` unguarded. It predates this
      PR, only reads, and `CLAUDE_APP_DIR` overrides it; left as is.

    Prevention: premortem row 74. README names the error.

## Info

F2. Finding: mutant t02 (the linked legacy file's blank branch returning `True` in place of
    `leave()`) survived: the record entry was kept and the note repeated on every run.

    Tests: the `blank` kind of
    `test_a_claude_md_linked_to_the_legacy_backup_and_installed_again_has_the_section_removed`
    asserts the entry is gone and a second run does not repeat the note (coverage).

F3. Finding: mutant t12 (`if linked:` for `if legacy_linked:`) survived: no test had CLAUDE.md
    linked to a safety backup with nothing but the section in it.

    Tests: `test_a_blank_claude_md_linked_to_its_safety_backup_holding_the_section_is_blank_again`
    (coverage).

F4. Finding: mutants t14 and t15 (a backup replaced by a dangling link taken for one already
    deleted, dropping the "no section" note) survived.

    Tests: `test_a_backup_replaced_by_a_dangling_link_is_not_taken_for_gone[safety_backup|legacy_backup]`
    (coverage).

    Prevention (F2-F4): premortem row 75. t04 is equivalent (legacy keeps its name while
    `legacy_path` is None); t11 is not a valid mutant.
