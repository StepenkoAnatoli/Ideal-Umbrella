"""config/cloud-setup.sh: writes the rules as a marked section of CLAUDE.md in the folder
Claude Code reads, and leaves the rest of the file alone (general review 44170ca, A7)."""
import os
import shutil
import subprocess

import pytest

from conftest import ROOT

SCRIPT = ROOT / "config" / "cloud-setup.sh"
BEGIN = "<!-- Ideal-Umbrella rules: begin -->"
END = "<!-- Ideal-Umbrella rules: end -->"
RULES = (ROOT / "config" / "CLAUDE.md").read_text(encoding="utf-8").replace("\r\n", "\n")

pytestmark = pytest.mark.skipif(shutil.which("bash") is None or os.name == "nt",
                                reason="the script runs in a Linux cloud container")


def run(home, config_dir=None):
    env = {"HOME": str(home), "PATH": os.environ.get("PATH", "")}
    if config_dir is not None:
        env["CLAUDE_CONFIG_DIR"] = str(config_dir)
    result = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result


def sections(text):
    return text.count(BEGIN), text.count(END)


def test_a_fresh_home_gets_the_section(tmp_path):
    run(tmp_path)
    text = (tmp_path / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
    assert text.startswith(BEGIN + "\n" + RULES) and text.endswith(END + "\n")
    assert sections(text) == (1, 1)


def test_text_already_there_is_kept_and_a_rerun_changes_nothing(tmp_path):
    # `cat >` replaced a CLAUDE.md that the image or an earlier setup step wrote.
    md = tmp_path / ".claude" / "CLAUDE.md"
    md.parent.mkdir()
    md.write_text("# Image rules\nkeep me\n", encoding="utf-8")
    run(tmp_path)
    once = md.read_text(encoding="utf-8")
    assert once.startswith("# Image rules\nkeep me\n\n" + BEGIN + "\n")
    run(tmp_path)
    assert md.read_text(encoding="utf-8") == once


def test_an_old_section_is_replaced_in_place_of_being_added_again(tmp_path):
    md = tmp_path / ".claude" / "CLAUDE.md"
    md.parent.mkdir()
    md.write_text(f"top\n\n{BEGIN}\nold rules\n{END}\n\nbottom\n", encoding="utf-8")
    run(tmp_path)
    text = md.read_text(encoding="utf-8")
    assert "old rules" not in text and sections(text) == (1, 1)
    assert text.startswith("top\n\nbottom\n\n" + BEGIN)


def test_claude_config_dir_is_where_the_file_goes(tmp_path):
    # The script wrote ~/.claude even when Claude Code reads CLAUDE_CONFIG_DIR.
    config = tmp_path / "cfg"
    run(tmp_path / "home", config)
    assert sections((config / "CLAUDE.md").read_text(encoding="utf-8")) == (1, 1)
    assert not (tmp_path / "home" / ".claude").exists()


def test_broken_markers_leave_the_file_alone(tmp_path):
    md = tmp_path / ".claude" / "CLAUDE.md"
    md.parent.mkdir()
    md.write_text(f"{BEGIN}\nno end here\nmy own text\n", encoding="utf-8")
    result = run(tmp_path)
    assert md.read_text(encoding="utf-8") == f"{BEGIN}\nno end here\nmy own text\n"
    assert "markers" in result.stderr


def test_a_linked_claude_md_stays_a_link(tmp_path):
    real = tmp_path / "dotfiles" / "CLAUDE.md"
    real.parent.mkdir()
    real.write_text(f"mine\n\n{BEGIN}\nold\n{END}\n", encoding="utf-8")
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "CLAUDE.md").symlink_to(real)
    run(tmp_path)
    assert (tmp_path / ".claude" / "CLAUDE.md").is_symlink()
    assert real.read_text(encoding="utf-8").startswith("mine\n\n" + BEGIN + "\n" + RULES)
