# keyline

Tools for Keyline machine notes: keyed, terse, whole-word English notes that an LLM writes for
itself (one `key: item; item` line per topic), with a deterministic check that no fact was lost
when a note is rendered to Hebrew or prose. Design and measurements:
`../research/panel-results.md` (section `=== SPEC ===`).

## Files

| File | What it does |
|---|---|
| `keyline_check.py` | Fact check: source note vs one or more renderings. Fails if a rendering is missing any date, time, version, URL, number, percentage, UPPER_CASE identifier (plurals such as `PRs` and Latin letters with diacritics such as `ÉCOLE` included), hex hash (7 to 128 digits), path, CamelCase name, proper noun (Latin letters with diacritics included), file name, snake_case or dunder token, or lowercase identifier with a digit (`sha256`, `utf8`) of the source, drops a hedge class, or has fewer negation words. A month or weekday name may appear in its Hebrew form. A source with no extractable invariant and no hedge is `INCONCLUSIVE`, not `PASS`. |
| `keyline_lint.py` | Style lint for a notes file: markdown furniture and invented abbreviations. |
| `measure.py` | o200k_base and cl100k_base token counts per file or per folder, with a before/after change line for two files. |
| `keyline_hook.py` | Claude Code PostToolUse hook for notes under `notes/` or `plans/` of the project: runs the lint, and the check when a sibling `.he.txt` or `.he.md` rendering exists. `--print-config` prints a ready-to-paste hook entry for this install. |
| `hooks-example.json` | Template hook entry. Replace `__PYTHON__` and `__KEYLINE_DIR__`, or use `keyline_hook.py --print-config` instead. |
| `CLAUDE-snippet.md` | The standing rule for a repo's CLAUDE.md (98 tokens o200k, header included). |
| `tests/` | The panel's worked examples and `run_tests.py`, which reproduces their results. |
| `cache/` | Built on first use: tiktoken encodings and the single-token word list. |

## Setup

The scripts need Python 3 (CI runs 3.12) and tiktoken (pinned in `requirements.txt`). Install it
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

Matching is exact and case-sensitive, by extraction: a token of the source is present when the
rendering's own extraction yields the same token, so `5` does not count as present because `503`
is, a bare number does not count inside a time or a grouped number (`10` is not in `10:00`, `2`
is not in `2,500`), a path or name does not count inside a longer one (`notes/a.txt` is not in
`notes/a.txt.bak`, `Jean-Luc` is not in `Jean-Luc-Picard`), but a Hebrew prefix glued to an
identifier or a path (`בv2.14.0`, `ב-__tests__/`) still counts, and so does a name the rendering
moves to the start of a sentence. A name that ends in a digit takes a dotted tail (`Python3.12`, `GPT4.5`, `python3.12` are one token each, as `v2.14.0` is); a name that ends in a letter takes none and is no token before the dotted number (`No.5`, `Fig.3`, `A.1` yield the number 5, 3, 1 alone: the abbreviation is prose a rendering translates, `No. 5`, `מס' 5`, `איור 3`, and the number is what it must keep), except a file name, whose dotted components after the stem may be numbers as well as letter extensions, in any order, as long as one is a letter extension (`app.log.1`, `backup.tar.gz.1`, `app.log.1.gz`, `syslog.2.gz` are one token each; `syslog.1`, with no extension, is the number alone). A date or a time between a file name's components is inside the file name (`backup.2026-10-25.sql`, `app.log.2026-10-25.gz`, `db.sql.14:30.gz`, `app.log.2026-10-25T14:30:00.000Z.gz` are one token each; a path's dotted tail follows the same rule: `notes/db.sql.14:30.gz` is one token, `notes/app.log.2026-10-25` the path and the date), at most two of them on each side of the first extension (`notes.txt.2026-10-25.2026-10-26` is a file name; a third date ends it and is a date of its own), while a dotted component that opens a date, a time or a percentage at the end of a name is not part of it: `app.log.2026-10-25T14:30Z` is the file name `app.log` and the timestamp, `db.sql.14:30` the file name and the time, `notes.txt.12.5%` the file name and the number `12.5%`, `GPT4.5%` the name `GPT4` and the number `5%`, each held to the rendering on its own. A `v` version ends before an interior date or time, which makes a file name (`v2.2026-10-25.txt`, `v2.14:30.txt` are one token each; `v2.2026-10-25T14:30Z` is the version `v2` and the timestamp), and before a capitalised word, which is a name of its own (`v5.6.15.Final` is the version `v5.6.15` and the name `Final`), except a lone capital letter, which stays on the version (`v2.A`). A capitalised word that opens a sentence is not held to the rendering (its capital proves nothing), unless it has a digit in it (`Python3.12 is required`, `Node18 is required`): a word with a digit is a name wherever it stands; and a period glued to the word after a digit or a capital (`J.Smith`, `v5.6.15.Final`) does not open a sentence, so `Smith` and `Final` are checked. A date and a time are the same instant written as one token or
two: `2026-10-25 14:30` passes against `2026-10-25T14:30Z` and `2026-10-25T14:30` against `2026-10-25 14:30`; a rendering may add seconds, fractional seconds or both, before a zone the source has (`14:30Z` is present in `14:30:00.000Z`) or without one (`14:30:00` in `2026-10-25T14:30:00.000Z`), and a zone (`Z`, `+02:00`) to a time or timestamp that has none, but a zone or a fraction the source has and the rendering drops is a miss. Markdown
list numbers (`1. ` to `999. `) are not facts and are skipped; `2024. ` starts with a year.
Proper nouns are extracted
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

