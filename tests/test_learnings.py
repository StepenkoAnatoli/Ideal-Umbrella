"""The learnings template and the rule lines that point at it."""
import re
import subprocess
import sys

import pytest

from conftest import ROOT

LINT = ROOT / "keyline" / "keyline_lint.py"
TEMPLATE = ROOT / "config" / "learnings.md"
OWN = ROOT / "notes" / "learnings.md"
HEADINGS = ("learnings", "decided", "tried and ruled out", "watch out")
RULE_FILES = ("config/CLAUDE.md", "config/cloud-setup.sh", "keyline/CLAUDE-snippet.md")


@pytest.mark.parametrize("path", [TEMPLATE, OWN], ids=["template", "own"])
def test_learnings_files_are_keyline(path):
    # One 'key: item; item' line per heading, the four headings in order, nothing else.
    lines = path.read_text(encoding="utf-8").splitlines()
    assert [line.split(":", 1)[0] for line in lines] == list(HEADINGS)
    for line in lines:
        assert re.fullmatch(r"[a-z ]+: \S.*", line), line
        assert not re.search(r"\*\*|`|^\s*(#{1,6}|[-*+]|\d+[.)])\s", line), line
    assert path.read_bytes().endswith(b"\n") and b"\r" not in path.read_bytes()


def test_learnings_files_pass_keyline_lint():
    pytest.importorskip("tiktoken")
    result = subprocess.run([sys.executable, "-I", str(LINT), str(TEMPLATE), str(OWN)],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("OK ") == 2


def test_template_holds_hints_and_the_own_file_holds_entries():
    template = TEMPLATE.read_text(encoding="utf-8")
    assert "replace the hints with real entries" in template
    own = OWN.read_text(encoding="utf-8")
    for hint in ("decided: choice and why", "tried and ruled out: approach dropped and why"):
        assert hint in template and hint not in own


@pytest.mark.parametrize("relative", RULE_FILES)
def test_rule_files_say_when_to_save_a_learning_and_where(relative):
    text = (ROOT / relative).read_text(encoding="utf-8")
    sentence = [line for line in text.splitlines() if "notes/learnings.md" in line]
    assert len(sentence) == 1, relative
    line = sentence[0]
    for heading in HEADINGS[1:]:
        assert f"under {heading}" in line, (relative, heading)
    for trigger in ("choice and why", "dropped and why", "bug's cause found after failed attempts",
                    "user correcting how something is done here"):
        assert trigger in line, (relative, trigger)


def test_cloud_setup_writes_config_claude_md_plus_its_cloud_line():
    # cloud-setup.sh carries a copy of config/CLAUDE.md in a heredoc; the copy drifts unnoticed.
    script = (ROOT / "config" / "cloud-setup.sh").read_text(encoding="utf-8")
    body = script.split("<<'EOF'\n", 1)[1].split("\nEOF\n", 1)[0].splitlines()
    rules = (ROOT / "config" / "CLAUDE.md").read_text(encoding="utf-8").splitlines()
    assert body[:-1] == rules
    assert body[-1].startswith("- In a cloud session the machine is discarded")
