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

Status: all 15 findings fixed in the PR that carries this report, plus ten more (16-25) found by
the pre-merge self-review: one regression of the fixes and nine edges of them, from a third
fresh-context reviewer run on the PR diff. After the fixes: pytest 154 passed (1 skipped as
root), keyline suite 35/35, pyflakes clean, JSON files parse. Findings 1-5 are the first
reviewer's, 6-15 the second reviewer's (its finding 4 is finding 1 here); the second reviewer
ran against the tree before the first five fixes and found none of them fixed by accident.

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

## Medium (second reviewer)
6. keyline/keyline_check.py:30-44: the INVARIANT regex has no alternative for a plural acronym
   (`PRs`), a bare version (`v2`), a git hash (`b07b3b6`), a lowercase word with a digit
   (`sha256`, `utf8`) or a dunder (`__init__`), so none is checked and a rendering that changes
   one PASSes when any other invariant keeps the source out of `INCONCLUSIVE`. Reproduced:
   `deploy: v2 live at 14:02` against `deploy: v3 live at 14:02` -> PASS, and the same for
   each of the other shapes.

   Class: words / "an extraction rule whose fall-through is silence: a token no alternative
   matches is not checked, and the checker cannot tell the user".
   Pattern: a token shape common in technical notes that `invariants()` returns nothing for.
   Other hits: `v2` (version alternative took `v1.2` only; fixed), `PRs`/`MRs` (upper took
   capitals only; fixed with an optional trailing `s` on two or more capitals, so `As`/`Is`/`Qs`
   stay prose), hex hashes (no alternative; fixed for 7-40 hex characters holding both a letter
   and a digit, so `deadbeef` and `defaced` stay prose), `__init__` (snake needed an inner
   underscore; fixed), lowercase+digit words (no alternative; fixed, after `number` so `14:02`
   and `2026` keep their kinds). Recorded, not extracted (keyline/README.md Honest limits):
   kebab names, two-word lowercase paths, hex hashes without a digit, lowercase words without a
   digit, one-letter acronym plurals. Every new extraction fails closed: a rendering has to keep
   the token literally.
   Fixed: the five alternatives above; keyline suite still 35/35 (no new extraction changed a
   PASS in the fixtures).
   Prevention: tests/test_keyline_check.py pins each shape (extracted, missing when changed,
   present in a Hebrew rendering) and pins the prose words that must not be extracted; the
   Honest limits list names what is still outside the rules, so a gap is a documented limit,
   not a silent one.

7. keyline/keyline_check.py:174-181 `present()`: a number is searched with the same boundary as
   every other token (`R` blocks a letter, a digit, `_` and `.digit`), so `10` is found inside
   `10:00` and `2` inside `2,500`. Reproduced: `max 10 connections at 14:02` against `restart
   at 10:00 at 14:02` -> PASS with the fact gone.

   Class: endings / "a presence check whose boundary is looser than the token the extraction
   took" (the extraction treats `2,500` and `10:00` as one token; the search did not).
   Pattern: `present()` for a kind whose extraction alternative allows an inner separator.
   Other hits: `1.2` in `1.2.3`, `80` in `8080`, `50%` in `150%`, `v2` in `v2.1`, `API` in
   `APIs`, a date in a timestamp: all already a miss (safe). `14:02` in `14:02:30` is found:
   the same instant at finer precision (safe, kept).
   Fixed: a number is searched with `L_NUMBER`/`R_NUMBER`, which also block `[.,:]digit` on
   either side; extraction is unchanged, so no fixture or count moved.
   Prevention: tests/test_keyline_check.py pins both separators, and the positive cases (`2`
   with `2,500` elsewhere in the rendering; a Hebrew rendering of `1,900`).

