# Ideal-Umbrella bug sweep — resume point (2026-10-25, after the fixes)

## Request (user)
"Make sure there are no bugs/errors and the read me is updated."

## State
- Earlier today: PRs #4, #6, #7, #8 merged; #3, #5 closed. README checked against the code (commit b101cbe).
- All 8 findings in `research/review-findings-2026-10-25.md` are fixed in commit 8a79183 on branch `ccr-da04ab7d-6rorpx` (draft PR #9). Each fix has a test that fails on the old code (14 new or changed tests failed when run against the old source, and all pass now).
- Local checks on 8a79183: pytest 44 passed; keyline 34/34; pyflakes clean on config/, tests/ and unused_tools.py; the three JSON configs parse.
- CHANGELOG.md (Unreleased > Fixed) and README.md (Install, Undo, scripts listing) describe the new behavior.

## Decisions and why
- #1: install reads everything first (read errors become ValueError and say "nothing written", which is now true). Then it writes the hook file, CLAUDE.md and the record, and settings.json last. That way the hook entry never points at a missing file.
- #2: after uninstall, install-record.json stays as `{"uninstalled": true}`, plus anything left as is. In no-record mode, keys are removed only when there is evidence of an install (our hook entry in settings, or the hook file). CLAUDE.md is backed up before it is deleted.
- #3: the record now has `installed` (the value written per key) and `claude_md.sha256`. Uninstall compares against those, and falls back to the templates for old records.
- #4: `Path(args.home).expanduser().resolve()` in both main()s.
- #5: `_write_json` resolves the path first (install, uninstall, add_to_repo). Uninstall restores CLAUDE.md with copyfile and unlink, not rename.
- #6: isinstance guards in `_is_ours` and verify.
- #7: on reinstall, if CLAUDE.md no longer matches the recorded hash (the user edited it), the new backup becomes the one restored. For a setting replaced with --force whose value differs from the recorded installed value, the user's value is what gets restored.
- #8: unused_tools exits 2 when the folder is missing and 1 when it has no transcripts.

## Open items
- PR #9: wait for CI to be green on Ubuntu and Windows.
- Merge of PR #9: on hold until the user confirms in this session. The instruction came from an automated task message, and the "standing approval" was only recorded in this file by an earlier session. Once the user confirms: mark the PR ready, then merge.
- Not checked: real Claude Code hook behavior on Windows, and the read-only CLAUDE.md variant of #1 (the sandbox runs as root).
