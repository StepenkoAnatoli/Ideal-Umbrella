# General review of the whole repo at 44170ca (PR #36 head)

Date: 2026-11-03. This review only reports problems; it changes no code. Scope: the whole repo — hooks, keyline, scripts, config installers, tests, docs, CI. Findings already in `research/review-findings-plain-2829343.md` (the `_plain` review) are not repeated.

How it ran: I reviewed the hooks, `keyline_hook.py` and CI myself. Two subagents covered the rest: `config/` (prefix A) and `scripts/` plus keyline outside `_plain` (prefix B). I re-ran every high and medium finding, except A2, which only the agent ran. Every command ran with a temp HOME and CLAUDE_CONFIG_DIR under the session scratchpad, written below as `$S`. The real `~/.claude` was never touched.

## Baseline (all green)
- `python -m pytest -q`: 1985 passed, 14 skipped.
- `python -I keyline/tests/run_tests.py`: 35/35 passed.
- `python -m pyflakes keyline scripts tests config hooks`: clean.

## Summary

| ID | Sev | File:line | Class | One line |
|---|---|---|---|---|
| A1 | high | config/add_to_repo.py:247-261, 753, 756 | design limit | A committed file symlink makes add_to_repo overwrite any file it points at, outside the repo too; no backup; exit 0 |
| A2 | medium | config/add_to_repo.py:323, 365 | pre-existing | runs `git` with the target's own `.git/config`; a planted `core.fsmonitor` executes |
| A3 | medium | config/install.py:190-192, 336-341; config/uninstall.py:37-50, 136-149 | design limit | any hook naming `context_check.py`, in any event, is treated as ours: install replaces it, uninstall deletes it |
| B1 | medium | keyline/keyline_check.py:256 | pre-existing (neighbour of the `_not_` fix) | curly-apostrophe negations (can’t) are not counted: fail-open |
| B2 | medium | keyline/keyline_check.py:261-267 | neighbour of a previous fix (prefix list) | Hebrew negations ואינו/שאינו, בלי and אל are missed: fail-open and fail-closed |
| B3 | medium | scripts/lint_validate.py:34-36 | pre-existing | recursive glob follows symlink cycles: hangs |
| B4 | medium | scripts/usage_breakdown.py:145-168 | design limit | `<session>/subagents/*.jsonl` are not counted: cost totals too low |
| C1 | medium | keyline/keyline_hook.py:73-86 | neighbour of a previous fix (symlinked notes/ folder) | an absolute `--watch` pattern through a symlinked path never matches: the hook silently checks nothing |
| A4 | low | config/add_to_repo.py:271, 756 | neighbour of a previous fix | no backup; `ensure_ascii=True` escapes non-ASCII; CONTRIBUTING says files are backed up |
| A5 | low | config/install.py:82-88 | design limit | `--home` with CLAUDE_CONFIG_DIR set installs where Claude Code does not look; verify passes |
| A6 | low | config/install.py:456-468, 586-592; add_to_repo.py:255-261 | pre-existing | backups/temp files briefly at umask mode before chmod/copystat (unverified timing) |
| A7 | low | config/cloud-setup.sh:5-6 | design limit | `cat >` replaces an existing CLAUDE.md, ignores CLAUDE_CONFIG_DIR, no marker section |
| A8 | low | config/install.py:396-397; add_to_repo.py:185-186 | pre-existing | duplicate JSON keys silently collapse on rewrite |
| A9 | low | config/verify-tokens.py:69 | design limit | `--api-key` on the command line is visible in `ps` and history |
| B5 | low | keyline/keyline_lint.py:215 | pre-existing | non-ASCII word split into ASCII fragments, flagged as abbreviations (`kämpft` -> `mpft`) |
| B6 | low | keyline/keyline_lint.py:162, 205 | neighbour of a previous fix (ledger uses split("\n")) | `splitlines()` splits on U+2028/U+0085/\x0c: wrong line numbers |
| B7 | low | keyline/keyline_lint.py (furniture regexes) | design limit | setext headings and a lone `#` are not flagged |
| C2 | low | keyline/keyline_hook.py:54-64 | fix without test | `--print-config` output (quoting, Windows branch) has no test |
| C3 | low | .github/workflows/ci.yml | pre-existing | actions pinned by tag, not SHA; no `permissions:` block |
| C4 | low | .github/workflows/ci.yml (Keyline suite) | design limit | tiktoken downloads o200k_base on every CI run (not cached): network flake |
| C5 | low | .github/workflows/ci.yml:47-51 | pre-existing | "JSON configs parse" leaves out keyline/hooks-example.json |
| C6 | low | hooks/context_check.py:316, 350-353 | design limit | any `hook_event_name` is echoed into `hookSpecificOutput`; on an event without `additionalContext` the output may be rejected |
| N1-N7 | low/unverified | see B notes | — | dedup of streamed usage, resumed-session double count, deny patterns, allow-file search up to `/`, plugin_cost followlinks, node_modules substring test, invariants hidden in an HTML comment |

