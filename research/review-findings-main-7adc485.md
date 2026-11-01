# Review of main 7adc485 (2026-11-01, ninth full pass)

This is a fresh full review of main at `7adc4858a76a59224315579f33f12e29688ddeda`, the merge of PR #32 (review 8's fixes). Main had not moved when the review started.
Review 8 (`research/review-findings-main-bcc441c.md`, including its self-review) was used as a checklist only: each old finding was re-run on this tree, and only those that still hold are listed, with their old number.

**Baseline on this tree** (Python 3.13, run as root):

| Check | Result |
|---|---|
| pytest | 1512 passed, 14 skipped (with tiktoken installed, as CI does; without it 4 fail, see B5) |
| keyline suite (`python -I keyline/tests/run_tests.py`) | 35/35 |
| pyflakes on `git ls-files '*.py'` | clean |
| The three JSON files CI checks | parse |
| Working tree | clean |

## Method

- Two fresh-context reviewers ran in parallel: **A** read `keyline/` and `scripts/`, **B** read `config/`, `hooks/`, `tests/`, CI and docs. Both started from the resume point and the review-8 report, and paid most attention to the code review 8's fixes changed:
  - `keyline/keyline_check.py`: `_unextended`, `PAIR_FAMILY`, the URL extraction and the "No. 5" rule;
  - `config/install.py` and `config/uninstall.py`: `settings_created` and the "settings.json away" path.
- Every medium was reproduced again in the main session with `python -I`. Each keyline medium was also run against the bcc441c tree (`git archive bcc441c keyline`) to tell regressions from older defects. Two lows (A4, A5) were reproduced there too.
- Install and uninstall probes ran only with `--home` and `HOME`/`CLAUDE_CONFIG_DIR` pointing at a fresh temp dir. The real `~/.claude` was never touched.
- Mutation runs ran on copies, not on the repo.
- Probe scripts are in the session scratchpad (`review9/a/`, `review9/b/`), not in the repo. Line numbers are 7adc485's.
- No code was changed. The fixes wait for the user.

**Counts:**

- 0 high.
- 4 medium: A1, A2 and A3 in keyline, and B1 in config. A1 and A2 are regressions from review 8's fixes. A3 predates review 8. B1 is a gap in review 8's `settings_created` fix.
- 12 low: 8 keyline/scripts (A4-A9 and two old neighbours), 4 config/tests (B2-B5).
- 7 informational.

**Pattern:** every medium is a **neighbour of a previous fix**, the recurring class the resume point names. Review 8's fixes closed the reported cases but used deny-lists or context rules that miss the next case over (URL end, "No." context, underscore emphasis, a stale record field). The mutation runs on both sides also found **fixes without tests**: 6 surviving mutations in keyline_check.py and 8 in install/uninstall.

`$KC` below is this one-liner, run from the repo root:

```
KC='import sys;sys.path.insert(0,"keyline");import keyline_check as k;print(k.check(sys.argv[1],sys.argv[2]))'
```

## High

None.

## Medium

### A1. (new, regression) A URL token swallows characters glued after it, so a faithful rendering fails

