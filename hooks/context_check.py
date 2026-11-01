"""Ideal-Umbrella: show what a session costs, and remind Claude to hand a long chat
over to a fresh session.

Hook for UserPromptSubmit (and optionally PostToolUse). It reads the session
transcript, takes the context size of the last main-chain model call and, once
that passes the threshold, adds a short note for Claude. It speaks again only
after the context has grown by another STEP tokens, and resets after compaction.

On every UserPromptSubmit it also prints a savings line as a systemMessage, which
Claude Code shows to the user and never sends to the model (0 tokens):
  Ideal-Umbrella: floor 40k, now 42k
The floor is the context of the session's first main-chain call (input, cache
write and cache read: the system prompt, the tools and the first message), "now"
the context after the last call ("now 20k after compaction" right after one, when it
leaves out the system prompt and tools). With IDEAL_UMBRELLA_BASELINE set to the floor of
an unoptimised session, the line ends in ", saved 31k vs baseline" (or ", 2k over
baseline"). The floor includes the first message, so the comparison holds only after a
short first prompt. The line is left out until the transcript holds a first call, and on
PostToolUse, where it would repeat on every tool call.
Stdlib only; run with `python -I`.

Environment:
  IDEAL_UMBRELLA_HANDOFF_AT    threshold in tokens (default 150000)
  IDEAL_UMBRELLA_HANDOFF_STEP  repeat interval in tokens (default 25000)
  IDEAL_UMBRELLA_BASELINE      floor of an unoptimised session in tokens; unset: no saving shown
  IDEAL_UMBRELLA_STATE_DIR     override the per-session state folder (tests)
  IDEAL_UMBRELLA_LOG           override the error log path
  IDEAL_UMBRELLA_TAIL_BYTES    how much of the transcript end to read (default 4 MB);
                               raise it if a single turn writes more than that; the floor
                               is looked for within 4 times this many bytes of the start
                               (set below the size of the first turn, the line is left out)

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
# What a transcript record can raise when read as numbers: torn or non-JSON lines, values that
# are not numbers, inf (1e400), NaN, and nesting deep enough to exhaust the parser's stack.
BAD_RECORD = (ValueError, TypeError, AttributeError, OverflowError, RecursionError)


def config_dir():
    """Where Claude Code keeps its files: CLAUDE_CONFIG_DIR when set, else ~/.claude.
    config/install.py accepts only an absolute CLAUDE_CONFIG_DIR, which the hook and Claude Code
    read alike. A "~" set by hand is expanded here although Claude Code does not expand it, so
    the hook's runtime state does not land under a folder named "~" in every project."""
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


def logged(prefix):
    """Log the exception being handled; "; details in <log>" when that worked, else the
    error itself (the log's folder may be the very thing that failed)."""
    if log(prefix + traceback.format_exc().strip()):
        return "; details in " + log_path()
    error = sys.exc_info()[1]
    return f" ({type(error).__name__}: {error})"


