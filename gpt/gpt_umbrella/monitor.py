"""Fail-open local hooks. Persist numeric usage only, never prompts/tool results."""
import hashlib
import json
import sys
from pathlib import Path
from .storage import read_json, write_json
from .usage import normalize

TAIL_BYTES = 4 * 1024 * 1024


def transcript_context(path):
    """Bounded compatibility fallback; absence is unknown, never zero usage."""
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    with p.open("rb") as stream:
        stream.seek(max(0, p.stat().st_size - TAIL_BYTES))
        lines = stream.read(TAIL_BYTES).splitlines()
    latest = None
    for line in reversed(lines):
        try:
            event = json.loads(line)
            if not isinstance(event, dict):
                continue
            payload = event.get("payload") or {}
            if event.get("type") == "compacted" or payload.get("type") == "context_compacted":
                if latest:
                    latest["compaction"] = hashlib.sha256(line).hexdigest()
                return latest  # Never use a measurement from before this boundary.
            if latest is None and event.get("type") == "event_msg" and payload.get("type") == "token_count":
                info = payload.get("info") or {}
                usage = normalize(info.get("last_token_usage"))
                window = info.get("model_context_window")
                if isinstance(window, int) and not isinstance(window, bool) and window > 0:
                    latest = {"tokens": usage["input"] + usage["output"], "window": window, "compaction": None}
        except (ValueError, TypeError, AttributeError, RecursionError):
            continue
    return latest


def handle(event, state_dir, threshold=0.75):
    if not 0 < threshold < 1:
        raise ValueError("threshold must be between zero and one")
    # One prompt-time hook avoids a synchronous process launch on every model request.
    if event.get("hook_event_name") != "UserPromptSubmit":
        return {}
    transcript = event.get("transcript_path")
    if not isinstance(transcript, str) or not transcript:
        return {}
    # Forks share a root session_id; the transcript identifies the actual conversation.
    identity = str(Path(transcript).resolve())
    filename = hashlib.sha256(identity.encode()).hexdigest() + ".json"
    state_path = Path(state_dir) / filename
    try:
        state = read_json(state_path)
        if not isinstance(state, dict):
            state = {}
    except (FileNotFoundError, ValueError):
        state = {}
    current = transcript_context(transcript)
    if not current:
        return {}  # Need a reported window; don't guess a model's capacity.
    ratio = current["tokens"] / current["window"]
    band = int((ratio - threshold) / 0.10 + 1e-9) if ratio >= threshold else -1
    old_band = state.get("band", -1)
    epoch = current.get("compaction")
    if epoch and epoch != state.get("compaction"):
        old_band = -1
        state = {"band": -1, "compaction": epoch}
    if band < 0:
        if old_band != -1:
            state["band"] = -1
            write_json(state_path, state)
        return {}
    if band == old_band:
        return {}
    state["band"] = band
    write_json(state_path, state)
    note = ("GPT Umbrella: context is approximately "
            f"{current['tokens']:,}/{current['window']:,} tokens ({ratio:.0%}). "
            "At the next natural boundary, update a concise task checkpoint: objective, decisions, "
            "changed files, verification and next action. Continue the task. Preserve useful history "
            "and cache reuse; do not restart or compact solely to reduce this number.")
    return {"systemMessage": f"GPT Umbrella: context approximately {ratio:.0%}; checkpoint reminder.",
            "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": note}}


def run(state_dir, threshold=0.75):
    try:
        stream = getattr(sys.stdin, "buffer", sys.stdin)
        raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError("hook event exceeds 1 MiB")
        event = json.loads(raw)
        if not isinstance(event, dict):
            raise ValueError("hook event is not an object")
        result = handle(event, state_dir, threshold)
        if result:
            print(json.dumps(result))
    except Exception as error:
        # Never block the user's task or echo event contents, paths, or error data.
        print(f"GPT Umbrella: monitor unavailable ({type(error).__name__}); continuing.", file=sys.stderr)
    return 0
