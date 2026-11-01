# Review rounds for PR #26 (branch `learnings-and-savings-line`, base main b46792d)

The two ideas from the Trail-Code comparison: the learnings template and the savings line. Each round runs two fresh-context reviewers on the PR's head: a breaker agent (the `first-pass:breaker` plugin is not installed in this environment, so a general-purpose agent was given its brief: prove each finding with a repro, rank it, propose the smallest fix) and the `code-review` skill at effort high. A round is logged here before anything is fixed; the fixes and the next round follow after the user's go.

## Round 1 — head eb91ef6

Checks at that head: pytest 264 passed 4 skipped, keyline 35/35, the three JSON files parse (Linux). CI: Ubuntu green, Windows red (finding 1).

### code-review skill (11 findings, 2 confirmed by execution)

1. MEDIUM, CONFIRMED (CI run 40320657075, windows-latest). `tests/test_learnings.py:25` asserts no `\r` in the two learnings files, and `.gitattributes` pins only `*.sh` to LF, so the Windows checkout (core.autocrlf=true) turns `config/learnings.md` and `notes/learnings.md` into CRLF and both parametrizations fail. The same checkout makes `add_to_repo.py` copy a CRLF template into user repositories (it copies raw bytes), which the Keyline rule rejects. Planned fix: `.gitattributes` gets `*.md text eol=lf` (the root fix; the test stays as the guard).
2. MEDIUM, CONFIRMED against main's hook. `hooks/context_check.py:185` calls `_prompt_tokens()` outside the `try`, so a first main-chain assistant line whose usage holds a non-integer (`"input_tokens": "n/a"`) or is a list raises out of `run()`: the new hook prints only "unexpected error" and no JSON, while main's hook printed the hand-off note for the same transcript. Planned fix: compute the status line under its own handler (log the error, fall back to no line), so the cosmetic line can never take the hand-off note down; the per-line parse catches `(ValueError, TypeError, AttributeError)`.
3. LOW. `config/add_to_repo.py:256` writes the optional learnings copy between the hook and `settings.json`, so a `notes` file, an unwritable `notes/` or an uncreatable `notes/learnings.md` aborts the core install with the hook on disk and no hook entry. Planned fix: write the courtesy file last, after `settings.json`, so the core install is whole and "Done before the error" lists it; the in-the-way test flips its expectation.
4. LOW, CONFIRMED. `IDEAL_UMBRELLA_TAIL_BYTES` is parsed again in `floor_tokens()`: an invalid value warns and logs twice per prompt. Planned fix: parse once in `run()` and pass the limit to both readers.
5. LOW. The floor is immutable but recomputed from the transcript head on every prompt, even when `n == 0`. Planned fix: skip the floor read when there is nothing to show (`n == 0`); the read stops at the first main-chain call, normally within the first few KB, so the state-file cache is not taken (it would couple the floor to a file that is dropped below the threshold).
6. LOW. `config/add_to_repo.py:212` builds the "Commit ..." hint by sniffing change messages and names files not written this run (a repository that already had the hook and settings and now gets only the learnings file is told to commit all three). Planned fix: build the hint from `progress`, the list of files written this run.
7. LOW, style. `handoff_due()` reads as a predicate but writes the band state. Planned: rename to `record_handoff()`; the docstring already says it keeps the state.
8. LOW. `config/add_to_repo.py:231` checks `notes/learnings.md` for a dangling link but not `notes` itself (nor `.claude`, pre-existing): a dangling `notes -> /mnt/sync/notes` makes `_write_bytes()` realpath through it, create the missing folder and write the template outside the repository while reporting "notes/learnings.md written". Planned fix: the dangling-link check covers the parent folders too (`.claude`, `.claude/hooks`, `notes`).
9. LOW, docs. README quick start runs `git add .claude notes/learnings.md` unconditionally: it stages a pre-existing user file's edits, and fails when `notes/` is gitignored. Planned fix: "git add the files the script names".
10. LOW, docs. `keyline/CLAUDE-snippet.md` says to save learnings in `notes/learnings.md` unconditionally, while `config/CLAUDE.md` says "when the repo has it". Planned fix: the same qualifier in the snippet (token count in `keyline/README.md` updated).
11. LOW. Right after a compaction `now` is `compactMetadata.postTokens`, which leaves out the system prompt and tools, so the line can read "floor 40k, now 20k" until the next call. Planned fix: when the measure comes from a compact boundary the line says "now 20k after compaction" (the number is real; the suffix says why it is below the floor); `max(now, floor)` would invent a number.

### breaker agent (1 high, 2 medium, 6 low, each confirmed by a repro; report at scratchpad `breaker1/report.md`, outside the repo)

Four of its nine findings repeat code-review findings and take the same planned fix: HIGH-1 (Windows CRLF checkout, CI run 40320657075) is finding 1; LOW-3 (`IDEAL_UMBRELLA_TAIL_BYTES` warned and logged twice per prompt) is finding 4; LOW-5 (a dangling `notes` folder link is written through, the missing folder created where it points) is finding 8; LOW-6 (the commit hint names the two `.claude` files on a run that wrote only `notes/learnings.md`) is finding 6. The five others:

