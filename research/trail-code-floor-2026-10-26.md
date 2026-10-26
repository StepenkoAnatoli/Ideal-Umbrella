# Trail-Code (formerly Graft) in this repo: what it adds to a fresh session

Measured 2026-10-26 in a single-repo cloud session (container, Claude Code CLI 2.1.310, headless `claude -p`, model claude-sonnet-5-5). Trail-Code 0.25.0 from npm (`@trailhq/trail-code`), installed with `trail init --agents claude -y` and `DO_NOT_TRACK=1`, then removed with `trail uninstall -y`.

## Result

| State | First-call context (input + cache write + cache read) | Runs |
|---|---|---|
| Trail off (control, before and after) | **40,053** | 40,053 / 40,053 / 40,053 / 40,053 / 40,178 / 40,053 |
| Trail on, everything it installs | **41,927 to 42,138** | 42,138 / 41,998 / 41,927 / 41,970 / 42,052 / 41,927 |
| Trail on, its skill removed | 41,940 | 41,940 / 41,940 |
| Trail on, its hooks on but SessionStart off | 40,053 | 40,053 / 40,053 |
| Trail on, all its hooks off | 40,053 | 40,053 / 40,053 |

**Trail raises the floor by about 1,900 tokens (+4.7%) per fresh session in this headless setup.** All of it comes from its SessionStart hook, which injects 5,481 characters of instructions plus the repo map header (saved in the session scratchpad as `trail-session-start-context.txt`). The skill it adds (`~/.claude/skills/trail/SKILL.md`, 17,898 characters) costs nothing measurable at the first call: only its description enters the capped skills listing, and the listing was already at budget. Its six other hooks (PreToolUse Bash, PostToolUse on Write/Edit and on Bash/Read/Grep/Glob/Skill, PostToolUseFailure, Stop, SessionEnd) add nothing at session start; they cost latency on every tool call and inject text only when `trail` commands are used.

On the desktop app, where the README's floor is 71,396 tokens, the same +1,900 would be +2.6%.

## Per-prompt injection

Trail's UserPromptSubmit hook ("context on tap") injected nothing for the two prompts tried: "Reply with the single word ok." and a question naming `config/install.py` and `autoCompactWindow`. The model answered the second one from the repo map header alone and said it could not tell which function decides, because the map lists only `graft/` cards, not the file. The per-prompt cost of Trail is therefore 0 until the agent runs `trail ask`, `trail grep`, `trail skeleton` or `trail callers`; those outputs are capped by Trail and carry a "[trail] tokens saved ≈ N" line.

## Behaviour changes seen

- In the first run after install, the one-word answer came back as "ok" plus a Trail line: "🌱 Stepenkoanatoli and Anatoli work in this repo. Commit .trail/ and .claude/settings.json once, and their Claude starts from your learnings, even before they install trail". The injected context tells the model to close replies with Trail tallies and notes, so output grows too.
- `trail init` read this session's own transcript ("looked back at 1 Claude Code sessions about this repo") to mine repeated instructions. Local only, nothing left to keep.
- Its PreToolUse Bash hook blocks running Trail's own hook scripts by hand ("Trail's hook scripts run only from the host's hooks, never by hand"), so hook output has to be read from a `--output-format stream-json --verbose` run.
- `trail init` writes outside the repo even with `--no-global`: `~/.claude/settings.json` (seven hooks), `~/.claude/helpers/graft-hooks.cjs` and `~/.claude/skills/trail/SKILL.md`. In the repo: `.claude/settings.json` (a SessionStart hook merged next to ours), `.claude/settings.local.json` (statusline, allowlist, `footerLinksRegexes`), `.trail/` (hook and statusline shims, graph cache, learnings). `trail uninstall -y` removed all of it except `.trail/README.md`, `.trail/SKILL.md`, `.trail/settings.json` and `.trail/learnings/`, which were deleted by hand.
- The graph build itself: 35 Python files, 381 nodes, 834 edges, 1.8 s, no model call.

## What was not measured

