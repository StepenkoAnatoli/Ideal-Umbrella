import io
import json
import os
import subprocess
import sys

from conftest import ROOT, clean_env, write_jsonl

HOOK = ROOT / "hooks" / "context_check.py"


def run_hook(tmp_path, event, threshold="150000", step="25000", stdin=None, baseline=None,
             tail_bytes=None):
    env = clean_env()
    env["IDEAL_UMBRELLA_HANDOFF_AT"] = threshold
    env["IDEAL_UMBRELLA_HANDOFF_STEP"] = step
    env["IDEAL_UMBRELLA_STATE_DIR"] = str(tmp_path / "state")
    env["IDEAL_UMBRELLA_LOG"] = str(tmp_path / "context_check.log")
    if baseline is not None:
        env["IDEAL_UMBRELLA_BASELINE"] = baseline
    if tail_bytes is not None:
        env["IDEAL_UMBRELLA_TAIL_BYTES"] = tail_bytes
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
    monkeypatch.setenv("IDEAL_UMBRELLA_TAIL_BYTES", "1000")   # the call starts past 4 * 1000
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
    for bad in ("71k", "-5"):
        result = run_hook(tmp_path, event(path), baseline=bad)
        assert result.returncode == 0
        assert "IDEAL_UMBRELLA_BASELINE" in result.stderr and "ignoring it" in result.stderr
        assert json.loads(result.stdout) == {"systemMessage": "Ideal-Umbrella: floor 40k, now 42k"}
    for off in ("  ", "0"):   # 0 turns the comparison off without a warning on every prompt
        quiet = run_hook(tmp_path, event(path), baseline=off)
        assert quiet.stderr == ""
        assert json.loads(quiet.stdout) == {"systemMessage": "Ideal-Umbrella: floor 40k, now 42k"}


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


def test_saving_is_taken_from_the_shown_thousands(context_check):
    # 40,999 shows as 40k; 71,000 - 40,999 floored is 30k, and the line read "40k ... saved 30k".
    assert context_check.status_line(40_999, 42_000, 71_000) == (
        "Ideal-Umbrella: floor 40k, now 42k, saved 31k vs baseline")
    assert context_check.status_line(40_999, 42_000, 38_500) == (
        "Ideal-Umbrella: floor 40k, now 42k, 2k over baseline")


def test_now_after_a_compaction_says_so(tmp_path):
    # postTokens leaves out the system prompt and the tools, so "now" can be below the floor.
    path = transcript(tmp_path, {"input_tokens": 40_000}, extra=[
        {"type": "system", "subtype": "compact_boundary", "compactMetadata": {"postTokens": 20_000}}])
    result = run_hook(tmp_path, event(path))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "systemMessage": "Ideal-Umbrella: floor 40k, now 20k after compaction"}


def test_oversize_first_record_is_skipped_and_the_search_goes_on(context_check, tmp_path, monkeypatch):
    # A file pasted into the first prompt: the record is longer than the limit. It used to end
    # the search (no line all session) and was read whole into memory first.
    monkeypatch.setenv("IDEAL_UMBRELLA_TAIL_BYTES", "4096")
    path = tmp_path / "pasted.jsonl"
    big = json.dumps({"type": "user", "message": {"content": "x" * 10_000}}).encode()
    call = json.dumps({"type": "assistant", "message": {"usage": {"input_tokens": 40_000}}}).encode()
    path.write_bytes(big + b"\n" + call + b"\n")
    reads = []
    real_open = open

    class Spy:
        def __init__(self, f):
            self.f = f

        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.f.close()

        def tell(self):
            return self.f.tell()

        def readline(self, size=-1):
            line = self.f.readline(size)
            reads.append(len(line))
            return line

    monkeypatch.setattr(context_check, "open", lambda *a, **k: Spy(real_open(*a, **k)), raising=False)
    assert context_check.floor_tokens(str(path)) == 40_000
    assert max(reads) <= 4096

    # The skip loop checks the bound per chunk: one record of 10 * limit bytes is not read
    # to its end (a 1 GiB record took seconds without that check).
    monkeypatch.setenv("IDEAL_UMBRELLA_TAIL_BYTES", "1000")
    huge = tmp_path / "huge.jsonl"
    huge.write_bytes(b'{"x": "' + b"x" * 10_000 + b'"}\n' + call + b"\n")
    reads.clear()
    assert context_check.floor_tokens(str(huge)) == 0
    assert sum(reads) < 5 * 1000


def test_bad_usage_in_the_first_call_does_not_take_the_note_down(tmp_path):
    # A non-integer usage value raised out of run(): no JSON at all, the hand-off note lost.
    path = write_jsonl(tmp_path / "odd.jsonl", [
        {"type": "assistant", "message": {"usage": ["not", "a", "dict"]}},
        {"type": "assistant", "message": {"usage": {"input_tokens": "n/a"}}},
        {"type": "assistant", "message": {"usage": {"input_tokens": 160_000}}},
    ])
    result = run_hook(tmp_path, event(path))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["systemMessage"].startswith("Ideal-Umbrella: floor 160k, now 160k; over 150k")
    assert "over 150k" in payload["hookSpecificOutput"]["additionalContext"]


