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


def test_a_write_cut_short_leaves_the_file_as_it_was(tmp_path):
    # Fresh review 4c3992c, F5: the file was rewritten in place (cat tmp > file, then >> file):
    # a write cut short (a full disk; here a 1 KiB file size limit) left half a section with a
    # begin marker and no end, which every later run then refused as broken markers.
    md = tmp_path / ".claude" / "CLAUDE.md"
    md.parent.mkdir()
    md.write_text("# Image rules\nkeep me\n", encoding="utf-8")
    env = {"HOME": str(tmp_path), "PATH": os.environ.get("PATH", "")}
    result = subprocess.run(["bash", "-c", 'trap "" XFSZ; ulimit -f 1; exec bash "$0"', str(SCRIPT)],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert md.read_text(encoding="utf-8") == "# Image rules\nkeep me\n"
    assert "not written" in result.stderr, result.stderr
    assert [p.name for p in md.parent.iterdir()] == ["CLAUDE.md"]


def _shim(tmp_path, name, body):
    """A PATH folder whose `name` runs body (bash) before, or instead of, the real command."""
    bin_dir = tmp_path / "shim"
    bin_dir.mkdir(exist_ok=True)
    tool = bin_dir / name
    tool.write_text("#!/bin/bash\n" + body + "\n", encoding="utf-8")
    tool.chmod(0o755)
    return {"HOME": str(tmp_path), "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}


def test_the_temp_file_is_never_more_open_than_the_file_it_replaces(tmp_path):
    # Self-check of F5 (PR #39): the temp file beside CLAUDE.md was made with the umask (0644)
    # and narrowed only after awk had copied the user's text into it, so a 0600 file sat in a
    # 0644 one for a moment, the class A8 closed for the installers. The awk shim records the
    # temp file's mode while awk runs.
    md = tmp_path / ".claude" / "CLAUDE.md"
    md.parent.mkdir()
    md.write_text("private\n", encoding="utf-8")
    md.chmod(0o600)
    seen = tmp_path / "seen"
    env = _shim(tmp_path, "awk", f'stat -c %a "{md}".ideal-umbrella-* > "{seen}"\n'
                                 f'exec "{shutil.which("awk")}" "$@"')
    result = subprocess.run(["bash", "-c", 'umask 022; exec bash "$0"', str(SCRIPT)], env=env,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert seen.read_text().split() == ["600"]
    assert oct(md.stat().st_mode & 0o777) == "0o600"
    assert RULES in md.read_text(encoding="utf-8")


def test_a_file_that_cannot_be_moved_over_is_still_written(tmp_path):
    # Self-check of F5 (PR #39): a CLAUDE.md that is a bind mount, or sits in a folder the
    # session may not write, cannot be replaced by a rename; it was left without the rules,
    # where the earlier in-place write had worked. A failing mv stands in for both.
    md = tmp_path / ".claude" / "CLAUDE.md"
    md.parent.mkdir()
    md.write_text("# Image rules\n", encoding="utf-8")
    env = _shim(tmp_path, "mv", "exit 1")
    result = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    text = md.read_text(encoding="utf-8")
    assert text.startswith(f"# Image rules\n\n{BEGIN}\n{RULES}") and text.endswith(f"{END}\n")
    assert [p.name for p in md.parent.iterdir()] == ["CLAUDE.md"]


def test_broken_markers_leave_no_temp_file_behind(tmp_path):
    # Fresh review 84bfecf, G1: the temp file is made before the marker check (self-check S2),
    # and the broken-marker exit did not remove it, so every run left an empty
    # CLAUDE.md.ideal-umbrella-<pid> beside the file (or in TMPDIR).
    md = tmp_path / ".claude" / "CLAUDE.md"
    md.parent.mkdir()
    md.write_text(f"{BEGIN}\nno end here\n", encoding="utf-8")
    result = run(tmp_path)
    assert "markers" in result.stderr
    assert [p.name for p in md.parent.iterdir()] == ["CLAUDE.md"]


def test_a_file_already_named_like_the_temp_file_is_neither_reused_nor_changed(tmp_path):
    # Fresh review 84bfecf, G2: the temp name was CLAUDE.md.ideal-umbrella-$$ and `: >` opened
    # it without O_EXCL, so a file already there (a run that kept its temp file, as the in-place
    # fallback does, under the same pid in a fresh container) was truncated and kept its own
    # mode: 0644 here, beside a 0600 CLAUDE.md (the S1 promise).
    md = tmp_path / ".claude" / "CLAUDE.md"
    md.parent.mkdir()
    md.write_text("private\n", encoding="utf-8")
    md.chmod(0o600)
    seen = tmp_path / "seen"
    env = _shim(tmp_path, "awk", f'stat -L -c %a /proc/$$/fd/1 > "{seen}"\n'
                                 f'exec "{shutil.which("awk")}" "$@"')
    pre = 'f="$1.ideal-umbrella-$$"; echo kept > "$f"; chmod 644 "$f"; umask 022; exec bash "$0"'
    result = subprocess.run(["bash", "-c", pre, str(SCRIPT), str(md)], env=env,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert seen.read_text().split() == ["600"]
    kept = [p for p in md.parent.iterdir() if p.name != "CLAUDE.md"]
    assert len(kept) == 1 and kept[0].read_text() == "kept\n"
    assert RULES in md.read_text(encoding="utf-8")


@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0,
                    reason="needs a user that file modes apply to")
def test_a_file_that_cannot_be_opened_for_writing_is_reported_as_not_written(tmp_path):
    # Fresh review 84bfecf, G3: when the in-place write could not even open the file (a
    # read-only CLAUDE.md in a folder the session may not write), the note said the file
    # "may be cut short" and kept a temp file in TMPDIR, though the file was never touched.
    md = tmp_path / ".claude" / "CLAUDE.md"
    md.parent.mkdir()
    md.write_text("# Image rules\n", encoding="utf-8")
    md.chmod(0o444)
    md.parent.chmod(0o555)
    tmpdir = tmp_path / "t"
    tmpdir.mkdir()
    env = {"HOME": str(tmp_path), "PATH": os.environ.get("PATH", ""), "TMPDIR": str(tmpdir)}
    try:
        result = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True)
    finally:
        md.parent.chmod(0o755)
    assert result.returncode == 0, result.stderr
    assert "not written" in result.stderr and "cut short" not in result.stderr, result.stderr
    assert list(tmpdir.iterdir()) == []
    assert md.read_text(encoding="utf-8") == "# Image rules\n"


def test_a_folder_named_claude_md_is_left_alone_with_a_note(tmp_path):
    # Fresh review 84bfecf, G4: with a folder in CLAUDE.md's place, `mv -f tmp folder` moved the
    # temp file into it and the run ended silently with no rules written anywhere.
    md = tmp_path / ".claude" / "CLAUDE.md"
    md.mkdir(parents=True)
    result = run(tmp_path)
    assert "not a file" in result.stderr, result.stderr
    assert list(md.iterdir()) == []
    assert [p.name for p in md.parent.iterdir()] == ["CLAUDE.md"]


@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0,
                    reason="needs a user that file modes apply to")
def test_a_read_only_claude_md_in_a_writable_folder_gets_the_rules(tmp_path):
    # Fresh review 84bfecf, G5: the temp file was given CLAUDE.md's mode before the section was
    # appended to it, so a 0444 CLAUDE.md (an image that ships it read-only) made the script's
    # own append fail: "not written", though the rename it is built for would have worked.
    md = tmp_path / ".claude" / "CLAUDE.md"
    md.parent.mkdir()
    md.write_text("# Image rules\n", encoding="utf-8")
    md.chmod(0o444)
    result = run(tmp_path)
    assert result.stderr == ""
    assert md.read_text(encoding="utf-8").startswith(f"# Image rules\n\n{BEGIN}\n{RULES}")
    assert oct(md.stat().st_mode & 0o777) == "0o444"
    assert [p.name for p in md.parent.iterdir()] == ["CLAUDE.md"]


# Round 2 review of the G1-G5 fixes (research/review-findings-fresh-84bfecf.md, R2-1 to R2-6).

def _host(tmp_path, before="", after=""):
    """The script pasted into a longer setup script, as the README says to use it."""
    host = tmp_path / "setup.sh"
    host.write_text(before + SCRIPT.read_text(encoding="utf-8") + "\n" + after, encoding="utf-8")
    env = {"HOME": str(tmp_path), "PATH": os.environ.get("PATH", "")}
    return subprocess.run(["bash", str(host)], env=env, capture_output=True, text=True)


def test_an_end_marker_before_the_begin_marker_leaves_the_file_alone(tmp_path):
    target = tmp_path / ".claude" / "CLAUDE.md"
    target.parent.mkdir()
    text = f"top\n{END}\nmine\n{BEGIN}\nMY PRECIOUS TEXT\nmore mine\n"
    target.write_text(text, encoding="utf-8")
    result = run(tmp_path)
    assert target.read_text(encoding="utf-8") == text
    assert "broken or repeated rule markers" in result.stderr


def test_pasted_under_set_e_the_setup_goes_on_and_gets_the_rules(tmp_path):
    target = tmp_path / ".claude" / "CLAUDE.md"
    target.parent.mkdir()
    target.write_text("# image rules\n", encoding="utf-8")
    result = _host(tmp_path, before="set -e\ntrap 'echo HOST-TRAP' EXIT\n", after="echo LATER-STEP-RAN\n")
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["LATER-STEP-RAN", "HOST-TRAP"]
    assert sections(target.read_text(encoding="utf-8")) == (1, 1)


def test_a_failed_write_does_not_end_the_setup_script(tmp_path):
    (tmp_path / ".claude" / "CLAUDE.md").mkdir(parents=True)
    result = _host(tmp_path, after="echo LATER-STEP-RAN\n")
    assert result.returncode == 0
    assert "not a file" in result.stderr and result.stdout == "LATER-STEP-RAN\n"


def test_marker_lines_in_a_code_fence_are_the_users_example(tmp_path):
    target = tmp_path / ".claude" / "CLAUDE.md"
    target.parent.mkdir()
    text = f"mine\n```text\n{BEGIN}\nMY EXAMPLE\n{END}\n```\nafter\n"
    target.write_text(text, encoding="utf-8")
    run(tmp_path)
    once = target.read_text(encoding="utf-8")
    assert once.startswith(text) and sections(once) == (2, 2)
    run(tmp_path)
    assert target.read_text(encoding="utf-8") == once


def test_a_crlf_file_gets_its_section_replaced(tmp_path):
    target = tmp_path / ".claude" / "CLAUDE.md"
    target.parent.mkdir()
    target.write_bytes(f"mine\r\n{BEGIN}\r\nold\r\n{END}\r\n".encode())
    run(tmp_path)
    text = target.read_bytes().decode()
    assert sections(text) == (1, 1) and "old" not in text and text.startswith("mine\r\n")


def test_a_marker_with_trailing_spaces_is_still_the_marker(tmp_path):
    target = tmp_path / ".claude" / "CLAUDE.md"
    target.parent.mkdir()
    target.write_text(f"mine\n{BEGIN} \nold\n{END}\t\n", encoding="utf-8")
    result = run(tmp_path)
    text = target.read_text(encoding="utf-8")
    assert result.stderr == "" and sections(text) == (1, 1) and "old" not in text


def test_a_hard_linked_claude_md_keeps_its_other_name(tmp_path):
    other = tmp_path / "dotfiles-CLAUDE.md"
    other.write_text("mine\n", encoding="utf-8")
    target = tmp_path / ".claude" / "CLAUDE.md"
    target.parent.mkdir()
    os.link(other, target)
    run(tmp_path)
    assert os.path.samefile(other, target) and sections(other.read_text(encoding="utf-8")) == (1, 1)


def test_a_link_into_a_missing_folder_is_left_a_link_with_a_note(tmp_path):
    target = tmp_path / ".claude" / "CLAUDE.md"
    target.parent.mkdir()
    target.symlink_to(tmp_path / "dotfiles" / "CLAUDE.md")
    result = run(tmp_path)
    assert target.is_symlink() and not (tmp_path / "dotfiles").exists()
    assert "missing" in result.stderr


@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() != 0, reason="chown needs root")
def test_a_claude_md_owned_by_another_user_keeps_its_owner(tmp_path):
    target = tmp_path / ".claude" / "CLAUDE.md"
    target.parent.mkdir()
    target.write_text("mine\n", encoding="utf-8")
    os.chown(target, 65534, 65534)
    run(tmp_path)
    assert (os.stat(target).st_uid, os.stat(target).st_gid) == (65534, 65534)
    assert sections(target.read_text(encoding="utf-8")) == (1, 1)


def test_blank_lines_outside_the_section_are_kept_as_written(tmp_path):
    target = tmp_path / ".claude" / "CLAUDE.md"
    target.parent.mkdir()
    text = "code:\n\n    line1\n    \n    line2\nhard break  \n\n\n"
    target.write_text(text, encoding="utf-8")
    run(tmp_path)
    once = target.read_text(encoding="utf-8")
    assert once.startswith(text + BEGIN)
    run(tmp_path)
    assert target.read_text(encoding="utf-8") == once
