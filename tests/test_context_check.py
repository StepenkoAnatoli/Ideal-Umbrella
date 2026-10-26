import json
import os
import subprocess
import sys

from conftest import ROOT, write_jsonl

HOOK = ROOT / "hooks" / "context_check.py"


def run_hook(tmp_path, event, threshold="150000", step="25000", stdin=None, baseline=None):
    env = os.environ.copy()
    env["IDEAL_UMBRELLA_HANDOFF_AT"] = threshold
    env["IDEAL_UMBRELLA_HANDOFF_STEP"] = step
    env["IDEAL_UMBRELLA_STATE_DIR"] = str(tmp_path / "state")
    env["IDEAL_UMBRELLA_LOG"] = str(tmp_path / "context_check.log")
    env.pop("IDEAL_UMBRELLA_BASELINE", None)
    if baseline is not None:
        env["IDEAL_UMBRELLA_BASELINE"] = baseline
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


def event(path, session="session-1", name=None):
    data = {"transcript_path": str(path), "session_id": session}
    if name:
        data["hook_event_name"] = name
    return data


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


def test_tail_bytes_bounds_how_far_back_the_hook_reads(context_check, tmp_path, monkeypatch):
    padding = [{"type": "user", "message": {"content": "x" * 1000}} for _ in range(5)]
    path = transcript(tmp_path, {"input_tokens": 200_000}, extra=padding)
    assert context_check.context_tokens(str(path)) == 200_000
    monkeypatch.setenv("IDEAL_UMBRELLA_TAIL_BYTES", "2000")
    assert context_check.context_tokens(str(path)) == 0


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
    assert payload["systemMessage"] == (
        "Ideal-Umbrella: floor 100k, now 160k; over 150k, a fresh session is due at the next "
        "step boundary.")
    assert "over 150k" in payload["hookSpecificOutput"]["additionalContext"]

    # Same band: the savings line alone, nothing for the model.
    second = run_hook(tmp_path, event(path))
    assert second.returncode == 0
    assert json.loads(second.stdout) == {"systemMessage": "Ideal-Umbrella: floor 100k, now 160k"}

    write_jsonl(path, [{
        "type": "assistant",
        "message": {"usage": {"input_tokens": 100_000, "output_tokens": 40_000}},
    }])
    reset = run_hook(tmp_path, event(path))
    assert reset.returncode == 0
    assert json.loads(reset.stdout) == {"systemMessage": "Ideal-Umbrella: floor 100k, now 140k"}
    assert not (tmp_path / "state" / "session-1").exists()

    write_jsonl(path, [{
        "type": "assistant",
        "message": {"usage": {"input_tokens": 100_000, "output_tokens": 60_000}},
    }])
    again = run_hook(tmp_path, event(path))
    assert again.returncode == 0
    assert "additionalContext" in json.loads(again.stdout)["hookSpecificOutput"]


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


def test_stdin_is_read_as_utf8_whatever_the_locale(context_check, tmp_path, monkeypatch, capsys):
    import io
    path = transcript(tmp_path, {"input_tokens": 160_000}, name="sessión.jsonl")
    monkeypatch.setenv("IDEAL_UMBRELLA_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("IDEAL_UMBRELLA_LOG", str(tmp_path / "context_check.log"))
    # A cp1252 text layer over UTF-8 bytes is what a Windows host hands the hook; the hook
    # must read the bytes underneath as UTF-8 or the transcript path never matches.
    raw = io.BytesIO(json.dumps(event(path)).encode("utf-8"))
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(raw, encoding="cp1252"))
    context_check.run()
    assert "now 160k; over 150k" in capsys.readouterr().out


