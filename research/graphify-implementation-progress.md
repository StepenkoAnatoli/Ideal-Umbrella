# Graphify-derived improvements: resume point (2026-10-27)

## State
- Branch `graphify-ideas` (from main b46792d, main merged in with a merge commit; never force-push). Draft PR #27, subscribed.
- Done and pushed: item 2 drift tests (3f30b51), item 3 pyflakes + Python 3.10/3.13 CI (3f30b51), item 4 CONTRIBUTING / PR template / hook security model (06c3224), item 1 first half, marker section in `~/.claude/CLAUDE.md` (a9b35d3; premortem `research/premortem-marker-section.md`).
- Next: item 5 `scripts/ledger.py`, item 7 `add_to_repo.py --handoff-at N`, then the review loop, then merge.

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
- Item 5: `scripts/ledger.py` (stdlib, `-I`, never raises, utf-8 stdout, opt-in manual): appends one JSON line per run to `research/measurements.jsonl`, prints the delta to the previous line. Seed the file with the 71,396 observation labelled as transcribed from the README; cite it in README fixed-load row; README Contents; CHANGELOG; tests.
- Item 7: `--handoff-at N` positive int -> `env.IDEAL_UMBRELLA_HANDOFF_AT` (string) in `.claude/settings.json`; other env keys kept; a differing value kept unless `--force`. Tests, README "Single-repository cloud sessions", CHANGELOG.
- Review loop: findings in `research/review-findings-graphify-<sha>.md` (Finding / Fixed / Other hits / Prevention), fixes failing-first and class-wide.

Before every push: `python -m pytest -q`, `python -I keyline/tests/run_tests.py`, `python -m pyflakes .`, `python -m json.tool` on `config/user-settings.json`, `config/repo-settings.json`, `.claude/settings.json`. Python 3.10 venv for local runs: scratchpad `py310/bin/python`.

## Open items
- Items 5 and 7, review loop, merge, PR #27 body update.