8. keyline/keyline_check.py:97-104 `_is_sentence_start`: it walks back over spaces and treats
   any of `-*+#>` as a list marker wherever it stands, so a name after a mid-line dash, `>` or
   `**bold:**` label is sentence furniture and never extracted. Reproduced: `db: moved to
   Postgres - Prisma stays at 14:02` against the same line without Prisma -> PASS.

   Class: words / "a line-start rule applied mid-line" (a marker is a marker only at the start
   of its line).
   Pattern: a check for a list or heading marker that does not look at what precedes it on
   the line.
   Other hits: keyline/keyline_check.py:60 `LIST_MARKER` is anchored with `^` (safe);
   keyline/keyline_lint.py's furniture rules match whole lines (safe).
   Fixed: a marker counts only when everything before it on the line is marker or space, so
   `- **Language:** TypeScript` still skips `Language` and now checks `TypeScript`, and a
   quoted or headed line still skips its first word.
   Prevention: tests/test_keyline_check.py pins a dash and a `>` mid-line (checked) against a
   bullet, a heading and a quote (first word skipped).

9. keyline/keyline_check.py:75-81 and :127-138: `HEDGE_GROUPS` is English only, so every
   hedged source FAILs against a correct Hebrew rendering with "hedges lost"; a month or
   weekday name is a proper noun that the rendering has to keep in English; and `MAY` in
   mixed case still counts as the modal. Reproduced: `risk: pool could be exhausted at 14:02;
   fix should ship` against its Hebrew rendering -> FAIL (possibility, obligation);
   `due: Monday at 14:02` against `יעד: ביום שני ב-14:02` -> FAIL (missing Monday). Fail
   closed, but the documented Hebrew use case could not PASS for a hedged or dated note.

   Class: neighbors / "a language-aware check with one language's word list where its sibling
   has both" (`NEG_HE` sits next to `NEG_EN`; the hedges had no Hebrew list).
   Pattern: a word list or alias table in keyline_check.py that exists for English only.
   Other hits: `PROPER_STOP` (English furniture; Hebrew has no capitals, so no Hebrew list is
   needed: safe); `LIST_MARKER` (punctuation: safe); the month/weekday names (no alias table at
   all; fixed with `CALENDAR`, full names and abbreviations, matched with the Hebrew prefixes
   because the boundary is ASCII-only).
   Fixed: `HEDGE_GROUPS_HE` with the four classes (inflections and the prefixes ו/ש/וש/כש),
   `CALENDAR` aliases used by `present()`, and an all-caps `MAY` is the month unless another
   all-caps word stands on the line (`WE MAY FAIL`).
   Prevention: tests/test_keyline_check.py pins a Hebrew rendering that keeps the classes
   (PASS), one that drops them (FAIL with both classes named), the word-to-class map, five
   calendar forms with their Hebrew form, the wrong weekday (FAIL) and the two `MAY` cases;
   keyline/README.md Honest limits says the Hebrew hedges are a word list.

