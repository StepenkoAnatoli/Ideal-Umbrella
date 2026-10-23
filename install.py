"""Ideal-Umbrella installer (user level).

Detects the running Python, copies hooks/context_check.py to ~/.claude/ballast/,
merges the two keys and the UserPromptSubmit hook into ~/.claude/settings.json
(idempotently, preserving other keys/hooks), and copies config/CLAUDE.md to
~/.claude/CLAUDE.md (backing up any existing file).

Usage:
  python install.py            apply
  python install.py --dry-run  show what would change, write nothing
  python install.py --no-claude-md  skip the CLAUDE.md copy
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOOK_SRC = HERE / "hooks" / "context_check.py"
CLAUDE_MD_SRC = HERE / "config" / "CLAUDE.md"
USER_SETTINGS = HERE / "config" / "user-settings.json"

HOME = Path(os.path.expanduser("~"))
CLAUDE_DIR = HOME / ".claude"
BALLAST_DIR = CLAUDE_DIR / "ballast"
SETTINGS_PATH = CLAUDE_DIR / "settings.json"
CLAUDE_MD_DST = CLAUDE_DIR / "CLAUDE.md"
HOOK_DST = BALLAST_DIR / "context_check.py"

DENY = [
    "Artifact",
    "ScheduleWakeup",
    "ReportFindings",
    "SearchPlugins",
    "SuggestPluginInstall",
    "SuggestSkills",
]


def load_json(path):
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        try:
            return json.load(f)
        except ValueError as e:
            raise SystemExit(f"{path} is not valid JSON ({e}); fix it first")


def is_ours(entry):
    return any("context_check.py" in h.get("command", "") for h in entry.get("hooks", []))


def merge_settings(settings):
    changes = []
    for key, value in (("autoCompactWindow", 250000), ("skillListingBudgetFraction", 0.005)):
        if settings.get(key) != value:
            changes.append(f"{key}: {settings.get(key)!r} -> {value!r}")
            settings[key] = value
    hooks = settings.setdefault("hooks", {})
    entries = hooks.setdefault("UserPromptSubmit", [])
    kept = [e for e in entries if not is_ours(e)]
    command = f'"{sys.executable}" -I "{HOOK_DST}"'
    new_entry = {"hooks": [{"type": "command", "command": command, "timeout": 15}]}
    if kept + [new_entry] != entries:
        changes.append("hooks.UserPromptSubmit: Ideal-Umbrella entry added/updated")
        hooks["UserPromptSubmit"] = kept + [new_entry]
    perms = settings.setdefault("permissions", {})
    deny = perms.setdefault("deny", [])
    for tool in DENY:
        if tool not in deny:
            deny.append(tool)
            changes.append(f"permissions.deny: added {tool}")
    return changes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-claude-md", action="store_true")
    args = ap.parse_args()

    settings = load_json(SETTINGS_PATH)
    changes = merge_settings(settings)

    # file copies
    copy_hook = not HOOK_DST.exists() or HOOK_DST.read_bytes() != HOOK_SRC.read_bytes()
    if copy_hook:
        changes.append(f"copy {HOOK_SRC} -> {HOOK_DST}")

    copy_md = False
    if not args.no_claude_md and CLAUDE_MD_SRC.is_file():
        if not CLAUDE_MD_DST.exists() or CLAUDE_MD_DST.read_text(encoding="utf-8") != CLAUDE_MD_SRC.read_text(encoding="utf-8"):
            copy_md = True
            changes.append(f"copy {CLAUDE_MD_SRC} -> {CLAUDE_MD_DST} (backup if existing)")

    print("Planned changes:")
    if changes:
        for c in changes:
            print("  - " + c)
    else:
        print("  (none - already up to date)")

    if args.dry_run:
        print("\n--dry-run: nothing written.")
        return 0

    CLAUDE_DIR.mkdir(parents=True, exist_ok=True)
    BALLAST_DIR.mkdir(parents=True, exist_ok=True)
    # backup settings
    if SETTINGS_PATH.exists() and changes:
        backup = CLAUDE_DIR / "ballast" / "settings.before-install.json"
        if not backup.exists():
            shutil.copyfile(SETTINGS_PATH, backup)
    with open(SETTINGS_PATH, "w", encoding="utf-8", newline="\n") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")

    if copy_hook:
        BALLAST_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(HOOK_SRC, HOOK_DST)

    if copy_md:
        if CLAUDE_MD_DST.exists():
            backup_md = CLAUDE_DIR / "CLAUDE.md.before-ideal-umbrella"
            if not backup_md.exists():
                shutil.copyfile(CLAUDE_MD_DST, backup_md)
        shutil.copyfile(CLAUDE_MD_SRC, CLAUDE_MD_DST)

    print("\nDone. Restart Claude Code / open a new session to pick up the settings.")
    print("Undo: python uninstall.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
