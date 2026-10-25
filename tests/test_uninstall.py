import json
import subprocess
import sys

import pytest

from conftest import ROOT, load_module

UNINSTALL = ROOT / "config" / "uninstall.py"
TEMPLATE_MD = (ROOT / "config" / "CLAUDE.md").read_text(encoding="utf-8")


@pytest.fixture
def uninstall_module():
    return load_module("uninstall_module", "config/uninstall.py")


def settings_file(home):
    return home / ".claude" / "settings.json"


def read_settings(home):
    return json.loads(settings_file(home).read_text(encoding="utf-8"))


def seed(home, settings, claude_md=None):
    claude = home / ".claude"
    claude.mkdir(parents=True)
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")
    if claude_md is not None:
        (claude / "CLAUDE.md").write_text(claude_md, encoding="utf-8")


def test_round_trip_restores_what_was_there(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    before = {
        "customKey": "keep-me",
        "autoCompactWindow": 123,
        "permissions": {"allow": ["Bash(ls:*)"], "deny": ["MyTool", "Artifact"]},
        "hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "bash my-own-hook.sh"}]}]},
    }
    seed(home, before, claude_md="my own rules\n")

    install_module.install(home, force=True)
    assert read_settings(home)["autoCompactWindow"] == 250000
    assert (home / ".claude" / "ballast" / "context_check.py").exists()

    changes, notices = uninstall_module.uninstall(home)
    assert changes
    assert notices == []
    assert read_settings(home) == before
    assert (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == "my own rules\n"
    assert not (home / ".claude" / "ballast" / "context_check.py").exists()
    record = json.loads((home / ".claude" / "ballast" / "install-record.json").read_text(encoding="utf-8"))
    assert record == {"uninstalled": True}


def test_fresh_install_round_trip_removes_everything(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    install_module.install(home)
    install_module.install(home)  # a second run must not lose the first run's record

    uninstall_module.uninstall(home)
    assert read_settings(home) == {}
    assert not (home / ".claude" / "CLAUDE.md").exists()


def test_values_changed_after_install_are_kept(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    install_module.install(home)
    settings = read_settings(home)
    settings["autoCompactWindow"] = 300000
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")
    (home / ".claude" / "CLAUDE.md").write_text("edited after install\n", encoding="utf-8")

    _, notices = uninstall_module.uninstall(home)
    after = read_settings(home)
    assert after["autoCompactWindow"] == 300000
    assert "skillListingBudgetFraction" not in after
    assert (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == "edited after install\n"
    assert any("autoCompactWindow" in n for n in notices)
    assert any("CLAUDE.md" in n for n in notices)


def test_sibling_hook_in_same_entry_is_kept(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    seed(home, {"hooks": {"UserPromptSubmit": [{"hooks": [
        {"type": "command", "command": "bash my-own-hook.sh"},
        {"type": "command", "command": "python3 -I old/context_check.py"},
    ]}]}})
    install_module.install(home)
    uninstall_module.uninstall(home)
    assert read_settings(home)["hooks"] == {
        "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "bash my-own-hook.sh"}]}]
    }


def test_without_record_leaves_deny_alone(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    install_module.install(home)
    (home / ".claude" / "ballast" / "install-record.json").unlink()

    _, notices = uninstall_module.uninstall(home)
    after = read_settings(home)
    assert "autoCompactWindow" not in after
    assert "hooks" not in after
    assert "Artifact" in after["permissions"]["deny"]
    assert not (home / ".claude" / "CLAUDE.md").exists()
    assert any("permissions.deny" in n for n in notices)


def test_dry_run_writes_nothing(install_module, tmp_path):
    home = tmp_path / "home"
    install_module.install(home)
    claude = home / ".claude"
    snapshot = {p: p.read_bytes() for p in claude.rglob("*") if p.is_file()}

    result = subprocess.run(
        [sys.executable, "-I", str(UNINSTALL), "--home", str(home), "--dry-run"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert "nothing written" in result.stdout
    assert {p: p.read_bytes() for p in claude.rglob("*") if p.is_file()} == snapshot


def test_nothing_installed_is_a_no_op(uninstall_module, tmp_path):
    changes, _ = uninstall_module.uninstall(tmp_path / "home")
    assert changes == []


def test_second_uninstall_keeps_the_users_own_values(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    before = {"autoCompactWindow": 250000, "skillListingBudgetFraction": 0.005, "model": "opus"}
    seed(home, before, claude_md=TEMPLATE_MD)

    install_module.install(home)
    uninstall_module.uninstall(home)
    changes, _ = uninstall_module.uninstall(home)
    assert read_settings(home) == before
    assert (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == TEMPLATE_MD
    assert not any("removed" in c or "deleted" in c for c in changes)


def test_without_record_or_hook_nothing_is_removed(uninstall_module, tmp_path):
    home = tmp_path / "home"
    before = {"autoCompactWindow": 250000, "skillListingBudgetFraction": 0.005}
    seed(home, before, claude_md=TEMPLATE_MD)

    uninstall_module.uninstall(home)
    assert read_settings(home) == before
    assert (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == TEMPLATE_MD


def changed_templates(uninstall_module, tmp_path, monkeypatch):
    """Simulate a git pull between install and uninstall."""
    inst = uninstall_module.install
    settings = json.loads(inst.USER_SETTINGS.read_text(encoding="utf-8"))
    settings["autoCompactWindow"] = 300000
    new_settings = tmp_path / "user-settings.json"
    new_settings.write_text(json.dumps(settings), encoding="utf-8")
    new_md = tmp_path / "CLAUDE.md"
    new_md.write_text(TEMPLATE_MD + "- a rule added later\n", encoding="utf-8")
    monkeypatch.setattr(inst, "USER_SETTINGS", new_settings)
    monkeypatch.setattr(inst, "CLAUDE_MD", new_md)


def test_uninstall_after_template_change_undoes_the_install(uninstall_module, tmp_path, monkeypatch):
    home = tmp_path / "home"
    seed(home, {"model": "opus"}, claude_md="my own rules\n")
    uninstall_module.install.install(home)
    changed_templates(uninstall_module, tmp_path, monkeypatch)

    _, notices = uninstall_module.uninstall(home)
    assert read_settings(home) == {"model": "opus"}
    assert (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == "my own rules\n"
    assert notices == []


def test_reinstall_keeps_edits_made_after_the_first_install(uninstall_module, tmp_path, monkeypatch):
    home = tmp_path / "home"
    seed(home, {}, claude_md="mine v1\n")
    inst = uninstall_module.install
    inst.install(home)
    (home / ".claude" / "CLAUDE.md").write_text("mine v2\n", encoding="utf-8")
    settings = read_settings(home)
    settings["autoCompactWindow"] = 100000
    settings_file(home).write_text(json.dumps(settings), encoding="utf-8")

    changed_templates(uninstall_module, tmp_path, monkeypatch)
    inst.install(home, force=True)
    uninstall_module.uninstall(home)
    assert (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == "mine v2\n"
    assert read_settings(home) == {"autoCompactWindow": 100000}


def test_symlinks_survive_uninstall(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    dotfiles = tmp_path / "dotfiles"
    dotfiles.mkdir()
    (dotfiles / "settings.json").write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    (dotfiles / "CLAUDE.md").write_text("my own rules\n", encoding="utf-8")
    try:
        settings_file(home).symlink_to(dotfiles / "settings.json")
        (claude / "CLAUDE.md").symlink_to(dotfiles / "CLAUDE.md")
    except OSError:
        pytest.skip("cannot create symlinks here")

    install_module.install(home)
    uninstall_module.uninstall(home)
    assert settings_file(home).is_symlink()
    assert (claude / "CLAUDE.md").is_symlink()
    assert json.loads((dotfiles / "settings.json").read_text(encoding="utf-8")) == {"model": "opus"}
    assert (dotfiles / "CLAUDE.md").read_text(encoding="utf-8") == "my own rules\n"


def test_malformed_hook_entry_survives_uninstall(install_module, uninstall_module, tmp_path):
    home = tmp_path / "home"
    seed(home, {"hooks": {"UserPromptSubmit": [{"hooks": ["echo hi"]}]}})
    install_module.install(home)
    uninstall_module.uninstall(home)
    assert read_settings(home)["hooks"] == {"UserPromptSubmit": [{"hooks": ["echo hi"]}]}
