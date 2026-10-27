# Review of main 99edcda (2026-10-25, third full pass)

Review of every source, config, test and doc file after PR #14 and #15 merged. Baseline on
this tree: pytest 76 passed, keyline suite 35/35 on Linux, pyflakes clean, the four JSON files
parse (the three templates and keyline/hooks-example.json). Each finding below was reproduced in
the scratchpad or traced to the line. A second, fresh-context reviewer read the same tree
independently and confirmed findings 1, 2 and 6; findings 8 to 14 are its additions, each
re-reproduced here before it was accepted. Its suggested fix for finding 11 was not taken (see
there).

Status: all findings fixed in PR #16 (on top of this report's commit). After the fixes: pytest
97 passed, keyline suite 35/35, pyflakes clean, JSON files parse.

## High
None.

## Medium
1. keyline/keyline_check.py:27-28 and :21: an ISO 8601 timestamp with a `T` separator is not
   extracted as a date. `date` requires a non-word character after the day, so `2026-10-25T10:00:00Z`
   splits into the numbers `2026` and `10` and the time `00:00Z`; the day never becomes an
   invariant. Reproduced: source "Outage began at 2026-10-25T10:00:00Z and ended
   2026-10-25T11:30:00Z", rendering with the first date changed to 2026-10-26 -> PASS. With a
   space instead of the `T` the same change FAILs as it should. Incident notes, the checker's
   main input, use this form constantly. Not listed under "Honest limits". Fix: a `datetime`
   alternative before `date` (`\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?`)
   or allow `T\d` after the date group.
   Fixed: a `datetime` alternative before `date`; `present()` accepts a space for the `T`, so
   "2026-10-25 10:00:00Z" counts as the same instant. tests/test_keyline_check.py.

## Low
2. config/uninstall.py:224-229 catches only ValueError; an OSError in the middle of the undo
   escapes as a traceback, after settings.json was already rewritten and backed up, with the
   record left as it was. Reproduced by replacing ~/.claude/ballast/context_check.py with a
   folder: `IsADirectoryError` from `paths["hook"].unlink()` (uninstall.py:174), exit 1, settings
   undone, record still the full install record. install.py:433-436 handles the same class with
   an "Error:" line. A second run after removing the obstacle finishes the undo, so nothing is
   lost; the message is the gap. The ValueError branch says "nothing written", which is also
   untrue once the settings write at :168 has happened.
   Fixed: `main()` reports OSError as one line that says the undo stopped part way and a second
   run finishes it; the ValueError line stays "nothing written" (it is raised only while reading).
3. config/install.py:247-256 and config/uninstall.py:146,213-214: an install-record.json that
   exists but is not valid JSON is treated as absent. Uninstall then says "no install record"
   (not "the record is unreadable"), runs in evidence mode, leaves permissions.deny alone, and
   overwrites the file with `{"uninstalled": true}`, so a record a user could have repaired by
   hand (it holds the values to restore) is gone. Reproduced with `{broken` as the record.
   Fixed: `read_record` raises ValueError for invalid JSON, a non-object or an unreadable file;
   install and uninstall stop before writing and say to fix or delete the record.
4. keyline/keyline_lint.py:58-61,83-85 and keyline/keyline_hook.py:141-154: the single-token
   word cache lives in keyline/cache/, which .gitignore excludes, so a fresh clone builds it on
   first use and that needs tiktoken. Without tiktoken, `lint_file` raises ModuleNotFoundError;
   the hook catches only OSError, so every Write/Edit of a watched note shows Claude a traceback
   (exit 1, non-blocking). keyline/measure.py:16-19 and scripts/plugin_cost.py:96-100 give the
   one-line install hint for the same case. Reproduced by running the hook with tiktoken
   blocked and the cache folder moved away.
   Fixed: `_tiktoken()` exits with the same one-line hint as measure.py.
