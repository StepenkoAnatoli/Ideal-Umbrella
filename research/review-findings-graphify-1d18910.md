# Review of branch graphify-ideas at 1d18910 (2026-10-27, seventeenth pass)

A breaker review of the diff `origin/main...1d18910` by one fresh-context reviewer. It ran on the
session's default model because the Fable usage limit was reached again. Its report and repro
scripts are in the session scratchpad, not in the repo: `review17-findings.md` and `review17/`
(`repro/` k1-k5; `mut/` with mutants r01-r08 of pass 16's changes; the pass-15 fuzzer, the
linked-backup sweep and the pass-12 ENOSPC sweep run again, with only the accepted flags). New
ground in this pass: `target()` with no home beside `CLAUDE_CONFIG_DIR`, the empty or relative
home refusal, `HOME` through `_absolute()`, the head check for `~name`, the pass-16 tests.

The findings of passes 1 to 16 were checked and not reported again
(`research/review-findings-graphify-5a18f22.md` to `-21bbc98.md`).

Status: every finding is fixed class-wide in the next commit on PR #27.
- pytest (3.13 and 3.10, 925 passed), keyline, pyflakes, the JSON checks, the CRLF copy and the
  suite with `write_text` forced to CRLF pass.
- 11 mutants (session scratchpad `fix17/mut.py`) are all killed: k01-k09 (the fix's lines) and the
  reviewer's survivors r01 and r03.

Every test named below failed before its fix, except where marked coverage.
Counts: 0 high, 0 medium, 2 low (K2, K5), 2 info (K3, K4).

Pattern across the pass: pass 16's rules for the home sat in the plain-`HOME` branch of
`target()`; `_absolute()` let pathlib decide what a `~` is, and did not apply the empty or
relative home rule to a `~` it expanded.

## Low

K2. Finding: pathlib drops a leading `./`, so `Path("./~alice").parts[0]` is `~alice` and
    `expanduser()` expands it: `--home ./~alice` and `CLAUDE_CONFIG_DIR=./~alice/cfg` installed
    into user alice's home, not into the folder `~alice` beside the run; with no such user the
    run stopped with a message naming the wrong thing. The hook (`os.path.expanduser`) reads
    `./~alice/cfg` as the folder, so hook and installer disagreed. This predates the PR
    (`Path(home_arg).expanduser()` in main).

    Fixed: `_absolute()` decides on the raw string: only a path whose text starts with `~` is
    expanded and gets the home-folder check.

    Tests: the `./~other` kind of `test_relative_home_gives_absolute_hook_path` (installs into
    `<cwd>/~other`, with `Path.expanduser` patched to map `~other` elsewhere); the
    `./~other/cfg` kind of `test_a_relative_claude_config_dir_is_refused` (see K3).

    Other hits: `hooks/context_check.py` `config_dir()` uses `os.path.expanduser`, which already
    expands only a leading `~`; `add_to_repo.py` takes a repo path and never expands `~`.

K5. Finding: `test_an_empty_or_relative_home_variable_is_refused` ran the real `main([])` with
    `HOME=""`; on a tree without the refusal (pass-16 mutant h02) the run acted on `/.claude`,
    and as root it wrote there. The test only looked at `tmp_path`. A stray `/.claude` in this
    session's container is most likely from that mutant run (throwaway container, not the
    repo).

    Fixed: `confine()` in tests/test_uninstall.py wraps `layout()` in both module copies (the
    fixture's and the one `uninstall` imports) and fails the test for a folder outside
    `tmp_path`, before any write. The refusal tests use it.

    Tests: the refusal tests with `confine()` (h02 now fails without writing outside `tmp_path`;
    coverage).

    Prevention (K2, K5): premortem rows 78 and 79.

## Info

K3. Finding: the pass-16 rule (an empty or relative home is refused) had two bypasses:
    (a) a relative `CLAUDE_CONFIG_DIR` was taken against the installer's folder, while Claude
    Code and the hook read it from each project folder; (b) `--home ~` or
    `CLAUDE_CONFIG_DIR=~/cfg` with `HOME=""` expanded to `/`, and with a relative `HOME` to the
    current folder.

    Fixed: `target()` refuses a `CLAUDE_CONFIG_DIR` that is neither absolute nor starts with `~`;
    `_own_home()` is the one check of `Path.home()` and of a bare `~`'s expansion (empty home
    variable or non-absolute home is refused, naming the variable and `--home`).

    Tests: `test_a_relative_claude_config_dir_is_refused[cfg|./~other/cfg x install|uninstall]`;
    the `--home ~` and `config ~/cfg` kinds of `test_an_empty_or_relative_home_variable_is_refused`.

    Other hits: the hook's `config_dir()` now agrees with install for every value install
    accepts. README line 75 says a relative `CLAUDE_CONFIG_DIR` stops the run.

K4. Finding: mutants r01 (`path.is_dir()` for the home folder) and r03 (an unset home variable
    refused like an empty one) survived: no test had `--home ~/sub` with `sub` not yet there,
    or an unset `HOME` taken from the passwd entry.

    Tests: the `~/sub` kind of `test_relative_home_gives_absolute_hook_path`;
    `test_an_unset_home_is_taken_from_the_passwd_entry` (POSIX; `pwd.getpwuid` patched)
    (coverage).

    Other hits: r02 (`.exists()` for `.is_dir()`) is near-equivalent (a file in place of the
    home is refused later by mkdir) and r05 (a dummy home beside `CLAUDE_CONFIG_DIR`) is
    equivalent (`layout()` ignores the home then).