10. config/install.py:364-425 `verify()`: it checks that the hook command names the hook file
    and nothing about the interpreter in front of it. The command embeds the absolute Python
    that ran the installer; after `rm -rf .venv` or a pyenv bump the shell prints "not found",
    `|| exit 0` keeps the prompt unblocked, and the reminder never fires again while
    `--verify-only` says all is well. Reproduced: interpreter replaced by
    `/nonexistent/venv/bin/python` -> `verify()` returns `(True, [], [])`.

    Class: outside call / "a verifier that checks the argument of a command and not the thing
    that runs it".
    Pattern: code that inspects a stored shell command string for correctness.
    Other hits: config/add_to_repo.py and config/repo-settings.json (the repository hook uses a
    bare `python3` and has no verifier; a missing `python3` there is the user's PATH: safe);
    `_is_ours` and `has_our_hook` (identify the entry, do not vouch for it: safe);
    keyline/keyline_hook.py `--print-config` (prints, never verifies: safe).
    Fixed: `verify()` reads the first word of the command (`shlex` on POSIX, the quoted token
    on Windows) and fails with "Hook interpreter not found: ...; run install.py again" when a
    path-like interpreter does not exist or a bare name is not on PATH.
    Prevention: tests/test_install.py pins the missing path (FAIL) and a bare name on PATH
    (PASS); README.md says what verification checks and how to repair it.

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

## Low (second reviewer)
11. keyline/keyline_hook.py:78 `watched()`: when the file is outside the project
    `relative_to` raises and the absolute path is used instead, so `~/notes/todo.md` or a
    sibling repository's `plans/x.md` is a watched note from any project: the hook lints it
    and exits 2 with "fix the file". Reproduced with `CLAUDE_PROJECT_DIR=proj` and a Write of
    `elsewhere/notes/todo.md` -> rc 2.

    Class: hostile input / "a path-relative test that falls back to the absolute path when
    the file is outside the root".
    Pattern: `relative_to(root)` under a `try` whose `except` keeps the absolute path.
    Other hits: keyline/keyline_hook.py:66 (the `--watch` patterns: a relative pattern is
    matched against `rel=None`, an absolute one against the absolute path, by design: safe);
    :100 (display only: safe).
    Fixed: the no-pattern fallback returns False outside the project.
    Prevention: tests/test_keyline_hook.py (new) runs `watched()` on an inside and an outside
    note and the hook itself as a subprocess on the outside one (rc 0, no output); the hook
    docstring and both READMEs say "of the project".

12. config/install.py:347 writes `CLAUDE.md` in place with `write_text`, and :328 the hook
    with `write_bytes`; `main()` prints only the error on `OSError`. A write that fails part
    way (disk full) leaves the user's `CLAUDE.md` as a truncated fragment, and the backup
    that holds the original is never named because the changes list is dropped with the
    exception. Reproduced with ENOSPC after five bytes: rc 1, `CLAUDE.md` = `# Sid`, backup
    present and unlisted, no record written.

    Class: halfway / "a user file overwritten in place, so a failed write is a truncated file"
    (and its report: "an error path that drops the progress made before it").
    Pattern: `write_text`, `write_bytes`, `open(..., "w")` or `shutil.copyfile` onto a file the
    user owns.
    Other hits: config/install.py:211 `_backup` (`copy2` to a new name: a failed backup is a
    partial copy under a `.bak` name and the original untouched: safe); config/uninstall.py:193
    `shutil.copyfile(backup, claude_md)` (same bug on the restore path; fixed);
    config/add_to_repo.py:190 `copyfile` of the hook into the repository (same bug; fixed);
    config/install.py:215 `_write_json` and config/add_to_repo.py:125 (already temp+rename:
    safe, now share the helper). hooks/context_check.py:66,169, keyline/keyline_lint.py:102
    and scripts/plugin_cost.py:106 write the tool's own state, cache and output files, which
    are rebuilt on the next run (safe).
    Fixed: one `_write_bytes` helper (temp file beside the target, mode copied, `os.replace`)
    in install.py used by `_write_json`, the hook, `CLAUDE.md` and uninstall's restore; a local
    copy in add_to_repo.py (stdlib-only, no import of install.py). `install()` and
    `uninstall()` take a `progress` list that each file-level change is appended to as it
    happens; on `OSError` `main()` prints "Done before the error:" with those lines, so the
    backup name is on screen.
    Prevention: tests/test_install.py and tests/test_uninstall.py fail the rename after a
    truncating write and check that the file is intact and (install) the backup is named.
    Pre-mortem of the fix: the rename needs write permission on the parent folder where the
    in-place write needed it on the file only; a read-only `~/.claude` with a writable
    `CLAUDE.md` now fails with a one-line `PermissionError` naming the folder instead of
    writing, which is the fail-closed side. The file mode is copied so a `chmod 600`
    `settings.json` stays `600`. Symlinks are still written through (`resolve` first).

13. config/uninstall.py:99-107: the deny removal is guarded by `isinstance(deny, list)` with
    no `else`, so a `permissions.deny` that is a string (a hand edit or a sync tool) is
    skipped in silence and `_leftover_record` drops `deny_added`; a later run says "Nothing to
    undo" and the six tools stay denied. Reproduced: record becomes `{"uninstalled": true}`.

    Class: failure is not empty / "a type guard that turns a wrong shape into a no-op and
    forgets the work it skipped".
    Pattern: `isinstance(...)` guards in undo_settings with no notice and no `left` entry.
    Other hits: config/uninstall.py:115-124 (hooks not a dict, entries not a list: nothing of
    ours can be inside a container of the wrong shape, so there is nothing to undo or to keep:
    safe); the scalar keys (compared by value, not shape: safe). config/install.py `verify()`
    already reports a non-list deny (safe).
    Fixed: a notice `permissions.deny is not a list (...); left as is`, `permissions.deny`
    goes on the left list and `deny_added` stays in the leftover record, so once the user
    turns it back into a list a second run removes the tools.
    Prevention: tests/test_uninstall.py pins the notice, the kept `deny_added` and the second
    run's removal.

14. config/add_to_repo.py:170: `os.path.exists` is False on a dangling symlink, so
    `.claude/settings.json -> /gone/dotfiles/settings.json` is "absent"; `_write_json` then
    resolves the link and `mkstemp` fails inside the missing folder. On main that was a
    traceback; after finding 5 of this review it is one misleading line naming the temp file.
    Reproduced both ways.

    Class: neighbors / "the installer's dangling-symlink check that its sibling installer
    does not have" (install.py got the check in PR #16, for two of its four paths).
    Pattern: a file the installer writes that is not checked with `is_symlink() and not
    exists()` before any write.
    Other hits: config/install.py:311 covered `settings` and `claude_md` only; the hook file
    and the install record were the same bug (a dangling hook link: `write_bytes` followed
    the link into the missing folder; fixed, all four paths). config/add_to_repo.py: the
    repository hook file (same bug; fixed). config/uninstall.py: reads and unlinks only; a
    dangling link is "absent" and left alone (safe).
    Fixed: both installers check every path they write, with the same "symlink to a missing
    target; fix or remove it first" message and nothing written.
    Prevention: tests/test_install.py and tests/test_add_to_repo.py are parametrised over
    every written path.

15. Docs that contradicted the code: README.md:66 said `settings.json` is written last (the
    record comes after it, for the reason in CHANGELOG); CHANGELOG.md:20 said the hook exits
    2 on a non-UTF-8 note (it exits 1, non-blocking); README.md:169 and keyline/README.md:114
    did not say the hook watches `notes/` and `plans/` of the project only; keyline/README.md
    Honest limits did not list the gaps of findings 6 and 9.

    Class: words / "a doc sentence that states a behaviour no test pins".
    Pattern: an ordering, exit-code or scope claim in README.md, keyline/README.md or
    CHANGELOG.md.
    Other hits: the suite counts in README.md, keyline/README.md and CHANGELOG.md (re-run and
    compared by hand this pass, 35 and 36: correct, not pinned); "written through a symlink"
    (pinned by the symlink tests in tests/test_install.py, test_uninstall.py and
    test_add_to_repo.py: safe); the install hint line (pinned by tests/test_keyline_lint.py:
    safe).
    Fixed: the five sentences, plus the new behaviours of this PR (atomic writes, the
    interpreter check, Hebrew hedges and calendar forms, the new extractions and what is still
    not extracted).
    Prevention: the behaviours the sentences describe are now each pinned by a test (exit
    code: tests/test_keyline_hook.py; ordering and atomic writes: tests/test_install.py), so
    a change breaks a test before it makes the sentence false.

## Pre-mortem of the fixes
- Words: the new extractions (finding 6) can only turn a PASS into a FAIL; a technical note
  with `utf8` now needs `utf8` in the rendering, which is the checker's rule for identifiers.
  The keyline fixtures did not move (35/35). A Hebrew source gains hedge classes from the
  Hebrew words (finding 9), symmetric with English.
- Neighbors: `present()` keeps `L`/`R` for every kind but number (finding 7), so no other
  kind's matching changed; `_is_sentence_start` still skips the first word of a bullet,
  heading and quote (finding 8).
- Outside call: a hand-written hook command whose interpreter is an environment variable or
  a shell function fails the new interpreter check (finding 10); the message says to run
  install.py again, which writes an absolute path.
- Halfway: see finding 12 (parent-folder permission, mode copy).
- Endings: `_write_bytes` removes its temp file on every failure path; the tests assert no
  `.CLAUDE.md-*` leftovers.

## Pre-merge self-review

### 16. Low: a file the installers create for the first time got mode 0600 (regression of 12)
- Where: `config/install.py` `_write_bytes` and `config/add_to_repo.py` `_write_bytes` (the
  atomic-write helpers added for finding 12).
- Reproduced: on the committed branch, `_write_bytes` on a path that does not exist left the file
  at 0600 under umask 022 (`mkstemp` creates the temp file private, and the mode was copied only
  from an existing target). On main the hook and `CLAUDE.md` were written with `write_bytes` /
  `write_text` / `copyfile` and got 0644; `settings.json` already came out of `mkstemp` at 0600
  there. A fresh `<repo>/.claude/hooks/context_check.py` or `<repo>/.claude/settings.json` that is
  read by another account, or a backup tool that preserves modes, sees the stricter mode.
- Class: neighbors / "a temp file created by mkstemp is renamed into place without resetting its
  mode": the helper kept the mode of an existing file and forgot the new-file branch.
- Pattern searched: `mkstemp` across the repository.
- Other hits: `config/install.py` `_write_bytes` (same bug, fixed), `config/add_to_repo.py`
  `_write_bytes` (same bug, fixed), `config/uninstall.py` (uses `install._write_bytes`, covered).
  No other `mkstemp` in the repo.
- Fixed: a new file gets `0o666 & ~umask` (what a plain write gives); an existing file keeps its
  mode as before. `_umask()` reads the umask by setting and restoring it.
- Tests (verified failing on the committed helpers: both wrote 0600): `tests/test_install.py`
  `test_new_files_get_the_umask_mode_not_the_temp_file_mode`, `tests/test_add_to_repo.py`
  same name. Skipped on Windows, where `st_mode` carries only the read-only bit.
- Prevention: the two helpers are the only writers of user files, and each has the mode test.

### 17. Medium: a Hebrew month or weekday form matched inside another Hebrew word (edge of 14)
- Where: `keyline/keyline_check.py` `present()`: the Hebrew forms from `CALENDAR` were wrapped in
  `L`/`R`, which are ASCII-only boundaries, so Hebrew letters could stand on either side.
- Reproduced: source "ship: May 3", rendering "מאיפה 3" passed (`מאיפה`, "from where", holds
  `מאי`); likewise `Sat` inside `מחשבת` and `June` inside `יוניקוד`. A rendering that dropped the
  month passed: the checker's no-false-PASS guarantee was broken for Hebrew renderings.
- Class: words / "a non-ASCII token matched with ASCII word boundaries". `NEG_HE` and `HEDGE_HE`
  already used `(?<![א-ת])` / `(?![א-ת])`; the calendar forms were the odd one out.
- Pattern searched: every regex built from a Hebrew list (`CALENDAR`, `HEDGE_HE`, `NEG_HE`,
  `HEDGE_GROUPS_HE`) and its boundaries.
- Other hits: none; the three other lists already carried Hebrew-letter boundaries.
- Fixed: each Hebrew form is its own alternative, `(?<![א-ת])[ובלמהשכ]{0,3}form(?![א-ת])`, so up to
  three prefix letters are allowed (במאי, ממאי, ובמאי) and nothing else. `לשבת` ("to sit") is ל +
  שבת and still counts as Saturday; documented in `keyline/README.md` Honest limits.
- Test (failed before the fix): `tests/test_keyline_check.py`
  `test_a_hebrew_calendar_form_inside_another_word_is_not_the_name` (May/מאיפה, Sat/מחשבת,
  June/יוניקוד; also asserts the three prefixed forms and לשבת pass).
- Prevention: `HEB` is the one boundary class used by every Hebrew regex; the test pins it.

### 18. Low: a label value after `**Label:**` became a checked name (edge of 8)
- Where: `keyline/keyline_check.py` `_is_sentence_start` and `PROPER_STOP`.
- Reproduced: source "- **Status:** Done", rendering "- **סטטוס:** בוצע" failed with "missing
  Done": finding 8 made the word after a mid-line label a mid-sentence word, so a capitalised
  status value counts as a proper name, and the hook pushes the English word into Hebrew notes.
- Class: words / "a capitalised common word counted as a name because of its position".
- Pattern searched: label values a rendering translates (`Done`, `High`, `Low`, `Medium`,
  `Closed`, `Blocked`, `Pending`, `Ready`, `Active`, `None`) against `PROPER_STOP`, which had
  `yes`, `no`, `open` only.
- Other hits: the ten values above, all added to `PROPER_STOP`; `- **Stack:** Postgres` is still
  checked (finding 8 kept).
- Test (failed before the fix): `test_a_status_value_after_a_bold_label_is_not_a_name`.
- Prevention: `PROPER_STOP` is the single list for common capitalised words; the comment names
  the label-value group so the next value goes there.

### 19. Low: `MAY` beside any acronym was the modal, so the CHANGELOG claim was false (edge of 15)
- Where: `keyline/keyline_check.py` `_all_caps_line`: `\b[A-Z]{2,}\b` matched `UTC`, `API`,
  `PR`, `DB`, which share almost every dated line with an all-caps month.
- Reproduced: "ship: MAY, 14:02 UTC" against its Hebrew rendering failed with "hedges lost:
  possibility (may)".
- Class: words / "a heuristic keyed on one neighbouring token instead of the line's shape".
- Pattern searched: every use of `_all_caps_line` (one caller, `hedges()`).
- Fixed: the line is all-caps only when it has no lowercase letter and another all-caps word
  ("WE MAY FAIL"); a mixed-case line makes `MAY` the month. The CHANGELOG sentence is now true.
- Test (failed before the fix): `test_upper_case_may_beside_an_acronym_is_the_month`.
- Prevention: the test pins the acronym case next to the all-caps-sentence case.

### 20. Low: a symlinked `notes/` or `plans/` folder inside the project was no longer watched (edge of 1)
- Where: `keyline/keyline_hook.py` `watched()`: the outside-project check resolved the file path
  but compared it with the unresolved project root, so a `notes/` folder symlinked to Dropbox,
  iCloud or another repo looked outside the project and the hook went silent.
- Class: neighbors / "one side of a path comparison resolved, the other not".
- Pattern searched: `resolve()` and `relative_to` across `keyline/` and `config/`
  (`config/install.py` `_runnable` and the symlink checks compare like with like).
- Other hits: none.
- Fixed: the lexical absolute pair is tried first (a symlinked folder inside the tree matches
  there), then the resolved pair; only when both fail is the file outside the project.
- Test (failed before the fix): `tests/test_keyline_hook.py`
  `test_a_symlinked_notes_folder_inside_the_project_is_watched` (skipped on Windows).
- Prevention: the test, beside the outside-project test from finding 1.

### 21. Low: `_write_bytes` on a read-only target: a stray temp file on Windows, a silent overwrite on POSIX (edge of 12)
- Where: `config/install.py` `_write_bytes`, `config/add_to_repo.py` `_write_bytes`.
- Reproduced: on POSIX a `chmod 444` `settings.json` was replaced by the rename (main's plain
  write refused it with `PermissionError`). On Windows `os.replace` fails on a read-only target,
  and the `finally` block's `os.remove` failed on the read-only temp file (mode copied from the
  target), leaving `.settings.json-xxxx` behind and masking the real error.
