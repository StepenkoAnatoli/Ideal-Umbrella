#!/usr/bin/env python3
"""Ideal-Umbrella: install user-level settings, hook, and CLAUDE.md.

Idempotent: running again updates only what changed.
Usage: python -I config/install.py [--verify-only]

What it does:
  1. Merges config/user-settings.json into ~/.claude/settings.json
  2. Copies config/CLAUDE.md to ~/.claude/CLAUDE.md
  3. Copies hooks/context_check.py to ~/.claude/ballast/context_check.py
  4. Prints a verification command to run in a new Claude Code session.
"""
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
USER_SETTINGS = HERE / "user-settings.json"
CLAUDE_MD = HERE / "CLAUDE.md"
HOOK_SRC = HERE.parent / "hooks" / "context_check.py"

CLAUDE_DIR = Path.home() / ".claude"
SETTINGS_DEST = CLAUDE_DIR / "settings.json"
CLAUDE_MD_DEST = CLAUDE_DIR / "CLAUDE.md"
HOOK_DEST = CLAUDE_DIR / "ballast" / "context_check.py"


def merge_settings(existing: dict, template: dict) -> list[str]:
    """Merge template into existing, return list of changes."""
    changes = []
    for key, value in template.items():
        if key == "hooks":
            existing_hooks = existing.setdefault("hooks", {})
            for event, entries in template["hooks"].items():
                current = existing_hooks.setdefault(event, [])
                # Remove any existing Ideal-Umbrella entries for this event
                kept = [e for e in current if "context_check.py" not in str(e)]
                if kept + entries != current:
                    changes.append(f"hooks.{event}: Ideal-Umbrella entry {'updated' if len(kept) < len(current) else 'added'}")
                    existing_hooks[event] = kept + entries
        elif existing.get(key) != value:
            changes.append(f"{key}: {existing.get(key)} -> {value}")
            existing[key] = value
    return changes


def install(verify_only: bool = False) -> list[str]:
    changes = []

    # 1. Merge user settings
    CLAUDE_DIR.mkdir(parents=True, exist_ok=True)
    existing = {}
    if SETTINGS_DEST.exists():
        with open(SETTINGS_DEST, encoding="utf-8") as f:
            try:
                existing = json.load(f)
            except json.JSONDecodeError as e:
                sys.exit(f"Error: {SETTINGS_DEST} is not valid JSON ({e}); fix it first.")

    with open(USER_SETTINGS, encoding="utf-8") as f:
        template = json.load(f)

    setting_changes = merge_settings(existing, template)
    if setting_changes and not verify_only:
        with open(SETTINGS_DEST, "w", encoding="utf-8", newline="\n") as f:
            json.dump(existing, f, indent=2)
            f.write("\n")
    changes.extend(setting_changes)

    # 2. Copy CLAUDE.md
    claude_md_content = CLAUDE_MD.read_text(encoding="utf-8")
    if not CLAUDE_MD_DEST.exists() or CLAUDE_MD_DEST.read_text(encoding="utf-8") != claude_md_content:
        if not verify_only:
            CLAUDE_MD_DEST.write_text(claude_md_content, encoding="utf-8", newline="\n")
        changes.append(f"CLAUDE.md {'updated' if CLAUDE_MD_DEST.exists() else 'written'}")

    # 3. Copy hook
    hook_content = HOOK_SRC.read_bytes()
    if not HOOK_DEST.exists() or HOOK_DEST.read_bytes() != hook_content:
        if not verify_only:
            HOOK_DEST.parent.mkdir(parents=True, exist_ok=True)
            HOOK_DEST.write_bytes(hook_content)
        changes.append(f"hook {'updated' if HOOK_DEST.exists() else 'written'}")

    return changes


def verify() -> tuple[bool, list[str]]:
    """Verify installation by checking files exist and have correct content."""
    issues = []

    # Check settings.json
    if not SETTINGS_DEST.exists():
        issues.append(f"Missing: {SETTINGS_DEST}")
    else:
        with open(SETTINGS_DEST, encoding="utf-8") as f:
            try:
                settings = json.load(f)
            except json.JSONDecodeError as e:
                issues.append(f"Invalid JSON in {SETTINGS_DEST}: {e}")
            else:
                # Check required keys
                if settings.get("autoCompactWindow") != 250000:
                    issues.append(f"autoCompactWindow is {settings.get('autoCompactWindow')}, expected 250000")
                if settings.get("skillListingBudgetFraction") != 0.005:
                    issues.append(f"skillListingBudgetFraction is {settings.get('skillListingBudgetFraction')}, expected 0.005")
                # Check hook
                hooks = settings.get("hooks", {}).get("UserPromptSubmit", [])
                found = False
                for entry in hooks:
                    for h in entry.get("hooks", []):
                        if "context_check.py" in h.get("command", ""):
                            found = True
                            cmd = h.get("command", "")
                            if "python3 -I ~/.claude/ballast/context_check.py" not in cmd:
                                issues.append(f"Hook command not portable: {cmd}")
                if not found:
                    issues.append("Ideal-Umbrella hook not found in UserPromptSubmit")

    # Check CLAUDE.md
    if not CLAUDE_MD_DEST.exists():
        issues.append(f"Missing: {CLAUDE_MD_DEST}")
    elif CLAUDE_MD_DEST.read_text(encoding="utf-8") != CLAUDE_MD.read_text(encoding="utf-8"):
        issues.append(f"CLAUDE.md content differs from config/CLAUDE.md")

    # Check hook
    if not HOOK_DEST.exists():
        issues.append(f"Missing: {HOOK_DEST}")
    elif HOOK_DEST.read_bytes() != HOOK_SRC.read_bytes():
        issues.append(f"Hook content differs from hooks/context_check.py")

    return len(issues) == 0, issues


def main():
    verify_only = "--verify-only" in sys.argv

    if not verify_only:
        print("Installing Ideal-Umbrella user-level configuration...")
        changes = install(verify_only=False)
        if changes:
            print("Changes:")
            for c in changes:
                print(f"  - {c}")
        else:
            print("Already up to date.")
    else:
        print("Verifying installation...")

    ok, issues = verify()
    if ok:
        print("\n[OK] Installation verified successfully.")
    else:
        print("\n[FAIL] Verification failed:")
        for issue in issues:
            print(f"  - {issue}")
        sys.exit(1)

    # Print verification command
    print("\nTo verify in a new Claude Code session, run:")
    print('  claude -p "Call get_usage and list every context category with its tokens."')
    print("\nExpected: context categories should include 'cache_read', 'cache_creation',")
    print("'input', 'output' with totals reflecting the compact window (250k) and")
    print("reduced skill listing.")


if __name__ == "__main__":
    main()