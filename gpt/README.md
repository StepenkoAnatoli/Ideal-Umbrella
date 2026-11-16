# GPT Umbrella — OpenAI Codex edition

Version 0.1.2, integrated into Ideal-Umbrella with a Unicode CLI output fix.
See the [multi-angle review and fixes](docs/review-2026-11-17.md).

Reduce avoidable context overhead in **local Codex**, and measure what actually changes.
Inspired by [Ideal Umbrella](https://github.com/StepenkoAnatoli/Ideal-Umbrella), inspected at
`415f786cf74828c1a039b0e75d0389321bf2eeed`. This is a new Python implementation for OpenAI
usage records and Codex configuration. It does not modify the GPT model or ordinary ChatGPT chats.

This is the **GPT/Codex part of Ideal-Umbrella**. The [repository root](../README.md)
documents the separate Claude Code implementation. Use this directory's commands for Codex;
the root `config/install.py` is the Claude installer.

Python **3.11+**, standard library only. No API key, network request, paid model call, or
third-party dependency is needed. Developed and tested on Windows with Codex CLI 0.156.1.
The [repository CI](../.github/workflows/ci.yml) runs GPT's suite through
`tests/test_gpt_entrypoint.py` on Ubuntu with Python 3.12, 3.13, and 3.14 and Windows
with Python 3.12. The Python 3.10 job skips GPT execution. Check actual CI results;
Python 3.11 is the minimum required by the code but is not currently in the CI matrix.

## What is included

| Component | Behavior |
| --- | --- |
| Usage analyzer | Reads Codex JSONL and saved Responses JSON; deduplicates response IDs; reports input, cache reads/writes, output and reasoning subsets. |
| Waste report | Ranks tool outputs by characters, flags large results, and hashes repeated commands instead of printing them. |
| Context monitor | Reminds the agent to save a checkpoint near 75% of its reported context window, then at additional 10 percentage point bands. |
| Installer | Backs up existing files, preserves existing settings, appends a small instruction section, copies the runtime, and registers hooks. |
| Uninstaller | Restores unchanged files exactly; removes intact owned sections while preserving later user edits. |
| Skill/instruction audit | Ranks source-file sizes without pretending all those files are loaded into context. |
| API request audit | Offline advice about eager tool definitions, changed prefix settings, and possibly replayed conversation history. |
| Before/after comparison | Shows total work, response counts and per-response averages; makes no causal savings claim. |

## Start with measurement

Clone Ideal-Umbrella if needed, then enter the **gpt** directory:

```powershell
git clone https://github.com/StepenkoAnatoli/Ideal-Umbrella.git
cd Ideal-Umbrella/gpt
```

Run these commands from that directory:

```powershell
python -I umbrella.py analyze --latest 10 --output output/before.json
python -I umbrella.py audit /path/to/your/skills --output output/skills.json
python -I umbrella.py install --dry-run
python -I umbrella.py install
python -I umbrella.py verify
```

`analyze` defaults to `$CODEX_HOME/sessions` or `~/.codex/sessions`. It reads **available JSONL
files only**; it does not access the app's database, paginated history, remote sessions, or
automatically add archived sessions. Pass explicit files/directories to include them. Child
agent files are included only when found under the selected directories. `--latest` limits
files, so it can omit child sessions. A report is not necessarily your entire account usage.

After installation, start a new local Codex chat to load configuration and instructions.
Codex must review and trust the installed hooks before they execute: use **Settings > Hooks**
in the desktop app, or `/hooks` in the CLI. `verify` checks installed files, not hook trust
or runtime activation. This project never writes trust approvals or bypasses that review.
See [official hooks documentation](https://learn.chatgpt.com/docs/hooks).

The normal `balanced` preset adds these settings **only when no existing setting/table owns them**:

```toml
tool_output_token_limit = 6000

[skills]
max_context_tokens = 5000
```

These are starting budgets to evaluate, not demonstrated optimal values. Existing
`tool_output_token_limit` is preserved. Any existing `skills` table is preserved in full,
so its budget is not changed. Other configuration layers can override these values.
The [official configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
documents these controls. The installer keeps model choice, reasoning effort, permissions,
tools, connectors, and compaction thresholds as configured.

`--preset observe` installs the monitor and concise workflow rules without adding output or
skill budgets. It is not a completely passive baseline because the rules can affect behavior.
To change presets or update this first version: uninstall, then install again. In-place
upgrades are intentionally not implemented.

## Compare after a matching task

```powershell
python -I umbrella.py analyze PATH/TO/COMPLETED-SESSION.jsonl --output output/after.json
python -I umbrella.py compare output/before.json output/after.json
```

For a meaningful experiment use the same task, repository state, model, reasoning setting,
tool access, and acceptance checks. Compare cold and warm cache runs separately. Record
completion time and correctness alongside tokens. A smaller prompt that causes more retries
can cost more overall. Sessions still being written can produce partial totals and warnings.

## Hooks and continuity

Only `UserPromptSubmit` is installed. It reads at most the last 4 MiB of the transcript to
obtain a reported context window and a recent usage estimate, and detects compaction
boundaries within that tail. It uses the transcript path to separate forks that share a
root session ID. There is no process launch or state write on each model request.
Below the reminder threshold the
monitor emits no extra context. It never starts a fresh chat, requests another model call,
or blocks a task. All hook errors exit successfully and print a short diagnostic.

The estimate is from the last model request; new prompt text and tool results can make the
next request larger. Transcripts are an unstable compatibility interface. If a usable
window/record is absent, the reminder stays quiet rather than guessing a model's capacity.
State is one small reminder-band/compaction fingerprint file per transcript under
`~/.codex/gpt-umbrella/state/`, retained until you delete it. Old v0.1.0 numeric state is
ignored. There is no automatic retention cleanup.

Workflow rules ask the agent to maintain a concise checkpoint after meaningful work, use
focused searches, read detailed references on demand, and investigate repeated failures.
They are instructions, not an enforcement mechanism. See [checkpoint template](templates/checkpoint.md).

## Optional API tools

```powershell
python -I umbrella.py analyze saved-response.json --rates my-model-rates.json
python -I umbrella.py audit-requests request-1.json request-2.json
```

Rates are supplied per million tokens and keyed by the exact model ID:

```json
{
  "your-model-id": {
    "input": 1,
    "cached_input": 0.1,
    "output": 5,
    "cache_write": 1.25,
    "cache_write_30m": 1.25,
    "cache_write_12h": 2.5
  }
}
```

**Those are illustrative rates, not a price quote.** Supply the correct model, service tier,
and applicable pricing. If the write lifetime is unknown, `cache_write` must be supplied;
the analyzer will not assume a TTL. Cache reads/writes are subsets of input, and reasoning
is already included in output. Missing required rates produce an unavailable estimate.
API estimates do not predict subscription quotas or charges.

The request audit changes no requests and makes no API calls. It is advisory; model
compatibility and actual cache diagnostics must be checked before acting on a suggestion.

## Undo and recovery

```powershell
python -I umbrella.py uninstall --dry-run
python -I umbrella.py uninstall
```

`--home ABSOLUTE_PATH` selects a Codex configuration directory for install, verify,
uninstall, hook, or default analysis. The installer refuses linked target paths, malformed
configuration, and untracked runtime files. It journals backups before applying changes,
rolls back ordinary write failures, and leaves a pending record after abrupt interruption;
run uninstall to recover that pending transaction before reinstalling.

Mutating commands use an exclusive `gpt-umbrella/mutation.lock`. After an abrupt process
crash, inspect the recorded process ID and confirm no installer is running before removing
a stale lock. Recorded file and backup paths are restricted to the installer's owned
namespace. Detected external edits during installation/undo cause a stop; rollback does
not overwrite an externally edited file. This is not a filesystem-wide lock on editors.

Edited managed sections are left intact with a notice. If hook entries changed, the runtime
is retained for inspection so an edited hook is not left pointing at deleted code. Backups
and numeric monitor state remain after uninstall. Keep the source checkout for maintenance.

## Validation

```powershell
python -m unittest discover -s tests -v
python -m compileall -q umbrella.py gpt_umbrella
```

Tests cover accounting, response deduplication, legacy fallback, privacy of reports,
malformed input, reminders and compaction, installer rollback, user-edit preservation,
isolated execution, and both PowerShell and cmd.exe hosts on Windows.

See [GPT-specific research](docs/gpt-research.md), [validation notes](docs/validation.md),
and [attribution](NOTICE.md). No percentage savings is claimed without matched measurements.
