# Ideal-Umbrella review: install / uninstall / hook (base f276303..7a37497)

Experiments were run in throwaway homes under /tmp/claude-0/exp (the script is /tmp/claude-0/exp/seq.py). No repo files were changed.
Both suites pass as they stand: pytest 30/30, keyline 34/34. None of the bugs below is covered by a test.

## 1. HIGH (stuck): a failed install leaves a hook that blocks every prompt
- **Worst case:** stuck. **Who meets it:** unusual. **Proof:** CONFIRMED.
- **Where:** config/install.py:240-268 (order of writes) and config/install.py:341-345 (`except ValueError`).
- **What happens:** install writes settings.json first, with the hook entry pointing at
  ~/.claude/ballast/context_check.py. After that it handles CLAUDE.md, then copies the hook,
  then writes the record.
  - If anything between those steps raises, the settings entry stays but the hook file and the record are never written.
  - `python -I <missing file>` exits with code **2**. For a UserPromptSubmit hook, exit 2 means "block the prompt and erase it".
  - So every prompt in every session gets blocked until the user edits settings.json by hand.
  - The repo-level command guards against this with `; exit 0`. The user-level command has no such guard.
- **Repro (CONFIRMED):**
  1. Use a home whose ~/.claude/CLAUDE.md is not UTF-8, e.g. `"caf\xe9"` in cp1252 (common for files saved by Windows editors).
  2. `python -I config/install.py --home H`
  3. Output: `Error: 'utf-8' codec can't decode byte 0xe9 ...; nothing written`, exit 1.
  4. But settings.json now has both keys, the 6 deny tools and the hook entry. There is no ballast/context_check.py and no install-record.json.
  - Why: UnicodeDecodeError is a subclass of ValueError, so main() catches it and prints "nothing written", which is false.
  - Running that hook command gives exit=2 (checked).
- **Same outcome (PLAUSIBLE, not run because root ignores file permissions):** a read-only CLAUDE.md, e.g. a Nix/home-manager symlink into /nix/store. That raises an uncaught PermissionError (traceback) in the same place.
- **Knock-on:** with no record, uninstall later runs in "no record" mode and leaves the 6 deny tools.
- **Smallest fix:**
  1. Do all the reads first: settings, CLAUDE.md and the hook source.
  2. Then copy the hook file, write CLAUDE.md and write the record.
  3. Write settings.json last.
  4. Only catch errors that really happen before any write. Optionally add `|| exit 0` semantics; this can't be done portably, so ordering is the real fix.
- **Test:** unit test. Put a non-UTF-8 CLAUDE.md in tmp home, run main(), and assert that settings.json is unchanged (or that the hook file exists whenever settings has the hook entry).

## 2. HIGH (data): running uninstall twice deletes the user's own settings values and CLAUDE.md
- **Worst case:** data. **Who meets it:** feature. **Proof:** CONFIRMED.
- **Where:** config/uninstall.py:62 (`elif key in added or not has_record: del`), :141 (`record is None` -> CLAUDE.md deleted), and :146-147 (the record is deleted after the first run).
- **Repro:**
  1. Start with settings `{"autoCompactWindow":250000,"skillListingBudgetFraction":0.005,"model":"opus"}`, and a ~/.claude/CLAUDE.md identical to config/CLAUDE.md. Both are the user's own, set up before install.
  2. Run install, then uninstall. The first uninstall correctly keeps both keys and CLAUDE.md, then deletes install-record.json.
  3. Run uninstall a second time. It runs in "no record" mode: `autoCompactWindow: removed`, `skillListingBudgetFraction: removed`, `CLAUDE.md deleted`.
  4. Result: settings is `{"model":"opus"}` and CLAUDE.md is gone. CLAUDE.md is unlinked with no backup.
- **Other triggers of the same no-record path:** a corrupt or unreadable record (`_read_record` returns None on ValueError), or a home where Ideal-Umbrella was never installed.
- **Smallest fix (either works):**
  - After a successful uninstall, keep a marker instead of nothing, e.g. rewrite the record as `{"uninstalled": true}`, and treat it as "nothing to undo".
  - Or in no-record mode, never delete CLAUDE.md without a backup, and only remove keys when the hook entry is also present (that is the evidence of a pre-record install).
- **Test:** unit test. Run install, uninstall, uninstall on a home with pre-existing identical values, and assert that the keys and CLAUDE.md survive.

## 3. MEDIUM (data/task): uninstall compares against the current template, not what was installed
- **Worst case:** data. **Who meets it:** feature (anyone who runs `git pull` between install and uninstall). **Proof:** CONFIRMED.
- **Where:** config/uninstall.py:52-58 (compares to `template`), :133 (CLAUDE.md compared to the current config/CLAUDE.md), and :146-147 (the record is deleted anyway).
- **Repro (on a copy of the repo):**
  1. Install over a user's own CLAUDE.md ("my own rules"). It is backed up to CLAUDE.md.bak-X.
  2. Then change config/user-settings.json autoCompactWindow to 300000 and append a line to config/CLAUDE.md. This is what a later git pull does.
  3. Run uninstall. Output: `note: autoCompactWindow is 250000, not the installed value; left as is` (wrong: 250000 IS the installed value), and `note: CLAUDE.md differs ...; left as is`.
  4. The record is then deleted.
  5. Result: the installed key stays forever. The user's own CLAUDE.md is never restored; it sits orphaned in .bak-X, and nothing points to it any more.
