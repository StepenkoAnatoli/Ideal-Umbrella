"""Undo an Ideal-Umbrella user-level install.

Removes the keys, the UserPromptSubmit hook entry, and the denied-tool entries that
Ideal-Umbrella added, and deletes the copied hook and CLAUDE.md (restoring the
backup taken at install time if present).
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
CLAUDE_DIR = HOME / ".claude"
BALLAST_DIR = CLAUDE_DIR / "ballast"
SETTINGS_PATH = CLAUDE_DIR / "settings.json"
HOOK_DST = BALLAST_DIR / "context_check.py"
CLAUDE_MD_DST = CLAUDE_DIR / "CLAUDE.md"
BACKUP_MD = CLAUDE_DIR / "CLAUDE.md.before-ideal-umbrella"


def load_json(path):
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def is_ours(entry):
    return any("context_check.py" in h.get("command", "") for h in entry.get("hooks", []))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    settings = load_json(SETTINGS_PATH)
    changes = []

    for key in ("autoCompactWindow", "skillListingBudgetFraction"):
        if key in settings:
            changes.append(f"remove {key}")
            if not args.dry_run:
                del settings[key]

    hooks = settings.get("hooks", {})
    if "UserPromptSubmit" in hooks:
        before = hooks["UserPromptSubmit"]
        after = [e for e in before if not is_ours(e)]
        if after != before:
            changes.append("remove Ideal-Umbrella UserPromptSubmit entry")
            if not args.dry_run:
                if after:
                    hooks["UserPromptSubmit"] = after
                else:
                    del hooks["UserPromptSubmit"]

    perms = settings.get("permissions", {})
    deny = perms.get("deny", [])
    ours = {"Artifact", "ScheduleWakeup", "ReportFindings", "SearchPlugins",
            "SuggestPluginInstall", "SuggestSkills"}
    new_deny = [t for t in deny if t not in ours]
    if new_deny != deny:
        changes.append("remove Ideal-Umbrella denied tools")
        if not args.dry_run:
            if new_deny:
                perms["deny"] = new_deny
            else:
                perms.pop("deny", None)
                if not perms:
                    settings.pop("permissions", None)

    if not hooks:
        settings.pop("hooks", None)

    if HOOK_DST.exists():
        changes.append(f"delete {HOOK_DST}")
    if CLAUDE_MD_DST.exists():
        changes.append(f"delete {CLAUDE_MD_DST}" + (" (restore backup)" if BACKUP_MD.exists() else ""))

    print("Planned changes:")
    for c in changes or ["(none)"]:
        print("  - " + c)

    if args.dry_run:
        print("\n--dry-run: nothing written.")
        return 0

    if SETTINGS_PATH.exists():
        with open(SETTINGS_PATH, "w", encoding="utf-8", newline="\n") as f:
            json.dump(settings, f, indent=2)
            f.write("\n")
    if HOOK_DST.exists():
        HOOK_DST.unlink()
    if CLAUDE_MD_DST.exists():
        CLAUDE_MD_DST.unlink()
        if BACKUP_MD.exists():
            shutil.move(str(BACKUP_MD), str(CLAUDE_MD_DST))
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
