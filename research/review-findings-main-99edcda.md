# Review of main 99edcda (2026-10-25, third full pass)

Read-only review of every source, config, test and doc file after PR #14 and #15 merged.
Baseline on this tree: pytest 76 passed, keyline suite 35/35 on Linux, pyflakes clean, the four
JSON files parse (the three templates and keyline/hooks-example.json). Each finding below was
reproduced in the scratchpad or traced to the line. A second, fresh-context reviewer is reading the
same tree independently; its confirmed findings will be merged in by a follow-up commit.

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

## Low
2. config/uninstall.py:224-229 catches only ValueError; an OSError in the middle of the undo
   escapes as a traceback, after settings.json was already rewritten and backed up, with the
   record left as it was. Reproduced by replacing ~/.claude/ballast/context_check.py with a
   folder: `IsADirectoryError` from `paths["hook"].unlink()` (uninstall.py:174), exit 1, settings
   undone, record still the full install record. install.py:433-436 handles the same class with
   an "Error:" line. A second run after removing the obstacle finishes the undo, so nothing is
   lost; the message is the gap. The ValueError branch says "nothing written", which is also
   untrue once the settings write at :168 has happened.
3. config/install.py:247-256 and config/uninstall.py:146,213-214: an install-record.json that
   exists but is not valid JSON is treated as absent. Uninstall then says "no install record"
   (not "the record is unreadable"), runs in evidence mode, leaves permissions.deny alone, and
   overwrites the file with `{"uninstalled": true}`, so a record a user could have repaired by
   hand (it holds the values to restore) is gone. Reproduced with `{broken` as the record.
4. keyline/keyline_lint.py:58-61,83-85 and keyline/keyline_hook.py:141-154: the single-token
   word cache lives in keyline/cache/, which .gitignore excludes, so a fresh clone builds it on
   first use and that needs tiktoken. Without tiktoken, `lint_file` raises ModuleNotFoundError;
   the hook catches only OSError, so every Write/Edit of a watched note shows Claude a traceback
   (exit 1, non-blocking). keyline/measure.py:16-19 and scripts/plugin_cost.py:96-100 give the
   one-line install hint for the same case. Reproduced by running the hook with tiktoken
   blocked and the cache folder moved away.
5. hooks/context_check.py:120-123: the comment says Claude Code records only `preTokens` and the
   hook therefore reports 0 after a compaction. Real compact_boundary events (five in this
   session's own transcript) carry `postTokens` (11095 to 20185), and the code at :123 uses it.
   The comment, and the rationale recorded in research/pr-cleanup-progress.md ("Claude Code
   records preTokens only"), are wrong; the code is right. Note that postTokens excludes the
   system prompt and tool definitions: the first assistant event after each compaction showed
   82k-96k, so the value is a floor, which is harmless here because both are under the threshold.
6. keyline/keyline_check.py:34: the proper-noun pattern `(?:[-'][A-Za-z0-9]+)*` absorbs an
   English possessive, so "Claude's hook" yields the invariant `Claude's`, and a rendering that
   writes "the hook of Claude" or Hebrew "של Claude" FAILs on it. Reproduced. It fails closed, so
   no wrong pass, but the limit is not in the README's "Honest limits".
7. Docs tied to one machine: keyline/README.md:23-31 and every command block use
   `py -3.14 -m venv .venv` and `.venv/Scripts/python.exe` (Windows only, while CI and README.md
   use `python -I`); keyline/README.md:115-116 cite `gittoken/.claude/settings.local.json` and
   `C:/Users/PC/Desktop/gittoken/rk-wt/PROGRESS.md`; README.md:171 says "venv in `keyline/.venv/`"
   although `.venv/` is gitignored and nothing creates it; README.md:143 names
   `~/.claude/projects/C--Users-PC-Desktop-gittoken`.

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
