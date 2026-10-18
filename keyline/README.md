# keyline

Tools for Keyline machine notes: keyed, terse, whole-word English notes that an LLM writes for
itself (one `key: item; item` line per topic), with a deterministic check that no fact was lost
when a note is rendered to Hebrew or prose. Design and measurements:
`../machine-language-panel-results.md` (section `=== SPEC ===`).

## Files

| File | What it does |
|---|---|
| `keyline_check.py` | Fact check: source note vs one or more renderings. Fails if a rendering is missing any date, time, version, number, percentage, UPPER_CASE identifier, path, CamelCase name, file name or snake_case token of the source, or has fewer negation words. |
| `keyline_lint.py` | Style lint for a notes file: markdown furniture and invented abbreviations. |
| `measure.py` | o200k_base and cl100k_base token counts per file or per folder, with a before/after change line for two files. |
| `keyline_hook.py` | Claude Code PostToolUse hook: runs the lint, and the check when a sibling `.he.txt` exists. |
| `hooks-example.json` | The hook entry to paste into a repo's `.claude/settings.json`. |
| `CLAUDE-snippet.md` | The standing rule for a repo's CLAUDE.md (98 tokens o200k, header included). |
| `tests/` | The panel's worked examples and `run_tests.py`, which reproduces their results. |
| `cache/` | Built on first use: tiktoken encodings and the single-token word list. |

## Setup

The venv lives in `.venv/` and holds only tiktoken 0.14.0. To rebuild it:

```bash
py -3.14 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe keyline_lint.py --rebuild-cache
```

All commands below use `.venv/Scripts/python.exe` from this folder.

## keyline_check.py

```bash
.venv/Scripts/python.exe keyline_check.py tests/incident.keyline.txt tests/incident.keyline.he.txt tests/incident.glyph.txt
```

```
PASS tests/incident.keyline.he.txt  (17 invariants present, negations 4 -> 4)
FAIL tests/incident.glyph.txt  (checked against tests/incident.keyline.txt)
  missing (2): HTTP, UTC
  negations: source 4, rendering 0 (4 lost)
```

`--list SOURCE` prints what would be checked. Exit 0 pass, 1 fail, 2 usage error.

Matching is exact and case-sensitive, on ASCII token boundaries: `5` does not count as present
because `503` is, but a Hebrew prefix glued to an identifier still counts. Markdown list numbers
(`1. `) are not facts and are skipped.

Negations counted, English and Hebrew together in both texts:

- English: no, not, never, without, none (the spec list), plus cannot and n't contractions.
- Hebrew: לא, אין, ללא, אף, מעולם (the spec list), plus ו/ש/וש/כש prefixes on לא, אין and ללא, and
  the inflected forms of אין (אינו, אינה, אינם, אינן, אינני, איננו, אינך). Without these the
  panel's own Hebrew prose rendering counts 1 negation instead of 4 and fails falsely.

## keyline_lint.py

```bash
.venv/Scripts/python.exe keyline_lint.py notes/*.txt
```

- Furniture: a line starting with a bullet (`- `, `* `, `+ `), a numbered item (`1. `, `2) `) or a
  header (`#` to `######`), or any `**` or backtick.
- Abbreviations: a lowercase ASCII word that is not one o200k_base token (with its leading space)
  AND has the shape of an invented abbreviation: a numeronym (k8s, i18n, a11y), 2-5 letters with
  no vowel (rst, mgmt), or 4-5 letters with one vowel (alrt, srvc). Words of 6+ letters, anything
  containing a digit (cp1252, sha256, git hashes), and plurals of a one-token word (diffs, slugs)
  pass. Chunks with `/ \ _ . = @ #` and similar characters, any capital letter, or a leading digit
  are treated as identifiers, names or numbers and skipped. Hyphenated words are checked part by part.
  Measured on 400 markdown files in gittoken (2026-10-18): the old rule flagged 3,774 distinct
  words, almost all real (worktree, uncommitted, harmlessly); this rule flags 87, mostly tool names
  and genuine shorthand, and still catches all eight invented test abbreviations.
- The single-token list (47,450 words) is built once from the o200k vocabulary into
  `cache/o200k_single_token_words.txt`. Lint runs read only that file.
- Common tool and format names (mcp, npm, npx, pnpm, venv, pwsh, docx, stdout...) are allowed by a
  built-in list in `keyline_lint.py`. Other real names go in a `keyline-allow.txt`, one per line.
  Every such file in the note's folder or a parent folder is read. `--no-allow` ignores those files
  and the built-in list; `--allow FILE` adds one.

