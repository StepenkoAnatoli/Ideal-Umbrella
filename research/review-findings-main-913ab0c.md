# Review of main 913ab0c (2026-10-25, second full pass)

Read-only review of every source, config, test and doc file after PR #13 merged.
Baseline on this tree: pytest 64 passed, keyline suite 35/35 on Linux, pyflakes clean,
the three JSON templates parse. Each finding below was reproduced or traced to the line.

## High
None.

## Medium
1. scripts/toolresult_share.py, scripts/usertext_split.py, scripts/usertext_top.py crash on a
   transcript line that is a JSON list or string: `e.get(...)` runs before any isinstance check
   (`AttributeError: 'list' object has no attribute 'get'`, reproduced with a file holding `[1,2]`).
   This is the same bug class fixed in usage_breakdown.py and unused_tools.py.
2. scripts/toolresult_share.py divides by zero on empty input or a transcript with no tool
   results (`tr / total`, `sum(big.values()) / tr`, `v / tr`). Reproduced with an empty .jsonl.
   usertext_split.py and usertext_top.py divide `v/tot` inside a loop that is empty when tot is 0,
   so they print nothing instead of crashing; they also give no usage message with no arguments.

## Low
3. scripts/unused_tools.py counts a tool_use block without a "name" as the tool `None` and
   prints "None: 1" (reproduced). Should skip or label it.
4. README.md says the keyline suite "has 35 checks on Windows and 34 elsewhere"; the suite has
   35 on Linux/macOS and 36 on Windows (one `os.name == "nt"` check is added, run_tests.py:144).
   keyline/README.md says `35/35`, which is right for Linux only.
5. config/install.py writes install-record.json before settings.json (install.py:333 vs 339).
   If the settings write fails, the record claims keys were installed that were not. Uninstall
   handles it (values differ from the installed ones, so they are reported and left), so the
   effect is a misleading notice, not data loss.
6. config/install.py `quote()` on Windows escapes an inner quote as `\"`, which cmd.exe does not
   honor; a home path containing a double quote would produce a broken hook command. Such paths
   are practically nonexistent on Windows (the character is not allowed in file names).
7. hooks/context_check.py: a compact_boundary event returns `compactMetadata.postTokens`, which
   Claude Code transcripts may not carry (they record preTokens). The hook then reports 0 until
   the next assistant event, which clears the band state; that is the intended reset, so the
   only cost is one prompt where the size is unknown. Keep in mind if the hook is ever used for
   anything besides the hand-off reminder.
8. config/install.py `_is_ours` and the same test in add_to_repo.py and uninstall.py treat any
   hook whose command contains "context_check.py" as Ideal-Umbrella's. A user's own hook with
   that file name would be rewritten or removed. Documented behaviour, pre-existing, unlikely.
9. keyline/measure.py imports tiktoken at module import time with no friendly message; the other
   tiktoken users (verify-tokens.py, plugin_cost.py, lint_validate.py) say how to install it.
10. Doc leftovers naming one machine: keyline/keyline_hook.py docstring example path
    `C:/Users/PC/Desktop/gittoken/...`; keyline/tests/run_tests.py docstring says to run with
    `.venv/Scripts/python.exe` and cites `gittoken/machine-language-panel-results.md` (the file
    is research/panel-results.md here). CHANGELOG.md says "HISTORY.md holds the narrative
    research log" while README points at research/progress-log.md; both files exist.

## Checked and found correct
- install/uninstall round trips, record merging, symlink write-through, backup naming, the
  `|| exit 0` guard, verify() warnings vs failures, non-UTF-8 CLAUDE.md handling.
- add_to_repo merge semantics (scalar kept unless --force, hook updated in place, siblings kept).
- context_check band logic, tail read, sidechain skip, UTF-8 stdin, state pruning, log trim.
- keyline_check invariants/hedges/negations and INCONCLUSIVE; keyline_lint; keyline_hook --watch.
- usage_breakdown cache-write split and duplicate message ids; lint_validate; plugin_cost;
  CI workflow; the three JSON templates; tests match the behaviour they describe.
