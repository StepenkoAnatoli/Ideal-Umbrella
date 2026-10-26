# Graphify-Labs/graphify compared with Ideal-Umbrella (2026-10-26)

Request (user): "Compare this repo to ideal umbrella and see if we can take some good ideas from there that fits perfectly to our repo."

Sources: graphify clone at commit 92741d1 (`git clone --depth 1`, read with `python3 -I`, treated as untrusted), its README, CONTRIBUTING.md, ARCHITECTURE.md, BENCHMARKS.md, docs/how-it-works.md, `graphify/install.py`, `graphify/benchmark.py`, `graphify/querylog.py`, `graphify/skill.md`, `tools/skillgen/gen.py`, its tests and CI; Ideal-Umbrella at main b46792d. Numbers quoted from graphify are its own claims, not re-measured here.

## The two repos in one paragraph each

**graphify** (135k stars, ~57k lines of Python, PyPI `graphifyy`) parses a codebase with tree-sitter into a knowledge graph (`graph.json`), clusters it (Leiden), and gives the model `graphify query/path/explain` so it reads a few hundred graph tokens instead of whole files. It ships a `/graphify` skill for 20+ hosts (Claude Code, Codex, Gemini CLI, Cursor), an always-on CLAUDE.md block, a PreToolUse hook that nudges "query the graph before Grep/Read", git hooks, an MCP server and a cloud product. It is a product with a community: translations, bots, CODEOWNERS, release automation, security policy.

**Ideal-Umbrella** (87 commits, stdlib only) cuts the fixed per-call context of Claude Code: a smaller `autoCompactWindow`, a tiny skill-listing budget, six denied tools, a 224-token rule file for side sessions and resume points, a `UserPromptSubmit` hook that reminds the model to hand off past 150k tokens, idempotent installers with records and backups, a cloud setup script, and measurement scripts over the transcripts. Every claim in its README is a measured number and "What did not work" is listed.

The overlap is the goal (fewer tokens per call) and the delivery vehicle (settings, CLAUDE.md, hooks). The difference is where the tokens go: graphify replaces file reads (tool results, ~30% of context in our measurements) with graph queries; Ideal-Umbrella shrinks the fixed load and the chat's own habits. So graphify the tool is not a fit as a dependency (see "Not a fit"), but several of its engineering habits are.

## Ideas that fit, ranked

### 1. Marker-delimited section in `~/.claude/CLAUDE.md` instead of whole-file replace (fits best)

What graphify does: `install.py` appends a `## graphify` section to the host's CLAUDE.md/AGENTS.md and removes it on uninstall with `_remove_marker_section(content, marker, boundary_prefix="## ")`: the heading line must equal the marker exactly (a substring match once deleted a user's own `## graphify-notes` section, their issue #2062), the section runs to the next `## ` heading or EOF, and a missing section returns None so the uninstall is a no-op. Install on an existing file appends, never rewrites; a second install finds the section and replaces only it.

