# keyline

Tools for Keyline machine notes: keyed, terse, whole-word English notes that an LLM writes for
itself (one `key: item; item` line per topic), with a deterministic check that no fact was lost
when a note is rendered to Hebrew or prose. Design and measurements:
`../research/panel-results.md` (section `=== SPEC ===`).

## Files

| File | What it does |
|---|---|
| `keyline_check.py` | Fact check: source note vs one or more renderings. Fails if a rendering is missing any date, time, version, number, percentage, URL, UPPER_CASE identifier (plurals such as `PRs` included, any script's capitals), hex hash, path, CamelCase name, proper noun, file name, snake_case or dunder token, or lowercase identifier with a digit (`sha256`, `utf8`) of the source, drops a hedge class, or has fewer negation words. A month or weekday name may appear in its Hebrew form. A source with no extractable invariant and no hedge is `INCONCLUSIVE`, not `PASS`. |
| `keyline_lint.py` | Style lint for a notes file: markdown furniture and invented abbreviations. |
| `measure.py` | o200k_base and cl100k_base token counts per file or per folder, with a before/after change line for two files that each produced a row. |
| `keyline_hook.py` | Claude Code PostToolUse hook for notes under `notes/` or `plans/` of the project: runs the lint on a note, and the check against each sibling rendering (`.he.txt`, `.he.md` or `.he.keyline`, any case). `--print-config` prints a ready-to-paste hook entry for this install. |
| `hooks-example.json` | Template hook entry. Replace `__PYTHON__` and `__KEYLINE_DIR__`, or use `keyline_hook.py --print-config` instead. |
| `CLAUDE-snippet.md` | The standing rule for a repo's CLAUDE.md (153 tokens o200k, header included; the last sentence says when to save a learning in `notes/learnings.md`). |
| `tests/` | The panel's worked examples and `run_tests.py`, which reproduces their results. |
| `cache/` | Built on first use: tiktoken encodings and the single-token word list. |

## Setup

The scripts need Python 3.10 or later (CI runs 3.10, 3.12 and 3.13) and tiktoken (pinned in `requirements.txt`). Install it
into the interpreter you will run them with, for example a venv in this folder:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt        # Windows: .venv\Scripts\python.exe
.venv/bin/python keyline_lint.py --rebuild-cache
```

All commands below are run from this folder with `python` standing for that interpreter. The
word cache in `cache/` is built on first use, so the first run needs tiktoken; without it the
scripts stop with a one-line install hint.

## keyline_check.py

```bash
python keyline_check.py tests/incident.keyline.txt tests/incident.keyline.he.txt tests/incident.glyph.txt
```

```
PASS tests/incident.keyline.he.txt  (17 invariants present, negations 4 -> 4)
FAIL tests/incident.glyph.txt  (checked against tests/incident.keyline.txt)
  missing (2): HTTP, UTC
  negations: source 4, rendering 0 (4 lost)
```

`--list SOURCE` prints what would be checked. Exit 0 pass, 1 fail or inconclusive, 2 usage error.

Matching is exact and case-sensitive, on Unicode word boundaries (letters of any script, digits
and `_`) except Hebrew letters: `5` does not count as present because `503` is, `COLE` is not in
`ÉCOLE`, a bare number does not count as present inside a time or a grouped number (`10` is not in
`10:00`, `2` is not in `2,500`), but a Hebrew prefix glued to an identifier still counts (`בv2.14.0`,
`ב-v2.1`). Text is compared in Unicode NFC, so a name saved with combining accents (NFD) matches,
and a combining mark NFC cannot fold into its letter (`a` with U+0331) is part of the word; a
Hebrew point is not, nor is a variation selector or a keycap mark (`✔️v2.1` holds `v2.1`, `5️⃣`
holds `5`). Emphasis marks (`**v2.1**`, `_API_`, `*ab.txt*`), also across the lines of one
paragraph, are dropped before the scan, so they neither hide nor extend a token. A pair does not
span a blank line, a line that starts a list item, heading, quote or code fence (`- `, `1. `,
`# `, `>`, a fence of three backticks or tildes) or a table cell separator `|`. A mark inside an
inline code span pairs only with a mark in the same span (`` `*.o` `` and a later `ab.txt*` are
no pair); emphasis around a code span (`**use `x` for v2.1**`) is still dropped.
An `_` or `*` that is not emphasis stays part of the token: anywhere inside a URL
(`https://x.io/a?_k_=1`, `#_frag_`, `&*b*=2`; marks around a whole URL, `**https://x.io/a**`,
are still emphasis), inside a path or identifier (`/srv/_data_/x.txt`; a run does not open after
or close after a `/` or `\`, so `**/*.py and docs/**` keeps its marks), glued to a word that
holds an `_` itself (`_private_var_`; of `_v2.1 adds max_retries_` only the closing `_` stays,
so `v2.1` is still a token), a dunder (`__init__`, `__init_subclass__`; `__12__` is bold), or a
lone edge mark (`_private_name`, `snake_case_`).
A token the source writes on its own is not present where a rendering only extends it, on either
side: `ab.txt` in `ab.txt.bak`, `ab.txt~`, `ab.txt=1` or `old/ab.txt`, `report.pdf` in `old-report.pdf`,
`Jean-Luc` in `Jean-Luc-Picard` or `Marie-Jean-Luc`, `14:30` in `14:30:15`, `notes/a` in
`notes/a/` or `/notes/a`, `API` in `API#x`, `API(x)` or `#API`, `v2.1` in `+v2.1`. Both sides
share one set of joiners; markup and plain punctuation (`(API)`, `API,` before a space) do not
extend. A token the source itself writes only glued by a joiner (`v2.1,v2.2`, `MODE=fast`,
`API(x)`) is present on its own or glued by the same joiner on the same side, not extended any
other way (`v2.1-rc,v2.2`, `MODE-X=fast` fail); a `*` (or another joiner that extends even
before a space) at the end of the token and one glued onward differ (`v2.1*` and `v2.1*-rc`). A date stays present inside an ISO timestamp (`2026-10-25T10:00Z`), but not inside a bad
or extended one (`2026-10-25T99`, `2026-10-25T10:00.bak`). A URL holds the characters RFC 3986
allows plus letters (`https://x.io/Zürich`); markup, quotes and dashes glued after it (`**`, `”`,
`—`, `…`) are not part of it. A URL is looked up as the rendering's whole URL, so
`https://e.com` is not in `https://e.com@evil.io` and `?x=1` is not in `?x=1&debug=1`. The one
exception is a pair or range of two tokens of one family joined by `-` or `/`: times, dates and
versions (`14:30-15:00`, `2026-10-25-2026-10-27`, `v2.1/v2.3`), and names with `/`
(`Postgres/MySQL`, `API/SDK`). A hyphen also joins the parts of one name (`Jean-Luc-Picard`,
`S3-IA`, `Paris-Nord`), so between names it counts as a pair only for month and weekday names
(`Monday-Friday`, `Mon-Fri`); in the source such a pair is two tokens, so `Monday to Friday`
renders it. A path, file name, hash or number never pairs. Markdown list numbers of
one or two digits (`1. `, `12) `) are not facts and are skipped when content follows them on the
line; `2024. Done` keeps `2024`, and so does `12.  ` with only a hard break after it. Proper nouns are extracted
when they are not ordinary sentence furniture (`stack: Postgres via Prisma` checks `Postgres`
and `Prisma`; so does `- **Stack:** Postgres`). A month or weekday name may appear in its Hebrew
form (`Monday` as `יום שני`, `October` as `אוקטובר`). Hedges are checked by class, so `could`
may render as `may` but not as `will`; a Hebrew rendering keeps the class with the Hebrew words
of the same group (`could` as `עלול`, `should` as `אמור`).

A source with no extractable invariant and no hedge is `INCONCLUSIVE` and exits 1. The checker
must never report a vacuous `PASS` on a source whose claims it did not understand.

Negations counted, English and Hebrew together in both texts:

- English: no, not, never, without, none (the spec list), plus cannot and n't contractions.
- Hebrew: לא, אין, ללא, אף, מעולם (the spec list), plus ו/ש/וש/כש prefixes on לא, אין and ללא, and
  the inflected forms of אין (אינו, אינה, אינם, אינן, אינני, איננו, אינך). Without these the
  panel's own Hebrew prose rendering counts 1 negation instead of 4 and fails falsely.

## keyline_lint.py

```bash
python keyline_lint.py notes/*.txt
```

- Furniture: a line starting with a bullet (`- `, `* `, `+ `), a numbered item of one or two digits
  (`1. `, `12) `; `2024. ` is a year, not an item), each with content after it (`12.  ` alone is
  not an item), or a header (`#` to `######`), or any `**` or backtick.
- Abbreviations: a lowercase ASCII word that is not one o200k_base token (with its leading space)
  AND has the shape of an invented abbreviation: a numeronym (k8s, i18n, a11y), 2-5 letters with
  no vowel (rst, mgmt), or 4-5 letters with one vowel (alrt, srvc). Words of 6+ letters, anything
  containing a digit (cp1252, sha256, git hashes), and plurals of a one-token word (diffs, slugs)
  pass. Chunks with `/ \ _ . = @ #` and similar characters, any capital letter, or a leading digit
  are treated as identifiers, names or numbers and skipped. Hyphenated words are checked part by part.
  Measured on a 400-file markdown corpus (2026-10-18): the old rule flagged 3,774 distinct
  words, almost all real (worktree, uncommitted, harmlessly); this rule flags 87, mostly tool names
  and genuine shorthand, and still catches all eight invented test abbreviations.
- The single-token list (47,450 words) is built once from the o200k vocabulary into
  `cache/o200k_single_token_words.txt`. Lint runs read only that file.
- Common tool and format names (mcp, npm, npx, pnpm, venv, pwsh, docx, stdout...) are allowed by a
  built-in list in `keyline_lint.py`. Other real names go in a `keyline-allow.txt`, one or more words per line
  (`#` starts a comment).
  Every such file in the note's folder or a parent folder is read. `--no-allow` ignores those files
  and the built-in list; `--allow FILE` adds one.

## measure.py

```bash
python measure.py tests/notes.markdown.md tests/notes.keyline.txt
```

```
  o200k  cl100k   chars  file
    104     106     385  tests\notes.markdown.md
     66      68     277  tests\notes.keyline.txt
    170     174     662  total (2 files)
change: o200k 104 -> 66 (-37%), cl100k 106 -> 68 (-36%)
```

Files are counted as stored: a trailing newline or CRLF line endings add tokens. A folder is
walked recursively; hidden files and folders, `cache/`, `__pycache__/` and `node_modules/` are
skipped, and a symlinked sub-folder is not followed (a symlinked file, or a symlink named as an
argument, is). The change line is printed only for exactly two file arguments that were both
counted. Exit 0 when every argument produced a row; 1 when one did not (a skipped file, an empty
folder: `nothing counted for ARG` on stderr); 2 for a usage error, an encoding tiktoken cannot load, or an argument that is missing,
cannot be read or is not a regular file or folder (a named pipe).

## Wiring the hook into one repo

1. In the repo, create `.claude/settings.json` to share the hook with the repo, or
   `.claude/settings.local.json` to keep it personal. Generate a ready-to-paste entry with
   `python keyline_hook.py --print-config` (it uses this Python and this keyline folder), or
   replace `__PYTHON__` and `__KEYLINE_DIR__` in `hooks-example.json`. Paste the result.
   If the file already has a `"hooks"` key, add the `PostToolUse` entry to it instead.
2. Keep notes in a `notes/` or `plans/` folder of that repo. The hook ignores every other path
   (a `notes/` folder outside the project too, and a dotfile or dotted folder below `notes/`,
   such as `.obsidian/`), and only acts on `.txt`, `.md`, `.keyline` or
   extension-less files. To watch specific files
   instead, append `--watch PATTERN` to the command (repeatable; fnmatch, case-insensitive; an
   absolute pattern matches the absolute path, a relative one the path from the project dir;
   the suffix rule still applies, so a watched `.py` file is passed over).
   Example: a repo whose `.claude/settings.local.json` appends `--watch /path/to/repo/PROGRESS.md`
   checks only that file, wherever it is written from. A `--watch` without a pattern, with a
   blank one or one starting with `--`, or any other argument, exits 1 with one line on stderr.
3. Put a Hebrew rendering of `notes/x.txt` at `notes/x.he.txt` (or `x.he.md`, `x.he.keyline`; any
   case). The hook then checks it whenever either file is written or edited: a rendering is
   checked against every note with its stem (`x.txt`, `x.md`, `x.keyline`, `x`) and is not linted.
   A file is a note only with a note suffix, in both directions: `data.json.he.txt` is not checked
   against `data.json`, nor `v1.2.he.txt` against `v1.2`.
4. Optional: add `keyline-allow.txt` at the repo root for project names that split into tokens.
5. Paste `CLAUDE-snippet.md` into the repo's CLAUDE.md.
6. Start a new Claude Code session in the repo so it loads the settings.

How it behaves: the matcher is `Write|Edit`. On findings the hook exits 2 and prints them to
stderr; when a file cannot be read, tiktoken is missing or an argument is wrong it exits 1
(non-blocking, one line on stderr). When the only findings are `INCONCLUSIVE` renderings, the
header says the rendering could not be checked, which is not a pass, rather than that the note
breaks the rules. For PostToolUse, Claude Code shows that stderr to Claude after the file is written, so
Claude fixes the file. The generated command uses absolute paths, so the repo can be anywhere.
The hook has been tested by piping simulated PostToolUse events through the generated command. It has not yet run inside a live Claude Code session.

## Reproduction

```bash
python tests/run_tests.py
```

The suite prints its final count; the current tree passes `35/35` on Linux and macOS and `36/36` on Windows (one path check is Windows only). Token counts match the panel exactly:

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
- The Keyline notes example passes the lint only because `pnpm` is on the built-in allow list (`--no-allow` fails it on `pnpm`).

## Honest limits

- Token counts come from OpenAI tokenizers. Claude's tokenizer is not public, so treat every count
  and percentage as a proxy. Check real numbers with Anthropic's count_tokens endpoint.
- The checker only sees tokens it can extract. It cannot catch a wrong verb, a swapped actor, a
  reversed causal chain or an invented sentence.
- Proper-noun detection is a heuristic: it skips the first word of a sentence/line and common
  furniture, so a name at the start of a sentence can be missed, and a capitalized common word
  mid-sentence can be checked. It is meant to fail closed, not to be a parser.
- Hedges are checked by class (possibility, probability, obligation, ability), not word-for-word:
  `could` -> `may` passes; `could` -> `will` fails. A hedge that changes class but keeps the
  same meaning is reported. Hebrew hedges come from a word list (עלול, ייתכן, כנראה, צריך, אמור,
  יכול, ניתן and their inflections); a Hebrew hedge spelt another way is not seen, and a Hebrew
  source gains a hedge class only from those words. Some of them have plain senses too (ניתן
  "was given", סביר "reasonable"), so a Hebrew source with one of those fails against an
  English rendering that does not hedge.
- Month and weekday names are accepted in English or in their Hebrew form, with up to three
  prefix letters (ב, מ, ל, ה, ו, ש, כ) and Hebrew-letter boundaries, so a word that is a prefix
  plus the name (לשבת, "to sit") still counts as the name; a rendering that writes the date as a number instead of the name is still a miss.
- A time with `:00` seconds matches with or without them (`14:30` and `14:30:00`); other seconds
  must be written. `May` is the month when a number, `:` or the line end follows, or a closing
  `**` followed by `:`, a number or the line end (`**May**: 3`, `## **May**`), or when it is not at
  a sentence start, or when a month name joined by `,`, `&`, `and`, `or`, `to`, `through`,
  `until` or `till` follows (`May, June and July`), or `is`, `was`, `has`, `had`, `will` or a
  period (`May was busy.`); `May I help?`, `May, I ask, ...`, `May the tests pass.`,
  `**May** we ship?` and `## Risks. May we ship?` are the modal
  verb (a header line is no exception of its own). An all-caps `MAY` is the modal only in an
  all-caps line, `_MAY_` emphasis included.
- The extension rule fails closed on some faithful English: `Postgres-based` for `Postgres`
  is an extension, and so is a name pair with a hyphen (`Paris-Berlin`). It also lets a name gain
  a slash pair (`Jean-Luc/Picard` for `Jean-Luc`), and a hyphenated pair of a time, date or version
  with another of its family (`v2.1-v2.3` for `v2.1`) passes as a range.
- Negations are counted, not aligned. A rendering that drops one negation and adds another
  elsewhere passes. Hebrew אף also means "even", so it can be over-counted. A
  negation inside underscore emphasis (`_not_`) counts; `No. 5` is a number sign, not a negation,
  only after a word on the same line, emphasis marks aside (`Ticket No. 5`, `Ticket **No. 5**`);
  anywhere else (`Up? No. 5 are down.`, `A: No. 5 fail`, `(no. 3 ...)`, a line that starts
  `No.`) it is the negation. A lowercase `no.` is a number sign only after a digit
  (`Item 3 no. 5`); after a word it is the answer (`I'd say no. 3 fail`), so `ticket no. 5`
  counts as a negation (fails closed). Each of these "No. N" negations counts in the rendering
  only as often as the source has one, so it cannot stand in for a dropped negation
  (`Do not deploy. Ticket No. 5.` to `Deploy. ticket no. 5.`, `Deploy. Ticket: No. 5.` or
  `Deploy (No. 5).` fails). The number must
  follow on the same line. `Ticket No 5` without the period counts as a negation (fails closed).
- Lowercase kebab names such as `checkout-api`, and two-word lowercase paths such as `src/auth`,
  are not extracted as invariants. Nor are hex hashes without a digit (`deadbeef`), lowercase
  words without a digit (`utf`, `prisma`) or a one-letter acronym plural (`Qs`); `PRs`, `sha256`,
  `b07b3b6`, `__init__`, `v2`, `S3`, `1e10` and `0x1f` are. A hex digest counts as a hash at 7 to
  128 digits (a SHA-512 included). A URL is one token with its scheme, so a rendering that drops
  `https://` misses it. Capitalised names in any cased script (`Émile`, `Ölçer`) are extracted;
  Hebrew has no case, so a Hebrew name is not. A sign is not part of a number
  (`-5` is the number `5`), so a rendering that drops it passes.
- The abbreviation lint only catches inventions that split into several tokens. The o200k
  vocabulary is multilingual, so short shorthands that are already one token pass: rb, cfg, err,
  conn, svc, msg, idx and others. Those are allowed by the spec. k8s, mgmt, dflt and similar are
  flagged. UPPER_CASE codes such as XH are treated as identifiers and never flagged.
- The shape rule is a heuristic. Invented compounds of 6+ letters (dbpool, oncall) pass, and pkts
  passes because pkt is one token. A short real word with one vowel that splits into tokens, such
  as blurb, is still flagged: use the allow file.
- The hook nudges; it does not block the write. The file is already on disk when it runs.