def log(message):
    """Append one line to the hook log; True when it was written. Logging must never break
    the prompt."""
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
        return True
    except Exception:
        return False


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
    """A positive integer setting, or default; a default of 0 means the setting is off."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    fallback = "ignoring it" if default == 0 else f"using {default}"
    # ASCII digits only, as add_to_repo.py's --handoff-at: int() alone also takes "1_000" and
    # other scripts' digits. Spaces around the number (a value read from a file) are fine.
    digits = raw.strip().lstrip("+-")
    try:
        if not (digits.isascii() and digits.isdigit()):
            raise ValueError(raw)
        value = int(raw)
    except ValueError:
        warn(f"{name}={raw!r} is not an integer; {fallback}")
        return default
    if value == 0 and default == 0:
        return 0   # 0 turns an off-by-default setting off, as leaving it unset does
    if value <= 0:
        warn(f"{name}={raw!r} must be positive; {fallback}")
        return default
    return value


def _usage(event):
    """The usage of a main-chain assistant event, else None."""
    if not isinstance(event, dict) or event.get("isSidechain") or event.get("type") != "assistant":
        return None
    return (event.get("message") or {}).get("usage") or {}


def _count(value):
    """A token count from the transcript: a non-negative int; raises one of BAD_RECORD."""
    return max(0, int(value or 0))


def _prompt_tokens(usage):
    """What the call carried in: input, cache write and cache read."""
    return sum(_count(usage.get(key)) for key in (
        "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"
    ))


def tail_limit():
    return parse_int("IDEAL_UMBRELLA_TAIL_BYTES", TAIL_BYTES)


def context_tokens(path, limit=None):
    """Context size at the last main-chain call, or after the last compaction."""
    return last_measure(path, limit)[0]


def last_measure(path, limit=None):
    """(tokens, compacted): the context size at the last main-chain call, or after the last
    compaction, and whether it came from a compact boundary (then it leaves out the system
    prompt and the tools)."""
    if limit is None:
        limit = tail_limit()
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        f.seek(max(0, size - limit))
        lines = f.read().splitlines()
    for raw in reversed(lines):
        try:
            measure = _measure(json.loads(raw))
        except BAD_RECORD:
            continue   # a torn line, or a record whose usage is not finite numbers
        if measure is not None:
            return measure
    return 0, False


def _measure(event):
    """(tokens, compacted) for one transcript record, or None when it carries no measure."""
    if not isinstance(event, dict) or event.get("isSidechain"):
        return None
    if event.get("subtype") == "compact_boundary":
        # compactMetadata.postTokens is the size of the compacted conversation. It leaves
        # out the system prompt and tool definitions, so it is a floor until the next
        # assistant event reports real usage. Older transcripts carry only preTokens: then
        # report 0, which also clears the band state so the reminder can fire again later.
        # A boundary always ends the scan: an unreadable postTokens is 0, never the usage
        # from before the compaction.
        try:
            return _count((event.get("compactMetadata") or {}).get("postTokens")), True
        except BAD_RECORD:
            return 0, True
    usage = _usage(event)
    if usage is None:
        return None
    n = _prompt_tokens(usage)
    if n:
        # Thinking tokens are part of the context window, so count all output here.
        return n + _count(usage.get("output_tokens")), False
    return None


def floor_tokens(path, limit=None):
    """Context size at the first main-chain call: the session's floor (the system prompt,
    the tools and the first message), read from the start of the transcript. 0 when no such
    call starts within 4 * `limit` bytes (`limit` is TAIL_BYTES) of the start. At most `limit`
    bytes are held at once: a record of `limit` bytes or more (a file pasted into the first
    prompt) is read in `limit`-sized pieces, which do not parse, and the search goes on."""
    if limit is None:
        limit = tail_limit()
    bound = 4 * limit
    with open(path, "rb") as f:
        while f.tell() < bound:
            raw = f.readline(limit)
            if not raw:
                return 0
            try:
                usage = _usage(json.loads(raw))
                n = _prompt_tokens(usage) if usage else 0
            except BAD_RECORD:
                n = 0
            if n:
                return n
    return 0


def status_line(floor, now, baseline, compacted=False):
    """The savings line, or "" while the transcript holds no first call or no context. The
    numbers are shown in whole thousands and the saving is taken from the shown ones, so the
    line adds up. Right after a compaction "now" leaves out the system prompt and the tools,
    so it can be below the floor: the line says where it comes from."""
    if not (floor and now):
        return ""
    floor_k, base_k = floor // 1000, baseline // 1000
    line = f"Ideal-Umbrella: floor {floor_k}k, now {now // 1000}k"
    if compacted:
        line += " after compaction"
    if baseline:
        if base_k >= floor_k:
            line += f", saved {base_k - floor_k}k vs baseline"
        else:
            line += f", {floor_k - base_k}k over baseline"
    return line


def record_handoff(n, threshold, step, session):
    """True when the hand-off note is due: the context is over the threshold and in a band
    this session has not been told about. Keeps the band in the per-session state file;
    below the threshold the state is dropped, so the note can fire again after a compaction."""
    state = os.path.join(state_dir(), session)
    if n < threshold:
        if os.path.exists(state):
            os.remove(state)
        return False
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
        return False
    os.makedirs(state_dir(), exist_ok=True)
    prune_state(state_dir())
    with open(state, "w", encoding="utf-8") as f:
        f.write(str(band))
    return True


def run():
    threshold = parse_int("IDEAL_UMBRELLA_HANDOFF_AT", DEFAULT_THRESHOLD)
    step = parse_int("IDEAL_UMBRELLA_HANDOFF_STEP", DEFAULT_STEP)
    baseline = parse_int("IDEAL_UMBRELLA_BASELINE", 0)
    if 0 < baseline < 1000:
        warn(f"IDEAL_UMBRELLA_BASELINE={baseline} is under 1000 tokens (shown as 0k); ignoring it")
        baseline = 0
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
    limit = tail_limit()
    n, compacted = last_measure(path, limit)
    event = data.get("hook_event_name") or "UserPromptSubmit"
    # The savings line and the hand-off check each run under their own handler: a failure in
    # one is logged and leaves the other standing (the line is cosmetic; the note is not).
    status = ""
    if n and event == "UserPromptSubmit":
        try:
            status = status_line(floor_tokens(path, limit), n, baseline, compacted)
        except Exception:
            log("savings line: " + traceback.format_exc().strip())
    try:
        due = record_handoff(n, threshold, step, session)
    except Exception:
        # Not cosmetic: say so where the user sees it. stderr of a hook that exits 0 shows only
        # in verbose mode, so on UserPromptSubmit the systemMessage carries it too (not on
        # PostToolUse, where it would repeat after every tool call). When the log cannot be
        # written either (the same unwritable folder), the message carries the error itself.
        failed = "the hand-off check failed" + logged("hand-off check: ")
        print("Ideal-Umbrella hook: " + failed, file=sys.stderr)
        if event == "UserPromptSubmit":
            status = f"{status}; {failed}" if status else "Ideal-Umbrella: " + failed
        due = False
    # A hook prints one JSON object, so the savings line and the hand-off note share it.
    if not due:
        if status:
            print(json.dumps({"systemMessage": status}))
        return
    if status:
        message = f"{status}; over {threshold // 1000}k, a fresh session is due at the next step boundary."
    else:
        message = (f"Ideal-Umbrella: context about {n // 1000}k tokens; "
                   "a fresh session is due at the next step boundary.")
    print(
        json.dumps(
            {
                "systemMessage": message,
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
            sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
        run()
    except Exception:
        # Never block the user's prompt. Leave a trace so a broken install is visible.
        print("Ideal-Umbrella hook: unexpected error" + logged(""),
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
