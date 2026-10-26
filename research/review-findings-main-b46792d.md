# Review of main b46792d (2026-10-26, seventh full pass)

Review of every source, config, test and doc file after PR #23 merged. Baseline on this tree:
pytest 241 passed, 4 skipped (as root), keyline suite 35/35 under `-I` on Linux, Python 3.13.17,
pyflakes clean, the JSON files parse, working tree clean. This pass had two parts, run by four
fresh-context reviewers in parallel:

1. A check of the six previous reports (V1: `review-findings-2026-10-25.md`, `main-913ab0c`,
   `main-99edcda`, `main-51da01e`; V2: `main-86f16e7`, `main-d608788`): for each of the 110 old
   findings, is the fix in the current code, which test fails if it is reverted, and did it miss
   a sibling. Result: 110 checked, 0 regressed, 0 not landed, 1 landed without a test (measure's
   read handler, finding 13), and 9 siblings the old fixes stopped short of (findings 1, 2, 5 and
   8-13). The verification tables are in the scratchpad (`review7/v1/report.md`,
   `review7/v2/report.md`, not in the repo).
2. A full review of the tree: A on keyline/ and scripts/ (findings marked A), B on config/,
   hooks/, tests/ and CI (marked B). Their reports and probe scripts are in the scratchpad
   (`review7/a/report.md`, `review7/b/report.md`).

All seven medium findings were re-reproduced here with `python -I` before being accepted (the
read-only one as uid 65534, since root ignores file modes); the lows are quoted from the
reviewers' own probe output. Line numbers are the reviewed tree's (main b46792d).

Status: all 35 fixed class-wide in this PR (see the Fixed/Other hits/Prevention lines under each
finding, added as the fixes landed); the self-review of the fix commits found 16 more (5 medium,
11 low), listed at the end, all fixed in the same PR.
Counts: 0 high, 7 medium, 28 low in the main pass; 0 high, 5 medium, 11 low in the self-review.

Pattern across the pass: the same three classes as the sixth review, with one addition. "Neighbour
of a previous fix" again dominates: numbers moved to lookup by extraction but path, file and
proper nouns stayed on the loose right boundary (2); the `hash` alternative got `{7,40}` for git
SHA-1 and a sha256 matches nothing (3); the boundaries were made ASCII-only on purpose but the
proper class stayed ASCII so `Zürich` is not a name (4); the datetime fix accepts a space for a
`T` but not a `T` for a space (1); `_read_json` got `utf-8-sig` and `read_record` did not (17).
"Absent is not empty": a deleted CLAUDE.md, a missing settings.json and a removed key are each
read as "nothing to undo" and the leftover record drops what a later run would need (7, 14, 15);
`.gitignore` has no suffix so it is a note (23); a YAML `>` is the first word of a description
(34). "Halfway state": the read-only refusal and the record-type errors fire after a backup or a
file was written (5, 6, 16). New this pass, "fix without test": five landed fixes that no test
pins (8, 9, 10, 13, and the two tests of 18 that pin the wrong outcome).

## High
None.

## Medium

1. (V1) keyline/keyline_check.py:22-23,32,220-239: a source written as `2026-10-25 14:30` (a
   `date` and a `time`) fails against a rendering that writes the same instant as
   `2026-10-25T14:30`: `R = r"(?![A-Za-z0-9_]|\.\d)"` refuses the `T` after the date and
   `L_TIME = L + r"(?<!\d:)"` refuses the `T` before the time; `present()` widens only the other
   direction (`body = re.escape(tok[:10]) + r"[T ]" + ...` for `kind == "datetime"`).
   Reproduced (re-run here): `check('Deploy at 2026-10-25 14:30.', 'Deploy at 2026-10-25T14:30Z.')`
   -> `ok=False, missing=['2026-10-25', '14:30']`; the T-form source against the space form passes.
   An ISO-normalising renderer fails a correct rendering (fails closed; the third review's finding 1
   fixed one direction).
   Class: neighbour of a previous fix (third review, finding 1).
   Test: `tests/test_keyline_check.py::test_space_separated_timestamp_counts_as_present_in_iso_form`:
   source "Deploy at 2026-10-25 14:30.", rendering "Deploy at 2026-10-25T14:30Z." -> `ok`;
   control "…T15:30Z." -> `missing == ['14:30']`.
   Smallest fix: in `present()`, let a `date` be followed by `T\d` and a `time` be preceded by
   `\d{4}-\d{2}-\d{2}T`.
   Fixed: `present()` looks a `date` up with `(?=T\d)` as an alternative right boundary and a `time`
   with `(?<=\d{4}-\d{2}-\d{2}T)` as an alternative left boundary, so "2026-10-25 14:30" is present
   in "2026-10-25T14:30Z" (the datetime `[T ]` form already covered the other direction),
   keyline/keyline_check.py:present, test
   `test_space_separated_timestamp_counts_as_present_in_iso_form`.
   Other hits: keyline/keyline_check.py:229 (the one-direction `[T ]` form, kept); none elsewhere
   (`grep -rn '\[T \]'`).
   Prevention: the test pins both directions and both controls (hour changed -> `['14:30']`, day
   changed -> `['2026-10-25']`); the comment above `L_TIME` now says why date, time and datetime are
   the only kinds still on a boundary lookup.