Totals: 1 high, 7 medium, 14 low, and 7 notes.

---

## High

### A1 — add_to_repo.py writes through a committed file symlink to any target
- **Where:** `config/add_to_repo.py:247-261` (`_write_bytes` follows `os.path.realpath`), called at :753 and :756. The outside-repo check (`missing()`, :706-710) runs only after the write, and it only prints a `note:`.
- **Class:** design limit. Writing through a *folder* link is intended and covered by `tests/test_add_to_repo.py:919`. Nothing checks a *file-level* link to an unrelated file.
- **Failure scenario:** someone clones a repo and runs `add_to_repo.py` on it. The repo holds `.claude/hooks/context_check.py -> ../../../../home/<user>/.bashrc`, or `.claude/settings.json -> ~/.claude/settings.json`. The link's target is replaced by the hook source, or has the repo template merged into it. No backup is made and the exit code is 0.
- **Repro** (I re-ran it):
  ```
  S=$SCRATCH/verify; mkdir -p $S/home $S/cfg $S/r1; export HOME=$S/home CLAUDE_CONFIG_DIR=$S/cfg GIT_CONFIG_NOSYSTEM=1
  echo "precious user data" > $S/home/victim.rc
  cd $S/r1 && git init -q hostile && cd hostile && mkdir -p .claude/hooks \
    && ln -s ../../../../home/victim.rc .claude/hooks/context_check.py && git add -A \
    && git -c user.email=a@b -c user.name=a commit -qm x && cd .. && git clone -q hostile clone
  cd <repo> && python -I config/add_to_repo.py $S/r1/clone; head -2 $S/home/victim.rc
  ```
  Output:
  ```
  .claude/hooks/context_check.py written
  note: .claude/hooks/context_check.py is installed, but it lands outside the repository (.../verify/home/victim.rc), so cloud sessions will not see it
  Commit .claude/settings.json and notes/learnings.md in that repository.
  """Ideal-Umbrella: show what a session costs, and remind Claude to hand a long chat
  over to a fresh session.
  ```
  The agent's run also showed `.claude/settings.json -> ~/other.json` merging the template into `other.json`.
- **Fix:** check before any write. When a file-level link's realpath is outside the real repo, or is not already a `context_check.py` or `settings.json`, refuse with nothing written, unless the user passes an explicit flag.
- **Missing tests:** a file link to an unrelated file outside the repo, and one to an unrelated file inside it (`-> ../../README.md`).

## Medium