- **Where:** `keyline/keyline_check.py:92`, the URL body ``[^\s<>"'`HEB]+``, and `_trim_url` at `:225`.
- **Repro:** `python3 -I -c "$KC" 'See https://x.io/a now' 'ראו **https://x.io/a** עכשיו'`
- **Observed:** ok=False, missing `['https://x.io/a']`. The rendering's token is `https://x.io/a**`. At bcc441c the same check passes.
- **Expected:** ok=True.
- **Same failure** for a URL followed by `*…*` emphasis, curly quotes, an em dash and a word, "…", a table `|`, and RLM, LRM, ZWSP, U+202C or U+2069.
- **Class:** neighbour of a previous fix; a deny-list where an allow-list is needed (the URL body lists what it refuses, not what a URL may hold).
- **Smallest fix:** build the URL body from RFC 3986 characters plus non-Hebrew letters, ``[\w\-.~:/?#\[\]@!$&()*+,;=%]`` with Hebrew excluded, and let `_trim_url` also strip a trailing `*` or `_`. Add the repro as a test.

### A2. (new, regression of the old #15/S4 fix) "No." before a digit loses its negation, so a dropped "No" passes

- **Where:** `keyline/keyline_check.py:163` `NUMBER_SIGN`, used by the negation count around `:460-476` (`_after_sentence_end`).
- **Repro:** `python3 -I -c "$KC" 'Q: Fixed? A: No. 5 tests still fail.' 'Q: Fixed? A: 5 tests still fail.'`
- **Observed:** ok=True, 0 negations on both sides. At bcc441c it fails correctly (1 negation to 0).
- **Expected:** ok=False.
- **Same fail-open** for `**Fixed?** No. 5`, `Fixed? — No. 5`, `He asked "fixed?" No. 5`, `(no. 3 …)`, `- No. 5 servers are down` (reproduced), `## No. 5 is down` (which contradicts the README), and `Done? Not yet, no. 3 tables remain.`
- **Class:** neighbour of a previous fix (S4); a context rule written as an allow-list of sentence boundaries, so every boundary not listed reads "No." as a number sign.
- **Smallest fix:** read "No." as a number sign only when the previous non-space character on the line is a letter or digit ("Ticket No. 5"). In every other case count it as a negation. Add the repros as tests.

### A3. (new, predates review 8) Underscore emphasis hides every invariant

- **Where:** `keyline/keyline_check.py:49-50`. "_" is a word character in the L and R boundaries.
- **Repro:** `python3 -I -c "$KC" 'Deploy to _Paris_ at _14:30_ with _v2.1_ and _5_ hosts, ticket API-7' 'Deploy to _Berlin_ at _16:00_ with _v9.9_ and _7_ hosts, ticket API-7'`
- **Observed:** ok=True, with only 2 invariants found. The same result at bcc441c.
- **Expected:** ok=False (city, time, version and count all changed).
- **Other directions:** with no plain invariant at all the result is INCONCLUSIVE. A plain source against an emphasised rendering fails closed.
- **Class:** neighbour of a previous fix (S34/S83 handled "_" for hedges and negations only).
- **Smallest fix:** strip edge underscores (`(?<![^\W_])_+(?=\S)` and its mirror) from both texts before scanning. This also fixes the old #10 neighbour below.

### B1. (new, gap in review 8's fix) A stale `settings_created` makes uninstall delete a settings.json the user wrote

- **Where:** `config/install.py:1011` in `_merge_record`, which keeps the old `settings_created` whenever the old record was not uninstalled:
  `if new.get("settings_created") is True or (old.get("settings_created") is True and not old.get("uninstalled")):`
- **Repro** (temp home, `--home $H`, `HOME`/`CLAUDE_CONFIG_DIR` set to it):
  1. `install.py` with no settings.json. The record says `settings_created: true`.
  2. `rm settings.json`; the user writes `{"permissions":{"deny":["Artifact"]}}`.
  3. `install.py` again. The record still says `settings_created: true`.
  4. `uninstall.py`.
- **Observed:** "settings.json deleted (the install created it)". The user's file is gone, with no pre-uninstall backup. The first-wins merge of `deny_added` also counts the user's `Artifact` deny as the installer's. The content survives only in the backup the second install wrote (`settings.json.bak-…`), which the uninstall does not mention.
- **Expected:** the file stays, with only the installer's changes undone, and a backup is written.
- **Variant:** the first install fails at its settings write, then the user creates the file. Same result.
- **Severity:** medium rather than low: it deletes a file the user wrote, with a message saying the installer created it. The data can be recovered only by noticing the install-time backup.
- **Class:** neighbour of a previous fix (C1/C2); a stale record field: a field that describes a file is kept after the file was replaced.
- **Smallest fix:** at `:1011`, keep the old True only when the file still holds the installer's own changes (for example, its hook entry), or when this run is the `settings_away` case. Add the repro as a test (it also kills mutation M2, see B4).

## Low

### keyline/ and scripts/ (reviewer A)

- **A4. `_token_at` look-ahead makes the check quadratic.** `keyline_check.py:243`, called from `_unextended` (`:270`, `:276`). `check("Meet Ab today.", "Meet "+"Ab-"*n+"Ab today.")` took 0.4 s for n=2500, 1.5 s for n=5000 and 6.3 s for n=10000 (reproduced). Reviewer A measured 37.8 s for n=20000 (60 KB), past the 30 s hook timeout. Class: neighbour of a previous fix (S6/S7); unbounded look-ahead in a per-token loop. Fix: `INVARIANT.match(text, pos, pos+256)`, and return early when `PAIR_FAMILY.get(kind)` is None.
- **A5. A list marker followed only by trailing whitespace is stripped.** `keyline_check.py:132` `LIST_MARKER` (`[ \t]+`) and `keyline_lint.py:41-42`. `check('Errors last week:\n12.  \nAll in API.', '…13.  …')` gives ok=True (reproduced); a markdown hard break leaves exactly those spaces. Class: neighbour of old #9; a separator is required but not content after it. Fix: `[ \t]+(?=\S)` in both files.
- **A6. The extension refusal sets differ between the two sides.** `keyline_check.py:65` `EXT_RIGHT` and `:280-283` for the left side. `check('Open ab.txt now','Open ab.txt=1 now')` gives ok=True. Also open on the right: `ab.txt*`, `ab.txt&x`, `API(x)`, `ab.txt,v`, `API$x`. Open on the left: `x@ab.txt`, `#API`, `+v2.1`, `C:notes/a.txt`. `API#x` fails while `#API` passes. Class: neighbour of S1; incomplete deny-list. Fix: one shared joiner set for both sides.
- **A7. "Monday-Friday" is one proper token.** `check('Mon open Monday-Friday','Mon open Monday to Friday')` fails, missing `Monday-Friday` (fails closed). The Hebrew form fails the same way. Class: halfway state; the `PAIR_FAMILY` calendar rule (`:67-68`, `:258-267`) is applied on the rendering side only. Fix: split a source proper token at "-" when both parts are in `CALENDAR`.
- **A8. measure.py exits 1 where its docstring says 2.** `keyline/measure.py:11-13` promises exit 2 for an argument that cannot be read. The walk's `onerror` (`:48`, through `_unlisted` `:30-32`) turns it into "skip … nothing counted", exit 1. Class: absent is not empty. Fix: scandir each argument up front and exit 2 on OSError (or correct the docstring).
- **A9. Fix without test: 6 surviving mutations of keyline_check.py.** Each left all tests green: (1) the left-side pair in `_unextended` without the `glued` check; (2) the `date T\d` pass at `:272` removed; (3) the `_pairs` calendar check needing only one side; (4) `NUMBER_SIGN` `[ \t]*` changed to `\s*` (S4 claimed a test for this); (5) `PAIR_FAMILY` without "ident"; (6) without "snake". 14 other mutations were killed. Class: fix without test. Fix: one test per survivor.
- **(old #15 neighbour) "May" as a sentence-start subject.** `check('May, June and July are busy.','מאי, יוני ויולי עמוסים.')` fails, missing_hedges `['possibility']`; "May and June…" and "May was busy." too. Fix: add `[ \t]*,` and a following month name to `MONTH_AFTER` (`:347`).
- **(old #10 neighbour) Underscore-wrapped URL.** `_https://x.io/a_` against `_http://…_` passes, because the token is `//x.io/a_`. Fixed with A3.

### config/, hooks/, tests/ (reviewer B)

- **B2. The C1 drop is skipped when `replaced` is set, so a later user settings.json is deleted.** `config/uninstall.py:455` (`… and not record.get("replaced")`); `README.md:137` claims the record part for a created settings.json that is gone is dropped. Repro (`review9/b/pe.sh`): install with no settings.json; the user sets `autoCompactWindow` to 123 and runs `install --force`; the user deletes that key; uninstall stops part way (hook path made a folder) after deleting settings.json; reruns say "settings left for a later run"; the user writes a new settings.json; uninstall deletes it ("the install created it"). Class: halfway state; neighbour of C1. Fix: drop the `replaced` condition when `settings_created` is True (or mark the record before the delete), and correct README:137.
- **B3. The "settings away" check ignores `uninstalled`.** `config/install.py:1059`. Repro (`review9/b/p2.sh` case 8): install with no settings.json; the user changes `autoCompactWindow`; uninstall leaves it, so the record keeps leftover fields; `rm settings.json`; install says "settings.json not found, though the install record holds changes", does not mark the new file as created; the next uninstall leaves `{}` plus a backup. Class: absent is not empty (leftover fields of an uninstalled record read as live). Fix: skip the away check when `old_record.get("uninstalled")`.
- **B4. Fix without test: 8 surviving mutations of install/uninstall.** M2 (`_merge_record` without `not uninstalled`, install.py:1011), M6 (C1 branch ignores `replaced`, uninstall.py:455), M7 (away check uses only `added_keys`, install.py:1059), M8 (`_changes_claude_md` counts backup deletes, uninstall.py ~258), M10 (`replace_json` keeps the progress line on failure, install.py ~568-590), M13 (`settings_missing` without `--force` untested, uninstall.py ~451), M14 (`replace_json` deletes a reused backup it did not just create), M15 (`SETTINGS_FIELDS` without `created`, uninstall.py:158). Class: fix without test. Fix: one test per survivor; the B1-B3 repros cover M2, M6 and M7.
- **B5. 4 tests in `tests/test_verify_tokens.py` fail instead of skipping without tiktoken.** `test_unreadable_file_is_reported_not_raised` (:19), `test_no_api_count_at_all_is_exit_1` (:68) and the 2 cases of `test_a_file_that_cannot_be_looked_at_is_not_called_missing` (:111). CI installs tiktoken, so CI is green. Class: a missing importorskip next to tests that have it. Fix: patch `count_tiktoken` as the test at :95 does, or `pytest.importorskip("tiktoken")`.

## Informational

- **A10 (keyline notes):** the ISO `T\d` pass at `:272` skips the extension check, so `2026-10-25T99` counts the date as present; "Ticket No 5" (no period) still counts as a negation; "Postgres/MySQL" against "Postgres or MySQL" fails closed (also at bcc441c); `_token_before` (`:249`) has a 64-character window; `scripts/usage_breakdown.py:37-42` `_int("12")` returns 12 though its docstring says text counts as 0.
- **(old #4/S29 residue)** A combining mark: `Ra̱ndi` extracts "Ra", so a change to "Rando" passes. Fix: add combining marks to `WORD` and the name classes.
- **B6.** After a first install failed at its settings write, the next install's notice says settings.json is "not found" though nothing was ever written. The end result is correct. Class: halfway state.
- **B7.** A user's own literal `{}` settings.json is deleted when the record says created. No data is lost; same root cause as B1.
- **I-1 (still holds).** `hooks/context_check.py:137` `parse_int` uses `int()`, so it accepts `" 12 "`, `"1_000"` and non-ASCII digits.
- **I-2 (still holds).** `config/verify-tokens.py:147` divides by the API count; a count of 0 raises `ZeroDivisionError`. Fix: print n/a.
- **I-3 (still holds).** `config/install.py` `_RECORD_FIELDS` (~895-904) does not type-check `uninstalled` or the `claude_md` subfields. Bad types caused no crash in a probe.

## Old findings that no longer hold

- **keyline/scripts:** mediums #1, #2, #3 and #4 (apart from the combining-mark residue); lows 5, 6, 9-14, 16, 18-22, 29, 30, 34, 35; 31 now returns INCONCLUSIVE as intended; perf 32 (0.04 s), 33 (0.57 s), S6 (0.29 s); #8 has a test (test_measure.py:253); #17; N1-N6; S1-S4 (S4 apart from A2); all keyline_hook.py findings. #7's token code is no longer in scope. A fuzz of 3000 malformed transcript events gave no traceback; a self-pass fuzz of 2 x 20000 random sources gave 0 failures.
- **config/hooks/tests:** 23, 24, 25 (read-only files refused before any change), 26, 27, 28, 44, 45, 46, C1, C2, C3, C4 (README qualified; B2 shows its wording is still too broad).
- **Checked, no defect:** an empty, invalid or directory settings.json gives a clean one-line error; a symlinked settings.json the install created is emptied through the link; dry-run output; an old record without `settings_created` keeps `{}`; install twice; install, uninstall, install. `hooks/` and `ci.yml` have not changed since bcc441c.

## Suggested order for fixes (when the user says so)

1. **B1**, then B2 and B3 with it: the only defects that delete a file the user wrote. One change to how `settings_created` survives a merge and a drop, with B4's tests for M2, M6, M7.
2. **A2**: fails open on a dropped negation, the check's core job. Small rule change plus tests.
3. **A3** (with the old #10 neighbour): fails open on every underscore-emphasised invariant.
4. **A1**: fails closed (false alarm), but common in markdown renderings.
5. **A4**: bound the look-ahead (one line).
6. The remaining lows: A5, A6, A7, A8, old #15 neighbour, B5; then the mutation tests in A9 and B4 not already added.
7. Informational notes at the user's discretion.

After the fixes, run a fresh-context self-review of the diff before merging, as the routine requires: this round's mediums are all neighbours of the last round's fixes.

## Fixes (PR #33, on "yes, fix all of them then check your work and merge")

- 18025a0: config/hooks/tests (B1-B7, I-1, I-2, the `uninstalled` part of I-3, the 8 mutations).
- ae22a1c: keyline/scripts (A1-A9, the old #4, #10 and #15 neighbours, A10's ISO and `_int` items) and CHANGELOG.
- **Not fixed on purpose:**
  - **Fail-open risk or no gain:** "Ticket No 5" without a period, since a fix would let "are no 5 servers" lose its negation. "Postgres/MySQL", since splitting at "/" lets a changed path pass. The 64-character `_token_before` window, which only fails closed.
  - **Would lose a value from before the first install:** the general form of B3 (skip the away check for every uninstalled record).
  - **Would turn a note into a stop:** I-3's `claude_md` subfields.

## Self-review of the PR diff (two fresh-context reviewers)

The mediums were reproduced in the main session with `python -I`.

### Keyline and scripts: 2 medium, 6 low, 6 fixes without test (SA)
- **SA1 (medium, regression)**
  - **Defect:** the A6 joiner set (`, = & * $ (`) now applies to the source too. A source token glued by one of these characters is "not alone", so any extended rendering passes.
  - **Repro:** `v2.1,v2.2` against `v2.1-rc,v2.2`; `MODE=fast` against `MODE-X=fast`; `Paris,London`, `14:30,15:00`, `v2.1*`, `API(x)`, and `**at\n14:30**` against `14:30:15`.
  - **Where:** keyline_check.py:133-135.
  - **Class:** neighbour of a previous fix.
  - **Fix:** accept an extended rendering occurrence only in a joiner context the source token had, or drop `,` and `*`.
- **SA2 (medium, regression)**
  - **Defect:** `_plain()` strips emphasis inside URLs, paths and identifiers.
  - **Repro:** `https://x.io/_api_/v1` against `https://x.io/api/v1`; `/srv/_data_/x.txt`; `__init_subclass__` against `init_subclass`; `_private_var_`.
  - **Where:** keyline_check.py:388-390.
  - **Class:** neighbour of a previous fix (A3).
  - **Fix:** an emphasis open must not follow `[\w*/\\.:~@=-]`, and a close must not precede `[\w*/\\]`. A dunder starts with a letter.
- **SA3 (low, regression):** variation selectors and keycap U+20E3 joined MARK, so `✔️v2.1` and `5️⃣` fail closed. Fix: leave U+FE00-FE0F, U+E0100-E01EF and Me out of MARK.
- **SA4 (low):** `_plain` resets emphasis pairing at every newline (:407), so multi-line `**…**` fails closed. Reset only at a blank line.
- **SA5 (low):** `__12__` and `__v2__` (bold) are kept as dunders. Fixed with SA2.
- **SA6 (low, halfway state):** a file argument to measure.py that cannot be read still exits 1. A8 fixed only folders.
- **SA7 (low):** `usage_breakdown._int` takes negative, fractional and huge values: -5 gives "-17%", 1e308 gives "nan%", and a 401-digit int raises OverflowError. Accept only finite values with 0 <= v < 2**63.
- **SA8 (low, pre-existing):** a lowercase "no." after a word ("I'd say no. 3 fail") is read as a number sign. Only "No."/"NO." after a word, or "no." after a digit, is a number sign.
- **SA9 (fix without test):** each of these mutants passes every test:
  - the A4 `TOKEN_REACH` bound removed, which makes `'Monday-'*20000` take 226 s;
  - the time-form order swapped;
  - the ISO word check removed;
  - `*` removed from EXT_ALWAYS_RIGHT;
  - MARK removed from the path class;
  - the newline reset (SA4).
- **Info:** `test_extraction_and_hedges_are_linear_on_100_kb` is flaky under CPU load (it predates this diff). A URL in `~~strike~~` fails closed. The README's extension examples use `a.txt`, which is never extracted.

### Config: 1 medium, 1 fix-without-test, 2 info (SB)
- **SB1 (medium, regression)**
  - **Defect:** a reinstall treats a created settings.json the user edited as one the user wrote. install.py:1093-1096 drops the whole settings part of the record when the file fails `holds_install`. `holds_install` (:204-222) checks only `added_keys`, not `replaced`.
  - **Repro:**
    1. Install with no settings.json.
    2. The user sets both keys (123, 0.5).
    3. `install --force`.
    4. The user removes the hook and `Artifact`.
    5. Install, then uninstall.
  - **Observed:** 123 and 0.5 are not restored, and 5 of the installer's deny tools stay. 7377502 restored both values and removed all six tools.
  - **Class:** neighbour of a previous fix (B1).
  - **Fix:** (a) `holds_install` also checks `replaced` keys against `installed`. (b) A file that fails the check drops only `settings_created`, `deny_added` and `created`, and keeps `added_keys`, `replaced` and `installed`, which uninstall compares by value. Document that the deny tools of such a file stay.
- **SB2 (fix without test):** mutants that remove the hook check (:212), the value check (:217) or the `bool(added)` guard (:222) pass every test.
- **SB3 (info):** the installer's own file, emptied by the user of everything it wrote, is left as `{}` with a backup and no note. Add a note.
- **SB4 (info):** a user file holding an installer value (`{"autoCompactWindow":250000}`) after the created one was deleted counts as created. A check based on content cannot tell these cases apart; document it.

## Second self-review (fresh reviewer, diff f36767d..da4f87e)

SA1-SA9 and SB1-SB4 fixed (0ea6811 config, da4f87e keyline). A fresh reviewer then found 0 high, 3 medium, 1 low, 3 info; all mediums reproduced with `python -I` and fixed with tests in the next commit:
- **M1 (medium, fix did not fully cover SA2):** emphasis marks inside a URL after `? & # , + ( ; ! $ %` were still stripped (`https://x.io/a?_k_=1` against `?k=1` passed). Fix: `_plain` skips marks inside a URL token.
- **M2 (medium, regression from SA8):** "Do not deploy. Ticket No. 5." against "Deploy. ticket no. 5." passed, the lowercased "no." standing in for the lost "not". Fix: the rendering's "word no. N" counts as a negation only as often as the source has one.
- **M3 (medium, regression from SA4):** emphasis paired across list items, so a glob `*` or trailing `_` vanished. Fix: pairing resets at a list item, heading or quote; an `_` pair whose first or last word holds an `_` is kept.
- **L1 (low, halfway state of SA1):** `v2.1*` against `v2.1*-rc` passed. Fixed: they are different extensions.
- **I1 (info, pre-existing):** `**/*.py and docs/**` was stripped as bold. Fixed: emphasis does not close after `/` or `\`.
- **Still passing, accepted:** a bare `v2.1` for a source `v2.1*` (a standalone token counts as present; `_unextended` decision).
- Checks: pytest 1801 passed, 14 skipped; keyline 35/35; pyflakes clean; self-pass fuzz 0 failures; 23 of 23 mutants killed.

## Third self-review (fresh reviewer, diff da4f87e..228c4ba)

0 high, 3 medium, 4 low, 2 info. Self-pass clean on 11,596 repo .md chunks and 60k fuzz strings; linear to 200 kB. All mediums reproduced with `python -I`, compared with main 7adc485, and fixed with tests:
- **"No. N" offsets a lost negation (medium, regression vs main):** "Do not deploy. Ticket No. 5." against "Deploy. Ticket **No. 5**." (also `(No. 5)`, `Ticket: No. 5`) passed. Fix: a "No./no. + number" that is not a sure number sign counts in the rendering only as often as the source has one; `**` and `_` are skipped when finding the word before it.
- **Kept `_` pair hid its tokens (medium, also on main):** `_\`max_retries\` is 5 from 14:30_` against `…14:45_` passed. Fix: kept or dropped is decided per mark; only a mark glued to an identifier holding `_` stays.
- **Emphasis paired across code spans (medium, also on main):** `` keep `ab.txt` `` against `` keep `ab.txt*` `` passed. Fix: a mark inside a code span pairs only within it; pairing resets at `|` and fence lines.
- Two lows fixed (L-a, L-d); L-b and L-c left by design.
- **Accepted, fails closed (low):** `_v2.1 adds max_retries_` against `v2.1 adds max_retries` fails, since the trailing `_` glued to `max_retries` is kept as part of the token.
- Checks: pytest 1838 passed, 14 skipped; keyline 35/35; pyflakes clean; 17 of 17 mutants killed.
- **Stopped here:** three rounds of fresh review each found neighbours in the emphasis stripper, each smaller than the last; the third round's fixes were verified against every repro of all rounds. A further review is a candidate for the next scheduled review rather than a blocker for this merge.
