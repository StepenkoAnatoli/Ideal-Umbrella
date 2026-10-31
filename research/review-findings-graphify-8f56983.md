# Review of branch graphify-ideas at 8f56983 (2026-10-27, eighteenth pass)

A breaker review of the diff `origin/main...8f56983` by one fresh-context reviewer. It ran on the
session's default model because the Fable usage limit was reached again. Its report and repro
scripts are in the session scratchpad, not in the repo: `review18-findings.md` and `review18/`
(`repro/` l1 (installer and Claude Code 2.1.311 under strace), l2 (empty passwd home, end to end
in a mount namespace), t1; `mut/` with mutants q01-q11 of pass 17's changes; the pass-15 fuzzer,
the linked-backup sweep and the pass-12 ENOSPC sweep run again, with only the accepted flags).
New ground in this pass: the raw-string `~` rule, `_own_home()`, the relative `CLAUDE_CONFIG_DIR`
refusal, the `confine()` guard.

The findings of passes 1 to 17 were checked and not reported again
(`research/review-findings-graphify-5a18f22.md` to `-1d18910.md`).

Status: every finding is fixed class-wide in the next commit on PR #27.
- pytest (3.13 and 3.10, 931 passed), keyline, pyflakes, the JSON checks, the CRLF copy and the
  suite with `write_text` forced to CRLF pass.
- 7 mutants (session scratchpad `fix18/mut.py`) are all killed: the reviewer's survivors q01 and
  q05, and l01-l05 (the fix's lines).

Every test named below failed before its fix, except where marked coverage.
Counts: 0 high, 0 medium, 1 low (L1), 2 info (L2, T1).

Pattern across the pass: the installer read its inputs by its own rules (shell-style `~` and
"empty is unset" for `CLAUDE_CONFIG_DIR`; the home variable rather than the home value), not by
the rules of the program that reads the result.

## Low

L1. Finding: Claude Code takes `CLAUDE_CONFIG_DIR` as it is (`CLAUDE_CONFIG_DIR ?? join(homedir(),
    ".claude")` in its source; checked in the installed cli.js and, by the reviewer, under
    strace): it does not expand `~`, and an empty value is not unset. The installer expanded
    `~/cfg` and took `""` for unset, so it installed into `$HOME/cfg` or `$HOME/.claude`,
    verified OK, and Claude Code read `<project>/~/cfg` or `<project>/settings.json`. Pass 17's
    README line ("absolute or start with `~`") and its CHANGELOG line said otherwise. This
    predates the PR (main expanded the value).

    Fixed: `target()` refuses any `CLAUDE_CONFIG_DIR` that is set and not absolute (empty, `~`,
    `~name`, relative), naming the value and saying Claude Code does not expand `~`. README and
    the CHANGELOG say how to uninstall an install made with such a value (set it to the
    expanded path).

    Tests: the `~/cfg`, `~other/cfg` and `""` kinds of
    `test_a_relative_claude_config_dir_is_refused` (with `confine()`); the `env` kinds of
    `test_a_home_that_cannot_be_found_is_a_one_line_error` and
    `test_a_home_of_another_user_that_is_not_there_is_refused`, and the `config ~/cfg` kind of
    `test_an_empty_or_relative_home_variable_is_refused`, are gone: those values are now
    refused before any `~` is expanded.

    Other hits: `hooks/context_check.py` `config_dir()` still expands a hand-set `~`, on
    purpose: the hook only keeps runtime state, and expanding keeps it out of a folder named
    `~` in every project; its docstring now says so instead of claiming it reads the value as
    install does. `add_to_repo.py` does not read `CLAUDE_CONFIG_DIR`.

    Prevention: premortem row 80 (check a value against what its consumer does, from the
    consumer's source).

## Info

L2. Finding: with no `HOME` (cron, `env -i`, systemd) and an empty home field in the passwd
    entry, `Path.home()` gives `/`, and `_own_home()` checked only the variable, so the run acted
    on `/.claude` (as root it installed there). Node's `os.homedir()` gives `""` there.

    Fixed: `_own_home()` reads the passwd home when the variable is unset (POSIX) and refuses an
    empty one, naming the passwd entry and `--home`.

    Tests: `test_an_empty_home_in_the_passwd_entry_is_refused[plain|--home ~|--home ~/sub x install|uninstall]`
    (POSIX, with `confine()`).

T1. Finding: mutants q01 (`head = "~"`, the G4 regression) and q05 (a bare `~` whose home is
    missing accepted) passed the suite: the G4 test never created your own home, so a refusal
    for the wrong reason passed, and no test had a bare `~` whose home is missing.

    Tests: `test_a_home_of_another_user_that_is_not_there_is_refused` creates your own home;
    `test_your_own_home_that_is_not_there_is_refused[install|uninstall]` (coverage).

    Other hits: review-18 q03 and q09 are equivalent.
