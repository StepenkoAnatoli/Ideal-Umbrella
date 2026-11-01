# Brief: implement the graphify-derived ideas (2026-10-26)

Owner of the work: a new Claude Code session (implementer: Opus 5.5; reviewer passes: Fable 5.1 in fresh context). The user starts it with "go"; nothing is changed before that.

## Request (user, 2026-10-26)
"implement the suggestions in new chat but tell him not to start before my go ... when he finishes, deploy fable 5.1 to review the work and fix the findings and then check again after he fixes the check findings tell him to check again until cant find anything and only when all done merge it. tell him to open new pr and use the current #24 only as a reference for understanding the work (ill close pr #24 when we finish)"

## Source of the ideas
`research/graphify-comparison.md` on branch `ccr-18e63515-crkba1` (PR #24, reference only; read it with `git fetch origin ccr-18e63515-crkba1 && git show origin/ccr-18e63515-crkba1:research/graphify-comparison.md`). Do not push to that branch and do not reuse PR #24. Start a new branch from `main` and open a new draft PR.

## Scope
In: items 1-5 and 7 of the comparison, in its "Suggested order" (2 and 3 first, then 4, then 1, then 5, then 7).
- 1: marker-delimited Ideal-Umbrella section in `~/.claude/CLAUDE.md` (exact-match H1 marker, append or replace the section only, uninstall removes the section only and deletes the file only when nothing else is left, verify compares the section only, record stores the section's sha256). Only the first half: `add_to_repo.py` writing the section into a repository's own CLAUDE.md stays out until a cloud measurement exists.
- 2: `tests/test_docs_match_source.py`: `cloud-setup.sh` heredoc == `config/CLAUDE.md` + its cloud-only line; every backtick path under README "Contents" exists; the README deny list and the two numeric keys equal `config/user-settings.json`. (`.claude/settings.json` and `config/repo-settings.json` differ by design in the hook path, `hooks/` vs `.claude/hooks/`; do not test them equal.)
- 3: pyflakes (or ruff default rules) as a CI step; Python 3.10 and 3.13 added on Ubuntu, Windows stays 3.12; supported range stated in README "Quick start"; fix whatever the older interpreter reveals.
- 4: `CONTRIBUTING.md` (about 30 lines: failing-first test, fix the class and list other hits, the three recurring classes, stdlib only, `-I` for untrusted input, both OSes, keyline for notes, every README number names its script), `.github/PULL_REQUEST_TEMPLATE.md` (what changed, class fixed, commands actually run, README/CHANGELOG touched), and a "Security model" paragraph for the hook in the README.
- 5: `scripts/ledger.py` appending one JSON line per manual run to `research/measurements.jsonl` and printing the delta to the previous line; the README's fixed-load row cites a ledger line. Never raises; opt-in and manual.
- 7: `add_to_repo.py --handoff-at N` writing `env.IDEAL_UMBRELLA_HANDOFF_AT` into `.claude/settings.json`.
Out: item 6 (re-read nudge hook) and the graphify-on-a-large-project experiment; both need measured sessions. Multi-host install, bots, pre-commit: not a fit.

## Repo rules that bind this work
- Failing-first test for every behaviour change; fix the class, not the instance (`research/pr-cleanup-progress.md`, "Recurring classes to watch": neighbour of a previous fix, halfway state, absent is not empty). The `first-pass:premortem` skill before the marker-section change; `first-pass:fix-the-class` for each defect.
- Stdlib only. Scripts that read untrusted files run under `-I`. Ubuntu and Windows both pass. Atomic writes, backups and the install record as in `config/install.py` today.
- Before every push: `python -m pytest -q`, `python -I keyline/tests/run_tests.py`, pyflakes on the whole repo, `python -m json.tool` on the three JSON configs. CHANGELOG.md and README.md updated with the code.
- Merges use a merge commit. Merge only when the user's go covered it (it does: "only when all done merge it"), CI is green on the final head, and the last review pass found nothing.

## Review loop (after the implementation is complete and CI is green)
1. Run a fresh-context review of the whole PR diff with the `first-pass:breaker` agent, model `fable` (Fable 5.1). Give it the diff base, the brief and the scope; ask for findings it can make concrete, with file:line.
2. Fix every finding class-wide with a failing-first test; record each in `research/review-findings-graphify-<sha>.md` (Finding / Fixed / Other hits / Prevention), the format of the existing `research/review-findings-main-*.md` files.
3. Run the review again on the new diff (a new breaker agent, model `fable`, fresh context). Repeat 2-3 until a pass reports no findings. Only then merge, with a merge commit, after CI is green on the final head.

## Reporting (user's standing rules)
- Full details in files; chat replies are a gist of at most 5 lines plus the file path.
- Resume point: `research/graphify-implementation-progress.md` (state, decisions and why, open items, file paths); replace it, do not append; commit and push it at every step boundary and before any hand-off (cloud machine is discarded).
- When all is merged: update the resume point, say so in one line with the PR link.