- Class: endings / "a cleanup step that can itself fail for the reason the write failed".
- Pattern searched: `mkstemp` (the two helpers; uninstall uses install's).
- Other hits: both helpers, fixed the same way.
- Fixed: an existing target that is not writable is refused up front with
  `PermissionError(EACCES, "the file is read-only; make it writable first")`, as main did; the
  `finally` block chmods the temp file to 0600 before removing it, so the remove cannot fail on
  the mode.
- Tests: `tests/test_install.py`
  `test_write_bytes_removes_the_temp_file_even_when_the_target_is_read_only` (passes on POSIX,
  documents the Windows case, runs on both CI runners) and `test_write_bytes_refuses_a_read_only_target`
  (failed before the fix; skipped as root, where `os.access` says writable).
- Prevention: the two helpers remain the only writers; both tests run in CI on Windows.

### 22. Low: `verify()` reported a hook interpreter written with `~` or `$HOME` as "not found" (edge of 6)
- Where: `config/install.py` `_runnable`.
- Reproduced: a hand-edited command (README "Manual install" step 1) such as
  `~/.venv/bin/python3 ...` or `$HOME/.venv/bin/python3 ...` failed verification although the
  shell expands both; a Git-Bash `/c/Python312/python.exe` on Windows did too.
- Class: words / "a path checked as typed, not as the shell will read it".
- Other hits: none (`_interpreter` writes an absolute path, so only hand edits reach this).
- Fixed: `expanduser` and `expandvars` before the check; on Windows a `/`-rooted path passes.
- Test (failed before the fix):
  `test_verify_accepts_a_hook_interpreter_written_with_tilde_or_a_variable`.
- Prevention: the test; `_runnable` is the one place the interpreter is checked.

### 23. Low: `test_usage_breakdown_runs_on_a_cp1252_console` passed on the old code (edge of 3)
- Where: `tests/test_utf8_output.py`.
- Reproduced: `scripts/usage_breakdown.py` prints only ASCII, so the cp1252 run could not tell
  the fixed script from the old one; the test was not evidence.
- Class: failure is not empty / "a regression test that passes without the fix".
- Fixed: the test is removed; a comment says why, and `tests/test_source_rules.py` keeps the
  script's UTF-8 stdout wrapper.
- Prevention: the failing-first rule of the fix routine (every other new test in this PR was
  run against the old code first).

### 24. Low: Hebrew hedge words with plain senses fail a Hebrew source against an unhedged English rendering (edge of 13)
- Where: `keyline/keyline_check.py` `HEDGE_HE`: ניתן is also "was given", סביר also
  "reasonable", so a Hebrew source using the plain sense gains a hedge class that a correct
  English rendering lacks.
- Class: words / "a word list used as a sense list".
- Decision: not changed. Dropping the words would bring back finding 13's false "hedges lost"
  for the common hedge sense; the check is symmetric by design. Documented in
  `keyline/README.md` Honest limits so the FAIL is explainable.
- Prevention: the README entry; the hook's message names the hedge class, which points at it.

### 25. Low: `hedges()` kept list markers and `__Bold__` was a dunder (edges of 8 and 7)
- Where: `keyline/keyline_check.py` `hedges()` and the `snake` alternative of `INVARIANT`.
- Reproduced: `hedges("2) May we proceed?")` gave no hedge (the `)` marker made `May` look
  mid-sentence) while `1. May we proceed?` and `- May we proceed?` gave the modal;
  `invariants("__Important__ note")` listed `__Important__` as a dunder, so a Hebrew rendering of
  a markdown note using `__text__` emphasis failed with "missing __Important__".
- Class: neighbors / "a normalisation applied in one extractor and not its sibling".
- Pattern searched: `LIST_MARKER` uses (`invariants()` only, before the fix) and the dunder
  regex (two places, both changed).
- Fixed: `hedges()` strips `LIST_MARKER` first, as `invariants()` does; a dunder is
  `__[a-z0-9]+__` (every real dunder, no bold word) in the extractor and the skip check.
- Tests (failed before the fix): `test_hedges_skip_list_markers_like_invariants`,
  `test_markdown_bold_with_underscores_is_not_a_dunder`.
- Prevention: the tests pin both extractors against the same inputs.

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