def test_a_failing_hand_off_check_keeps_the_savings_line(tmp_path):
    # The state folder cannot be created (a file in its place): the line used to be lost too.
    path = transcript(tmp_path, {"input_tokens": 160_000})
    (tmp_path / "state").write_text("in the way", encoding="utf-8")
    result = run_hook(tmp_path, event(path))
    assert result.returncode == 0
    message = json.loads(result.stdout)["systemMessage"]
    # stderr of a hook that exits 0 shows only in verbose mode: the line says it too.
    assert message.startswith("Ideal-Umbrella: floor 160k, now 160k; the hand-off check failed")
    assert "hand-off check" in (tmp_path / "context_check.log").read_text(encoding="utf-8")
    assert "the hand-off check failed" in result.stderr   # not cosmetic: not only in the log


def test_invalid_tail_bytes_warns_once(tmp_path):
    path = transcript(tmp_path, {"input_tokens": 40_000})
    env_result = run_hook(tmp_path, event(path), tail_bytes="abc")
    assert env_result.stderr.count("IDEAL_UMBRELLA_TAIL_BYTES") == 1, env_result.stderr
    assert json.loads(env_result.stdout) == {"systemMessage": "Ideal-Umbrella: floor 40k, now 40k"}


def test_bad_usage_in_the_last_call_falls_back_to_the_one_before(tmp_path):
    # The round-1 test put the bad records first; the reverse scan never reached them, and a
    # bad value in the newest record still took the note and the line down.
    path = write_jsonl(tmp_path / "odd-last.jsonl", [
        {"type": "assistant", "message": {"usage": {"input_tokens": 160_000}}},
        {"type": "assistant", "message": {"usage": {"input_tokens": 170_000, "output_tokens": "n/a"}}},
        {"type": "assistant", "message": {"usage": {"input_tokens": 1e400}}},
    ])
    result = run_hook(tmp_path, event(path))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["systemMessage"].startswith("Ideal-Umbrella: floor 160k, now 160k; over 150k")


def test_infinite_usage_is_skipped(context_check, tmp_path):
    # 1e400 parses as inf, and int(inf) raised OverflowError past the handler: the note was lost.
    path = tmp_path / "inf.jsonl"
    path.write_bytes(
        b'{"type": "assistant", "message": {"usage": {"input_tokens": 1e400}}}\n'
        b'{"type": "assistant", "message": {"usage": {"input_tokens": 160000}}}\n'
        b'{"type": "assistant", "message": {"usage": {"input_tokens": Infinity}}}\n')
    assert context_check.last_measure(str(path)) == (160_000, False)
    assert context_check.floor_tokens(str(path)) == 160_000


def test_a_bad_compact_boundary_still_ends_the_scan(context_check, tmp_path):
    # An unreadable postTokens used to be skipped, and the scan read the usage from before the
    # compaction: "now 200k" and a false hand-off note.
    path = write_jsonl(tmp_path / "bad-boundary.jsonl", [
        {"type": "assistant", "message": {"usage": {"input_tokens": 200_000}}},
        {"type": "system", "subtype": "compact_boundary", "compactMetadata": {"postTokens": "x"}},
    ])
    assert context_check.last_measure(str(path)) == (0, True)
    result = run_hook(tmp_path, event(path))
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_negative_usage_counts_as_zero(context_check, tmp_path):
    path = write_jsonl(tmp_path / "negative.jsonl", [
        {"type": "assistant", "message": {"usage": {"input_tokens": -50_000, "cache_read_input_tokens": 40_000}}},
    ])
    assert context_check.floor_tokens(str(path)) == 40_000


def test_floor_search_reads_at_most_four_times_the_limit(context_check, tmp_path, monkeypatch):
    # Oversize records were skipped without counting: a huge first prompt was read to its end.
    monkeypatch.setenv("IDEAL_UMBRELLA_TAIL_BYTES", "1000")
    big = json.dumps({"type": "user", "message": {"content": "x" * 3000}}).encode()
    call = json.dumps({"type": "assistant", "message": {"usage": {"input_tokens": 40_000}}}).encode()
    near = tmp_path / "near.jsonl"
    near.write_bytes(big + b"\n" + call + b"\n")          # the call starts within 4 * limit
    assert context_check.floor_tokens(str(near)) == 40_000
    far = tmp_path / "far.jsonl"
    far.write_bytes(big + b"\n" + big + b"\n" + call + b"\n")   # it starts past 4 * limit
    assert context_check.floor_tokens(str(far)) == 0


