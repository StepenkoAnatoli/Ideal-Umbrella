# Ideal-Umbrella bug sweep — resume point (2026-10-25)

## Request (user)
"Make sure there are no bugs/errors and the read me is updated."

## Done
- PR clean-up finished earlier today: #4, #6, #7, #8 merged; #3, #5 closed. Main has CI on Ubuntu and Windows.
- Checks run on main (7a37497):
  - pytest 30 passed; keyline 34/34.
  - The four JSON configs are valid.
  - `bash -n config/cloud-setup.sh` passes.
  - pyflakes: only unused imports, now removed. The `claude` redefinition in `scripts/tokentest.py` is an intended fallback.
- README checked against the code. Every number and default matches (deny list of 6, TAIL_BYTES 4 MB, thresholds 150000/25000, CLAUDE.md 224 tokens with o200k). Fixed on branch `ccr-da04ab7d-6rorpx` (commit b101cbe):
  - The `--force` line was missing from the install commands.
  - The cloud-setup section didn't mention its extra cloud-only rule.
  - The manual undo steps didn't say to delete `install-record.json`.
  - The research folder listing was incomplete.
- An independent review found 8 bugs. Repro, fix and test for each are in `research/review-findings-2026-10-25.md`. None is fixed yet.

## Next: fix the findings, in this order, each with a test that fails on the old code
1. HIGH: install writes settings.json before the hook copy and the CLAUDE.md read. A failure partway leaves a hook pointing at a missing file, and every prompt is blocked. Fix: do all reads and checks first, write settings.json last.
2. HIGH: a second uninstall runs without the record and deletes the user's own values that match the template, and an identical CLAUDE.md. Fix: keep a marker after uninstall, or make no-record mode require proof the hook is installed.
3. MEDIUM: uninstall compares against the current templates, not the values that were installed (after a git pull). Fix: store the installed values in the record.
4. MEDIUM: `--home .` or a literal `~` writes a relative hook path. Fix: resolve and expanduser `--home`.
5. MEDIUM: a symlinked settings.json is replaced by a regular file. Fix: write through to the link's target.
6. LOW: a malformed hook entry crashes install, uninstall and verify.
7. LOW: reinstall then uninstall drops later CLAUDE.md edits.
8. LOW: `unused_tools.py` treats a mistyped folder as "no denied tool was used". Fix: error out when the folder is missing.
After the fixes: run pytest and the keyline suite, update CHANGELOG/README where behavior changes, push to the same branch and PR, merge when CI is green (the user approved merging).

## Decisions
- The user approved making a kept user value a verify warning (done in #8).
- The user gave standing approval to merge and close PRs as needed.