def test_old_state_files_are_pruned(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    old, recent = state / "old-session", state / "recent-session"
    old.write_text("0", encoding="utf-8")
    recent.write_text("0", encoding="utf-8")
    long_ago = 40 * 24 * 3600
    os.utime(old, (os.path.getmtime(old) - long_ago, os.path.getmtime(old) - long_ago))
    path = transcript(tmp_path, {"input_tokens": 160_000})
    result = run_hook(tmp_path, event(path))
    assert result.returncode == 0, result.stderr
    assert not old.exists()
    assert recent.exists()
    assert (state / "session-1").exists()


def test_log_is_trimmed_when_it_grows_past_the_cap(tmp_path):
    log = tmp_path / "context_check.log"
    log.write_text("old line\n" * 150_000, encoding="utf-8")   # about 1.3 MB
    before = log.stat().st_size
    path = transcript(tmp_path, {"input_tokens": 160_000})
    result = run_hook(tmp_path, event(path), threshold="150k")
    assert result.returncode == 0
    assert log.stat().st_size < before
    assert "not an integer" in log.read_text(encoding="utf-8").splitlines()[-1]


def test_compaction_boundary_without_post_tokens_reports_zero(context_check, tmp_path):
    path = transcript(tmp_path, {"input_tokens": 200_000},
                      extra=[{"subtype": "compact_boundary", "compactMetadata": {"preTokens": 200_000}}])
    assert context_check.context_tokens(str(path)) == 0


def test_compaction_above_threshold_starts_the_bands_again(tmp_path):
    # 240k -> reminder (band 3); a compaction landing at 160k is still over the threshold, and
    # the band-3 state used to keep the hook silent until 250k.
    path = transcript(tmp_path, {"input_tokens": 240_000})
    first = run_hook(tmp_path, event(path))
    assert "now 240k; over 150k" in json.loads(first.stdout)["systemMessage"]

    write_jsonl(path, [
        {"subtype": "compact_boundary", "compactMetadata": {"postTokens": 160_000}},
        {"type": "assistant", "message": {"usage": {"input_tokens": 160_000}}},
    ])
    after = run_hook(tmp_path, event(path))
    assert after.returncode == 0, after.stderr
    assert "now 160k; over 150k" in json.loads(after.stdout)["systemMessage"]
    assert "hookSpecificOutput" not in json.loads(run_hook(tmp_path, event(path)).stdout)


def test_state_dir_follows_claude_config_dir(context_check, monkeypatch, tmp_path):
    # Claude Code keeps its files in CLAUDE_CONFIG_DIR when it is set; the hook used ~/.claude.
    # The value is read as install.py reads it (~ expanded, made absolute), so a quoted
    # "~/cfg" does not put the state under a folder named "~" in every project.
    monkeypatch.delenv("IDEAL_UMBRELLA_STATE_DIR", raising=False)
    monkeypatch.delenv("IDEAL_UMBRELLA_LOG", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "~/cfg")
    cfg = os.path.realpath(os.path.join(str(tmp_path), "cfg"))
    assert context_check.state_dir() == os.path.join(cfg, "ballast", "state")
    assert context_check.log_path() == os.path.join(cfg, "ballast", "context_check.log")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "rel")
    monkeypatch.chdir(tmp_path)
    assert context_check.state_dir() == os.path.join(os.path.realpath(str(tmp_path)), "rel", "ballast", "state")
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    assert context_check.state_dir().endswith(os.path.join(".claude", "ballast", "state"))


# --- the savings line -------------------------------------------------------------------

def test_floor_tokens_is_the_first_main_chain_call_input_side(context_check, tmp_path):
    # The floor is what the first call carried in (system prompt, tools, first message); the
    # output of that call is not part of it. Sidechain calls and events without usage are
    # skipped, so a subagent that ran first does not set the floor.
    path = write_jsonl(tmp_path / "chain.jsonl", [
        {"type": "user", "message": {"content": "hello"}},
        {"type": "assistant", "isSidechain": True, "message": {"usage": {"input_tokens": 5_000}}},
        {"type": "assistant", "message": {"usage": {"output_tokens": 10}}},
        {"type": "assistant", "message": {"usage": {
            "input_tokens": 1_000, "cache_creation_input_tokens": 30_000,
            "cache_read_input_tokens": 9_000, "output_tokens": 500}}},
        {"type": "assistant", "message": {"usage": {"input_tokens": 90_000}}},
    ])
    assert context_check.floor_tokens(str(path)) == 40_000
    assert context_check.context_tokens(str(path)) == 90_000


def test_floor_search_is_bounded_by_tail_bytes(context_check, tmp_path, monkeypatch):
    padding = [{"type": "user", "message": {"content": "x" * 1000}} for _ in range(5)]
    path = write_jsonl(tmp_path / "long.jsonl", padding + [
        {"type": "assistant", "message": {"usage": {"input_tokens": 40_000}}}])
    assert context_check.floor_tokens(str(path)) == 40_000
    monkeypatch.setenv("IDEAL_UMBRELLA_TAIL_BYTES", "2000")
    assert context_check.floor_tokens(str(path)) == 0


def test_floor_tokens_skips_lines_that_are_not_json(context_check, tmp_path):
    path = tmp_path / "torn.jsonl"
    path.write_bytes(b'{"type": "assistant", "message": {"usage": {"input_tokens"\n'
                     + json.dumps({"type": "assistant", "message": {"usage": {"input_tokens": 40_000}}}).encode() + b"\n")
    assert context_check.floor_tokens(str(path)) == 40_000


