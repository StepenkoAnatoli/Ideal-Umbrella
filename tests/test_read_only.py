"""A read-only file must not leave an install or an uninstall half done.

Review 6 of the graphify branch, finding L1: install refused a read-only CLAUDE.md only at its
write, after the record, the hook and a backup were written; the backup copied the read-only
mode, and on Windows, where a read-only file cannot be deleted, every uninstall then stopped at
that backup. Windows is simulated here (os.access says a file without the write bit is not
writable, and unlink refuses it), so the tests also run as root, where a real chmod is ignored.
"""
import hashlib
import json
import os
import pathlib
import stat

import pytest

from conftest import ROOT, load_module

# The rules with LF line ends: a Windows checkout may give config/CLAUDE.md CRLF.
RULES = (ROOT / "config" / "CLAUDE.md").read_bytes().replace(b"\r\n", b"\n")


@pytest.fixture
def windows_read_only(monkeypatch, tmp_path):
    real_access, real_unlink = os.access, pathlib.Path.unlink

    def access(path, mode, *args, **kwargs):
        if mode & os.W_OK and os.path.isfile(path) and not os.stat(path).st_mode & stat.S_IWUSR:
            return False
        return real_access(path, mode, *args, **kwargs)

    def unlink(self, *args, **kwargs):
        if self.is_file() and not self.is_symlink() and not self.stat().st_mode & stat.S_IWUSR:
            raise PermissionError(13, "Access is denied", str(self))
        return real_unlink(self, *args, **kwargs)
    monkeypatch.setattr(os, "access", access)
    monkeypatch.setattr(pathlib.Path, "unlink", unlink)
    yield
    for path in tmp_path.rglob("*"):
        if path.is_file() and not path.is_symlink():
            path.chmod(path.stat().st_mode | stat.S_IWUSR)


@pytest.fixture
def uninstall_module():
    return load_module("uninstall_module", "config/uninstall.py")


def claude(home):
    return home / ".claude"


