# Review of main 51da01e (2026-10-25, fourth full pass)

Review of every source, config, test and doc file after PR #16 and #17 merged. Baseline on
this tree: pytest 97 passed, keyline suite 35/35 on Linux, pyflakes clean, the JSON files
parse. Each finding was reproduced in the scratchpad before it was accepted. A second,
fresh-context reviewer read the same tree independently; its additions are marked and were
re-reproduced here.

This pass follows the request "fix the class each time": for each finding the bug class is
named in one searchable sentence, the whole repository is searched for the same pattern, every
hit is listed with a verdict and fixed with a failing-first test, and a prevention is added.
The two previous reviews had already found this class twice (third review, findings 4 and 9;
second review, findings 7 and 10): the fixes covered the reported line, not the pattern, which
is why it came back.

Status: all findings fixed in the PR that carries this report. After the fixes: pytest 118
passed, keyline suite 35/35, pyflakes clean, JSON files parse.

## High
None.

## Medium
1. keyline/keyline_lint.py:58-67 and :113-118: with the word cache present and tiktoken not
   installed, `token_count()` calls `_tiktoken()`, which raises `SystemExit` with the install
   hint. `except Exception` does not catch `SystemExit` (it is a `BaseException`), so the
   linter stops with the hint instead of reporting "not one token", and the PostToolUse hook
   with it (exit 1, hint on stderr, the note never linted). Reproduced: a copy of keyline/ with
   its cache, tiktoken hidden, `keyline_lint.py note.txt` on a note holding "mgmt" -> exit 1
   with the hint. Introduced by the fix for finding 4 of the third review (PR #16), which
   turned the ImportError traceback into `SystemExit` without looking at the second caller.

   Class: failure is not empty / "a helper that raises SystemExit inside a function whose
   caller catches Exception".
   Pattern: `sys.exit(` or `raise SystemExit` in any function other than `main()`.
   Other hits (all fixed): config/install.py:194,196 `_read_json` (same bug: the exit escaped
   `verify()`, see finding 5); config/add_to_repo.py:115,117 `_read_json` (same bug);
   config/verify-tokens.py:43 `count_tiktoken` (same bug: exits from inside the file loop).
   Safe: keyline/measure.py:19 (module level, the script's own entry), the scripts' module-level
   usage exits, every `sys.exit(main())`.
   Fixed: `TiktokenMissing(ImportError)` carries the hint; `token_count()` now returns None and
   the finding reads "not one token"; `main()` and the hook print the hint in one line (exit 2
   and 1). `_read_json` in both installers raises `ValueError`, which their `main()` already
   reports. `count_tiktoken` raises `ImportError`, reported by `main()`.
   Prevention: tests/test_source_rules.py `test_only_main_exits` scans every script with `ast`
   and fails CI on an exit outside `main()`.

2. scripts/usertext_top.py:26 (found by CI on Windows after the first push of this PR): the
   script runs with `-I`, which ignores `PYTHONUTF8` and `PYTHONIOENCODING`, so its stdout is
   the console code page (cp1252). The first non-ASCII character in a user's text, or the
   U+FFFD a replaced byte becomes after finding 3's `errors="replace"`, ends the script with
   `UnicodeEncodeError`. Reproduced on Linux with UTF-8 mode off and stdout forced to cp1252
   (tests/test_utf8_output.py), and by the Windows CI job. Any non-English transcript hits it.

   Class: words / "a script that prints input-derived text without setting UTF-8 output"
   (the class of the Windows fix in PR #16 for install.py, which covered the three installers).
   Pattern: a `print()` to stdout in a script with no `sys.stdout.reconfigure(encoding="utf-8")`.
   Other hits (all fixed): scripts/toolresult_share.py:81,86 and scripts/unused_tools.py:55
   (tool names from the transcript; same bug), config/verify-tokens.py:141,143 (file names;
   same bug), scripts/lint_validate.py:71-80 (corpus words; same bug), scripts/plugin_cost.py:111
   (plugin names; same bug), scripts/tokentest.py:69 (decoded token pieces; it wrapped stdout
   in its own `TextIOWrapper`, the same fix spelt differently; now the common form).
   Safe but brought under the rule: scripts/usertext_split.py:27 and scripts/usage_breakdown.py
   (fixed labels and numbers), hooks/context_check.py:172 (`json.dumps` is ASCII). Stderr needs
   nothing: Python writes it with `backslashreplace`.
   Fixed: every script sets UTF-8 stdout before its first print (the installers and keyline
   scripts already did).
   Prevention: tests/test_source_rules.py `test_scripts_that_print_set_utf8_stdout` fails CI
   on a script that prints to stdout without the reconfigure; tests/test_utf8_output.py runs
   five scripts on a cp1252 console with non-ASCII input.

## Low
3. keyline/keyline_lint.py:105: a `keyline-allow.txt` (or `--allow` file) that is not UTF-8
   raises `UnicodeDecodeError` out of `load_allow()`, which `lint_file()`'s UTF-8 handling at
   :160-165 does not cover: traceback from the linter and from the hook on every write of a
   note under that folder. Reproduced with a Latin-1 allow file beside a clean note.

   Class: hostile input / "a text file opened as UTF-8 whose decode error is not handled"
   (the class of third-review finding 9 and second-review finding 10).
   Pattern: `open(... encoding=...)` in text mode or `.read_text(...)` without `errors=` and
   not under a `try` that handles `UnicodeDecodeError`.
   Other hits: keyline/keyline_lint.py:92 `load_words` (same bug on a damaged cache file;
   fixed), scripts/usertext_split.py:14, scripts/usertext_top.py:11 and
   scripts/toolresult_share.py:33 (same bug; the sibling scripts unused_tools.py and
   usage_breakdown.py already read with `errors=`; fixed with `errors="replace"`),
   config/verify-tokens.py:116 (same bug, a traceback mid-table; fixed: "Error reading" and the
   next file), config/install.py:190 and config/add_to_repo.py:111 `_read_json` (the decode
   error was caught as "not valid JSON", a wrong message; fixed: "is not UTF-8"),
   config/install.py:416 (the template read in `verify()`; fixed by `_read_text`),
   scripts/unused_tools.py:59 (the repository's own template; fixed with one handler).
   Safe: config/install.py:229 and :256, hooks/context_check.py:158 (under a handler),
   config/uninstall.py:156 and scripts/plugin_cost.py, scripts/lint_validate.py (errors=).
   Fixed: one `read()` helper in keyline_lint.py (as keyline_check.py has) used by
   `load_words`, `load_allow` and `lint_file`; the others as listed.
   Prevention: tests/test_source_rules.py `test_text_reads_handle_a_decode_error` scans every
   script and fails CI on a text read with neither `errors=` nor a decode handler.
4. keyline/keyline_check.py:127-138: `hedges()` skips a capitalised "May" only when a number
   follows, so "It shipped in May because the fix landed" counts a possibility hedge. A Hebrew
   rendering that writes the month as מאי is then reported as "hedges lost: possibility (may)".
   Reproduced with that sentence against its Hebrew rendering: FAIL. (The month is also
   extracted as a proper noun, like any month name, so the rendering has to keep "May"
   literally; that is the checker's rule for names and is unchanged.)

   Class: words / "a month name matched by the modal rule by case alone" (the class of
   third-review finding 8, whose fix covered "May 2026" only).
   Pattern: the modal "may" matched case-insensitively with a capitalised exception.
   Other hits: none; "May" is the only hedge, negation or stop word that is also a month.
   Fixed: a capitalised "May" that is not at a sentence start is the month; "May I help?" at a
   sentence start or after a list marker is still the modal.
   Prevention: tests/test_keyline_check.py pins the four forms.
5. config/install.py:462: `verify()` runs outside the `try` that reports a `ValueError` or
   `OSError` from `install()`, both after an install and under `--verify-only`. A hook path
   that is a folder gives `IsADirectoryError` from `read_bytes()` (:421) as a traceback, and a
   bad settings.json exited from `_read_json` with "nothing written" after the install had
   written. Reproduced with `~/.claude/ballast/context_check.py` as a folder: traceback from
   `--verify-only`. CHANGELOG says the install "reports a file-system error ... as one line".

   Class: neighbors / "a script's file reads without the OSError handler its sibling path has".
   Pattern: an entry point that reads or writes files outside its `try ... except OSError`.
   Other hits: config/add_to_repo.py:135-174 `main()` (same bug: no handler at all; `.claude`
   as a regular file gives `FileExistsError` from `os.makedirs`; fixed: the work moved to
   `_add()`, `main()` reports `ValueError` and `OSError` in one line), keyline/keyline_lint.py:190
   `load_words()` and `--rebuild-cache` (same bug: a cache path in the way is a traceback;
   fixed). Safe: config/uninstall.py `main()` (both handlers), keyline/keyline_check.py `main()`
   (every read under a handler), keyline/keyline_hook.py (OSError handler), hooks/context_check.py
   (`except Exception` with a log line).
   Fixed: `verify(home)` runs under the same handlers as `install()`.
   Prevention: a test per entry point with a file in the way (tests/test_install.py,
   tests/test_add_to_repo.py, tests/test_keyline_lint.py); the exit scan of finding 1 keeps
   `_read_json` an exception the handlers can see.

## Checked and found correct
- hooks/context_check.py: band logic, compaction reset, state pruning and log trimming, the
  UTF-8 stdin wrapper, invalid-integer fallbacks. config/uninstall.py: both handlers in
  `main()`, the record leftover, the missing-backup path. keyline_check.py: the timestamp,
  possessive and empty-source fixes of the third review hold; `present()` with a space for the
  `T`. keyline_hook.py: the watch patterns and the exit codes. scripts/unused_tools.py and
  usage_breakdown.py: tolerant reads, non-object lines. CI: both runners, PYTHONUTF8 comment.
- README.md, keyline/README.md, CHANGELOG.md: the suite counts (35, 36 on Windows), the
  one-line install hint, the install ordering claims; the CHANGELOG line on install's
  file-system errors is now true for the verification step too (finding 5).