5. hooks/context_check.py:120-123: the comment says Claude Code records only `preTokens` and the
   hook therefore reports 0 after a compaction. Real compact_boundary events (five in this
   session's own transcript) carry `postTokens` (11095 to 20185), and the code at :123 uses it.
   The comment, and the rationale recorded in research/pr-cleanup-progress.md ("Claude Code
   records preTokens only"), are wrong; the code is right. Note that postTokens excludes the
   system prompt and tool definitions: the first assistant event after each compaction showed
   82k-96k, so the value is a floor, which is harmless here because both are under the threshold.
   Fixed: comment rewritten; the resume point's rationale corrected.
6. keyline/keyline_check.py:34: the proper-noun pattern `(?:[-'][A-Za-z0-9]+)*` absorbs an
   English possessive, so "Claude's hook" yields the invariant `Claude's`, and a rendering that
   writes "the hook of Claude" or Hebrew "של Claude" FAILs on it. Reproduced. It fails closed, so
   no wrong pass, but the limit is not in the README's "Honest limits".
   Fixed: an apostrophe followed by a lone `s` ends the name; `Jean-Luc's` still gives `Jean-Luc`.
7. Docs tied to one machine: keyline/README.md:23-31 and every command block use
   `py -3.14 -m venv .venv` and `.venv/Scripts/python.exe` (Windows only, while CI and README.md
   use `python -I`); keyline/README.md:115-116 cite `gittoken/.claude/settings.local.json` and
   `C:/Users/PC/Desktop/gittoken/rk-wt/PROGRESS.md`; README.md:171 says "venv in `keyline/.venv/`"
   although `.venv/` is gitignored and nothing creates it; README.md:143 names
   `~/.claude/projects/C--Users-PC-Desktop-gittoken`.
   Fixed: portable setup and command lines, a generic `--watch` example, no machine paths.

Added by the second reviewer (numbering continues):

8. keyline/keyline_check.py:74-80: the month in "May 2026" or "May 14" counts as the possibility
   hedge `may`, so a Hebrew rendering ("במאי 2026") is reported as having lost a hedge. Reproduced.
   Fixed: a capitalised `May` followed by a number is skipped in `hedges()`.
9. keyline/keyline_check.py `read()`, keyline/keyline_lint.py `lint_file()`, keyline/keyline_hook.py:
   a note that is not UTF-8 (cp1252 from a Windows editor) raises UnicodeDecodeError, which is not
   an OSError, so all three show a traceback and exit 1 instead of the documented exit 2 and one
   line. Reproduced with `caf\xe9 503`.
   Fixed: both readers turn the decode error into an OSError naming the file and the byte, so the
   existing handlers print one line (check and lint exit 2; the hook exits 1, non-blocking).
10. config/uninstall.py:183: a record whose `claude_md.backup` is not a string (`1`) raises
    TypeError in `with_name`. Reproduced. Fixed: a non-string backup name counts as none.
11. config/uninstall.py:176-211: a record with no `claude_md` entry and a CLAUDE.md equal to the
    template leaves the file without a word. Reproduced. The reviewer suggested deleting it the
    way the no-record path does; that is wrong for the current installer, where a missing entry
    means the install never wrote the file (it already matched the template), and the existing
    test `test_second_uninstall_keeps_the_users_own_values` pins that. Fixed with a notice instead:
    "CLAUDE.md matches the template but was not written by this install; left as is".
12. .github/workflows/ci.yml:16-17: the comment says `PYTHONUTF8=1` keeps child processes off the
    Windows ANSI code page, but every child is started with `-I`, which implies `-E` and ignores
    `PYTHON*` variables (verified: `utf8_mode` is 0 under `-I`). CI is green because the keyline
    scripts set UTF-8 output themselves. Related: config/install.py and uninstall.py print the home
    path in their listings without setting the encoding, so a non-ANSI home path through a pipe on
    Windows could raise UnicodeEncodeError (not run here). Fixed: comment corrected; install,
    uninstall and add_to_repo set `sys.stdout` to UTF-8 like the keyline scripts.
13. hooks/context_check.py:151-161: the band state is only reset below the threshold. After a
    reminder at 240k (band 3), a compaction that lands at 160k (still over the threshold) keeps
    the hook silent until 250k, because `band <= last`. Reproduced with a synthetic transcript
    (the reviewer's premise that Claude Code records only `preTokens` is the same error as
    finding 5; the mechanism holds with the `postTokens` that real transcripts carry). Fixed: a
    lower band than the last reminder starts the bands again; a test for a `preTokens`-only
    boundary (0) added.
14. README.md:66 says a failed install changes nothing; that holds for failures while reading or
    checking. A `~/.claude/CLAUDE.md` symlink to a missing target passes `exists()` as absent,
    the hook file is copied, then the CLAUDE.md write fails with ENOENT. Reproduced. Harmless
    (no settings entry, so the hook file is inert). Fixed: a dangling symlink at `settings.json`
    or `CLAUDE.md` is a read-phase error ("fix or remove it first"); the README sentence says
    what a failed write leaves behind.
15. tests/test_install.py: the test that the generated hook command does not block prompts cannot
    fail (every error ends in `|| exit 0`), and no test ran the command with the hook present, so a
    quoting mistake on Windows would be invisible. Fixed: a test installs into a temporary home,
    runs the installed command through the shell on a 160k transcript and expects the reminder.

## Checked and found correct
- install.py: order of writes (hook, CLAUDE.md, settings.json, record), symlinked settings,
  `--force` and the "template changed" path, `_merge_record` first-wins with user edits,
  `verify()` on a string deny list and a non-list hook entry, quoting on both platforms, a home
  path containing a quote, relative `--home`.
- uninstall.py: round trip restores the prior settings exactly, sibling hooks kept, missing
  CLAUDE.md backup keeps the file, record marker makes a second run a no-op, dry run writes
  nothing.
- add_to_repo.py: writes settings.json before copying the hook (the reverse of install.py) but
  the repo hook command ends in `; exit 0` and is gated on `CLAUDE_CODE_REMOTE`, so a settings
  file that briefly points at a missing hook blocks nothing. `_write_json` lacks
  `ensure_ascii=False` (install.py has it): cosmetic, both parse the same.
- hooks/context_check.py: run against this session's real transcript (6.9 MB, five compactions):
  131,598 tokens at the time of the check, sidechain events skipped, boundary handling as the
  test expects. Tail read starting mid-line, invalid integer settings, UTF-8 stdin on a cp1252
  locale, state pruning and log trimming behave as documented.
- keyline_check.py: list markers, Hebrew prefixes on negations, hedge classes, `5` vs `503`,
  `and/or`, hyphenated names, times with and without `Z` (dropping the `Z` is reported, by design).
- keyline_lint.py: furniture rules, numeronyms, plural of a one-token word, allow files read
  from parent folders (the direct parent is read twice; harmless).
- keyline_hook.py: `--watch` absolute and relative patterns, `.he.txt` pairing, exit codes.
- Transcript scripts: isinstance guards and zero-division guards from PR #14 hold; message-id
  dedup in usage_breakdown.py matches the real transcript layout (one line per content block,
  identical usage on each).
- CI: ubuntu and windows, Python 3.12, PYTHONUTF8=1, pytest, keyline suite, JSON parse of the
  three templates (keyline/hooks-example.json is not in the list; it parses).
- Tests: none vacuous; each asserts on content or exit codes, and the regression tests name the
  bug they pin.