def snapshot(folder):
    return {p.relative_to(folder): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def read_only(path):
    path.chmod(path.stat().st_mode & ~0o222)


def every_file_needs_a_write(inst, home, tmp_path, monkeypatch):
    """An install, then a change to both templates and to the hook file, so the next run writes
    the record, the hook, CLAUDE.md and settings.json."""
    claude(home).mkdir(parents=True)
    (claude(home) / "CLAUDE.md").write_bytes(b"mine\n")
    inst.install(home)
    template = tmp_path / "CLAUDE-template.md"
    template.write_bytes(RULES + b"- a rule added later\n")
    monkeypatch.setattr(inst, "CLAUDE_MD", template)
    settings = json.loads(inst.USER_SETTINGS.read_text(encoding="utf-8"))
    settings["autoCompactWindow"] = 123456
    (tmp_path / "user-settings.json").write_text(json.dumps(settings), encoding="utf-8")
    monkeypatch.setattr(inst, "USER_SETTINGS", tmp_path / "user-settings.json")
    (claude(home) / "ballast" / "context_check.py").write_bytes(b"# an older hook\n")


@pytest.mark.parametrize("name", ["CLAUDE.md", "settings.json", "ballast/context_check.py",
                                  "ballast/install-record.json"])
def test_a_read_only_file_stops_install_before_any_write(install_module, windows_read_only, tmp_path,
                                                         monkeypatch, name):
    home = tmp_path / "home"
    every_file_needs_a_write(install_module, home, tmp_path, monkeypatch)
    read_only(claude(home) / name)
    before = snapshot(home)
    with pytest.raises(PermissionError, match="read-only"):
        install_module.install(home)
    assert snapshot(home) == before


@pytest.mark.parametrize("name", ["CLAUDE.md", "settings.json", "ballast/context_check.py"])
def test_a_read_only_file_with_nothing_to_write_does_not_stop_install(install_module, windows_read_only, tmp_path,
                                                                      name):
    # Review 7, finding L3: only a read-only file the run would write is refused.
    home = tmp_path / "home"
    install_module.install(home)
    read_only(claude(home) / name)
    assert install_module.install(home) == ([], [])


def test_a_read_only_claude_md_does_not_stop_install_when_only_the_record_changes(install_module, windows_read_only,
                                                                                 tmp_path):
    # Review 7, finding L3 (p05): the user put the markers around the whole-file install by hand,
    # so the record moves to the section format and CLAUDE.md is not written.
    home = tmp_path / "home"
    install_module.install(home)
    md = claude(home) / "CLAUDE.md"
    record_path = claude(home) / "ballast" / "install-record.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["claude_md"] = {"backup": None, "sha256": hashlib.sha256(RULES).hexdigest()}
    record_path.write_text(json.dumps(record), encoding="utf-8")
    before = md.read_bytes()
    read_only(md)
    changes, _ = install_module.install(home)
    assert changes == ["CLAUDE.md section recorded"]
    assert md.read_bytes() == before
    assert json.loads(record_path.read_text(encoding="utf-8"))["claude_md"]["format"] == "section"


def test_a_backup_of_a_read_only_file_can_be_deleted(install_module, windows_read_only, tmp_path):
    source = tmp_path / "CLAUDE.md"
    source.write_bytes(b"mine\n")
    read_only(source)
    backup = install_module._backup(source)
    assert backup.read_bytes() == b"mine\n"
    assert backup.stat().st_mode & stat.S_IWUSR


@pytest.mark.parametrize("kind", ["safety", "legacy"])
def test_uninstall_deletes_a_read_only_backup_of_its_own(install_module, uninstall_module, windows_read_only,
                                                         tmp_path, kind):
    # A backup made read-only by an earlier version (copystat), by the user or by a sync tool.
    home = tmp_path / "home"
    claude(home).mkdir(parents=True)
    (claude(home) / "CLAUDE.md").write_bytes(b"mine\n")
    install_module.install(home)
    if kind == "legacy":
        # The whole-file installer's state: CLAUDE.md is the rules, the user's file a backup.
        for path in claude(home).glob("CLAUDE.md.bak-*"):
            path.unlink()
        (claude(home) / "CLAUDE.md").write_bytes(RULES)
        (claude(home) / "CLAUDE.md.bak-20250101-000000").write_bytes(b"mine\n")
        record_path = claude(home) / "ballast" / "install-record.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["claude_md"] = {"backup": "CLAUDE.md.bak-20250101-000000",
                               "sha256": hashlib.sha256(RULES).hexdigest()}
        record_path.write_text(json.dumps(record), encoding="utf-8")
    for path in claude(home).glob("CLAUDE.md.bak-*"):
        read_only(path)
    uninstall_module.uninstall(home)
    assert (claude(home) / "CLAUDE.md").read_bytes() == b"mine\n"
    assert list(claude(home).glob("CLAUDE.md.bak-*")) == []
    assert uninstall_module.uninstall(home) == ([], [])


def test_a_read_only_settings_file_stops_add_to_repo_before_any_write(add_to_repo, windows_read_only, tmp_path):
    repo = tmp_path / "repo"
    (repo / ".claude").mkdir(parents=True)
    (repo / ".claude" / "settings.json").write_text("{}\n", encoding="utf-8")
    read_only(repo / ".claude" / "settings.json")
    before = snapshot(repo)
    with pytest.raises(PermissionError, match="read-only"):
        add_to_repo._add(str(repo), False)
    assert snapshot(repo) == before


def test_a_read_only_file_with_nothing_to_write_does_not_stop_add_to_repo(add_to_repo, windows_read_only, tmp_path):
    # Review 7, finding L3 (p09): a second run writes nothing, so its read-only files are fine.
    repo = tmp_path / "repo"
    repo.mkdir()
    add_to_repo._add(str(repo), False)
    written = [p for p in repo.rglob("*") if p.is_file()]
    assert len(written) == 3   # the hook, settings.json and notes/learnings.md
    for path in written:
        read_only(path)
    before = snapshot(repo)
    add_to_repo._add(str(repo), False)
    assert snapshot(repo) == before


