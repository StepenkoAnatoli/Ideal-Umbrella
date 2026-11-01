# Review of main bcc441c (2026-11-01, eighth full pass)

This is a fresh full review of main at `bcc441cd36c6008fe44bbf3b1b8295de5c127841`, after PRs #26, #27, #29 and #30 merged.
It replaces the seventh review (PR #25, on main b46792d), which the user closed unfinished.

**Baseline on this tree** (Python 3.13.18, run as root):

| Check | Result |
|---|---|
| pytest | 1297 passed, 14 skipped |
| keyline suite (`python -I keyline/tests/run_tests.py`) | 35/35 |
| pyflakes on `git ls-files '*.py'` | clean |
| The three JSON files CI checks | parse |
| Working tree | clean |

Reviewer B also ran pytest on other Pythons and as uid 65534:

- Python 3.10 and 3.14: 1297 passed, 14 skipped.
- uid 65534: 1301 passed, 10 skipped. That needs `TIKTOKEN_CACHE_DIR=keyline/cache/tiktoken` and the proxy CA variables unset, because the user cannot read the root-owned CA bundle.

## Method

Two fresh-context reviewers ran in parallel, as in reviews 1-6:

- **A** reviewed `keyline/` and `scripts/` (findings marked A).
- **B** reviewed `config/`, `hooks/`, `tests/` and CI (findings marked B).

Each reviewer also re-checked the findings of the unmerged seventh review that fall in its scope. The source was `git show origin/ccr-review7:research/review-findings-main-b46792d.md`. Its fixes never landed, so each old finding was re-run on current main. A finding that still holds carries its old number, `(old #N)`. The self-check items of that report (S-numbers) were about fix commits that never landed, so one is reported only where its defect exists in current main.

Every medium was reproduced again in the main session with `python -I` before it was accepted. Two lows were reproduced there too: N1 and old #14. Reviewer B reproduced old #6 as uid 65534, because root ignores file modes. Line numbers are bcc441c's. The probe scripts are in the session scratchpad (`review8/a/`, `review8/b/`), not in the repo.

No code was changed. The fixes wait for the user.

**Counts:**

- 0 high.
- 4 medium: old #1 to #4, all in `keyline_check`.
- 42 low:
  - 24 old main findings that still hold (lows 5-28);
  - 9 old self-check items (29-37; 37 duplicates 24);
  - 9 fresh findings (38-46).
- 3 informational notes.
- Of the old report's 35 main findings, 28 still hold (4 medium and 24 low) and 7 no longer hold. The rest of its self-check items are moot.

**Pattern:** the open items are mostly the seventh review's findings, unchanged, because its fixes were never merged:

- Three of the four mediums fail open: a changed path, digest or name passes the check. The fourth fails closed (old #1).
- "Absent is not empty" still covers uninstall: old #14, and the new note on a settings.json the install created.
- "Fix without test" still covers old #9 and #13.
- Fresh findings are few: a change line between the wrong pair of files in `measure.py` (N1), and a case mismatch between twin rendering lookups (N3, a neighbour of a previous fix).

## High

None.

## Medium

### 1. (old #1, A) A date and time written with a space fail against the ISO form

- **Where:** `keyline/keyline_check.py:22-32` and `:227-230`.
- **What goes wrong:** `present()` widens a `datetime` token to accept `[T ]`, but only in one direction. A source written with a space, `2026-10-25 14:30`, is extracted as a separate `date` and `time`:
  - `R` refuses the `T` after the date.
  - `L_TIME` (`(?<!\d:)` plus ASCII `L`) refuses the `T` before the time.
- **Effect:** a renderer that normalises to ISO fails a correct rendering. This fails closed.
- **Repro:**
  ```
  python -I -c "import sys;sys.path.insert(0,'keyline');import keyline_check as k;print(k.check('Deploy at 2026-10-25 14:30.','Deploy at 2026-10-25T14:30Z.'))"
  ```
  Output: `ok=False, missing=['2026-10-25', '14:30']`.
- **Class:** neighbour of a previous fix (third review, finding 1).
- **Fix:** let a `date` be followed by `T\d`, and a `time` be preceded by `\d{4}-\d{2}-\d{2}T`.
- **Test:** the source above against the T form passes; a control with `T15:30Z` gives `missing == ['14:30']`.

### 2. (old #2, A) A rendering that only extends a path, file or name passes

- **Where:** `keyline/keyline_check.py:23` (`R`) and `:230`.
- **What goes wrong:** the right boundary lets `.x`, `-X` and `/` follow the token.
- **Effect:** each pair below gives `ok=True`. It fails open.

  | Source | Rendering |
  |---|---|
  | `notes/a.txt` | `notes/a.txt.bak` |
  | `report.pdf` | `report.pdf.gpg` |
  | `~/.claude` | `~/.claude.bak` |
  | `build.sh` | `build.sh.old` |
  | `API.md` | `API.md.bak` |
  | `Jean-Luc` | `Jean-Luc-Picard` |
  | `notes/a.txt` | `notes/a.txt/` |

- **Repro:**
  ```
  python -I -c "import sys;sys.path.insert(0,'keyline');import keyline_check as k;print(k.check('See notes/a.txt now.','See notes/a.txt.bak now.'), k.check('Ask Jean-Luc today.','Ask Jean-Luc-Picard today.'))"
  ```
  Output: both `ok=True, missing=[]`.
- **Class:** neighbour of a previous fix. Numbers moved to lookup by extraction; path, file and proper nouns stayed on the loose boundary.
- **Fix:** look these kinds up by extraction too, as numbers are. Or give them the right boundary `(?![A-Za-z0-9_]|[.\-/][A-Za-z0-9_])` and refuse a trailing `/`.

### 3. (old #3, A) A hex digest longer than 40 characters is not extracted

- **Where:** `keyline/keyline_check.py:54`, `[0-9a-f]{7,40}`.
- **Effect:** a changed sha256 passes. The README's Honest limits do not say so.
- **Repro:**
  ```
  python -I -c "import sys;sys.path.insert(0,'keyline');import keyline_check as k;h='3b4ca1f2'*8;print(k.invariants('sha256 '+h+' at 14:02'), k.check('sha256 '+h+' at 14:02.','sha256 '+h[:-1]+'3 at 14:02.').ok)"
  ```
  Output: `{'sha256': 'ident', '14:02': 'time'} True`.
- **Class:** neighbour of a previous fix (fourth review added `{7,40}` for git SHA-1).
- **Fix:** use `{7,128}`, or list the lengths 7-40, 56, 64, 96 and 128. Add a sha256 test.

### 4. (old #4, A) A capitalised name with a non-ASCII letter is not extracted

- **Where:** `keyline/keyline_check.py:52` (`proper` is ASCII-only) and `:22-23` (ASCII boundaries).
- **Effect:** a changed name passes. The README does not list this limit.
- **Repro:**
  ```
  python -I -c "import sys;sys.path.insert(0,'keyline');import keyline_check as k;print(k.invariants('Meeting at 10:00 in Zürich with Léa'), k.check('Meeting at 10:00 in Zürich with Léa.','Meeting at 10:00 in Paris with Bob.').ok)"
  ```
  Output: `{'10:00': 'time'} True`.
- **Related:** S36/S42, `Visit ÉCOLE` extracts `COLE`. See the lows.
- **Class:** neighbour of a previous fix (the boundaries were made ASCII-only on purpose; the name class followed by accident).
- **Fix:** build `proper` and `upper` from Unicode letters (`[^\W\d_]`). Keep the Hebrew-prefix tolerance by excluding Hebrew letters from the boundary class. Add tests for Zürich, Léa and ÉCOLE.

## Low: old findings that still hold

### keyline/ and scripts/ (reviewer A)

5. **(old #10)** `keyline/keyline_hook.py:186-191`: the read-error message is wrong in two ways.
   - A non-UTF-8 note prints `cannot read: <path> is not UTF-8`, with a stray colon.
   - A non-UTF-8 rendering or allow file is blamed on the note: `cannot read <note>: <other> is not UTF-8`.
   - No test pins either case.
   - Fix: print the exception alone, and add tests.
6. **(old #11)** `keyline/keyline_check.py:~235`: an upper-case month is not matched to its Hebrew form.
   - `Due OCTOBER 3` against `Due באוקטובר 3` reports `OCTOBER` missing.
   - Cause: the Hebrew calendar forms are tried only for `proper` or `MAY`.
   - Fix: look up `tok.upper()` in `CALENDAR` for any kind.
7. **(old #12)** `keyline/README.md:85` still says "Measured on 400 markdown files in gittoken".
8. **(old #13)** `keyline/measure.py:89-91`: the per-file read handler has no test that needs it.
   - With the handler removed, `tests/test_measure.py` still passes: 17 passed, 2 skipped as root; 19 passed as uid 65534.
   - Fix: add a test that injects the `OSError`, so it does not depend on running as non-root.
9. **(old #21)** `keyline/keyline_check.py:80`, `keyline/keyline_lint.py:41`: a leading number is taken as a list marker.
   - `invariants("2024. Migration done")` is `{}`, so 2024 changed to 2025 passes.
   - Dropping the 503 from `503. Gateway ...` also passes.
   - The lint flags the line as a numbered item.
   - Fix: treat only `\d{1,2}[.)]` as a list marker.
10. **(old #22)** `keyline/keyline_check.py:48`: a URL is extracted without its scheme.
    - `https://example.com/a/b?x=1` gives `//example.com/a/b` and `1`, so `https` changed to `http` passes.
    - Fix: add a URL alternative.
11. **(old #23)** `keyline/keyline_hook.py:164-165`: dotfiles under notes/ are linted.
    - A `.gitignore` holding `# Ignore list` fails with "furniture: header" and exit 2.
    - A `.DS_Store` holding `\xff` gives "cannot read" and exit 1.
    - Fix: skip names that start with a dot.
12. **(old #24)** `keyline/keyline_hook.py:123-130`: a bad `--watch` is not reported.
    - A bare `--watch`, `--watch ""` or a misspelt flag (`--wacth`) silently falls back to the notes rule.
    - Fix: print an error and exit 1.
13. **(old #25)** `keyline/keyline_hook.py:193`: when only the rendering check is inconclusive, the output still says "this machine note breaks the Keyline rules".
    - Fix: choose the header by finding type.
14. **(old #26)** `keyline/keyline_hook.py:36,95-106`: some renderings are never checked.
    - Only `.he.txt` counts as a rendering, so `notes/b.he.md` is linted as a note and never checked.
    - `c.he.txt` is checked only against `c.txt`, not against `c.md`, so a mismatch with `c.md` exits 0.
15. **(old #27)** `keyline/keyline_check.py:101,185`: two Hebrew false fails.
    - `Ticket No. 5` against `מס' 5` fails with negations 1 -> 0.
    - `May: ship v2`, `## May`, `**May**: 3` and `**May** 5` each fail with "hedges lost: possibility".
    - Fix: exclude `No\.\s*\d` from the negations. Treat `May` as the month before `:` or `*`, at the end of a line, and in a header.
16. **(old #28)** `keyline/measure.py:84-88,105`: wrong exit codes.
    - A named file that was skipped still exits 0.
    - An empty folder exits 0 and prints only the header.
    - Fix: exit 1 when a named argument produced no row.
17. **(old #29)** `keyline/measure.py:30`: a symlinked sub-folder is skipped silently.
    - A test pins this on purpose, but the docstring does not say so.
    - It is now only a doc gap.
18. **(old #31)** Malformed transcript fields crash the scripts, and a BOM loses data.
    - `scripts/usage_breakdown.py:79-80,94,100`: any of these raises `AttributeError` or `TypeError`: `usage` that is a list or the string `"x"`, `message.id` that is a list, or `text: null`. A BOM drops the first line.
    - `scripts/unused_tools.py:65`: a BOM gives 0 tool calls.
    - `scripts/usertext_split.py:27-30`: a non-string text raises `TypeError`; a BOM gives "no user text found".
    - `scripts/usertext_top.py:59-62`: `AttributeError` on `strip`.
    - `scripts/toolresult_share.py`: `text: null` raises `TypeError` (`:92`, `:142`); an `id` that is a list is unhashable (`:132`); a `name` of 7 raises `AttributeError` (`:99`); a `role` of null raises `TypeError` (`:121`); a BOM gives "no messages found".
    - `scripts/plugin_cost.py:57`: a `plugin.json` with a BOM shows the folder name instead of the plugin's name.
    - Fix: open with `utf-8-sig`, and add `isinstance` guards.
19. **(old #32)** `scripts/plugin_cost.py:117,114`.
    - An output path in a missing folder gives a traceback.
    - `tiktoken.get_encoding` is unguarded (found by reading the code).
20. **(old #33)** `scripts/plugin_cost.py:49`: `glob("**", recursive=True)` runs without `include_hidden`, so a plugin under a hidden folder is not counted.
21. **(old #34)** `scripts/plugin_cost.py:44-45`: a YAML folded or literal description is read wrong; `desc_of` returns `> Folded text here`.
22. **(old #35)** `keyline/keyline_lint.py:155-158` and the README's Honest limits.
    - An allow-file line `mgmt srvc` counts as one entry, so both words are still flagged.
    - The Honest limits do not mention long digests (medium 3) or non-ASCII names (medium 4).

### config/, hooks/, tests/ (reviewer B)

23. **(old #14)** `config/uninstall.py:420` (`if settings is not None:`, otherwise `left=[]`) and `:149` `_leftover_record`.
    - **What goes wrong:** with settings.json missing at uninstall time, the leftover record becomes `{"uninstalled": true}`. When the file comes back, a second uninstall removes only the hook entry. The user's replaced value is lost: `autoCompactWindow` stays at 250000 instead of the original 123, and the deny entries stay.
    - **Repro:** `review8/b/p14.sh`: install `--force` over `{"autoCompactWindow":123}`, move settings.json away, uninstall, move it back, uninstall again. Reproduced again in the main session.
    - **Class:** absent is not empty.
    - **Fix:** when settings is None and a record exists, carry the settings fields into the leftover record, with the notice "settings.json not found; settings left for a later run".
24. **(old #15)** `config/uninstall.py:90`: a replaced key the user deleted is skipped without a word.
    - README:137 documents that the key stays deleted.
    - But the value the install replaced (123) is never mentioned.
    - This is the same as S108.
    - Fix: add a notice "autoCompactWindow: you deleted it; it was 123 before the install".
25. **(old #6, uninstall side)** `config/uninstall.py:374`: a read-only file stops the uninstall part way.
    - `uninstall()` has no `refuse_read_only` check before its first write. The install side is fixed.
    - **Repro:** as uid 65534 with settings.json at mode 444 (`review8/b/p6.sh`).
    - **Observed:** `the undo stopped part way`. CLAUDE.md is already reverted and a settings backup is already written. A rerun after `chmod 644` finishes.
    - **Class:** halfway state; neighbour of a previous fix.
    - **Fix:** call `install.refuse_read_only` on every file uninstall will change, before the first write.
    - **Related:** S45, a read-only `~/.claude` folder, is the same class. Install's check covers files, not the folder.
26. **(old #9, partial)** `config/add_to_repo.py:247-262`: the temp-file cleanup in `finally` has no test.
    - With the cleanup deleted, all 1297 tests pass. The same mutation in `install.py` fails 2 tests.
    - The read-only pre-check is covered.
    - Fix: port install's "no `*.tmp` left after a failed write" test.
27. **(old #18)** `config/uninstall.py:543-544`: a backup name that `backup_of` rejects deletes CLAUDE.md.
    - Examples: a name with a separator, a non-string, or `../.claude/my-backup.md`. The named file still exists and is never mentioned.
    - Two tests assert the deletion: `tests/test_uninstall.py:654` and `:1122`.
    - Fix: take the "left as is, the backup it names is not usable" branch, and change those two tests.
28. **(old #20)** `config/install.py:14-20`: the docstring lists the steps out of order.
    - It says settings, CLAUDE.md, hook, verify.
    - The code writes the interim record, the hook, CLAUDE.md and its backup, settings and its backup, then the final record.
    - Fix: reorder the docstring, and mention that the record is written first.

### Self-check items whose defect exists in current main (reviewer A)

29. **(S36/S42)** `Visit ÉCOLE` extracts `COLE`, and a rendering with `COLE` passes. This shares the root cause of medium 4.
30. **(S56, fails closed)** A time without seconds fails against the same time with seconds.
    - `14:30Z` against `14:30:00Z` is reported missing.
    - The full datetime `...T14:30Z` against `...T14:30:00Z` is reported missing too.
31. **(S57/S71)** `Answer: yes/no.` against the Hebrew `כן/לא.` reports `yes/no` missing.
    - Before a final period, `yes/no` is taken as a path.
    - Mid-sentence it extracts nothing (`{}`).
32. **(S59)** Camel-case extraction is quadratic: `"aA"*16000+"_"` takes 5.9 s.
33. **(S72)** `_all_caps_line` is quadratic: `"MAY "*40000` (160 KB) takes 25.6 s, close to the hook's 30 s timeout.
34. **(S83)** `hedges("it _could_ fail")` is `{}`. Underscore emphasis hides a hedge, and the README does not list this as a limit.
35. **(S84, nit)** The snake filter at `keyline/keyline_check.py:174` can never match.
36. **(S51)** The Windows junction case was not checkable on Linux. It is listed for completeness.
37. **(S108)** The same as low 24.

## Low: fresh findings

38. **(N1, A)** `keyline/measure.py:99`: the change line is printed between the wrong pair of files.
    - The condition is `len(argv) == 2 and len(rows) == 2`, so the change line is printed whenever two rows exist, whatever produced them.
    - **Repro:** a folder `d/` holding `a.txt` and `b.txt`, and a non-UTF-8 `new.txt`. `python -I keyline/measure.py d/ new.txt` prints `change: o200k 2 -> 6 (+200%)` between a.txt and b.txt, exit 0. Reproduced again in the main session. `measure.py d/ emptydir/` does the same.
    - **Class:** halfway state (a summary of a partial result).
    - **Fix:** print the change line only when both arguments are files and each produced a row.
39. **(N2, A)** `keyline/measure.py:43`: a FIFO argument prints "error: no such file or folder".
    - Fix: say "not a regular file or folder".
40. **(N3, A)** `keyline/keyline_hook.py:95-97` against `:164`: the two rendering lookups disagree on case.
    - `is_rendering` ignores case; the sibling lookup does not.
    - Editing `c.txt` beside `c.HE.TXT` exits 0 without checking the rendering. Editing `c.HE.TXT` itself is checked.
    - **Class:** neighbour of a previous fix.
41. **(N4, A)** `scripts/plugin_cost.py:62,124`: a non-string plugin `name` (`["x"]`) raises "TypeError: unsupported format string passed to list.__format__".
42. **(N5, A)** `scripts/lint_validate.py:66-67`: `load_old` and `load_words` are unguarded, so a missing or non-UTF-8 word file gives a traceback.
43. **(N6, A, cosmetic)** `scripts/ledger.py`: hand-edited `NaN`, `inf` or `null` values print as `nan`, `+inf%` or `None -> 5`. There is no crash, and no other defect was found in the new ledger.
44. **(N7, B)** `config/uninstall.py`: when the install created settings.json, uninstall leaves `{}` plus a backup instead of removing the file.
    - `created` tracks keys and containers, not the file.
    - **Class:** absent is not empty.
45. **(N8, B)** `config/add_to_repo.py:_write_bytes`: writing through a symlinked hook (via `realpath`) has no test. Only the settings symlink is tested.
46. **(N9, B)** Fault injection: failing install's settings write (k=6) and then running uninstall leaves an orphan `settings.json.bak-*` identical to settings. The error output names it, so it is recoverable.

Informational (no action proposed):

- `hooks/context_check.py` `parse_int` accepts Unicode digits and `1_000`, because it uses `int()`. This is harmless.
- `config/verify-tokens.py` can raise `ZeroDivisionError` if the Anthropic count is 0, which is unrealistic.
- `install._RECORD_FIELDS` does not check `uninstalled` or the `claude_md` subfields. Probes showed no crash.

## Old findings that no longer hold

- **#5:** `_check_record_fields` now refuses wrong field types with one line and writes nothing.
- **#7:** a CLAUDE.md deleted after the install now gets a notice naming the backup (README:137).
- **#8:** a symlinked settings file is now tested (`tests/test_add_to_repo.py:237`); changing `realpath` to `abspath` fails it. A symlinked hook is still untested (N8).
- **#16:** the interim record is now written before CLAUDE.md.
- **#17:** `read_record` uses `utf-8-sig`, pinned by `test_a_record_saved_with_a_bom_is_read`.
- **#19:** a legacy record without `sha256` now gets a notice naming the backup.
- **#30:** transcripts are now opened inside the `except OSError` (PRs #26/#27). As uid 65534 an unreadable file gives one line and exit 1.
- **Self-check items:**
  - S44 is fixed: both streams use `backslashreplace` (`keyline_hook.py:140`).
  - The dotted-number timing part of S36 and S59 is now linear.
  - S38, S48, S49, S52, S55, S58, S67 and S69 concern code that was never merged. A spot check of S69 is correct: `Python3.12` against `3.11` fails, missing `['12']`.
  - Reviewer B found no further in-scope defect. B probed S46 (recoverable) and S151 (a clean "cannot read" error).

## Suggested order for fixes (when the user says so)

1. Mediums 1-4 in `keyline_check`, with tests. Medium 2 is the most serious, because a changed path or name passes the check.
2. Old #14, #6, #18 and N7 in uninstall: they lose or keep the user's state silently.
3. The rest of the lows, class by class: transcript guards (18, 41, 42), hook argument and notes handling (11-14, 40), and doc and test gaps (7, 8, 17, 22, 26, 28, 34, 45).

## Fixes (PR #32, on "yes, fix all of them then check your work and merge")

All findings are fixed except 36 (a Windows junction, which cannot be checked on Linux) and the 3 informational notes. Each fix has a test that failed before the fix, with three exceptions:

- 26 and 45 add tests to unchanged code. Each test was checked by a mutation (the code removed, or `realpath` changed to `abspath`).
- 7 and 28 are doc wording, so they have no test.

Commits:

- 74a3343: config/ findings 23-28 and 44-46.
- 51f97b8: keyline/ and scripts/ findings 1-22, 29-35 and 38-43.

After both commits: pytest 1430 passed, 14 skipped (as root), keyline 35/35, pyflakes clean. The config tests also pass as uid 65534: 927 passed, 10 skipped.

The table gives, per finding, the fix (in `keyline_check.py` unless the line names another file), its test, the other hits of the same pattern, and how the fix is kept from coming back.

| # | Fixed | Test | Other hits | Prevention |
|---|---|---|---|---|
| 1 | Datetime matches `[T ]` both ways. Time and datetime share `_clock` (`:310`, `:329`). | `test_a_date_and_time_written_with_a_space_pass_against_the_iso_form` | The time kind shares `_clock`. Fixed. | One time normaliser. |
| 2 | `R_ALONE` (`:54`). `_scan` notes the tokens the source writes on their own; `present` refuses an extension of those. | `test_a_rendering_that_only_extends_a_token_fails`, `test_a_token_glued_to_more_text_in_the_source_passes_against_itself` | None. Lookup by extraction was tried first; it broke the self-pass rule on Hebrew prefixes. | Each kind has an "extension fails" test. |
| 3 | Hash length `{7,128}` (`:90`). | `test_a_sha256_digest_is_one_invariant` | None. | Tests at the SHA-512 limit. |
| 4 | Unicode `UP`/`LO` classes in upper, camel and proper (`:22-43`, `:86-88`). | `test_a_capitalised_name_with_a_non_ascii_letter_is_extracted` | Low 29, same root cause. Fixed. | No letter class built from `A-Z`. |
| 5 | The message uses `e.filename` (`keyline_hook.py:216`). | `test_a_rendering_that_is_not_utf8_is_not_blamed_on_the_note` | The stat path (`:191`) is correct. | The message is built from the error itself. |
| 6 | `CALENDAR_FULL` for any kind (`:139`, `:340`). | `test_an_upper_case_month_or_weekday_accepts_its_hebrew_form` | DEC, SAT and MAR stay acronyms, on purpose. | — |
| 7 | keyline/README.md no longer names gittoken. | — | None. | No private repository is named in a public doc. |
| 8 | Test only. | `test_a_file_that_fails_to_read_is_skipped_not_a_traceback` (fails by mutation without the handler) | None. | Every `except` has a test. |
| 9 | List marker is `\d{1,2}` (`:119`, `keyline_lint.py:42`). | `test_a_leading_number_of_three_or_more_digits_is_not_a_list_marker` | The hedge path shares `LIST_MARKER`. Fixed. | One marker definition. |
| 10 | New `url` kind and `_trim_url` (`:79`, `:210`). | `test_a_url_keeps_its_scheme` | None. | — |
| 11 | Dotfiles skipped (`keyline_hook.py:97-101`). | `test_a_dotfile_under_notes_is_not_a_note` | Hidden files walked by `measure.py`. Fixed. | Every walker skips dotted names. |
| 12 | `parse_watch` rejects unknown or empty arguments with exit 1 (`keyline_hook.py:145-169`). | `test_a_bad_hook_argument_is_reported_not_ignored` | None. | Unknown arguments are refused, never skipped. |
| 13 | The header is chosen from the finding types (`keyline_hook.py:220-223`). | `test_an_inconclusive_rendering_alone_does_not_say_the_note_breaks_the_rules` | None. | — |
| 14 | `HE_SUFFIXES` (`.he.txt`, `.he.md`, `.he.keyline`); renderings are checked against every same-stem note (`keyline_hook.py:41`, `:105-128`). | `test_a_rendering_is_checked_against_every_note_with_its_stem` | Low 40. Fixed. | One helper pair for both directions. |
| 15 | `No. 5` is not a negation (`:148`). May before `:` or `*`, at line end or in a header is the month (`:275-295`). | `test_ticket_no_is_not_a_negation`, `test_may_as_a_label_or_header_is_the_month` | None. | — |
| 16 | Exit 1 with "nothing counted for ARG" (`measure.py:131`). | `test_a_named_argument_that_produced_no_row_exits_1` | None. | — |
| 17 | The docstring and README say a symlinked sub-folder is not followed. | `test_the_docstring_says_a_walked_symlinked_folder_is_not_followed` | None. | — |
| 18 | `utf-8-sig` and `isinstance` guards in usage_breakdown, usertext_split, usertext_top, toolresult_share, unused_tools and plugin_cost. | `test_malformed_fields_and_a_bom_neither_crash_nor_lose_the_first_line` and 3 more | `.mcp.json` and the unused_tools settings file. Fixed. | User JSON is read with `utf-8-sig`, and every field's type is checked. |
| 19 | Output write and `get_encoding` guarded (`plugin_cost.py:136`, `:144`). | `test_an_output_path_in_a_missing_folder_is_one_line_not_a_traceback` | `get_encoding` in keyline_lint and measure. Fixed. | Every tiktoken load and output write is guarded. |
| 20 | `os.walk(followlinks=True)` with a realpath seen-set (`plugin_cost.py:54`). | `test_a_plugin_under_a_hidden_folder_is_counted` | lint_validate skips hidden folders on purpose (documented). | — |
| 21 | Block indicators read (`plugin_cost.py:49`). | `test_a_folded_or_literal_description_is_read_without_its_indicator` | None. | — |
| 22 | An allow line is split into words (`keyline_lint.py:151`). Honest limits updated. | `test_an_allow_file_line_with_several_words_allows_each` | None. | — |
| 23 | settings.json missing: the leftover record keeps the settings fields, with a notice (`uninstall.py:158-161`, `:453`). | `test_settings_missing_at_uninstall_are_kept_for_a_later_run` | A missing CLAUDE.md drops its entry: documented design, and the notice names the backups. | A missing file keeps its part of the record. |
| 24/37 | "you deleted it; it was V before the install" notice (`uninstall.py:99`). | `test_a_replaced_key_the_user_deleted_names_the_value_from_before` | None. | Each dropped record entry is acted on or named. |
| 25 | Uninstall dry-runs itself, then calls `refuse_read_only` on each file it will change (`uninstall.py:468`). | `test_a_read_only_file_stops_uninstall_before_any_write[...]` | S45 (a read-only folder) is not fixed: `os.access` on folders is unreliable. | Every writer checks every file before its first write. |
| 26 | Test only. | `test_write_bytes_removes_the_temp_file_when_the_rename_fails` | install.py is already tested. | A twin helper gets the twin test. |
| 27 | CLAUDE.md is left as is, with "the backup ... is not usable" (`uninstall.py:600`). The 2 tests are changed. | `test_backup_name_with_a_separator_in_record_does_not_crash` | The legacy_backup message now says "not usable". | A value we cannot use is not read as no value. |
| 28 | The docstring is in write order (`install.py:15`). | — | None. | — |
| 29 | Same change as 4. | `test_an_upper_case_word_with_a_non_ascii_letter_is_one_identifier` | — | — |
| 30 | `:00` seconds are optional in `_clock`. | `test_a_time_without_seconds_matches_the_same_time_with_zero_seconds` | None. | — |
| 31 | A trailing period is stripped before the path-shape check (`:225`). | `test_a_yes_no_pair_before_a_period_is_prose_not_a_path` | None. | — |
| 32 | Camel uses an emulated atomic group (`:87`). | `test_extraction_and_hedges_are_linear_on_100_kb` | Path and file are bounded at 200 characters. | The linear-time test. |
| 33 | `_Lines` per-line cache (`:248-272`). | Same test as 32. | None. | Same. |
| 34 | `EN_L`/`EN_R` replace `\b` in HEDGE and NEG_EN (`:147`). | `test_underscore_emphasis_does_not_hide_a_hedge_or_a_negation` | NEG_EN. Fixed. | No `\b` around English words. |
| 35 | Snake uses `ALNUM`; the dead filter is removed (`:89`). | `test_every_snake_token_has_an_inner_underscore_or_is_a_dunder` | — | — |
| 38 | The change line needs two file arguments that each produced a row (`measure.py:123`). | `test_the_change_line_needs_two_files_that_each_produced_a_row` | None. | — |
| 39 | `NotRegular` message (`measure.py:35`). | `test_a_named_pipe_argument_is_not_called_missing` | None. | — |
| 40 | Same change as 14. | `test_a_rendering_named_in_capitals_is_found_from_its_note` | — | — |
| 41 | A non-string name falls back to the folder name (`plugin_cost.py:79`). | `test_a_plugin_name_that_is_not_text_falls_back_to_the_folder` | — | — |
| 42 | `load_old`/`load_words` guarded (`lint_validate.py:66-77`). | `test_a_word_cache_that_cannot_be_read_is_one_line_not_a_traceback` | — | — |
| 43 | Only finite numbers are compared (`ledger.py:108-120`). | `test_a_hand_edited_nan_inf_or_null_is_shown_as_written_without_a_change` | — | — |
| 44 | Install records `settings_created: true`; uninstall deletes such a settings.json when the undo leaves `{}` and the file is not a link. A record without the field keeps `{}`. | `test_a_settings_file_the_install_created_is_deleted`, `test_a_record_that_does_not_say_who_made_settings_json_keeps_it` | CLAUDE.md already has `created`. | A file the install creates is recorded as created. |
| 45 | Tests only. | `test_a_symlinked_hook_stays_a_link_and_its_target_is_updated` (add_to_repo and install) | install.py had the same gap. Fixed. | Each written file has a symlink test. |
| 46 | `install.replace_json` deletes its own backup when the write fails, and drops it from the progress list. | `assert_undone` in `tests/test_failed_writes.py` | The uninstall settings write uses the same helper. | A backup the record does not name is removed when its write fails. |