What we do: `config/install.py` replaces `~/.claude/CLAUDE.md` wholesale (backup unless the record's sha256 says the file is still ours), and `--verify-only` fails with "CLAUDE.md content differs from config/CLAUDE.md" the moment the user adds a line of their own. A user who already has a global CLAUDE.md has to merge by hand or lose it to a backup.

Proposed: two H1 markers (`# Ideal-Umbrella rules` ... to the next `# ` heading or EOF, exact-match heading as in graphify), install = append or replace the section only, uninstall = remove the section only and delete the file only if nothing else is left, verify = compare the section only. The record keeps the section's sha256 instead of the file's. The one risk is the compaction summariser or the model editing inside the section; the verify step already reports a differing section, which is the right behaviour.

Cost: a day; install, uninstall, verify, tests (`tests/test_install.py`, `tests/test_uninstall.py`), README "Install" and "Undo". Benefit: removes the main reason a user with an existing CLAUDE.md cannot run `install.py`, and makes re-install and verify tolerant of the user's own rules. Also opens the second half of the idea: `add_to_repo.py` could write the same section into the repo's own `CLAUDE.md` so single-repo cloud sessions get the rules without pasting `cloud-setup.sh` into the environment setup script (README "Cloud sessions" says only `.claude/settings.json` is read; a repo `CLAUDE.md` is read in every session, so this needs one cloud measurement before it goes in the README).

### 2. Drift tests between generated or duplicated text and its source

What graphify does: `tools/skillgen/gen.py` treats fragment files as the source, regenerates `skill.md` per host, and `--check` byte-diffs the committed output in CI and in pre-commit; `--bless` rewrites it. Tests `test_architecture_doc.py` (imports every symbol the ARCHITECTURE.md module table names), `test_cli_help.py` (`--help` lists every command) and `test_claude_md.py` (install creates, appends, is idempotent) make the docs a contract.

Where we have the same drift risk today:
- `config/cloud-setup.sh` holds the whole of `config/CLAUDE.md` inside a heredoc plus one cloud-only line. A change to one and not the other is silent.
- README "What is applied to every session" repeats the two keys, the deny list and the hook timeout from `config/user-settings.json`.
- README "Contents" lists paths; a rename leaves a dead entry.
- README "Tests" and `ci.yml` both say what CI runs.

Proposed: one test file, `tests/test_docs_match_source.py`, with three tests: heredoc body == `config/CLAUDE.md` + the cloud line (or make `cloud-setup.sh` generated from `config/CLAUDE.md` by a small script with `--check`, as skillgen does); every backtick path under "Contents" exists; the README deny list and the two numeric keys equal `user-settings.json`. This continues the repo's own `tests/test_source_rules.py` habit (rules as tests) and the resume point's "neighbour of a previous fix" class (the two copies of the rules are twins).

Cost: two hours. Benefit: the next rule edit cannot leave cloud sessions on an old rule set.

### 3. Lint in CI and a declared Python range

What graphify does: CI matrix on Python 3.10, 3.12, 3.13, 3.14 and three OSes; ruff; bandit and pip-audit as non-blocking steps; pre-commit config.

What we do: `ci.yml` runs pytest, the keyline suite and `json.tool` on Ubuntu and Windows, Python 3.12 only; pyflakes is run by hand before each merge (the resume point records "pyflakes clean" every time). `keyline/README.md:23` says "CI runs 3.12"; no minimum version is declared anywhere, and the hook runs under whatever `python3` the user's machine has.

Proposed: add `python -m pyflakes .` (or ruff with the default rule set) as a CI step, and widen the matrix to 3.10 and 3.13 on Ubuntu only (Windows stays 3.12 to keep CI time). A quick read found no 3.12-only syntax; `os.path.isjunction` is already guarded with `getattr`. State the supported range in the README "Quick start".

Cost: half an hour plus whatever the older interpreter reveals. Benefit: the by-hand step becomes a gate, and a user on 3.10 or 3.11 learns from CI, not from a traceback in a hook.

### 4. A short CONTRIBUTING.md with "What we value", and a PR template that asks for the commands actually run

What graphify does: CONTRIBUTING "What We Value" is 15 invariants (correctness over execution, provenance, determinism, inference kept apart from fact, fail-closed, "a regression test proves the old failure", narrow PRs, document heuristic boundaries, never hand-edit generated artifacts, no ambient environment in tests, treat inputs as untrusted, cross-platform, docs are the contract) plus a "Working with AI coding agents" section. Its PR template has a "Verification & Invariants" checklist and "How was this tested? List the commands actually run."

What we have: the same rules exist, but spread over `research/pr-cleanup-progress.md` (failing-first tests, fix the class, the three recurring classes), `tests/test_source_rules.py`, CLAUDE.md and the README. A new contributor or a fresh session has to find them.

Proposed: `CONTRIBUTING.md` of about 30 lines: failing-first test, fix the class and list other hits, the three recurring classes to check (neighbour of a previous fix, halfway state, absent is not empty), stdlib only, `-I` for anything that reads untrusted files, Windows and Ubuntu both, keyline for notes, "every README number comes from a script in `scripts/` with the command named". A `.github/PULL_REQUEST_TEMPLATE.md` with: what changed, which class it fixes, commands actually run, README/CHANGELOG touched. Add a "Security model" paragraph for the hook to the README or CONTRIBUTING: runs with `-I`, reads only the session transcript, writes only under `~/.claude/ballast/`, never blocks a prompt (`|| exit 0`), timeout 15 s. graphify's SECURITY.md is a longer version of the same idea; ours fits in a paragraph.

Cost: an hour. Benefit: the rules survive the chat; the repo's own CLAUDE.md principle ("keep decisions in files") applied to the contribution rules.

### 5. A measurement ledger so README numbers are reproducible and regressions are caught

What graphify does: `benchmark.py` prints corpus tokens vs average query tokens per question with a reduction ratio; the skill appends cumulative token cost to `graphify-out/cost.json` (runs, total input, total output) on every run; `querylog.py` is an opt-in JSONL log that never raises; "Honesty Rules" in the skill say always show raw numbers.

What we have: the README tables and "Measured numbers" come from `scripts/usage_breakdown.py`, `toolresult_share.py`, `verify-tokens.py` and hand runs recorded in `research/progress-log.md`; the fixed new-session load (71,396 tokens) is one dated observation. A Claude Code update that adds tools or re-expands the skill listing would move it and nothing would notice.

Proposed: `scripts/ledger.py` that appends one JSON line per run (date, Claude Code version, new-session fixed tokens, first-call cache write, number of tools, deny list applied yes/no) to `research/measurements.jsonl`, and prints the delta against the previous line in graphify's before/after style. The README rows then cite a ledger line. Keep it opt-in and manual (the hook stays silent); a JSONL append that never raises is the right shape, as in `querylog.py`.

Cost: half a day. Benefit: the README's main claim stays checkable over time, and the "Biggest costs still left" list gets a trend.

### 6. Candidate to measure before adopting: a PreToolUse nudge that fires only on a re-read of an unchanged file

What graphify does: `_install_claude_hook` writes two PreToolUse entries to `.claude/settings.json` (matcher `Bash|Grep` and `Read|Glob`, command `graphify hook-guard ...`, `timeout: 10` because the Claude Code default is 600 s, their issue #3314), and the guard adds a line of context on every Grep or Read suggesting a graph query first; it fails open and runs in ~170 ms warm.

Why it is only a candidate for us: `research/panel-results.md` lists "Tool-output hygiene and no re-reads (read a file once, then grep)" as a measured, high-confidence idea, and Bash output plus re-reads are 15% of a long session's context. But a hook that speaks on every Read adds tokens to every call, which is the opposite of this repo's goal. The version that fits is a PreToolUse hook on `Read` that stays silent unless the same path was read earlier in this session and its mtime and size are unchanged, and then says one line ("read at turn N, unchanged; grep the part you need"). It needs the same shape as `context_check.py`: `-I`, explicit timeout, exit 0 on any error, transcript-only state.

Cost: a day plus a measured A/B over two sessions with `scripts/toolresult_share.py`. Benefit unknown until measured; put it in "What did not work" if the saving is under the hook's own cost.

### 7. Small: let `add_to_repo.py` write the hand-off threshold as an `env` key

graphify reads a `.graphifyrc` per project (`rcfile.py`). The equivalent for us is already available through Claude Code settings: `add_to_repo.py --handoff-at 120000` could write `env.IDEAL_UMBRELLA_HANDOFF_AT` into `.claude/settings.json` so a repository can set its own threshold without a wrapper script. Twenty lines and one test. Only worth it if someone asks for a per-repo threshold.

## Already equivalent (nothing to take)

- Command-scoped hook recognition: graphify fixed matching by command text (their #4359); `install.py` and `add_to_repo.py` already identify the hook by `context_check.py` in the command and update it in place.
- Explicit hook timeout: graphify learned it from an issue; ours has had `timeout: 15` from the start.
- Fail-open hook: `|| exit 0` and `exit 0` in both of our hook commands.
- Atomic writes, backups, install record, idempotent re-run, `--verify-only`: ours are at least as careful (graphify's `_unsafe_purge_reason` guard before `rmtree` is not needed because `uninstall.py` deletes a fixed path under home, not one taken from the environment).
- Honesty posture: graphify's "Honesty Rules" (never invent, always show raw numbers) match the README's "What did not work" and measured tables.
- Confidence tags EXTRACTED/INFERRED/AMBIGUOUS: the keyline format already separates fact, hedge and number by rule.

## Not a fit

- **graphify itself as a dependency or recommended companion.** Its own `docs/how-it-works.md` shows the saving scales with repo size: 71.5x at 52 files, 5.4x at 4 files, about 1x at 6 files ("six files already fits in a context window"); BENCHMARKS.md reports ERPNext at about 140K tokens per query. Ideal-Umbrella is 17 Python files outside its tests; the fixed cost of the graph, the skill text and the always-on block would exceed what it saves here. It is worth one experiment on a large project, measured with `scripts/toolresult_share.py` before and after, and a line in the README under "What did not work" or "Measured numbers" either way. Its README headline "80% fewer tokens" is a marketing figure for the cloud product, not a measurement we can reuse.
- **Multi-host skill install (Codex, Gemini, Cursor).** Our levers are Claude Code settings keys; the only portable part is the rules text, and an AGENTS.md copy of `config/CLAUDE.md` is optional and low value until someone uses another host.
- **Community machinery**: translations, welcome and PR-management bots, CODEOWNERS, Discord, Docker image, release-graph workflow, MCP server. Overhead without a community to serve.
- **Pre-commit framework**: the repo has no non-stdlib dev tooling; a CI lint step (item 3) covers it.

## Suggested order

1. Items 2 and 3 (drift tests, lint and matrix in CI): small, no behaviour change, catch real classes.
2. Item 4 (CONTRIBUTING, PR template, security paragraph): writing only.
3. Item 1 (marker section): the one behaviour change; failing-first tests, then README.
4. Item 5 (ledger), then item 6 as a measured experiment.

## Resume point (2026-10-26)

- State: comparison written to `research/graphify-comparison.md` on branch `ccr-18e63515-crkba1`; no code changed. graphify clone at `/home/user/graphify-labs/graphify` (commit 92741d1) is scratch, not in the repo.
- Decisions: graphify the tool is not adopted (saving scales with repo size, ~1x at our size, per its own docs); its install, drift-test, CI and documentation habits are the candidates, ranked above.
- Open items: the user asked for the suggestions to be implemented in a new session (brief: `research/graphify-implementation-brief.md`; scope items 1-5 and 7, new branch from main, new PR, Fable 5.1 review loop until clean, then merge). PR #24 stays as the reference and the user closes it at the end. Item 6 and the graphify-on-a-large-project experiment need measurement before any README claim.
