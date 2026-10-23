import json
import os
import subprocess
import sys

from conftest import ROOT, write_jsonl

HOOK = ROOT / "hooks" / "context_check.py"


def run_hook(tmp_path, event, threshold="150000", step="25000", stdin=None):
    env = os.environ.copy()
    env["IDEAL_UMBRELLA_HANDOFF_AT"] = threshold
    env["IDEAL_UMBRELLA_HANDOFF_STEP"] = step
    env["IDEAL_UMBRELLA_STATE_DIR"] = str(tmp_path / "state")
    env["IDEAL_UMBRELLA_LOG"] = str(tmp_path / "context_check.log")
    payload = stdin if stdin is not None else json.dumps(event)
    return subprocess.run(
        [sys.executable, "-I", str(HOOK)],
        input=payload,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def transcript(tmp_path, usage, extra=None, name="session.jsonl"):
    events = [{
        "type": "assistant",
        "isSidechain": False,
        "message": {"usage": usage, "content": []},
    }]
    if extra:
        events.extend(extra)
    return write_jsonl(tmp_path / name, events)


def event(path, session="session-1"):
    return {"transcript_path": str(path), "session_id": session}


def test_context_tokens_counts_all_output(context_check, tmp_path):
    path = transcript(tmp_path, {
        "input_tokens": 100_000,
        "cache_creation_input_tokens": 50_000,
        "cache_read_input_tokens": 10_000,
        "output_tokens": 60_000,
        "output_tokens_details": {"thinking_tokens": 50_000},
    })
    # Thinking is part of the context window; the old code subtracted it and returned 170k.
    assert context_check.context_tokens(str(path)) == 220_000


def test_context_tokens_uses_compaction_boundary(context_check, tmp_path):
    path = transcript(
        tmp_path,
        {"input_tokens": 500_000},
        extra=[{"subtype": "compact_boundary", "compactMetadata": {"postTokens": 120_000}}],
    )
    assert context_check.context_tokens(str(path)) == 120_000


def test_context_tokens_ignores_sidechains(context_check, tmp_path):
    path = write_jsonl(tmp_path / "chain.jsonl", [
        {"type": "assistant", "isSidechain": False, "message": {"usage": {"input_tokens": 160_000}}},
        {"type": "assistant", "isSidechain": True, "message": {"usage": {"input_tokens": 900_000}}},
    ])
    assert context_check.context_tokens(str(path)) == 160_000


def test_fires_once_per_band_and_resets_below_threshold(tmp_path):
    path = transcript(tmp_path, {"input_tokens": 100_000, "output_tokens": 60_000})
    first = run_hook(tmp_path, event(path))
    assert first.returncode == 0, first.stderr
    payload = json.loads(first.stdout)
    assert "context about 160k tokens" in payload["systemMessage"]
    assert "over 150k" in payload["hookSpecificOutput"]["additionalContext"]

    second = run_hook(tmp_path, event(path))
    assert second.returncode == 0
    assert second.stdout.strip() == ""

    write_jsonl(path, [{
        "type": "assistant",
        "message": {"usage": {"input_tokens": 100_000, "output_tokens": 40_000}},
    }])
    reset = run_hook(tmp_path, event(path))
    assert reset.returncode == 0
    assert reset.stdout.strip() == ""
    assert not (tmp_path / "state" / "session-1").exists()

    write_jsonl(path, [{
        "type": "assistant",
        "message": {"usage": {"input_tokens": 100_000, "output_tokens": 60_000}},
    }])
    again = run_hook(tmp_path, event(path))
    assert again.returncode == 0
    assert again.stdout.strip()


def test_malformed_threshold_warns_and_uses_default(tmp_path):
    path = transcript(tmp_path, {"input_tokens": 160_000})
    result = run_hook(tmp_path, event(path), threshold="150k")
    assert result.returncode == 0
    assert "not an integer; using 150000" in result.stderr
    assert result.stdout.strip()


def test_unexpected_error_is_logged_not_raised(tmp_path):
    result = run_hook(tmp_path, None, stdin="not-json")
    assert result.returncode == 0
    assert "unexpected error" in result.stderr
    log = (tmp_path / "context_check.log").read_text(encoding="utf-8")
    assert "JSONDecodeError" in log
