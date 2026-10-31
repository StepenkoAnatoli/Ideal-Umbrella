# Review of branch graphify-ideas at 4e19841 (2026-10-27, nineteenth pass)

A breaker review of the diff `origin/main...4e19841` by one fresh-context reviewer. It ran on the
session's default model because the Fable usage limit was reached again. Its report and repro
scripts are in the session scratchpad, not in the repo: `review19-findings.md` and `review19/`
(`repro/` a1 (no HOME and no passwd entry, 3.10-3.13), a2/a2b (the suite with no passwd entry
or no HOME), a3; `mut/` with mutants p01-p11 of pass 18's changes; the pass-15 fuzzer and both
sweeps run again, with only the accepted flags). New ground in this pass: the absolute-only
`CLAUDE_CONFIG_DIR`, `_own_home()` reading the passwd home, the hook docstring, the pass-18 tests.

No wrong result, write outside the target, traceback or data loss was found in the code; both
findings are about docs and test portability.

The findings of passes 1 to 18 were checked and not reported again
(`research/review-findings-graphify-5a18f22.md` to `-8f56983.md`).

Status: both findings are fixed class-wide in the next commit on PR #27.
- pytest (3.13 and 3.10, 931 passed), keyline, pyflakes, the JSON checks, the CRLF copy and the
  suite with `write_text` forced to CRLF pass; the suite also passes for a user with no passwd
  entry (the reviewer's a2 run) and with `HOME` unset.
- The pass-18 mutants (session scratchpad `fix18/mut.py`, q01, q05, l01-l05) are still killed
  with the rewritten passwd tests.

Counts: 0 high, 0 medium, 1 low (D1), 1 info (T1).

## Low

D1. Finding: the CHANGELOG [Unreleased] line on `CLAUDE_CONFIG_DIR` (from main) still said install
    reads it "with `~` expanded and the path made absolute"; install now refuses any value that
    is not absolute.

    Fixed: that line says install takes it only as an absolute path, as Claude Code does, and
    that the hook also expands a hand-set `~`.

    Other hits: the review-17 CHANGELOG line said `CLAUDE_CONFIG_DIR=./~name/...` is a folder
    named `~name`; it is refused as relative (since pass 17), and the line now says so. README
    and the review-18 CHANGELOG line told only a `~` install how to uninstall; both now cover a
    relative value too (set it to the absolute path it was taken for).

## Info

T1. Finding: `test_an_unset_home_is_taken_from_the_passwd_entry` and
    `test_an_empty_home_in_the_passwd_entry_is_refused` built the fake entry from
    `pwd.getpwuid(os.getuid())` and removed `HOME` with `raising=True`, so they failed with
    `KeyError` for a user with no passwd entry (random-uid containers) or with `HOME` unset
    (`env -i`), where the code itself works.

    Fixed: the entry is built from scratch with `pwd.struct_passwd`, and `HOME` is removed with
    `raising=False`.

    Tests: the 7 cases failed under `env -u HOME` and in the reviewer's no-passwd run before the
    fix and pass after it.

    Other hits: no other test calls `pwd.getpwuid` or removes `HOME`/`USERPROFILE` with
    `raising=True`.

    The surviving review-19 mutants p03, p05, p09, p10 and p11 are equivalent or
    near-equivalent (stricter, or Windows-only with `USERPROFILE` unset).
