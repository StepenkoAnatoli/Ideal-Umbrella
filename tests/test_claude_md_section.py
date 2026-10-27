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


FENCED = [
    pytest.param("# Mine\n\nExample:\n```markdown\n" + BEGIN + "\n- example A\n" + END + "\n```\n- more\n", id="backticks"),
    pytest.param("~~~\n" + BEGIN + "\n- example A\n" + END + "\n~~~\n", id="tildes"),
    pytest.param("````md\n```\n" + BEGIN + "\n- a\n" + END + "\n```\n````\n", id="longer-fence-holds-a-shorter-one"),
    pytest.param("  ```\n" + BEGIN + "\n- a\n```\n", id="begin-only-inside-a-fence"),
    # Review 2, finding 2b: a ``` fence never closed used to hide the ~~~ fence after it.
    pytest.param("notes\n```\nstray\n\nExample:\n~~~\n" + BEGIN + "\n- example A\n" + END + "\n~~~\n",
                 id="a-fence-never-closed-before-a-fenced-example"),
]


@pytest.mark.parametrize("before", FENCED)
def test_marker_lines_inside_a_code_fence_are_an_example_not_the_section(install_module, uninstall_module, tmp_path, before):
    # Review 1, finding 1: a fenced example of the managed block was taken for the section,
    # replaced with the rules, and then removed by uninstall, losing the example lines.
    home = tmp_path / "home"
    write_md(home, before)
    install_module.install(home)
    assert read_md(home) == before + "\n" + SECTION
    ok, issues, _ = install_module.verify(home)
    assert ok, issues
    changes, _ = install_module.install(home)
    assert changes == []
    uninstall_module.uninstall(home)
    assert read_md(home) == before
    assert backups(home) == []


def test_a_fence_never_closed_does_not_hide_the_section(install_module, tmp_path):
    # An opening fence line with no closing one would, read as Markdown, run to the end of the
    # file and swallow the section install appends; then every run would append another.
    home = tmp_path / "home"
    write_md(home, "mine\n```\nstray\n")
    install_module.install(home)
    changes, _ = install_module.install(home)
    assert changes == []
    assert read_md(home).count(BEGIN) == 1


def test_a_hand_wrapped_old_install_is_migrated_and_undone(install_module, uninstall_module, tmp_path):
    # Review 1, finding 2: a user of the whole-file installer put the markers around the rules
    # by hand (the new manual install step). The record kept the whole-file format, so
    # uninstall refused and the file the old install moved aside stayed in its backup.
    home = tmp_path / "home"
    old_install(install_module, home, before="my own rules\n")
    write_md(home, SECTION)
    install_module.install(home)
    assert read_md(home) == SECTION
    entry = read_record(home)["claude_md"]
    assert entry["format"] == "section" and entry["legacy_backup"] == OLD_BACKUP
    assert install_module.install(home) == ([], [])
    uninstall_module.uninstall(home)
    assert read_md(home) == "my own rules\n"
    assert backups(home) == []


