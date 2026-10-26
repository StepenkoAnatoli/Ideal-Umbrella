# Graphify-derived improvements: plan and resume point (2026-10-26)

## State
- Plan only. Nothing committed, no branch, no push. Waiting for the user's "go".
- Base: main b46792d. Branch to create on "go": `graphify-ideas` from `origin/main` (this session designates no branch; HEAD is detached at main). New draft PR; PR #24 / `ccr-18e63515-crkba1` read only.
- Sources read: brief and comparison (on `origin/ccr-18e63515-crkba1`), README, ci.yml, config/install.py, uninstall.py, add_to_repo.py (structure), config/CLAUDE.md, cloud-setup.sh, the three JSON configs, research/pr-cleanup-progress.md, review-findings-main-51da01e.md (format).

## Order (comparison "Suggested order"; one commit per item, push at each step boundary)
1. Item 2, drift tests: `tests/test_docs_match_source.py`
   - heredoc body in `config/cloud-setup.sh` (lines 6-17) == `config/CLAUDE.md` + the one cloud-only line (parse between `<<'EOF'` and `EOF`; compare after normalising line endings only).
   - every backticked path in README "Contents" exists (glob-free; strip trailing `/`; names inside `config/` parentheses resolve under `config/`, `scripts/` names under `scripts/`).
   - README deny list (the six names in the "Never-used tools" row) and the two numeric keys equal `config/user-settings.json`. Not testing `.claude/settings.json` == `config/repo-settings.json` (differ by design).
   - Failing-first: each test is first run against a deliberately broken temp copy (a monkeypatched path) to show it fails, then on the tree.
2. Item 3, CI: `.github/workflows/ci.yml`
   - matrix: ubuntu 3.10, 3.12, 3.13; windows 3.12 (via `include`).
   - new step `python -m pyflakes .`; add `pyflakes` to `requirements-dev.txt` (dev-only, not a runtime dependency; stdlib-only rule is about shipped code).
   - README "Quick start": "Python 3.10 or later (CI: 3.10, 3.12, 3.13 on Ubuntu; 3.12 on Windows)"; `keyline/README.md:23` ("CI runs 3.12") updated.
   - Run the suite locally under 3.10 (`uv python install 3.10`; 3.11/3.12/3.13 are on the machine) and fix what it reveals, with tests.
3. Item 4, docs: `CONTRIBUTING.md` (~30 lines, content per brief), `.github/PULL_REQUEST_TEMPLATE.md` (what changed / class fixed / commands actually run / README and CHANGELOG touched), README "Security model" paragraph for the hook (`-I`, reads only the transcript tail, writes only under `~/.claude/ballast/`, `|| exit 0`, timeout 15 s). Drift test extended: CONTRIBUTING's command list matches README "Tests" (cheap twin check).
4. Item 1, marker section (the one behaviour change; premortem first, written into this file before code).
   - install: no file -> write section; file without section -> append (one blank line separator), never rewrite the user's text; file with section -> replace the section only. Backup before any change to a file that holds user text. Record `claude_md: {sha256: <section hash>, backup, created: bool}`.
   - uninstall: remove the section only; delete the file only when what is left is whitespace and the install created it; a section that differs from the recorded hash is left and reported; no section -> no-op.
   - verify: compares the section only; user text outside it passes; missing or differing section fails.
   - Migration: a record from the old whole-file install (file hash == file) is treated as "the whole file is our section" so re-install and uninstall stay correct.
   - Tests in `tests/test_install.py` / `tests/test_uninstall.py`, all failing-first: append to an existing file, idempotent re-install, template change replaces only the section, user lines before and after survive install+uninstall byte for byte, heading that merely starts with the marker (e.g. `# Ideal-Umbrella rules (mine)`) is not ours, CRLF file, section at EOF without trailing newline, two sections (refuse, report), old-format record migration, symlinked CLAUDE.md written through, dry-run.
   - README "Install", "Undo", "Manual install" step 2; CHANGELOG.
5. Item 5, ledger: `scripts/ledger.py` (stdlib, run with `-I`): args `--fixed-tokens N --first-call-cache-write N --tools N --deny-applied yes|no [--cc-version V] [--file research/measurements.jsonl]`; appends one JSON line with the date, prints the delta to the previous line; never raises (bad or missing file -> message, exit 0 for the append when possible, non-zero only for bad arguments). Seed `research/measurements.jsonl` with the existing 2026-10 observation (71,396), labelled as transcribed from README, and cite it in the README "Biggest costs still left" fixed-load row. Tests: append, delta, corrupt previous line, missing dir, unicode path.
6. Item 7, `add_to_repo.py --handoff-at N`: writes `env.IDEAL_UMBRELLA_HANDOFF_AT` (string, as Claude Code `env` values are strings) into `.claude/settings.json`; keeps other `env` keys; an existing different value is kept unless `--force` (same rule as scalars today); validates N is a positive int. Tests in `tests/test_add_to_repo.py`. README "Single-repository cloud sessions".
7. Review loop per the brief (breaker passes on model `fable`, fresh context each, until a pass finds nothing), findings in `research/review-findings-graphify-<sha>.md`; merge with a merge commit when CI is green on the final head.

Before every push: `python -m pytest -q`, `python -I keyline/tests/run_tests.py`, `python -m pyflakes .`, `python -m json.tool` on the three JSON configs.

## Decisions and why (proposed; the user can change them in "go")
- Marker shape differs from the comparison's proposal: `config/CLAUDE.md` already has two H1 headings ("# Side sessions and subagents", "# Long chats and restarts"), so "section runs to the next `# ` heading" would cut our own section in half. Proposed: explicit begin/end lines matched exactly, `<!-- Ideal-Umbrella: begin -->` / `<!-- Ideal-Umbrella: end -->` (about 16 tokens per session added). Alternative: wrap in `# Ideal-Umbrella rules` and demote our headings to `##`; rejected because it changes the rule text every session reads and still breaks if a user's H1 follows without a blank line. Exact-line match (graphify issue #2062 lesson).
- pyflakes over ruff: already the tool run by hand in every resume point; pure Python, pip-installable on every matrix entry.
- Python floor 3.10: the brief's range; to be confirmed by running the suite under 3.10.

## Risks
- Skills `first-pass:premortem`, `first-pass:fix-the-class` and the `first-pass:breaker` agent type are not installed in this session (not in the skill list, no plugin dir). Fallback: write the premortem and the fix-the-class records by hand in the repo's existing format, and run each review pass as a fresh `general-purpose` agent on model `fable` with a breaker brief (adversarial, file:line, repro command per finding). Will say so in the PR body.
- Python 3.10 is not on the machine; `uv python install 3.10` needs the network proxy. If it fails, CI is the first 3.10 run.
- Marker change touches the most-reviewed code (install/uninstall); halfway-state class (record written before settings.json) must keep holding; old-record migration is the main regression risk.
- README "Contents" test may force small README wording changes to make paths parseable.

## Open items
- User "go" (and any scope change).

## Files
- This file: `research/graphify-implementation-progress.md` (local, uncommitted).
- Reference: `origin/ccr-18e63515-crkba1:research/graphify-implementation-brief.md`, `...:research/graphify-comparison.md`.
