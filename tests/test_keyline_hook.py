import json
import os
import subprocess
import sys

import pytest

from conftest import ROOT, load_module

HOOK = ROOT / "keyline" / "keyline_hook.py"


@pytest.fixture
def keyline_hook():
    return load_module("keyline_hook", "keyline/keyline_hook.py")


def test_a_note_outside_the_project_is_not_watched(keyline_hook, tmp_path):
    # When the path was not under the project, watched() fell back to the absolute path and
    # matched any notes/ or plans/ folder anywhere (~/notes/todo.md).
    proj = tmp_path / "proj"
    inside = proj / "notes" / "todo.md"
    outside = tmp_path / "elsewhere" / "notes" / "todo.md"
    for note in (inside, outside):
        note.parent.mkdir(parents=True)
        note.write_text("# My todo\n- buy milk\n", encoding="utf-8")
    assert keyline_hook.watched(inside, proj)
    assert not keyline_hook.watched(outside, proj)
    assert keyline_hook.watched(outside, proj, [str(outside)])   # an explicit --watch still applies

    event = json.dumps({"tool_name": "Write", "cwd": str(proj), "tool_input": {"file_path": str(outside)}})
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(proj))
    result = subprocess.run([sys.executable, "-I", str(HOOK)], input=event, capture_output=True,
                            text=True, encoding="utf-8", env=env)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
