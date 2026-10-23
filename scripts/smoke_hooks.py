"""Smoke-test the hooks by piping simulated Claude Code events through them."""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = sys.executable

failures = []


def run(cmd, stdin_obj):
    p = subprocess.run(cmd, input=json.dumps(stdin_obj), capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


# 1. context_check.py below threshold -> no output, exit 0
import tempfile, os
td = tempfile.mkdtemp()
transcript = Path(td) / "t.jsonl"
transcript.write_text(json.dumps({"type": "assistant", "isSidechain": False,
    "message": {"usage": {"input_tokens": 1000, "cache_creation_input_tokens": 0,
                          "cache_read_input_tokens": 0, "output_tokens": 10}}}) + "\n",
    encoding="utf-8")
code, out, err = run([PY, "-I", str(ROOT / "hooks" / "context_check.py")],
                     {"transcript_path": str(transcript), "session_id": "smoke-1",
                      "hook_event_name": "UserPromptSubmit"})
if code != 0:
    failures.append(f"context_check below threshold exited {code}: {err}")
print(f"context_check below threshold: exit {code} (expect 0)")

# 2. context_check.py above threshold -> exit 0, emits JSON with systemMessage
transcript.write_text(json.dumps({"type": "assistant", "isSidechain": False,
    "message": {"usage": {"input_tokens": 200000, "cache_creation_input_tokens": 0,
                          "cache_read_input_tokens": 0, "output_tokens": 10}}}) + "\n",
    encoding="utf-8")
code, out, err = run([PY, "-I", str(ROOT / "hooks" / "context_check.py")],
                     {"transcript_path": str(transcript), "session_id": "smoke-2",
                      "hook_event_name": "UserPromptSubmit"})
try:
    obj = json.loads(out)
    ok = "systemMessage" in obj and "additionalContext" in obj.get("hookSpecificOutput", {})
except Exception:
    ok = False
if not (code == 0 and ok):
    failures.append(f"context_check above threshold bad: exit {code} out={out!r} err={err!r}")
print(f"context_check above threshold: exit {code}, valid JSON={ok}")

# 3. keyline_hook.py on a clean file -> exit 0
import tempfile as tf
d = Path(tf.mkdtemp())
note = d / "notes" / "x.txt"
note.parent.mkdir()
note.write_text("key: value; 2026-10-19\n", encoding="utf-8")
code, out, err = run([PY, str(ROOT / "keyline" / "keyline_hook.py")],
                     {"tool_name": "Write", "cwd": str(d), "tool_input": {"file_path": str(note)}})
if code != 0:
    failures.append(f"keyline_hook clean exited {code}: {err}")
print(f"keyline_hook clean file: exit {code} (expect 0)")

# 4. keyline_hook.py on furniture -> exit 2
bad = d / "notes" / "y.md"
bad.write_text("# header\n- bullet\n", encoding="utf-8")
code, out, err = run([PY, str(ROOT / "keyline" / "keyline_hook.py")],
                     {"tool_name": "Write", "cwd": str(d), "tool_input": {"file_path": str(bad)}})
if code != 2:
    failures.append(f"keyline_hook furniture exited {code}, expected 2: {err}")
print(f"keyline_hook furniture: exit {code} (expect 2)")

if failures:
    print("\nFAILURES:")
    for f in failures:
        print("  - " + f)
    sys.exit(1)
print("\nAll smoke checks passed.")
