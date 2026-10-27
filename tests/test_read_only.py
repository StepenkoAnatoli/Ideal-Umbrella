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

from conftest import load_module


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
    template.write_bytes(inst.CLAUDE_MD.read_bytes() + b"- a rule added later\n")
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


def test_a_read_only_file_with_nothing_to_write_does_not_stop_install(install_module, windows_read_only, tmp_path):
    home = tmp_path / "home"
    install_module.install(home)
    read_only(claude(home) / "CLAUDE.md")
    assert install_module.install(home) == ([], [])


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
        rules = install_module.CLAUDE_MD.read_bytes()
        for path in claude(home).glob("CLAUDE.md.bak-*"):
            path.unlink()
        (claude(home) / "CLAUDE.md").write_bytes(rules)
        (claude(home) / "CLAUDE.md.bak-20250101-000000").write_bytes(b"mine\n")
        record_path = claude(home) / "ballast" / "install-record.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["claude_md"] = {"backup": "CLAUDE.md.bak-20250101-000000",
                               "sha256": hashlib.sha256(rules).hexdigest()}
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



@pytest.mark.parametrize("name", ["CLAUDE.md", "settings.json", "ballast/install-record.json"])
def test_an_uninstall_stopped_by_a_read_only_file_is_finished_once_it_is_writable(
        install_module, uninstall_module, windows_read_only, tmp_path, name):
    # Uninstall checks no write access up front (it cannot tell which files it will leave as
    # they are before it works through them); a stop part way must still be finished by a rerun.
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