def test_baseline_under_a_thousand_is_ignored_with_a_warning(tmp_path):
    path = transcript(tmp_path, {"input_tokens": 40_000, "output_tokens": 2_000})
    result = run_hook(tmp_path, event(path), baseline="710")
    assert "IDEAL_UMBRELLA_BASELINE=710" in result.stderr and "ignoring it" in result.stderr
    assert json.loads(result.stdout) == {"systemMessage": "Ideal-Umbrella: floor 40k, now 42k"}


def test_deep_nesting_does_not_take_the_note_down(context_check, tmp_path):
    # One record nested deep enough to exhaust the parser's stack raised RecursionError out of
    # run(): no JSON, the hand-off note lost.
    path = tmp_path / "deep.jsonl"
    path.write_bytes(
        b'{"type": "assistant", "message": {"usage": {"input_tokens": 160000}}}\n'
        + b'{"type": "user", "toolUseResult": ' + b"[" * 100_000 + b"]" * 100_000 + b"}\n")
    assert context_check.last_measure(str(path)) == (160_000, False)
    result = run_hook(tmp_path, event(path))
    assert result.returncode == 0, result.stderr
    assert "over 150k" in json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    deep_first = tmp_path / "deep-first.jsonl"
    deep_first.write_bytes(b"[" * 100_000 + b"]" * 100_000 + b"\n"
                           b'{"type": "assistant", "message": {"usage": {"input_tokens": 40000}}}\n')
    assert context_check.floor_tokens(str(deep_first)) == 40_000


def test_bad_numbers_outside_the_input_terms_are_guarded(tmp_path):
    # Survivors of round 3's mutations: an inf usage in the floor scan, a negative output, a
    # negative postTokens.
    inf_first = tmp_path / "inf-first.jsonl"
    inf_first.write_bytes(
        b'{"type": "assistant", "message": {"usage": {"input_tokens": 1e400}}}\n'
        b'{"type": "assistant", "message": {"usage": {"input_tokens": 40000}}}\n'
        b'{"type": "assistant", "message": {"usage": {"input_tokens": 60000}}}\n')
    result = run_hook(tmp_path, event(inf_first))
    assert json.loads(result.stdout) == {"systemMessage": "Ideal-Umbrella: floor 40k, now 60k"}
    negative_output = write_jsonl(tmp_path / "neg-out.jsonl", [
        {"type": "assistant", "message": {"usage": {"input_tokens": 40_000}}},
        {"type": "assistant", "message": {"usage": {"input_tokens": 60_000, "output_tokens": -1_000}}},
    ])
    result = run_hook(tmp_path, event(negative_output))
    assert json.loads(result.stdout) == {"systemMessage": "Ideal-Umbrella: floor 40k, now 60k"}
    negative_post = write_jsonl(tmp_path / "neg-post.jsonl", [
        {"type": "assistant", "message": {"usage": {"input_tokens": 200_000}}},
        {"type": "system", "subtype": "compact_boundary", "compactMetadata": {"postTokens": -5}},
    ])
    result = run_hook(tmp_path, event(negative_post))
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_hand_off_failure_is_not_repeated_on_post_tool_use(tmp_path):
    path = transcript(tmp_path, {"input_tokens": 160_000})
    (tmp_path / "state").write_text("in the way", encoding="utf-8")
    result = run_hook(tmp_path, event(path, name="PostToolUse"))
    assert result.returncode == 0
    assert result.stdout == ""   # the line would show after every tool call
    assert "the hand-off check failed" in result.stderr


def test_hand_off_failure_names_the_error_when_the_log_cannot_be_written(tmp_path):
    # The message pointed at a log that the same unwritable folder kept from being written.
    path = transcript(tmp_path, {"input_tokens": 160_000})
    (tmp_path / "state").write_text("in the way", encoding="utf-8")
    (tmp_path / "context_check.log").mkdir()
    result = run_hook(tmp_path, event(path))
    message = json.loads(result.stdout)["systemMessage"]
    assert "the hand-off check failed (" in message and "details in" not in message


def test_no_floor_read_when_the_transcript_has_no_usage(context_check, tmp_path, monkeypatch):
    # With nothing to show (no usage yet) the floor scan is skipped: it reads up to 4 times
    # TAIL_BYTES on every prompt.
    path = tmp_path / "t.jsonl"
    path.write_text(json.dumps({"type": "user", "message": {"content": "hi"}}) + "\n",
                    encoding="utf-8")
    calls = []
    monkeypatch.setattr(context_check, "floor_tokens", lambda *a, **k: calls.append(a) or 0)
    monkeypatch.setenv("IDEAL_UMBRELLA_STATE_DIR", str(tmp_path / "state"))
    stdin = json.dumps({"transcript_path": str(path), "session_id": "s",
                        "hook_event_name": "UserPromptSubmit"}).encode()
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(stdin), encoding="utf-8"))
    context_check.run()
    assert calls == []
