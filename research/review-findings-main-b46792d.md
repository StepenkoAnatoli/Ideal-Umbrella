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
Counts: 0 high, 7 medium, 28 low in the main pass; 0 high, 5 medium, 11 low in self-check pass 1; 0 high, 6 medium, 4 low in pass 2; 0 high, 4 medium, 7 low in pass 3.

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
   Fixed: The interim record no longer carries settings data. config/install.py:546 writes
   `dict(old_record, claude_md=record["claude_md"])` (before: the full record with `added_keys: []`,
   `replaced: {}`), so an install interrupted at the last write (N=5) leaves a record that holds
   only `claude_md`. config/uninstall.py:70-72 tells the three states apart: `has_record` (a record
   with `added_keys`/`replaced`/`installed`), `unfinished` (a record with none of them and not the
   `uninstalled` marker), `no_record` (no file). An unfinished record is treated like no record for
   the settings: the template values are removed when the hook entry is there (uninstall.py:93
   notice "the install record holds no settings data (the install did not finish); the template
   values are removed as without a record"), left alone otherwise (uninstall.py:98 "... and there is
   no Ideal-Umbrella hook; settings values left as is"), and `permissions.deny` is left with its own
   notice (uninstall.py:146 "... permissions.deny left as is"). The marker record (`uninstalled:
   true`) stays silent, so a second uninstall prints what it did before. The module docstring says
   so. Re-install after N=5 is `([], [])` as before, since the files already equal the templates;
   the repair is the uninstall. Tests: tests/test_install.py:725
   `test_interrupt_at_the_final_record_is_undone_by_the_uninstall` (helper `_interrupt` at :716
   fails the N-th `_write_json` of the record; asserts the record keys are `["claude_md"]`, the re-
   install changes nothing, the uninstall leaves `{"model": "opus", "permissions": {"deny":
   <template deny>}}`, both "no settings data" notices, CLAUDE.md restored, hook gone). Failed first
   with the record holding `added_keys`, and the uninstall leaving the two keys and the hook entry
   in settings.json.
   Other hits: the same `unfinished` test now guards the deny branch (uninstall.py:146) that used
   the same `record is None` rule; the interim write in install.py was the only place that wrote
   settings data before settings.json. Decision noted: the deny tools are left, not removed, because
   without settings data in the record they cannot be told from the user's own entries, the same
   rule the no-record path already applies; the test pins that choice (the s2 report's expectation
   was looser).
   Prevention: the test above; the rule "the record never names a settings value before
   settings.json holds it" is in install.py's docstring (write order) and the interim write carries
   only `claude_md`.

44. (S2) keyline/keyline_hook.py:154: stderr is reconfigured to UTF-8 with strict errors, so a
    file name that is not valid UTF-8 (`notes/\xff.txt`, a surrogate in the event JSON) turns
    every message into a traceback: a blocking lint failure becomes exit 1 with the finding
    lost, and the read-error path breaks the one-line contract. Reproduced. Medium. Class:
    neighbour of a previous fix (finding 19 covered file content, not the name).
   Fixed: `sys.stderr.reconfigure(encoding="utf-8")` reset `errors` to strict, so a surrogate-
   escaped file name made every message a `UnicodeEncodeError` traceback.
   keyline/keyline_hook.py:163 now reconfigures with `errors="backslashreplace"`; a lone surrogate
   prints as the escape `\udcff` (the code point, not the original byte). Docstring sentence at
   keyline_hook.py:30-32: "A file name is printed as is; a byte in it that is no UTF-8 is shown as a
   backslash escape, not as a traceback." Test: tests/test_keyline_hook.py:262
   `test_a_file_name_outside_utf8_is_reported_not_a_traceback` (note `b"\xff.txt"` with a lint
   finding: exit 2, first line `NOTE_HEADER`, `\udcff.txt` and `furniture` in stderr, no Traceback;
   as a non-root user also the unreadable case: exit 1 and exactly one line). Failed first with the
   traceback and exit 1.
   Other hits: the same `reconfigure(encoding="utf-8")` shape in config/install.py:697,
   config/uninstall.py:383, config/add_to_repo.py:197 and keyline/measure.py:60 (stdout, which
   prints paths and home folders); all now pass `errors="backslashreplace"`, as do the twelve
   other sites of the same shape (keyline_check.py:371, keyline_lint.py:232, config/verify-tokens.py:78,
   hooks/context_check.py:198, scripts/lint_validate.py, plugin_cost.py, tokentest.py,
   toolresult_share.py, unused_tools.py, usage_breakdown.py, usertext_split.py, usertext_top.py).
   Prevention: tests/test_source_rules.py rule 6, `test_utf8_reconfigure_keeps_an_errors_handler`
   (every `reconfigure(encoding="utf-8")` call also passes `errors=`); failed first on the twelve.
   Prevention: the test; a source rule in tests/test_source_rules.py ("a `reconfigure(encoding=...)`
   passes `errors=` too") would catch the next one; not added because that file is outside my set,
   proposed in Docs.

45. (S2) config/install.py:243-250: `_refuse_read_only` checks files, not directories; with
    `.claude` at 555 and CLAUDE.md absent the hook is written and the CLAUDE.md temp file then
    fails (named halfway state). Low.
   Fixed: install checked the four files but not the folders their writes need, so with `.claude`
   mode 555 the hook was written (ballast/ is writable) and the CLAUDE.md temp file then failed.
   config/install.py:245 `_refuse_read_only` now also calls the new
   `_refuse_unwritable_folder(path)` (install.py:257): it takes the target's parent, and the
   resolved parent when the target is a symlink, walks up to the nearest folder that exists, and
   raises `ValueError("<folder> is read-only; make it writable first")` when `os.access(folder,
   os.W_OK)` is false; it is a no-op on Windows, where os.access never reports a folder as read-only
   (see #5), and a file in the way is left to the write's own error, as before. Test:
   tests/test_install.py:805 `test_a_read_only_folder_is_refused_before_any_write`, parametrized
   over `.claude` and `.claude/ballast` (mode 555), skipped as root and on Windows; expects exit 1,
   "is read-only" on stderr, no "Done before the error", and no file written. Failed first (as uid
   65534) with "Done before the error: hook written".
   Other hits: config/add_to_repo.py:148 `_refuse_read_only` had the same gap (G8c: `.claude` 555
   with `hooks/` absent wrote nothing but failed after the check phase with a bare OSError; with
   `hooks/` present and writable the hook was copied first): it now walks `dirname(abspath)` and
   `dirname(realpath)` up to an existing folder the same way (add_to_repo.py:157-161); test
   tests/test_add_to_repo.py:284
   `test_a_read_only_claude_folder_is_refused_before_the_hook_is_written`. uninstall's removals are
   #4.
   Prevention: the two folder tests, run as uid 65534 in the /var/tmp copy (they skip as root); g.sh
   G2/G2b/G8c/G9 now end "nothing written".

46. (S2) config/uninstall.py:232-251: the hook folder is not checked either, so settings.json is
    written and the hook unlink fails with "the undo stopped part way"; on Windows a read-only
    hook file does the same because nothing clears the attribute before `unlink()`, unlike
    add_to_repo's `_write_bytes`. Low.
   Fixed: uninstall wrote settings.json and then failed at `unlink()` of the hook when `ballast/`
   was 555 (or, on Windows, when the hook file had the read-only attribute).
   config/uninstall.py:274-290: before the settings backup, the files the undo will delete (hook,
   state link or folder, log, the CLAUDE.md backup when it is restored, CLAUDE.md itself when it
   will be deleted) are collected and each folder is checked with
   `install._refuse_unwritable_folder(path, through_link=False)` (a link is unlinked, not followed),
   so a read-only folder is a one-line refusal before anything is written. New `_remove(path)`
   (uninstall.py:184) sets `S_IWRITE` on a regular file (try/except OSError; never on a symlink) and
   then unlinks, so a read-only hook, log, backup or CLAUDE.md is deleted on Windows too; it
   replaces `unlink()` at uninstall.py:296 (hook), :317 (log), :329 (backup after restore), :352 and
   :364 (CLAUDE.md); the state symlink keeps `unlink()`. Tests: tests/test_uninstall.py:715
   `test_a_read_only_hook_folder_is_refused_before_settings_is_written` (ballast 555; skip root/nt;
   failed first with settings.json rewritten and "the undo stopped part way"),
   tests/test_uninstall.py:739 `test_read_only_files_the_undo_deletes_are_deleted` (hook, log and
   backup mode 0444, `Path.unlink` monkeypatched to raise PermissionError on a file without
   S_IWRITE, the Windows behaviour, so the chmod-before-unlink path is exercised and fails first on
   Linux: it failed with that PermissionError).
   Other hits: every `unlink()` of a regular file in uninstall.py (five sites) went through
   `_remove`; the folder check covers all five removal targets, not only the hook. install.py's
   temp-file cleanup already chmods before removing.
   Prevention: the two tests; `_remove` is the only way uninstall deletes a regular file.

47. (S2) config/install.py:243 and config/add_to_repo.py:148: on Windows `os.access` sees the
    read-only attribute only, so an ACL-denied target brings the old halfway state back; the
    README line should say "read-only attribute or mode". Low (documented limit).
   Fixed: no code fix is possible without an ACL helper (os.access on Windows consults the read-only
   attribute only, and never reports a folder as unwritable), so the docstrings now say what the
   check sees: config/install.py:245-256 `_refuse_read_only` ("os.access sees a POSIX mode or the
   Windows read-only attribute, not a Windows ACL that denies the write: that write fails at its own
   turn, as before") and :257-262 `_refuse_unwritable_folder` (no-op on Windows),
   config/add_to_repo.py:148-154 the same wording. The behaviour behind an ACL denial is unchanged:
   the hook is written, then the denied write fails with the "Done before the error" listing, and
   the backup names are printed. README wording to apply is in Docs ("read-only attribute or mode",
   and the Honest-limits sentence).
   Other hits: none (the two `_refuse_read_only` functions are the only pre-write permission checks;
   uninstall reuses install's).
   Prevention: documented limit; the Windows CI leg runs the attribute-based tests
   (`test_read_only_files_the_undo_deletes_are_deleted` exercises the attribute path there for
   real).

48. (S2) keyline/keyline_hook.py:193-197: two notes beside one rendering is printed under "fix
    the rendering" and then checked against both notes, so the first line points at the wrong
    file. Low.
   Fixed: two notes beside one rendering were printed under RENDERING_HEADER ("fix the rendering")
   with a FAIL line per note, although the fix is to remove a note. keyline/keyline_hook.py:45 adds
   `TWO_NOTES_HEADER = "keyline: more than one note beside this rendering; keep the one it renders,
   then write it again."`; :200-210 sets `too_many` when more than one note is found and reports one
   line `<rendering>: notes beside it: <a>, <b>`, skipping the per-note checks (`run_check` runs
   only with at most one note); :232 picks the header `NOTE_HEADER if lint_problems else
   TWO_NOTES_HEADER if too_many else RENDERING_HEADER`, so a lint finding still comes first. Exit
   stays 2 (blocking, since no check ran). Docstring kept in step (keyline_hook.py:16-18 and
   :29-30). Test: tests/test_keyline_hook.py:217 `test_two_notes_for_one_rendering_are_reported`
   updated: first line equals `TWO_NOTES_HEADER`, "fix the rendering" not in it, no "FAIL" line,
   both notes named. Failed first with AttributeError on the missing constant, and the old header.
   Other hits: none; the note-side path (a note written while a second note shares its rendering)
   goes through the same `too_many` branch since the rendering is what is looked up.
   Prevention: the updated test; the header table in the docstring.

49. (S2) keyline/keyline_hook.py:178-179: an explicit `--watch` pattern that names a dotfile is
    silently ignored; the README says only that the suffix rule still applies. Low.
   Fixed: the dotfile skip ran before the `--watch` patterns, so `--watch notes/.todo.md` could
   never match. keyline/keyline_hook.py:187 now `if not patterns and path.name.startswith("."):`: an
   explicit pattern overrides the dotfile rule; the suffix rule still applies. Docstring
   keyline_hook.py:13 says so. Test: tests/test_keyline_hook.py:244
   `test_an_explicit_watch_pattern_names_a_dotfile` (`notes/.hidden.txt` with a lint finding: exit 0
   without a pattern, exit 2 with `--watch notes/.hidden.txt` and the note named). Failed first with
   exit 0 under the pattern.
   Other hits: the out-of-project rule and the suffix rule were checked: a pattern still does not
   override the suffix rule (documented) and the out-of-project rule already yields to an absolute
   pattern.
   Prevention: the test.

50. (S2) config/install.py:482-510: an interrupt at the interim record or the CLAUDE.md write
    leaves an orphan `CLAUDE.md.bak-*` and the next install makes a second backup of the same
    user file (the orphan `settings.json.bak-*` of finding 5, one file earlier). Low.
   Fixed: a cheap fix exists for both shapes. N=2 (interim record write fails right after the backup
   was made): config/install.py:546-556 unlinks the backup it just made (not one it reused), drops
   its "CLAUDE.md backup:" line from `changes`/`progress`, then re-raises, so nothing of the install
   is left. N=3 (CLAUDE.md write fails after the interim record was written): the next install reads
   `old_record["claude_md"]["backup"]` (install.py:478-486, `recorded_copy`): when the name is a
   plain file name, the file exists and its bytes equal the current CLAUDE.md, that backup is reused
   instead of making a second one (install.py:513-516), no "edits made after the last install"
   notice is printed for it, and the interim record is written again with the same name. A backup
   whose bytes differ (the user edited CLAUDE.md in between) is not reused: a fresh one is made, as
   before. Docstring step 2 (install.py:15-18) says both. Tests: tests/test_install.py:752
   `test_interrupt_at_the_interim_record_leaves_no_orphan_backup` (failed first with one
   `CLAUDE.md.bak-*` left) and :772
   `test_interrupt_at_the_claude_md_write_reuses_the_recorded_backup` (`_write_bytes` monkeypatched
   to fail once on CLAUDE.md; failed first with two backups after the re-install).
   Other hits: settings.json's backup is made right before its write (same call), and the full
   record is written after it; the interrupt there (N=4) was already covered and leaves the backup
   that the record names. No other backup is made before its record.
   Prevention: the two tests plus interrupt.py (N=2 `baks: []`, N=3 one backup and no second
   "CLAUDE.md backup:" line).

51. (S2) keyline/measure.py:36-39: a Windows junction is neither reported nor skipped as the
    symlinked folder the docstring describes; install and add_to_repo already have `_is_link`
    with `os.path.isjunction` for this. Low (code reading).
   Fixed: keyline/measure.py:26 `_is_link(path)` = `os.path.islink(path) or bool(isjunction and
   isjunction(path))` (os.path.isjunction, Python 3.12+ on Windows); used for the skip line (:43)
   and the prune (:46), both on `os.path.join(root, d)`. Docstring: "symlinked folders, on Windows
   junctions too, are skipped". Tests: tests/test_measure.py:151
   `test_a_junction_is_skipped_as_a_symlinked_folder` (monkeypatches `os.path.isjunction` so the
   code path runs on Linux; failed first with the folder's file counted and no skip line) and :170
   `test_a_real_junction_is_skipped` (`mklink /J`, nt-only).
   Other hits: config/add_to_repo.py and uninstall.py already had `_is_link` with the junction
   check; measure.py was the last `islink`-only site in my files.
   Prevention: the two tests (the nt-only one runs on the Windows CI leg).

## Self-check pass 2 (fresh-context pass over the fix commits 07671ca..c829812)

Two reviewers who had not seen the findings above read only the pass 1 fix commits: R1 the
keyline_check commits 07671ca and c50d1e5, R2 the config/hook/measure commit c829812. Every
medium was re-reproduced here with `python -I` (the read-only case as uid 65534 in a copy
under /var/tmp, since root ignores file modes) before being accepted.
Counts: 0 high, 6 medium, 4 low (R2 findings 52-55: 2 medium, 2 low; R1 findings 56-61: 4 medium,
2 low); all fixed class-wide in this PR.

52. (R2) keyline/keyline_hook.py:187: the fix for finding 50 turned the dotfile rule off for
    every `--watch` pattern, not only one that names the file: fnmatch's `*` matches a leading
    dot, so `--watch notes/*` linted `notes/.gitignore` (`# build output` is a furniture header,
    exit 2) where the same write was exit 0 before c829812. Reproduced. Medium. Class:
    regression inside a fix; neighbour of the tested input (a glob instead of the file name).
   Fixed: `watched()` keeps, for a dotfile, only the patterns whose last component starts with a
   dot (`notes/.todo.md`, `notes/.*`, `*/.git*`), the way a shell glob reads `*`; with none left
   the file is not watched, so the check in main() went. Test:
   tests/test_keyline_hook.py `test_a_watch_glob_does_not_make_a_dotfile_a_note` (`notes/*`, `*`,
   an absolute glob and `notes/*ignore` give exit 0 and no output; `notes/.*`, the file name, its
   absolute path and `*/.git*` give exit 2 with NOTE_HEADER). Failed first with exit 2 on `notes/*`.
   Other hits: none (the notes/-folder rule has no pattern side).
   Prevention: docstring, keyline/README.md step 2, README.md hook line and CHANGELOG say which
   patterns mean a dotfile.

53. (R2) config/uninstall.py:271-285 with :307: the pre-write folder check covered the folder
    holding each removed path (ballast/ for the state folder), but `shutil.rmtree` also unlinks
    inside the state folder and its sub-folders: with a read-only `state/` the undo rewrote
    settings.json (with a backup) and deleted the hook, then stopped at `state/` on every run,
    the shape finding 45 set out to remove. README.md promised the check. Reproduced as uid
    65534. Medium. Class: halfway state (a sibling of the fixed hook-folder case).
   Fixed: the removals check also walks the state folder (not a link) and refuses any folder in
   it that is not writable, before the first write. Test: tests/test_uninstall.py
   `test_a_read_only_state_folder_is_refused_before_settings_is_written` (a 555 sub-folder with a
   file: two runs exit 1 with "read-only ... nothing written", no settings backup, settings.json
   and the hook untouched; skipped as root and on Windows). Failed first as uid 65534 with the
   halfway undo.
   Other hits: the Windows twin, a read-only file inside `state/` (`_remove` cleared the mode on
   the hook, log, backup and CLAUDE.md; rmtree does not): `_remove_tree` clears the mode on
   every file under the folder first, through the shared `_clear_read_only`. Test:
   `test_read_only_files_inside_the_state_folder_are_deleted` (rmtree made to refuse a read-only
   file as Windows does; fails without the fix on every platform).
   Prevention: README.md names the state folder's own tree among the checked folders and the
   files inside it among those whose attribute is cleared.

54. (R2) config/uninstall.py:71 with config/install.py:553: the interim record was the old
    record plus `claude_md`, so over the marker an uninstall leaves (`{"uninstalled": true}`) it
    kept that key; an install on the marker interrupted at its final write left
    `{"uninstalled": true, "claude_md": ...}` while settings.json held the keys, and the next
    uninstall read it as neither unfinished nor absent: the keys went by the hook evidence, the
    deny tools stayed, and no notice said so (the docstring and README promise one). Low. Class:
    "absent is not empty" (a marker key is not install data); notice missing.
   Fixed: the interim record drops `uninstalled` (`_merge_record` already dropped it from the
   final record). Test: tests/test_install.py
   `test_interrupt_at_the_final_record_over_a_marker_is_an_unfinished_record` (install, uninstall,
   re-install interrupted at the final record: the record is `{"claude_md": ...}`, the next
   uninstall gives the "no settings data ... permissions.deny" notice and the settings end as
   with no record). Failed first with the key kept and no notice.
   Other hits: none; the final record goes through `_merge_record`.
   Prevention: CHANGELOG names the marker among what the interim record does not carry.

55. (R2) keyline/keyline_hook.py:213-217: "more than one note beside one rendering is a finding
    of its own" held only when the rendering was written; a write of the note the rendering does
    not render still checked it against the rendering and said "fix the rendering" with a FAIL
    block, so two writes of the same three files gave contradictory instructions. Low. Class:
    halfway state (one side of the shape fixed in finding 49).
   Fixed: the note branch asks `notes_for(rendering)` first and reports the same "notes beside
   it" line under TWO_NOTES_HEADER when there is more than one, checking only once one note is
   left. Test: tests/test_keyline_hook.py `test_two_notes_are_reported_from_the_note_side_too`
   (write of the other note: TWO_NOTES_HEADER, no FAIL, all three files named; after deleting a
   note the check runs and FAILs under RENDERING_HEADER). Failed first with RENDERING_HEADER and
   a FAIL block.
   Other hits: none (two branches, both covered now).
   Prevention: docstring, keyline/README.md step 3 and CHANGELOG say "whichever of the files is
   written".

56. (R1) keyline/keyline_check.py:286-299 (`present()`), keyline/README.md:47: a source timestamp
    or time that carries a zone is a miss in a rendering that keeps the zone and adds seconds or a
    fraction: the escaped zone is appended straight after the clock, so `2026-10-25T14:30Z` is not
    found in `2026-10-25T14:30:00Z`, and the time kind adds the `(?:\.\d+)?` tail only without a
    `Z`, so `14:30:00Z` is not found in `14:30:00.000Z` (the datetime kind got the fraction fix of
    finding 42, the time kind did not). The README line says a rendering may add seconds, a
    fraction or a `Z` without the "no zone" qualification. Reproduced. Medium. Class: halfway fix
    (one of two kinds), doc does not match code.
   Fixed: `present()` builds the clock part of a datetime or time lookup with the new
   `_clock_lookup()` (keyline/keyline_check.py:345-354): a fraction the source wrote is required;
   after whole seconds a fraction may be added; after `HH:MM` seconds and then a fraction may be
   added; the zone the source has is required after that, and a token without a zone may gain one.
   The time kind now parses its token with `TIME` (keyline/keyline_check.py:57) the way the datetime
   kind parses with `DATETIME`, so both kinds take the same shape (present() at
   keyline/keyline_check.py:307-342; the `tail` variable is gone). Test
   `test_a_rendering_may_add_seconds_or_a_fraction_before_a_zone_the_source_has`
   (tests/test_keyline_check.py:516-535, 9 cases) failed first on 8 of 9 cases (`14:30Z` in
   `14:30:00Z`, `14:30:00Z` in `14:30:00.000Z`, `2026-10-25T14:30Z` in `2026-10-25T14:30:00Z` and
   `...00.000Z`, `+02:00` kept, the two-token form, the Hebrew line of the reviewer's input; the no-
   zone case passed before, as the report said) and passes now. The CLI reproduction `in/ts_src.txt`
   vs `in/ts_ren.txt` now prints PASS (2 invariants present).
   Other hits: the datetime kind with a short clock (`2026-10-25T14:30Z` in `2026-10-25T14:30:00Z`)
   was the same shape and is fixed by the same helper; the time kind with a short clock and a zone
   (`14:30Z` in `14:30:00.000Z`) too. The date kind is unchanged (it has no clock).
   Prevention: the guard test `test_a_dropped_or_changed_zone_or_fraction_is_still_a_miss`
   (tests/test_keyline_check.py:538-550, 9 cases: dropped `Z`, dropped fraction, `Z` -> `+02:00`,
   `+02:00` -> `Z`, for both kinds) pins the misses; keyline/README.md:58 now says exactly what the
   code does ("may add seconds, fractional seconds or both, before a zone the source has ... or
   without one ..., and a zone to a time or timestamp that has none; a zone or a fraction the source
   has and the rendering drops is a miss"); the comment above `_clock_lookup()` and in `present()`
   (keyline/keyline_check.py:325-330) says the same.

57. (R1) keyline/keyline_check.py:189-194 (`_is_path`) against the widened path start (:77): the
    prose exception "one slash between two plain lowercase words" still matches `[a-z]+` only, so
    `yes/no` and `oui/non` are prose while `él/ella`, `sim/não` and `כן/לא` are paths a translated
    rendering misses; `él/ella` passed before 07671ca (nothing was extracted). Reproduced. Medium.
    Class: halfway state (the start class widened, the prose exception not); regression inside a fix.
   Fixed: `_is_path()` (keyline/keyline_check.py:195-206) tests each side of the slash with
   `PROSE_WORD = [a-z LATIN_LOWER]+ | [א-ת]+` instead of `[a-z]+`, the same letters the path start
   takes (ASCII, the module's LATIN constants, Hebrew). Test
   `test_a_slash_between_two_plain_words_in_any_script_is_prose`
   (tests/test_keyline_check.py:553-562: `yes/no`, `and/or`, `él/ella`, `sim/não`, `כן/לא`,
   `oui/non`, `sí/no`) failed first on `él/ella`, `sim/não`, `כן/לא`, `sí/no` (and on `yes/no`,
   which was my own rendering lacking the negation that `no` counts; corrected to the reviewer's
   `כן/לא` rendering) and passes now. The CLI reproduction `in/path_src.txt` vs `in/path_ren.txt`
   now prints PASS.
   Other hits: `sim/não` (diacritic not first) and `כן/לא` (Hebrew) were the same asymmetry and are
   covered by the same class; no other place in the module has a `[a-z]+` prose test. A plain two-
   word Hebrew pair with no dot (`תיקיה/קובץ`) is now prose like `src/lib`, consistently.
   Prevention: guard test `test_a_real_path_is_still_a_path` (tests/test_keyline_check.py:565-581)
   pins `notes/a.txt`, `תיקיה/קובץ.txt`, `école/notes.txt`, `כן/לא.txt`, `a1/b`, `a_b/c`, `a-b/c`,
   `a/b/c`, `src/lib.rs`, `él/ella1`, `sim/não_x`, `כן/לא/x`, `Yes/No` as paths that a swap reports,
   and `src/lib` as the documented two-word prose it was before (it was never a path:
   keyline/README.md:201 says so; "exactly as before" is kept). keyline/README.md:201-204 now states
   the rule with its letters; the code comment in `_is_path()` lists both sides.

58. (R1) keyline/keyline_check.py:243 (`hedges()`, the `[ \t]+\d|:` test after `May`): a `May`
    heading (`## May`, or `May` alone on its line) followed by a line that starts with a digit is
    now a possibility hedge, since the line break no longer counts as the whitespace before the
    digit; a monthly note with `## May` / `5 PRs merged` fails its `## מאי` rendering with "hedges
    lost: possibility (may)" where it passed before. The test for the narrowing covers only the
    modal reading. Reproduced. Medium. Class: regression inside a fix.
   Fixed: `hedges()` (keyline/keyline_check.py:276-294) calls the new `_is_month_line()`
   (keyline/keyline_check.py:253-273) as one more reason a `May`/`MAY` is the month. The rule, as
   documented in its docstring: the token is the whole content of its line, allowing only Markdown
   heading, quote and list markers, bold or whitespace before it (`#>-*+_`, space, tab) and bold, a
   colon or whitespace after it (`*_:`, space, tab); a numbered or bulleted list marker is already
   stripped by LIST_MARKER. With any such furniture (`## May`, `**May**`, `> May`, `May:`) it is the
   month. A bare `May` line with no furniture is the month unless the sentence it opens, up to the
   first `.`, `?` or `!` or a blank line, ends in `?` (`May\n5 items be removed?` stays the modal,
   as the existing test asserts). Sentence ends are found once per text through a small cache, so
   8000 bare `May` lines take 0.04 s. Test
   `test_a_may_that_is_the_whole_content_of_its_line_is_the_month`
   (tests/test_keyline_check.py:584-596, 9 cases including the reviewer's `## May\n5 PRs merged at
   14:02` vs `## מאי\n5 PRs מוזגו ב-14:02`, plain `May\n5 PRs`, `**May**`, `- May`, `> May`, `##
   May\nnothing shipped`, a heading before a question, a heading after a blank line) failed first on
   8 of 9 (`# MAY` passed before: the all-caps rule already made it the month) and passes now;
   `test_a_bare_may_line_that_opens_a_question_is_the_modal` (tests/test_keyline_check.py:599-607)
   failed first and passes now. The CLI reproduction `in/may_src.txt` vs `in/may_ren.txt` now prints
   PASS. The existing `test_a_month_at_a_line_end_before_a_number_on_the_next_line` still passes
   (the rule only adds month readings, never a modal one, so `MAY\nWE PROCEED?` and every MAY case
   are unchanged).
   Other hits: `## May\nnothing shipped` (no digit on the next line) was the same regression one
   step further and is covered; `May` alone after a blank line too.
   Prevention: the docstring of `_is_month_line()` is the rule; keyline/README.md:215 states it in
   Honest limits; the two tests above pin both sides.

59. (R1) keyline/keyline_check.py:75, :80, :85 (version, CamelCase and number rules): two inputs
    the linear-time test does not cover are quadratic in `invariants()`: a dotted digit run that
    does not end at a boundary (`1.1.1…1_`: the version and number rules consume the run from
    every digit after a `.`, fail `R` at the end and backtrack; 16000 pairs 54 s, past the hook's
    30 s timeout) and a lower-upper letter run (`aAaA…A_`: the CamelCase rule rescans the tail from
    every split; 9.7 s). Pre-existing, 4x per doubling, the same on the pre-fix module.
    Reproduced. Medium. Class: catastrophic backtracking not covered by the linear-time test.
   Fixed: the version alternative's digit form and the whole number alternative carry `(?<!\d\.)`
   (keyline/keyline_check.py:81 and :91), so neither starts right after `<digit>.` and a dotted
   digit run that fails R at its end is scanned once from its first digit, not from every digit
   after a `.`. The CamelCase alternative is `[A-Z]*[a-z]+[A-Z][A-Za-z0-9]*`
   (keyline/keyline_check.py:86) instead of `[A-Za-z]*[a-z][A-Z][A-Za-z0-9]*`: one split per letter
   run (leading capitals, the first lowercase run, a capital) instead of one per lower-upper pair;
   it matches the same tokens (a letter prefix has a lower-upper adjacency iff its first lowercase
   run is followed by a capital). Both are plain regex, no 3.11+ syntax. The four inputs were added
   to the parametrized linear-time test
   `test_a_long_diacritic_or_hebrew_run_is_extracted_in_linear_time`
   (tests/test_keyline_check.py:413: `("1.", 16000, "1_")`, `("1.", 16000, "1é")`, `("aA", 16000,
   "_")`, `("aA", 16000, "é")`, units of 2 characters, 32 KB texts, ids `1.-16000-1_` etc.); all
   four failed first (the run of the targeted tests took 129 s) and pass now at 0.17 s, 0.12 s,
   0.006 s, 0.006 s.
   Other hits: the `é`-terminated twins (R fails on a Latin letter as on `_`) are the same shape and
   are in the test. The `(?<!\d\.)` guard also stopped the accidental number after a name glued to a
   dotted number (`Python3.12`, `python3.12`, `GPT4.5` gave `12`, `12`, `5` before; nothing after),
   so a swapped `Python3.12` passed; the upper, CamelCase, proper, snake, hash and identifier rules
   now take a dotted tail `(?:\.\d+)*`, so each is one token (as `v2.14.0` is), found by extraction;
   `test_a_name_glued_to_a_dotted_number_is_one_token` (7 tokens, failing first on all 7 against the
   guarded rules without the tails) pins it, with a sentence-end `Python3. 5` guard and a 16000-dot
   tail under 2 s (0.12 s). README (extraction paragraph and Honest limits: `Python3.12rc1` is
   nothing) and CHANGELOG say so. `v1.1.1...1_` starts at the `v` only. The comma form, the hash,
   snake, upper, proper and ident rules were checked (one start per run, or bounded by 200) and were
   already linear; the path/file alternatives still try from each inner digit but are bounded by
   their 200-character look-ahead, which is the 0.17 s left.
   Prevention: the parametrized test with a 2.0 s bound; the comment above INVARIANT
   (keyline/keyline_check.py:68-73) names both constructions; the guard test
   `test_camel_case_shapes_after_the_linear_rule` (tests/test_keyline_check.py:610-621: `fooBar`,
   `FooBar`, `ABcD`, `getHTTP2`, `aB`, `aAaAaA` camel; `ABc` nothing; `Abc` proper; `ABC` upper;
   `ab1` ident; `aAaA_` nothing) pins the equivalence (it passes on the old pattern too, as a guard;
   my first version expected `ABc` to be proper, which it never was, and was corrected).

60. (R1) keyline/README.md:55-56 (Honest limits, hex runs longer than 128 digits): "a digit-first
    one is nothing" is not what the code does when the letters all follow the digits: the number
    rule's `(?:%|[A-Za-z]+)?` suffix takes them and the run is a `number` token (`1` + 128 `a`);
    only a digit-first run with digits after a letter (`1a1a…`) is nothing. Low. Class: doc
    mismatch.
   Fixed: keyline/README.md:205 (Honest limits, hashes longer than 128 digits) now reads "a letter-
   first one is a lowercase identifier instead; a digit-first one is a number when all its letters
   follow the digits, `1aaa…`, and nothing when a digit follows a letter, `1a1a…`: none is a hash",
   which is what `invariants()` does (`'1'+'a'*128` -> number, `'1a'*65` -> nothing, `'a1'*65` ->
   ident, checked on the live module). No code change, so no failing-first test.
   Other hits: none; the CHANGELOG Docs bullet (CHANGELOG.md:21) stated nothing wrong and now names
   the digit-first case.
   Prevention: the sentence is the one place that states it; the reviewer's logic probe shape is
   reproducible from the report.

61. (R1) keyline/keyline_check.py:66-68 (comment above `INVARIANT`): "`ZürichAirport` is not
    extracted; neither is `richAirport`" contradicts the commit's own test and the README: it is
    extracted, as a proper noun; the comment means "not by the CamelCase rule". Low. Class: doc
    mismatch.
   Fixed: the comment above INVARIANT (keyline/keyline_check.py:68-73) now says "The CamelCase,
   snake_case, hash and identifier rules stay ASCII: `ZürichAirport` is taken by the proper rule,
   not by the CamelCase rule, and `xZürichAirport` yields nothing (`richAirport` is not a start:
   L)", matching tests/test_keyline_check.py:312 and keyline/README.md:210. The sentence about the
   rescan from every lower-upper pair was dropped, since finding 59 removed that rescan; the comment
   now describes the one-split form instead. No code change, so no failing-first test.
   Other hits: none; the README and the test already said the right thing.
   Prevention: the existing test `test_a_token_does_not_start_after_a_diacritic` asserts the
   behaviour the comment now describes.

## Self-check pass 3 (fresh-context pass over the fix commits e1ed25d and 014ca69)

Two reviewers who had not seen the findings above read only the pass 2 fix commits: R2 the
config/hook commit e1ed25d, R1 the keyline_check commit 014ca69. Every medium was
re-reproduced here with `python -I` (the folder-mode cases as uid 65534 in a copy under
/var/tmp, since root ignores file modes) before being accepted.
Counts: R2 findings 62-67: 0 high, 2 medium, 4 low; R1 findings 68-71: 0 high, 2 medium, 2 low;
72 (found while verifying 70): 0 high, 0 medium, 1 low; pass 3 total 0 high, 4 medium, 7 low; all
fixed class-wide in this PR.

62. (R2) config/uninstall.py:301-305: the pre-write state-tree check walked with `os.walk`, which
    swallows the listing error of a folder it cannot read or search, and tested `os.access(W_OK)`
    only, so a sub-folder (or `state/` itself) with mode 000, 333, 644 or 100 was never refused:
    the undo rewrote settings.json (with a backup) and deleted the hook, then stopped at `state/`
    on every run, the halfway shape the e1ed25d fix closed for mode 555 only. Reproduced as uid
    65534 (all six modes). Medium. Class: neighbour of the fixed input (an unreadable or
    unsearchable folder instead of a read-only one); halfway state.
   Fixed: config/uninstall.py:220 `_refuse_unremovable_tree(root)` replaces the old `os.walk` +
   `os.access(W_OK)` loop (called at config/uninstall.py:334, before the first write). It walks with
   `os.walk(root, onerror=unlistable)`; a folder that cannot be listed raises `"<folder> cannot be
   read; make it readable first"` (line 233, `error.filename or root`), a folder with entries that
   lacks write raises `"<folder> is read-only; make it writable first"` (line 236), and a folder
   with entries that is writable but lacks the search bit raises `"<folder> cannot be entered; make
   it searchable first"` (line 238). main's handler is unchanged, so the user sees `...; nothing
   written`. Deviation from the design: the search-bit case has its own message because a 0o644
   folder is writable, and "make it writable first" would send the user to the wrong chmod.
   Other hits: none; `_refuse_unremovable_tree` is the only pre-write check of the state tree, and
   `_remove_tree` (line 207) is the only remover. `install.py` never walks the state tree.
   Prevention: tests/test_uninstall.py:772
   `test_an_unlistable_or_unsearchable_state_folder_is_refused_before_settings_is_written`,
   parametrized over `sub` 0o000/0o333/0o644/0o100 and `state` 0o000/0o333; each asserts the mode-
   specific message, settings.json byte-equal, no `.bak-*`, hook present, and `state/sub/s1.json`
   still there after the chmod is restored. Skipped as root and on Windows. Failed before the fix on
   every parameter (uninstall went on to delete, or raised from inside rmtree after settings was
   written).

63. (R2) config/install.py:548 with config/uninstall.py:70: the interim record dropped the marker's
    `uninstalled` key but carried the leftover fields a marker holds for a key the uninstall left
    as is (`added_keys`, `replaced`, `installed`, `created`), so a re-install over such a marker
    interrupted at its final write left a record that read as a full one: the next uninstall undid
    only the leftover key and left `skillListingBudgetFraction` and the six deny tools in
    settings.json with no notice. Reproduced. Medium. Class: neighbour of the fixed input (a marker
    with leftovers instead of a clean marker); "absent is not empty".
   Fixed: config/install.py:515-516 `marker = bool(old_record.get("uninstalled"))`; `interim = {} if
   marker else {k: v for k, v in old_record.items() if k != "uninstalled"}`. Over a marker the
   interim record is `{}` or `{"claude_md": ...}` (line 568 still writes `dict(interim,
   claude_md=record["claude_md"])`), so the marker's leftover `added_keys`/`replaced`/`installed` no
   longer reach the interim record. The final record is still `_merge_record(old_record, record)`,
   so a live record keeps its earlier fields as before.
   Other hits: config/uninstall.py:167 `_leftover_record` only carries
   `added_keys`/`replaced`/`installed` when the record it reads holds them; before, a no-settings-
   data record (`{}` or `{"claude_md": ...}`) got empty lists invented, and `has_record` on the next
   uninstall took the marker for a full record (found in the adversarial re-read, scenario "second
   run").
   Prevention: tests/test_install.py:778
   `test_interrupt_at_the_final_record_over_a_marker_with_a_leftover_key_is_an_unfinished_record`
   (marker with two leftover keys, interrupt at the final record, record is `{"claude_md": ...}`,
   the next uninstall removes both template values with the no-settings-data notice, and the marker
   it leaves is exactly `{"uninstalled": true}`); the existing test at line 752 still passes. Failed
   before the fix: the interim record carried `added_keys`.

64. (R2) config/install.py:542-549: over a clean marker, when CLAUDE.md already equals the template
    no interim record is written at all, so an interrupt at the final record leaves the marker
    itself beside a settings.json holding the keys, the deny tools and the hook entry; the next
    uninstall reads the marker as neither unfinished nor absent and removes the keys silently,
    leaving the deny tools with no notice, the outcome finding 54 was meant to close. Reproduced.
    Low. Class: neighbour of the fixed input (the interim write skipped instead of carrying the
    marker); doc text not matching the code ("the run says so").
   Fixed: config/install.py:521-522: `if marker and not md_changed and (hook_changed or
   setting_changes): _write_json(paths["record"], interim)` writes the empty interim record before
   the hook (the run's first write). The docstring step 3 and closing paragraph say so (install.py
   docstring: "over the marker an uninstall leaves, when step 2 writes nothing, an empty interim
   record is written before step 1"; "holds no settings data of this run and nothing of an
   uninstall's marker").
   Other hits: the hook-only run over a marker (settings up to date, CLAUDE.md up to date, hook
   missing) had the same gap; the same branch covers it since `hook_changed` is in the condition. A
   run with nothing to write writes no record, as before (the marker stays, nothing happened).
   Prevention: tests/test_install.py:844 `test_interrupt_at_the_final_record_over_a_marker_without_a
   _claude_md_write_is_an_unfinished_record` (CLAUDE.md equals the template, interrupt at record
   write 2, record `== {}`, next uninstall removes the template values and notices "no settings
   data"); tests/test_install.py:817 `test_interrupt_at_the_final_record_over_a_marker_with_only_the
   _hook_to_write_is_an_unfinished_record` (`progress == ["hook written"]`, record `{}`). Both
   failed before the fix: the record was still the marker and the next uninstall said "nothing to
   undo".

65. (R2) config/uninstall.py:301-305: an empty read-only `state/` (or sub-folder) was refused with
    "is read-only; make it writable first" although removing it needs only its parent to be
    writable; the pre-fix code removed it. Reproduced as uid 65534. Low. Class: regression inside
    a fix (over-refusal with a clear message).
   Fixed: same function as 62, config/uninstall.py:235-238: the write and search checks are guarded
   by `(dirs or names)`, so an empty folder, whatever its mode, is not refused (rmdir needs only its
   parent). `_remove_tree` (line 207) then clears the read bit via `_clear_read_only` and rmtree
   removes it.
   Other hits: none; the old check also refused an empty read-only sub-folder, covered by the
   parametrization.
   Prevention: tests/test_uninstall.py:810 `test_an_empty_read_only_state_folder_is_removed`,
   parametrized over `state` and `state/sub` at 0o555, asserts the uninstall completes and the state
   folder is gone. Failed before the fix with "is read-only; make it writable first".

66. (R2) config/uninstall.py:202-208: `_remove_tree` cleared the Windows read-only attribute on
    files only, so a read-only sub-folder inside `state/` would stop `rmtree` after settings.json
    and the hook were written, as a read-only file did before e1ed25d. Not reproducible on Linux
    (no such attribute). Low. Class: neighbour of the fixed input (a folder instead of a file,
    Windows).
   Fixed: config/uninstall.py:207 `_remove_tree` now calls `_clear_read_only(Path(folder))` for the
   root and every folder `os.walk` yields, not only for the files, before `shutil.rmtree`. On
   Windows `RemoveDirectory` refuses a folder with the read-only attribute, which `os.access` never
   reports; on POSIX the chmod changes nothing a non-empty folder was not already refused for
   (docstring line 212).
   Other hits: none; `_clear_read_only` (skips symlinks, swallows OSError) is the only place the
   attribute is handled, and install.py never removes a tree.
   Prevention: tests/test_uninstall.py:831
   `test_read_only_files_and_folders_inside_the_state_folder_are_deleted` (renamed and extended):
   adds an empty `state/ro` with `S_IREAD|S_IEXEC`, records every `_clear_read_only` call, and
   replaces rmtree with a Windows-like one that refuses any file or folder without `S_IWRITE`;
   asserts `{state, state/"sub", state/"ro"} <= set(cleared)`. Failed before the fix on the `state`
   folder itself.

67. (R2) keyline/keyline_hook.py:78-84: the dotfile rule looked at the file name only, so a note
    under a dot-folder inside the watched tree (`notes/.trash/x.md`, Obsidian's trash) was linted
    and could block with exit 2, with or without `--watch notes/*`, where a shell glob would not
    descend into `.trash/`. Pre-existing. Reproduced. Low. Class: neighbour of the fixed input (a
    dot-folder instead of a dotfile).
   Fixed: keyline/keyline_hook.py:78 `_spells_dots(pattern, target)` returns True only when every
   dot component of the target (split on "/") has a pattern segment at the same index that starts
   with "."; `watched()` (line 89) picks `absolute` or `rel` per pattern, skips the pattern when
   `target is None or not _spells_dots(pat_n, target)`, then `fnmatch.fnmatchcase`. Without
   patterns, line 118 refuses any dot component of the relative path (`any(part.startswith(".") for
   part in rel.parts)`) before the notes/plans check. The old `path.name.startswith(".")` block is
   gone. `**` spells nothing: `notes/**` does not reach `notes/.trash/x.md`, as in a shell without
   globstar's dotglob.
   Other hits: `.DS_Store` and `notes/.gitignore` keep their old outcome (one dot component at the
   file name). A dot folder above the project root is not a component of `rel`, so a project checked
   out under `~/.work/proj` still gets its notes watched (the rule is on the relative path; an
   absolute pattern is matched against the absolute path and must spell those dots itself, which is
   what the reviewer's absolute-pattern case exercises).
   Prevention: tests/test_keyline_hook.py:282 `test_a_note_under_a_dot_folder_is_not_a_note`:
   `notes/.trash/x.md` with a bad header exits 0 with no pattern and with `notes/*`, `*`,
   `notes/*/x.md`, `notes/**`, `notes/**/x.md`, absolute `notes/*`; exits 2 with NOTE_HEADER for
   `notes/.trash/*`, `notes/.*/*`, `*/.trash/x.md`, `notes/.trash/x.md`, and the absolute note path;
   `watched()` checks for `notes/a/.b/c.txt` (not watched alone or with `notes/a/*/*`, watched with
   `notes/a/.b/*`). Failed before the fix on the no-pattern case and on `notes/*`, `*`,
   `notes/*/x.md`, `notes/**`.

68. (R1) keyline/keyline_check.py:87-94 (the `(?:\.\d+)*` tails added in 014ca69), keyline/README.md:57,
    CHANGELOG.md: the docs said a name that ends in a digit takes a dotted tail, but the regex took
    the tail after any upper, camel, proper, snake, hash or ident token, so an abbreviation glued to a
    number became one token: `No.5`, `Ch.2`, `Fig.3`, `Vol.3`, `A.1`, `Q3.2` yielded `No.5` etc.
    where the pre-commit checker yielded the number, which a rendering that writes `No. 5` or
    `מס' 5` keeps. A correct rendering failed with four misses. Reproduced. Medium. Class:
    regression inside a fix; neighbour of the fixed input (an abbreviation instead of a name ending
    in a digit); doc narrower than the code.
   Fixed: the six tails are `(?:(?<=\d)\.\d+)*`, so only a token that ends in a digit takes a tail;
   `No.5` is `No` (dropped at a sentence start, a plain proper noun elsewhere, R's `\.\d` look-ahead
   already failed it before the digit) and `5` is a number, as before 014ca69. The INVARIANT comment,
   keyline/README.md and CHANGELOG.md say so (`No.5`, `Fig.3`, `A.1` are the abbreviation and the
   number).
   Other hits: `Zürich.5` and `my_lib.5` (a Latin-letter proper noun, a snake name) are the same
   shape and are covered by the same change; the `Fig.3` case in
   `test_a_name_glued_to_a_dotted_number_is_one_token` was asserting the regression and is now
   `Node18.17`.
   Prevention: tests/test_keyline_check.py `test_an_abbreviation_before_a_dotted_number_keeps_the_number`
   (`No.5`/`Ch.2`/`Fig.3`/`Vol.3` against `מס' 5`/`פרק 2`/..., `A.1`, `Q3.2`, `Zürich.5`/`my_lib.5`;
   each asserts the number is the kept invariant and the rendering passes). Failed first with
   `missing: No.5, Ch.2, Fig.3, Vol.3`.

69. (R1) keyline/keyline_check.py:227-231 (proper nouns at a sentence start are skipped) with the
    `(?<!\d\.)` guards of 014ca69: the number rule no longer takes the `12` of `Python3.12`, and the
    proper rule takes the whole token, but a proper noun that opens a line or sentence is skipped in
    a source, so `Python3.12 is required at 14:02.` or `Fig.3 shows the drop.` at a line start lost
    the version entirely: a rendering with `Python3.11` or `Fig.4` passed where the pre-commit
    checker caught the `12`/`3`. The test avoided the sentence start. Reproduced. Medium. Class:
    regression inside a fix; test avoids the neighbour.
   Fixed: the sentence-start skip applies only to a capitalised word without a digit
   (`not any(c.isdigit() for c in tok)`): `Python3.12`, `Node18`, `Fig3` at a line start are kept,
   while `Server` at a line start is still furniture. keyline/README.md says a capitalised word with
   a digit at a sentence start is held to the rendering.
   Other hits: none; upper (`GPT4.5`) and ident (`python3.12`) were never skipped.
   Prevention: tests/test_keyline_check.py `test_a_name_with_a_digit_at_a_sentence_start_is_not_furniture`
   (`Python3.12 ...` vs `Python3.11 ...`, `Fig.3` with 68 applied is `3`, `Node18 is required`
   after `Done.\n`, `Art.5 GG applies` vs `Art.6`; each asserts the swapped token is missing and that
   `Server` at a line start is still not an invariant). Failed first with the rendering passing.

70. (R1) keyline/keyline_check.py:255-275 (`_is_month_line`, furniture sets `"#>-*+_ \t"` before
    and `"*_: \t"` after) and :284 (the `[ \t]+\d|:` test after `May`): a closed ATX heading
    `## May ##`, a bold label with the colon outside the bold `**May**: 3 fixed` and a bold month
    before a number `**May** 5 PRs` were still the modal (the trailing `#` is not in the after-set;
    the colon and digit tests did not see through `**`), so a Hebrew rendering (`## מאי ##`,
    `**מאי**:`) failed with "hedges lost". Pre-existing (the pass 2 fix covered `## May`,
    `**May**`, `May:` only). Reproduced. Low. Class: neighbour of the fixed input (a different
    Markdown marker around the same word).
   Fixed: `#` joins the after-set (`FURNITURE_AFTER = [*_:# \t]*`) and the colon/number test is
   `MONTH_AFTER = (?:\*{1,2}|_{1,2})?(?:[ \t]+\d|:)`, so a closing bold or underscore marker may
   sit between the month and the colon or the number. keyline/README.md lists `## May ##`,
   `**May**:` and `**May** 5`.
   Other hits: `**May** we proceed?` is still the modal (the question mark after the sentence),
   asserted in the same test.
   Prevention: tests/test_keyline_check.py `test_a_closed_heading_or_a_bold_month_before_a_colon_or_a_number`
   (`## May ##`, `**May**: 3 fixed`, `**May** 5 PRs`, `__May__: done`, each against a Hebrew
   rendering; `**May** we proceed?` keeps the hedge). Failed first with `hedges lost: possibility`.

71. (R1) keyline/keyline_check.py:202-209 (`_is_path`) with the path rule's `[\w.~/\\-]*` tail: the
    prose exception saw the token with its sentence period, so `and/or.` or `él/ella.` at the end of
    a sentence had `ella.` as its second part, not a plain word, and was kept as the path `él/ella`;
    a rendering that translates the pair failed. Pre-existing (the pass 2 test placed the pair
    mid-sentence only); the README sentence had no sentence-end caveat. Reproduced. Low. Class:
    neighbour of the fixed input (sentence punctuation after the pair); doc promises more than the
    code.
   Fixed: `_is_path` is given `tok.rstrip(".")`, the same stripping the kept token gets, so the
   pair is judged without its period. keyline/README.md says the pair is prose at the end of a
   sentence too, and that a dot inside (`notes/a_b.`) is still a path.
   Other hits: `and/or,` and `and/or:` were already prose (the tail stops at a comma or colon);
   `notes/a_b.` is still a path, asserted in the same test.
   Prevention: tests/test_keyline_check.py `test_a_prose_pair_at_the_end_of_a_sentence_is_prose`
   (`and/or.`, `él/ella.`, `כן/לא.` at a sentence end against a translated rendering, and
   `see notes/a_b.\nDone` still yields the path). Failed first with `missing: él/ella`.

72. (self, found while verifying 70) keyline/keyline_check.py:180-200, :240-275 (`_is_sentence_start`,
    `_all_caps_line`, `_is_month_line`) called from `invariants()` and `hedges()`: each call
    re-found the line around the match with `rfind`/`find` and sliced it, so a long line of many
    matching tokens was scanned once per token: 80,000 `**May**` on one line took 6.9 s, 20,000
    `MAY ` 12 s, growing with the square of the line. Reproduced. Low. Class: quadratic time
    (the shape the pass 2 linear-rule fix closed for the regex side, left open on the helper side).
   Fixed: a per-call `_Line` cache (the line bounds, its leading markers, its furniture end and its
   first two all-caps words found once per line) shared by the three helpers; a line's hedge-ending
   lookup is cached as before. `**May**` ×80,000: 0.31 s; `MAY ` ×20,000: 0.06 s; the fuzz of
   100,000 random texts (`fix7e/fuzz.py`) shows no difference from the pre-fix module beyond the
   intended 68-71 changes.
   Other hits: none; `invariants()` and `hedges()` are the only callers.
   Prevention: tests/test_keyline_check.py `test_a_line_of_many_tokens_is_scanned_once` (eight
   shapes: `**May**`, `May `, `MAY `, `- May`, `**Foo**`, `- Foo`, 100 bullets before `May`, and
   `WE MAY FAIL` lines; each under 1.5 s at 2,000-40,000 units, where the pre-fix module took 3-12 s
   on the slow ones).

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