def test_a_hand_wrapped_old_install_that_created_the_file_is_deleted(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    old_install(install_module, home)
    write_md(home, SECTION)
    install_module.install(home)
    assert read_record(home)["claude_md"]["created"] is True
    uninstall_module.uninstall(home)
    assert not md(home).exists()


BOM = "﻿"


def test_a_bom_before_the_section_is_kept(install_module, uninstall_module, tmp_path):
    # Review 1, finding 3: the BOM was dropped when the begin marker was line 1.
    home = tmp_path / "home"
    install_module.install(home)
    write_md(home, BOM + read_md(home) + "my text\n")
    edit_section(home)
    install_module.install(home)
    assert read_md(home) == BOM + SECTION + "my text\n"
    uninstall_module.uninstall(home)
    assert read_md(home) == BOM + "my text\n"


def test_a_created_file_holding_a_bom_and_the_section_is_deleted(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    install_module.install(home)
    write_md(home, BOM + read_md(home))
    uninstall_module.uninstall(home)
    assert not md(home).exists()


def test_a_hand_copy_after_a_bom_is_wrapped_not_added_again(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    write_md(home, BOM + RULES)
    install_module.install(home)
    assert read_md(home) == BOM + SECTION
    uninstall_module.uninstall(home)
    assert read_md(home) == BOM + RULES
    assert backups(home) == []


def test_removing_only_the_marker_lines_keeps_the_rules_ours(install_module, uninstall_module, tmp_path):
    # Review 1, finding 6: the rules the install added were wrapped as the user's own on the
    # next run, so uninstall left them, and a second backup was made and never removed.
    home = tmp_path / "home"
    write_md(home, "mine\n")
    install_module.install(home)
    write_md(home, read_md(home).replace(BEGIN + "\n", "").replace(END + "\n", ""))
    install_module.install(home)
    assert read_md(home) == "mine\n\n" + SECTION
    assert len(backups(home)) == 1
    uninstall_module.uninstall(home)
    assert read_md(home) == "mine\n"
    assert backups(home) == []


def test_a_new_backup_before_the_section_is_added_again_is_the_one_recorded(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    write_md(home, "mine\n")
    install_module.install(home)
    first = backups(home)
    write_md(home, "mine\nmore\n")   # the user deleted the whole section and wrote more
    install_module.install(home)
    uninstall_module.uninstall(home)
    assert read_md(home) == "mine\nmore\n"
    assert backups(home) == first   # the newer backup equals the file again and goes


def test_a_failed_write_after_the_backup_leaves_no_orphan_backup(install_module, uninstall_module, tmp_path, monkeypatch):
    # Review 1, finding 7: the rerun made a second backup and recorded only that one.
    home = tmp_path / "home"
    write_md(home, "mine\n")
    real = install_module._write_bytes

    def failing(path, data):
        if path.name == "CLAUDE.md":
            raise OSError(28, "No space left on device")
        real(path, data)
    monkeypatch.setattr(install_module, "_write_bytes", failing)
    with pytest.raises(OSError):
        install_module.install(home)
    monkeypatch.setattr(install_module, "_write_bytes", real)
    install_module.install(home)
    assert len(backups(home)) == 1
    uninstall_module.uninstall(home)
    assert read_md(home) == "mine\n"
    assert backups(home) == []


def test_uninstall_reports_an_edited_section_this_install_did_not_write(install_module, uninstall_module, tmp_path):
    # Review 1, finding 8: the record has no CLAUDE.md entry (the section was already there),
    # and the user edited it: uninstall said nothing.
    home = tmp_path / "home"
    write_md(home, "mine\n\n" + SECTION)
    install_module.install(home)
    assert "claude_md" not in read_record(home)
    edited = edit_section(home)
    _, notices = uninstall_module.uninstall(home)
    assert read_md(home) == edited
    assert any("section" in n and "left as is" in n for n in notices), notices


def test_an_old_install_saved_with_a_bom_is_migrated_and_undone(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    old_install(install_module, home, before="mine\n")
    write_md(home, BOM + RULES)
    install_module.install(home)
    assert read_md(home) == BOM + SECTION
    uninstall_module.uninstall(home)
    assert read_md(home) == "mine\n"
    assert backups(home) == []


@pytest.mark.parametrize("before", [
    pytest.param("# Mine\n```\n" + RULES + "```\nend\n", id="rules"),
    pytest.param("# Mine\n~~~\n" + BEGIN + "\n" + RULES + END + "\n~~~\nend\n", id="rules-with-markers"),
])
def test_a_fenced_copy_of_the_rules_is_an_example_not_wrapped(install_module, uninstall_module, tmp_path, before):
    # Review 2, finding 1: the wrap path looked for an unmarked copy of the rules with no
    # notion of fences, so every install added another marker pair inside the user's example.
    home = tmp_path / "home"
    write_md(home, before)
    install_module.install(home)
    assert read_md(home) == before + "\n" + SECTION
    assert install_module.install(home) == ([], [])
    ok, issues, _ = install_module.verify(home)
    assert ok, issues
    uninstall_module.uninstall(home)
    assert read_md(home) == before
    assert backups(home) == []


def test_a_fence_closed_only_after_the_section_does_not_hide_it(install_module, uninstall_module, tmp_path):
    # Review 2, finding 2a: a stray fence line before the section paired with a code block the
    # user added after it, so the section looked fenced: every install appended another one,
    # and uninstall could not find any.
    home = tmp_path / "home"
    write_md(home, "mine\n```\nstray\n")
    install_module.install(home)
    later = "```\ncode\n```\n"
    write_md(home, read_md(home) + later)
    assert install_module.install(home) == ([], [])
    ok, issues, warnings = install_module.verify(home)
    assert ok, issues
    assert any("code fence" in w for w in warnings), warnings
    # Review 3, finding 3: the same text is also what a fenced example of the section looks
    # like after the live one is deleted, so uninstall leaves it and says how to finish.
    _, notices = uninstall_module.uninstall(home)
    assert read_md(home) == "mine\n```\nstray\n\n" + SECTION + later
    assert any("code fence" in n and "line 5" in n for n in notices), notices
    assert read_record(home)["claude_md"]["format"] == "section"
    write_md(home, "mine\n```\nstray\n```\n\n" + SECTION + later)   # the fence closed by hand
    uninstall_module.uninstall(home)
    assert read_md(home) == "mine\n```\nstray\n```\n\n" + later


def test_a_fenced_example_of_the_section_is_never_taken_for_it(install_module, uninstall_module, tmp_path):
    # Review 3, finding 3: the user keeps the installed block as a fenced example and deletes
    # the live section. Its body hashes to the record, so the fallback for a section that only
    # looks fenced took it, and uninstall deleted the user's example.
    home = tmp_path / "home"
    write_md(home, "mine\n")
    install_module.install(home)
    user = "mine\n\nThe block the installer adds looks like this:\n\n```markdown\n" + SECTION + "```\n"
    write_md(home, user)
    assert install_module.install(home) == ([], [])
    ok, issues, warnings = install_module.verify(home)
    assert any("code fence" in w for w in warnings), warnings
    _, notices = uninstall_module.uninstall(home)
    assert read_md(home) == user
    assert any("code fence" in n for n in notices), notices


def test_a_template_change_does_not_rewrite_a_fenced_section(install_module, tmp_path, monkeypatch):
    home = tmp_path / "home"
    write_md(home, "mine\n")
    install_module.install(home)
    user = "mine\n\n```markdown\n" + SECTION + "```\n"
    write_md(home, user)
    record = record_path(home).read_bytes()
    new_md = tmp_path / "CLAUDE.md"
    new_md.write_bytes((RULES + "- a rule added later\n").encode("utf-8"))
    monkeypatch.setattr(install_module, "CLAUDE_MD", new_md)
    with pytest.raises(ValueError, match="code fence"):
        install_module.install(home)
    assert read_md(home) == user
    assert record_path(home).read_bytes() == record


def test_a_wrapped_copy_stays_the_users_after_the_template_changes(install_module, uninstall_module, tmp_path, monkeypatch):
    # Review 2, finding 3: the record lost "wrapped" when the section was updated, so uninstall
    # then removed the user's own copy of the rules, and no message named the backup holding it.
    home = tmp_path / "home"
    write_md(home, "# My notes\n" + RULES + "more of mine\n")
    install_module.install(home)
    safety = read_record(home)["claude_md"]["safety_backup"]
    new_md = tmp_path / "CLAUDE.md"
    new_md.write_bytes((RULES + "- a rule added later\n").encode("utf-8"))
    monkeypatch.setattr(install_module, "CLAUDE_MD", new_md)
    monkeypatch.setattr(uninstall_module.install, "CLAUDE_MD", new_md)
    _, notices = install_module.install(home)
    assert read_record(home)["claude_md"]["wrapped"] is True
    assert any(safety in n for n in notices), notices
    uninstall_module.uninstall(home)
    assert read_md(home) == "# My notes\n" + RULES + "- a rule added later\nmore of mine\n"


# Review 4, info C (M8): a name that starts like ours and goes on is the user's too.
@pytest.mark.parametrize("name", ["CLAUDE.md.bak-before-trying-it", "CLAUDE.md.bak-20250101-000000-mine"])
def test_a_backup_the_user_named_is_never_taken_for_ours(install_module, uninstall_module, tmp_path, name):
    # Review 2, finding 8: any <name>.bak-* with the same bytes was reused, then deleted.
    home = tmp_path / "home"
    write_md(home, "mine\n")
    own = home / ".claude" / name
    own.write_bytes(b"mine\n")
    install_module.install(home)
    assert read_record(home)["claude_md"]["safety_backup"] != own.name
    uninstall_module.uninstall(home)
    assert read_md(home) == "mine\n"
    assert own.read_bytes() == b"mine\n"


def test_uninstall_names_the_legacy_backup_when_claude_md_is_gone(install_module, uninstall_module, tmp_path):
    # Review 2, info 1: the record entry was dropped in silence, orphaning the user's old file.
    home = tmp_path / "home"
    old_install(install_module, home, before="mine\n")
    install_module.install(home)
    md(home).unlink()
    _, notices = uninstall_module.uninstall(home)
    assert any(OLD_BACKUP in n for n in notices), notices


def test_an_old_install_that_created_the_file_and_was_wrapped_is_deleted(install_module, uninstall_module, tmp_path):
    # Review 2, info 5: the old-format wrap path said created=False whatever the old record said.
    home = tmp_path / "home"
    old_install(install_module, home)
    write_md(home, RULES + "\n")
    install_module.install(home)
    assert read_record(home)["claude_md"]["created"] is True
    uninstall_module.uninstall(home)
    assert not md(home).exists()


def test_a_failed_restore_of_the_legacy_backup_keeps_both_files(install_module, uninstall_module, tmp_path, monkeypatch):
    # Review 2, info 3: no test made this write fail (the one named for it patched a copy that
    # no longer happens).
    import os
    home = tmp_path / "home"
    old_install(install_module, home, before="my own rules\n")
    install_module.install(home)
    real_replace = os.replace

    def failing_replace(src, dst, *args, **kwargs):
        if str(dst).endswith("CLAUDE.md"):
            raise OSError(28, "No space left on device")
        return real_replace(src, dst, *args, **kwargs)
    monkeypatch.setattr(os, "replace", failing_replace)
    with pytest.raises(OSError):
        uninstall_module.uninstall(home)
    assert read_md(home) == SECTION
    assert (home / ".claude" / OLD_BACKUP).read_bytes() == b"my own rules\n"


def test_a_hand_copy_wrapped_again_after_its_marker_lines_were_deleted_stays_the_users(
        install_module, uninstall_module, tmp_path):
    # Review 3, finding 1: the wrap path set "wrapped" from "is there a record" alone, so the
    # second wrap of the user's own copy recorded it as the installer's and uninstall removed it.
    home = tmp_path / "home"
    before = "my notes\n\n" + RULES
    write_md(home, before)
    install_module.install(home)
    write_md(home, before)   # the user deletes the two marker lines
    install_module.install(home)
    assert read_record(home)["claude_md"]["wrapped"] is True
    uninstall_module.uninstall(home)
    assert read_md(home) == before


def test_a_long_fence_with_only_shorter_closers_is_ordinary_text(install_module):
    # A ```` line is closed only by a fence of four or more; with none after it, it is text.
    text = "````\n```\n" + SECTION
    assert install_module.find_section(text) is not None


@pytest.mark.parametrize("later, after", [
    pytest.param(None, None, id="file-deleted"),
    pytest.param("other\n", "other\n", id="file-rewritten"),
])
def test_a_new_section_after_a_wrapped_copy_is_the_installers(install_module, uninstall_module, tmp_path,
                                                             later, after):
    # The wrapped copy is gone with the file it was in; the section the next install writes is
    # the installer's, so uninstall takes it away (and the file, when install created it).
    home = tmp_path / "home"
    write_md(home, "my notes\n\n" + RULES)
    install_module.install(home)
    if later is None:
        md(home).unlink()
    else:
        write_md(home, later)
    install_module.install(home)
    assert "wrapped" not in read_record(home)["claude_md"]
    uninstall_module.uninstall(home)
    assert (read_md(home) if md(home).exists() else None) == after


# Review 4, finding A: joined was stripped only as the exact bytes recorded, so a file whose
# line endings an editor or git changed after the install kept a lone CR or a blank line.
@pytest.mark.parametrize("before, convert, after", [
    ("mine\n", ("\n", "\r\n"), b"mine\r\n"),
    ("mine", ("\n", "\r\n"), b"mine"),
    ("mine\r\n", ("\r\n", "\n"), b"mine\n"),
    ("a\r\nb", ("\r\n", "\n"), b"a\nb"),
])
def test_line_endings_changed_after_install_leave_no_trace_on_uninstall(install_module, uninstall_module, tmp_path,
                                                                        before, convert, after):
    home = tmp_path / "home"
    write_md(home, before)
    install_module.install(home)
    write_md(home, read_md(home).replace(*convert))
    _, notices = uninstall_module.uninstall(home)
    assert md(home).read_bytes() == after
    if after == before.encode("utf-8"):
        assert backups(home) == []
        return
    # The copy from before the install no longer equals the file, so it is kept, and named
    # (review 4, info E1).
    assert len(backups(home)) == 1
    assert any(backups(home)[0] in n for n in notices), notices


def test_a_safety_backup_kept_after_the_user_edited_their_own_text_is_named(install_module, uninstall_module,
                                                                            tmp_path):
    # Review 4, info E1: the backup was kept, correctly, but no notice said it was there.
    home = tmp_path / "home"
    write_md(home, "mine\n")
    install_module.install(home)
    write_md(home, "mine, edited\n" + read_md(home)[len("mine\n"):])
    _, notices = uninstall_module.uninstall(home)
    assert read_md(home) == "mine, edited\n"
    assert any(backups(home)[0] in n for n in notices), notices


def test_a_backup_keeps_the_time_of_the_file_it_copies(install_module, tmp_path):
    # Review 4, info C (M6): nothing checked that the backup keeps the file's time.
    import os
    home = tmp_path / "home"
    write_md(home, "mine\n")
    os.utime(md(home), (1_000_000_000, 1_000_000_000))
    install_module.install(home)
    backup = home / ".claude" / read_record(home)["claude_md"]["safety_backup"]
    assert int(backup.stat().st_mtime) == 1_000_000_000


def test_verify_reads_a_record_that_is_still_pending(install_module, tmp_path):
    # Review 4, info C (M22): no test ran verify against a record with "pending". Here the
    # record's own entry names a section that never landed; the earlier entry names the one
    # on disk, which only the hash finds (a stray fence line above it).
    home = tmp_path / "home"
    write_md(home, "mine\n```\nstray\n")
    install_module.install(home)
    write_md(home, read_md(home) + "```\ncode\n```\n")
    record = read_record(home)
    record["pending"] = json.loads(json.dumps(record))
    record["claude_md"]["sha256"] = "0" * 64
    record_path(home).write_text(json.dumps(record), encoding="utf-8")
    ok, issues, warnings = install_module.verify(home)
    assert not any("no Ideal-Umbrella section" in i for i in issues), issues
    assert any("code fence" in w for w in warnings), warnings


@pytest.mark.parametrize("template_change", [False, True])
def test_an_edited_backup_left_by_a_failed_write_goes_with_uninstall(install_module, uninstall_module, tmp_path,
                                                                     monkeypatch, template_change):
    # Review 4, finding D: the user edits the section and installs again; the backup of the
    # edited file is made, then the CLAUDE.md write fails. No record named that backup, so
    # uninstall left it, a copy of CLAUDE.md that nothing mentions.
    home = tmp_path / "home"
    write_md(home, "mine\n")
    install_module.install(home)
    safety = read_record(home)["claude_md"]["safety_backup"]
    edited = edit_section(home)
    if template_change:
        path = tmp_path / "CLAUDE.md"
        path.write_bytes((RULES + "- a rule added later\n").encode("utf-8"))
        monkeypatch.setattr(install_module, "CLAUDE_MD", path)
    real_write = install_module._write_bytes

    def failing(path, data):
        if path == md(home):
            raise OSError(28, "No space left on device")
        real_write(path, data)
    monkeypatch.setattr(install_module, "_write_bytes", failing)
    with pytest.raises(OSError):
        install_module.install(home)
    monkeypatch.setattr(install_module, "_write_bytes", real_write)
    assert len(backups(home)) == 2
    uninstall_module.uninstall(home)
    assert read_md(home) == edited
    assert backups(home) == [safety]
