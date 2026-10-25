"""Ideal-Umbrella: remind Claude to hand a long chat over to a fresh session.

Hook for UserPromptSubmit (and optionally PostToolUse). It reads the session
transcript, takes the context size of the last main-chain model call and, once
that passes the threshold, adds a short note for Claude. It speaks again only
after the context has grown by another STEP tokens, and resets after compaction.
Stdlib only; run with `python -I`.

Environment:
  IDEAL_UMBRELLA_HANDOFF_AT    threshold in tokens (default 150000)
  IDEAL_UMBRELLA_HANDOFF_STEP  repeat interval in tokens (default 25000)
  IDEAL_UMBRELLA_STATE_DIR     override the per-session state folder (tests)
  IDEAL_UMBRELLA_LOG           override the error log path
  IDEAL_UMBRELLA_TAIL_BYTES    how much of the transcript end to read (default 4 MB);
                               raise it if a single turn writes more than that

Invalid integer settings fall back to the defaults with a warning; they never
crash the hook before it can read the prompt event.
"""
import datetime
import io
import json
import os
import sys
import time
import traceback

DEFAULT_THRESHOLD = 150000
DEFAULT_STEP = 25000
TAIL_BYTES = 4 * 1024 * 1024
STATE_MAX_AGE = 30 * 24 * 3600   # state files of sessions older than this are removed
LOG_MAX_BYTES = 1024 * 1024      # the log keeps about its last half when it passes this


def config_dir():
    """Where Claude Code keeps its files: CLAUDE_CONFIG_DIR when set, else ~/.claude. The
    variable is read as config/install.py reads it (~ expanded, made absolute), so the hook
    and the installer agree on the folder."""
    value = os.environ.get("CLAUDE_CONFIG_DIR")
    if value:
        return os.path.realpath(os.path.expanduser(value))
    return os.path.join(os.path.expanduser("~"), ".claude")


def state_dir():
    return os.environ.get("IDEAL_UMBRELLA_STATE_DIR") or os.path.join(config_dir(), "ballast", "state")


def log_path():
    return os.environ.get("IDEAL_UMBRELLA_LOG") or os.path.join(
        os.path.dirname(state_dir()), "context_check.log"
    )


NOTE = (
    "Ideal-Umbrella: this chat's context is about {k}k tokens (over {t}k). At the next "
    "step boundary, not mid-step: write a resume point (state, decisions and why, "
    "open items, file paths) to the task's progress file, then offer a fresh "
    "session whose brief points to that file. If the user already chose to stay "
    "here, mention it in one line only."
)


def log(message):
    """Append one line to the hook log. Logging must never break the prompt."""
    try:
        path = log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        stamp = datetime.datetime.now().isoformat(timespec="seconds")
        if os.path.exists(path) and os.path.getsize(path) > LOG_MAX_BYTES:
            with open(path, "rb") as f:
                f.seek(-LOG_MAX_BYTES // 2, os.SEEK_END)
                tail = f.read().split(b"\n", 1)[-1]
            with open(path, "wb") as f:
                f.write(tail)
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{stamp} {message}\n")
    except Exception:
        pass


def prune_state(folder):
    """Drop state files of sessions not seen for STATE_MAX_AGE, so the folder stays small."""
    try:
        cutoff = time.time() - STATE_MAX_AGE
        with os.scandir(folder) as entries:
            for entry in entries:
                if entry.is_file() and entry.stat().st_mtime < cutoff:
                    os.remove(entry.path)
    except OSError:
        pass


def warn(message):
    print(f"Ideal-Umbrella hook: {message}", file=sys.stderr)
    log(message)


def parse_int(name, default):
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        warn(f"{name}={raw!r} is not an integer; using {default}")
        return default
    if value <= 0:
        warn(f"{name}={raw!r} must be positive; using {default}")
        return default
    return value


def context_tokens(path):
    """Context size at the last main-chain call, or after the last compaction."""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        f.seek(max(0, size - parse_int("IDEAL_UMBRELLA_TAIL_BYTES", TAIL_BYTES)))
        lines = f.read().splitlines()
    for raw in reversed(lines):
        try:
            event = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(event, dict) or event.get("isSidechain"):
            continue
        if event.get("subtype") == "compact_boundary":
            # compactMetadata.postTokens is the size of the compacted conversation. It leaves
            # out the system prompt and tool definitions, so it is a floor until the next
            # assistant event reports real usage. Older transcripts carry only preTokens: then
            # report 0, which also clears the band state so the reminder can fire again later.
            return (event.get("compactMetadata") or {}).get("postTokens") or 0
        if event.get("type") != "assistant":
            continue
        usage = (event.get("message") or {}).get("usage") or {}
        n = sum(int(usage.get(key) or 0) for key in (
            "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"
        ))
        if n:
            # Thinking tokens are part of the context window, so count all output here.
            return n + max(0, int(usage.get("output_tokens") or 0))
    return 0


def run():
    threshold = parse_int("IDEAL_UMBRELLA_HANDOFF_AT", DEFAULT_THRESHOLD)
    step = parse_int("IDEAL_UMBRELLA_HANDOFF_STEP", DEFAULT_STEP)
    # Claude Code sends UTF-8; the locale codec (cp1252 on many Windows hosts) would choke on
    # a non-ASCII transcript path, so read the bytes and decode them as UTF-8 ourselves.
    stdin = getattr(sys.stdin, "buffer", None)
    data = json.load(io.TextIOWrapper(stdin, encoding="utf-8") if stdin is not None else sys.stdin)
    if not isinstance(data, dict):
        return
    path = data.get("transcript_path") or ""
    session = "".join(c for c in str(data.get("session_id", "")) if c.isalnum() or c == "-")
    if not (path and session and os.path.isfile(path)):
        return
    n = context_tokens(path)
    state = os.path.join(state_dir(), session)
    if n < threshold:
        if os.path.exists(state):
            os.remove(state)
        return
    band = (n - threshold) // step
    try:
        with open(state, encoding="utf-8") as f:
            last = int(f.read().strip())
    except (OSError, ValueError):
        last = -1
    # Same band as the last reminder: stay silent. A lower band means the context shrank
    # (a compaction that still landed above the threshold): the old reminder is stale, so
    # start again from this band.
    if band == last:
        return
    os.makedirs(state_dir(), exist_ok=True)
    prune_state(state_dir())
    with open(state, "w", encoding="utf-8") as f:
        f.write(str(band))
    event = data.get("hook_event_name") or "UserPromptSubmit"
    print(
        json.dumps(
            {
                "systemMessage": f"Ideal-Umbrella: context about {n // 1000}k tokens; "
                "a fresh session is due at the next step boundary.",
                "hookSpecificOutput": {
                    "hookEventName": event,
                    "additionalContext": NOTE.format(k=n // 1000, t=threshold // 1000),
                },
            }
        )
    )


def main():
    try:
        # The JSON printed is ASCII, but keep the rule every script follows: UTF-8 output.
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        run()
    except Exception:
        # Never block the user's prompt. Leave a trace so a broken install is visible.
        log(traceback.format_exc().strip())
        print(
            "Ideal-Umbrella hook: unexpected error; details in " + log_path(),
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
