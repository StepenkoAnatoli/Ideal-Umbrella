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
finding, added as the fixes landed).
Counts: 0 high, 7 medium, 28 low.

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

## Low

8. (V1) config/add_to_repo.py:152: `os.path.realpath(path)` writes through a symlinked
   `.claude/settings.json` or hook, but no test in tests/test_add_to_repo.py fails if it is
   removed (install.py's twin is pinned by `test_symlinked_settings_stay_symlinks`). Behaviour
   confirmed right by probe. Class: fix without test (sibling of first review 5).
   Test: `test_symlinked_settings_and_hook_stay_symlinks`. Smallest fix: add the test.

9. (V1) config/add_to_repo.py:154-170: the read-only refusal and the temp-file cleanup in
   `finally` are untested there; install.py's copy has two tests. Class: fix without test
   (sibling of fourth review 21). Test: `test_write_bytes_removes_the_temp_file_when_the_rename_fails`
   and `test_write_bytes_refuses_a_read_only_target` in tests/test_add_to_repo.py.
   Smallest fix: add the tests, or reuse `install._write_bytes`.

10. (V1) keyline/keyline_hook.py:183-185: a note that is not UTF-8 ends the hook with one line and
    exit 1, but no test drives the hook with such a note (third review 9 added tests for check and
    lint only); and `where` is empty for the note itself, so the line reads "cannot read: <path>
    is not UTF-8" with a stray colon. Class: fix without test (sibling of third review 9).
    Test: `tests/test_keyline_hook.py::test_a_non_utf8_note_is_one_line_and_exit_1`.
    Smallest fix: add the test; build the message without the colon when `where` is empty.

11. (V1) keyline/keyline_check.py:235: the Hebrew calendar form is accepted only `if kind ==
    "proper" or tok == "MAY"`, so `Due OCTOBER 3` (extracted as `upper`) against `Due באוקטובר 3`
    is reported as missing `OCTOBER`; the comment justifies the limit with `DEC`/`SAT`, which the
    full names are not. Fails closed. Reproduced (re-run here): `missing=['OCTOBER']`.
    Class: neighbour of a previous fix (fourth review 9/17).
    Test: `test_an_all_caps_month_or_weekday_accepts_its_hebrew_form`.
    Smallest fix: accept the form for an `upper` token longer than three letters that is in
    CALENDAR.

12. (V1) keyline/README.md:85: "Measured on 400 markdown files in gittoken (2026-10-18)" still
    names the one-machine corpus the second and third reviews removed everywhere else.
    Class: neighbour of a previous fix (docs). Smallest fix: "a 400-file markdown corpus".

13. (V2) keyline/measure.py:77-79: the per-file read handler is landed but no test fails when it is
    removed: `test_unreadable_file_is_skipped_not_a_traceback` uses a dangling symlink, which the
    later `is_file()` check (sixth review 2) now skips before the read. Confirmed by deleting the
    handler: the test still passes. Class: fix without test.
    Test: `tests/test_measure.py::test_a_file_that_cannot_be_read_is_skipped_not_a_traceback`
    (mode 000, skip as root). Smallest fix: add the test.

14. (B) config/uninstall.py:198-199: with settings.json absent at uninstall time, `undo_settings`
    never runs, `left` stays empty, and `_leftover_record` writes the bare marker, discarding
    `replaced` (the `--force` original) and `deny_added`; after the file is back, a later run only
    removes the hook entry. Reproduced: install `--force` over `{"autoCompactWindow": 123}`, move
    settings.json away, uninstall, move it back, uninstall -> 250000 stays.
    Class: absent is not empty. Test: `test_missing_settings_keeps_the_record_for_a_later_run`.
    Smallest fix: when settings is None, keep every recorded key in the leftover record and say so.

15. (B) config/uninstall.py:88: a key the user removed after a `--force` install is skipped in
    silence and its `replaced` value dropped from the record; README:113 says values you changed
    are "left alone and reported". Reproduced: no line about `autoCompactWindow` or 123.
    Class: absent is not empty. Test: `test_removed_replaced_key_is_reported`.
    Smallest fix: a notice naming the key and the earlier value.

16. (B) config/install.py:448-455: `_write_bytes(paths["claude_md"], ...)` runs before the interim
    record, so an interruption between the two leaves a template CLAUDE.md with no record of its
    backup; the next install records nothing and the uninstall says "not written by this install".
    Reproduced in-process (`_write_json` raising once). Class: halfway state (neighbour of the
    sixth review's interim-record fix).
    Test: `test_interrupt_before_the_interim_record_is_recovered_by_the_next_install`.
    Smallest fix: write the interim record before the CLAUDE.md write.

17. (B) config/install.py:338 `read_record` opens with `encoding="utf-8"` while `_read_json` uses
    `utf-8-sig`: a record saved with a BOM (a hand repair in a Windows editor, which the error
    message invites) is refused as "not valid JSON" by both scripts. Reproduced.
    Class: neighbour of a previous fix. Test: `test_record_with_a_bom_is_read`.
    Smallest fix: `utf-8-sig`.

18. (B) config/uninstall.py:161-170,263: `_backup_of` returns None for a backup name that is not a
    plain file name, and the `entry is not None` branch then deletes CLAUDE.md as if no backup had
    been made; the user's real backup stays on disk unmentioned. The two tests that cover this
    (`test_non_string_backup_name_in_record_does_not_crash`,
    `test_backup_name_with_a_separator_in_record_does_not_crash`) assert "CLAUDE.md deleted",
    pinning the wrong outcome. Reproduced. Class: test pins the wrong behaviour.
    Test: change both to assert the file stays and a notice names the bad name.
    Smallest fix: take the "backup is missing" branch when the record names a backup that
    `_backup_of` rejects.

19. (B) config/install.py:436-446: with a record from before `sha256` existed, a CLAUDE.md the user
    edited plus a template change takes the `"sha256" not in old_md` branch: the edits are backed
    up but the record keeps the first backup and the uninstall never mentions the second;
    README:113 does not hold for such records. Reproduced. Class: legacy record (one day of
    records). Test: `test_legacy_record_without_sha256_reports_the_second_backup`.
    Smallest fix: the "edits after the last install" notice, saying which backup the uninstall
    restores and naming the new one.

20. (B) config/install.py:14-16 docstring lists the steps in the reverse of the real write order
    (hook, CLAUDE.md, interim record, settings.json, record), which README:66 describes correctly.
    Class: doc drift. Smallest fix: reorder.

21. (A) keyline/keyline_check.py:80: `LIST_MARKER` strips `2024. ` and `503. `, so a line that
    starts with a year or status code and a full stop loses that number: `invariants("2024.
    Migration done")` -> `{}`. Reproduced (re-run here). Class: neighbour of the fifth review's
    "a number alone on a line is not a marker". Test: `test_a_year_that_starts_a_sentence_is_a_number`.
    Smallest fix: a list marker has at most three digits.

22. (A) keyline/keyline_check.py:48: a URL is extracted without its scheme (`//example.com/a/b`),
    so `https` -> `http` passes. Reproduced. Class: extraction edge case.
    Test: `test_a_url_keeps_its_scheme`. Smallest fix: a `url` alternative before `path`.

23. (A) keyline/keyline_hook.py:159: a dotfile written under notes/ is linted as an extension-less
    note (`Path(".gitignore").suffix == ""`): `notes/.gitignore` -> "furniture: header", exit 2;
    `notes/.DS_Store` -> exit 1. Reproduced. Class: absent is not empty.
    Test: `test_a_dotfile_under_notes_is_not_a_note`. Smallest fix: skip names starting with ".".

24. (A) keyline/keyline_hook.py:122-130: `--watch` without a value, `--watch ""` or a misspelt flag
    is silently ignored and the hook falls back to the notes/plans rule. Reproduced. Class:
    neighbour (keyline_lint's `main()` refuses `--allow` without a value).
    Test: `test_a_watch_flag_without_a_pattern_is_an_error` (exit 1, one line).
    Smallest fix: an error for a missing value and for any other `-` argument.

25. (A) keyline/keyline_hook.py:187: when only the rendering check fails, the header still says
    "this machine note breaks the Keyline rules; fix the file", pointing Claude at the wrong file.
    Reproduced. Class: halfway state of an earlier message change.
    Test: `test_a_failed_rendering_names_the_rendering`. Smallest fix: a second header when
    every problem is a FAIL/INCONCLUSIVE line.

26. (A) keyline/keyline_hook.py:35,94-105: only `.he.txt` is a rendering, so `notes/b.he.md` is
    linted as a note and its rendering looked for at `b.he.he.txt`; and `note_for` returns the
    first of four candidates, so with both `c.txt` and `c.md` beside `c.he.txt` the `.md` note is
    never checked and nothing says so. Reproduced. Class: neighbour (the note suffixes grew to
    four; the rendering suffix stayed one). Tests: `test_a_markdown_rendering_is_a_rendering`,
    `test_two_notes_for_one_rendering_are_reported`.
    Smallest fix: `.he.md` is a rendering too; more than one note is a reported problem.

27. (A) keyline/keyline_check.py:101,185: `"No. 5"` counts as a negation, so a Hebrew rendering
    `מס' 5` fails with "1 lost"; and a line-leading label `May:` is a possibility hedge while
    `מאי:` is not. Reproduced (re-run here). Class: extraction edge case.
    Tests: `test_number_sign_no_is_not_a_negation`, `test_month_label_may_is_not_a_hedge`.
    Smallest fix: `no` before an optional dot and a digit is not a negation; `May` before `:`
    is the month.

28. (A) keyline/measure.py:68-84: a file named on the command line that is not UTF-8 or cannot be
    read is "skipped" with exit 0 and the change line silently omitted (the skip path was written
    for walked folders), and an empty folder prints the header only. Reproduced. Class: neighbour
    of the sixth review's stat-error exit 2. Test: `test_a_named_file_that_cannot_be_counted_is_an_error`
    (exit 2). Smallest fix: return 2 after the report when an argv file was skipped.

29. (A) keyline/measure.py:30: a symlinked sub-folder inside a walked folder is skipped without a
    "skip" line (`os.walk` does not follow links) while a symlinked file is counted. Reproduced.
    Class: neighbour (the file case was handled). Test: `test_a_symlinked_folder_is_reported`.
    Smallest fix: print `skip (symlinked folder)` for each.

30. (A) scripts/usage_breakdown.py:66, scripts/unused_tools.py:23: the transcript is opened outside
    any try, so a file unreadable between the glob and the read is a traceback; the sixth review
    gave the three other transcript scripts "open in try, one line". VISIBLE.
    Class: neighbour of a previous fix. Test: `test_an_unreadable_transcript_is_one_line` in both
    test files (monkeypatched open). Smallest fix: the same try, one line.

31. (A) scripts/usage_breakdown.py:71-92: `usage` that is a list, `message.id` that is a list and
    `"text": null` each traceback, and a BOM drops the first line silently. Reproduced on
    one-line transcripts. Class: neighbour (`isinstance` was added for `event` and `message`
    only). Test: extend `test_non_object_lines_are_skipped`. Smallest fix: type checks and
    `utf-8-sig`.

32. (A) scripts/plugin_cost.py:106,103: the output write and `tiktoken.get_encoding` are
    unguarded, so an output path in a missing folder (and the first offline run) is a traceback;
    CHANGELOG:47 says the script "fails cleanly on a missing folder". Reproduced.
    Class: neighbour (the input folder got the check). Test: `test_missing_output_folder_is_an_error`.
    Smallest fix: try/except OSError around both, one line, exit 1.

33. (A) scripts/plugin_cost.py:48: `glob("**", recursive=True)` does not descend into hidden
    folders, so a plugin under a hidden intermediate folder is not counted. Reproduced.
    Test: `test_a_plugin_under_a_hidden_folder_is_counted`. Smallest fix: `include_hidden=True`.

34. (A) scripts/plugin_cost.py:40-46: a YAML folded or literal description (`description: >`)
    keeps the indicator as its first word. Reproduced. Class: absent is not empty.
    Test: `test_a_folded_description_drops_the_indicator`. Smallest fix: strip `>`/`|` indicators.

35. (A) keyline/README.md:144,92 and keyline/keyline_lint.py:153: the Honest limits do not mention
    non-ASCII names (4) or digests over 40 hex digits (3); and the allow-file rule "one per line"
    is not enforced: a line `mgmt srvc` becomes the single entry "mgmt srvc" that never matches,
    both words still flagged. Reproduced. Class: doc claim the code does not meet.
    Test: `test_allow_file_words_on_one_line_are_all_allowed`. Smallest fix: split the line on
    whitespace; the two doc lines.

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