@pytest.mark.parametrize("name", ["CLAUDE.md", "settings.json", "ballast/install-record.json"])
def test_an_uninstall_stopped_by_a_read_only_file_is_finished_once_it_is_writable(
        install_module, uninstall_module, windows_read_only, tmp_path, name):
    # Uninstall now refuses a read-only file before its first write (review 8, low 25); a stop
    # at the file must still be finished by a rerun once it is writable.
    home = tmp_path / "home"
    claude(home).mkdir(parents=True)
    (claude(home) / "CLAUDE.md").write_bytes(b"mine\n")
    (claude(home) / "settings.json").write_text('{"model": "opus"}\n', encoding="utf-8")
    install_module.install(home)
    read_only(claude(home) / name)
    with pytest.raises(PermissionError):
        uninstall_module.uninstall(home)
    (claude(home) / name).chmod(0o644)
    uninstall_module.uninstall(home)
    assert (claude(home) / "CLAUDE.md").read_bytes() == b"mine\n"
    assert json.loads((claude(home) / "settings.json").read_text(encoding="utf-8")) == {"model": "opus"}
    assert not (claude(home) / "ballast" / "context_check.py").exists()
    assert list(claude(home).glob("CLAUDE.md.bak-*")) == []
    assert uninstall_module.uninstall(home) == ([], [])


def test_a_file_another_user_owns_is_deleted_without_a_chmod(install_module, monkeypatch, tmp_path):
    # Review 7, finding L1: on Linux and macOS deleting a file needs write access to its folder
    # only. A log left by `sudo claude` is root's: os.access says it is not writable, and a chmod
    # of it fails with EPERM, so a chmod before the delete stopped every uninstall there.
    path = tmp_path / "context_check.log"
    path.write_bytes(b"log\n")
    real_access = os.access

    def access(p, mode, *args, **kwargs):
        return False if os.fspath(p) == os.fspath(path) and mode & os.W_OK else real_access(p, mode, *args, **kwargs)

    def chmod(*args, **kwargs):
        raise PermissionError(1, "Operation not permitted", str(path))
    monkeypatch.setattr(os, "access", access)
    monkeypatch.setattr(os, "chmod", chmod)
    install_module.remove(path)
    assert not path.exists()


def test_a_refused_delete_is_reported_when_the_chmod_fails_too(install_module, monkeypatch, tmp_path):
    # Review 8, info I1: a log another user owns in a folder that is not writable. The delete is
    # refused because of the folder; the error must say so, not the chmod's "not permitted".
    path = tmp_path / "context_check.log"
    path.write_bytes(b"log\n")
    real_access = os.access

    def access(p, mode, *args, **kwargs):
        return False if os.fspath(p) == os.fspath(path) and mode & os.W_OK else real_access(p, mode, *args, **kwargs)

    def unlink(self, *args, **kwargs):
        raise PermissionError(13, "Permission denied (the folder)", str(self))

    def chmod(*args, **kwargs):
        raise PermissionError(1, "Operation not permitted", str(path))
    monkeypatch.setattr(os, "access", access)
    monkeypatch.setattr(pathlib.Path, "unlink", unlink)
    monkeypatch.setattr(os, "chmod", chmod)
    with pytest.raises(PermissionError) as refused:
        install_module.remove(path)
    assert refused.value.errno == 13 and "the folder" in str(refused.value)


def test_a_writable_file_whose_delete_is_refused_is_never_chmodded(install_module, monkeypatch, tmp_path):
    # Review 8, mutant q04: a read-only bit is not why the delete failed, so a chmod cannot help,
    # and on POSIX it needs the file's owner.
    path = tmp_path / "context_check.log"
    path.write_bytes(b"log\n")
    chmodded = []

    def unlink(self, *args, **kwargs):
        raise PermissionError(13, "Permission denied (the folder)", str(self))
    monkeypatch.setattr(pathlib.Path, "unlink", unlink)
    monkeypatch.setattr(os, "chmod", lambda *args, **kwargs: chmodded.append(args))
    with pytest.raises(PermissionError) as refused:
        install_module.remove(path)
    assert "the folder" in str(refused.value) and chmodded == []