12. MEDIUM, CONFIRMED. The tests read the host environment. With `IDEAL_UMBRELLA_BASELINE=71000` set (the README now tells users to set it) `tests/test_install.py::test_generated_hook_command_runs_the_hook` and `tests/test_context_check.py::test_stdin_is_read_as_utf8_whatever_the_locale` fail: the line becomes `now 160k, 89k over baseline; over 150k` and the assertion looks for `now 160k; over 150k`. `IDEAL_UMBRELLA_TAIL_BYTES=abc` fails the three new tests that assert an empty stderr; `=1000` fails `test_floor_search_is_bounded_by_tail_bytes` and the pre-existing `test_tail_bytes_bounds_how_far_back_the_hook_reads`. `run_hook` pops only `IDEAL_UMBRELLA_BASELINE`; the in-process test has no isolation. Planned fix: an autouse fixture added to `tests/conftest.py` that deletes every `IDEAL_UMBRELLA_*` variable with monkeypatch, which covers the in-process tests; `run_hook` and the install test build their subprocess environment from `os.environ` with every `IDEAL_UMBRELLA_*` key removed before setting their own.
13. MEDIUM, CONFIRMED. `floor_tokens()` (`hooks/context_check.py:179-189`) reads and parses a whole line before `seen >= limit` is checked, so `IDEAL_UMBRELLA_TAIL_BYTES` bounds neither memory nor time: a transcript whose first line is 300 MB without a newline took 5.4 s and 911 MB resident (a real 2.1 MB transcript takes 40 ms; the old hook read at most 4 MB of the file end). A 1 GB line would pass the 15 s timeout of the repo hook entry, after which Claude Code drops the hook output. Contrived at the head of a transcript, but this is the first code path that can read the whole file. Planned fix: read with `f.readline(limit)`, so at most `limit` bytes are held at once; a record longer than the limit (a pasted file in the first prompt) is skipped, its rest consumed in `limit`-sized chunks without parsing, and the search goes on; the bytes of parsed records count toward the bound. This also closes 14.
14. LOW, CONFIRMED. A first record larger than the limit (a pasted file or image in the first prompt; 5 MB in the repro) ends the floor search, so the savings line never appears in that session and nothing says why. Planned fix: part of 13 (the oversize record is skipped and the search continues); a test with a 5 MB first line followed by a 40k call expects `floor 40k`.
15. LOW, CONFIRMED, not a regression. Above the threshold a failure inside `handoff_due()` (the state folder cannot be created: a regular file in its place in the repro) raises before anything is printed, so the user loses the savings line exactly when the context is large; below the threshold the line survives. Planned fix: together with finding 2, each of the two parts runs under its own handler: the status line falls back to no line and the hand-off check to "not due", each failure logged, and whatever is left is printed.
16. LOW, CONFIRMED. The three numbers are floored to thousands separately, so they do not add up on screen: floor 40,999, now 42,000, baseline 71,000 prints `floor 40k, now 42k, saved 30k vs baseline` (71 - 40 = 31). Planned fix: compute the saving from the rounded thousands (`baseline // 1000 - floor // 1000`), so the line agrees with itself; a test with floor 40,999 expects `saved 31k`.

Checked by the breaker and found correct (no action): the Keyline lint passes on both learnings files, CRLF copies included; the token counts 286, 148, 76 and 341 match the README and keyline/README claims; the cloud-setup.sh heredoc equals config/CLAUDE.md plus its cloud line; `handoff_due()` is a verbatim move of the old inline block; the hooks reference says `systemMessage` is shown to the user, and one JSON object without `additionalContext` adds nothing to the context (an `async: true` hook would deliver it to Claude; this hook is not async); this session's real transcript (2.1 MB, 105 calls) gives `floor 71k, now 166k` with the unchanged NOTE in 40 ms; sidechain-first, zero-usage, torn, non-JSON, BOM and non-UTF-8 lines are skipped; the baseline edge cases parse as documented; `add_to_repo.py` leaves an existing `notes/learnings.md` alone (`--force` included), writes through a `notes` folder symlink, and a `notes` file in the way gives one `Error:` line with "Done before the error".

### Round 1 total
16 unique items (11 from the code-review skill, 5 more from the breaker; 4 breaker findings overlapped). Fix order after the go: 1 (Windows CI, `.gitattributes`); the hook: 2 and 15 (own handlers), 4 (parse the limit once), 5 (skip the floor read when there is nothing to show), 7 (rename), 11 (compaction suffix), 13 and 14 (bounded floor read, oversize record skipped), 16 (rounded thousands); `add_to_repo.py`: 3 (learnings file written last), 6 (hint from `progress`), 8 (parent folders in the dangling-link check); tests: 12 (`tests/conftest.py`, env scrubbing); docs: 9 (README quick start), 10 (snippet qualifier, keyline/README token count). Then the three checks, the push, round 2 on the new head.

### Round 1 fixes (2026-10-31)
All 16 applied as planned. 1: `.gitattributes` `*.md text eol=lf`. Hook: 2/15 the savings line and the hand-off check each under their own handler (logged as "savings line:" / "hand-off check:"), the floor parse catches `(ValueError, TypeError, AttributeError)`; 4 `IDEAL_UMBRELLA_TAIL_BYTES` parsed once in `run()` (`tail_limit()`), passed to `last_measure()` and `floor_tokens()`; 5 no floor read when `n == 0`; 7 `handoff_due` -> `record_handoff`; 11 `last_measure()` returns `(tokens, compacted)`, the line says `now 20k after compaction`; 13/14 `floor_tokens()` reads with `readline(limit)`, an oversize record is skipped chunk by chunk and the search goes on; 16 saving from the shown thousands. `add_to_repo.py`: 3 learnings file written after `settings.json`; 6 commit hint built from `progress`; 8 dangling-link check covers `.claude`, `.claude/hooks`, `notes`. Tests: 12 `clean_env()` and an autouse fixture in `tests/conftest.py`; `run_hook` and the install test use `clean_env`. Docs: 9 README quick start says to add the files the script names (a comment, not a `<...>` placeholder that a shell would read as a redirect); 10 snippet qualifier, keyline/README 148 -> 153. New tests: saving rounding, compaction suffix, oversize first record (reads bounded by the limit), bad usage keeps the note, failing hand-off check keeps the line, invalid tail bytes warns once, commit hint for a learnings-only run, dangling folder links (3 params). Checks: pytest 274 passed 4 skipped (also with `IDEAL_UMBRELLA_BASELINE=71000 IDEAL_UMBRELLA_TAIL_BYTES=abc` and with `IDEAL_UMBRELLA_TAIL_BYTES=1000` set on the host), keyline 35/35, the three JSON files parse.

## Round 2 — head 49ecc6d

Checks at that head: pytest 274 passed 4 skipped, keyline 35/35, the three JSON files parse. CI: Ubuntu and Windows green (run 41230145951).

