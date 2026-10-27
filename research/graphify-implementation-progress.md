# Graphify-derived improvements: resume point (2026-10-27, after review pass 1)

## State
- Branch `graphify-ideas` (from main b46792d, main merged in with a merge commit; never force-push). Draft PR #27, subscribed.
- Done and pushed: item 2 drift tests (3f30b51), item 3 pyflakes + Python 3.10/3.13 CI (3f30b51), item 4 CONTRIBUTING / PR template / hook security model (06c3224), item 1 first half, marker section in `~/.claude/CLAUDE.md` (a9b35d3; premortem `research/premortem-marker-section.md`), item 5 `scripts/ledger.py` + `research/measurements.jsonl` (c7c3fa2), item 7 `add_to_repo.py --handoff-at` with object-valued template keys merged key by key (a59ed16). PR #27 body updated.
- Review pass 1 (fresh fable agent, head 5a18f22): 9 findings, all fixed class-wide with failing-first tests; record `research/review-findings-graphify-5a18f22.md`. Includes source rule 6 (every json.load/loads handles RecursionError) and backup reuse in `install._backup`.
- Next: review pass 2 with a NEW fresh fable agent on the fixed head; repeat until a pass finds nothing; then merge on green CI.

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

Before every push: `python -m pytest -q`, `python -I keyline/tests/run_tests.py`, `python -m pyflakes .`, `python -m json.tool` on `config/user-settings.json`, `config/repo-settings.json`, `.claude/settings.json`. Python 3.10 venv for local runs: scratchpad `py310/bin/python`.

## Open items
- Review pass 2 and later, merge.
- Not fixed (outside this PR): `keyline/keyline_lint.py:197` numbers lines with `str.splitlines()` (a U+2028 shifts reported lines).
