# Review of branch graphify-ideas at 21bbc98 (2026-10-27, sixteenth pass)

A breaker review of the diff `origin/main...21bbc98` by one fresh-context reviewer. It ran on the
session's default model because the Fable usage limit was reached again. Its report and repro
scripts are in the session scratchpad, not in the repo: `review16-findings.md` and `review16/`
(`repro/` g1-g5; `mut/` with mutants s01-s10 of pass 15's changes; the pass-15 fuzzer and
linked-backup sweep run again, with only the accepted flag). New ground in this pass: the
`RuntimeError` catches in `target()` and `_absolute()`, the pass-15 tests.

The findings of passes 1 to 15 were checked and not reported again
(`research/review-findings-graphify-5a18f22.md` to `-4bbd9d2.md`).

Status: every finding is fixed class-wide in the next commit on PR #27.
- pytest (3.13 and 3.10, 910 passed), keyline, pyflakes, the JSON checks, the CRLF copy and the
  suite with `write_text` forced to CRLF pass. The g1, g2, g3 and g5 repros give the one-line
  error or the install into `CLAUDE_CONFIG_DIR` on the fixed tree.
- 9 mutants (session scratchpad `fix16/mut.py`): s01, s02 and h01-h03, h05-h07 are killed. h04
  (`HOME` named on Windows too) changes only the Windows message; the `USERPROFILE` cases of
  `test_an_empty_or_relative_home_variable_is_refused` kill it on Windows CI.

Every test named below failed before its fix, except where marked coverage.
Counts: 0 high, 0 medium, 3 low (G1, G2, G3), 3 info (G4, G5, G6).

Pattern across the pass: pass 13 to 15 hardened `--home` and `CLAUDE_CONFIG_DIR` (through
`_absolute()`), but not the plain-`HOME` branch of `target()`, which kept its own rules for a
missing home, a dangling link and a loop.

## Low

G1. Finding: with no `HOME` and no passwd entry (random-uid containers), a set
    `CLAUDE_CONFIG_DIR` was refused with "cannot find your home folder; give it with --home",
    although the home is not used then; following the advice installed into `<home>/.claude`,
    which Claude Code does not read while `CLAUDE_CONFIG_DIR` is set.

    Fixed: `target()` returns no home when `CLAUDE_CONFIG_DIR` is set (`layout()`,
    `hook_command()`, `merge_settings()`, `verify()` and `uninstall()` use the home only through
    `layout()`, which ignores it then).

    Tests: `test_no_home_folder_is_no_matter_when_claude_config_dir_is_set[install|uninstall]`.

G2. Finding: a `HOME` that is a symlink loop ended in a traceback on Python 3.10-3.12
    (`Path.resolve()` raises `RuntimeError` there).

G3. Finding: a `HOME` that is a symlink to a missing folder (an unmounted volume) was resolved,
    so install created the missing folder and wrote beneath the mount point; `--home` with the
    same path stopped with "symlink to a missing target".

    Fixed (G2, G3): `target()` passes `HOME` through `_absolute()`, as `--home`, so
    `refuse_dangling()` sees the link and stops before any write.

    Tests: `test_a_home_that_is_a_link_to_nothing_is_a_one_line_error[dangling|loop x install|uninstall]`
    (the loop kind fails before the fix on 3.10 only).

    Other hits: `--home` and `CLAUDE_CONFIG_DIR` already went through `_absolute()`; `target()`
    has no other path.

    Prevention (G1-G3, G5): premortem row 76.

## Info

G4. Finding: on Windows `ntpath.expanduser('~nosuchuser')` gives `C:\Users\nosuchuser` whether or
    not that user exists, so `--home ~nosuchuser` was installed into instead of refused, against
    the README.

    Fixed: `_absolute()` refuses a `~` or `~name` whose home folder is not a directory, with the
    same one-line error naming the path. A bare `~` whose home is not there is refused too (it
    was installed into before; a home folder that does not exist is not one to install into).

    Tests: `test_a_home_of_another_user_that_is_not_there_is_refused[home|env x install|uninstall]`
    (simulated by patching `Path.expanduser` as Windows maps it); the `~other` kind of
    `test_relative_home_gives_absolute_hook_path` (another user's home that exists still
    installs).

    Prevention: premortem row 77. README names the case.

G5. Finding: `HOME=""` was taken as `/` (and `USERPROFILE=""` on Windows as the current folder),
    so the run acted on `/.claude`.

    Fixed: `target()` refuses a home variable that is empty or whose `Path.home()` is not
    absolute (also a relative `HOME`), naming the variable and `--home`.

    Tests: `test_an_empty_or_relative_home_variable_is_refused[""|relative x HOME|USERPROFILE x install|uninstall]`
    (each variable runs on its own platform).

    Other hits: `hooks/context_check.py` uses `os.path.expanduser("~")` at run time; with an
    empty `HOME` there it would look under `/.claude`, where nothing was installed, and it never
    blocks a prompt; `scripts/plugin_cost.py` only reads. Left as is.

G6. Finding: mutants s01 (`HOME` not resolved) and s02 (the `_absolute()` message without the
    path) survived.

    Tests: the `None` kind of `test_relative_home_gives_absolute_hook_path` (a `HOME` with `..`
    gives a resolved hook path) kills s01; `test_a_home_that_cannot_be_found_is_a_one_line_error`
    asserts the path in the message (coverage).
