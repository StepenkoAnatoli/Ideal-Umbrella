"""~/.claude/CLAUDE.md: install manages only the lines between two marker lines.

The installer used to replace the whole file (after a backup), and uninstall put the backup
back, so a user's own rules were moved aside for as long as Ideal-Umbrella was installed.
Each test below guards one failure story of research/premortem-marker-section.md.
"""
import hashlib
import json

import pytest

from conftest import ROOT, load_module

RULES = (ROOT / "config" / "CLAUDE.md").read_bytes().decode("utf-8").replace("\r\n", "\n")
BEGIN = "<!-- Ideal-Umbrella rules: begin -->"
END = "<!-- Ideal-Umbrella rules: end -->"
SECTION = f"{BEGIN}\n{RULES}{END}\n"
OLD_BACKUP = "CLAUDE.md.bak-20250101-000000"


@pytest.fixture
def uninstall_module():
    return load_module("uninstall_module", "config/uninstall.py")


def md(home):
    return home / ".claude" / "CLAUDE.md"


def write_md(home, text):
    md(home).parent.mkdir(parents=True, exist_ok=True)
    md(home).write_bytes(text.encode("utf-8"))


def read_md(home):
    return md(home).read_bytes().decode("utf-8")


def record_path(home):
    return home / ".claude" / "ballast" / "install-record.json"


def read_record(home):
    return json.loads(record_path(home).read_text(encoding="utf-8"))


def backups(home):
    return sorted(p.name for p in (home / ".claude").glob("CLAUDE.md.bak-*"))


def old_install(install_module, home, before=None):
    """What the whole-file installer before the marker section left behind: CLAUDE.md is the
    rules, the user's earlier file (if any) is in a backup, and the record holds the backup
    name and the hash of the whole file."""
    install_module.install(home)
    write_md(home, RULES)
    for name in backups(home):
        (home / ".claude" / name).unlink()
    if before is not None:
        (home / ".claude" / OLD_BACKUP).write_bytes(before.encode("utf-8"))
    record = read_record(home)
    record["claude_md"] = {"backup": OLD_BACKUP if before is not None else None,
                           "sha256": hashlib.sha256(RULES.encode("utf-8")).hexdigest()}
    record_path(home).write_text(json.dumps(record), encoding="utf-8")


def test_install_writes_only_the_section_when_there_is_no_file(install_module, tmp_path):
    home = tmp_path / "home"
    install_module.install(home)
    assert read_md(home) == SECTION
    assert read_record(home)["claude_md"]["created"] is True


@pytest.mark.parametrize("before, joined", [("my own rules\n", "\n"), ("mine", "\n\n")])
def test_install_appends_the_section_after_user_text(install_module, tmp_path, before, joined):
    home = tmp_path / "home"
    write_md(home, before)
    install_module.install(home)
    assert read_md(home) == before + joined + SECTION
    assert [(home / ".claude" / b).read_text(encoding="utf-8") for b in backups(home)] == [before]


def test_reinstall_is_idempotent_with_user_text(install_module, tmp_path):
    # Story 1: config/CLAUDE.md has two H1 headings, so a section that ends at the next heading
    # would be found half and appended again on every run.
    home = tmp_path / "home"
    write_md(home, "# Mine\n- a\n")
    install_module.install(home)
    after_first = read_md(home)
    changes, notices = install_module.install(home)
    assert changes == [] and notices == []
    assert read_md(home) == after_first
    assert after_first.count(BEGIN) == 1
    assert len(backups(home)) == 1


def test_a_line_that_mentions_the_marker_is_not_one(install_module, tmp_path):
    # Story 2 (graphify #2062: a substring match): only a whole line is a marker. Story 14:
    # trailing whitespace on a marker line is ignored.
    home = tmp_path / "home"
    note = f"Note: `{BEGIN}` starts the installer's part.\n"
    write_md(home, note)
    install_module.install(home)
    assert read_md(home) == note + "\n" + SECTION
    write_md(home, note + "\n" + SECTION.replace(BEGIN, BEGIN + "  \t").replace(END, END + " "))
    changes, _ = install_module.install(home)
    assert not any("CLAUDE.md" in c for c in changes), changes


BROKEN = [
    pytest.param(f"mine\n{BEGIN}\n- a\n", id="begin-only"),
    pytest.param(f"mine\n- a\n{END}\n", id="end-only"),
    pytest.param(SECTION + SECTION, id="two-sections"),
    pytest.param(f"{END}\n- a\n{BEGIN}\n", id="reversed"),
]


@pytest.mark.parametrize("text", BROKEN)
def test_broken_markers_stop_install_before_any_write(install_module, tmp_path, capsys, text):
    # Story 3: guessing where a broken section ends could delete the user's text.
    home = tmp_path / "home"
    write_md(home, text)
    assert install_module.main(["--home", str(home)]) == 1
    err = capsys.readouterr().err
    assert "marker" in err and "nothing written" in err
    assert read_md(home) == text
    assert sorted(p.name for p in (home / ".claude").iterdir()) == ["CLAUDE.md"]