def test_a_read_only_file_that_still_cannot_be_deleted_keeps_its_mode(install_module, windows_read_only, monkeypatch,
                                                                       tmp_path):
    # Review 7, finding L1: a delete that fails for another reason (a read-only folder) must not
    # leave the file's read-only bit cleared.
    path = tmp_path / "CLAUDE.md.bak-20250101-000000"
    path.write_bytes(b"mine\n")
    read_only(path)
    mode = path.stat().st_mode
    real_unlink = pathlib.Path.unlink

    def unlink(self, *args, **kwargs):
        if self == path:
            raise PermissionError(13, "Access is denied", str(self))
        return real_unlink(self, *args, **kwargs)
    monkeypatch.setattr(pathlib.Path, "unlink", unlink)
    with pytest.raises(PermissionError):
        install_module.remove(path)
    assert path.stat().st_mode == mode


def test_a_symlinked_read_only_hook_is_removed_and_its_target_left_read_only(install_module, windows_read_only,
                                                                            tmp_path):
    target = tmp_path / "dotfiles" / "context_check.py"
    target.parent.mkdir()
    target.write_bytes(b"# hook\n")
    read_only(target)
    link = tmp_path / "context_check.py"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks need a privilege on this Windows")
    mode = target.stat().st_mode
    install_module.remove(link)
    assert not link.is_symlink() and target.exists()
    assert target.stat().st_mode == mode


def _record(home):
    return claude(home) / "ballast" / "install-record.json"


def _set_entry(home, entry):
    record = json.loads(_record(home).read_text(encoding="utf-8"))
    record["claude_md"] = entry
    _record(home).write_text(json.dumps(record), encoding="utf-8")


def _entry(home):
    return json.loads(_record(home).read_text(encoding="utf-8"))["claude_md"]


def _whole_file_install(inst, home):
    """The whole-file installer's state: CLAUDE.md is the rules, the user's file a backup."""
    claude(home).mkdir(parents=True)
    inst.install(home)
    (claude(home) / "CLAUDE.md").write_bytes(RULES)
    (claude(home) / "CLAUDE.md.bak-20250101-000000").write_bytes(b"mine\n")
    _set_entry(home, {"backup": "CLAUDE.md.bak-20250101-000000", "sha256": hashlib.sha256(RULES).hexdigest()})


def safety_same_bytes(inst, home):
    # The install made its safety backup, then stopped before its CLAUDE.md write.
    claude(home).mkdir(parents=True)
    (claude(home) / "CLAUDE.md").write_bytes(b"mine\n")
    inst.install(home)
    (claude(home) / "CLAUDE.md").write_bytes(b"mine\n")


def converted_whole_file(inst, home):
    # A whole-file install moved to the section format: uninstall restores the old file.
    _whole_file_install(inst, home)
    inst.install(home)
    assert _entry(home)["legacy_backup"] == "CLAUDE.md.bak-20250101-000000"


def converted_whole_file_restored(inst, home):
    # An uninstall restored the file from the legacy backup, then stopped before deleting it.
    converted_whole_file(inst, home)
    (claude(home) / "CLAUDE.md").write_bytes(b"mine\n")


def whole_file_restored(inst, home):
    # The same, for a record the whole-file installer wrote.
    _whole_file_install(inst, home)
    (claude(home) / "CLAUDE.md").write_bytes(b"mine\n")


def edited_same_bytes(inst, home):
    # The install backed up the user's edits to the section, then stopped before its write.
    claude(home).mkdir(parents=True)
    (claude(home) / "CLAUDE.md").write_bytes(b"mine\n")
    inst.install(home)
    md = claude(home) / "CLAUDE.md"
    md.write_bytes(md.read_bytes().replace(b"\n# ", b"\n# Edited: ", 1))
    (claude(home) / "CLAUDE.md.bak-20250101-000001").write_bytes(md.read_bytes())
    _set_entry(home, {**_entry(home), "edited_backup": "CLAUDE.md.bak-20250101-000001"})


@pytest.mark.parametrize("state", [safety_same_bytes, converted_whole_file, converted_whole_file_restored,
                                   whole_file_restored, edited_same_bytes])
