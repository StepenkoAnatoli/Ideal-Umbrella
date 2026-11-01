# Review of branch graphify-ideas at 881e367 (2026-10-31, forty-second pass)

One fresh-context reviewer did a breaker review of the diff `origin/main...881e367`, with real installs and
uninstalls of the head and mutant trees.

Its report and repro scripts are in the session scratchpad, not in the repo: `review42-findings.md` and
`review42/`. That folder holds:
- `repro/r1_notes_locked.sh` (L3): `add_to_repo.py` run as another user on a repo whose `notes` links into a
  folder that user may not search;
- `out/`: every output, including the mutant runs (`mut_a_reversed_os.out`, `mut_b_badrecord.out`).
L2 was found with pass 41's `review41/repro/w1_real.py` and `c1_clauses.py`.

New ground in this pass: pass 41's README wording and tests, and the merge of main (379d00c) into
`config/add_to_repo.py`, `hooks/context_check.py` and the source-rule tests.

The findings of passes 1 to 41 were checked and are not reported again (`research/review-findings-graphify-5a18f22.md` to `-2735a08.md`).

**Status:** no defect in install or uninstall (`config/install.py` and `config/uninstall.py` are byte-equal to
f6079da's). Three low findings: a test rule (L1), one README clause (L2) and a false notice in the merged
`add_to_repo.py` (L3). All are fixed in the next commit on PR #27.

Checks run on the fixed tree, all passing:
- pytest on 3.13, on 3.10, and on a real 3.14 (with an 8 MB stack and with an unlimited one);
- keyline, pyflakes and the JSON checks;
- the CRLF copy (`crlf-p44`), with and without `write_text` forced to CRLF, and the forced run in the tree.

## L1 (low, test): the `errors=` source rule took the OS choice whichever way round

**Defect class:** a test that would not catch a regression.

**Evidence:** `_never_fails_to_encode` in `tests/test_source_rules.py` (added by the merge) accepted any
conditional whose two branches were `backslashreplace` and `surrogateescape`, without looking at the condition.
The reviewer's mutant swapped `!=` for `==` in `config/add_to_repo.py` (`surrogateescape` on Windows), and the
rule passed. On Windows a path can hold a lone surrogate (NTFS names are UTF-16); `surrogateescape` encodes only
U+DC80 to U+DCFF, so the print would end in `UnicodeEncodeError`, the traceback rule 3 exists to prevent. The
CHANGELOG merge line claimed the choice was checked.

**Fixed:**
- The rule now needs the condition to be `os.name` compared (`==` or `!=`) with `"nt"`, `backslashreplace` on
  the Windows branch, and `backslashreplace` or `surrogateescape` on the other.
- `test_the_encode_rule_wants_backslashreplace_on_windows` checks the rule on 8 expressions: both right forms,
  both reversed forms, a `sys.platform` test, an `os.name != "posix"` test and a bare `surrogateescape`. It
  failed 4 rows before the fix.
- Mutants (scratchpad `fix42/mut.py`): R1, the reviewer's swap in `add_to_repo.py`, now fails
  `test_scripts_that_print_set_utf8_stdout`. R2 (drop the `"nt"` check) and R3 (ignore `==` against `!=`) fail
  the new test. All three are killed.
- The CHANGELOG merge line now says `backslashreplace` on Windows and `surrogateescape` elsewhere.

**Other hits:** the only `errors=` chosen by OS is `config/add_to_repo.py`'s `reconfigure`; every other script uses
the constant `backslashreplace`.

## L2 (low, docs): a text that is only a bare CR, a CRLF line added above and the blank line deleted

**Defect class:** a doc claims more than the code does.

**Evidence:** `\r` is installed, so `joined` is `\n\n`. A line `note` is added on top with CRLF, and the blank
line is deleted (in either order). The bytes above the section are then `note\r\n\r\n`, and uninstall gives
`note`: it loses `\r\n\r`. The README's parenthetical said such a text "loses it" (the CR), which reads as
`note\r\n`. The bytes are the same as the text `note` with no final line break, installed and converted to CRLF.
That reading is already pinned by `test_line_endings_changed_after_install_leave_no_trace_on_uninstall`
(`mine-convert1-mine`). This is pass 37's trade for bytes that fit two histories.

**Fixed (docs and test):**
- README: "a text that is only that CR, with that blank line also deleted, reads as a line with no final line
  break converted to CRLF, and loses the CR and the line break typed before it".
- `test_a_text_that_is_only_a_bare_cr_with_the_blank_line_deleted_reads_as_a_crlf_conversion` states the history
  of the clause.
- No mutant can fail only this test: the same bytes are pinned by the conversion test above. Mutant U1 (keep the
  CR for these bytes) fails both, and also `test_a_line_added_with_lf_above_a_file_turned_to_crlf_leaves_no_separator`.

**Other hits:** none. The reviewer's 5-piece model check found only this row outside the README's clauses.

## L3 (low, false notice): a `notes` link that cannot be looked through was called "a symlink to a missing target"

**Defect class:** `os.path.exists()` taken for "missing" when the look is refused (pass 24's class).

**Evidence:** main's learnings copy decided its `notes` pair with `_is_link(p) and not os.path.exists(p)`.
`os.path.exists` says False on EACCES, so `repo/notes` linking into a folder only root may search got the note
"is a symlink to a missing target". That advises putting back a target that is in place. The core files above it
use `_look`, which says "cannot look at". The exit code was 0 and nothing was lost.

**Fixed:**
- `add_to_repo.py` looks at `notes` and `notes/learnings.md` with `_look`, as it does the core files. A
  `ValueError` from it becomes the note "notes/learnings.md not copied: cannot look at <path> (<reason>)", still
  a notice and exit 0. Whether the file is there is also decided by `_look`.
- `test_a_learnings_link_into_a_folder_that_cannot_be_searched_is_not_called_missing` (a link on `notes` and a
  link on `notes/learnings.md`) failed both cases before the fix.
- Mutant N1 (main's form put back) fails both cases and nothing else. N2 (`os.path.exists` for "is there") is
  equivalent: by that line the loop has already looked at both paths without a refusal.
- README line 99 lists "a link into a folder it may not search" among the cases that get a note.

**Other hits:**
- The other `os.path.exists` calls in `add_to_repo.py` run after the `_look` checks of the same paths:
  settings and hook reads, the read-only check, and `_write_bytes`.
- `hooks/context_check.py` (main's) checks its own state and log files with `os.path.exists`. A hook that cannot
  look at its state takes it for none, which is the hook's best-effort rule. It was not changed.

## Info

- **I1.** CI ran on 881e367 and is green on all five jobs.
- **I2.** Pass 41's mutants T1, T3 and T6 each still fail only their new rows; H is equivalent.
- **I3.** `_named_handlers` catches a dropped `RecursionError` in `BAD_RECORD` (the reviewer's mutant).
- **I4.** The merged `add_to_repo.py` raises every `ValueError` before the first write, keeps both sides'
  checks, and its README and CHANGELOG lines match the code, apart from L1 and L3.
- **I5 to I7.** Pass 41's reruns match its record. No lost user byte outside the stated exceptions and trades.

## Prevention

When a rule accepts a choice made by a condition, check the condition too. When code comes in from another
branch, run this branch's rules (`_look`, not `exists()`) over it as well as its tests.