## measure.py

```bash
.venv/Scripts/python.exe measure.py tests/notes.markdown.md tests/notes.keyline.txt
```

```
  o200k  cl100k   chars  file
    104     106     385  tests\notes.markdown.md
     66      68     277  tests\notes.keyline.txt
    170     174     662  total (2 files)
change: o200k 104 -> 66 (-37%), cl100k 106 -> 68 (-36%)
```

Files are counted as stored: a trailing newline or CRLF line endings add tokens.

## Wiring the hook into one repo

1. In the repo, create `.claude/settings.json` to share the hook with the repo, or
   `.claude/settings.local.json` to keep it personal. Paste the contents of `hooks-example.json`.
   If the file already has a `"hooks"` key, add the `PostToolUse` entry to it instead.
2. Keep notes in a `notes/` or `plans/` folder of that repo. The hook ignores every other path,
   and only acts on `.txt`, `.md`, `.keyline` or extension-less files. To watch specific files
   instead, append `--watch PATTERN` to the command (repeatable; fnmatch, case-insensitive; an
   absolute pattern matches the absolute path, a relative one the path from the project dir).
   Live example: `gittoken/.claude/settings.local.json` and `rk-wt/.claude/settings.local.json`
   watch only `C:/Users/PC/Desktop/gittoken/rk-wt/PROGRESS.md`.
3. Put a Hebrew rendering of `notes/x.txt` at `notes/x.he.txt`. The hook then checks it whenever
   either file is written or edited.
4. Optional: add `keyline-allow.txt` at the repo root for project names that split into tokens.
5. Paste `CLAUDE-snippet.md` into the repo's CLAUDE.md.
6. Start a new Claude Code session in the repo so it loads the settings.

How it behaves: the matcher is `Write|Edit`. On findings the hook exits 2 and prints them to
stderr. For PostToolUse, Claude Code shows that stderr to Claude after the file is written, so
Claude fixes the file. Paths in the hook command are absolute, so the repo can be anywhere.
The hook has been tested by piping simulated PostToolUse events through the exact command in
`hooks-example.json`. It has not yet run inside a live Claude Code session.

## Reproduction

```bash
.venv/Scripts/python.exe tests/run_tests.py
```

22 of 22 checks pass. Token counts match the panel exactly:

| Fixture | o200k | cl100k |
|---|---|---|
| incident, verbose prose | 301 | 302 |
| incident, Keyline | 204 | 206 |
| incident, Hebrew Keyline | 308 | 594 |
| incident, Hebrew prose | 375 | 742 |
| incident, glyph version | 182 | 180 |
| notes, markdown | 104 | 106 |
| notes, Keyline | 66 | 68 |
| notes, Hebrew Keyline | 89 | 162 |

Two panel claims do not reproduce exactly:

- The panel says prose to Keyline passes in both directions. Keyline to prose passes, but prose
  to Keyline fails on `API`: the prose says "Checkout API" and the note lowercased it to
  `checkout-api`. The checker is right that the token changed.
- The Keyline notes example passes the lint only with `pnpm` in `tests/keyline-allow.txt`.

## Honest limits

- Token counts come from OpenAI tokenizers. Claude's tokenizer is not public, so treat every count
  and percentage as a proxy. Check real numbers with Anthropic's count_tokens endpoint.
- The checker only sees tokens it can extract. It cannot catch a wrong verb, a swapped actor, a
  reversed causal chain, a dropped hedge (could, may, likely) or an invented sentence.
- Negations are counted, not aligned. A rendering that drops one negation and adds another
  elsewhere passes. Hebrew אף also means "even", so it can be over-counted.
- Lowercase kebab names such as `checkout-api`, and two-word lowercase paths such as `src/auth`,
  are not extracted as invariants.
- The abbreviation lint only catches inventions that split into several tokens. The o200k
  vocabulary is multilingual, so short shorthands that are already one token pass: rb, cfg, err,
  conn, svc, msg, idx and others. Those are allowed by the spec. k8s, mgmt, dflt and similar are
  flagged. UPPER_CASE codes such as XH are treated as identifiers and never flagged.
- The shape rule is a heuristic. Invented compounds of 6+ letters (dbpool, oncall) pass, and pkts
  passes because pkt is one token. A short real word with one vowel that splits into tokens, such
  as blurb, is still flagged: use the allow file.
- The hook nudges; it does not block the write. The file is already on disk when it runs.
