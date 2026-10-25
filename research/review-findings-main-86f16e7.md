# Review of main 86f16e7 (2026-10-25, fifth full pass)

Review of every source, config, test and doc file after PR #18 merged. Baseline on this tree:
pytest 154 passed, 1 skipped (as root), keyline suite 35/35 on Linux, pyflakes clean on
keyline/ and scripts/, the JSON files parse, working tree clean. Two fresh-context reviewers
read the tree in parallel: A on keyline/, scripts/ and their docs (findings marked A), B on
config/, hooks/, tests/, CI and their docs (marked B). Their full reports are in the scratchpad
(`review5/a/report.md`, `review5/b/report.md`, not in the repo). Every medium finding and a
sample of the lows (A3, A4, A5, B2) were re-reproduced here with `python -I` before being
accepted; the rest are quoted from the reviewers' own probe output. Nothing in the repo was
changed by this pass.

Status: all 20 findings fixed in PR #19 (the PR that carries this report), each with a
failing-first test, a search of the whole repository for the same pattern (listed under "Other
hits") and a prevention. After the fixes: pytest 178 passed (1 skipped as root), keyline suite
35/35, pyflakes clean, JSON files parse. Counts: 0 high, 3 medium, 17 low. Findings 17 and 18
were PLAUSIBLE (one step depends on Claude Code behaviour that cannot be checked here) and are
fixed on the assumption that the documented behaviour holds; all others were CONFIRMED by a run
and their reproductions now give the expected result. Line numbers in the finding text are the
reviewed tree's; the ones in each "Fixed" block are the fixed tree's.

Pattern across the pass: most findings are neighbours of fixes from the fourth review. The
number boundary was tightened for `.,:` but not for `-`, `/` or `%` (1, 4); the calendar alias
table was keyed on the lowercase token without the kind (5); the sibling installer and the
sibling reader did not get the ordering, error listing and OSError handling their twins got
(3, 9, 15); and four doc sentences were left behind by code changes (6, 7, 8, 20).

## High
None.

## Medium

1. (A) keyline/keyline_check.py:25-26 (`L_NUMBER`/`R_NUMBER`) and :213 (`present()`): a bare
   source number counts as present when it only occurs inside a date, a percentage or a slash
   date in the rendering, so a dropped fact PASSes. Reproduced: source `pool max 10
   connections at 14:02`, rendering `restart on 2026-10-25 at 14:02` -> `ok=True missing=[]`
   (`10` found as the month); source `impact: 25 users; due 2026-10-25`, rendering `impact:
   users; due 2026-10-25` -> ok (`25` found as the day); `10` found inside `10%` although the
   extractor takes `10%` as one token (:43); `10` found inside `10/25`. Expected: `missing (1):
   10` / `25`. This breaks the checker's one guarantee (no false PASS) in normal use: incident
   notes hold small numbers and ISO dates on the same line.
   Class: Neighbors; the same class as finding 7 of the fourth review ("a presence check whose
   boundary is looser than the token the extraction took"): that fix blocked `[.,:]digit` but
   not `-digit`, `/digit` or a trailing `%`.
   Test: unit, `check("max 10 at 14:02", "on 2026-10-25 at 14:02").missing == ["10"]`, same
   for the day, for `10%` and `10/25`, and the positive case `check("10 at 14:02 on
   2026-10-25", ...)` still ok.
   Smallest fix: extend the number boundary to `(?<!\d[-./,:])` on the left and
   `(?![-./,:]\d|%)` on the right; re-run the suite, no fixture should move.
   Fixed: keyline/keyline_check.py:27-28, `L_NUMBER` also blocks `\d-`, `\d/` on the left and an
   ISO date's year and month positions (`\d{4}-`, `\d{4}-\d{2}-`); `R_NUMBER` blocks `/\d`, `%`
   and a year's `-MM-DD` on the right. A lone dash stays a boundary on purpose, so a range
   (`pages 5-10`) and a Hebrew prefix (`ב-10`) are still found; the source extractor never
   yields a bare number from a date, a percentage or a slash pair, so only the rendering side
   needed the block. All four reproductions now report the number missing.
   Other hits: `present()` is the only presence check and `L_NUMBER`/`R_NUMBER` its only number
   boundary; the keyline fixtures (35/35) did not move.
   Prevention: tests/test_keyline_check.py
   `test_number_is_not_found_inside_a_date_a_percentage_or_a_slash_pair` (the three date
   positions, `10%`, `10/25`, and the positive cases `ב-14:02`, `5-10`, `ב-10`).

2. (A) keyline/keyline_lint.py:99-102 (`build_cache`), :106-110 (`load_words`), :168-171
   (`lint_text`): a truncated or empty word cache is trusted, so the lint flags ordinary words;
   the cache write is a plain `write_text` with no temp file and rename, and the file's
   existence is the only "built" check (the header's own `47450 words` count is never
   compared). `lint_text` reports a word even when tiktoken itself says it is one token (the
   message literally reads "is 1 tokens"). Reproduced: the cache cut to half loads 23724 words
   without complaint and `lint_text("check that this works with the first build")` reports
   `check`, `that`, `this` ... as "is 1 tokens"; an empty cache file (what a disk-full write
   leaves) loads 0 words and `this must work` gives three findings. Worst case: every
   Write/Edit of a note exits 2 with "fix the file" for words like `this` and `with`, and the
   cache never heals because its existence is the done-marker. Who meets it: a crash, Ctrl-C,
   full disk or two parallel PostToolUse hooks on the first run after a clone (the cache is
   gitignored, so every clone builds it once). CONFIRMED for the truncated/empty cache; the
   concurrent first-run race is PLAUSIBLE (two hooks really overlapping was not timed).
   Class: Halfway (the done-marker is the file's existence), Twice (two first runs build the
   same file in place), Failure is not empty (an empty cache reads as "no word is one token").
   Test: unit, point `WORDS_CACHE` at a file holding the header and ten words: `load_words()`
   must rebuild or raise; `lint_text("this must work", {"the"}, set())` with tiktoken present
   must yield nothing because `token_count` returns 1.
   Smallest fix: in `lint_text`, `if n == 1: continue` (tiktoken is the source of truth when
   available); in `load_words`, parse the `; N words` header and rebuild when the count
   differs; in `build_cache`, write to a temp file beside the target and `os.replace`.
   Fixed: keyline/keyline_lint.py:105-115, `build_cache()` writes to a `mkstemp` file beside the
   cache and `os.replace`s it, removing the temp file when the build fails; :122-125,
   `load_words()` parses the header's `; N words` and rebuilds when it is missing or does not
   match the lines present (an empty file rebuilds too); :184, `lint_text()` skips a word
   tiktoken counts as one token. The second first run now builds into its own temp file and
   the rename is atomic, so two overlapping hooks cannot see each other's half.
   Other hits: config/install.py:264 and config/add_to_repo.py:142 already write temp-and-rename.
   Safe: hooks/context_check.py:172 (the state file is a one-number band marker, read under
   `except (OSError, ValueError)` at :163 and rewritten on the next prompt); scripts/plugin_cost.py:106
   (an output report the user reads, not a done-marker).
   Prevention: tests/test_keyline_lint.py `test_a_truncated_word_cache_is_rebuilt`,
   `test_a_cache_build_that_fails_part_way_leaves_no_cache` (rename fails: no cache, no temp
   file; the next build succeeds) and `test_a_one_token_word_is_never_an_abbreviation`.

3. (B) config/add_to_repo.py:204-215: `_add()` writes settings.json (:205) before copying the
   hook file (:214), and `main()` (:176-179) prints only the error, so a failure between the
   two leaves a committed hook entry pointing at a file that does not exist and says nothing
   about it. Reproduced: `<repo>/.claude/settings.json` = `{"customKey":"keep"}` and
   `<repo>/.claude/hooks` a regular file; `python -I config/add_to_repo.py <repo>` prints
   `Error: [Errno 17] File exists: '.../.claude/hooks'`, rc 1, and settings.json already holds
   the two keys and the hook entry for `.claude/hooks/context_check.py`. Harm is small (the
   repo command ends in `; exit 0`, so nothing blocks), but install.py:336-338 follows the
   opposite order for exactly this reason and :517-525 lists "Done before the error", and
   CHANGELOG.md:17 claims all three installers list what they wrote before an error.
   Class: Halfway / Neighbors (the sibling installer's ordering and error listing are missing
   here).
   Test: unit, tests/test_add_to_repo.py: `.claude/hooks` as a file, run `_add`; assert rc 1
   and settings.json unchanged (or that stderr names "settings.json written").
   Smallest fix: copy the hook first, then write settings.json; or keep the order and print a
   progress list as install.py does. Fix the CHANGELOG sentence either way.
   Fixed: config/add_to_repo.py:223-228, `_add()` copies the hook first, then writes
   settings.json, and appends each file to a progress list; `main()` :182 prints "Done before
   the error:" with that list on an OSError, as install.py and uninstall.py do. The
   reproduction now ends with `Error: ... hooks` and no settings.json. CHANGELOG.md:17 is true
   for all three installers now.
   Other hits: config/install.py (hook before settings, progress list) and config/uninstall.py
   (progress list) already did both; no other script writes two files that refer to each other.
   Prevention: tests/test_add_to_repo.py `test_hooks_folder_in_the_way_leaves_settings_unwritten`
   and `test_error_after_a_write_lists_what_was_written`.

## Low

4. (A) keyline/keyline_check.py:22-23, :208: a time is found inside a longer time or a
   timestamp on the left side. Reproduced: `present('00:30', 'time', '2026-10-25T10:00:30Z')
   == True`; source `cron at 00:30 on 2026-10-25`, rendering `ran at 10:00:30 on 2026-10-25`
   -> ok. Expected `missing (1): 00:30`. (`14:02` in `14:02:30` is the documented, intended
   case; a time found after a `:` is a different instant.) Class: Neighbors (the fourth review
   marked "14:02 in 14:02:30" safe and did not look at the left side). Fix: for `kind ==
   "time"` a left boundary that also blocks `\d:`.
   Fixed: keyline/keyline_check.py:30, `L_TIME = L + r"(?<!\d:)"`, used by `present()` for
   `kind == "time"`; `00:30` is no longer found in `10:00:30`, `14:02` in `14:02:30` still is.
   Other hits: none; the timestamp kind has its own full-match boundaries.
   Prevention: tests/test_keyline_check.py `test_time_is_not_found_at_the_end_of_a_longer_time`.

5. (A) keyline/keyline_check.py:217-218: `CALENDAR.get(tok.lower())` runs for every kind,
   `upper` included, so an all-caps identifier that spells a calendar abbreviation is accepted
   in its Hebrew month or day form. Reproduced: source `arch: DEC alpha at 14:02`, rendering
   `ארכיטקטורה: דצמבר אלפא ב-14:02` -> ok; source `solver: SAT at 14:02`, rendering `פותר:
   בשבת ב-14:02` -> ok. Expected `missing (1): DEC` / `SAT`. Class: Neighbors (an alias table
   keyed on the lowercase token without the kind; the fourth review pinned `MAY`/`מאי` only).
   Fix: apply the aliases to `kind == "proper"` plus the already pinned `MAY`, not to `upper`.
   Fixed: keyline/keyline_check.py:226, the Hebrew calendar forms apply only to `kind ==
   "proper"` and the pinned `MAY`; `DEC`, `SAT` and `MAR` are reported missing against their
   Hebrew month or day.
   Other hits: `CALENDAR` is read only there.
   Prevention: tests/test_keyline_check.py `test_an_upper_case_acronym_is_not_a_hebrew_month_or_day`
   (the three acronyms, and `Dec` and `MAY` still accepted).

6. (A) Docs: "a source with no extractable invariant is INCONCLUSIVE, never PASS"
   (keyline/keyline_check.py:8-9, keyline/README.md:12, README.md:167) is false for a
   hedge-only source: the code at keyline_check.py:245 is `inconclusive = not inv and not
   source_hedges`, which keyline/README.md:61 states correctly. Reproduced: source `the pool
   could be exhausted`, rendering `the pool may be exhausted` -> `PASS (0 invariants
   present ...)`. Class: Words. Fix: make the three sentences match :61, or the code match
   the sentences.
   Fixed: the three sentences (keyline/keyline_check.py:8-9, keyline/README.md:12,
   README.md:167) now read "no extractable invariant and no hedge is INCONCLUSIVE, never PASS",
   which is what :245 does.
   Other hits: a grep for "never PASS" finds no other copy.
   Prevention: none mechanical; the sentence names the condition the code tests.

7. (A) Docs: `pnpm` is in `BUILTIN_ALLOW` (keyline/keyline_lint.py:50-53, said at
   keyline/README.md:90), so keyline/README.md:160 ("passes the lint only with `pnpm` in
   `tests/keyline-allow.txt`") and the docstring at keyline_lint.py:8 and :17 (lists `pnpm`
   among the shapes the lint flags) are false. Reproduced: `notes.keyline.txt` copied to a
   folder with no `keyline-allow.txt` anywhere above it -> `OK`, rc 0. Class: Words. Fix:
   delete or correct README.md:160 ("only with `--no-allow`") and use a word that is not built
   in for the docstring examples.
   Fixed: keyline/README.md:160 says the example passes only because `pnpm` is on the built-in
   list (`--no-allow` fails it); keyline/keyline_lint.py:8 uses `tmpl` as the no-vowel example,
   :13 lists `pnpm` among the built-in names, and the allow-file example is `kubectl`.
   Other hits: README.md mentions `pnpm` nowhere else.
   Prevention: none mechanical.

8. (A) .github/workflows/ci.yml:16-17 says the keyline suite's child scripts run with `-I`;
   keyline/tests/run_tests.py:38 and :155 start them as `[sys.executable, script, ...]` with no
   `-I`, and ci.yml:29 runs the suite itself without `-I` while README.md:137,172,178 and
   run_tests.py:3 say `python -I`. Consequence: on the Windows runner the keyline scripts
   inherit `PYTHONUTF8=1`, so a missing UTF-8 wrapper would not show there (only the
   source-rule scan would catch it). Class: Words. Fix: add `"-I"` to both `subprocess.run`
   calls and run the suite with `-I` in ci.yml.
   Fixed: keyline/tests/run_tests.py:38 and :155 start the scripts with `-I`;
   .github/workflows/ci.yml:33 runs the suite with `python -I`. The suite still passes 35/35.
   Other hits: every `[sys.executable, ...]` list in tests/ already had `-I` except
   tests/test_utf8_output.py, which runs without it on purpose (it sets `PYTHONIOENCODING`
   to reproduce a cp1252 console; `-I` would discard it).
   Prevention: tests/test_source_rules.py `test_tests_start_scripts_with_isolation` (rule 5)
   fails on a `[sys.executable, ...]` list in tests/ or keyline/tests/ without `"-I"` second,
   with test_utf8_output.py as the listed exception.

9. (A) keyline/measure.py:57: `p.read_bytes()` handles only `UnicodeDecodeError`, and
   `files_in` (:30-33) lists every name `os.walk` returns, so a dangling symlink, an unreadable
   file or a FIFO under the folder is a traceback with no table for the readable files.
   Reproduced: folder with `ok.txt` and `broken.txt -> /nonexistent/x.txt` ->
   `FileNotFoundError`, rc 1. Class: Failure is not empty / Neighbors (keyline_check and
   keyline_lint read under an OSError handler; this sibling does not). Fix: `except
   (UnicodeDecodeError, OSError)` with a one-line skip.
   Fixed: keyline/measure.py:61, an `OSError` on a file is one `skip (cannot read: ...)` line on
   stderr and the table is printed for the rest.
   Other hits: keyline_check.py and keyline_lint.py already read under an OSError handler;
   config/install.py:528 and config/uninstall.py:237 read under their `main()`'s OSError handler.
   Prevention: tests/test_measure.py `test_unreadable_file_is_skipped_not_a_traceback`
   (a dangling symlink beside a readable file).

10. (A) keyline/keyline_check.py:36-37: the `path` and `file` alternatives of the INVARIANT
    regex scan `[\w.~-]*` to the end of the run at every position where `L` passes (after
    every `-`), so a long dash-joined run is quadratic. Measured: `invariants("ab-ab-...")`
    2000 pairs 0.32 s, 8000 pairs 4.15 s, 16000 pairs (48 KB) 16.5 s; the hook's timeout is
    30 s, so a note holding such a line is killed on every edit. Class: Scale and time. Fix: a
    cheap lookahead requiring a separator before the path alternative, or a cap on run length.
   Fixed: keyline/keyline_check.py:43, the `path` alternative's lead-in is bounded
   (`[\w.~-]{0,200}`) and so is the `file` alternative, so each start position scans at most
   200 characters. Measured after the fix: 2000 pairs 0.04 s, 8000 pairs 0.14 s, 16000 pairs
   0.28 s (was 0.32 / 4.15 / 16.5 s). A real path component longer than 200 characters is not
   extracted as a path; its words still are.
   Other hits: the other alternatives are bounded by their own character classes.
   Prevention: tests/test_keyline_check.py `test_a_long_dash_joined_run_is_extracted_in_linear_time`
   (8000 pairs in under 2 s).

11. (A) scripts/usage_breakdown.py:144: `glob.glob(os.path.join(folder, "*.jsonl"))` without
    `glob.escape`, so a folder named `proj[1]` with a valid transcript reports `no .jsonl files
    in .../proj[1]`, rc 1. scripts/lint_validate.py:33 and scripts/plugin_cost.py:48 both
    escape. Class: Neighbors. Fix: `glob.escape(folder)`.
   Fixed: scripts/usage_breakdown.py:144 uses `glob.escape(folder)`.
   Other hits: scripts/lint_validate.py:33 and scripts/plugin_cost.py:48,62-63,79 already
   escape. Safe: scripts/unused_tools.py:21 (`Path.rglob` with a literal pattern; the folder
   is not part of the pattern).
   Prevention: tests/test_source_rules.py `test_glob_patterns_escape_the_folder` (rule 4) fails
   on a function that calls `glob.glob`/`iglob` without `glob.escape`; tests/test_usage_breakdown.py
   `test_folder_with_glob_characters_is_found` runs the script on `proj[1]`.

12. (A) keyline/keyline_hook.py:16-17 docstring: "Exit 0 when clean or not applicable. Exit 2
    with the findings on stderr when anything fails" omits exit 1 at :160-165 (read error or
    missing tiktoken, the non-blocking code CHANGELOG.md:25 records). Class: Words. Fix: one
    clause.
   Fixed: keyline/keyline_hook.py docstring names exit 1 (non-blocking, one line on stderr)
   for a read error or missing tiktoken.
   Other hits: keyline/README.md already listed the three codes.
   Prevention: none mechanical.

13. (B) config/install.py:465: `--verify-only` tracebacks with `TypeError: 'NoneType' object
    is not iterable` when `hooks.UserPromptSubmit` is `null` (or any non-list); the install
    path reports the same file as one line, and `main()` catches only `ValueError` and
    `OSError` (:539-545). Reproduced on an installed home with the list set to `null`.
    CHANGELOG.md:21 says verification reports a bad settings.json as one line. Class: Failure
    is not empty. Test: `verify()` on `"UserPromptSubmit": null` and `5` returns the issue.
    Fix: `if not isinstance(hooks, list): issues.append(...); hooks = []`.
   Fixed: config/install.py:495, `verify()` reports `hooks.UserPromptSubmit is not a list:
   <value>` as an issue and continues with an empty list; `--verify-only` on the reproduction
   exits 1 with that line.
   Other hits: :483 (`permissions.deny`) already had the check; `merge_settings()` raises
   `ValueError` for the install path, which `main()` reports.
   Prevention: tests/test_install.py `test_verify_reports_a_user_prompt_submit_that_is_not_a_list`
   (`null`, `5`, `"x"`).

14. (B) config/uninstall.py:201: `Path.with_name` raises `ValueError` on a record backup name
    that holds a separator (`sub/CLAUDE.md.bak-...`), after settings.json was rewritten and
    the hook deleted; the handler at :259-262 assumes every `ValueError` came from the read
    phase and prints `...; nothing written`. Reproduced. Class: Halfway (an error path that
    misreports what was done). Fix: validate `backup_name` in the read phase, or treat a bad
    name like a non-string one (`backup = None`).
   Fixed: config/uninstall.py:152, `_backup_of()` returns None unless the record's backup name
   is a string with no separator, and catches `ValueError` from `with_name`; the undo then
   treats the backup as absent (CLAUDE.md is deleted, as for a non-string name) and the
   message no longer claims "nothing written".
   Other hits: config/install.py:235,238 call `with_name` on names it built itself;
   keyline/keyline_hook.py:95,101 on a stem taken from the note's own name. Safe.
   Prevention: tests/test_uninstall.py `test_backup_name_with_a_separator_in_record_does_not_crash`
   (`../CLAUDE.md.bak`, `sub/CLAUDE.md.bak`).

15. (B) config/verify-tokens.py:118-123: `(OSError, UnicodeDecodeError)` is caught around both
    the file read and `count_tiktoken()`, so a tiktoken encoding download failure
    (`requests.exceptions.ConnectionError` is an `OSError`) prints `Error reading <path>` for
    every file, the table is empty and rc is 0; all-`ERROR` anthropic counts also exit 0.
    Reproduced with the client stubbed. Note: `tests/test_verify_tokens.py::
    test_unreadable_file_is_reported_not_raised` counts "Error reading" == 2 and so fails
    whenever the download fails (how this was found, running the suite as `nobody`). Class:
    Failure is not empty / Outside call. Fix: call `count_tiktoken` outside the read `try`,
    print its error once and return 1; return 1 when `ratios_o200k` is empty after at least
    one file was read.
   Fixed: config/verify-tokens.py:131, the file read and `count_tiktoken()` sit in separate
   `try` blocks; a tiktoken failure (any exception, the download error included) is one
   `Error: tiktoken failed on <file>: ...` line and exit 1; :159, no API count at all is
   `Error: no file was counted by the API` and exit 1.
   Other hits: no other script wraps two unrelated calls in one `except OSError`.
   Prevention: tests/test_verify_tokens.py `test_tiktoken_failure_is_one_error_and_exit_1`
   and `test_no_api_count_at_all_is_exit_1`.

16. (B) config/install.py:240 (`os.replace` in `_write_bytes`): a hard-linked settings.json,
    CLAUDE.md or hook gets a new inode, so a dotfiles copy kept as a hard link stops tracking
    the live file. Reproduced: link count 2 -> 1, the dotfiles copy still `{"model":"opus"}`.
    The pre-PR-#18 in-place write kept the link; README.md:67 names symlinks only. Class:
    Neighbors / Words. Fix: document at README.md:67, or write in place when `st_nlink > 1`
    after a successful temp write.
   Fixed: documented. README.md:67 says a hard-linked `settings.json`, `CLAUDE.md` or hook is
   replaced by a new file and the other link keeps the old content; the `_write_bytes`
   docstring says the same. Writing in place when `st_nlink > 1` was rejected: it would bring
   back the half-written file the temp-and-rename exists to prevent, for a setup (a dotfiles
   hard link to a live settings file) the README now warns about.
   Other hits: the same sentence covers all three installers, which share `_write_bytes`.
   Prevention: none mechanical.

17. (B) config/install.py:60-66 (`quote()`), :474-479 (`verify()`): on Windows the hook
    command is double-quoted and Claude Code runs hooks through bash, where double quotes
    turn `\\` into `\` and expand `$name`; a UNC home (`\\server\share\...`, what
    `Path.resolve()` gives for a mapped drive) or a `$` in a path component runs nothing,
    `|| exit 0` hides it and `verify()` passes because it checks the string, not the shell's
    reading. The bash half was reproduced here. PLAUSIBLE: unchecked step is that Claude Code
    on Windows runs the user-level hook with bash rather than cmd or PowerShell (the repo's
    own `.claude/settings.json` sets `"shell": "bash"` for the repo hook; the user-level entry
    sets nothing). Related to the documented `quote()` limit in the decisions (a double quote
    in a path), but a different character class. Fix: `verify()` warns on `\\`, `$` or a
    backtick in the quoted path on Windows, or single-quote when the command will run in
    bash.
   Fixed: config/install.py:85, `shell_risk(value, windows=None)` returns the characters bash
   changes inside double quotes (`$`, a backtick, `\\`) found in a Windows path, else None;
   `verify()` :515 adds a warning naming them and the hook path when the hook command holds
   one. A warning, not a failure, because the shell Claude Code uses for the user-level hook
   on Windows is the unchecked step. On POSIX the command is single-quoted and nothing is
   checked.
   Other hits: `quote()` is the only quoting; add_to_repo.py's command is a template with a
   relative path and no user text.
   Prevention: tests/test_install.py
   `test_shell_risk_names_what_bash_changes_in_a_double_quoted_windows_path`.

18. (B) config/install.py:49-57, :498 and hooks/context_check.py:35-38 use `Path.home() /
    ".claude"`, ignoring `CLAUDE_CONFIG_DIR`, so for a user who set that variable the
    installer writes and verifies a folder Claude Code does not read, and "verified
    successfully" means nothing was applied. PLAUSIBLE: that Claude Code honours the variable
    for settings.json is documented upstream and not testable here. Class: Neighbors (the
    reader of the files lives elsewhere). Fix: `layout()` uses `CLAUDE_CONFIG_DIR` when set
    and `--home` is not given; README says so.
   Fixed: config/install.py:49 `layout(home, config_dir=None)` and :64 `target(home_arg)`:
   without `--home`, `CLAUDE_CONFIG_DIR` (when set) is where the files go and are verified,
   with `--home` it is ignored; `install()`, `verify()`, `merge_settings()` and
   `hook_command()` take the folder through, config/uninstall.py:281 uses the same `target()`,
   and hooks/context_check.py:35-44 reads its state folder and log from `CLAUDE_CONFIG_DIR`
   too. README.md documents the variable under the install options.
   Other hits: scripts/plugin_cost.py:27-31 uses `Path.home()` for the Claude desktop app's
   folder, which is a different product's path. Safe.
   Prevention: tests/test_install.py `test_claude_config_dir_is_honoured_when_home_is_not_given`
   (install, verify and `--home` override) and tests/test_context_check.py
   `test_state_dir_follows_claude_config_dir`.

19. (B) Uninstall leaves `~/.claude/ballast/state/` and `ballast/context_check.log` (written
    by the hook once it fired), and neither README.md:114 ("By hand: delete ...") nor the
    uninstall.py docstring (:2-7) names them. Reproduced. Class: Endings. Fix: remove them in
    `uninstall()` (the hook rebuilds them), or list them in the README.
   Fixed: config/uninstall.py:208-217 removes `ballast/state/` and `ballast/context_check.log`
   after the hook (the hook rebuilds them), reports "state folder deleted" and "log deleted",
   and lists both in `--dry-run`; README.md's "By hand" list and the uninstall docstring name
   them.
   Other hits: `layout()` now carries both paths (`state`, `log`), so the installer and the
   uninstaller cannot disagree on them.
   Prevention: tests/test_uninstall.py `test_uninstall_removes_the_state_folder_and_the_log`.

20. (B) tests/test_install.py:434-449
    `test_write_bytes_removes_the_temp_file_even_when_the_target_is_read_only` never reaches
    the cleanup it is named for on either CI runner: as a non-root user `os.access(W_OK)` is
    False and `_write_bytes` refuses at :230-231 before `mkstemp` (probe as `nobody`: 0
    `mkstemp` calls, 0 `replace` calls); only as root does the `finally` path run, and
    `match="simulated|read-only"` accepts both outcomes. A regression in the `finally` block
    would pass CI. Class: a test that proves nothing. Fix: split it: a writable target with a
    monkeypatched `os.replace` failure asserts no temp file is left; the refusal case is
    already `test_write_bytes_refuses_a_read_only_target`.
   Fixed: tests/test_install.py, the test is replaced by
   `test_write_bytes_removes_the_temp_file_when_the_rename_fails`: `os.access` is patched to
   True and `os.replace` raises, so the cleanup in `finally` runs for every user, and the
   assertion accepts only the simulated error. The refusal case stays in
   `test_write_bytes_refuses_a_read_only_target`.
   Other hits: no other test uses an `A|B` match that would accept the path it means to skip.
   Prevention: the test itself; it fails before the fix as root and as a plain user.

## Observations, not findings
- A source date `2026-10-14` is reported missing when the rendering writes the same day as
  an ISO timestamp `2026-10-14T14:02:00Z`, and so is a source time only present inside that
  timestamp: FAIL, fail closed. The mirror of the fourth review's "space for the T" fix; a
  clumsier path for JSON renderings, not a wrong PASS.
- measure.py's docstring says hidden folders, `cache/` and `__pycache__/` are skipped; the
  code also skips `node_modules` (an omission, not a contradiction).
- Running the suite as `nobody` in this sandbox fails two tests
  (`test_verify_tokens.py::test_unreadable_file_is_reported_not_raised`,
  `test_plugin_cost.py::test_counts_skills_commands_mcp_and_hooks`) only because tiktoken's
  encoding download goes through a CA bundle that other users cannot read here; CI has
  network. Finding 15 is the product-side half of the first one.

## Checked and found correct
- Every earlier fix in both areas holds, pinned by pytest or re-run: ISO timestamps as one
  invariant and the `[T ]` form; possessive `'s`; `May`/`MAY` rules; `PRs`/`v2`/hashes/
  `sha256`/`__init__`; `10` not in `10:00`, `2` not in `2,500`; mid-line markers and label
  values; Hebrew hedges by class; calendar aliases with Hebrew-letter boundaries; `__Bold__`
  not a dunder; empty source INCONCLUSIVE; non-UTF-8 note, allow file and cache = one line;
  `TiktokenMissing` caught in `token_count`, `main()` and the hook; the hook ignores
  `~/notes/todo.md` outside the project and watches a symlinked `notes/` inside it; `--watch`
  patterns; `--print-config` ASCII JSON.
- `_write_bytes` in both installers: new file `0o666 & ~umask` (0644 observed), existing mode
  kept, read-only target refused as non-root with no temp file, temp file removed on a failed
  rename (as root), symlinked targets written through; dangling-symlink check on all six
  paths; `verify()` interpreter check with `~`/`$HOME` and the Windows `_interpreter`;
  uninstall round trip byte for byte, missing backup, non-list deny notice, OSError mid-undo,
  record after settings.json, `{"uninstalled": true}` marker; install order hook -> CLAUDE.md
  -> settings.json -> record with "Done before the error".
- hooks/context_check.py: `compact_boundary` carries `postTokens` in real transcripts (three
  events checked in this machine's own transcript), band reset, prune and log trim, UTF-8
  stdin wrapper, invalid-integer fallback, empty stderr, rc 0. `|| exit 0` and `; exit 0`
  commands run end to end through `bash -c`.
- Source rules (tests/test_source_rules.py): exits only in `main()`, text reads guarded, UTF-8
  stdout; pyflakes clean. CI runs pytest, the keyline suite and the three JSON parses on both
  OSes. `config/cloud-setup.sh` = `config/CLAUDE.md` + the one cloud line; `.claude/
  settings.json` = `repo-settings.json` with the `hooks/` path as README.md:135 says.
- Doc numbers re-run: the README PASS/FAIL blocks, the measure sample (104/106/385,
  66/68/277, 170/174/662, -37%/-36%), `CLAUDE-snippet.md` at 98 o200k tokens, 47,450 cache
  words, suite counts 35/36, `unused_tools.py` exit codes, `lint_validate.py`/`plugin_cost.py`
  usage and errors. README/CHANGELOG sentences on install merge and backups, write order,
  kept-value warnings, uninstall semantics, threshold variables, and CHANGELOG:16,18,27-29,
  33,38,39,42-55 are true.
- Transcript scripts: isinstance and zero-division guards, `errors="replace"` reads, usage on
  no arguments, message-id dedup and the 5m/1h split in usage_breakdown.py.
- No test writes outside `tmp_path` or the scratch state/log folders (suite under an empty
  `HOME` leaves it empty, `git status` clean).

## Could not check
- The concurrent first-run cache build (finding 2) was not timed with two real hook
  processes; the consequence was reproduced with a truncated file.
- `scripts/tokentest.py` was not run (it calls the Anthropic API; neither the package nor a
  key is present, and runs that reach outside were not allowed).
- Windows was reasoned, not run (findings 8, 17 and 20's Windows halves); CI covers the
  suite there.
- Whether Claude Code accepts the `"shell": "bash"` hook field (no upstream schema offline).

## Outside this task
- none.