@pytest.mark.parametrize("text", BROKEN)
def test_broken_markers_stop_uninstall_before_any_write(install_module, uninstall_module, tmp_path, text):
    home = tmp_path / "home"
    install_module.install(home)
    settings = (home / ".claude" / "settings.json").read_bytes()
    write_md(home, text)
    ok, issues, _ = install_module.verify(home)
    assert not ok and any("marker" in i for i in issues), issues
    with pytest.raises(ValueError, match="marker"):
        uninstall_module.uninstall(home)
    assert read_md(home) == text
    assert (home / ".claude" / "settings.json").read_bytes() == settings


def test_old_whole_file_install_is_migrated(install_module, tmp_path):
    # Story 4: every existing user re-runs install over a file that is the rules, unmarked.
    home = tmp_path / "home"
    old_install(install_module, home, before="my own rules\n")
    changes, _ = install_module.install(home)
    assert read_md(home) == SECTION
    assert not any("backup" in c for c in changes), changes
    entry = read_record(home)["claude_md"]
    assert entry["format"] == "section"
    assert entry["legacy_backup"] == OLD_BACKUP
    assert entry["created"] is False


def test_uninstall_after_migration_restores_the_old_backup(install_module, uninstall_module, tmp_path):
    # Story 5: the backup the whole-file install made must still come back.
    home = tmp_path / "home"
    old_install(install_module, home, before="my own rules\n")
    install_module.install(home)
    changes, notices = uninstall_module.uninstall(home)
    assert f"CLAUDE.md restored from {OLD_BACKUP}" in changes, (changes, notices)
    assert read_md(home) == "my own rules\n"
    assert backups(home) == []


