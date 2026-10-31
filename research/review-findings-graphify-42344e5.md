# Review of branch graphify-ideas at 42344e5 (2026-10-27, thirty-second pass)

One fresh-context reviewer did a breaker review of the diff `origin/main...42344e5`. It ran on the
session's default model because the Fable usage limit was reached again. A container restart cut its
first mutant run short; it was resumed and rerun.

Its report and repro scripts are in the session scratchpad, not in the repo: `review32b-findings.md` and
`review32b/`. That folder holds:
- `repro/r1_*.py` to `repro/r19_*.py` (outputs in `rN.out`), each taking a source tree;
- `mut/`: an AST mutant generator over the lines the PR changed in the install, uninstall,
  add_to_repo, verify-tokens, ledger, transcript and measure scripts (1,000+ mutants; the 155
  non-equivalent survivors of per-file runs were rerun on the full suite, and 147 survived it).

New ground in this pass: mutation testing of every line the PR changed, not only the latest commit.

The findings of passes 1 to 31 were checked and are not reported again (`research/review-findings-graphify-5a18f22.md` to `-5a72af2.md`).

**Status:** one wrong result in the code, found while writing the tests (F1 below); the rest are test
gaps. All are fixed in the next commit on PR #27.

What the reviewer confirmed:
- CI at 42344e5 is green on all five jobs.
- The pass-31 test reaches both its branches on Linux and Windows; the pass-31 CHANGELOG lines and record match the code.

Checks run on the fixed tree, all passing:
- pytest on 3.13, on 3.10, and on a real 3.14 (with an 8 MB stack and with an unlimited one);
- keyline, pyflakes and the JSON checks;
- the CRLF copy, and the suite with `write_text` forced to CRLF.

Mutants are in the session scratchpad, `fix32/` (`muta.py`, `mutb.py`, `mutc.py`, output `all.out`), and all
of them are killed.

**Counts:** 0 high, 5 medium (test gaps), 7 low (F1: code defect; L1: docs and a test; L2-L6: test gaps), 9 info (no action).

## Found while fixing

### F1. Uninstall dropped the user's final line break when the blank line above the section was deleted

**Finding:** over a CLAUDE.md that ends in a line break (`mine\n`), install adds one more break and the
section, and records `joined` as one break. If the user then deletes that blank line, the break left
above the section is the user's own, but uninstall took it: the file became `mine`. README line 122
says your own text stays byte for byte.

**Fixed (code):** `_rest_without_section` takes a single recorded break only when the text above still
ends in a break after it (install adds a single break only after text that already ends in one).

**Test (failing first):** `test_a_deleted_blank_line_above_the_section_keeps_the_users_final_line_break`
(LF and CRLF). Mutants c1 (the guard dropped) and c2 (the count term dropped) are killed.

**Other hits:** `joined` is read nowhere else; install only writes it.

## Medium (test gaps; the code was right)

1. **M1, U188:** with the blank line deleted above the section of a file that had no final break, a
   regression cut into the user's text (`min`). Test: `test_a_deleted_blank_line_above_the_section_costs_none_of_the_users_text` (LF and CRLF).
2. **M2, I245:** a fenced copy of the rules more than `span` lines below the top was taken for a hand
   copy. Test: a new `rules-far-below-the-top` case of `test_a_fenced_copy_of_the_rules_is_an_example_not_wrapped`.
3. **M3, I382 and I542:** a ``` block holding a `~~~` line (and the reverse) with example markers.
   Tests: two new cases of `test_marker_lines_inside_a_code_fence_are_an_example_not_the_section`.
4. **M4, I661 and I588:** a copy of the rules that does not start a line. Test:
   `test_a_copy_of_the_rules_that_does_not_start_a_line_is_not_wrapped`.
5. **M5, U306:** after an uninstall that left a non-UTF-8 CLAUDE.md, a rerun once the byte is fixed
   must still remove the section. Test: `test_a_non_utf8_claude_md_with_the_section_is_undone_once_the_byte_is_fixed`.

## Low

### L1. A hand copy at the very end of the file without its final line break is added once more

**Finding:** README line 70 said an unmarked copy of the rules is wrapped rather than added twice. A copy
missing only its final line break is added as a section.

**Fixed (docs and test):** wrapping it would give the rules a line break that uninstall cannot take back
byte for byte, while adding a section round-trips exactly. README line 70 now names this case beside the
mixed-line-ending one (E4 in `-032a6bf.md`). Test:
`test_a_hand_copy_at_the_end_without_its_final_line_break_is_added_as_a_section` (round trip, no backup left).

### L2. Tracebacks a regression would bring back (tests added)

A47 and A50 (add_to_repo without or with a missing repo), L141 and L142 (ledger lines of another type),
U45 (`"joined": 5`), I696 and I627 (`--verify-only` without a readable record), I327 and U571 (an
OSError while finding the home), I609 (a `pending` record naming a key the user deleted, install and
uninstall). Each test asserts the exit code and the one-line message.

### L3. Notices a regression could drop or falsify (tests added or tightened)

V265 (and the `except FileNotFoundError` variant), A90, U269, U443, U493, U98, U543, U545, I439, I656,
I1060: each notice is now asserted word for word.

### L4. add_to_repo's settings depth limit (A135)

Test: `test_settings_nested_up_to_the_limit_are_read` (100 levels read, 101 refused), as for install.

### L5. A CRLF hand copy of the rules (I783)

Test: `test_a_hand_copy_in_a_crlf_file_is_wrapped_not_added_again`.

### L6. List items in record fields (I597 and I600)

`deny_added: ["Artifact", 5]` and `created: [5]` join the malformed-record cases.

## Info (no action)

- I595 is killed by the CRLF tree (Windows CI).
- Rules from main the PR did not touch (measure's missing-argument wording, the ValueError skip in the
  transcript readers, plugin_cost's error terms) stay outside this PR.
- `--home relhome` from a deleted current folder names no path in its error; the message comes from the OS.
- The remaining survivors were read and are equivalent or wording-only.

## Prevention

Mutation testing over every line the PR changed, not only the newest commit, found gaps that 31 passes
of targeted review had not. The next pass reruns it over the full diff.
