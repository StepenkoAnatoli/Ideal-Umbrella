# Graphify-derived improvements: resume point (2026-10-27, after review pass 4)

## State
- Branch `graphify-ideas` (from main b46792d, main merged in with a merge commit; never force-push). Draft PR #27, subscribed.
- Done and pushed: item 2 drift tests (3f30b51), item 3 pyflakes + Python 3.10/3.13 CI (3f30b51), item 4 CONTRIBUTING / PR template / hook security model (06c3224), item 1 first half, marker section in `~/.claude/CLAUDE.md` (a9b35d3; premortem `research/premortem-marker-section.md`), item 5 `scripts/ledger.py` + `research/measurements.jsonl` (c7c3fa2), item 7 `add_to_repo.py --handoff-at` with object-valued template keys merged key by key (a59ed16). PR #27 body updated.
- Review pass 1 (fresh fable agent, head 5a18f22): 9 findings, all fixed class-wide with failing-first tests; record `research/review-findings-graphify-5a18f22.md`. Includes source rule 6 (every json.load/loads handles RecursionError) and backup reuse in `install._backup`.
- Review pass 2 (fresh agent on the default model, because the Fable usage limit was reached; head db5cd0c): 13 findings (1 medium, 7 low, 5 info), all fixed class-wide with failing-first tests in 68e1c61; record `research/review-findings-graphify-db5cd0c.md`. Main changes: fenced copies are never wrapped (`_unfenced_copy`), an unclosed fence is ordinary text, `find_section(text, recorded)` falls back to the recorded hash, the full record is written before any other file, `_check_json` (depth 100, lone surrogates) after every JSON read (source rule 7), installer-named backups only.
- Review pass 3 (fresh agent on the default model, Fable limit again; head f6ca6ef): 10 findings (2 medium, 5 low, 3 info), all fixed class-wide with failing-first tests in the commit after f6ca6ef; record `research/review-findings-graphify-f6ca6ef.md`. Main changes: the record written first keeps the one it replaces as `pending` and `settle_record` resolves it against the files (update runs stopped by a failed write are undone completely); `_backup` writes whole or not at all; the wrap path keeps the record's `wrapped`; a section found only by the hash inside a code fence is never changed (`fenced_line`, `fence_advice`); non-finite floats rejected and `allow_nan=False`; a non-UTF-8 hook path stops install before any write; every script prints with `errors="backslashreplace"` (source rule 3); `tests/test_failed_writes.py` covers five kinds of run.
- Review pass 4 (fresh agent on the default model, Fable limit again; head 032a6bf): 3 low findings, 1 info finding (6 surviving mutants), 5 notes, all fixed or noted with failing-first tests in the commit after 032a6bf; record `research/review-findings-graphify-032a6bf.md`. Main changes: uninstall reads `joined` as a number of line breaks (line endings changed after install); a rerun writes the settled record when the earlier one kept `pending`; the edited-section backup is named `edited_backup` and deleted by uninstall when CLAUDE.md holds the same bytes; a kept safety backup is named; no "part way" before any step; mutant tests for M1, M6, M8, M22.
- Next: review pass 5 with a NEW fresh agent (fable if the limit allows, else the default model), findings to the scratchpad `review5-findings.md`, brief listing all four findings files; fix like before; repeat until a pass finds nothing; then merge on green CI.

## Scope (from the user; brief and comparison on `origin/ccr-18e63515-crkba1`, read only; PR #24 not reused)
- In: items 2, 3, 4, 1 (first half only: `add_to_repo.py` writing into a repo CLAUDE.md is OUT), 5, 7.
- Out: item 6, any graphify-as-dependency experiment.
- Merge with a merge commit when the review loop has a clean pass and CI is green on the final head; no further confirmation needed.

## Decisions and why
- Markers are exact whole lines `<!-- Ideal-Umbrella rules: begin -->` / `<!-- Ideal-Umbrella rules: end -->` (trailing whitespace ignored), not headings: `config/CLAUDE.md` has two H1 headings, so a heading boundary would cut it.
- Old whole-file installs migrate: record hash == whole file -> section, old backup kept as `legacy_backup`, restored on uninstall.
- An exact unmarked copy of the rules is wrapped in markers rather than duplicated; uninstall then removes only the marker lines.
- Uninstall never writes back a non-UTF-8 file it decoded leniently.
- `config/cloud-setup.sh` stays whole-file (cloud machine starts empty).
- pyflakes over ruff (pure Python, already used by hand).
- `first-pass:premortem`, `first-pass:fix-the-class`, `first-pass:breaker` are not installed: done by hand; review passes are fresh general-purpose agents on model `fable` with a breaker brief.

## Plan for the rest
- Review loop: findings in `research/review-findings-graphify-<sha>.md` (Finding / Fixed / Other hits / Prevention), fixes failing-first and class-wide; repeat with a new agent until a pass finds nothing; then merge with a merge commit on green CI, update this file, one-line reply with the PR link.
- Other hit noted for item 7's class: `config/install.py merge_settings` merges its only object key (`permissions`) by hand; a future object key in `config/user-settings.json` would need the same.

Before every push: `python -m pytest -q` (also with the Python 3.10 venv), `python -I keyline/tests/run_tests.py`, `python -m pyflakes .`, `python -m json.tool` on `config/user-settings.json`, `config/repo-settings.json`, `.claude/settings.json`. Python 3.10 venv for local runs: scratchpad `py310/bin/python`.

## Open items
- Review pass 5 and later, merge.
- Not fixed (outside this PR): `keyline/keyline_lint.py:197` numbers lines with `str.splitlines()` (a U+2028 shifts reported lines).
