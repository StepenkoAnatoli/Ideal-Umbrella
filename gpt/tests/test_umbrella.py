import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from gpt_umbrella.analyze import analyze, compare, discover
from gpt_umbrella.audit import request_audit
from gpt_umbrella.install import install, uninstall, verify, hook_entries
from gpt_umbrella.monitor import handle, run, transcript_context
from gpt_umbrella.storage import read_json, write_json
from gpt_umbrella.usage import normalize, estimate


def usage(i=1000, c=500, o=100, r=20, w=0):
    return {"input_tokens": i, "cached_input_tokens": c, "output_tokens": o,
            "reasoning_output_tokens": r, "cache_write_input_tokens": w}


def record(identity="r1", u=None):
    return {"type": "token_usage_record", "payload": {"response_id": identity, "usage": u or usage()}}


def token_event(u=None, window=2000):
    return {"type": "event_msg", "payload": {"type": "token_count", "info": {
        "total_token_usage": u or usage(), "last_token_usage": u or usage(), "model_context_window": window}}}


class Temporary(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def transcript(self, values, name="session.jsonl"):
        path = self.root / name
        path.write_text("\n".join(json.dumps(v) for v in values) + "\n", encoding="utf-8")
        return path


class UsageTests(unittest.TestCase):
    def test_subsets_not_added(self):
        u = normalize(usage(w=200))
        self.assertEqual(estimate(u, {"input": 2, "cached_input": 0.2, "cache_write": 2.5, "output": 10}), 0.0022)

    def test_responses_lifetimes(self):
        u = normalize({"input_tokens": 12000, "output_tokens": 0, "input_tokens_details": {
            "cached_tokens": 4000, "cache_write_tokens": 7000,
            "cache_write_tokens_details": {"ttl_30m_tokens": 3000, "ttl_12h_tokens": 4000}}})
        self.assertEqual(estimate(u, {"input": 1, "cached_input": 0.1, "cache_write_30m": 1.25,
                                     "cache_write_12h": 2.5}), 0.01515)

    def test_unknown_write_rate_refused(self):
        with self.assertRaises(ValueError):
            estimate(normalize(usage(w=1)), {"input": 1, "cached_input": 0.1, "output": 2})

    def test_invalid_counts(self):
        for bad in (True, -1, 1.5, "5", float("nan")):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                normalize(usage(i=bad))
        with self.assertRaises(ValueError):
            normalize(usage(c=1001))
        with self.assertRaises(ValueError):
            normalize(usage(r=101))


class AnalysisTests(Temporary):
    def test_stream_duplicates_and_event_counter_not_added(self):
        path = self.transcript([record(u=usage(o=50)), record(), token_event()])
        result = analyze([path])
        self.assertEqual(result["usage"]["total"], 1100)
        self.assertEqual(result["response_records"], 1)

    def test_shared_response_across_files(self):
        a = self.transcript([record()])
        b = self.transcript([record(), record("r2")], "fork.jsonl")
        self.assertEqual(analyze([a, b])["usage"]["input"], 2000)

    def test_legacy_duplicate_events(self):
        path = self.transcript([token_event(), token_event(), token_event(usage(i=2000))])
        result = analyze([path])
        self.assertEqual(result["usage"]["input"], 2000)
        self.assertEqual(result["legacy_session_totals"], 1)

    def test_legacy_copy_not_added_to_records(self):
        meta = {"type": "session_meta", "payload": {"id": "same"}}
        a = self.transcript([meta, record()])
        b = self.transcript([meta, token_event()], "old.jsonl")
        self.assertEqual(analyze([a, b])["usage"]["input"], 1000)
        self.assertEqual(analyze([b, a])["usage"]["input"], 1000)

    def test_tool_output_private_and_commands_hashed(self):
        events = []
        for i in range(2):
            events.extend([{"type": "response_item", "payload": {"type": "function_call", "call_id": str(i),
                "name": "exec_command", "arguments": json.dumps({"cmd": "secret-command"})}},
                {"type": "response_item", "payload": {"type": "function_call_output", "call_id": str(i),
                "output": "private-data" * 2000}}])
        result = analyze([self.transcript(events)])
        self.assertNotIn("secret-command", json.dumps(result))
        self.assertNotIn("private-data", json.dumps(result))
        self.assertEqual(result["tools"]["exec_command"]["outputs_over_12000_characters"], 2)
        self.assertEqual(result["repeated_commands"][0]["occurrences"], 2)

    def test_corrupt_line_is_counted(self):
        path = self.transcript([record()])
        with path.open("a") as f:
            f.write("{broken\n")
        self.assertEqual(analyze([path])["warnings"]["malformed_json_lines"], 1)

    def test_response_json(self):
        path = self.root / "response.json"
        write_json(path, {"object": "response", "id": "r", "model": "gpt-test", "usage": usage(), "output": []})
        result = analyze([path])
        self.assertEqual(result["by_model"]["gpt-test"]["total"], 1100)

    def test_compare(self):
        result = analyze([self.transcript([record()])])
        self.assertEqual(compare(result, result)["metrics"]["input_per_response"]["change_percent"], 0)

    def test_empty_discovery_errors(self):
        with self.assertRaises(ValueError):
            discover([self.root])


class MonitorTests(Temporary):
    def event(self, path, **extra):
        return {"hook_event_name": "UserPromptSubmit", "session_id": "../../escape", "transcript_path": str(path), **extra}

    def test_below_threshold_no_context_or_state(self):
        path = self.transcript([token_event()])
        self.assertEqual(handle(self.event(path), self.root / "state"), {})
        self.assertFalse((self.root / "state").exists())

    def test_reminder_deduplicated_and_reset(self):
        path = self.transcript([token_event(usage(i=1500))])
        state = self.root / "state"
        self.assertIn("hookSpecificOutput", handle(self.event(path), state))
        self.assertEqual(handle(self.event(path), state), {})
        self.transcript([token_event()])
        handle(self.event(path), state)
        self.transcript([token_event(usage(i=1500))])
        self.assertIn("hookSpecificOutput", handle(self.event(path), state))
        self.assertEqual(len(list(state.glob("*.json"))), 1)

    def test_compaction_invalidates_old_context(self):
        path = self.transcript([token_event(), {"type": "compacted", "payload": {}}])
        self.assertIsNone(transcript_context(path))

    def test_model_event_is_ignored_without_state_write(self):
        event = {"hook_event_name": "PostModelRequest", "thread_id": "t1", "status": "completed",
                 "token_usage": usage(), "model": "test", "prompt": "DO-NOT-STORE"}
        self.assertEqual(handle(event, self.root), {})
        self.assertEqual(list(self.root.glob("*.json")), [])

    def test_fail_open(self):
        with patch("sys.stdin", io.StringIO("{bad")), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(run(self.root), 0)


class InstallTests(Temporary):
    def setUp(self):
        super().setUp()
        self.home = self.root / "Codex home with spaces"

    def test_roundtrip_and_idempotence(self):
        self.home.mkdir()
        originals = {"config.toml": b'\xef\xbb\xbf# Mine\r\nmodel = "unchanged"\r\n', "AGENTS.md": b"My rules without newline"}
        for name, data in originals.items():
            (self.home / name).write_bytes(data)
        install(self.home)
        self.assertEqual(verify(self.home), [])
        self.assertEqual(install(self.home)["changes"], [])
        uninstall(self.home)
        for name, data in originals.items():
            self.assertEqual((self.home / name).read_bytes(), data)
        self.assertFalse((self.home / "hooks.json").exists())

    def test_preserve_existing_config_and_hooks(self):
        self.home.mkdir()
        config = 'tool_output_token_limit = 9000\n[skills]\nmax_context_tokens = 8000\n'
        (self.home / "config.toml").write_text(config)
        own = {"hooks": [{"type": "command", "command": "my-own-hook"}]}
        write_json(self.home / "hooks.json", {"hooks": {"UserPromptSubmit": [own]}})
        install(self.home)
        self.assertEqual((self.home / "config.toml").read_text(), config)
        uninstall(self.home)
        self.assertEqual(read_json(self.home / "hooks.json")["hooks"]["UserPromptSubmit"], [own])

    def test_post_install_edits_survive(self):
        install(self.home)
        with (self.home / "AGENTS.md").open("a") as f:
            f.write("\nNew user rule\n")
        with (self.home / "config.toml").open("a") as f:
            f.write("include_instructions = true\n")
        uninstall(self.home)
        self.assertIn("New user rule", (self.home / "AGENTS.md").read_text())
        config = tomllib.loads((self.home / "config.toml").read_text())
        self.assertEqual(config, {"skills": {"include_instructions": True}})

    def test_dry_run_writes_nothing(self):
        install(self.home, dry_run=True)
        self.assertFalse(self.home.exists())

    def test_observe_does_not_create_config(self):
        install(self.home, preset="observe")
        self.assertFalse((self.home / "config.toml").exists())

    def test_malformed_config_stops_before_write(self):
        self.home.mkdir()
        (self.home / "config.toml").write_text("broken TOML")
        with self.assertRaises(ValueError):
            install(self.home)
        self.assertFalse((self.home / "AGENTS.md").exists())

    def test_write_failure_rolls_back(self):
        from gpt_umbrella import install as module
        original = module.atomic_write
        def failing(path, data):
            if Path(path) == self.home / "AGENTS.md":
                raise OSError("simulated disk failure")
            original(path, data)
        with patch.object(module, "atomic_write", failing), self.assertRaises(OSError):
            install(self.home)
        self.assertFalse((self.home / "config.toml").exists())
        self.assertFalse((self.home / "gpt-umbrella/install-record.json").exists())

    def test_installed_cli_runs_under_isolation(self):
        install(self.home)
        proc = subprocess.run([sys.executable, "-I", str(self.home / "gpt-umbrella/runtime/umbrella.py"), "verify", "--home", str(self.home)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    @unittest.skipUnless(os.name == "nt", "Windows hook command")
    def test_powershell_hook_with_spaces(self):
        install(self.home)
        command = hook_entries(self.home)["UserPromptSubmit"]["hooks"][0]["command"]
        transcript = self.transcript([token_event(usage(i=1500))])
        event = {"hook_event_name": "UserPromptSubmit", "session_id": "test", "transcript_path": str(transcript)}
        proc = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command], input=json.dumps(event), capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("hookSpecificOutput", json.loads(proc.stdout))

    @unittest.skipUnless(os.name == "nt", "Windows hook command")
    def test_cmd_host_hook_with_spaces(self):
        install(self.home)
        command = hook_entries(self.home)["UserPromptSubmit"]["hooks"][0]["command"]
        proc = subprocess.run(["cmd.exe", "/d", "/s", "/c", command], input="{}", capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_edited_hook_retains_runtime(self):
        install(self.home)
        hooks = read_json(self.home / "hooks.json")
        hooks["hooks"]["UserPromptSubmit"][0]["hooks"][0]["timeout"] = 7
        write_json(self.home / "hooks.json", hooks)
        result = uninstall(self.home)
        self.assertTrue(result["notices"])
        self.assertTrue((self.home / "gpt-umbrella/runtime/umbrella.py").exists())

    def test_corrupt_backup_refuses_undo(self):
        self.home.mkdir()
        (self.home / "AGENTS.md").write_text("existing rules")
        install(self.home)
        record = read_json(self.home / "gpt-umbrella/install-record.json")
        backup = self.home / record["files"]["AGENTS.md"]["backup"]
        backup.write_text("corrupted")
        with self.assertRaises(ValueError):
            uninstall(self.home)
        self.assertEqual(verify(self.home), [])

    def test_duplicate_json_keys_refused_before_write(self):
        self.home.mkdir()
        (self.home / "hooks.json").write_text('{"hooks": {}, "hooks": {}}')
        with self.assertRaises(ValueError):
            install(self.home)
        self.assertFalse((self.home / "AGENTS.md").exists())


class RequestTests(unittest.TestCase):
    def test_eager_tools_and_prefix_change(self):
        tools = [{"type": "function", "name": str(i)} for i in range(8)]
        reports = request_audit([{"tools": tools}, {"tools": [], "instructions": "secret"}])
        self.assertTrue(reports["requests"][0]["recommendations"])
        self.assertTrue(reports["requests"][1]["recommendations"])
        self.assertNotIn("secret", json.dumps(reports))


if __name__ == "__main__":
    unittest.main()
