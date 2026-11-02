# Review of the emphasis stripper `_plain` at main 2829343

Scope: `keyline/keyline_check.py`, `_plain` (:457-520) and what it uses (EMPHASIS :420, `_GLUED_DASH`, DUNDER_BODY, URL_SPAN, URL_TAIL, `_code_spans` :434, LIST_MARKER), and how its output feeds `check`.
I changed no repo files. Scratch files are in `/tmp/claude-0/-home-user-Ideal-Umbrella/a7dbdc8e-9944-5a86-9067-4a3f36643dea/scratchpad/plain/`:
- `h.py` loads both versions.
- `oracle.py` is the CommonMark oracle (markdown-it-py 3.0.0, installed into `site/` in that folder).
- `addemph.py`, `failopen2.py` and `fo2.out` are the fuzzers and their output.
- `lin.py` is the timing script.
- `proto.py` and `proto_eval.py` hold the prototype of the recommendation.

Every repro below was run as `python3 -I` with `sys.path.insert(0, 'keyline')` (or the 7adc485 copy) and `keyline_check.check(source, rendering)`.

## Summary

- **High:** 0.
- **Medium:** 3, all fail-open and all pre-existing at 7adc485.
  - M1: a run between punctuation is read as an opener.
  - M2: `___x___`.
  - M3: marks stripped inside code spans.