- **Smallest fix:**
  - Store the installed values (and a hash of the installed CLAUDE.md) in install-record.json, and compare against those.
  - Do not delete the record while anything was "left as is".
- **Test:** unit test. Monkeypatch USER_SETTINGS and CLAUDE_MD to changed copies between install and uninstall, and assert that the key is removed and the backup is restored.

## 4. MEDIUM (task/stuck): a relative or literal-`~` --home writes a relative hook path; verify passes, every prompt is blocked
- **Worst case:** stuck. **Who meets it:** unusual. **Proof:** CONFIRMED.
- **Where:** config/install.py:342 / :66 (`Path(args.home)` is not resolved; `hook_command` embeds it as given).
- **Repro:**
  1. `cd ~ && python -I config/install.py --home .`
  2. The hook command becomes `/usr/bin/python -I .claude/ballast/context_check.py`, and verify prints [OK].
  3. Claude Code runs hooks from the project directory, where that path does not exist, so exit=2 blocks every prompt (checked from /tmp).
  4. The same happens with `--home ~` on Windows PowerShell or cmd, which pass a literal `~`.
- **Smallest fix:** `Path(args.home).expanduser().resolve()` in both main()s (install and uninstall).
- **Test:** unit test. `main(["--home", "."])` with chdir into tmp, then assert the command path is absolute.

## 5. MEDIUM (data): a symlinked settings.json (dotfiles, stow, home-manager) is replaced by a regular file
- **Worst case:** data. **Who meets it:** feature. **Proof:** CONFIRMED.
- **Where:** config/install.py:193-203 `_write_json` (`os.replace` onto the link path); uninstall uses the same function. The same pattern is in config/add_to_repo.py:110-119.
- **Repro:**
  1. Make ~/.claude/settings.json a symlink to dotfiles/settings.json, then install.
  2. Afterwards settings.json is no longer a symlink, and the dotfiles copy is unchanged.
  3. Later dotfile edits silently stop applying, and the user's dotfiles management is broken.
- **Note:** CLAUDE.md is written through the link by `write_text`, but uninstall's `backup.replace(claude_md)` also replaces a symlinked CLAUDE.md.
- **Smallest fix:** resolve the path first (`path = path.resolve()`), and create the temp file in the resolved file's folder.
- **Test:** unit test with a symlink (skip it on Windows without privileges). Assert `is_symlink()` after install.

## 6. LOW (crash): a malformed hook entry crashes install, uninstall and verify with a traceback
- **Worst case:** crash. **Who meets it:** unusual. **Proof:** CONFIRMED.
- **Where:** config/install.py:75 `_is_ours` calls `h.get` with no isinstance check. The same applies at :311 (verify) and through uninstall.py:32.
- **Repro:** settings `{"hooks":{"UserPromptSubmit":[{"hooks":["echo hi"]}]}}` gives `AttributeError: 'str' object has no attribute 'get'`. Nothing is written.
- **Smallest fix:** `isinstance(h, dict) and ...`, as add_to_repo.py already does. Use the same guard in verify.

## 7. LOW (data): reinstall then uninstall restores the pre-first-install CLAUDE.md, dropping later user edits
- **Worst case:** data. **Who meets it:** unusual. **Proof:** CONFIRMED by tracing.
- **Where:** config/install.py:226-229 (the first claude_md backup wins).
- **What happens:**
  1. Install over user file U; the backup is B1.
  2. The user then puts their own edits into ~/.claude/CLAUDE.md (U2).
  3. A reinstall (after a template update) backs up U2 to B2 and writes the template.
  4. Uninstall restores B1 (U); U2 survives only in an unreferenced B2.
- The same logic applies to settings: a user value set after install and then overwritten with --force is dropped on uninstall. The key is deleted because it is in `added_keys`; the value survives only in a settings backup.
- **Fix:** when the current file before replacement is not the template, record the newest backup as well, or tell the user which backup holds their latest edits.

## 8. LOW (small): unused_tools.py treats a missing or mistyped folder as "no denied tool was used"
- **Proof:** CONFIRMED.
- **Where:** scripts/unused_tools.py:21, :44.
- **Repro:** `python -I scripts/unused_tools.py /no/such/dir` prints "0 transcripts", then every denied tool shows "called 0 time(s)" and nothing is flagged.
- **Fix:** exit non-zero when the folder is missing or 0 transcripts are found.

## Checked and held
- context_check.py:
  - Any exception is caught and main() returns 0; it never exits 2.
  - TAIL_BYTES that is bad, zero or negative falls back with a warning.
  - A huge value only reads the whole file, bounded by the 15 s timeout, which is non-blocking.
  - A partial first line is skipped.
- install twice is idempotent: no changes and the record is untouched.
- install --force records the old value, and uninstall restores it.
- The _merge_record first-wins rule holds for keys and deny.
- Sibling hooks are kept.
- dry-run writes nothing.
- uninstall with no settings.json works.
- Errors in merge_settings are raised before any write.
- add_to_repo.py merge guards non-dict hooks, and its is_ours is safe.
- verify-tokens.py: no new issues.
- ci.yml is valid. PYTHONUTF8=1 hides nothing, because every text open in config/hooks/keyline/scripts passes an explicit encoding.
- keyline_hook: exit 2 only on real lint findings; OSError gives exit 1.

## Not checked
- Real Claude Code behaviour on Windows: which shell runs a hook command with `"C:\..."` quoting.
- The read-only CLAUDE.md variant of #1, because this sandbox runs as root.

## Outside this task
None.
