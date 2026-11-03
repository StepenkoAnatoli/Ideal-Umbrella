# Fresh review of PR #39 (ccr-fix-general, head 4c3992c)

Scope: the diff vs main, read fresh: bugs the fixes introduced, neighbours they missed, docs that no longer match. Not re-raised (as asked): N3, N7, the Windows `$` in `_quote`, add_to_repo making no backup. None of the findings below opens a new failure path for those.

## Findings

| ID | Sev | File:line (at 4c3992c) | Class | Failure |
|----|-----|-----------|-------|---------|
| F1 | medium | config/install.py verify (~1312) | missed neighbour of A3 (strict hook match) | Install keeps a user's own `UserPromptSubmit` hook that names `context_check.py`, but verify still matched any command naming it and checked that one's path: settings with `python3 ~/tools/my_context_check.py --mine` beside ours made a good install print `[FAIL]` and exit 1. |
| F2 | medium | keyline/keyline_check.py:268 (NEG_HE) | missed neighbour of B2 (negation counting); fail-open | `אל(?=[ \t]+ת…)` counted אל תוך ("into"), אל תחת, אל תל אביב as negations. "Do not copy v2.1 into the folder." -> "העתיקו את v2.1 אל תוך התיקייה." gave PASS 1->1 (negation lost, not reported); the reverse gave a false FAIL 1->0. |
| F3 | low | config/uninstall.py undo_settings | introduced by A3 | A hook wired by hand to `ballast/context_check.py` in a non-template event (`PostToolUse`, documented as supported) is left, while uninstall deletes the file it runs; nothing told the user, and the hook then errors on every call. |
| F4 | low | config/add_to_repo.py A1 check | introduced by A1; wrong message | A repository inside `CLAUDE_CONFIG_DIR` (a plugin marketplace clone) or a home holding `~/.claude` was refused with "replace the link with a plain file", though there is no link. |
| F5 | low | config/cloud-setup.sh section write | halfway state, introduced by A7 | `cat tmp > file; rm tmp` then `>> file`: a write cut short (full disk) left a begin marker without an end, and every later run refused the file as broken markers. |

Repros: F1 `install.py --home H` with the settings above (exit 1); F2 `keyline_check` on the sentence pair above; F3 settings with a `PostToolUse` hook running `~/.claude/ballast/context_check.py`, then uninstall; F4 `git init $CLAUDE_CONFIG_DIR/plugins/x && add_to_repo.py` there; F5 `bash -c 'trap "" XFSZ; ulimit -f 1; exec bash config/cloud-setup.sh'` over an existing CLAUDE.md.

## Fixes

Each test was run on the old code first and failed for the stated reason.

| ID | Fix | Test |
|----|-----|------|
| F1 | verify checks the hooks that are ours (`_is_our_hook`) when any are; only with none does it judge the others, so a lone foreign hook still fails | tests/test_install.py `test_a_users_own_context_check_hook_beside_ours_verifies` (2 commands), guard `test_a_context_check_hook_that_is_not_ours_alone_still_fails_verification` |
| F2 | אל before תוך, תחת, תל (whole word) is not counted; comment names the remaining construct-noun limit (אל תחנה), also in keyline/README | tests/test_keyline_check.py: 3 sentences in `test_hebrew_al_as_to_is_not_a_negation`, 3 rows in `test_a_negation_survives_or_is_reported_in_both_directions` |
| F3 | uninstall leaves the hand-wired hook and prints a note naming the event and telling the user to delete it | tests/test_uninstall.py `test_a_users_own_hook_that_names_context_check_is_left_alone` (note iff the command runs `ballast/context_check.py`) |
| F4 | when the plain path (repo resolved, no link below it) already lies in the config folder, the message says the repository is inside Claude Code's own folder; otherwise the symlink message stays | tests/test_add_to_repo.py `test_a_repository_inside_the_claude_config_folder_is_refused_without_naming_a_symlink` |
| F5 | the whole file is built in a temp file beside the real target (links resolved), given its mode, and moved over it; any failed step removes the temp file, notes it on stderr and exits 0 | tests/test_cloud_setup.py `test_a_write_cut_short_leaves_the_file_as_it_was` |

Class searches: the only loose `"context_check.py" in` match left is verify's, by design; cloud-setup.sh is the only shell script; NEG_HE/NEG_EN live only in keyline_check.py.

Docs: README (hook matching, add_to_repo refusal, cloud setup), keyline/README (Hebrew negations), CHANGELOG "Fixed" F1-F5.

## Self-check of the fixes (after fa13143)

I re-read the fa13143 diff with the same rules. F1, F3 and F4 hold. Two of the fixes brought problems of their own, and one fix was too narrow:

| ID | Sev | File:line (at 0ae7588) | Class | Failure |
|----|-----|-----------|-------|---------|
| S1 | low | config/cloud-setup.sh:31 | temp wider than its source (A8), brought in by F5 | The temp file beside `CLAUDE.md` was made with the umask (0644). It was narrowed only after awk had copied the user's text into it, so a 0600 file sat in a 0644 copy for a moment. That is the class A8 closed for the installers, and README promises it never happens. |
| S2 | low | config/cloud-setup.sh:54 | regression, brought in by F5 | A `CLAUDE.md` that can be written but not renamed over (a bind mount, or a folder the session may not write) was left without the rules: "not written". The in-place write before F5 had worked there. |
| S3 | medium | keyline/keyline_check.py:269 | F2 too narrow (fail-open) | Docs often put ת-nouns after אל in the construct form: אל תיקיית הפרויקט (to the project folder), אל תפריט ההגדרות (to the settings menu), אל תבנית, אל תצורת. These still counted as "don't". "Do not copy v2.1 to the project folder." rendered as "העתיקו את v2.1 אל תיקיית הפרויקט." passed with the negation lost. |

| ID | Fix | Test (each failed on 0ae7588 for the stated reason) |
|----|-----|------|
| S1 | The temp file is made under `umask 077` before anything is written to it, then given the file's mode. A new file gets the umask default. | tests/test_cloud_setup.py `test_the_temp_file_is_never_more_open_than_the_file_it_replaces`: an awk shim records the temp file's mode. It was 644 before the fix. |
| S2 | When the temp file cannot be made beside `CLAUDE.md` it goes to TMPDIR. When the rename fails, the file is written in place. If that write stops short, the note names the temp file, which holds the whole text. | tests/test_cloud_setup.py `test_a_file_that_cannot_be_moved_over_is_still_written`: an `mv` shim that fails. |
| S3 | `AL_TO` lists תוך, תחת, תל and the common docs ת-nouns (absolute and construct forms). A listed word that is also a verb only fails closed. | tests/test_keyline_check.py: 8 noun sentences and 2 lost-negation rows, plus verb guards אל תשבית, אל תמחקו. |

## Checks

See the PR #39 body for the commit and the exact results of `python -m pytest -q`, `python -I keyline/tests/run_tests.py` and `python -m pyflakes $(git ls-files '*.py')`.
