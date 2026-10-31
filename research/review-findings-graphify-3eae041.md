# Review of branch graphify-ideas at 3eae041 (2026-10-27, twenty-second pass)

A breaker review of the diff `origin/main...3eae041` by one fresh-context reviewer. It ran on the
session's default model because the Fable usage limit was reached again. Its report and repro
scripts are in the session scratchpad, not in the repo: `review22-findings.md` and `review22/`
(`repro/` c1, c2; `mut/mutate.py` n01-n06; `fuzz/sfuzz.py` settings with failed runs, 0 of 1500
seeds with problems; `fuzz/rfuzz.py` record field types, 0 tracebacks in 800 seeds;
`fuzz/md/mdfuzz.py`, 0 of 600). New ground in this pass: the pass-21 fixes (`_merge_record`
dropping a kept value for a key the run adds, the UTF-16 record error, the dangling-link advice).

The findings of passes 1 to 21 were checked and not reported again
(`research/review-findings-graphify-5a18f22.md` to `-195c85a.md`).

Status: no behaviour defect was found; all three findings are fixed class-wide in the next commit
on PR #27.
- pytest (3.13 and 3.10), keyline, pyflakes, the JSON checks, the CRLF copy and the suite with
  `write_text` forced to CRLF pass.
- Mutants (session scratchpad `fix22/mut.py`): the reviewer's n01, n02, n03, n05 and n06, plus
  b1-b3 and k1-k3 on the offset fix, are killed. n04 (`e.start` to `e.end`) no longer applies to
  the new code; b3 is its equivalent.

Counts: 0 high, 0 medium, 1 low (T1), 2 info (I1, I2).

## Low

T1. Finding: the tests for the pass-20/21 error advice checked only that one wording was absent
    ("remove it", "delete it"). Mutants that drop `RECORD_KEPT` from the UTF-16 record error
    (n01), or turn the dangling-link advice into "delete it first" (n02 install.py, n03
    add_to_repo.py), passed all 952 tests.

    Fixed: every dangling-link test (5 in test_install.py, 1 in test_uninstall.py, 2 in
    test_add_to_repo.py) also asserts "put the target back" is in the error; the UTF-16 test
    asserts `RECORD_KEPT`; `test_the_error_for_a_bad_record_does_not_advise_deleting_it` asserts
    the whole `RECORD_ADVICE` instead of "fix it".

    Other hits: the other tests of pass-20/21 messages already assert the required words
    ("is not UTF-8", "nothing written").

## Info

I1. Finding: "is not UTF-8 (... at byte N)" was 3 too low for a file that starts with a UTF-8
    BOM: `utf-8-sig` counts from after the BOM. Seen in `read_record` and both `_read_json`.

    Fixed: install.py and add_to_repo.py read the bytes once, decode them with `utf-8-sig` and
    report the offset through `_bad_byte`, which adds the BOM's 3 bytes. The keyline readers and
    verify-tokens keep their text-mode read (it translates line ends, which their counts
    depend on) and look for the BOM only when building the error.

    Tests: `test_the_offset_of_a_byte_that_is_not_utf8_counts_a_bom` for install (settings and
    record), add_to_repo, keyline_lint, keyline_check and verify-tokens, each with and without a
    BOM. The BOM kinds failed before the fix.

    Other hits: `keyline/keyline_lint.py` `read`, `keyline/keyline_check.py` `read` and
    `config/verify-tokens.py` (which printed the codec's own "position N", also after the BOM)
    are fixed the same way. `keyline/measure.py` and `scripts/ledger.py` give no offset.

I2. Finding: nothing tested a hand-deleted key under a record from before "installed" existed;
    mutant n05 (pop `replaced` only when the record has `installed`) survived. The code was
    right.

    Fixed: `test_a_key_deleted_by_hand_after_a_forced_install_stays_deleted` is parametrised
    with a `before-installed` kind that removes `installed` from the record after the first
    install.

## Prevention

Premortem row 83: a test for a message asserts the words that must be there, not only ones that
must not; a position named in an error is checked against the raw file, BOM included.