- The exploration savings Trail claims (46% fewer tool calls, 42% fewer uncached input tokens on its benchmark). Measuring that needs a set of real tasks run twice; the floor was the question here.
- The desktop app floor with Trail: the app adds its own tools and could not be run from the container.

## Caveat on the first run

The very first `claude -p` in this container, before Trail was installed, reported 35,297 tokens (2 input, 9,839 cache write, 25,456 cache read). Every later run in the same Trail-free state reported 40,053. Removing all Trail pieces, stripping the cached feature flags from `~/.claude.json`, and the plugin sync times were checked and none explains the 4,756-token difference. The control used for the comparison is the repeated 40,053, measured back to back with the Trail-on runs; the first-run number is recorded here and not used.

## How to reproduce

```bash
npm install -g @trailhq/trail-code
export DO_NOT_TRACK=1
# control
claude -p "Reply with the single word ok." --output-format json --model claude-sonnet-5-5   # sum usage.input_tokens + cache_creation_input_tokens + cache_read_input_tokens
trail init --agents claude -y
claude -p "Reply with the single word ok." --output-format json --model claude-sonnet-5-5
claude -p "Reply with the single word ok." --output-format stream-json --verbose --model claude-sonnet-5-5   # hook_response events show what each hook injected
trail uninstall -y
```

## Resume point (replace, don't append)

State: measurement done, Trail removed from the container, nothing of Trail committed. PR #21 (branch `ccr-39f8db68-eukrxv`) carries this file and is ready for review, CI green. Decision: Trail is not added to the repo; its floor cost is small (+1,900 tokens) but its purpose (code map, learnings) is orthogonal to this repo's, and the repo is 35 small Python files where `grep` already lands in one call. Decision (2026-10-26, user): take two of Trail's ideas, nothing else. A side session was opened for them; it waits for the user's go.

### Next task: the two ideas (brief for the side session)

1. Learnings template. Trail keeps what the code can't tell the next session under three headings: `Decided`, `Tried and ruled out`, `Watch out`. Add that to this repo in Keyline style (one `key: item; item` line per entry, see `keyline/CLAUDE-snippet.md`): a template file in `config/` and a copy at `notes/learnings.md` for this repo; `config/add_to_repo.py` copies the template into a target repo when `notes/learnings.md` is absent (and `config/uninstall.py` leaves it alone, it is the user's data); one sentence in `keyline/CLAUDE-snippet.md` and `config/CLAUDE.md` saying when to save a learning (a bug's cause after failed attempts, an approach dropped and why, a choice and why, the user correcting how something is done here) and under which heading. `keyline/keyline_hook.py` already lints files under `notes/`, so the template must pass `keyline_lint.py`. Tests in `tests/`.
2. Savings line. `hooks/context_check.py` already reads the context size at the last main-chain call. On every UserPromptSubmit also compute the session floor (the first main-chain assistant usage in the transcript) and print a `systemMessage` only (shown to the user, never sent to the model, so it costs 0 tokens; no `additionalContext` for this): `Ideal-Umbrella: floor 40k, now 42k` and, when `IDEAL_UMBRELLA_BASELINE` is set to the unoptimised floor in tokens, `, saved Nk vs baseline`. Keep the existing hand-off note unchanged. The hook must stay stdlib-only, `-I` safe, never block the prompt; extend `tests/test_context_check.py`. Document the variable in the hook docstring and in `README.md`.
3. Checks before each push: `python -m pytest -q`, `python -I keyline/tests/run_tests.py`, `python -m json.tool` on the three settings files (what `.github/workflows/ci.yml` runs). Draft PR, subscribe to it.
4. Review loop, after the push: deploy review agents (`first-pass:breaker` on the diff, plus the `code-review` skill); fix every real finding, re-run the checks, push; then run the reviews again on the new head. Repeat until a full round finds nothing to fix. Log each round (findings, fixed or why not) in a `research/review-findings-<date>.md` file. Only then report done.
5. Report: at most 5 lines plus the path of the findings file, and replace this resume point with the new state.