- Furniture: a line starting with a bullet (`- `, `* `, `+ `), a numbered item (`1. `, `2) `) or a
  header (`#` to `######`), or any `**` or backtick.
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
  built-in list in `keyline_lint.py`. Other real names go in a `keyline-allow.txt`, one per line (several words on one line are each allowed; `#` starts a comment).
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

Files are counted as stored: a trailing newline or CRLF line endings add tokens.

## Wiring the hook into one repo

1. In the repo, create `.claude/settings.json` to share the hook with the repo, or
   `.claude/settings.local.json` to keep it personal. Generate a ready-to-paste entry with
   `python keyline_hook.py --print-config` (it uses this Python and this keyline folder), or
   replace `__PYTHON__` and `__KEYLINE_DIR__` in `hooks-example.json`. Paste the result.
   If the file already has a `"hooks"` key, add the `PostToolUse` entry to it instead.
2. Keep notes in a `notes/` or `plans/` folder of that repo. The hook ignores every other path
   (a `notes/` folder outside the project too, a dotfile such as `notes/.gitignore`, and a file
   under a dot folder such as `notes/.trash/x.md`), and only
   acts on `.txt`, `.md`, `.keyline` or extension-less files. To watch specific files
   instead, append `--watch PATTERN` to the command (repeatable; fnmatch, case-insensitive; an
   absolute pattern matches the absolute path, a relative one the path from the project dir;
   the suffix rule still applies, so a watched `.py` file is passed over, while the dot rule
   gives way to a pattern that spells the dot at that component: `notes/.todo.md` or `notes/.*`
   means the dotfile and `notes/.trash/*` the file under the dot folder, `notes/*` means
   neither, as in a shell). A `--watch` with no
   pattern, or any other flag, is an error on every write (exit 1, one line on stderr), not a
   silent fall-back to the `notes/`/`plans/` rule.
   Example: a repo whose `.claude/settings.local.json` appends `--watch /path/to/repo/PROGRESS.md`
   checks only that file, wherever it is written from.
3. Put a Hebrew rendering of `notes/x.txt` at `notes/x.he.txt` (or `notes/x.he.md`). The hook
   then checks it whenever either file is written or edited. Two notes beside one rendering
   (`x.txt` and `x.md`) are a finding of their own, whichever of the three files is written: the
   first line says to keep the one it renders, the notes are named, and the check waits until
   one note is left.
4. Optional: add `keyline-allow.txt` at the repo root for project names that split into tokens.
5. Paste `CLAUDE-snippet.md` into the repo's CLAUDE.md.
6. Start a new Claude Code session in the repo so it loads the settings.

How it behaves: the matcher is `Write|Edit`. On findings the hook exits 2 and prints them to
stderr, headed by the file to fix: the note when the lint found something, else the rendering (a
note write that leaves its rendering stale is fixed in the rendering); when the note cannot be read or tiktoken is missing it exits 1 (non-blocking, one line on
stderr). For PostToolUse, Claude Code shows that stderr to Claude after the file is written, so
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
- A file name that is not UTF-8 is printed as a backslash escape of its surrogate code point
  (`\udcff`), not as the byte.
- Proper-noun detection is a heuristic: it skips the first word of a sentence/line and common
  furniture, so a name at the start of a sentence can be missed, and a capitalized common word
  mid-sentence can be checked. It is meant to fail closed, not to be a parser.
- Hedges are checked by class (possibility, probability, obligation, ability), not word-for-word:
  `could` -> `may` passes; `could` -> `will` fails. A hedge that changes class but keeps the
  same meaning is reported. A hedge set in underscore italics (`_could_`, `_may_`) is not seen,
  in a source or a rendering; `*could*` is. Hebrew hedges come from a word list (עלול, ייתכן, כנראה, צריך, אמור,
  יכול, ניתן and their inflections); a Hebrew hedge spelt another way is not seen, and a Hebrew
  source gains a hedge class only from those words. Some of them have plain senses too (ניתן
  "was given", סביר "reasonable"), so a Hebrew source with one of those fails against an
  English rendering that does not hedge.
- Month and weekday names are accepted in English or in their Hebrew form, with up to three
  prefix letters (ב, מ, ל, ה, ו, ש, כ) and Hebrew-letter boundaries, so a word that is a prefix
  plus the name (לשבת, "to sit") still counts as the name; a rendering that writes the date as a number instead of the name is still a miss.