### code-review skill, high (9 findings; CR1 confirmed by execution)
- CR1 MEDIUM, CONFIRMED: `last_measure()` parsed usage outside any handler, so a non-integer usage on the newest main-chain record still lost the line and the note (on main too); the round-1 test put the bad records first. Fixed: per-record `_measure()` under `except (ValueError, TypeError, AttributeError)`, older records used.
- CR2 LOW: a learnings write failure still exits 1 on every run with no commit hint. Fixed (with B1).
- CR3 LOW: a hand-off check failure went only to the log. Fixed: also one stderr line.
- CR4 LOW: skipped oversize bytes did not count, so the floor scan's time was unbounded. Fixed (with B3).
- CR5 LOW: the resume point still said "nothing is fixed yet". Fixed: replaced in this round's commit.
- CR6 LOW, perf: floor re-read on every prompt. Rejected: round 1 decided against a state-file cache; the read stops at the first call, now also within 4 * limit.
- CR7 LOW: a baseline under 1000 shows as 0k. Fixed: warning, ignored.
- CR8 LOW: commit hint sliced " written" off messages. Fixed: `progress` holds paths; the messages add " written".
- CR9 LOW, style: `context_tokens()` is only a wrapper. Rejected: the stable entry point the tests and the docs use.

### breaker agent (7 findings, each with a repro; the agent could not write its report file, so its findings are summarized here)
- B1 LOW-MEDIUM = CR2. Fixed: the learnings write is under `except OSError` -> `note: notes/learnings.md not written (...)`, exit 0, left out of the hint; the in-the-way test now runs twice and expects exit 0 both times.
- B2 LOW = CR1.
- B3 LOW = CR4: 1 GiB of oversize records took 1.67 s. Fixed: the scan stops at `f.tell() >= 4 * limit`, docstring says so.
- B4 LOW: `IDEAL_UMBRELLA_TAIL_BYTES` below the first turn's size hides the line. Docs only (README and hook docstring): lowering it is the user's choice, and the bound is what the setting is for.
- B5 LOW, docs: the floor includes the first message. Fixed: one sentence in the README and the hook docstring.
- B6 LOW: a gitignored `notes/` got the copy and the hint named it. Fixed: `git check-ignore` (git missing or not a repo: not ignored) -> no copy, a `note:`.
- B7 VERY LOW: "longer than limit" vs a skip at exactly `limit` bytes. Fixed: docstring says "`limit` bytes or more".

### Round 2 fixes
Tests added: bad usage in the newest record, floor scan bound at 4 * limit (near and far), baseline under 1000, notes file in the way (exit 0 twice), gitignored notes; the failing-hand-off test also checks stderr; the oversize test's record is 10 KB (inside the new bound). Checks: pytest 278 passed 4 skipped (also with `IDEAL_UMBRELLA_BASELINE=500 IDEAL_UMBRELLA_TAIL_BYTES=abc` on the host), keyline 35/35, the three JSON files parse.

## Round 3 — head 8ce006d

Checks at that head: pytest 278 passed 4 skipped, keyline 35/35, the three JSON files parse. CI: Ubuntu and Windows green.

### code-review skill, high (10 findings, none repeating rounds 1-2; details at scratchpad `review-round3-findings.json`, outside the repo); all accepted, planned fixes:
- R1 MEDIUM, CONFIRMED: usage `1e400`/`Infinity` -> `int(inf)` raises OverflowError, not caught by `last_measure()`'s handler: the note is lost. Fix: add OverflowError to both handler tuples (`last_measure`, `floor_tokens`).
- R2 MEDIUM, CONFIRMED: a compact boundary whose `postTokens` is not a number is skipped and the scan reads pre-compaction usage (`now 200k`, a false hand-off note). Fix: a boundary always ends the scan; unparsable `postTokens` -> `(0, True)`. The round-2 test that ends in a bad boundary is split: bad usage last (falls back), bad boundary last (0, no line).
- R3 LOW, CONFIRMED: negative usage -> `floor -5k`. Fix: `max(0, ...)` on each term in `_prompt_tokens`.
- R4 LOW, docs: README (lines 120, 132) and the hook docstring say the floor is looked for within `IDEAL_UMBRELLA_TAIL_BYTES`; the code reads up to 4 * limit. Fix together with R8: one bound, `f.tell() < 4 * limit`, and the docs say "within 4 times IDEAL_UMBRELLA_TAIL_BYTES of the start"; `test_floor_search_is_bounded_by_tail_bytes` uses a limit of 1000.
- R5 LOW: a gitignored `.claude/` still gets the hook and settings and the hint names them. Fix: `_git_ignores` checked for every path written; an ignored core path gets a `note:` (written all the same: the local session still uses it).
- R6 LOW: `_git_ignores` reads git exit 128 (dubious ownership, GIT_DIR set) as "not ignored". Fix: returns True (0) / False (1) / None (other, git missing); None -> a note that git could not say, the file is copied.
- R7 LOW, simplification: `learnings_missing` reused as a "written" flag; `files = progress` alias. Fix: append the change line next to `progress.append` inside the try; use `progress` directly.
- R8 LOW, simplification: two overlapping bounds in `floor_tokens` (`seen` and `f.tell()`). Fix: one position bound (with R4).
- R9 LOW, test: the notes-in-the-way test never asserts the first run's commit hint. Fix: assert it on run 1.
- R10 LOW, resume point counts: round 2 had 3 overlaps (B1=CR2, B2=CR1, B3=CR4), 13 unique items: 10 fixed, 2 rejected, 1 docs only. Fix: corrected in the resume point.