- **Low:** 9 (L1-L4 fail-open, C1-C5 fail-closed). C1, C3-Hebrew and C4 are regressions against 7adc485, but only fail-closed.
- **Self-pass:** `check(t, t)` passes on all 3,554 CommonMark paragraphs of the 79 repo `.md` files, and on all 92 tracked `.md`/`.txt` files read whole. No self-pass failure was found.
- **Linear time:** confirmed on 22 adversarial 100k/200k inputs. Every ratio is about 2x, the worst 2.7x within noise, and the 400k/800k follow-up stays linear.
- **Negations and hedges** never pass through `_plain`. `negations()` and `hedges()` read the raw text, and `NEG_EN`/`HEDGE` use letter-or-digit edges (`EN_L`/`EN_R`), so `_not_` and `**not**` count. No emphasis-driven negation fail-open was found. The only way `_plain` reaches the result is through `_scan` (invariants and extensions) and `present` (the rendering's plain text).

## 1. Design and recommendation

### Current design

1. A single regex (EMPHASIS) classifies each `*`/`_` run as an opener, a closer or a block reset (blank line, list/heading/quote/fence line, `|`). This uses fixed lookbehind and lookahead character sets.
   - The `open` alternative is tried first, so a run that could be either becomes an opener.
   - Runs are `*{1,3}` and `_{1,2}`.
2. Openers go on a stack per exact run string (`"**"` pairs only with `"**"`). A code span has its own stack, and the stacks are cleared at a reset.
3. Marks inside a URL_SPAN are skipped.
4. A matched `_` pair is dropped mark by mark, unless:
   - it is a dunder (lowercase DUNDER_BODY), or
   - the word glued to that mark holds a `_` (`glued_identifier`).
5. A `*` pair is always dropped.
6. Unmatched marks stay in the text.

### Why it keeps producing fail-open neighbours

A mark the stripper does not drop stays glued to the token. `_` is a word character, so an undropped `_` makes the token invisible to INVARIANT (L/R boundaries). The token is then never checked, and the result is fail-open.

So every place where the classifier differs from what a writer means hides tokens:
- open-first resolution (M1);
- the `_{1,2}` limit (M2);
- the `~ = . -` exclusions (L1);
- the Python `\w` lookbehind against Hebrew/CJK (L4).

Each round fixed one shape and moved the edge somewhere else.

### Options

- **(a) CommonMark delimiter-run algorithm.** This means left/right-flanking rules, the stack with the "rule of 3", and splitting runs of 3 into 1+2.
  - It would fix M1, M2 and C1 as a class, and it is linear with the openers_bottom table.
  - However, CommonMark itself disagrees with the project's identifier-safety rules. `list.__format__`, `__init__` in prose, `SA1-_SA9_` and `~_20_` are emphasis in CommonMark. Every current exception (dunder, glued identifier, path `/`, URL) would have to be layered back on top.
  - It is about 100 more lines, and still heuristic at the exceptions. The hiding failure mode stays: any exception that keeps an `_` hides a token.
- **(b) Recommended: a second discovery pass, plus verbatim code spans.**
  - Keep `_plain` as the strict pass.
  - Also scan an *edge-free* copy of the source: every `*`/`_` run that touches a word edge is removed, outside URL spans.
  - Source invariants become the union of the two scans.
  - A token found only by the edge-free scan is looked up in the edge-free copy of the rendering. Tokens `_plain` sees are still judged strictly as today.
  - This turns every present and future "mark hides a token" neighbour into a checked token, without the stripper having to be right.
  - Both sides go through the same functions, so identical text still passes.
  - Prototype (`proto.py`, about 15 lines): it makes M1a, M1b, M2, L1 and L1b fail as they should. It adds 0 self-pass failures on the 3,554 repo paragraphs.
  - Cost: for tokens found only in the second pass, the edge-free copy does not tell `_private` from `private` or `ab.txt*` from `ab.txt`. Today those tokens are not checked at all, so this is still a gain.
  - For M3, compare inline code-span contents verbatim (each source span must appear in the rendering) instead of stripping inside spans. Code is never translated, and this catches `` `__FILE__` `` → `` `FILE` ``.
- **(c) Strip both ways and require both sides to agree** (compare tokens with and without stripping). Without stripping, a rendering that only adds emphasis fails, so this fails closed on exactly the cases the contract wants to pass. Not recommended.

### Optional local fixes, if (b) is not taken

- Let a run that is preceded and followed by punctuation close when a same-length opener is on the stack (CommonMark both-flanking rule). This fixes M1 and C6.
- Accept `_{1,3}` and treat `___` like `***`. This fixes M2 and C5.
- Allow a `*` opener after `_` and a `*` closer before `_`. This fixes C1.

## 2. Findings

### Medium (fail-open)

**M1. A mark run between punctuation is read as an opener, so a closing `_` stays and hides the token next to the opening `_`.**
- **Where:** EMPHASIS (:420). The `open` alternative comes first, and its lookbehind allows `% ) " ' ! ?`, so `%_,`, `)_,` and `"_.` become openers.
- **Repros** (each gives ok=True at 2829343 and at 7adc485):
  - `check('Cache writes were _27%_, reads 58% at 14:30.', 'Cache writes were _57%_, reads 58% at 14:30.')`
  - `check('Meet in _Paris (FR)_, at 14:30.', 'Meet in _Berlin (FR)_, at 14:30.')`
  - `check('_Paris said "yes"_. Owner: Dana at 14:30.', '_Berlin said "yes"_. Owner: Dana at 14:30.')`
  - `check('Load **_97%_**. Owner: Dana at 14:30.', 'Load **_27%_**. Owner: Dana at 14:30.')`
- **Fuzz evidence:** in the repo paragraphs, most of the non-dash `_`/`__`/`**_`/`*__` fail-opens were `_N%_` followed by `.`, `,` or `)`, for example "cache writes _27%_, output 15%".
- **Other direction:** the same root cause fails closed when a rendering adds emphasis. `check('Coverage is 50% for Paris (FR) at 14:30.', 'Coverage is _50%_, for _Paris (FR)_, at 14:30.')` gives ok=False.
- **Class:** halfway state of A3 (underscore emphasis hides invariants). This is not a regression: 7adc485 never stripped `_`.
- **Realism:** an emphasised percentage or parenthesised name followed by punctuation is common in reports.

**M2. `___x___` (bold italic with underscores) is never stripped and hides x.**
- **Where:** `_{1,2}(?=[^\s_])`. A run of three `_` has no position that is not preceded by `_`, so it never opens.
- **Repro:** `check('Meet in ___Paris___ at 14:30.', 'Meet in ___Berlin___ at 14:30.')` gives ok=True. So does `'Meet in **Berlin** at 14:30.'` as the rendering. Both versions behave the same.
- **Fuzz:** a source token wrapped in `___` and then changed passed in 91% of cases (6,914 of 7,612 across rendering styles).
- **Other direction:** `check('Meet in Paris at 14:30.', 'Meet in ___Paris___ at 14:30.')` gives ok=False (fail-closed).
- **Class:** halfway state of A3, pre-existing. It is valid CommonMark but rare in practice.

**M3. Marks inside an inline code span are stripped, so a changed code identifier passes.**
- **Where:** `_plain` pairs marks inside a span on purpose (test `test_emphasis_around_or_inside_code_is_still_dropped`: `` `_v2.1_` `` → `` `v2.1` ``). DUNDER_BODY is lowercase-only, so upper-case dunders are also stripped.
- **Repros** (each gives ok=True at 2829343 and at 7adc485):
  - ``check('Use `__FILE__` and `__LINE__` since v2.1.', 'Use `FILE` and `LINE` since v2.1.')``
  - ``check('Set `_Config_` in v2.1.', 'Set `Config` in v2.1.')``
  - At 7adc485 these pass because the token is hidden; at 2829343 they pass because the two sides are made equal.
- **Class:** design limit. CommonMark never parses emphasis inside code.
- **Realism:** moderate. C macros like `__FILE__`, `__LINE__` and `__GNUC__` appear in docs, and a rendering "cleaning up" underscores is plausible.
- **Fix:** see 1(b): compare code-span contents verbatim.

### Low (fail-open)

**L1. The opener exclusions `~ = . -` hide tokens that CommonMark treats as emphasised.**
- **Repros** (each gives ok=True in both versions):
  - `check('Retries: ~_20_ at 14:30.', 'Retries: ~_50_ at 14:30.')`
  - `check('Window 14:30-_15:00_ for v2.1.', 'Window 14:30-_16:00_ for v2.1.')`
  - `check('Set measured=__True__ in v2.1.', 'Set measured=__False__ in v2.1.')`
  - The fuzz also hit `SA1-_SA9_`, `UTF-_8_`, `-_25%_` and `.__he.txt__`.
- **Class:** neighbour of the SA2 fix (a tradeoff made to protect `a-_b_` and `?_k_=1`-style identifiers). Rare in real prose.

**L2. A glob `*` that is not in a recognised code span pairs with a later `*` glued to a token, so a rendering that adds `ab.txt*` passes.**
- **Repros** (each gives ok=True in both versions):
  - `check('Delete *.log and keep ab.txt at 14:30.', 'Delete *.log and keep ab.txt* at 14:30.')`
  - The same through an indented code block: `'Run:\n\n    rm *.o\nKeep ab.txt*'` (ok=True).
  - The same through HTML code: `'<code>*.o</code> and keep ab.txt*'` (ok=True).
- **Class:** design limit. In the plain-prose case CommonMark agrees that it is emphasis. Indented code blocks and HTML `<code>` are not recognised as code (pre-existing neighbour of N3).

**L3. A CRLF blank line does not reset pairing.**
- **Cause:** `\n[ \t]*\n` does not allow `\r`, and BLANK_LINE in `_code_spans` has the same gap.
- **Repro:** `check('Delete *.log files.\r\n\r\nKeep ab.txt at 14:30.', 'Delete *.log files.\r\n\r\nKeep ab.txt* at 14:30.')` gives ok=True. With LF it gives ok=False (fixed).
- **Reach:** `read()` opens in text mode, which turns CRLF into LF, so this only reaches API callers of `check()`. The hook is not affected.
- **Class:** halfway state of SA4/M3. The fix is `[ \t\r]*`.

**L4. An `_` glued after a Hebrew or CJK letter is never an opener, because Python's `\w` includes those letters while WORD excludes Hebrew.**
- **Repro:** `check('Ship ב_Paris_ at 14:30', 'Ship ב_Berlin_ at 14:30')` gives ok=True in both versions.
- **Class:** pre-existing. CommonMark also renders it literally, so it is unrealistic.

### Low (fail-closed: the rendering only adds or removes emphasis)

**C1 (regression against 7adc485): `_**x**_` and `__*x*__` added by a rendering fail.**
- **Cause:** the `*` opener lookbehind excludes `\w`, which includes `_`, and the closer lookahead does the same.
- **Repros** (ok=False at 2829343, ok=True at 7adc485):
  - `check('Meet in **Paris** at 14:30.', 'Meet in _**Paris**_ at 14:30.')`
  - `check('Needs Python 3.10 or later.', 'Needs __*Python*__ 3.10 or later.')`
- **Fuzz:** 8-9% of these additions in the repo fail.

**C2 (pre-existing, documented): `__word__` on a single lowercase word is kept as a dunder.**
- A rendering that drops the bold fails: `check('Count the __tools__ at 14:30.', 'Count the tools at 14:30.')` gives ok=False.
- **Fuzz:** 41% of `__x__` removals and 42% of `*__x__*` removals fail. Lowercase hashes such as `*__bcc441c__*` also count as dunders.
- This is a deliberate tradeoff (`__init__`); the fix is a dunder word list or a code-span-only dunder rule.

**C3: Bold glued to a Hebrew or CJK letter is not stripped.**
- `check('פגישה בParis ב-14:30', 'פגישה ב**Paris** ב-14:30')` gives ok=False. This is a regression against 7adc485, which passed.
- `check('会议在**Paris**举行，时间14:30', '会议在Paris举行，时间14:30')` gives ok=False (pre-existing).
- **Cause:** the opener lookbehind uses Python `\w`, not WORD.

**C4 (regression, fail-closed only): emphasis spanning lines of one blockquote is cut at each `\n>`.**
- **Repro:** `check('> **Deploy at 14:30** in Paris', '> **Deploy at\n> 14:30** in Paris')` gives ok=False at 2829343 and ok=True at 7adc485.
- **Cause:** the reset at `>` is meant for the start of a quote, but it also fires on quote continuation lines.

**C5: A `|` in prose resets pairing** (`**sub-word tokens (R|CA**`). The same happens after `/` (`**Class: endings /**`, the I1 tradeoff). Both are rare.

### Checked and found clean

The following behave correctly on both sides:
- nested `*a **b** c*` and `**a _b_ c**`; `***x***`; `**_x_**`; `*__x__*` around a non-dunder;
- links `[_x_](url)` and marks inside URLs; headings; tables (fixed against 7adc485, which was fail-open on `| _Paris_ |`);
- ``` fences and ~~~ fences, with or without blank lines inside;
- escaped `\*` and `\_` (kept; `\_x\_` makes the token itself include the backslash, so a change fails closed);
- `<em>`; Cyrillic `_Париж_`; emoji-adjacent `🎉**Paris**🎉`; `**Paris**'s`; the `__format__`/`__tests__/` dunders (kept, which is correct even though CommonMark bolds them).

## 3. Method and numbers

- **Self-pass:** 3,554 inline paragraphs (markdown-it block parse of 79 `.md` files) and 92 whole `.md`/`.txt` files gave 0 failures.
- **CommonMark-strip oracle:** for each paragraph p, the CommonMark-stripped text s is p with emphasis removed (lossless reconstruction checked; 28 paragraphs skipped as lossy).
  - `check(p, s)` and `check(s, p)` failed only on dunders (`__tests__/`, `list.__format__`). That is correct behaviour for identifiers, which CommonMark mis-bolds.
- **Add/remove fuzz** (`addemph.py`, about 1,200 cases per style, kept only where CommonMark confirms pure emphasis). Fail-closed counts:

  | Style | Added | Removed |
  |---|---|---|
  | `___` | 200 | 40 |
  | `_**` | 97 | 2 |
  | `__*` | 107 | 5 |
  | `__` | 18 | 501 |
  | `*__` | 28 | 538 |
  | `_` | 24 | 22 |
  | `*` | 4 | 0 |
  | `**` | 6 | 1 |

  Most of the `_` and `**_` failures are snake identifiers kept on purpose (the M3 rule of the second self-review).
- **Fail-open fuzz** (`failopen2.py`, single-occurrence tokens whose plain change is caught). The source token is wrapped in style X, and the rendering changes the token and wraps it in style Y. Pass rate (which should be 0):

  | Source style | Pass rate |
  |---|---|
  | `___` | 91% |
  | `_` | about 8% (mostly `-_x_`, `~_x_` and `_N%_` followed by punctuation) |
  | `__` | about 2.5% |
  | `**_` and `*__` | about 1% |
  | `*`, `**`, `***`, bare | 0 |

- **Linearity** (`lin.py`, 100k then 200k characters, `_plain` and `check(t, t)`). The 22 generators covered:
  - mark runs: unmatched openers, unmatched closers, nested `_`/`*` stacks, `*`×n, `_`×n, `*_`×n;
  - identifiers: long and repeated dunder bodies, glued identifiers, dash runs;
  - code and URLs: backtick runs of 1-7, code spans with marks, URLs with marks;
  - resets and scripts: list resets, pipes, CRLF, Hebrew dash prefixes, punctuation runs.

  Every ratio was 1.8-2.7x, and the worst at 200k was `check` at 1.25 s (`crlf`, `backticks_code_marks`). The follow-up at 100k→800k for nested and mixed runs: 0.07→0.24→0.45→0.96 s, which is linear.

## 4. Prototype of the recommendation

See `proto.py` (scratch only). `check2` = `check` plus the edge-free discovery pass. Results:
- It turns M1a, M1b, M2, L1 (`~_20_`) and L1b (`14:30-_15:00_`) into failures with the right missing token.
- L4 (`ב_Paris_`) still passes, because the prototype's edge regex uses Python `\w`. Use WORD there.
- Self-pass on the 3,554 repo paragraphs: 0 new failures.

It does not address M3 (needs verbatim code spans) or the fail-closed C items.

## 5. Fixes (PR #35)

Fixed in `keyline/keyline_check.py`, tests in `tests/test_keyline_check.py` (each fails on 2829343), README updated. Design: the recommendation above (edge-free second scan, code spans verbatim).

| Finding | Status |
|---|---|
| M1, M2, M3 | fixed; repros now `ok=False`, identical text still passes |
| L1, L3, L4 | fixed |
| C1, C3 (Hebrew), C4 | fixed |
| L2 | left: glob `*` in prose is emphasis per CommonMark; indented code not parsed (design limit) |
| C2 | left: lowercase `__word__` kept as a dunder to protect `__init__` (fail-closed) |
| C3 (CJK), C5 | left: fail-closed and rare |

Known cost: renderings that strip backticks from code holding marks fail a little more often (111 against 106 of 1,929 repo paragraphs), since code is now compared as written; fail-closed. In the fail-open fuzz, passes of a changed token fell from 273 to 10, all one `___tools___`-in-code case that 2829343 also passes (no invariant kind is extracted from a plain lowercase word).

Checks: pytest 1886 passed / 14 skipped, run_tests 35/35, pyflakes clean, self-pass 0 failures over 1,862 repo paragraphs and files, linear to 800 kB, 25 of 28 mutants killed and the other 3 argued equivalent.

### Self-review of the fix (round 2)

A fresh reviewer of d27ac81 found F1 (medium, fail-open regression: code tokens with edge marks skipped the extension check), F2 (low, fail-open: blockquote blank/list/heading/fence lines no longer reset pairing), F3 (low, fail-closed: a real NUL read as the code marker) and F4 (medium, pre-existing: `present()` quadratic over many tokens sharing a first run; 35 kB adversarial input 25 s against the hook's 30 s timeout). All four are fixed with tests that fail first. F4: a differential search over 140,934 pairs shows 0 result differences from the old walk; the repros take 0.25 s. Checks: pytest 1905 passed / 14 skipped, run_tests 35/35, pyflakes clean, self-pass 0 failures over 1,867 repo paragraphs and files.
