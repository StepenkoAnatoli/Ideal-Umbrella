# GPT-specific research — 2026-11-16

Scope: local Codex first; API recommendations are separate and are not silently applied
to Codex or ChatGPT. Findings use official OpenAI documentation opened on this date.

## What changes from Ideal Umbrella

The upstream project reduces repeated context through Claude settings, handoff reminders,
brief notes, and transcript measurements. Its Claude-specific configuration, pricing,
token fields, and measured percentages cannot establish what helps Codex. GPT Umbrella
uses a new implementation and measures available OpenAI usage data.

## 1. Preserve cache reuse while controlling growth

OpenAI's cache matches reusable prompt prefixes. Rewriting earlier messages or compacting
can reduce reuse. Stable instructions and tool definitions should precede changing content.
Cache accounting also differs by model generation: current documentation distinguishes
ordinary input, cached reads, and cache writes with model-dependent lifetimes and rates.

Implemented: correct subset accounting, explicit price inputs, cache-read fraction, and
checkpoints without forced chat restarts. Recommendation: tune compaction only after
measuring overall cost, latency, and task quality. Raw context size alone is insufficient.
[Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching).

## 2. Load tools when they are needed

Supported Responses models can discover deferred tools with `tool_search`. Related tools
can be grouped into namespaces or MCP servers so fewer definitions load initially.
Definitions discovered later are appended, helping retain earlier cacheable content.

Implemented: offline eager-tool checks. For a future API integration, add deferred discovery
with model compatibility checks. In local Codex, use its existing discovery behavior and
inspect measurements before disabling capabilities.
[Tool search](https://developers.openai.com/api/docs/guides/tools-tool-search).

## 3. Prefer supported compaction over ad hoc history rewriting

The Responses API supports server-side compaction and carries forward an opaque compaction
item. Correct chaining matters: preserve compaction items when maintaining an input array,
or pass new input using `previous_response_id` without replaying the entire history.

Implemented: possible history-replay advice. Future addition: an API adapter that preserves
these items and tests task continuity. No automatic transcript rewriting is included.
[Compaction](https://developers.openai.com/api/docs/guides/compaction).

## 4. Keep reasoning and model choices stable unless evidence supports a change

GPT models expose reasoning controls, but lower effort is a quality tradeoff. Current
documentation describes append-only configuration updates for supported GPT-6 API models,
which can preserve the earlier prefix when effort changes.

Implemented: the request audit flags changed reasoning settings for investigation.
Suggested experiment: route clearly bounded work to a cheaper model or lower effort only
after testing acceptance criteria and retries. This is a proposed experiment, not a shipped
router or a promised saving.
[Keep the prefix unchanged](https://developers.openai.com/api/docs/guides/preserved-reasoning).

## 5. Reduce oversized results at their source

OpenAI's latency guidance recommends relevant retrieved context and stable shared inputs.
For coding work, focused searches, small file ranges, and summaries of build failures are
practical ways to limit irrelevant content before it enters history.

Implemented: a configurable tool-output budget, large-result rankings, and short workflow
rules. Next addition: a command wrapper that saves complete logs and returns an error-focused
preview plus a path, validated against logs where a critical line appears in the middle.
[Latency optimization](https://developers.openai.com/api/docs/guides/latency-optimization).

## 6. Measure successful tasks, not just shorter prompts

Implemented: response-level deduplication, explicit legacy limitations, separate reasoning
counts, and descriptive before/after comparisons. Next addition: a repeatable benchmark
harness with fixed repository snapshots, correctness checks, timing, and warm/cold cache
runs. Add confidence intervals only once there are enough independent trials.

Priority: reliable measurement and output targeting first; API deferred discovery second;
model routing after quality evaluation. Do not remove useful tools based only on their
listing size, count characters as tokens, or infer subscription quota savings from API rates.

## Compatibility evidence

Codex exposes skill-catalog and tool-output budgets and lifecycle hooks. Hooks require
explicit trust in Codex. Transcript structure is not guaranteed stable, so unknown formats
must be reported as unsupported rather than counted as zero usage.
[Configuration](https://learn.chatgpt.com/docs/config-file/config-reference) ·
[Hooks](https://learn.chatgpt.com/docs/hooks).