def test_uninstall_after_migrating_a_file_the_old_install_created_deletes_it(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    old_install(install_module, home)
    install_module.install(home)
    assert read_record(home)["claude_md"]["created"] is True
    uninstall_module.uninstall(home)
    assert not md(home).exists()


def test_old_install_edited_by_the_user_is_wrapped_not_duplicated(install_module, uninstall_module, tmp_path):
    # Story 4, second half: the user added a line under the old whole-file install. Appending
    # would leave the rules twice; the unmarked copy is the installer's own and is wrapped.
    home = tmp_path / "home"
    old_install(install_module, home, before="mine\n")
    write_md(home, RULES + "- my extra rule\n")
    install_module.install(home)
    assert read_md(home) == SECTION + "- my extra rule\n"
    _, notices = uninstall_module.uninstall(home)
    assert read_md(home) == "- my extra rule\n"
    assert any(OLD_BACKUP in n for n in notices), notices


def test_a_hand_copied_rules_file_is_wrapped_and_given_back_unchanged(install_module, uninstall_module, tmp_path):
    # The manual install used to say "copy config/CLAUDE.md": the copy is wrapped in markers
    # rather than duplicated, and uninstall takes only the marker lines away again.
    home = tmp_path / "home"
    write_md(home, "mine\n" + RULES)
    install_module.install(home)
    assert read_md(home) == "mine\n" + SECTION
    uninstall_module.uninstall(home)
    assert read_md(home) == "mine\n" + RULES
    assert backups(home) == []


@pytest.mark.parametrize("before", ["mine\n", "mine", "mine\n\n\n", "# H\r\n- a\r\n", "", "   \n"])
def test_install_then_uninstall_restores_user_text_byte_for_byte(install_module, uninstall_module, tmp_path, before):
    # Story 6: the blank line install adds must go too, or every cycle grows the file. Story 10:
    # a file that existed (even empty) is kept. The install's backup equals the result and goes.
    home = tmp_path / "home"
    write_md(home, before)
    install_module.install(home)
    uninstall_module.uninstall(home)
    assert read_md(home) == before
    assert backups(home) == []


def test_crlf_file_keeps_crlf_and_stays_idempotent(install_module, tmp_path):
    # Story 7: LF section lines in a CRLF file compared as "edited" on the next run.
    home = tmp_path / "home"
    write_md(home, "a\r\nb\r\n")
    install_module.install(home)
    assert read_md(home) == "a\r\nb\r\n\r\n" + SECTION.replace("\n", "\r\n")
    changes, _ = install_module.install(home)
    assert changes == []
    ok, issues, _ = install_module.verify(home)
    assert ok, issues


def edit_section(home):
    text = read_md(home)
    first_rule = next(line for line in RULES.splitlines() if line.startswith("- "))
    write_md(home, text.replace(first_rule, "- my tweak", 1))
    return read_md(home)


def test_edited_section_is_backed_up_before_replace(install_module, tmp_path):
    # Story 8: an edit inside the section was silently overwritten.
    home = tmp_path / "home"
    write_md(home, "mine\n")
    install_module.install(home)
    edited = edit_section(home)
    before = set(backups(home))
    changes, notices = install_module.install(home)
    assert read_md(home) == "mine\n\n" + SECTION
    new = set(backups(home)) - before
    assert len(new) == 1
    name = new.pop()
    assert (home / ".claude" / name).read_text(encoding="utf-8") == edited
    assert any(name in n for n in notices), notices


def test_uninstall_leaves_an_edited_section(install_module, uninstall_module, tmp_path):
    # Story 9.
    home = tmp_path / "home"
    write_md(home, "mine\n")
    install_module.install(home)
    edited = edit_section(home)
    _, notices = uninstall_module.uninstall(home)
    assert read_md(home) == edited
    assert any("section" in n and "left as is" in n for n in notices), notices
    assert read_record(home)["claude_md"]["format"] == "section"


def test_uninstall_deletes_only_a_file_install_created(install_module, uninstall_module, tmp_path):
    # Story 10.
    created = tmp_path / "created"
    install_module.install(created)
    uninstall_module.uninstall(created)
    assert not md(created).exists()
    empty = tmp_path / "empty"
    write_md(empty, "")
    install_module.install(empty)
    uninstall_module.uninstall(empty)
    assert md(empty).exists() and read_md(empty) == ""


def test_verify_ignores_user_text_outside_the_section(install_module, tmp_path):
    # Story 12.
    home = tmp_path / "home"
    write_md(home, "mine\n")
    install_module.install(home)
    write_md(home, read_md(home) + "- added later\n")
    ok, issues, _ = install_module.verify(home)
    assert ok, issues


def test_verify_fails_without_a_section(install_module, tmp_path):
    home = tmp_path / "home"
    install_module.install(home)
    write_md(home, RULES)
    ok, issues, _ = install_module.verify(home)
    assert not ok and any("section" in i for i in issues), issues


def test_section_without_final_newline_is_ours(install_module, uninstall_module, tmp_path):
    # Story 13.
    home = tmp_path / "home"
    write_md(home, "mine\n")
    install_module.install(home)
    write_md(home, read_md(home).rstrip("\n"))
    changes, _ = install_module.install(home)
    assert not any("CLAUDE.md" in c for c in changes), changes
    uninstall_module.uninstall(home)
    assert read_md(home) == "mine\n"


def test_text_added_after_the_section_is_kept_and_not_glued(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    write_md(home, "mine")
    install_module.install(home)
    write_md(home, read_md(home) + "later\n")
    uninstall_module.uninstall(home)
    assert read_md(home) == "mine\n\nlater\n"


def test_non_utf8_text_outside_the_section_is_not_rewritten(install_module, uninstall_module, tmp_path):
    # Uninstall decodes CLAUDE.md with replacement characters so a stray byte cannot block it;
    # writing that text back would turn the byte into U+FFFD. Such a file is left as is.
    home = tmp_path / "home"
    write_md(home, "mine\n")
    install_module.install(home)
    raw = md(home).read_bytes().replace(b"mine", b"caf\xe9")
    md(home).write_bytes(raw)
    _, notices = uninstall_module.uninstall(home)
    assert md(home).read_bytes() == raw
    assert any("CLAUDE.md" in n and "UTF-8" in n for n in notices), notices


def test_without_a_record_a_section_equal_to_the_template_is_removed_with_a_copy(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    write_md(home, "mine\n")
    install_module.install(home)
    record_path(home).unlink()
    for name in backups(home):
        (home / ".claude" / name).unlink()
    uninstall_module.uninstall(home)
    assert BEGIN not in read_md(home) and "mine" in read_md(home)
    assert len(backups(home)) == 1


@pytest.mark.parametrize("legacy", [OLD_BACKUP, 1, "../x.bak", "sub/x.bak"])
def test_a_missing_or_unusable_legacy_backup_keeps_the_file(install_module, uninstall_module, tmp_path, legacy):
    # After the migration only the section is left; removing it would leave the user without
    # the file the whole-file install moved aside, so the file stays and the record keeps it.
    home = tmp_path / "home"
    old_install(install_module, home, before="mine\n")
    install_module.install(home)
    (home / ".claude" / OLD_BACKUP).unlink()
    record = read_record(home)
    record["claude_md"]["legacy_backup"] = legacy
    record_path(home).write_text(json.dumps(record), encoding="utf-8")
    changes, notices = uninstall_module.uninstall(home)
    assert read_md(home) == SECTION
    assert not any("CLAUDE.md" in c for c in changes), changes
    assert any("left as is" in n and "missing" in n for n in notices), notices
    assert read_record(home)["claude_md"]["legacy_backup"] == legacy


def test_dry_run_names_the_section_and_writes_nothing(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    write_md(home, "mine\n")
    install_module.install(home)
    installed = read_md(home)
    changes, _ = uninstall_module.uninstall(home, dry_run=True)
    assert "CLAUDE.md: Ideal-Umbrella section removed" in changes
    assert read_md(home) == installed
    assert len(backups(home)) == 1