def test_status_line_wording(context_check):
    assert context_check.status_line(40_000, 42_000, 0) == "Ideal-Umbrella: floor 40k, now 42k"
    assert context_check.status_line(40_000, 42_000, 71_000) == (
        "Ideal-Umbrella: floor 40k, now 42k, saved 31k vs baseline")
    assert context_check.status_line(40_000, 42_000, 38_000) == (
        "Ideal-Umbrella: floor 40k, now 42k, 2k over baseline")
    assert context_check.status_line(40_000, 42_000, 40_000) == (
        "Ideal-Umbrella: floor 40k, now 42k, saved 0k vs baseline")
    assert context_check.status_line(0, 42_000, 71_000) == ""
    assert context_check.status_line(40_000, 0, 71_000) == ""


def test_savings_line_on_every_prompt_below_threshold(tmp_path):
    path = transcript(tmp_path, {"input_tokens": 1_000, "cache_creation_input_tokens": 39_000,
                                 "output_tokens": 2_000})
    for _ in range(2):
        result = run_hook(tmp_path, event(path))
        assert result.returncode == 0, result.stderr
        assert result.stderr == ""
        # A systemMessage only: shown to the user, never sent to the model.
        assert json.loads(result.stdout) == {"systemMessage": "Ideal-Umbrella: floor 40k, now 42k"}


def test_savings_line_with_baseline(tmp_path):
    path = transcript(tmp_path, {"input_tokens": 40_000, "output_tokens": 2_000})
    saved = run_hook(tmp_path, event(path), baseline="71000")
    assert json.loads(saved.stdout) == {
        "systemMessage": "Ideal-Umbrella: floor 40k, now 42k, saved 31k vs baseline"}
    over = run_hook(tmp_path, event(path), baseline="38000")
    assert json.loads(over.stdout) == {
        "systemMessage": "Ideal-Umbrella: floor 40k, now 42k, 2k over baseline"}


def test_invalid_baseline_warns_and_shows_no_saving(tmp_path):
    path = transcript(tmp_path, {"input_tokens": 40_000, "output_tokens": 2_000})
    for bad in ("71k", "-5", "0"):
        result = run_hook(tmp_path, event(path), baseline=bad)
        assert result.returncode == 0
        assert "IDEAL_UMBRELLA_BASELINE" in result.stderr and "ignoring it" in result.stderr
        assert json.loads(result.stdout) == {"systemMessage": "Ideal-Umbrella: floor 40k, now 42k"}
    blank = run_hook(tmp_path, event(path), baseline="  ")
    assert blank.stderr == ""
    assert json.loads(blank.stdout) == {"systemMessage": "Ideal-Umbrella: floor 40k, now 42k"}


def test_no_savings_line_before_the_first_call(tmp_path):
    # Claude Code runs the hook on the first prompt, before any model call: nothing to show.
    path = write_jsonl(tmp_path / "fresh.jsonl", [{"type": "user", "message": {"content": "hi"}}])
    result = run_hook(tmp_path, event(path), baseline="71000")
    assert result.returncode == 0, result.stderr
    assert result.stdout == "" and result.stderr == ""


def test_hand_off_note_carries_the_savings_line(tmp_path):
    path = transcript(tmp_path, {"input_tokens": 40_000, "cache_read_input_tokens": 120_000})
    result = run_hook(tmp_path, event(path), baseline="200000")
    payload = json.loads(result.stdout)
    assert payload["systemMessage"] == (
        "Ideal-Umbrella: floor 160k, now 160k, saved 40k vs baseline; over 150k, a fresh session "
        "is due at the next step boundary.")
    note = payload["hookSpecificOutput"]["additionalContext"]
    assert note.startswith("Ideal-Umbrella: this chat's context is about 160k tokens (over 150k).")
    assert "floor" not in note and "baseline" not in note
    assert payload["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"


def test_post_tool_use_gets_no_savings_line(tmp_path):
    # On PostToolUse the line would repeat on every tool call; only the hand-off note is sent.
    low = transcript(tmp_path, {"input_tokens": 40_000, "output_tokens": 2_000}, name="low.jsonl")
    result = run_hook(tmp_path, event(low, name="PostToolUse"))
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    high = transcript(tmp_path, {"input_tokens": 160_000}, name="high.jsonl")
    result = run_hook(tmp_path, event(high, session="s-2", name="PostToolUse"))
    payload = json.loads(result.stdout)
    assert payload["systemMessage"] == (
        "Ideal-Umbrella: context about 160k tokens; a fresh session is due at the next step boundary.")
    assert payload["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert "over 150k" in payload["hookSpecificOutput"]["additionalContext"]


def test_hook_never_blocks_on_an_unreadable_transcript(tmp_path):
    # A transcript folder in place of the file: no stdout, exit 0 (exit 2 would erase the prompt).
    folder = tmp_path / "session.jsonl"
    folder.mkdir()
    result = run_hook(tmp_path, event(folder))
    assert result.returncode == 0 and result.stdout == ""