### A2 — add_to_repo.py runs git with the target folder's own config
- **Where:** `config/add_to_repo.py:323` (`git check-ignore`) and :365 (`git ls-files -s`).
- **Class:** pre-existing.
- **Failure scenario:** the target folder came from an archive, a shared drive or another tool, which keeps `.git/config`; a plain `git clone` does not. Its `core.fsmonitor` command runs as the user. `safe.directory` does not help, because the user owns the folder. Mitigating fact: the README next tells the user to run `git add` there, which would run the same command anyway.
- **Repro** (the agent's run, git 2.43.0):
  ```
  cd $S/r2 && git init -q evil && cd evil && echo hi > a && git add a && git -c user.email=a@b -c user.name=a commit -qm x
  git config core.fsmonitor "echo FSMONITOR-RAN >> $S/pwned.txt; false"
  cd <repo> && python -I config/add_to_repo.py $S/r2/evil >/dev/null; cat $S/pwned.txt
  ```
  Output: `FSMONITOR-RAN`, four times, and the run exits 0.
- **Fix:** run `git -c core.fsmonitor=false -c core.untrackedCache=false ...`, or warn about the risk in the docs. Add a test with a planted fsmonitor.

### A3 — "ours" means any hook that names context_check.py, in every event
- **Where:** `config/install.py:190-192` (`_is_ours`) and :336-341, where install rewrites the matching command and does not record the old one. `config/uninstall.py:37-50` and :136-149, where uninstall removes matches in *all* events.
- **Class:** design limit. README:69 states the rule, but the rule's reach is wider than the README sentence suggests: it matches `my_context_check.py`, and it reaches events the template never names.
- **Failure scenario:** a user's own `Stop` hook `python3 ~/tools/my_context_check.py` is deleted by uninstall. A user's own UserPromptSubmit `context_check.py --mine` is replaced by install and never restored. The only copy left is the settings backup, which no message mentions.
- **Repro** (I re-ran it):
  ```
  export HOME=$S/home CLAUDE_CONFIG_DIR=$S/cfg3; mkdir -p $CLAUDE_CONFIG_DIR
  echo '{"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "python3 ~/tools/my_context_check.py --stop"}]}]}}' > $CLAUDE_CONFIG_DIR/settings.json
  python -I config/install.py >/dev/null; python -I config/uninstall.py | grep Stop
  python -I -c "import json,sys;print(json.load(open(sys.argv[1])).get('hooks'))" $CLAUDE_CONFIG_DIR/settings.json
  ```
  Output:
  ```
    - hooks.Stop: Ideal-Umbrella hook removed
  {'Stop': []}
  ```
- **Fix:** treat a hook as ours only when it names the installed path (`ballast/context_check.py`, or the path in the install record) and sits in an event the template names. Record a replaced command so uninstall can restore it. Add tests for both cases.

### B1 — curly-apostrophe negations are not counted
- **Where:** `keyline/keyline_check.py:256`. NEG_EN matches only `[A-Za-z]+n't` with an ASCII `'`.
- **Class:** pre-existing; neighbour of the `_not_` fix.
- **Failure scenario:** the source says "We can’t ship" (typographic quotes are common in LLM and editor output), and the rendering drops the negation. The check still passes, so the meaning is reversed without a warning. In the other direction, an English "do not" rendered as "Don’t" is a false alarm.
- **Repro** (I re-ran it; `$S/neg.py` is printed below):
  ```
  import sys; sys.path.insert(0,'keyline'); import keyline_check as k
  for a,b in [("We can’t ship v2.1 on Friday.","We can ship v2.1 on Friday."),
              ("Do not deploy v2.1 before 14:30.","Don’t deploy v2.1 before 14:30."),
              ("אל תפרסו את v2.1 ביום שישי.","Deploy v2.1 on Friday."),
              ("Deploy v2.1 without approval.","פרסו את v2.1 בלי אישור.")]:
      print(k.report("src","ren",a,b)[0], repr(a), "->", repr(b))
  ```
  `python -I $S/neg.py` output:
  ```
  True 'We can’t ship v2.1 on Friday.' -> 'We can ship v2.1 on Friday.'
  False 'Do not deploy v2.1 before 14:30.' -> 'Don’t deploy v2.1 before 14:30.'
  True 'אל תפרסו את v2.1 ביום שישי.' -> 'Deploy v2.1 on Friday.'
  False 'Deploy v2.1 without approval.' -> 'פרסו את v2.1 בלי אישור.'
  ```
  Rows 1 and 3 are fail-open (B1, B2). Rows 2 and 4 are fail-closed: a correct rendering fails.
- **Fix:** match `[A-Za-z]+n[’ʼ']t`, and add tests in both directions.

### B2 — Hebrew negation list gaps
- **Where:** `keyline/keyline_check.py:261-267` (NEG_HE).
- **Class:** neighbour of a previous fix (the prefix list).
- **What is missed:**
  - the ו/ש/כש prefixes on the inflected אינו family (ואינו, שאינו);
  - בלי ("without");
  - אל before a verb (the "don't" imperative).
- **Failure scenario:** a Hebrew source loses its negation and the check still passes (fail-open). A correct English-to-Hebrew rendering, the main use case, fails 1->0 (fail-closed). That teaches users to ignore the check.
- **Repro:** rows 3 and 4 above. The agent also ran `'השרת ואינו יציב אחרי v2.1.' -> 'The server is stable after v2.1.'`, which gave ok=True, and the reverse with `שאינו`, which gave ok=False 1->0.
- **Fix:** apply `(?:ו|ש|כש)?` to the אינ* forms. Add `בלי` and `אל(?=\s+ת)` (or a similar pattern). Add tests in both directions.

### B3 — lint_validate.py hangs on a symlink cycle
- **Where:** `scripts/lint_validate.py:34-36`. `glob.glob("**/*.md", recursive=True)` follows directory links; node_modules, `.git` and MAX_FILES are applied only after the full walk.
- **Class:** pre-existing.
- **Failure scenario:** the default corpus is `ROOT.parent`, the folder of sibling repos. A pnpm `node_modules` there with link cycles makes the run hang.
- **Repro** (I re-ran it):
  ```
  mkdir -p $S/c/pkg && echo hi > $S/c/pkg/a.md && ln -sfn .. $S/c/pkg/x && ln -sfn .. $S/c/pkg/y
  timeout 20 python -I -c "import sys; sys.path.insert(0,'scripts'); import lint_validate as l; print(len(l.corpus_files(sys.argv[1])))" $S/c; echo exit=$?
  ```
  Output: `exit=124` (killed after 20 s, no result).
- **Fix:** walk with `os.walk(followlinks=False)`, prune hidden folders and node_modules in place, and stop at MAX_FILES.

### B4 — usage_breakdown.py does not count subagent transcripts
- **Where:** `scripts/usage_breakdown.py:145-168`. `transcripts()` lists only the project folder, while `unused_tools.py` walks it recursively.
- **Class:** design limit.
- **Failure scenario:** in a session with many subagents, the cost and cache-write totals come out too low. The README's cost split (43/37/20) may be affected; that is unverified.
- **Repro** (I re-ran it). P holds `sess1.jsonl` (a 1h write of 1000, output 100) and `sess1/subagents/agent-a1.jsonl` (a 5m write of 90000, output 5000):
  ```
  python -I scripts/usage_breakdown.py $P
  ```
  Output:
  ```
  1 transcripts, 1 API responses
  cache_creation_input_tokens                     1,000
  cache_creation_5m_input_tokens                      0
  output_tokens                                     100
  ```
  The expected result is 2 transcripts, a 5m write of 90,000 and output of 5,100.
- **Fix:** walk the folder recursively, keep the `message.id` dedup, and add a subagents/ test. Then re-measure the README "Why" numbers.

### C1 — an absolute `--watch` pattern through a symlinked path never matches
- **Where:** `keyline/keyline_hook.py:73-86`. The edited path is resolved (`path.resolve()`), but the pattern is not. On macOS, `/tmp` and `/var` are links, and some home folders sit on linked volumes.
- **Class:** neighbour of a previous fix. The symlinked notes/ folder fix (test_keyline_hook.py:41) reads the path both as written and as resolved; `--watch` reads it only as resolved.
- **Failure scenario:** a user follows keyline/README.md:193 (`--watch /path/to/repo/PROGRESS.md`) for a repo whose path goes through a link. The hook exits 0 on every edit and never checks the file, and nothing reports it.
- **Repro** (I ran it):
  ```
  mkdir -p $S/real && ln -sfn $S/real $S/link && touch $S/real/PROGRESS.md
  python -I -c "import sys; sys.path.insert(0,'keyline'); import keyline_hook as h; from pathlib import Path
  p=Path(sys.argv[1]+'/link/PROGRESS.md'); print(h.watched(p, sys.argv[1]+'/link', [sys.argv[1]+'/link/PROGRESS.md']))" $S
  ```
  Output: `False`.
- **Fix:** match both the path as written (abspath) and the resolved path against the pattern as written and the pattern resolved, as the default mode does. Add a test.

## Low
- **A4**, `config/add_to_repo.py:271, 756` (neighbour of a previous fix). install.py:603 writes with `ensure_ascii=False` and makes a backup. add_to_repo does neither, so non-ASCII text in a repo settings.json comes back as `\uXXXX`, and an untracked file has no copy. CONTRIBUTING.md says "User files are ... backed up before they are replaced": that disagrees with the code. Fix: use `ensure_ascii=False`, and either back up the file or narrow the CONTRIBUTING line.
- **A5**, `config/install.py:82-88` (design limit). With CLAUDE_CONFIG_DIR exported, `--home ~` installs into `~/.claude`, which Claude Code does not read, and `--verify-only` still reports OK. Unverified beyond reading the code. Fix: print a notice when both are set.
- **A6**, `config/install.py:456-468, 586-592` and `add_to_repo.py:255-261` (pre-existing). A 0600 settings.json, whose `env` may hold secrets, has its backup and temp file sitting at 0644 for a moment before chmod/copystat. If copystat fails, the backup stays 0644. Unverified (timing). Fix: create the file with the source's mode, or 0600, before writing data.
- **A7**, `config/cloud-setup.sh:5-6` (design limit). `cat > ~/.claude/CLAUDE.md` replaces any CLAUDE.md that the image or an earlier step wrote, ignores CLAUDE_CONFIG_DIR, and uses no marker section. Fix: write to `${CLAUDE_CONFIG_DIR:-$HOME/.claude}` and append a marked section.
- **A8**, `config/install.py:396-397` and `add_to_repo.py:185-186` (pre-existing). When a key appears twice, only the last one survives the rewrite, and no message says so; the backup still has the original. Fix: use an `object_pairs_hook` that refuses duplicates with a one-line error.
- **A9**, `config/verify-tokens.py:69` (design limit). `--api-key` is visible in `ps` and in shell history. Fix: drop the flag, or warn in its help.
- **B5**, `keyline/keyline_lint.py:215` (pre-existing). `kämpft` gives `abbreviation: 'mpft' is 2 tokens`, while the docstring says the rule covers ASCII words only. Fix: skip any chunk with a non-ASCII letter.
- **B6**, `keyline/keyline_lint.py:162, 205` (neighbour of the ledger.py `split("\n")` fix). `splitlines()` also splits on U+2028, \x85 and \x0c, so line numbers drift, and a `- ` after U+2028 is flagged as a bullet. Fix: use `split("\n")`.
- **B7**, keyline_lint furniture regexes (design limit). A setext heading (`Title` over `---`) and a lone `#` pass the lint. Fix: add a setext rule and use `^#{1,6}(\s|$)`.
- **C2**, `keyline/keyline_hook.py:54-64` (fix without test). Nothing tests `--print-config`. The tests only cover it as a refused `--watch` argument. Its quoting and the Windows branch (`_quote`: `"..."` with `\"`, where a `$` in the path would still expand under bash) are unchecked. Fix: add a test that parses the output and runs the command with a piped event.
- **C3**, `.github/workflows/ci.yml` (pre-existing). `actions/checkout@v4` and `setup-python@v5` are pinned by tag, not by commit SHA, and there is no `permissions: contents: read`, so the GITHUB_TOKEN keeps the repo default. Fix: pin by SHA and add a read-only `permissions` block.
- **C4**, `.github/workflows/ci.yml` (design limit). The keyline suite builds `keyline/cache/` (gitignored), which makes tiktoken download o200k_base on each run. The pip cache does not cover that file, so a network outage at openaipublic fails CI. Fix: cache `TIKTOKEN_CACHE_DIR` with actions/cache.
- **C5**, `.github/workflows/ci.yml:47-51` (pre-existing). The "JSON configs parse" step leaves out `keyline/hooks-example.json`. Fix: add it, or glob `**/*.json`.
- **C6**, `hooks/context_check.py:316, 350-353` (design limit). `hook_event_name` from the event is echoed into `hookSpecificOutput.hookEventName`. The docstring names UserPromptSubmit and PostToolUse; if the hook is wired to another event such as Stop, the output's schema may be refused and the note lost. Fix: send `hookSpecificOutput` only for those two events.

### Notes (low or unverified; details are in the B agent's notes)
- N1: usage_breakdown keeps only the first streamed line per `message.id`. If earlier lines carry partial `output_tokens`, output is undercounted; taking the max per field is safer. Unverified.
- N2: a resumed session's file can repeat earlier history, and toolresult_share, unused_tools and usertext_* count those lines twice. Fix: dedup by uuid.
- N3: unused_tools compares deny entries exactly, so an `mcp__server` or `Tool(pattern)` deny always shows 0 calls. Design limit; the current config holds plain names only.
- N4: keyline_lint `load_allow` (:153-162) reads `keyline-allow.txt` in every parent folder up to `/`, so a planted `/tmp/keyline-allow.txt` whitelists words for notes under /tmp. It also uses `Path.is_file()`, which the repo replaced with `os.stat` elsewhere (a neighbour of that fix).
- N5: `plugin_cost.py:58` uses `os.walk(followlinks=True)`, which can loop or walk the whole filesystem.
- N6: `lint_validate.py:36` tests `"node_modules" not in f` as a substring of the full path, so a parent path containing that word drops every file.
- N7: keyline_check passes a rendering whose invariants sit only inside an HTML comment. Counts are not aligned or ordered; that part is documented.

## Checked and found sound
- **hooks/context_check.py:**
  - session-id sanitising, so no path traversal;
  - every BAD_RECORD path: torn lines, inf/NaN, deep nesting, non-dict `message` or `usage`;
  - `parse_int` with `+-5`, `1_000`, non-ASCII digits, 0 and negatives;
  - log rotation arithmetic;
  - a cut through a JSON line at the 4 MB tail boundary cannot parse into a false record;
  - a failure in the savings line or the hand-off check is isolated, and the hook always exits 0.
- **keyline_hook.py:**
  - non-string or missing `file_path`, non-dict `tool_input`, a NUL in the name, an unreadable folder;
  - dotfiles below notes/;
  - `--watch` argument parsing;
  - the suffix rule kept under `--watch`.
- **Hook command quoting on POSIX:** with CLAUDE_CONFIG_DIR containing `'$(touch ...)` and a backtick, nothing is injected (agent A).
- **Docs:** README "Security model of the hook", the env-var defaults, and the savings-line format all match the code. `cloud-setup.sh` matches `config/CLAUDE.md`, as `tests/test_docs_match_source.py` already checks.

## Missing tests (collected)
- A1: a file-level link to an unrelated file, both outside and inside the repo.
- A2: a planted `core.fsmonitor`.
- A3: a user's own `*context_check.py` hook in another event, and in UserPromptSubmit.
- A4: non-ASCII text surviving an add_to_repo rewrite.
- B1/B2: `’` negations, and ואינו, בלי and אל, each in both directions.
- B3: a symlink cycle in the lint_validate corpus.
- B4: a `subagents/` transcript in usage_breakdown.
- B5/B6: a non-ASCII word and U+2028 in keyline_lint.
- C1: `--watch` through a symlinked path.
- C2: `--print-config` round trip.

## Suggested order
1. Fix A1, A3 and C1: they lose user data or silently skip the check.
2. Fix B1 and B2: fail-open in the main use case.
3. Fix A2 and B3/B4: hardening and correct numbers. Re-measure the README "Why" split after B4.
4. Batch the lows.

## Fixes (branch `ccr-fix-general`, PR #39)
Each fix began with a failing test. Each was checked for the same class elsewhere, and each moved README and CHANGELOG with it. Checks are listed under the table.

| ID | Commit | What changed |
|---|---|---|
| A1 | aea4db8 | add_to_repo stops, with nothing written, in two cases. The first is a settings or hook symlink to a file with a different name. The second is a file or folder link that lands in `~/.claude` or `CLAUDE_CONFIG_DIR`. A same-name link, such as a copy in a dotfiles folder, still works. `install.py` is the neighbour; it writes into the config folder by design. |
| A3 | ec79c14 | A hook counts as ours only when it runs `ballast/context_check.py` (in a repo, `.claude/hooks/context_check.py`) in an event the template names. The fix covers install, uninstall and add_to_repo. `--verify-only` keeps its loose match on purpose, because it only reports. A replaced command is not recorded: with the strict match, install only ever replaces its own hook. |
| C1 | 89d0bc5 | `--watch` reads the path and the pattern both as written and resolved. `shown()` is used for display only, so it is unchanged. |
| B1, B2 | 047174c | NEG_EN takes `’` and `ʼ` in n't. NEG_HE adds בלי and the ו/ש/וש/כש prefixes on the אינ* forms. It also adds the imperative אל or ואל, but only before a word starting with ת, so that אל meaning "to" is not counted. |
| A2 | 95ce586 | The git reads in add_to_repo run with `-c core.fsmonitor=false -c core.untrackedCache=false`. The README warns that the user's own later `git add` is not covered. |
| B3 | 95ce586 | `corpus_files` walks with `os.walk(followlinks=False)`, skips hidden folders and node_modules as it goes, and stops at MAX_FILES. |
| B4 | 04fc025 | COUNT picks the largest sessions, with `<session>/subagents/*.jsonl` read alongside each one. The report says how many subagent transcripts it read. The README cost split is flagged because it has not been measured again: no local transcripts are available in this container. |

| B5, B6, B7 | 22bd2e9 | The abbreviation lint skips a word that is not ASCII. Lines split at `\n` only, so U+2028, NEL and form feed keep line numbers right. A setext underline and a lone `#` count as headers. |
| N4 | 05b75ae | Allow files are read from the note's folder up to the repository root (the first folder holding `.git`), never from a world-writable folder, and only when they are regular files. |
| C2 | a7dffb6 | A test runs the printed `--print-config` command through `/bin/sh` from a folder whose name holds spaces, `$HOME`, quotes and backticks; another checks the Windows quoting. |
| C3, C4, C5 | d3645f7 | CI has `permissions: contents: read`, actions pinned by SHA, a cache for the tiktoken data, and parses every tracked `*.json` (the README Tests block runs the same loop). |
| C6 | 9925753 | `hookSpecificOutput` is sent only on UserPromptSubmit and PostToolUse; other events get `systemMessage` alone. |
| A4, A6, A8 | df16776 | Duplicate JSON keys are refused with nothing written. add_to_repo keeps non-ASCII text (`ensure_ascii=False`). Temp files and backups are created with the source file's mode, never wider. add_to_repo still makes no backup, since git holds the copy; CONTRIBUTING is narrowed to say so. |
| A5 | 8100050 | install, verify and uninstall warn on stderr when `--home` is given while CLAUDE_CONFIG_DIR is set. |
| A7 | 113908e | cloud-setup.sh writes a marked section into `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/CLAUDE.md`, replaces only that section, keeps other text, links and mode, and warns (exit 0) on broken markers. |
| A9 | 7f0b372 | verify-tokens takes the key from ANTHROPIC_API_KEY; `--api-key` still works and warns that it shows in `ps` and history. |
| N5 | 6fda1ca | plugin_cost does not follow a link to a folder that holds the app folder. |
| N1, N2 | 9d0c3ca | usage_breakdown takes the largest count of each usage field across a response's streamed lines. All five transcript scripts count a line whose `uuid` was already read once. Tests clear CLAUDE_CONFIG_DIR so the A5 warning does not depend on the runner. |
| N6 | 95ce586 | Already fixed by B3: lint_validate prunes by folder name, not by substring. |

Left as documented limits: N3 (unused_tools compares deny entries exactly; the shipped config holds plain names only, and pattern matching would mean re-implementing Claude Code's rule syntax) and N7 (invariants inside an HTML comment; the check does not parse markdown, and that is documented). Checks at 9d0c3ca, with a temp HOME and CLAUDE_CONFIG_DIR: pytest 2069 passed, 14 skipped; run_tests 35/35; pyflakes clean.