def test_uninstall_deletes_read_only_files_of_its_own_in_every_branch(install_module, uninstall_module,
                                                                      windows_read_only, tmp_path, state):
    # Review 7, finding L3: every file uninstall deletes goes through install.remove(), so a
    # read-only bit on a backup, the hook or the log does not stop it on Windows.
    home = tmp_path / "home"
    state(install_module, home)
    (claude(home) / "ballast" / "context_check.log").write_bytes(b"log\n")
    names = sorted(p.name for p in claude(home).glob("CLAUDE.md.bak-*"))
    assert names
    for path in [*claude(home).glob("CLAUDE.md.bak-*"), claude(home) / "ballast" / "context_check.py",
                 claude(home) / "ballast" / "context_check.log"]:
        read_only(path)
    changes, _ = uninstall_module.uninstall(home)
    assert not (claude(home) / "ballast" / "context_check.py").exists()
    assert not (claude(home) / "ballast" / "context_check.log").exists()
    left = sorted(p.name for p in claude(home).glob("CLAUDE.md.bak-*"))
    if state is edited_same_bytes:
        # The section the user edited stays, and with it the copy from before the install.
        assert left == [n for n in names if n != "CLAUDE.md.bak-20250101-000001"] != [], changes
    else:
        assert left == [], changes
        assert (claude(home) / "CLAUDE.md").read_bytes() == b"mine\n"


def test_a_symlink_whose_delete_is_refused_never_has_its_target_chmodded(install_module, windows_read_only,
                                                                         monkeypatch, tmp_path):
    # Review 7, finding L3 (p03): os.chmod and os.access follow a symlink, so clearing the
    # read-only bit after a refused delete of a link would change the target (dotfiles) instead.
    target = tmp_path / "dotfiles" / "context_check.py"
    target.parent.mkdir()
    target.write_bytes(b"# hook\n")
    read_only(target)
    link = tmp_path / "context_check.py"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks need a privilege on this Windows")
    mode = target.stat().st_mode
    real_unlink, refused = pathlib.Path.unlink, []

    def unlink(self, *args, **kwargs):
        if self == link and not refused:
            refused.append(self)
            raise PermissionError(13, "Access is denied", str(self))
        return real_unlink(self, *args, **kwargs)
    monkeypatch.setattr(pathlib.Path, "unlink", unlink)
    with pytest.raises(PermissionError):
        install_module.remove(link)
    assert link.is_symlink() and target.stat().st_mode == mode


@pytest.mark.parametrize("name", ["CLAUDE.md", "settings.json", "ballast/install-record.json"])
def test_a_read_only_file_stops_uninstall_before_any_write(install_module, uninstall_module, windows_read_only,
                                                           tmp_path, name):
    # Review 8, low 25 (old #6, the uninstall side): uninstall had no read-only check before its
    # first write, so a read-only settings.json stopped it after CLAUDE.md was reverted and a
    # settings backup written. Halfway state; the neighbour of install's check.
    home = tmp_path / "home"
    claude(home).mkdir(parents=True)
    (claude(home) / "CLAUDE.md").write_bytes(b"mine\n")
    (claude(home) / "settings.json").write_text('{"model": "opus"}\n', encoding="utf-8")
    install_module.install(home)
    (claude(home) / "ballast" / "context_check.log").write_text("a line\n", encoding="utf-8")   # deleted first
    read_only(claude(home) / name)
    before = snapshot(home)
    with pytest.raises(PermissionError, match="read-only"):
        uninstall_module.uninstall(home)
    assert snapshot(home) == before


def test_a_read_only_claude_md_uninstall_leaves_as_is_does_not_stop_it(install_module, uninstall_module,
                                                                      windows_read_only, tmp_path):
    # Only a file the run would change is refused: a CLAUDE.md with no section of ours stays.
    home = tmp_path / "home"
    claude(home).mkdir(parents=True)
    install_module.install(home)
    md = claude(home) / "CLAUDE.md"
    md.write_bytes(b"my own file now\n")
    read_only(md)
    uninstall_module.uninstall(home)
    assert md.read_bytes() == b"my own file now\n"
    assert not (claude(home) / "ballast" / "context_check.py").exists()
