"""Adversarial cases added during the 2026-11-17 review."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gpt_umbrella.analyze import analyze, compare
from gpt_umbrella.audit import request_audit
from gpt_umbrella.install import install, uninstall, mutation_lock
from gpt_umbrella.monitor import handle
from gpt_umbrella.storage import read_json, write_json


def usage(i=1600):
    return {"input_tokens": i, "cached_input_tokens": 0, "output_tokens": 0,
            "reasoning_output_tokens": 0}


def count(i=1600):
    return {"type": "event_msg", "payload": {"type": "token_count", "info": {
        "total_token_usage": usage(i), "last_token_usage": usage(i), "model_context_window": 2000}}}


class ReviewCases(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def log(self, name, events):
        path = self.root / name
        path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
        return path

    def prompt(self, path):
        return {"hook_event_name": "UserPromptSubmit", "session_id": "shared-root",
                "transcript_path": str(path)}

    def test_fork_reminders_are_independent(self):
        a = self.log("parent.jsonl", [count()])
        b = self.log("fork.jsonl", [count()])
        state = self.root / "state"
        self.assertIn("hookSpecificOutput", handle(self.prompt(a), state))
        self.assertIn("hookSpecificOutput", handle(self.prompt(b), state))

    def test_stale_saved_usage_does_not_override_transcript(self):
        path = self.log("chat.jsonl", [count(800)])
        state = self.root / "state"
        handle({"hook_event_name": "PostModelRequest", "session_id": "shared-root", "status": "completed",
                "token_usage": usage(1700), "model": "old-model"}, state)
        self.assertEqual(handle(self.prompt(path), state), {})

    def test_compaction_resets_band_even_if_next_context_is_high(self):
        path = self.log("chat.jsonl", [count()])
        state = self.root / "state"
        self.assertIn("hookSpecificOutput", handle(self.prompt(path), state))
        self.log("chat.jsonl", [count(), {"type": "compacted", "timestamp": "2026-11-17T00:00:00Z", "payload": {}}, count()])
        self.assertIn("hookSpecificOutput", handle(self.prompt(path), state))

    def test_manifest_cannot_delete_unowned_file(self):
        home = self.root / "home"
        install(home)
        sentinel = home / "unrelated.txt"
        sentinel.write_bytes(b"must survive")
        manifest = home / "gpt-umbrella/install-record.json"
        record = read_json(manifest)
        record["files"]["unrelated.txt"] = {"before": None, "after": hashlib.sha256(sentinel.read_bytes()).hexdigest(), "backup": None}
        write_json(manifest, record)
        with self.assertRaises(ValueError):
            uninstall(home)
        self.assertEqual(sentinel.read_bytes(), b"must survive")

    def test_malformed_call_id_does_not_crash_analysis(self):
        p = self.log("bad.jsonl", [{"type": "response_item", "payload": {
            "type": "function_call", "call_id": [], "name": "exec_command"}}])
        report = analyze([p])
        self.assertTrue(report["warnings"])

    def test_mixed_legacy_models_are_not_priced_as_last_model(self):
        p = self.log("mixed.jsonl", [
            {"type": "turn_context", "payload": {"model": "model-a"}}, count(1000),
            {"type": "turn_context", "payload": {"model": "model-b"}}, count(2000)])
        report = analyze([p], {"model-b": {"input": 100, "output": 100}})
        self.assertNotIn("model-b", report["by_model"])
        self.assertTrue(report["warnings"])

    def test_analysis_invalidates_context_after_compaction(self):
        p = self.log("compact.jsonl", [count(), {"type": "compacted", "payload": {}}])
        self.assertIsNone(analyze([p])["session_details"][0]["last_context_estimate"])

    def test_compare_exposes_total_work(self):
        before = {"response_records": 1, "usage": {k: 100 for k in ("input", "cached", "write", "ordinary_input", "output", "reasoning")}}
        after = {"response_records": 3, "usage": {k: 150 for k in before["usage"]}}
        result = compare(before, after)
        self.assertEqual(result["totals"]["input"]["change_percent"], 50)

    def test_string_input_is_not_replayed_history(self):
        result = request_audit([{"previous_response_id": "r1", "input": "hello"}])
        self.assertEqual(result["requests"][0]["recommendations"], [])

    def test_namespaced_eager_tools_are_counted(self):
        tools = [{"type": "namespace", "name": "tools", "tools": [{"type": "function", "name": str(i)} for i in range(6)]}]
        self.assertEqual(request_audit([{"tools": tools}])["requests"][0]["eager_tools"], 6)

    def test_mutations_are_serialized(self):
        home = self.root / "home"
        with mutation_lock(home):
            with self.assertRaises(ValueError):
                install(home)
        self.assertFalse((home / "gpt-umbrella/install-record.json").exists())
        self.assertFalse((home / "gpt-umbrella/mutation.lock").exists())

    def test_rollback_preserves_concurrent_external_edit(self):
        from gpt_umbrella import install as module
        home = self.root / "home"
        original = module.atomic_write
        def write_then_conflict(path, data):
            if Path(path) == home / "AGENTS.md":
                (home / "config.toml").write_text('model = "external-edit"\n')
                raise OSError("simulated failure after external editor saved")
            original(path, data)
        with patch.object(module, "atomic_write", write_then_conflict), self.assertRaises(OSError):
            install(home)
        self.assertEqual((home / "config.toml").read_text(), 'model = "external-edit"\n')
        self.assertTrue((home / "gpt-umbrella/install-record.json").exists())
        uninstall(home)
        self.assertEqual((home / "config.toml").read_text(), 'model = "external-edit"\n')

    def test_malformed_backup_path_refused(self):
        home = self.root / "home"
        home.mkdir()
        (home / "AGENTS.md").write_text("user rules")
        install(home)
        manifest = home / "gpt-umbrella/install-record.json"
        record = read_json(manifest)
        record["files"]["AGENTS.md"]["backup"] = "AGENTS.md"
        write_json(manifest, record)
        with self.assertRaises(ValueError):
            uninstall(home)

    def test_invalid_rate_object_is_unavailable_not_traceback(self):
        p = self.log("rate.jsonl", [
            {"type": "turn_context", "payload": {"model": "model-a"}},
            {"type": "token_usage_record", "payload": {"response_id": "r1", "usage": usage()}}])
        result = analyze([p], {"model-a": "invalid"})
        self.assertIn("unavailable", result["api_list_price_estimates"]["model-a"])


if __name__ == "__main__":
    unittest.main()