- Negations are counted, not aligned. A rendering that drops one negation and adds another
  elsewhere passes. Hebrew אף also means "even", so it can be over-counted.
- Lowercase kebab names such as `checkout-api`, and two-word lowercase paths such as `src/auth`
  (one slash between two plain lowercase words is prose, `and/or`, `él/ella` and `כן/לא` alike, at
  the end of a sentence too; a dot inside, a digit, an underscore, a dash, a capital or a second slash makes it a path), are not
  extracted as invariants. Nor are hex hashes without a digit (`deadbeef`) or longer than
  128 digits (a letter-first one is a lowercase identifier instead; a digit-first one is a number when all its letters follow the digits, `1aaa…`, and nothing when a digit follows a letter, `1a1a…`: none is a hash), lowercase words without a digit (`utf`, `prisma`) or a one-letter acronym plural
  (`Qs`); `PRs`, `sha256`, `b07b3b6`, a sha256 or sha512 digest, `__init__`, `v2`, `S3`, `1e10`,
  `0x1f`, `Python3.12` and `https://x.y/z` (scheme included) are; `Python3.12rc1`, a name whose dotted tail ends in letters, is nothing, and a name that ends in a letter before a dotted number (`Zürich.5`, `my_lib.5`, `syslog.1`) yields the number only, unless it has a letter extension (`app.log.1`, `app.log.1.gz` are one file name each). A file name's stem is one character only when it is a lowercase letter before a lowercase extension of two or more letters that no period follows, after the dotted numbers and dates any stem takes (`a.out`, `a.py`, `a.1.out`, `x.tar.gz.1`, `x.2026-10-25.tar.gz` are one token each), so that `e.g.`, `i.e.`, `x.y`, `p.ex.`, `f.eks.`, `z.Bsp.`, `v.Chr.`, `J.Smith` and `2.nd` are prose; `a.out.` at the end of a sentence is not extracted. A date the source names alone is found inside a file name before an extension (`2026-10-25` is in `backup.2026-10-25.sql`) but not before a rotation number (`app.log.2026-10-25.1`). A sign is not part of a number (`-5` is the
  number `5`), so a rendering that drops it passes.
- A name is a capitalised word of ASCII letters or Latin letters with diacritics (`Zürich`, `Léa`,
  `Øyvind`, `São`, `Łukasz`), and an all-caps one (`ÉCOLE`, `NGUYỄN`) is an identifier; a name in another script (Greek, Cyrillic, Hebrew) is not extracted. A CamelCase name is ASCII-only (`ZürichAirport` is a proper noun because it starts capital-lowercase; `xZürichAirport` is nothing). A file name or path may start with a Latin letter with a diacritic (`Übersicht.md`, `école/notes.txt`) or a Hebrew letter (`סיכום.md`, `תיקיה/קובץ.txt`). A Hebrew prefix letter glued to a Latin token (`בnotes/a.txt`, `ב-__tests__/`) stays out of it, but one glued to a Hebrew name (`בסיכום.md`) is part of the token, so the source's `סיכום.md` is not found there and the check fails closed; write it with a dash (`ב-סיכום.md`).
- Presence is decided by extraction, so a rendering that joins a token to something else fails
  closed even when the fact survived: `Postgres` is not found in `Postgres/Prisma` (a path to the
  extractor), `10` not in `10/` and `API` not in `API.md`. A numbered item of up to three digits
  is a list marker, so a line that starts with `503. ` loses the number; `2024. ` keeps it.
  `No. 5` is a number sign, not a negation; `no 5xx errors` (no dot) still counts as one, and so does `no.` at the end of a line, whatever number the next line starts with (likewise `May` before a number on the next line is the modal, not the month, unless `May` is the whole content of its line: a heading or label such as `## May`, `## May ##`, `**May**`, `**May**:` or `May:` is the month, as are `**May** 5`, `***May*** 5` and `May, 2026` on one line, and so is a bare `May` line unless the sentence it opens ends in a question mark, `May\n5 items be removed?`).
- An allow-file line with several words allows each of them; the rule stays one word per line
  because a comment after `#` applies to the whole line.
- The abbreviation lint only catches inventions that split into several tokens. The o200k
  vocabulary is multilingual, so short shorthands that are already one token pass: rb, cfg, err,
  conn, svc, msg, idx and others. Those are allowed by the spec. k8s, mgmt, dflt and similar are
  flagged. UPPER_CASE codes such as XH are treated as identifiers and never flagged.
- The shape rule is a heuristic. Invented compounds of 6+ letters (dbpool, oncall) pass, and pkts
  passes because pkt is one token. A short real word with one vowel that splits into tokens, such
  as blurb, is still flagged: use the allow file.
- The hook nudges; it does not block the write. The file is already on disk when it runs.
