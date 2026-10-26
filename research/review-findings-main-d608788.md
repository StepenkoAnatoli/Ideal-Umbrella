# Review of main d608788 (2026-10-26, sixth full pass)

Review of every source, config, test and doc file after PR #19 merged. Baseline on this tree:
pytest 209 passed, 2 skipped (one as root, one Windows-only), keyline suite 35/35 under `-I`
on Linux, Python 3.13.17, the JSON files parse, working tree clean. Two fresh-context reviewers
read the tree in parallel: A on keyline/, scripts/ and their docs (findings marked A), B on
config/, hooks/, tests/, CI and their docs (marked B). Their full reports and probe scripts are
in the scratchpad (`review6/a/report.md`, `review6/b/report.md`, not in the repo). All three
medium findings were re-reproduced here with `python -I` before being accepted (the install one
as user `nobody`, since root ignores file modes); the lows are quoted from the reviewers' own
probe output. Nothing in the repo was changed by this pass.

Status: reported, not fixed. Counts: 0 high, 3 medium, 8 low. Every finding was CONFIRMED by
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

6. (A) keyline/keyline_hook.py:144-147: a non-string `cwd` in the event is a traceback, not
   exit 0. The `except Exception` at :142 guards only the `file_path` lookup; `cwd` is used
   unguarded in `os.path.abspath(root)` and `Path(event.get("cwd") or ".") / path`.
   Reproduced: `{"cwd":5,"tool_input":{"file_path":"/abs/proj/notes/a.txt"}}` -> TypeError in
   `abspath`, rc 1; with a relative file_path -> TypeError in `Path(5)`, rc 1. The docstring and
   README contract is "unknown or malformed events: exit 0".
   Class: neighbour of a previous fix (the guard covers `file_path` but not `cwd`).
   Fix: `cwd = event.get("cwd"); if not isinstance(cwd, str): cwd = None` once, used in both
   places; or widen the try at :142 to cover root and path construction.

7. (A) scripts/plugin_cost.py:70 and the other `enc.encode` calls: a tiktoken special token in
   a SKILL.md description crashes the script. Reproduced: a plugin whose SKILL.md front matter
   holds `description: "uses <|endoftext|> marker"` -> `ValueError: Encountered text
   corresponding to disallowed special token '<|endoftext|>'`, rc 1. keyline/measure.py:38
   passes `disallowed_special=()` for exactly this. Also: :36 opens SKILL.md with
   `encoding="utf-8"`, not `utf-8-sig`, so a BOM-marked file's front matter is not recognised
   (description "") while the skill is still counted.
   Class: twin not given the same fix.
   Fix: `disallowed_special=()` on every `enc.encode` in plugin_cost.py; `utf-8-sig` at :36.

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

9. (A) keyline/README.md:120-122 and keyline/keyline_hook.py:9: both say `--watch PATTERN`
   watches the matching files "instead", but the note-suffix rule (`NOTE_SUFFIXES`: .txt, .md,
   .keyline, no extension) still applies after a pattern match, so `--watch '*.rst'` never acts.
   Reproduced: the event for `<proj>/PROGRESS.rst` with `--watch '*.rst'` -> rc 0, no output;
   the same event for `PROGRESS.md` -> `PROGRESS.md:1:` findings, rc 2.
   Class: documentation that does not match the code.
   Fix: one clause in both places ("the pattern replaces the notes/plans rule only; the file
   must still be .txt, .md, .keyline or extension-less"), or drop the suffix check when patterns
   are given.

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

## Outside this task

- Nothing in the repo was changed by this pass; the findings above wait for a decision on
  whether to fix them (the fix-the-class routine of the earlier passes applies: failing-first
  test, name the class, search the whole repository, fix every hit, add a prevention, then a
  fresh-context self-review of the diff before any merge).
