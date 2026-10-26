# Review of main d608788 (2026-10-26, sixth full pass)

Review of every source, config, test and doc file after PR #19 merged. Baseline on this tree:
pytest 209 passed, 2 skipped (one as root, one Windows-only), keyline suite 35/35 under `-I`
on Linux, Python 3.13.17, the JSON files parse, working tree clean. Two fresh-context reviewers
read the tree in parallel: A on keyline/, scripts/ and their docs (findings marked A), B on
config/, hooks/, tests/, CI and their docs (marked B). Their full reports and probe scripts are
in the scratchpad (`review6/a/report.md`, `review6/b/report.md`, not in the repo). All three
medium findings were re-reproduced here with `python -I` before being accepted (the install one
as user `nobody`, since root ignores file modes); the lows are quoted from the reviewers' own
probe output. The fixes landed in the same PR (#20); each finding below ends with what was
changed, the other hits of its class, and the prevention.

Status: all 11 fixed class-wide in PR #20 (merged as main 02e57bb), plus 3 findings of the
self-review of the diff; a check of those fixes found 3 more, fixed in PR #22
(pytest 241 passed, 4 skipped; keyline suite 35/35).
Counts: 0 high, 3 medium, 8 low. Every finding was CONFIRMED by
a run or is visible in the code as quoted. Line numbers are the reviewed tree's (main d608788).

Pattern across the pass: again mostly neighbours of earlier fixes. A filter written for `A`,
`I`, `A1` also drops `S3` and `Q4` (1); the fifth review's FIFO fix covered the open error but
not the blocking read (2); the "record last" rule protects uninstall from a failed install but
leaves the CLAUDE.md backup unrecorded when the failure comes after that write (3); the hook's
`except Exception` guard covers `file_path` but not `cwd` (6); `measure.py` got
`disallowed_special=()` and `plugin_cost.py` did not (7); the `errors="replace"` reads were
added but a missing path still tracebacks (8); and two doc sentences describe `--watch` as a
replacement for a rule it only narrows (9).

## High
None.

## Medium

1. (A) keyline/keyline_check.py:172: every all-caps token with exactly one letter is dropped by
   the filter meant for `A`, `I` and `A1`:
   `if kind == "upper" and len(re.findall(r"[A-Z]", tok)) < 2: continue`. So `S3`, `A100`,
   `H100`, `H264`, `P0`, `Q4` are never extracted and a rendering that changes them passes.
   Reproduced (re-run here): `check("bucket S3 at 14:02", "bucket GCS at 14:02")` -> ok=True,
   `invariants(...)` holds only `14:02`; likewise `A100`->`H100`, `H264`->`H265`, `P0`->`P1`,
   `Q4`->`Q3` all PASS. These are ordinary identifiers in incident and planning notes.
   Class: a filter wider than its target (neighbour of the `A`/`I`/`A1` exclusion).
   Test: unit, `check("bucket S3 at 14:02", "bucket GCS at 14:02").missing == ["S3"]`, the same
   for `Q4`, `P0`, `A100`; `A`, `I`, `As` still skipped; `check(line, line)` for each.
   Smallest fix: skip only the real non-identifiers, e.g. `re.fullmatch(r"[A-Z]s?", tok)`
   (keeps `A`, `I`, `As`; `A1` is then checked, the safer direction); update the comment and
   keyline/README.md if it lists the exclusion. Presence is tested by the same extraction, so
   the self-check invariant holds.
   Fixed: the filter is now `re.fullmatch(r"[A-Z]s?", tok)`: a lone letter and its plural
   (`A`, `I`, `As`) are skipped, every other all-caps token (`S3`, `A100`, `P0`, `Q4`, `H264`,
   and now `A1`) is an invariant. Tests: `tests/test_keyline_check.py`
   `test_a_one_letter_acronym_with_digits_is_an_identifier` (six tokens, extracted, pass against
   self, fail when replaced) and `test_a_lone_capital_letter_is_still_not_an_identifier`.
   Other hits: the only other kind filter with a count is the `snake` one two lines below
   (`"_" not in tok.strip("_")`), which is exact; `PROPER_STOP` is a word list, not a shape.
   Reviewer A's two fuzzers (20000 and 30000 random lines, three seeds each) still report 0
   self-check failures with the wider rule. Prevention: the test names the shape by example
   (one letter plus digits), so a later tightening of the rule fails it; keyline/README.md
   "Honest limits" now lists `S3` among the tokens that are extracted.

2. (A) keyline/measure.py:24-33 (`files_in`) and :57 (`read_bytes`): a FIFO under the measured
   folder hangs the run. `os.walk` lists the FIFO under `names`, `read_bytes()` blocks until a
   writer appears, so the `except (UnicodeDecodeError, OSError)` added by the fifth review
   (finding 9, whose text says "a file or a FIFO under the folder is a traceback" and whose
   "Fixed" block treats it as covered) never runs. Reproduced (re-run here):
   `mkdir m; printf 'hello\n' > m/a.txt; mkfifo m/pipe; timeout 10 python3 -I keyline/measure.py m`
   -> rc 124, no output. keyline/keyline_check.py:274 blocks the same way when the rendering
   argument is a FIFO. The hook is safe (`is_file()` is False for a FIFO).
   Class: fix narrower than its finding (the error path was handled, the blocking path not).
   Test: unit with `os.mkfifo` under a temp folder (skip on Windows), `files_in` returns only
   the regular file; CLI test that `measure.py` on that folder finishes.
   Smallest fix: in `files_in`, keep regular files only (`is_file()`, or `stat.S_ISFIFO`/
   `S_ISSOCK` on `lstat` if the dangling-symlink message in tests/test_measure.py must stay);
   in keyline_check.py's CLI an `os.path.isfile` check before `open` with the existing
   "no such file" message.
   Fixed: `measure.py` skips anything in a walked folder that is not a regular file before
   reading it, with one stderr line (`skip (not a regular file): pipe.txt`; a dangling symlink
   says `symlink to a missing target`). Test: `tests/test_measure.py`
   `test_a_named_pipe_in_a_folder_is_skipped_not_read` (mkfifo in the folder, run under a 30 s
   timeout, exit 0, the pipe named, the good file counted; skipped where `os.mkfifo` is missing).
   Decision on `keyline_check.py`: its CLI reads the paths it is given as written, including a
   pipe, because `keyline_check.py note.txt <(translate note.txt)` is a legitimate use (process
   substitution is a pipe) and the hook never hands it anything but a regular file
   (`path.is_file()` and `he.is_file()` are checked first). A pipe given on the command line
   is read on purpose, as `cat` would. Other hits: `scripts/usage_breakdown.py:144` and
   `scripts/unused_tools.py:21` now keep regular files only in their globbed lists (finding 8
   covers the folder case there); `scripts/lint_validate.py:34` globs `*.md` and reads inside
   `try/except OSError`, and a FIFO named `x.md` in a corpus folder would still block it (left:
   a corpus-building dev script, not a hook or an installer). Prevention: the walk-then-read
   pattern now has a test with a FIFO in it; the rule is "a walked path is read only when
   `is_file()`".

3. (B) config/install.py:405-438: when the settings.json write fails after CLAUDE.md was
   replaced (read-only settings.json as a non-root user, disk full, `.claude` not writable),
   the run exits 1 with the user's CLAUDE.md already replaced and no record written. The record
   is written last on purpose (:434-436), but it is the only place that links CLAUDE.md to its
   backup (:413-418). The next install, after the cause is fixed, finds `current_md ==
   claude_md` (:405) and records no `claude_md`; `uninstall()` then takes the branch at
   config/uninstall.py:260-263 ("CLAUDE.md matches the template but was not written by this
   install; left as is") and the user's file is never restored, although README.md:113 says
   the uninstaller restores the CLAUDE.md backup. Reproduced (re-run here as `nobody`,
   scratchpad `review6/b/probe1_failed_settings.sh`): run 1 `Error: [Errno 13] the file is
   read-only ...`, "Done before the error" lists the CLAUDE.md backup and update, exit 1, no
   install-record.json; run 2 exit 0 with a record without `claude_md`; uninstall prints the
   note and leaves the template in place, `CLAUDE.md.bak-<stamp>` orphaned. Each retry also
   creates a `settings.json.bak-*` right before the write fails (:428), one more orphan per try.
   Class: halfway state (a partial write leaves a file the record does not describe);
   neighbour of the "record last" fix.
   Test: make `_write_json` raise on the settings path (or chmod 444 as non-root), run
   `install()` twice, then `uninstall()`; assert CLAUDE.md is restored from the first backup.
   Smallest fix (either): pre-flight every write before the first one (refuse when
   `paths["settings"]` exists and is not writable, the same `os.access` test `_write_bytes`
   makes at :280-281, and the same for the CLAUDE.md, hook and record parents), which also
   stops the orphan settings backup; or write an interim record right after the CLAUDE.md
   write (`_merge_record(old_record, {"claude_md": ...})`) and the full one after settings. A
   record that names a CLAUDE.md backup but no settings keys makes uninstall restore CLAUDE.md
   and leave settings alone, which is correct.
   Fixed: `install()` writes the record twice when CLAUDE.md changes: once right after the
   CLAUDE.md write, holding only the `claude_md` entry merged into the old record, and the
   final one after settings.json as before. A settings write that fails after the CLAUDE.md
   write now leaves a record naming the backup, so the next install keeps that entry and
   uninstall restores it. The settings values are still recorded only once settings.json holds
   them: `tests/test_install.py::test_record_is_written_after_settings` now asserts that the
   record after a failed settings write holds no `added_keys`, `replaced`, `deny_added` or
   `installed` (it used to assert no record at all). New test:
   `test_a_failed_settings_write_after_claude_md_still_lets_uninstall_restore_it` (settings
   write fails, install again, uninstall, CLAUDE.md is back to "my own rules"). The pre-flight
   alternative was not taken: a disk-full or a folder appearing between the check and the
   write would still produce the halfway state, and the interim record covers every cause.
   Other hits: `config/add_to_repo.py` writes the hook before settings.json and has no record
   and no undo, so nothing is left unrecorded there; `config/uninstall.py` already writes its
   leftover record last and restores from the record it read. Prevention: README.md's write
   order sentence now says the CLAUDE.md change is recorded before settings.json is written.

## Low

4. (A) keyline/keyline_check.py:55 (`number` alternative): exponent and hex literals are not
   extracted and the sign is not part of the token. Reproduced: `invariants("limit 1e10")` ->
   {} (`1` is followed by `e`, so `R` fails), `invariants("mask 0x1f")` -> {};
   `check("limit 1e10 at 14:02", "limit 1e9 at 14:02")` -> ok; `check("mask 0x1f at 14:02",
   "mask 0x2f at 14:02")` -> ok; `check("temp -5 today", "temp 5 today")` -> ok; `check("delta
   +3", "delta -3")` -> ok. None of these is in the "Honest limits" list
   (keyline/README.md:163-180).
   Class: extraction gap documented nowhere (false PASS).
   Fix: either extend the alternative (`[-+]?\d+(?:[.,]\d+)*(?:[eE][-+]?\d+)?` plus a
   `0x[0-9a-fA-F]+` branch, keeping `R`; run the fuzzers and `check(line, line)` after), or add
   one line to "Honest limits" saying signs, exponents and hex literals are not compared.
   Fixed: the `number` alternative is now
   `0[xX][0-9a-fA-F]+|\d+(?:[.,]\d+)*(?:[eE][-+]?\d+)?(?:%|[A-Za-z]+)?`, so `1e10`, `2.5e-3`,
   `0x1f` and `0xDEADBEEF` are one invariant each (the hex alternative comes first so `0x1f`
   is not `0` plus letters). Signs stay outside the number: `[-+]?` before `\d` would turn
   `2020-2024` and `FY2024-25` into different tokens, and both are pinned by earlier tests.
   Test: `tests/test_keyline_check.py::test_an_exponent_or_hex_number_is_one_invariant` (four
   forms, extracted, pass against self, fail when replaced). The fuzzers (above) stay at 0
   self-check failures. Other hits: none; `number` is the only numeric alternative and
   `present()` looks numbers up by extraction, so the rendering side follows automatically.
   Prevention: keyline/README.md "Honest limits" names `1e10` and `0x1f` as extracted and says
   a sign is not part of a number.

5. (A) keyline/keyline_hook.py:161-163: `except OSError` prints "cannot read <note>" for errors
   that come from the tiktoken cache, not the note: a file named `cache` in the keyline folder,
   a read-only keyline folder, or an offline download (requests' exceptions derive from
   OSError). Reproduced (copy of keyline/ with `touch cache`): `keyline hook: cannot read
   <proj>/notes/a.txt: [Errno 20] Not a directory: '<kl>/cache/tiktoken'`, rc 1. The lint CLI
   says `error: [Errno 20] ...` (rc 2), which at least does not blame the note.
   Class: a catch-all whose message names one cause (same class as the fifth review's pre-merge
   finding 1).
   Fix: read the note in its own try (message "cannot read {path}") and let the lint/cache
   OSError fall to a second handler with "keyline hook: {e}"; the same split in keyline_lint
   `main` if wanted.
   Fixed: the hook loads the lint's word list (`keyline_lint.load_words()`) before the
   note is touched, in its own `try`, and reports an `OSError` or `TiktokenMissing` from it as
   `keyline hook: <error>` with exit 1. The `except OSError` around the lint and the check keeps
   `cannot read`, and adds the note's path only when the error does not already name a file
   (an allow file beside the note names itself). Test: `tests/test_keyline_hook.py`
   `test_a_word_cache_error_is_not_reported_as_the_note_being_unreadable` (in-process `main()`
   with `load_words` raising "is a folder"; exit 1, the cause printed, no "cannot read").
   Other hits: `keyline_lint.py main()` already loads the words in a separate `try` (lines
   257-261) and reports `error: <e>`; `keyline_check.py` has no cache. Prevention: the hook's
   `run_main` helper in the tests makes the next in-process hook test a few lines.

6. (A) keyline/keyline_hook.py:144-147: a non-string `cwd` in the event is a traceback, not
   exit 0. The `except Exception` at :142 guards only the `file_path` lookup; `cwd` is used
   unguarded in `os.path.abspath(root)` and `Path(event.get("cwd") or ".") / path`.
   Reproduced: `{"cwd":5,"tool_input":{"file_path":"/abs/proj/notes/a.txt"}}` -> TypeError in
   `abspath`, rc 1; with a relative file_path -> TypeError in `Path(5)`, rc 1. The docstring and
   README contract is "unknown or malformed events: exit 0".
   Class: neighbour of a previous fix (the guard covers `file_path` but not `cwd`).
   Fix: `cwd = event.get("cwd"); if not isinstance(cwd, str): cwd = None` once, used in both
   places; or widen the try at :142 to cover root and path construction.
   Fixed: `cwd = event.get("cwd")`, replaced by `"."` unless it is a non-empty string, and
   used for both the project root fallback and the relative `file_path`. Test:
   `tests/test_keyline_hook.py::test_a_cwd_that_is_not_a_string_is_ignored` (`"cwd": 5` with a
   relative path; exit 0, nothing on stderr). Other hits: `hooks/context_check.py:154` reads
   `transcript_path` with `or ""` and passes it to `Path`, which raises `TypeError` for a
   non-string too; the hook's `main` is wrapped in a catch-all that exits 0 (checked:
   `data.get("transcript_path") or ""` at :154, the guard at the call site), so it does not
   traceback. `event["tool_input"]["file_path"]` in the keyline hook is inside the
   `except Exception` guard already. Prevention: the rule for hook input is "every field read
   from the event is type-checked where it is read"; the two hooks now follow it for every
   field they use.

7. (A) scripts/plugin_cost.py:70 and the other `enc.encode` calls: a tiktoken special token in
   a SKILL.md description crashes the script. Reproduced: a plugin whose SKILL.md front matter
   holds `description: "uses <|endoftext|> marker"` -> `ValueError: Encountered text
   corresponding to disallowed special token '<|endoftext|>'`, rc 1. keyline/measure.py:38
   passes `disallowed_special=()` for exactly this. Also: :36 opens SKILL.md with
   `encoding="utf-8"`, not `utf-8-sig`, so a BOM-marked file's front matter is not recognised
   (description "") while the skill is still counted.
   Class: twin not given the same fix.
   Fix: `disallowed_special=()` on every `enc.encode` in plugin_cost.py; `utf-8-sig` at :36.
   Fixed: `disallowed_special=()` on the one `enc.encode` in `scripts/plugin_cost.py` (the
   docstring count, line 70); `desc_of` reads with `utf-8-sig`. Test:
   `tests/test_plugin_cost.py::test_a_description_with_a_special_token_or_a_bom_is_counted`.
   Other hits: `keyline/keyline_lint.py:162` encodes a single lowercase word (a chunk holding
   `<`, `|` or `>` is an identifier to the lint and never reaches it, and the call is inside
   `except Exception`); `keyline/measure.py` already passes `disallowed_special=()`;
   `scripts/tokentest.py:54` encodes its own fixed samples. The `.json` reads in
   `plugin_cost.py` (:56, :75) stay `utf-8`: `json.load` rejects a BOM either way, and both are
   inside `except (OSError, ValueError)`, so a BOM-marked manifest counts as empty rather than
   stopping the run (not changed: a manifest with a BOM is not valid JSON to Claude Code
   either). Prevention: the test holds the literal `<|endoftext|>`, the token that made
   tiktoken raise.

8. (A) scripts/toolresult_share.py:36, scripts/usertext_split.py:17, scripts/usertext_top.py:14:
   `open(path, ...)` on a missing path is a FileNotFoundError traceback, rc 1.
   scripts/usage_breakdown.py:66 and scripts/unused_tools.py:23: a directory named `x.jsonl`
   inside the transcript folder (matched by the glob) is an IsADirectoryError traceback, rc 1
   (usage_breakdown validates the folder argument itself, so this is its one unguarded read).
   Reproduced: `python3 -I scripts/usertext_top.py /nonexistent.jsonl`; `mkdir tr/x.jsonl;
   python3 -I scripts/usage_breakdown.py tr`.
   Class: unguarded read (neighbour of the `errors="replace"` fix).
   Fix: wrap the open in `try/except OSError as e: print(f"error: {e}", file=sys.stderr);
   return 1`, or skip non-files in the glob loop for the folder-reading scripts.
   Fixed: the three scripts open each transcript inside `try/except OSError` and exit 1 with
   `error: <e>` (the message names the path); `usage_breakdown.py` and `unused_tools.py` keep
   only regular files from their globs. Tests:
   `tests/test_transcript_scripts.py::test_a_missing_transcript_is_one_line_not_a_traceback`
   (all three scripts), `tests/test_usage_breakdown.py` and `tests/test_unused_tools.py`
   `test_a_folder_named_like_a_transcript_is_skipped`. Other hits: `scripts/lint_validate.py:65`
   already catches `OSError`; `scripts/plugin_cost.py:56`, `:75` and `:36` catch it;
   `scripts/unused_tools.py:62` reads the repo's own `user-settings.json`; `config/*` reads go
   through `_read_text`/`_read_bytes`, which turn the error into a `ValueError` naming the file.
   Prevention: the transcript-script test file now has one parametrized test per failure shape
   (usage, odd lines, empty input, missing file), so a fourth script added to `SCRIPTS` gets
   all of them.

9. (A) keyline/README.md:120-122 and keyline/keyline_hook.py:9: both say `--watch PATTERN`
   watches the matching files "instead", but the note-suffix rule (`NOTE_SUFFIXES`: .txt, .md,
   .keyline, no extension) still applies after a pattern match, so `--watch '*.rst'` never acts.
   Reproduced: the event for `<proj>/PROGRESS.rst` with `--watch '*.rst'` -> rc 0, no output;
   the same event for `PROGRESS.md` -> `PROGRESS.md:1:` findings, rc 2.
   Class: documentation that does not match the code.
   Fix: one clause in both places ("the pattern replaces the notes/plans rule only; the file
   must still be .txt, .md, .keyline or extension-less"), or drop the suffix check when patterns
   are given.
   Fixed: both sentences gained "the suffix rule still applies, so a watched `.py` file is
   passed over" (keyline/README.md step 2 and the hook's docstring). Test:
   `tests/test_keyline_hook.py::test_watch_patterns_do_not_lift_the_suffix_rule` (a watched
   `PROGRESS.py` exits 0 in silence, and both texts hold the clause). Other hits:
   `keyline/hooks-example.json` and `CLAUDE-snippet.md` do not describe `--watch`; the root
   README.md does not mention it. Prevention: the test counts the clause in both documents, so
   dropping it from one fails.

10. (B) config/install.py:408-418: a reinstall after `config/CLAUDE.md` changed leaves an orphan
    backup of the installer's own previous template. The record correctly keeps the first
    backup (:415), but :409 has already written a fresh `CLAUDE.md.bak-<stamp>` of template v1,
    and the install output reports it as "CLAUDE.md backup: ...", which reads as the user's
    file. Reproduced (scratchpad `review6/b/probe3_orphan_backups.sh`): install with a user
    CLAUDE.md, append a line to config/CLAUDE.md, install again, uninstall -> the first backup
    is restored and `CLAUDE.md.bak-<stamp2>` (template v1) stays behind.
    Class: neighbour of a previous fix (the record's first-wins logic was fixed; the backup
    made beside it was not).
    Fix: decide "is the current file ours" (the `old_md["sha256"] == text_hash(current_md)`
    test at :413-414) before calling `_backup` and skip the backup when it is ours, or unlink
    the fresh backup in that branch.
   Fixed: whether the current CLAUDE.md is still what the last install wrote (`sha256` in the
   old record equals the hash of the file) is decided before the backup, and no backup is made
   when it is: the first backup stays the one the record names. The record branch is
   unchanged otherwise (an old record without `sha256` still keeps its entry, and is still
   backed up, since the file could be the user's). Test: `tests/test_install.py`
   `test_reinstall_after_a_template_change_does_not_back_up_the_installers_own_file` (install,
   point `CLAUDE_MD` at a longer template, install again: "CLAUDE.md updated" without a
   "CLAUDE.md backup:" line, exactly one `.bak-*` and it holds the user's text). Other hits:
   settings.json is backed up on every rewrite by design (the record, not a backup, is what
   restores it; nothing names those backups); `config/add_to_repo.py` backs up the repo's
   settings.json the same way. Prevention: the test asserts the count of backup files, not
   just the change list.

11. (B) config/uninstall.py:107-110 and :132-133, with config/install.py:181-184 and :191-196:
    the uninstaller deletes `permissions`, `permissions.deny` and `hooks` whenever they end up
    empty, whether or not the install created them; `merge_settings` uses `setdefault` and does
    not record which containers existed. Reproduced (scratchpad
    `review6/b/probe2_odd_settings.sh`): `{"hooks": {}}`, `{"permissions": {}}` and
    `{"permissions": {"deny": []}}` each come back as `{}` after install and uninstall.
    Harmless to Claude Code (an empty container means the same as none), but it is the one case
    where the round trip is not an identity, which the record was introduced to guarantee.
    Class: round trip loses a user's key.
    Fix: record which containers `merge_settings` created (e.g. `record["created"] =
    ["permissions", "permissions.deny", "hooks", "hooks.UserPromptSubmit"]`) and let
    `undo_settings` delete only those; or never delete an empty container.
   Fixed: `merge_settings` records the containers it creates in `record["created"]`
   (`permissions`, `permissions.deny`, `hooks`, `hooks.<event>`), `_merge_record` carries the
   list across installs, and `undo_settings` deletes an emptied container only when the record
   lists it. A record without the list (an install from before this change) and the no-record
   mode keep the old behaviour and delete, since they say nothing either way: `_merge_record`
   writes the list only when the old record has one or there is no old record, so a re-install
   after a pull does not turn "unknown" into "created nothing" (self-review finding 1); the
   leftover record keeps the whole list whenever something is left as is, so a second run
   still knows who made the containers (self-review finding 2). Tests:
   `tests/test_uninstall.py::test_empty_containers_the_user_had_before_are_kept` (seed
   `{"permissions": {"deny": []}, "hooks": {"UserPromptSubmit": []}}`, install, uninstall,
   settings equal the seed) and `test_containers_the_install_created_are_removed`. Other hits:
   `config/add_to_repo.py:85-92` creates `hooks` and `hooks.<event>` with `setdefault` too, but
   has no undo, so nothing deletes them. Prevention: the round-trip test compares the whole
   settings object with the seed, so any other container the undo touches shows up.

## Observations, not findings

- hooks/context_check.py:132: a float `postTokens` prints "context about 200.0k tokens" and
  writes state `2.0`; the next prompt's `int("2.0")` (:167) raises, `last = -1`, and the
  reminder repeats on every prompt until the next assistant event. Claude Code writes integers;
  `int(... or 0)` would close it. (B)
- hooks/context_check.py:132-136: `compactMetadata`/`message` as a string, `usage` as a list
  or a non-numeric usage string -> caught by `main()`, one stderr line per prompt, exit 0. Not
  shapes Claude Code writes. Empty stdin -> JSONDecodeError logged as "unexpected error". (B)
- hooks/context_check.py:116-142: a last line larger than `IDEAL_UMBRELLA_TAIL_BYTES` (4 MB)
  makes the whole tail unparsable, so the state is cleared silently; documented in the module
  docstring. A warning when a non-empty transcript's tail yields no event would make it
  visible. (B)
- config/add_to_repo.py:172: `_write_json` lacks `ensure_ascii=False` (install.py:296 has it),
  so non-ASCII values are rewritten as `\uXXXX`; same JSON, less readable diffs. `.claude/hooks`
  being a file gives `Error: [Errno 17] File exists`, accurate but terse. (B)
- config/install.py:107-110 `_is_ours`: any hook command containing `context_check.py` is
  taken over and removed on uninstall, including a user's own checkout copy. By design. (B)
- A settings.json with a UTF-8 BOM is rewritten without the BOM; Claude Code reads both. (B)
- tests/test_source_rules.py:163-184 `_isolated`: combined short flags (`-IX utf8`, `-Ic`) are
  not split and `[sys.executable, *FLAGS, p]` returns False, over-matching in the safe
  direction; rule 2 accepts `errors="strict"` and a bare `except Exception` as decode handling
  and does not see `Path.open()`; rule 3 does not see `sys.stdout.write`; rule 1 does not see
  builtin `exit()`/`os._exit`. A grep of config/ hooks/ keyline/ scripts/ finds none of these
  forms, so the rules currently miss nothing. (B)
- .github/workflows/ci.yml:34-38: the runner prepends `$ErrorActionPreference = 'stop'` and
  `$PSNativeCommandUseErrorActionPreference = $true` to pwsh steps, so a non-final failing line
  of the multi-line `json.tool` step does fail the step; dropped as a finding. (B)
- Performance: a 5 MB note takes about 14 s in the hook and 7 s in keyline_check (linear;
  inside Claude Code's default hook timeout). (A)
- Hebrew: `'x could y'` -> `'x בעלול y'` loses the hedge (`ב` is not among the hedge prefixes
  ו/ש/וש/כש while CALENDAR accepts [ובלמהשכ]); arguably not a real inflection. (A)
- measure.py counts hidden files (the docstring says hidden folders are skipped; consistent with
  the code). usage_breakdown.py counts content blocks of duplicate message ids on every event,
  which is right for streamed events; a `text: null` block would TypeError at :93 but no real
  transcript has one. A non-UTF-8 note makes the hook's message repeat the path twice. (A)
- Symlinked note files and a `plans/` symlink to a folder outside the project are both linted
  (the path as written is checked first; design). (A)

## Checked and found correct

- Self-check invariant `check(line, line)`: an atom-based mixed-script fuzzer (3 seeds x 30,000
  lines) and a random-character fuzzer (3 seeds x 40,000 lines) -> 0 failures, 0 lines over
  50 ms. (A)
- keyline/README.md examples re-run exactly (PASS "17 invariants 4->4"; the FAIL example lists
  HTTP, UTC, 4 lost; the measure table; CLAUDE-snippet.md = 98 o200k tokens; the cache header's
  47,450 words matches the file). `--print-config` matches hooks-example.json. (A)
- Hook events: missing keys, a JSON list, empty or non-UTF-8 stdin, `file_path` an int -> rc 0
  silently; file outside the project -> 0; relative path against cwd; non-UTF-8 note -> rc 1
  with one line; `--watch PROGRESS.md` with CLAUDE_PROJECT_DIR != cwd -> rc 2 with a
  `PROGRESS.md:1:` finding; `.he.txt` sibling check; FIFO as the note -> 0. (A)
- Hebrew probes: calendar month names with every prefix, `May` as `MAY`, hedge class changes,
  negation counts, RLM/NBSP/ZWJ characters, list markers -> PASS/FAIL as intended. (A)
- measure.py: dangling symlink skipped with a message; empty folder -> header only, rc 0; FIFO
  given directly as the argument -> "no such file or folder", rc 2; BOM files decoded; special
  tokens in notes do not crash. keyline_check/keyline_lint CLI: directory argument -> `Is a
  directory` rc 2; missing file rc 2; exit codes 0/1/2 as documented. (A)
- keyline_lint.py: abbreviation rule, plural-of-one-token rule, numeronyms, BUILTIN_ALLOW,
  keyline-allow.txt lookup up the parents, atomic cache write, header-count rebuild on a
  truncated cache, TiktokenMissing hint without a traceback. (A)
- scripts/usage_breakdown.py: the RATES comment matches the current Opus 5.5 prices (input $4,
  output $20, cache read $0.20 per MTok; cache writes 1.25x and 2x); message-id dedup; nested
  `cache_creation` 5m/1h split and a null `cache_creation_input_tokens`; `abc`, `0` and a
  missing folder give messages, rc 1. scripts/tokentest.py names `claude-opus-5-5`. The other
  five scripts give the documented output on fixture transcripts and survive invalid UTF-8.
  requirements.txt pins tiktoken==0.14.0, matching the installed version. (A)
- install(): write order hook -> CLAUDE.md -> settings -> record; a failing read changes
  nothing (dangling-symlink pre-check for all four files; settings as a list, `deny: null`,
  `UserPromptSubmit: null`, `hooks: []`, `permissions: []` all refused with "nothing written",
  exit 1). `_write_bytes` writes through a symlink, keeps the mode, refuses a read-only target
  as non-root, cleans the temp file; `_new_temp` is identical in install.py, add_to_repo.py and
  keyline_lint.py:115. `_merge_record` first-wins, user-edit and template-change paths;
  `--force` recorded and restored. (B)
- verify(): paths, deny list, hook entry, interpreter resolution with `~`/`$VAR`, CLAUDE.md and
  hook content. `CLAUDE_CONFIG_DIR` as `~/cfg`, a relative path and with a trailing slash:
  install, verify, the hook's state folder and uninstall agree. (B)
- add_to_repo.py: symlinked settings written through the link, idempotent second run, dangling
  link / non-object / missing repo / no args refused with exit 1. (B)
- uninstall(): sibling hooks kept; only our deny entries removed; a non-list deny left with a
  notice; a partial failure (hook path is a directory) reports "Done before the error", keeps
  the record, and a second run finishes; symlinked `state/` and log unlinked without touching
  their targets; CLAUDE.md restore through `_write_bytes`; missing-backup branch keeps the
  file. (B)
- hooks/context_check.py: truncated last line skipped, CRLF, empty or garbage transcript,
  compact_boundary with and without `postTokens`, string usage numbers, sidechains skipped,
  non-object lines skipped, `session_id` sanitised, transcript path that is a directory,
  band logic, junk state file, invalid env ints, `hook_event_name` echoed; always exit 0. (B)
- Tests and CI: `umask_022` fixture pins the mode expectation; the scanner rules fire on
  crafted violations; `keyline/tests/run_tests.py:190` exits 1 on failure; `.gitattributes`
  keeps `cloud-setup.sh` LF; `pytest.ini` and `requirements-dev.txt` as documented. README.md
  :62-69 and :113-117 and the CHANGELOG head match the code, except as finding 3 qualifies
  README:113. (B)

## Could not check

- scripts/tokentest.py and config/verify-tokens.py end to end (they call the Anthropic API; no
  key, and runs that reach outside were not allowed).
- Windows (junctions, `shell_risk` quoting, cp1252 console, hook path handling): reasoned from
  the code only; CI covers the suites there.
- The "flags 87" corpus number in keyline/README.md (the corpus is not in the repo).
- Permission-denied paths in keyline (read-only keyline folder, unreadable note): the reviewer
  ran as root, which bypasses them; the install probe was run as `nobody` instead.
- Whether Claude Code accepts `"shell": "bash"` in hook entries, and whether
  `compactMetadata.postTokens` is always an integer in real transcripts.

## Self-review of the PR diff

A fresh-context pass over `git diff d608788..eea85ec` (the 11 fixes) found three defects in
the fixes themselves, all reproduced and fixed in the same PR; the rest of the diff, the
docs and the "Fixed:" claims were checked and found sound.

1. Medium, config/install.py `_merge_record`: a record from before `created` existed
   (`added_keys`, `deny_added`, `installed`, no `created`) was rewritten with `created: []`
   by any re-install that changed something (a hook or template change after a pull), and
   `uninstall.py` then read the empty list as "the install created nothing" and left
   `{"permissions": {"deny": []}, "hooks": {"UserPromptSubmit": []}}` where the pre-PR
   uninstall left `{}`; the finding 11 "Fixed:" claim above held only when the re-install
   wrote nothing. Class: a merge that defaults an absent, meaningful key to its empty value.
   Fixed: `created` is written only when the old record has it or there is no old record.
   Test: `tests/test_uninstall.py::test_reinstall_over_a_record_without_created_still_removes_the_containers`
   (install, delete `created` from the record, change the templates, install again, uninstall;
   settings are `{}`). Other hits: `added_keys`, `deny_added` and `installed` default to empty
   in the same function, but empty and absent mean the same for them (nothing to undo), so
   they are left. Prevention: the test covers the upgrade path, which the two container tests
   (fresh install only) did not.
2. Low, config/uninstall.py `_leftover_record`: `created` was carried into the leftover record
   only when `permissions.deny` was left as is, so after a first run that left a scalar value
   (the user changed `autoCompactWindow`) and kept the user's empty `hooks: {}`, a second run
   found no list, treated the container as unknown and deleted it. Fixed: the list is carried
   whenever anything is left as is. Test:
   `test_a_second_uninstall_run_still_keeps_the_users_empty_container` (seed `{"hooks": {}}`,
   install, change the value, uninstall, restore the value, uninstall; `{"hooks": {}}` stays).
   Other hits: none; `claude_md` is already carried on its own condition. Prevention: same test.
3. Medium, keyline/measure.py: the new `p.is_file()` check raised `PermissionError` for an entry
   in a folder that lists its names but cannot be searched (mode 0444 under a non-root user;
   `pathlib` re-raises every `OSError` but ENOENT/ENOTDIR/EBADF/ELOOP), a traceback where the
   pre-PR read gave `skip (cannot read: Permission denied)` and counted the rest. Class: a
   guard added before a guarded operation that is not itself guarded. Fixed: the stat is inside
   the same `except OSError` skip. Reproduced as uid 65534 before and after the fix; test:
   `tests/test_measure.py::test_a_file_that_cannot_be_stated_is_skipped_not_a_traceback`
   (skipped as root and on Windows). Other hits: `files_in()`'s `is_file()` on the argument
   itself and `keyline_hook.py`'s `path.is_file()` were claimed handled here and were not
   (both raised `PermissionError` as a traceback; see the check below, finding 3). Prevention:
   the test runs as the CI user, which is not root.

Not a finding, noted: the `where` suffix in the hook's `cannot read{where}` message is
unreachable (every `OSError` the block raises names the file), harmless; the measure
"symlink to a missing target" wording has no test asserting the string.

## Check of the self-review fixes

A fresh-context pass over b5b03eb (the only commit of PR #20 no reviewer had read) found
three defects, fixed in PR #22 the same way; everything else in that commit (the interim
record path, every measure.py entry kind, the new test as root, as CI's user and on Windows,
the docs) was checked and found sound.

1. Medium, config/install.py `_merge_record`: the self-review fix wrote `created` only when
   the old record had it or there was no old record, and a clean uninstall leaves the marker
   record `{"uninstalled": true}`, which is neither; so install, uninstall, install, uninstall
   (the normal cycle) dropped the list on the re-install and the second uninstall deleted the
   user's empty container. Class: "absent is not empty", second instance; the first fix tested
   emptiness of the record instead of the presence of install data. Fixed: the list is written
   unless the old record holds install data (`added_keys`, `replaced`, `deny_added`,
   `installed`) without `created`. Test:
   `tests/test_uninstall.py::test_reinstall_after_a_clean_uninstall_still_knows_what_it_created`.
2. Low, config/install.py `_merge_record` with config/uninstall.py `_leftover_record`: the
   leftover record carries the whole `created` list, including containers the uninstall just
   deleted; a re-install unioned it, so a container the user made by hand in between was
   recorded as the install's and deleted by the next uninstall. Fixed: over a record with
   `uninstalled` set, the re-install's own list replaces the old one (after an uninstall only
   the containers this install creates are its own; keeping an emptied one it did not create
   is harmless, deleting the user's is not). Test:
   `test_a_container_the_user_adds_between_uninstall_and_reinstall_is_kept`.
3. Low, keyline/measure.py `files_in()` and keyline/keyline_hook.py `main()`: the self-review
   section claimed both `is_file()` calls on the argument were handled; they were not, and a
   file named directly inside a folder that cannot be searched was a traceback from each
   (reproduced as uid 65534). Fixed: measure's main catches `OSError` next to
   `FileNotFoundError` ("error: cannot read <arg>: Permission denied", exit 2); the hook wraps
   the stat in the same "cannot read" handler, exit 1. Tests:
   `tests/test_measure.py::test_an_argument_that_cannot_be_stated_is_one_line_not_a_traceback`
   (skipped as root and on Windows) and
   `tests/test_keyline_hook.py::test_a_file_that_cannot_be_stated_is_one_line_not_a_traceback`
   (`Path.is_file` patched to raise, so it runs everywhere). Other hits: `keyline_lint.py`'s
   `load_allow` `is_file()` on parent folders is inside the lint's `OSError` handler in both
   entry points; `keyline_check.py` reads its arguments through `read()`, whose `OSError` is
   caught in `main`. Prevention: the report sentence that claimed the hits were handled is
   corrected above; a claim of "inside the handler" now needs the line of the `try`.

## Outside this task

- The findings above were fixed in PR #20 with the fix-the-class routine (failing-first test,
  name the class, search the whole repository, fix every hit, add a prevention) and a
  fresh-context self-review of the diff before the merge.
