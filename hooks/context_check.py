"""Ballast: remind Claude to hand a long chat over to a fresh session.

Hook for UserPromptSubmit (and optionally PostToolUse). It reads the session
transcript, takes the context size of the last main-chain model call and, once
that passes the threshold, adds a short note for Claude. It speaks again only
after the context has grown by another STEP tokens, and resets after compaction.
Stdlib only; run with `python -I`.
"""
import json
import os
import sys

THRESHOLD = int(os.environ.get("BALLAST_HANDOFF_AT", "150000"))
STEP = int(os.environ.get("BALLAST_HANDOFF_STEP", "25000"))
STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "ballast", "state")
TAIL_BYTES = 4 * 1024 * 1024

NOTE = (
    "Ballast: this chat's context is about {k}k tokens (over {t}k). At the next "
    "step boundary, not mid-step: write a resume point (state, decisions and why, "
    "open items, file paths) to the task's progress file, then offer a fresh "
    "session whose brief points to that file. If the user already chose to stay "
    "here, mention it in one line only."
)


def context_tokens(path):
    """Context size at the last main-chain call, or after the last compaction."""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        f.seek(max(0, size - TAIL_BYTES))
        lines = f.read().splitlines()
    for raw in reversed(lines):
        try:
            e = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(e, dict) or e.get("isSidechain"):
            continue
        if e.get("subtype") == "compact_boundary":
            return (e.get("compactMetadata") or {}).get("postTokens", 0)
        if e.get("type") != "assistant":
            continue
        u = (e.get("message") or {}).get("usage") or {}
        n = (u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
             + u.get("cache_read_input_tokens", 0))
        if n:
            thinking = (u.get("output_tokens_details") or {}).get("thinking_tokens", 0)
            return n + max(0, u.get("output_tokens", 0) - thinking)
    return 0


def main():
    try:
        data = json.load(sys.stdin)
        path = data.get("transcript_path") or ""
        session = "".join(c for c in str(data.get("session_id", "")) if c.isalnum() or c == "-")
        if not (path and session and os.path.isfile(path)):
            return
        n = context_tokens(path)
        state = os.path.join(STATE_DIR, session)
        if n < THRESHOLD:
            if os.path.exists(state):
                os.remove(state)
            return
        band = (n - THRESHOLD) // STEP
        try:
            with open(state, encoding="utf-8") as f:
                last = int(f.read().strip())
        except (OSError, ValueError):
            last = -1
        if band <= last:
            return
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(state, "w", encoding="utf-8") as f:
            f.write(str(band))
        event = data.get("hook_event_name") or "UserPromptSubmit"
        print(json.dumps({
            "systemMessage": f"Ballast: context about {n // 1000}k tokens; "
                             "a fresh session is due at the next step boundary.",
            "hookSpecificOutput": {
                "hookEventName": event,
                "additionalContext": NOTE.format(k=n // 1000, t=THRESHOLD // 1000),
            },
        }))
    except Exception:
        return  # never block the user's prompt


if __name__ == "__main__":
    main()