### breaker agent (5 findings, 3 low and 2 very low; no high or medium; 2 repeat code-review)
F4 (first run's commit hint never asserted) is R9; F5 (bad `postTokens` falls back to pre-compaction usage) is R2. New, all accepted, planned fixes:
- R11 LOW, CONFIRMED by mutation: the `f.tell()` bound inside the skip loop has no test (removing it keeps 278 passing; a 1 GiB record goes 0.03 s -> 7.68 s). Disappears with R8 if the single position bound is checked per chunk; test: the `Spy` on one record of 10 * limit bytes (limit 1000), `assert sum(reads) < 5 * 1000`.
- R12 LOW, CONFIRMED: a dangling `notes` or `notes/learnings.md` link is still a hard error (exit 1, nothing written), against the courtesy rule, even when git ignores `notes/`. Fix: only `.claude`, `.claude/hooks`, settings.json and the hook stay in the raising loop; for the two learnings paths a dangling link means no copy and a `note:` "notes/learnings.md not copied: <p> is a symlink to a missing target"; the `notes` and `notes/learnings.md` params of the two dangling-link tests expect exit 0, the note, the `.claude` files, and still nothing created under `gone`.
- R13 LOW, Windows only (reasoned and simulated on Linux, not run on Windows): `_git_ignores` uses `capture_output=True, timeout=10`; on timeout CPython's Windows branch calls `communicate()` without a timeout, so a git child holding the pipes outlives the bound. Fix: `stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL` (only the exit status is used).
Checked and found correct by the breaker: floor_tokens boundaries (exact-limit records with and without newline, EOF in the skip loop, limit=1, outer bound covered), the last-record fallback, rounding, compaction suffix, baseline under 1000, separate handlers, `_git_ignores` non-repo and git-missing paths, notices vs `progress` vs "Done before the error", conftest scrubbing, `.gitattributes`, the four token counts.

### Round 3 total
13 unique items (R1-R13). Fix order: hook R1, R2, R3, R8+R4+R11 (one position bound, docs, skip-loop test); `add_to_repo.py` R12, R5, R6, R13, R7; tests R9; resume point R10. Then the checks, push, round 4.

### Round 3 fixes (2026-10-31)
All 13 applied. Hook: R1 OverflowError in both handler tuples; R2 a compact boundary always ends the scan, an unreadable `postTokens` is `(0, True)` (the round-2 test's last record is now an `inf` usage; a new test ends in a bad boundary: no line, no note); R3 `max(0, ...)` per term, and on `postTokens`; R8/R4/R11 one bound in `floor_tokens()`: `f.tell() < 4 * limit`, checked per chunk in the skip loop, `seen` gone; README and docstring say "within 4 times `IDEAL_UMBRELLA_TAIL_BYTES` of the start"; the bound test uses 1000; the skip-loop test (one 10 KB record, limit 1000, `sum(reads) < 5000`) fails when the per-chunk check is removed (mutation run). `add_to_repo.py`: R12 only `.claude`, `.claude/hooks`, settings.json and the hook raise on a dangling link; on `notes` or `notes/learnings.md` it is a `note:`, exit 0; R5 every written core path is checked with `_git_ignores`: an ignored one is written, gets a `note:` and is left out of the hint; R6 `_git_ignores` returns True/False/None: a folder with no `.git` entry at or above it is False without running git (no note outside repositories), git missing, a timeout or an exit other than 0/1 is None, which gives a "git could not say" `note:` and the file is written; R13 stdin/stdout/stderr to DEVNULL; R7 `copy_learnings` is only "copy it", the change line is added after the write succeeds, the hint is built from `progress` less `ignored`. R9 the notes-in-the-way test asserts the first run's hint. R10 was already right in the resume point (3 overlaps, 13 unique: 10 fixed, 2 rejected, 1 docs only). New tests: inf usage, bad boundary, negative usage, skip-loop bound, dangling learnings links (2 params), ignored `.claude/`, git exit 128 (POSIX, a fake git on PATH), no git note outside a repository. Checks: pytest 284 passed 4 skipped (also with `IDEAL_UMBRELLA_BASELINE=500 IDEAL_UMBRELLA_TAIL_BYTES=abc`), keyline 35/35, the three JSON files parse.

## Round 4 — head d64316b

Checks at that head: pytest 284 passed 4 skipped, keyline 35/35, the three JSON files parse. Reviewers told to skip rounds 1-3.

### code-review skill, high (10 findings; C1-C3 confirmed by execution; details at scratchpad `review-round4-findings.json`, outside the repo)
- C1 LOW-MEDIUM, CONFIRMED: a symlinked `.claude`, `.claude/hooks` or `notes` folder: `git check-ignore` exits 128 ("beyond a symbolic link"), the note says git could not say, and the hint names paths `git add` refuses; files outside the repository never reach cloud sessions.
- C2 LOW, CONFIRMED: RecursionError (one record nested 100000 deep) is not in the handler tuples: the note is lost.
- C3 LOW, CONFIRMED: the git tests read the host's git config and environment (a global excludes file, GIT_DIR).
- C4 LOW: with git unable to answer and a `notes` file in the way, one note says "written all the same", the next "not written".
- C5 LOW: the hand-off failure goes to stderr, which Claude Code shows for an exit-0 hook only in verbose mode.
- C6 LOW: the resume point was only partly replaced after round 3.
- C7 LOW: `_in_git_repo` ignored GIT_DIR and GIT_CEILING_DIRECTORIES.
- C8 LOW, simplification: the exception tuple written three times, the clamp four.
- C9 LOW: `IDEAL_UMBRELLA_BASELINE=0` warned on every prompt.
- C10 LOW, efficiency: up to three git spawns, each with its own 10 s timeout.

### breaker agent (no high or medium; 5 findings, the agent's report in its reply)
- B1 LOW = C1 (repro: `notes -> docs` inside the repo, `.claude/hooks -> outside`).
- B2 VERY LOW: the "git ignores it" note only on the run that writes the file; a second run said "already up to date".
- B3 LOW, test gap: mutations survive: no clamp on `output_tokens` or `postTokens`, OverflowError dropped from `floor_tokens`.
- B4 LOW, test gap: no test with `.git` as a file (worktree, submodule): `exists` -> `isdir` survives.
- B5 VERY LOW: the oversize-record branch in `floor_tokens` is near-dead (`readline(limit)` never returns more than `limit`; the outer bound already bounds reads; pieces do not parse).

### Round 4 fixes
All 15 accepted (14 unique). Hook: C2/C8 one `BAD_RECORD` tuple (RecursionError added) and one `_count()` helper for every usage number; B5 the oversize branch dropped, the docstring says such a record is read in `limit`-sized pieces that do not parse; C9 0 turns an off-by-default setting off without a warning; C5 a hand-off failure is also appended to the systemMessage. `add_to_repo.py`: C1/B1 `_repo_path()` resolves where each file really lands: outside the repository -> a `note:` and out of the hint (the learnings file not copied); inside -> git is asked by that real path and the hint names it; C10 one `git check-ignore -z --stdin` call before any write, input and output through temp files (no pipes, R13 kept); B2 both core files are checked on every run, not only when written; C4 the "could not say" note no longer claims a write and is given for the learnings file only after it is written; C7 `_in_git_repo` honours GIT_DIR and GIT_CEILING_DIRECTORIES. Tests: C3 `git_env()` strips GIT_* and the global and system config and excludes file, used by `run()` and every `git init`; B3 inf in the floor scan, negative output, negative postTokens (each mutation now fails a test); B4 a worktree (`exists` -> `isdir` now fails); deep nesting; symlinked `notes -> docs`; files outside through symlinks; GIT_DIR; the second-run note; the contradiction case. C6 the resume point is replaced in full. Checks: pytest 290 passed 4 skipped (also with `IDEAL_UMBRELLA_BASELINE=500 IDEAL_UMBRELLA_TAIL_BYTES=abc GIT_DIR=/nonexistent`), keyline 35/35, the three JSON files parse.

## Round 5 — head a6550dd

Checks at that head: pytest 290 passed 4 skipped, keyline 35/35, the three JSON files parse. Reviewers told to skip rounds 1-4.

### code-review skill, high (9 findings; D1 confirmed by execution; details at scratchpad `review-round5-findings.json`, outside the repo)
- D1 LOW-MEDIUM, CONFIRMED: `_git_ignored` encoded paths as strict UTF-8; a `notes` link to a folder whose name is not UTF-8 aborted the whole install ("nothing written").
- D2 LOW: the hand-off failure was appended to the systemMessage on PostToolUse too, so it repeated after every tool call.
- D3 LOW: the failure message pointed at a log that `log()` could not write either.
- D4 LOW: for a file reached through an in-repo symlink the hint never named the link.
- D5 LOW: `_in_git_repo()` re-implemented git's discovery (GIT_DIR, ceilings) and could disagree with it.
- D6 VERY LOW: README still described the dropped oversize skip.
- D7-D9 LOW, simplification: a `files` alias, an over-built `asked` filter, realpath computed twice.

### breaker agent (no high or medium; 6 findings, the agent's report in its reply)
- E1 LOW-MEDIUM = D4, wider: a link on `.claude`, `.claude/hooks` or `notes` was neither named in the hint nor asked of git, so an ignored `.claude` link gave a confident, wrong hint.
- E2 VERY LOW = D1, plus a second case: a surrogate-escaped path in a note crashed the print after the writes (strict UTF-8 stdout), losing the hint, exit 1.
- E3 LOW, test gap: the GIT_CEILING_DIRECTORIES branch of `_in_git_repo` survived mutation. Moot: D5 removed the function.
- E4 VERY LOW: a path starting with ":" is read by `check-ignore --stdin` as pathspec magic (wrong answer, or exit 128 for all paths).
- E5 VERY LOW, test gap: the `n and` guard before the floor read survived mutation.
- E6 VERY LOW, rejected as out of scope: running the script on a subfolder of a repository installs where cloud sessions do not look. Behaviour already on main, not in this diff.

### Round 5 fixes
All accepted except E6 (out of scope) and E3 (moot). Hook: D2 the failure goes into the systemMessage on UserPromptSubmit only (stderr and the log always); D3 `log()` returns whether it wrote, else the message carries the error type and text. `add_to_repo.py`: D1/E2 paths go to git as file-system bytes (`os.fsencode`/`os.fsdecode`, ValueError in the handler), stdout and stderr use `errors="backslashreplace"`; D5 `_in_git_repo` dropped: exit 128 with "not a git repository" (LC_ALL=C) means no repository; E4 paths go to git as `./<path>`; D4/E1 `_links()` finds each symlink on the way to a file by its own repo path; the links are asked in the same git call; a link git ignores gives a `note:` on every run and keeps the file out of the hint (learnings not copied); otherwise the hint names the link with the file (the "commit the link too" note is gone); D6 README; D7-D9 simplified. Tests: a non-UTF-8 folder name, the `.claude` link in the hint, an ignored link (both runs), a ":" folder, `notes -> docs` hint with the link, no floor read with no usage (E5), PostToolUse quiet on failure, unwritable log. Each new guard was mutation-checked (reverting it fails a test). Checks: pytest 297 passed 4 skipped (also with `IDEAL_UMBRELLA_BASELINE=500 IDEAL_UMBRELLA_TAIL_BYTES=abc GIT_DIR=/nonexistent`), keyline 35/35, the three JSON files parse.

## Round 6 — head 3c92b83

Checks at that head: pytest 297 passed 4 skipped, keyline 35/35, the three JSON files parse. Reviewers told to skip rounds 1-5.

### code-review skill, high (10 findings; G1-G3, G5 confirmed by execution; details at scratchpad `review-round6-findings.json`, outside the repo)
- G1 LOW-MEDIUM, CONFIRMED: "not a git repository" also matches a broken GIT_DIR or stale .git file ("...: '/nonexistent'"), read as no repository: a confident hint naming ignored files.
- G2 LOW, CONFIRMED: `_links()` did not follow a link to a link; an ignored middle link (`notes -> mid -> docs`) went unnoticed and unnamed.
- G3 LOW, CONFIRMED: a link with an absolute target was hinted as safe to commit; it dangles in a clone at another path.
- G4 LOW: `main()`'s unexpected-error path still said "details in <log>" when the log was not written.
- G5 VERY LOW, CONFIRMED: a link shared by both `.claude` files gave the same "could not say" note twice.
- G6 VERY LOW: the learnings note blamed `learnings.md` when the ignored thing was the `notes` link.
- G7 VERY LOW: backslashreplace printed a non-UTF-8 folder as `\udcff`, not a path `git add` takes.
- G8-G10 simplification: the unsure-note expression twice, a no-op stderr reconfigure, paths resolved twice before writing.

### breaker agent (no high or medium; the agent's report in its reply)
- F1 LOW = G3, plus a relative link that leaves the repository and comes back.
- F2 LOW: a submodule on the path (`notes` a submodule) makes the batch `check-ignore` exit 128: "could not say" for every file, and a hint `git add` refuses.
- F3 VERY LOW = G5.
- Test gaps: `if own is not None` in `_links()` (covered by the F1 test), the not-written core-file unsure notes (covered by the G5 test, second run).

### Round 6 fixes
All accepted. G1 only git's discovery text ("not a git repository (or any") means no repository; G2/G3/F1 `_links()` follows chains and marks a link whose target is absolute or climbs out lexically as not portable; a file behind such a link, or behind an ignored link, gets a `note:` naming the link and stays out of the hint (learnings not copied); G4 one `logged()` helper for both handlers; G5/G8 one `check()` helper with a set of noted paths; G6 the note names the link; G7 stdout uses surrogateescape on POSIX (backslashreplace on Windows); G9 stderr reconfigure dropped; G10 writes take the plain paths (`_write_bytes` resolves); F2 `_repo_path()` treats a folder on the way with its own `.git` (submodule, nested repository) as outside. Tests for each (broken GIT_DIR, chain, absolute and out-and-back targets, shared-link note once on both runs, unexpected error with an unwritable log, submodule, the non-UTF-8 name printed as its bytes); every new guard mutation-checked. Checks: pytest 303 passed 4 skipped (also with `IDEAL_UMBRELLA_BASELINE=500 IDEAL_UMBRELLA_TAIL_BYTES=abc GIT_DIR=/nonexistent`), keyline 35/35, the three JSON files parse.

## Round 7 — head 519f360

Checks at that head: pytest 303 passed 4 skipped, keyline 35/35, the three JSON files parse; CI green on 3c92b83 (run 41232882923). Reviewers told to skip rounds 1-6.

### code-review skill, high (9 findings; H1, H2 reproduced; details at scratchpad `review-round7-findings.json`, outside the repo)
- H1 MEDIUM, CONFIRMED: `_links()` checked only the last part of a link's target: `notes -> lnk/docs` with `lnk` ignored gave a confident hint and a link that breaks in a clone (also an absolute middle link).
- H2 MEDIUM, CONFIRMED: a link in the chain inside a nested repository (`notes -> sub/x`, `sub` with its own .git) was never noted; git never records it.
- H3 LOW, Windows: stripping `\\?\` from `\\?\UNC\server\share` left a relative-looking target.
- H4 LOW: the ignored-link note lost its fix ("unignore it or commit it with git add -f").
- H5 LOW: a `.claude` in a nested repository was reported as "outside the repository" with a path inside it.
- H6 LOW: stderr still printed a non-UTF-8 folder as `\udcxx`.
- H7 design: the link walker gained a special case every round; one step-by-step resolver would do.
- H8 cleanup: the outside/ignored/blocked checks written twice (core files, learnings), already drifting (H4).
- H9 cleanup: `logged()` took the error it could read itself.

### breaker agent (no high or medium; the agent's report in its reply)
- I1 LOW = H1 (repros with `sub` ignored, absolute, and `.claude/hooks -> ../sub/h`).
- I2 VERY LOW, Windows: Python 3.13's `isabs` no longer calls a rooted `\Users\u\...` absolute; plus H3.
- I3 LOW, test gaps: the `own is None` guard (a chain out of the repository and back) and the resolved-folder lookup (`.claude -> cfg`, `cfg/hooks -> ../real`) survived mutation.
- I4 VERY LOW, docs: README step 2 listed fixed paths, which the hint can now differ from.

### Round 7 fixes
All accepted. H7/H1/H2/I1: `_links(real_repo, name)` is now one resolver that walks the path a component at a time as the file system does (link targets re-queued component by component, `..` on the resolved folder, a hop limit), recording every link followed as "ok", "absolute" (absolute, drive, rooted or lexically climbing out: H3/I2, `\\?\UNC\` turned into `\\`) or "nested" (H2; not asked of git). H8/H4/H5: one `missing(name)` gives the reason and fix for core files and the learnings file alike ("is installed, but ..."; "lands in a submodule or nested repository (rel)" vs "lands outside the repository (path)"; the ignored-link note keeps its fix). H6: stdout and stderr both surrogateescape on POSIX. H9: `logged(prefix)`. I4: README step 2 points at the hint. Tests: middle link ignored and named, link in a nested repository, `.claude -> cfg` + `cfg/hooks -> ../real` hint, a chain out and back, submodule wording; each new guard mutation-checked. Checks: pytest 307 passed 4 skipped (also with `IDEAL_UMBRELLA_BASELINE=500 IDEAL_UMBRELLA_TAIL_BYTES=abc GIT_DIR=/nonexistent`), keyline 35/35, the three JSON files parse.

## Round 8 — head fbac227

Checks at that head: pytest 307 passed 4 skipped, keyline 35/35, the three JSON files parse; CI green on 519f360 (run 41233492320). Reviewers told to skip rounds 1-7.

### code-review skill, high (10 findings; K1-K3 reproduced)
- K1 LOW, CONFIRMED: the "commit it with git add -f" fix was given for the learnings file, which is not written when ignored, and for files behind a link, where `git add -f .claude/settings.json` is refused ("beyond a symbolic link").
- K2 LOW, CONFIRMED: `_links()` judged a link leaving the repository by `normpath` of its text, which folds `..` across links: `notes -> a/b/lnk/../r3/docs` with `lnk -> ../..` was hinted as safe (breaks in a clone under another name); `notes -> lnk/../../docs` with `lnk -> a/b/c` was wrongly called outside.
- K3 LOW, CONFIRMED: a link into `.git` (`notes -> .git/info`) got a confident hint; `git add` stages nothing there.
- K4 LOW: past the hop limit or when `readlink` fails, the realpath fallback called the link "ok" even when it led outside.
- K5 VERY LOW: only stdout was checked for `reconfigure`; a plain stderr raised AttributeError in-process.
- K6 design: two resolvers (realpath for the file, the walker for links).
- K7 cleanup: the note sentence built twice from a (reason, fix) tuple.
- K8 test gap: the outside-link assertion had been weakened to "it lands".
- K9 docs: `_add`'s docstring did not say links join the hint or which cases are left out.
- K10 conventions: the link-walker lesson was not saved in notes/learnings.md.

### breaker agent (no high; details at scratchpad `round8-breaker.md`, outside the repo)
- J1 LOW-MEDIUM, CONFIRMED: a submodule that is not checked out has no `.git`, so `_nested()` missed it: check-ignore failed for every path ("could not say"), the learnings file was copied into the submodule and the hint named a path git add refuses.
- J2 LOW = K2.

### Round 8 fixes
K1: `missing()` builds the whole clause; an ignored core file's fix names the path to force-add (the real path, or the link), the learnings file's fix is "unignore it and run this again". K2/J2: each queued part carries the link whose target it came from; a `..` that takes the walk above the repository on disk marks that link "absolute" (the text check is gone). K3/J1: `_nested()` also refuses any `.git` component and any folder git records as a gitlink (`_gitlinks()`, one `git ls-files -s -z`, output to a temp file); wording "a submodule, a nested repository or .git". K4: the fallback marks the link "absolute" when realpath lands outside. K5: each stream checked for `reconfigure`. K7: done with K1. K8: assertion restored. K9: docstring updated. K10: watch-out line added. K6 rejected: with K2 fixed both resolvers walk the disk and agree; merging them is a refactor with no failing case. Tests for each (9 new; all fail on fbac227). Checks: pytest 316 passed 4 skipped, keyline 35/35, the three JSON files parse. Windows CI went red on 4b78517 (run 41234638124): four new tests built link targets with "/", which Windows cannot follow; fixed in round 9 (M1).

## Round 9 — head 4b78517

Checks at that head: pytest 316 passed 4 skipped, keyline 35/35, the three JSON files parse; CI green on fbac227 (run 41234061181), red on Windows for 4b78517 (run 41234638124). Reviewers told to skip rounds 1-8.

### code-review skill, high (9 findings; M2-M5 reproduced; details at scratchpad `review-round9-findings.json`, outside the repo)
- M1 HIGH, CONFIRMED: Windows CI red: four round-8 tests made link targets with "/".join; Windows links with "/" dangle.
- M2 LOW, CONFIRMED: a link target passing with `..` through a folder a clone lacks (`notes -> build/../docs`, build ignored, a nested repository or untracked) got a confident hint.
- M3 LOW, CONFIRMED: an ignored real path returned before the links were checked: with `.claude -> cfg` and both ignored, the fix named only `cfg/settings.json`; with an absolute link, the fix could not help.
- M4 LOW, CONFIRMED: a link at a submodule's own path (`notes` a gitlink, `notes -> docs` on disk) was hinted; `git add notes` replaces the submodule.
- M5 LOW, CONFIRMED: the `git add -f` path was not quoted (`my cfg/settings.json`).
- M6 VERY LOW (macOS, not run): gitlinks compared case-sensitively on a case-insensitive file system.
- M7 LOW: `_gitlinks()` listed the whole index under a 10 s timeout; a timeout silently brought J1 back.
- M8 docs: round 8's log said 11 tests (9) and never recorded its checks or the red Windows run.
- M9 VERY LOW: past 40 hops an absolute link landing inside is "ok".

### breaker agent (no high; details at scratchpad `round9-breaker.md`, outside the repo)
- L1 LOW-MEDIUM = M3.
- L2 LOW = M2.
- L3 LOW = M5.
- T1 test gap: dropping `gitlinks` from the `_links` call passed every test.

### Round 9 fixes
M1: targets built with `os.path.join`. M2/L2: `_links()` also returns the folders the walk enters and leaves with `..`; one of those that is nested, ignored or holds nothing git records (nor a file this run writes) gets a note naming it. M3/L1: links are checked before the real path; an ignored real path and ignored links are named together, and the force-add names them all. M4: `_nested()` also refuses a path that is itself a gitlink. M5/L3: `_arg()` quotes a path for the shell ('...' on POSIX, "..." on Windows; a leading "-" gets "./"). M6: gitlinks folded with `FOLD` on Windows and macOS. M7: `_ls_files()` asks only about the folders on the way (literal pathspecs); a first walk without gitlinks finds them, a second walk runs only when some are found. M8: round 8's entry corrected. T1: a link inside a submodule that is not checked out. M9 rejected: the OS refuses a path past 40 links (ELOOP) anyway, so no file is written through it. Tests: 8 new (one Windows/macOS only); every new guard fails on 4b78517, and dropping `gitlinks` from `_links` fails two.

## Round 10 — head e9ec96d (findings logged, NOT yet fixed)

Checks at that head: pytest 323 passed 5 skipped locally, keyline 35/35, the three JSON files parse. CI run 41235257361: Ubuntu green, **Windows pytest red** (job 124637568608; most likely `test_a_submodule_recorded_in_other_case_is_noted`, see P2; read the job log first). Reviewers told to skip rounds 1-9.

### code-review skill, high (10 findings; P1 reproduced, P2 reproduced on the git side)
- P1 MEDIUM, CONFIRMED: the untracked check for a folder passed with `..` ignores the links this run names in the hint: `.claude/hooks/context_check.py -> ../../tools/context_check.py` (new, uncommitted) gets "passes through the folder .claude/hooks, which git does not track" and drops out of the hint. Fix: count every link in `links[*]` (and their parent folders) as tracked, along with `recorded` and the written real paths; build one set of tracked folder prefixes once (also P9).
- P2 MEDIUM, CONFIRMED: M6 does nothing: `git ls-files -- notes` matches pathspecs case-sensitively even with core.ignorecase, so a gitlink "Notes" is never listed. Fix: use `:(icase)` pathspecs when FOLD folds (drop `--literal-pathspecs` then and use `:(literal,icase)`), or list gitlinks differently.
- P3 LOW: `_ls_files()` returning None (timeout, failure) gives no notice; submodule and untracked checks are silently skipped. Fix: a notice like `_unsure()`.
- P4 LOW: on_way includes every ancestor, so `ls-files -- packages` lists a whole subtree. Fix: ask ancestors as exact entries (gitlinks) and list only under passed folders.
- P5 LOW: a passed folder with `ignored` None (git cannot say) gets no "could not say" notice. Fix: `_unsure(folder)` when `ignored.get(folder) is None`.
- P6 LOW, Windows: `_arg` double quotes leave `$`, backtick (PowerShell) and `%VAR%` (cmd) live; a leading `@` splats. config/install.py has `quote()`/`shell_risk()` for this.
- P7 cleanup: `_arg` POSIX branch re-implements `shlex.quote`; mirror install.py's `quote()` (copy it: the script runs with -I).
- P8 cleanup: `unignore()` quotes only for what == "it"; make it take a list of paths, quote and join itself, pick it/them by length.
- P9 cleanup: the untracked check rebuilds a list per passed folder; one set computed once.
- P10 docs: README line 92 has a stray comma ("breaks in a clone and, gets") and reads badly; split the sentence.

### breaker agent (details were in the scratchpad, lost with the container; summary here)
- N1 LOW, CONFIRMED (= P1 variant): `notes -> sub/n`, `sub/n -> ../docs` with sub untracked: committing the hinted links gives the clone `sub`; fix as P1.
- N2 LOW, contrived, CONFIRMED: `notes -> sub/../docs` with sub a recorded submodule gets "lies in a submodule", but a clone has the empty `sub` folder. Fix: skip the `_nested` check for a passed folder when `FOLD(folder) in gitlinks` (the folder itself, not its contents).
- Test gaps: dropping `--literal-pathspecs`, `_arg`'s leading "-" handling, or passed folders from the check-ignore call passes every test; the "ignored" layout test asserts only the shared prefix ("git ignores" wording unchecked).

### Windows CI fix after round 10 (P2 fixed; the rest still open)
Run 41235257361 (job 124637568608) failed three tests on Windows. Two, `..` in a link target: Windows folds `..` in a target as text before following any link in it, so `_links()` now normpaths a target on Windows, and the two POSIX-semantics tests (`climbs_out_and_back`, `only_looks_outside`) skip there. The third is P2: `_ls_files()` now sends `:(literal,icase)` pathspecs where FOLDS (Windows, macOS) and `:(literal)` elsewhere; checked against git with a gitlink "Notes" asked for as "notes". Checks: pytest 323 passed 5 skipped, keyline 35/35, the three JSON files parse.

### Second Windows CI fix (d9cbe21)
Run 41235731230 (job 124638997364) failed `test_a_folder_a_link_passes_through_must_reach_a_clone` (all three layouts) on Windows: the normpath from the fix above folded `build/../docs` to `docs`, so `build` was never recorded as passed. Windows itself never needs `build`, but a POSIX clone of the same link walks it, so the note stays: before normpath, a relative target's text is walked from the link's folder and every folder its `..` leaves is recorded as passed. Checks: pytest 323 passed 5 skipped, keyline 35/35, the three JSON files parse.

## Loop stopped (2026-10-31)
The user stopped the loop after round 10 and had PR #26 merged at its green head 5fb472c (merge b199638). Round 10's P1, P3-P10, N1, N2 and the test gaps were not fixed and stay open as follow-ups; no round 11 ran.

## Round 10 follow-ups fixed (2026-10-31, branch `round10-follow-ups`)
The user asked for the follow-ups after PR #26 merged. P2 was already fixed (Windows CI fix above).
- P1/N1/P9: one `tracked` set built once (what `_ls_files` lists, the real paths written, every link marked "ok", and every folder above each, folded with FOLD); a passed folder is untracked only when it is not in that set. An ignored "ok" link counts too: its own note names the `git add -f` that puts it in the clone.
- N2: `lacks(folder)`: a passed folder that is itself a recorded submodule is not "in a submodule" (a clone has the empty folder); used for both the check-ignore list and the note.
- P3: `_ls_files()` returns [] for git's "not a git repository (or any" (exit 128, LC_ALL=C), so a folder outside any repository stays quiet; any other failure gives the note "git could not list what it records on the way, ...".
- P5: `check()` also gives "git could not say whether <folder> is ignored" for a passed folder git could not judge.
- P6/P7: `_arg()` is `shlex.quote` on POSIX; on Windows bare only for `[\w+=:,./-]` (no `@`, no `%`), else double quotes, as `config/install.py`'s `quote()` (copied: the script runs with -I). `_risk()` adds a warning when a Windows path holds `$`, backtick or `%`.
- P8: `unignore(paths, what=None)` quotes and joins the paths itself and picks it/them by count.
- P10: README sentence split; it also names the two new notices and the Windows warning.
- P4 rejected: git pathspecs always take in a folder's contents and the index has no exact-entry match (`:(glob)` and `:(literal)` both list `packages/a/f` for `packages`, checked on git 2.43); `ls-tree HEAD` would miss a staged submodule. The listing of one subtree stays far below the 10 s timeout, and a timeout now gives P3's note.
- Test gaps: the layout test asserts each reason in full (dropping passed folders from check-ignore now fails it); `_arg`'s leading "-" and Windows quoting are unit-tested; literal pathspecs are tested with a folder `:b` (a `b[1]` folder could not catch it: git matches a pathspec literally before as a glob).
- Tests: 7 new; the 6 behaviour tests fail on the pre-fix code; mutations (literal magic dropped, passed folders dropped from check-ignore, the "-" guard dropped) each fail a test.
- Checks: pytest 330 passed 5 skipped, keyline 35/35, the JSON files parse.
