# GPT Umbrella reference

[Back to the beginner guide](../README.md). Run commands from the repository's `gpt/` directory.

## Skill and instruction inventory

```powershell
python -I umbrella.py audit /path/to/your/skills --output output/skills.json
```

This ranks instruction and skill source files by characters. It does not measure which
files were loaded into a particular chat. Replace the example path with a real directory.

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
They are instructions, not an enforcement mechanism. See [checkpoint template](../templates/checkpoint.md).

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

See [GPT-specific research](gpt-research.md), [validation notes](validation.md),
and [attribution](../NOTICE.md). No percentage savings is claimed without matched measurements.