2. (V2) keyline/keyline_check.py:23,229-230: a path, file name or proper noun is found inside a
   longer token of the rendering, because only numbers are looked up by extraction while every
   other kind uses the boundary `R`, which lets `.bak`, `.gpg`, `-Picard` or a trailing `/`
   follow: `check('see notes/a.txt at 14:02', 'see notes/a.txt.bak at 14:02')` -> `ok=True`;
   likewise `report.pdf` -> `report.pdf.gpg`, `~/.claude` -> `~/.claude.bak`, `build.sh` ->
   `build.sh.old`, `Jean-Luc` -> `Jean-Luc-Picard`, `notes/a.txt` -> `notes/a.txt/` all pass.
   The extractor itself sees the difference (the rendering's token is the longer one).
   Reproduced (re-run here): the four pairs above, each `(True, [])`.
   Class: neighbour of a previous fix (fifth review moved numbers to lookup by extraction; the
   `time` alternative was tightened; path, file and proper were left on `R`).
   Test: `tests/test_keyline_check.py::test_a_path_or_name_is_not_found_inside_a_longer_one`:
   for each pair `check(src, ren).missing == [tok]` and `check(src, src).ok`.
   Smallest fix: look `path`, `file` and `proper` up by extraction like numbers (`tok in tokens`,
   keeping the Hebrew calendar forms for `proper`).
   Fixed: `present()` looks every kind except `date`, `time` and `datetime` up by extraction (`tok
   in tokens`), with the Hebrew CALENDAR forms kept as a second chance for `proper` (and the `upper`
   names of finding 11); `check()` extracts the rendering with the new `invariants(text,
   names_at_sentence_start=True)` so a name the rendering moves to a sentence start still counts;
   the `path` and `file` alternatives now start at an ASCII word character, `.` or `~` (never a
   Hebrew letter or a dash: `\w` is Unicode there, so `ב-__tests__/` and `בnotes/a.txt` used to be
   one token and would have failed the lookup), keyline/keyline_check.py:present, invariants, check,
   INVARIANT, test `test_a_path_or_name_is_not_found_inside_a_longer_one` (10 pairs) and
   `test_a_hebrew_prefix_or_a_sentence_start_still_counts_for_a_path_or_name` (6 pairs, pins what
   the boundary lookup had).
   Other hits: keyline/keyline_check.py:230-231 (`left, right = ..., R` served every kind, so the
   same hole held for `upper` in `API.md`, `ident` in `sha256.txt`, `snake` in `max_conn.py`,
   `proper` in `Postgres/Prisma`: all moved to extraction, all in the test);
   keyline/keyline_check.py:48-49 (path/file alternatives starting at `\w` or `-`); none outside
   keyline_check.py.
   Prevention: the two tests above plus `test_a_source_passes_against_itself` and the self-check
   fuzzer (`check(line, line)` over 120,000 lines incl. the new shapes, 0 failures) pin that lookup
   by extraction never fails a verbatim rendering; the block comment above `L_TIME` names the rule
   and its two documented edges (`10/` is a path; `Postgres/Prisma` is a path).

3. (A) keyline/keyline_check.py:54: a hex digest longer than 40 characters that starts with a
   digit matches no alternative, so a rendering that changes a sha256/sha512 digest passes:
   `(?P<hash>...[0-9a-f]{7,40})` caps at 40 and `R` then fails at every shorter length; `number`
   fails the same way; a letter-start digest is caught only by accident, as `ident`.
   Reproduced (re-run here): `d='3b4ca1f2'*8; check(f'artifact sha256: {d} at 14:02',
   f'artifact sha256: {d[:-1]}0 at 14:02').ok` -> True; `invariants(...)` holds only `sha256`.
   Class: neighbour of a previous fix (fourth review added `hash` for git SHA-1).
   Test: `tests/test_keyline_check.py::test_a_long_hex_digest_is_one_invariant` over
   `'3b4ca1f2'*8`, `'ab4ca1f2'*8`, `'3b4ca1f2'*16`: kind `hash`, a changed last digit is missing.
   Smallest fix: `[0-9a-f]{7,128}` (sha512 is 128) and the Honest-limits line.
   Fixed: the `hash` alternative is `[0-9a-f]{7,128}` (git SHA-1 to sha512),
   keyline/keyline_check.py:INVARIANT, test `test_a_long_hex_digest_is_one_invariant` (sha256 digit-
   start, sha256 letter-start, sha512: kind `hash`, a changed last digit missing, self passes).
   Other hits: keyline/keyline_check.py:54 only (`grep -rn '7,40'` finds no other; README:186-188
   lists what is and is not extracted and gets the new text below).
   Prevention: the test pins all three lengths; the comment above `INVARIANT` now states the 7-128
   range and the README Honest-limits line names it.

4. (A) keyline/keyline_check.py:50: a capitalised name with a non-ASCII letter is not extracted
   (or is cut at it): `(?P<proper>[A-Z][a-z][A-Za-z0-9]*...)` with the ASCII `R` yields nothing
   for `Zürich`, `Léa`, `Øyvind` and `Caf` for `Café`, so a rendering that swaps the name passes.
   Reproduced (re-run here): `check('Meeting at 10:00 in Zürich with Léa', 'Meeting at 10:00 in
   Paris with Bob').ok` -> True, `invariants(...)` -> `{'10:00': 'time'}`.
   Class: neighbour of a previous fix (the boundaries were made ASCII-only so a Hebrew prefix
   glued to a token counts; the proper class stayed ASCII). Realistic in the repo's own use.
   Test: `tests/test_keyline_check.py::test_a_name_with_a_diacritic_is_a_proper_noun` over
   `Zürich`, `Léa`, `Øyvind`, `São`: extracted as `proper`, a swap is missing, self passes.
   Smallest fix: Latin letters with diacritics in the proper alternative and in the first branch
   of `R`; re-run the self-check fuzzer.
   Fixed: `LATIN` (Latin-1 Supplement, Latin Extended-A/B and Latin Extended Additional letters,
   built with `str.isalpha()`), with `LATIN_UPPER`/`LATIN_LOWER`, is in the three character classes
   of the `proper` alternative and in the first branch of `R` (so "Caf" is not a token before "é");
   `L` and the other boundaries stay ASCII, keyline/keyline_check.py:LATIN, R, INVARIANT, test
   `test_a_name_with_a_diacritic_is_a_proper_noun` over Zürich, Léa, Øyvind, São, Café, Łukasz.
   Other hits: keyline/keyline_check.py:23 (`R`) and :52 (`proper`); the `camel`, `upper`, `snake`,
   `ident` classes stay ASCII on purpose (identifiers), and `PROPER_STOP` compares with
   `tok.lower()`, which is Unicode-aware already.
   Prevention: the test pins extraction, the swap and the self pass for six names; the fuzzer gained
   those names plus `ZürichAirport` and `Caf` (0 failures, seeds 1-3).

5. (V1) config/install.py:357-360, config/uninstall.py:66-81,90: an install record that is a JSON
   object but holds a wrong-typed field is neither refused nor treated as absent:
   `tracked = list(old.get("added_keys", [])) + list(old.get("replaced", {}))`,
   `keys = list(dict.fromkeys([*added, *replaced]))` and `if key in installed` raise TypeError
   (a traceback, not the one-line "fix it or delete it first" of `read_record`), and a string
   `added_keys` is exploded into its letters. In install the TypeError fires inside
   `_merge_record` after the hook and CLAUDE.md were written: the user's CLAUDE.md is replaced,
   its backup unrecorded, and a later uninstall says the file "was not written by this install".
   Reproduced (re-run here): record `{"added_keys": 5}` beside a user CLAUDE.md,
   `install.py --home ...` -> `TypeError: 'int' object is not iterable`; afterwards CLAUDE.md
   holds the template, `CLAUDE.md.bak-*` the user's text, the hook exists, the record is
   unchanged; `uninstall.py` then prints "matches the template but was not written by this
   install; left as is".
   Class: neighbour of a previous fix (third review validated the record's JSON and outer type,
   its finding 10 one inner field); halfway state.
   Test: `tests/test_install.py::test_record_with_a_wrong_typed_field_stops_the_install_before_any_write`
   over `{"added_keys": 5}`, `{"installed": null}`, `{"replaced": "x"}`, `{"created": "hooks"}`:
   exit 1, one line naming the record and "nothing written", CLAUDE.md unchanged, no hook, no
   backup; `tests/test_uninstall.py::test_record_with_a_wrong_typed_field_is_reported_not_raised`.
   Smallest fix: check the field types once in `read_record()` (both scripts read through it) and
   raise the existing ValueError; that runs in the read phase.
   Fixed: `read_record()` in config/install.py now calls `_check_record()` which refuses (ValueError
   "<record>: <field> must be <type>, not <value>; fix it or delete it first")
   `added_keys`/`deny_added`/`created` that are not lists of str, `replaced`/`installed`/`claude_md`
   that are not dicts, `uninstalled` that is not a bool and `claude_md.sha256` that is not a str;
   the check runs in the read phase, so nothing is written. Tests:
   `test_record_with_a_wrong_typed_field_stops_the_install_before_any_write` (tests/test_install.py,
   parametrized over four fields), `test_record_with_a_wrong_typed_field_is_reported_not_raised`
   (tests/test_uninstall.py; uninstall reads the record through the same function, so it reports one
   line and exits 1).
   Other hits: config/uninstall.py uses `read_record()` (same check applies); config/install.py:573
   `key not in settings` and config/add_to_repo.py:71 are the "add it" branch, correct;
   `claude_md.backup` is left unchecked on purpose — finding 18 handles it at use.
   Prevention: validate every field of a user-editable file where it is read, not where it is used,
   and list the fields in one place.

6. (B) config/install.py:286, reached only after :436 `_backup(paths["claude_md"])` or :458
   `_backup(paths["settings"])`; config/uninstall.py:200-205 the same order: a read-only
   CLAUDE.md or settings.json is refused by `_write_bytes` after its backup (and the hook, and
   for settings also CLAUDE.md and the interim record) were written, so every attempt leaves one
   more orphan `*.bak-*` and README:66 ("an install that fails while reading or checking ...
   changes nothing") does not hold for a condition that is checkable while reading.
   Reproduced (re-run here as uid 65534): `chmod 444 ~/.claude/CLAUDE.md`, install twice ->
   "Done before the error: hook written, CLAUDE.md backup: ...", then "CLAUDE.md backup: ...-1";
   the folder holds both backups and the hook. Reviewer V2 found the settings.json twin in both
   install and uninstall independently (merged here).
   Class: check after the side effect (neighbour of the read-only refusal, fourth review 21).
   Test: `tests/test_install.py::test_a_read_only_target_is_refused_before_any_write` (skip as
   root) for CLAUDE.md and settings.json: install twice, no `*.bak-*`, no hook;
   `tests/test_uninstall.py::test_a_read_only_settings_file_is_refused_before_it_is_backed_up`.
   Smallest fix: refuse an unwritable target in the read-and-check phase of install (ValueError,
   "nothing written") and before the backup in uninstall.
   Fixed: `_refuse_read_only(path)` (config/install.py, before `_backup`; `os.access(path,
   os.W_OK)`, so the Windows read-only attribute counts) is called in `install()` for hook,
   CLAUDE.md, settings.json and the record — each only if it would be written — after
   `merge_settings` and before any write; config/uninstall.py calls it for settings.json (if
   changes), CLAUDE.md (if it would be restored) and the record before the settings backup. Tests:
   `test_a_read_only_target_is_refused_before_any_write` (tests/test_install.py, CLAUDE.md and
   settings.json, asserts no `*.bak-*` and no ballast folder, skip as root),
   `test_a_read_only_settings_file_is_refused_before_it_is_backed_up` (tests/test_uninstall.py, skip
   as root). Hand probe as uid 65534 under /var/tmp: "… is read-only; make it writable first;
   nothing written", no orphan files.
   Other hits: config/install.py:243,249,298,468; config/uninstall.py:236,238,240;
   config/add_to_repo.py:148,152,162,244,246 (finding 9). `_write_bytes` keeps its own refusal as
   the last line of defence.
   Prevention: every precondition a write can fail on (type, encoding, link target, permission) is
   checked in the read phase for all files at once, before the first write.

7. (B) config/uninstall.py:238 `if current_md is not None:` guards the whole CLAUDE.md block, so
   when the user deleted CLAUDE.md after the install, the backup of their pre-install file is
   neither restored nor mentioned, and `_leftover_record` (`claude_md_left` stays False) drops
   `claude_md` from the record, so no later run can restore it either; README:113 promises
   "restore the CLAUDE.md backup".
   Reproduced (re-run here): seed CLAUDE.md "mine", install, delete CLAUDE.md, uninstall ->
   no CLAUDE.md line, record `{"uninstalled": true}`, `CLAUDE.md.bak-*` left on disk.
   Class: absent is not empty.
   Test: `tests/test_uninstall.py::test_deleted_claude_md_still_restores_the_backup`: CLAUDE.md
   reads "mine" again and the backup is gone.
   Smallest fix: when `current_md is None` and the record names an existing backup, restore it
   (the install's own write is already gone; the backup is what remains to undo).
   Fixed: in config/uninstall.py the CLAUDE.md decision is computed before any write: `restore =
   backup exists and (ours or current_md is None)`, so a missing CLAUDE.md with an existing backup
   is restored (the earlier code fell through on `current_md is None`). Test:
   `test_deleted_claude_md_still_restores_the_backup` (tests/test_uninstall.py).
   Other hits: config/install.py:480,489 `current_md is None` are the absent-at-install case
   (correct); the matching missing-backup case is
   `test_deleted_claude_md_with_a_missing_backup_keeps_the_record` (keeps the record entry, notice
   "CLAUDE.md is already gone; the backup … is missing").
   Prevention: when a file may be absent, write the truth table (present/absent x ours/not ours x
   backup present/absent) and test each row that changes the outcome.

## Low

8. (V1) config/add_to_repo.py:152: `os.path.realpath(path)` writes through a symlinked
   `.claude/settings.json` or hook, but no test in tests/test_add_to_repo.py fails if it is
   removed (install.py's twin is pinned by `test_symlinked_settings_stay_symlinks`). Behaviour
   confirmed right by probe. Class: fix without test (sibling of first review 5).
   Test: `test_symlinked_settings_and_hook_stay_symlinks`. Smallest fix: add the test.
   Fixed: no code change needed; `test_symlinked_settings_and_hook_stay_symlinks`
   (tests/test_add_to_repo.py) passed against the current code and now guards it;
   `test_write_bytes_removes_the_temp_file_when_the_rename_fails` covers the `finally` branch of
   `_write_bytes` (temp removed, target untouched) that had no test.
   Other hits: none — `_write_bytes` is the only writer in config/add_to_repo.py; the
   install/uninstall writers share the same shape and already had symlink tests.
   Prevention: a fix lands with the test that would have failed before it, named after the
   behaviour.

9. (V1) config/add_to_repo.py:154-170: the read-only refusal and the temp-file cleanup in
   `finally` are untested there; install.py's copy has two tests. Class: fix without test
   (sibling of fourth review 21). Test: `test_write_bytes_removes_the_temp_file_when_the_rename_fails`
   and `test_write_bytes_refuses_a_read_only_target` in tests/test_add_to_repo.py.
   Smallest fix: add the tests, or reuse `install._write_bytes`.
   Fixed: `_refuse_read_only(path)` in config/add_to_repo.py (os.path version, same message) is
   called in `_add` for the hook target (if it changed) and settings.json (if there are changes)
   before the hook is written. Tests:
   `test_a_read_only_settings_file_is_refused_before_the_hook_is_written` (subprocess `run(repo)`,
   asserts no hook file, skip as root), `test_write_bytes_refuses_a_read_only_target` (skip as
   root). Hand probe as uid 65534: one line on stderr, no `.claude/hooks/` created.
   Other hits: config/add_to_repo.py:244,246 (new); same class as finding 6 in install/uninstall.
   Prevention: same as 6 — permission checks belong in the read phase, per file, before the first
   write.

10. (V1) keyline/keyline_hook.py:183-185: a note that is not UTF-8 ends the hook with one line and
    exit 1, but no test drives the hook with such a note (third review 9 added tests for check and
    lint only); and `where` is empty for the note itself, so the line reads "cannot read: <path>
    is not UTF-8" with a stray colon. Class: fix without test (sibling of third review 9).
    Test: `tests/test_keyline_hook.py::test_a_non_utf8_note_is_one_line_and_exit_1`.
    Smallest fix: add the test; build the message without the colon when `where` is empty.
   Fixed: `keyline/keyline_hook.py:main` read handler builds the line from the error (`cannot read
   <e.filename>: <strerror>` for a system error, the message itself for the no-errno not-UTF-8 error
   so a not-UTF-8 rendering is no longer blamed on the note, else `cannot read <note>: <e>`), exit
   1, one line, stray colon gone, test `test_a_non_utf8_note_is_one_line_and_exit_1`.
   Other hits: none.
   Prevention: the test asserts exit 1, exactly one stderr line, the note's name, "not UTF-8" and no
   `read:` in it.

11. (V1) keyline/keyline_check.py:235: the Hebrew calendar form is accepted only `if kind ==
    "proper" or tok == "MAY"`, so `Due OCTOBER 3` (extracted as `upper`) against `Due באוקטובר 3`
    is reported as missing `OCTOBER`; the comment justifies the limit with `DEC`/`SAT`, which the
    full names are not. Fails closed. Reproduced (re-run here): `missing=['OCTOBER']`.
    Class: neighbour of a previous fix (fourth review 9/17).
    Test: `test_an_all_caps_month_or_weekday_accepts_its_hebrew_form`.
    Smallest fix: accept the form for an `upper` token longer than three letters that is in
    CALENDAR.
   Fixed: `present()` accepts the Hebrew CALENDAR form for an `upper` token that is `MAY` or longer
   than three letters (`OCTOBER`, `MONDAY`, `SATURDAY`); `DEC`, `SAT`, `MAR` stay acronyms,
   keyline/keyline_check.py:present, test
   `test_an_all_caps_month_or_weekday_accepts_its_hebrew_form`.
   Other hits: keyline/keyline_check.py:236 only; `hedges()` already treats `MAY` by line shape,
   unchanged.
   Prevention: the test pins the three full names, the dropped-name control and the `DEC` control;
   `test_an_upper_case_acronym_is_not_a_hebrew_month_or_day` still guards the short forms.

12. (V1) keyline/README.md:85: "Measured on 400 markdown files in gittoken (2026-10-18)" still
    names the one-machine corpus the second and third reviews removed everywhere else.
    Class: neighbour of a previous fix (docs). Smallest fix: "a 400-file markdown corpus".
   Fixed: documentation only, keyline/README.md:85 (exact line under Docs); no code, no test.
   Other hits: `grep -rn gittoken` outside research/ and HISTORY.md (history of record, left): none.
   Prevention: the second review's rule that no doc names one machine's corpus; the line now says "a
   400-file markdown corpus".

13. (V2) keyline/measure.py:77-79: the per-file read handler is landed but no test fails when it is
    removed: `test_unreadable_file_is_skipped_not_a_traceback` uses a dangling symlink, which the
    later `is_file()` check (sixth review 2) now skips before the read. Confirmed by deleting the
    handler: the test still passes. Class: fix without test.
    Test: `tests/test_measure.py::test_a_file_that_cannot_be_read_is_skipped_not_a_traceback`
    (mode 000, skip as root). Smallest fix: add the test.
   Fixed: nothing in `keyline/measure.py` (the `except OSError` around `read_bytes()` was right);
   the missing test `test_a_file_that_cannot_be_read_is_skipped_not_a_traceback` added (mode 000,
   skipped as root and on Windows; run as uid 65534: 8 passed, 0 skipped).
   Other hits: none.
   Prevention: deleting that handler now fails the test on the Ubuntu runner.

14. (B) config/uninstall.py:198-199: with settings.json absent at uninstall time, `undo_settings`
    never runs, `left` stays empty, and `_leftover_record` writes the bare marker, discarding
    `replaced` (the `--force` original) and `deny_added`; after the file is back, a later run only
    removes the hook entry. Reproduced: install `--force` over `{"autoCompactWindow": 123}`, move
    settings.json away, uninstall, move it back, uninstall -> 250000 stays.
    Class: absent is not empty. Test: `test_missing_settings_keeps_the_record_for_a_later_run`.
    Smallest fix: when settings is None, keep every recorded key in the leftover record and say so.
   Fixed: config/uninstall.py `uninstall()` when settings.json is absent and a record exists: the
   record keeps `added_keys`, `replaced` and `deny_added` (nothing is marked done), and prints
   "<settings> is missing; the values recorded for it are kept in the record for a later run". Test:
   `test_missing_settings_keeps_the_record_for_a_later_run` (tests/test_uninstall.py).
   Other hits: config/uninstall.py CLAUDE.md missing-backup branch applies the same rule (keep the
   record entry); config/install.py has no comparable drop.
   Prevention: "absent is not empty": an absent file is its own branch with a notice, never the `{}`
   default.

15. (B) config/uninstall.py:88: a key the user removed after a `--force` install is skipped in
    silence and its `replaced` value dropped from the record; README:113 says values you changed
    are "left alone and reported". Reproduced: no line about `autoCompactWindow` or 123.
    Class: absent is not empty. Test: `test_removed_replaced_key_is_reported`.
    Smallest fix: a notice naming the key and the earlier value.
   Fixed: config/uninstall.py `undo_settings`: `key not in settings` with `key in replaced` appends
   "<key> was removed after the install; its earlier value <value> is not put back" instead of
   `continue` alone. Test: `test_removed_replaced_key_is_reported` (tests/test_uninstall.py).
   Other hits: config/install.py:573 and config/add_to_repo.py:71 are "add it" branches (correct);
   deny-list entries already report what they skip.
   Prevention: every `continue` that drops recorded state needs a notice or a comment saying why
   silence is right.

16. (B) config/install.py:448-455: `_write_bytes(paths["claude_md"], ...)` runs before the interim
    record, so an interruption between the two leaves a template CLAUDE.md with no record of its
    backup; the next install records nothing and the uninstall says "not written by this install".
    Reproduced in-process (`_write_json` raising once). Class: halfway state (neighbour of the
    sixth review's interim-record fix).
    Test: `test_interrupt_before_the_interim_record_is_recovered_by_the_next_install`.
    Smallest fix: write the interim record before the CLAUDE.md write.
   Fixed: config/install.py `install()` writes the interim record (`_merge_record(old_record,
   {"claude_md": record["claude_md"]})`) before CLAUDE.md, so an interrupt leaves either the old
   state or a record that names today's backup and hash. Test:
   `test_interrupt_before_the_interim_record_is_recovered_by_the_next_install`
   (tests/test_install.py; `_write_json` raises once, asserts the first write is the record,
   CLAUDE.md untouched, next install + uninstall restores).
   Other hits: the settings.json write already follows its own backup+record ordering; add_to_repo
   keeps hook-before-settings (documented reason at config/add_to_repo.py:219).
   Prevention: write the thing that lets you recover before the thing you may need to recover from,
   and test the interrupt at each boundary.

17. (B) config/install.py:338 `read_record` opens with `encoding="utf-8"` while `_read_json` uses
    `utf-8-sig`: a record saved with a BOM (a hand repair in a Windows editor, which the error
    message invites) is refused as "not valid JSON" by both scripts. Reproduced.
    Class: neighbour of a previous fix. Test: `test_record_with_a_bom_is_read`.
    Smallest fix: `utf-8-sig`.
   Fixed: `read_record()` in config/install.py opens with `encoding="utf-8-sig"` and maps
   `UnicodeDecodeError` to "… is not UTF-8 (…); fix it or delete it first". Test:
   `test_record_with_a_bom_is_read` (tests/test_install.py).
   Other hits: no other `encoding="utf-8"` JSON reads in config/ (grep); config/add_to_repo.py
   `_read_json` already used utf-8-sig; hooks/context_check.py:166 reads its own state file (not
   user-edited, out of scope).
   Prevention: every JSON file a user may open in an editor is read with utf-8-sig.

18. (B) config/uninstall.py:161-170,263: `_backup_of` returns None for a backup name that is not a
    plain file name, and the `entry is not None` branch then deletes CLAUDE.md as if no backup had
    been made; the user's real backup stays on disk unmentioned. The two tests that cover this
    (`test_non_string_backup_name_in_record_does_not_crash`,
    `test_backup_name_with_a_separator_in_record_does_not_crash`) assert "CLAUDE.md deleted",
    pinning the wrong outcome. Reproduced. Class: test pins the wrong behaviour.
    Test: change both to assert the file stays and a notice names the bad name.
    Smallest fix: take the "backup is missing" branch when the record names a backup that
    `_backup_of` rejects.
   Fixed: config/uninstall.py: when `_backup_of()` returns None for a named backup (non-string or
   contains a separator) CLAUDE.md is left as is and the record entry kept, with "the record names a
   backup that is not a plain file name (<name>); fix the record first"; the two existing tests
   `test_non_string_backup_name_in_record_does_not_crash` and
   `test_backup_name_with_a_separator_in_record_does_not_crash` (tests/test_uninstall.py) now assert
   the file is unchanged, the notice names the bad value and the record entry stays.
   Other hits: none — `_backup_of` is the only consumer of `claude_md.backup`; finding 5
   deliberately leaves the type check to this branch so the message names the file.
   Prevention: a "does not crash" test is not a test; assert the outcome the user sees.

19. (B) config/install.py:436-446: with a record from before `sha256` existed, a CLAUDE.md the user
    edited plus a template change takes the `"sha256" not in old_md` branch: the edits are backed
    up but the record keeps the first backup and the uninstall never mentions the second;
    README:113 does not hold for such records. Reproduced. Class: legacy record (one day of
    records). Test: `test_legacy_record_without_sha256_reports_the_second_backup`.
    Smallest fix: the "edits after the last install" notice, saying which backup the uninstall
    restores and naming the new one.
   Fixed: config/install.py legacy branch (`"sha256" not in old_md`, backup made) prints "CLAUDE.md
   differed from the last install (the record has no content hash, so edits cannot be told apart);
   today's file is in <backup>; uninstall will restore <earlier> | uninstall will delete CLAUDE.md".
   Test: `test_legacy_record_without_sha256_reports_the_second_backup` (tests/test_install.py).
   Other hits: the hashed branch already reports; config/uninstall.py's template-compare fallback
   for records without sha256 is the matching read side (unchanged, notice already there).
   Prevention: when behaviour depends on a field older records lack, the fallback says so in output.

20. (B) config/install.py:14-16 docstring lists the steps in the reverse of the real write order
    (hook, CLAUDE.md, interim record, settings.json, record), which README:66 describes correctly.
    Class: doc drift. Smallest fix: reorder.
   Fixed: config/install.py module docstring now lists the write order: hook → CLAUDE.md change and
   its backup recorded in install-record.json first → CLAUDE.md → settings.json merge → full record
   → verify, matching the code after finding 16.
   Other hits: README.md line 66 says the same (text below); config/uninstall.py docstring already
   matches its code.
   Prevention: when the write order changes, the docstring and README line are part of the diff.

21. (A) keyline/keyline_check.py:80: `LIST_MARKER` strips `2024. ` and `503. `, so a line that
    starts with a year or status code and a full stop loses that number: `invariants("2024.
    Migration done")` -> `{}`. Reproduced (re-run here). Class: neighbour of the fifth review's
    "a number alone on a line is not a marker". Test: `test_a_year_that_starts_a_sentence_is_a_number`.
    Smallest fix: a list marker has at most three digits.
   Fixed: `LIST_MARKER` takes at most three digits (`\d{1,3}[.)]`), so "2024. Migration done" keeps
   the year; the lint's "numbered item" furniture rule is the sibling and took the same bound,
   keyline/keyline_check.py:LIST_MARKER and keyline/keyline_lint.py:FURNITURE, tests
   `test_a_year_that_starts_a_sentence_is_a_number` and
   `test_a_year_with_a_full_stop_is_not_a_numbered_item`.
   Other hits: keyline/keyline_lint.py:41 (fixed); keyline/keyline_check.py:197 (`hedges()` reuses
   `LIST_MARKER`, covered). Honest edge kept as the report prescribed: a three-digit status code
   "503. " at a line start is still a marker.
   Prevention: both tests pin 1-, 2- and 3-digit markers as markers and the four-digit year as a
   number.

22. (A) keyline/keyline_check.py:48: a URL is extracted without its scheme (`//example.com/a/b`),
    so `https` -> `http` passes. Reproduced. Class: extraction edge case.
    Test: `test_a_url_keeps_its_scheme`. Smallest fix: a `url` alternative before `path`.
   Fixed: a `url` alternative (`scheme://` up to whitespace or a closing quote, bracket, backtick or
   separator) before `path`, so `https://example.com/a/b?x=1` is one token and `https` -> `http` is
   missing; looked up by extraction (finding 2), so `(https://...),` in a Hebrew rendering still
   passes, keyline/keyline_check.py:INVARIANT, test `test_a_url_keeps_its_scheme`.
   Other hits: keyline/keyline_check.py:48 only.
   Prevention: the test pins the kind, the scheme change, two Hebrew renderings with punctuation
   around the URL and the self pass; the fuzzer gained five URL shapes.

23. (A) keyline/keyline_hook.py:159: a dotfile written under notes/ is linted as an extension-less
    note (`Path(".gitignore").suffix == ""`): `notes/.gitignore` -> "furniture: header", exit 2;
    `notes/.DS_Store` -> exit 1. Reproduced. Class: absent is not empty.
    Test: `test_a_dotfile_under_notes_is_not_a_note`. Smallest fix: skip names starting with ".".
   Fixed: `keyline/keyline_hook.py:main` returns 0 for a name starting with `.` before the suffix
   rule, test `test_a_dotfile_under_notes_is_not_a_note`.
   Other hits: `keyline/measure.py:38` already skips hidden folders;
   `keyline_lint.py`/`keyline_check.py` take explicit paths only.
   Prevention: the test asserts exit 0 and empty stderr for `.gitignore`, `.DS_Store` (binary) and
   `.env.he.txt`.

24. (A) keyline/keyline_hook.py:122-130: `--watch` without a value, `--watch ""` or a misspelt flag
    is silently ignored and the hook falls back to the notes/plans rule. Reproduced. Class:
    neighbour (keyline_lint's `main()` refuses `--allow` without a value).
    Test: `test_a_watch_flag_without_a_pattern_is_an_error` (exit 1, one line).
    Smallest fix: an error for a missing value and for any other `-` argument.
   Fixed: `keyline/keyline_hook.py:parse_watch` raises `ValueError` for `--watch` with no or an
   empty pattern and for any other argument; `main()` prints `keyline hook: <reason>; fix the hook
   command in settings.json` and returns 1 before stdin is read, test
   `test_a_watch_flag_without_a_pattern_is_an_error`.
   Other hits: `keyline/keyline_lint.py:243-249` (`--allow` with no value prints usage, exit 2;
   verified, not my file); `keyline/keyline_check.py:355` and `keyline/measure.py:52` refuse a
   leading `-`; `scripts/unused_tools.py` uses argparse.
   Prevention: the test is parametrised over `--watch`, `--watch ""`, `--wacth x`, `--watch x -v`;
   `test_watch_patterns_do_not_lift_the_suffix_rule` keeps the valid shape working.

25. (A) keyline/keyline_hook.py:187: when only the rendering check fails, the header still says
    "this machine note breaks the Keyline rules; fix the file", pointing Claude at the wrong file.
    Reproduced. Class: halfway state of an earlier message change.
    Test: `test_a_failed_rendering_names_the_rendering`. Smallest fix: a second header when
    every problem is a FAIL/INCONCLUSIVE line.
   Fixed: `keyline/keyline_hook.py:main` keeps lint findings and check findings in two lists and
   prints `NOTE_HEADER` only when the lint found something, else `RENDERING_HEADER` ("this rendering
   no longer matches its machine note; fix the rendering."), test
   `test_a_failed_rendering_names_the_rendering`.
   Other hits: none.
   Prevention: the test asserts the first stderr line names the rendering and lacks "breaks the
   Keyline rules" when only the check fails.

26. (A) keyline/keyline_hook.py:35,94-105: only `.he.txt` is a rendering, so `notes/b.he.md` is
    linted as a note and its rendering looked for at `b.he.he.txt`; and `note_for` returns the
    first of four candidates, so with both `c.txt` and `c.md` beside `c.he.txt` the `.md` note is
    never checked and nothing says so. Reproduced. Class: neighbour (the note suffixes grew to
    four; the rendering suffix stayed one). Tests: `test_a_markdown_rendering_is_a_rendering`,
    `test_two_notes_for_one_rendering_are_reported`.
    Smallest fix: `.he.md` is a rendering too; more than one note is a reported problem.
   Fixed: `keyline/keyline_hook.py` has `HE_SUFFIXES = (".he.txt", ".he.md")`, `rendering_suffix()`,
   `renderings_for()` and `notes_for()`; a note is checked against every rendering it has, a
   rendering with more than one note is a finding (`<rendering>: more than one note beside this
   rendering (notes/c.txt, notes/c.md); keep the one it renders`, exit 2) and each note is still
   checked; `rendering_for`/`note_for`/`HE` removed (no other caller; `keyline/tests/run_tests.py`
   imports `watched()` only), tests `test_a_markdown_rendering_is_a_rendering`,
   `test_two_notes_for_one_rendering_are_reported`.
   Other hits: `keyline/README.md:15,126` and the hook docstring named `.he.txt` only (docstring
   updated; README text in Docs below).
   Prevention: the two tests pin `.he.md` as a rendering and the two-notes finding.

27. (A) keyline/keyline_check.py:101,185: `"No. 5"` counts as a negation, so a Hebrew rendering
    `מס' 5` fails with "1 lost"; and a line-leading label `May:` is a possibility hedge while
    `מאי:` is not. Reproduced (re-run here). Class: extraction edge case.
    Tests: `test_number_sign_no_is_not_a_negation`, `test_month_label_may_is_not_a_hedge`.
    Smallest fix: `no` before an optional dot and a digit is not a negation; `May` before `:`
    is the month.
   Fixed: `NEG_EN` is `no(?!\.\s*\d)`, so "No. 5" / "no.5" is a number sign and `מס' 5` passes,
   while "no 5xx errors" (no dot) stays a negation on purpose (fail closed); `hedges()` treats
   "May"/"MAY" followed by ":" as the month, keyline/keyline_check.py:NEG_EN, hedges, tests
   `test_number_sign_no_is_not_a_negation` and `test_month_label_may_is_not_a_hedge`.
   Other hits: keyline/keyline_check.py:101 and :200 only; `NEG_HE` has no such form.
   Prevention: the two tests pin "No. 5", "no.5", "No.  7", the three negations of "no 5xx errors,
   no data lost. No." and "May: ship v2" against "מאי: לשלוח v2", with "May we proceed?" as the
   control.

28. (A) keyline/measure.py:68-84: a file named on the command line that is not UTF-8 or cannot be
    read is "skipped" with exit 0 and the change line silently omitted (the skip path was written
    for walked folders), and an empty folder prints the header only. Reproduced. Class: neighbour
    of the sixth review's stat-error exit 2. Test: `test_a_named_file_that_cannot_be_counted_is_an_error`
    (exit 2). Smallest fix: return 2 after the report when an argv file was skipped.
   Fixed: `keyline/measure.py:main` counts per argument; zero counted prints `error: the file named
   could not be counted (see the skip line): <arg>` or `error: nothing counted in folder: <arg>` to
   stderr, the report is still printed, return 2; docstring states the exit codes, test
   `test_a_named_file_that_cannot_be_counted_is_an_error`.
   Other hits: `keyline/measure.py:56` unguarded `tiktoken.get_encoding` (fixed: `error: tiktoken
   could not load its encodings: <e>`, exit 1; finding 32's class).
   Prevention: the test asserts exit 2 plus the error line for a not-UTF-8 named file and for an
   empty folder; a skip inside a walked folder stays exit 0 (existing tests).

29. (A) keyline/measure.py:30: a symlinked sub-folder inside a walked folder is skipped without a
    "skip" line (`os.walk` does not follow links) while a symlinked file is counted. Reproduced.
    Class: neighbour (the file case was handled). Test: `test_a_symlinked_folder_is_reported`.
    Smallest fix: print `skip (symlinked folder)` for each.
   Fixed: `keyline/measure.py:files_in` prints `skip (symlinked folder): <path>` to stderr and drops
   the folder from the walk, test `test_a_symlinked_folder_is_reported`.
   Other hits: none (`measure.py` holds the only `os.walk`; `scripts/unused_tools.py:21` rglob;
   `keyline/lint_validate.py:34` corpus glob).
   Prevention: the test asserts the skip line and that the linked folder's file is not in the
   report.

30. (A) scripts/usage_breakdown.py:66, scripts/unused_tools.py:23: the transcript is opened outside
    any try, so a file unreadable between the glob and the read is a traceback; the sixth review
    gave the three other transcript scripts "open in try, one line". VISIBLE.
    Class: neighbour of a previous fix. Test: `test_an_unreadable_transcript_is_one_line` in both
    test files (monkeypatched open). Smallest fix: the same try, one line.
   Fixed: `scripts/usage_breakdown.py:summarize` and `scripts/unused_tools.py:tool_calls` open the
   transcript in `try/except OSError`, print `error: cannot read <path>: <strerror>` to stderr and
   continue, tests `test_an_unreadable_transcript_is_one_line` (in tests/test_usage_breakdown.py and
   tests/test_unused_tools.py).
   Other hits: `scripts/toolresult_share.py:44`, `scripts/usertext_split.py:17`,
   `scripts/usertext_top.py:14` already under try; `scripts/plugin_cost.py:36,63,82` guarded;
   `keyline/lint_validate.py:65` guarded; `hooks/context_check.py:117,166` not transcripts and not
   mine.
   Prevention: both tests monkeypatch `open` to fail for one transcript and assert one line plus the
   other transcript still counted.

31. (A) scripts/usage_breakdown.py:71-92: `usage` that is a list, `message.id` that is a list and
    `"text": null` each traceback, and a BOM drops the first line silently. Reproduced on
    one-line transcripts. Class: neighbour (`isinstance` was added for `event` and `message`
    only). Test: extend `test_non_object_lines_are_skipped`. Smallest fix: type checks and
    `utf-8-sig`.
   Fixed: `scripts/usage_breakdown.py` checks field types (`usage` must be a dict, `message.id` a
   non-empty str, `content` a list, text/thinking via `_len()` which returns 0 for a non-str) and
   opens with `utf-8-sig`, test `test_wrong_typed_usage_fields_are_skipped_and_a_bom_is_read` (kept
   separate from `test_non_object_lines_are_skipped`).
   Other hits: all fixed: `scripts/toolresult_share.py:22,82,84` (`_len`), `:59-61` (role non-str),
   `:72,75` (`_key` for id/tool_use_id), `:45` BOM; `scripts/usertext_split.py:18,28` and
   `scripts/usertext_top.py:15,25` (BOM, `isinstance(t, str)`); `scripts/unused_tools.py:25,69` (BOM
   on transcripts and user-settings.json); `scripts/plugin_cost.py:63,82` (BOM on
   plugin.json/.mcp.json). Not mine: `config/install.py:338` (finding 17).
   Prevention:
   `tests/test_transcript_scripts.py::test_wrong_typed_fields_do_not_crash_and_a_bom_is_read` (all
   three scripts), `tests/test_unused_tools.py::test_a_transcript_with_a_bom_is_read`; source rule 2
   still covers decode errors.

32. (A) scripts/plugin_cost.py:106,103: the output write and `tiktoken.get_encoding` are
    unguarded, so an output path in a missing folder (and the first offline run) is a traceback;
    CHANGELOG:47 says the script "fails cleanly on a missing folder". Reproduced.
    Class: neighbour (the input folder got the check). Test: `test_missing_output_folder_is_an_error`.
    Smallest fix: try/except OSError around both, one line, exit 1.
   Fixed: `scripts/plugin_cost.py:main` guards `tiktoken.get_encoding` (`Error: tiktoken could not
   load o200k_base: <e>`, exit 1, before any plugin is read) and the output write (`Error: cannot
   write <out>: <strerror>`, exit 1), test `test_missing_output_folder_is_an_error`.
   Other hits: `keyline/measure.py:56` (fixed, see 28); `keyline/keyline_lint.py:161,172` guarded;
   `config/verify-tokens.py:44-45` guarded by its caller at line 128; `scripts/tokentest.py:31`
   guarded; writes: `hooks/context_check.py:177` (not mine), `keyline/keyline_lint.py:107`
   (handled).
   Prevention: the test asserts exit 1 and one line for each failure and that no `out.json` appears
   when the encoding cannot load.

33. (A) scripts/plugin_cost.py:48: `glob("**", recursive=True)` does not descend into hidden
    folders, so a plugin under a hidden intermediate folder is not counted. Reproduced.
    Test: `test_a_plugin_under_a_hidden_folder_is_counted`. Smallest fix: `include_hidden=True`.
   Fixed: `scripts/plugin_cost.py:plugin_roots` passes `include_hidden=True` to `glob.glob` (Python
   3.11+, CI is 3.12; `glob.escape` kept), test `test_a_plugin_under_a_hidden_folder_is_counted`.
   Other hits: `keyline/lint_validate.py:34` (corpus glob; skipping `.git/` there is right, left
   alone); `scripts/unused_tools.py:21` rglob already enters hidden folders.
   Prevention: the test asserts both `.plugins/cache/hidden` and `plain/shown` are found.

34. (A) scripts/plugin_cost.py:40-46: a YAML folded or literal description (`description: >`)
    keeps the indicator as its first word. Reproduced. Class: absent is not empty.
    Test: `test_a_folded_description_drops_the_indicator`. Smallest fix: strip `>`/`|` indicators.
   Fixed: `scripts/plugin_cost.py:desc_of` strips a leading YAML block indicator (`>` or `|` with
   optional `-`/`+` and indentation digit, followed by whitespace or end), test
   `test_a_folded_description_drops_the_indicator`.
   Other hits: none.
   Prevention: the test covers `>`, `|`, `>-`, `|+`, `>2`, `|-2` and the control `Plain text >=
   here` (kept).

35. (A) keyline/README.md:144,92 and keyline/keyline_lint.py:153: the Honest limits do not mention
    non-ASCII names (4) or digests over 40 hex digits (3); and the allow-file rule "one per line"
    is not enforced: a line `mgmt srvc` becomes the single entry "mgmt srvc" that never matches,
    both words still flagged. Reproduced. Class: doc claim the code does not meet.
    Test: `test_allow_file_words_on_one_line_are_all_allowed`. Smallest fix: split the line on
    whitespace; the two doc lines.
   Fixed: `load_allow()` does `allow.update(line.split("#", 1)[0].lower().split())`, so a line "mgmt
   srvc  # tool names" allows both words; the module docstring says so,
   keyline/keyline_lint.py:load_allow, test `test_allow_file_words_on_one_line_are_all_allowed`.
   Other hits: keyline/keyline_lint.py:153 (fixed) and :17-19 (docstring, fixed);
   keyline/README.md:91 and the Honest limits (text below).
   Prevention: the test pins both words allowed, a tab-indented word and the absence of the old
   "mgmt srvc" entry; the README line says what a multi-word line does.

## Self-review of the PR diff (fresh-context pass over the fix commits 18527a9..aa8b466)

Two reviewers who had not seen the findings above read only the fix commits: S1 keyline_check,
keyline_lint and scripts; S2 install, uninstall, add_to_repo, keyline_hook and measure. Every
medium was re-reproduced here with `python -I` before being accepted. One regression never
reached a commit: the first draft of the `url` alternative (finding 22) had an unbounded scheme
class, and the existing linear-time test caught it (`"a-" * 16000` went from 0.2 s to 2 s); the
scheme is now at most 31 characters. The findings below are numbered on from the main list.
Counts: 0 high, 5 medium, 11 low; all fixed class-wide in this PR.

36. (S1) keyline/keyline_check.py:27 vs 67-68: the fix for finding 4 widened `proper` and the
    right boundary to LATIN letters but the left boundary `L` stayed ASCII, so a capital after a
    diacritic is a fresh start: `"Zé" * 16000 + "_"` takes 24 s (the hook timeout is 30 s, the
    same shape finding 22's draft had), `ÉCOLE` yields the token `COLE` and `école/notes.txt`
    yields `cole/notes.txt`, so a rendering that writes `COLE` passes. Reproduced (5.8 s at
    8000). Medium. Class: neighbour of a previous fix (same class as findings 2-4).
   Fixed: `L` takes the same letters as `R`: keyline/keyline_check.py:30 `L =
   rf"(?<![A-Za-z0-9_{LATIN}])"`. `Zé`*16000+`_` 24.7 s -> 0.003 s; `the ÉCOLE` no longer yields
   `COLE`, `école/notes.txt` no longer `cole/notes.txt`, `xZürichAirport` no longer `richAirport`.
   Tests: `test_a_long_diacritic_or_hebrew_run_is_extracted_in_linear_time`
   (tests/test_keyline_check.py:404-420, 11 inputs incl. `"Zé"*16000+"_"`, `"Zé"*16000+".5"`,
   `"Éé"*16000+".5"`, each < 2.0 s), `test_a_token_does_not_start_after_a_diacritic` (:423).
   Other hits: the `'s` lookahead inside `proper` (:82) was `(?!s(?![A-Za-z0-9]))`, now
   `(?![A-Za-z0-9{LATIN}])`; `_all_caps_line` used `[a-z]` and `\b[A-Z]{2,}\b`, now
   `LOWER_LETTER`/`CAPS_WORD` with the Latin letters (:234-235). Classes left ASCII on purpose, with
   a comment at :57-59: `camel` (its `[A-Za-z]*[a-z][A-Z]` rescans a letter run from every lower-
   upper pair; adding the diacritics would make `éÉéÉ…` quadratic like the pre-existing `aB`*N case
   the s1 report measured at 2.4-3.0 s), `snake`, `hash`, `ident`, the URL scheme and the drive
   letter. `ZürichAirport` is a `proper` token (it was already), `xZürichAirport` is nothing.
   Prevention: the timing test above (hook budget is 30 s, bound 2.0 s) and the comment at :27-29
   that L and R must take the same letters.

37. (S1) keyline/keyline_check.py:63-64: the `path` and `file` first-character classes moved to
    ASCII (finding 22's fix) and so dropped `סיכום.md`, `תיקיה/קובץ.txt` and `Übersicht.md`,
    which the tree before the fix extracted; the swaps `סיכום.md` to `טיוטה.md` and
    `Übersicht.md` to `Übersicht.txt` now pass. Reproduced. Medium. Class: regression inside a fix.
   Fixed: (a) `path` and `file` first-character classes take LATIN (:77-78). (b) Hebrew start branch
   `HEB_START = rf"(?<![{HEB}])[{HEB}](?![A-Za-z0-9_{LATIN}-])"` (:37) as an alternative first
   character of `path` and `file`: a Hebrew letter opens a name only when no Hebrew letter precedes
   it (one start per word, never one per letter) and no Latin letter, digit or dash follows it.
   `HEB` moved up to :25. Results: `סיכום.md` file, `תיקיה/קובץ.txt` path, `Übersicht.md` file,
   `école/notes.txt`, `Łódź/plan.md` paths; the three s1 swaps fail closed again. `בnotes/a.txt` ->
   `notes/a.txt`, `בÜbersicht.md` -> `Übersicht.md`, `בZürich` -> `Zürich`, `ב-__tests__/` ->
   `__tests__/`, `ו-billing.spec.ts` -> `billing.spec.ts` (the dash refusal was needed: without it
   `ב-__tests__/` became one token and two existing cases of
   `test_a_hebrew_prefix_or_a_sentence_start_still_counts_for_a_path_or_name` failed). `בסיכום.md`
   (Hebrew prefix glued to a Hebrew name): one token `בסיכום.md`; a source `סיכום.md` is not found
   in it, so the check FAILS CLOSED with `missing: סיכום.md`. The dash form `ב-סיכום.md` yields
   `סיכום.md` and passes. Tests: `test_a_file_name_or_path_may_start_with_a_hebrew_or_latin_letter`
   (:432-447, 5 pairs), `test_a_hebrew_prefix_glued_to_a_latin_name_or_path_still_yields_it`
   (:450-462, incl. the `בסיכום.md` limit and `תיקיה-ישנה/קובץ.txt`).
   Other hits: none (no other rule starts a token at a Hebrew letter; `proper`/`upper` stay Latin by
   design, README already says names in another script are not extracted).
   Prevention: the Hebrew inputs in the linear-time test (`"ס"*16000+"_"`, `"ס"*16000+".5"`,
   `"סZ"*8000+"_"`, `"Zס"*8000+"_"`, `"ס"*16000+"/x"`); the comment at :32-36. Honest note: with the
   lookbehind removed the same inputs are still linear (0.17 s at N=8000, 0.34 s at 16000) because
   the path/file tails are bounded at 199, so the test cannot tell the two apart; the lookbehind
   keeps a Hebrew letter inside a word from costing ~400 steps each (0.014 s vs 0.34 s at 16000).

38. (S1) keyline/keyline_check.py:119: `NEG_EN` `no(?!\.\s*\d)` (finding 27) crosses a line
    break, so `Data lost: no.` followed by `1. Restart` on the next line is read as "No. 1" and
    the negation is dropped; a rendering that flips it to "yes" passes. Reproduced. Medium.
    Class: neighbour of a previous fix.
   Fixed: keyline/keyline_check.py:136 `no(?!\.[ \t]*\d)`: `no.` at a line end before `1. Restart`,
   `2026-10-25 …` or `10:00 …` counts as a negation; `No. 5`, `no.5`, `No.  7` still do not. Test:
   `test_number_sign_no_is_not_a_negation` extended (:385-397) with the three line-break cases and
   the fail-open check pair (now `ok=False`).
   Other hits: `hedges()` :243 `re.match(r"\s+\d|:", …)` for the month `May` also crossed a line
   break (`May\n5 items` was the month, hedge dropped); now `[ \t]+\d`. Test:
   `test_a_month_at_a_line_end_before_a_number_on_the_next_line` (:465). No other `\s` in a
   negation/hedge pattern: NEG_HE, HEDGE, HEDGE_HE have none; LIST_MARKER already uses `[ \t]+`;
   keyline_lint's FURNITURE `\s` is a line-level style rule, not a negation/hedge.
   Prevention: the two tests; comments at :134-135 and :250-251.

39. (S1) keyline/keyline_check.py:201: a `url` token keeps a trailing `:`, `?` or `!`, so a
    sentence-final URL before one of them always fails (closed). Low.
   Fixed: :218 `tok = tok.rstrip(".:!?") if kind == "url" else tok.rstrip(".")`.
   `https://x.y/z:`/`?`/`!` -> `https://x.y/z`; the three Hebrew renderings pass. Test:
   `test_a_url_keeps_its_scheme` extended (:374-382).
   Other hits: none. The only other kinds whose token can end in `.` are `path` (already stripped);
   `number`, `version`, `file`, `proper`, `hash`, `ident`, `time` cannot end in `.:!?` by their
   patterns. `;` `,` `)` `]` `}` quotes and `|` are already excluded from the url class.
   Prevention: the extended test; p5 shows every trailing punctuation shape.

40. (S1) keyline/README.md:58-59: "and the other way round" is false when the source has a
    trailing `Z` or JS-style milliseconds (`2026-10-25T14:30:00.000Z`). Low.
   Fixed: (a) the `time` alternative takes fractional seconds after whole seconds, :74
   `(?::\d{2}(?:\.\d+)?)?` (`14:30:00.250Z` is one time token; `1:30.5` lap-style stays `1` + `30.5`
   as before); (b) the time lookup in `present()` allows an added fraction before an added `Z` when
   the source time has seconds, :297 `tail = r"(?:\.\d+)?Z?" if re.fullmatch(r"\d{1,2}:\d{2}:\d{2}",
   tok) else r"Z?"` — `2026-10-25 14:30:00` now passes against `2026-10-25T14:30:00.000Z`; (c) the
   datetime lookup is built from the token's parts (`DATETIME` :55, :289-293): an added fraction
   after whole seconds and an added `Z` on a zone-less token are accepted (`2026-10-25T14:30:00Z` vs
   `…T14:30:00.000Z`, `2026-10-25T14:30` vs `…T14:30Z` now pass, as the two-token form already did),
   while a dropped zone (`T14:30Z` -> ` 14:30`, `+02:00` -> `Z`) or a dropped fraction (`.250Z` ->
   `Z`) stays a miss. Test: `test_added_fractional_seconds_and_a_kept_zone_in_the_iso_form`
   (:473-487).
   Other hits: none.
   Prevention: that test pins both directions, incl. the zone-kept miss the README sentence must
   describe.

41. (S1) keyline/README.md:196-197: "a hex hash longer than 128 digits is not extracted" holds
    only when it starts with a digit; letter-first it is an `ident`. Low (doc).
   Fixed: doc only (see Docs). Behaviour unchanged and confirmed by p5: 129 hex digit-first ->
   nothing, letter-first -> `ident`, 128 -> `hash`.
   Other hits: none.
   Prevention: README wording says "not extracted as a hash".

42. (S1) keyline/keyline_check.py: `upper` is ASCII-only and `proper` needs a lowercase tail, so
    an all-caps name with a diacritic (`ÉCOLE`, `NGUYỄN`) is not extracted at all once 36 is
    fixed. Low.
   Fixed: `upper` takes LATIN_UPPER in its first character, its tail and the `_` parts, :79:
   `ÉCOLE`, `NGUYỄN`, `ZÜRICH`, `SÃO_PAULO` are `upper` tokens and a swap to `PARIS` fails closed.
   The lone-letter filter is `LONE_LETTER = [A-Z{LATIN_UPPER}]s?` (:92), so `É`, `Ó`, `Ås` alone are
   not identifiers. Linear: `"ÉÉ"*8000+".5"` 0.002 s, `"ÉCOLE"*4000+"_"` 0.002 s (one start per run,
   L blocks the rest); fuzzers clean. Tests:
   `test_an_all_caps_name_with_a_diacritic_is_an_identifier` (:484-497),
   `test_a_lone_capital_letter_with_a_diacritic_is_not_an_identifier` (:499-501),
   `test_an_all_caps_line_may_hold_a_diacritic_word` (:504, `MAY ÉCOLE` is the modal like `MAY
   PARIS`, `MAY école` the month).
   Other hits: `_all_caps_line` (see 1). The calendar fallback in `present()` is unaffected
   (`len(tok) > 3` + CALENDAR lookup).
   Prevention: the tests above and the `ÉÉ`/`ÉCOLE` runs in the timing test.

43. (S2) config/install.py:510 and config/uninstall.py:64: an interrupt at the fifth and last
    write (the full record, after settings.json) leaves the interim record, which says
    `added_keys: []`; the next install sees every value already present and records nothing, and
    the uninstall trusts the record and leaves the three scalar keys, `permissions.deny` and an
    empty hooks container behind while writing `{"uninstalled": true}`. Reproduced. Medium.
    Class: halfway state (the boundary after the one finding 6's fix covered).

44. (S2) keyline/keyline_hook.py:154: stderr is reconfigured to UTF-8 with strict errors, so a
    file name that is not valid UTF-8 (`notes/\xff.txt`, a surrogate in the event JSON) turns
    every message into a traceback: a blocking lint failure becomes exit 1 with the finding
    lost, and the read-error path breaks the one-line contract. Reproduced. Medium. Class:
    neighbour of a previous fix (finding 19 covered file content, not the name).

45. (S2) config/install.py:243-250: `_refuse_read_only` checks files, not directories; with
    `.claude` at 555 and CLAUDE.md absent the hook is written and the CLAUDE.md temp file then
    fails (named halfway state). Low.

46. (S2) config/uninstall.py:232-251: the hook folder is not checked either, so settings.json is
    written and the hook unlink fails with "the undo stopped part way"; on Windows a read-only
    hook file does the same because nothing clears the attribute before `unlink()`, unlike
    add_to_repo's `_write_bytes`. Low.

47. (S2) config/install.py:243 and config/add_to_repo.py:148: on Windows `os.access` sees the
    read-only attribute only, so an ACL-denied target brings the old halfway state back; the
    README line should say "read-only attribute or mode". Low (documented limit).

48. (S2) keyline/keyline_hook.py:193-197: two notes beside one rendering is printed under "fix
    the rendering" and then checked against both notes, so the first line points at the wrong
    file. Low.

49. (S2) keyline/keyline_hook.py:178-179: an explicit `--watch` pattern that names a dotfile is
    silently ignored; the README says only that the suffix rule still applies. Low.

50. (S2) config/install.py:482-510: an interrupt at the interim record or the CLAUDE.md write
    leaves an orphan `CLAUDE.md.bak-*` and the next install makes a second backup of the same
    user file (the orphan `settings.json.bak-*` of finding 5, one file earlier). Low.

51. (S2) keyline/measure.py:36-39: a Windows junction is neither reported nor skipped as the
    symlinked folder the docstring describes; install and add_to_repo already have `_is_link`
    with `os.path.isjunction` for this. Low (code reading).

## Checked and found clean (both reviewers and both verifiers)

Install/uninstall/reinstall sequences run for real (hand-reformatted settings.json, our hook
copied by hand into another event, CLAUDE.md edited then reverted between two uninstalls, a value
the first uninstall left then reinstall and `--force`, legacy records on a plain cycle,
`CLAUDE_CONFIG_DIR` with a trailing separator through install, hook, uninstall and verify);
`_merge_record` first-wins and `created` across install, marker and reinstall; symlinked files
written through and dangling links refused; the context hook on every malformed stdin shape;
`add_to_repo.py` order and `--force`; the CI matrix (no test skipped on both runners); the
`check(line, line)` invariant over 60,000 fuzzed lines; extraction of every documented shape;
the lint's flags and allow-file handling; the hook's event handling; the transcript scripts on
malformed content; every README and CHANGELOG claim except the ones named above.
