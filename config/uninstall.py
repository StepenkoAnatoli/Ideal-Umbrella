#!/usr/bin/env python3
"""Ideal-Umbrella: undo what config/install.py did.

Puts back the settings values that were there before the install, removes only the
permissions.deny tools and the hook entry the installer added, deletes the copied hook,
and restores the CLAUDE.md backup (or removes a CLAUDE.md the installer created).
settings.json is backed up before it is rewritten.

It works from <home>/.claude/ballast/install-record.json, which install.py writes. Without
that record (installs made before it existed) it removes the two keys only if they still
hold the template values, removes the hook, and leaves permissions.deny alone.

A value you changed after installing is left as it is and reported.

Usage:
  python -I config/uninstall.py [--home PATH] [--dry-run]
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import install  # noqa: E402


def _without_our_hooks(entries):
    """Drop Ideal-Umbrella hooks; keep sibling hooks and every other entry."""
    kept = []
    for entry in entries:
        if not install._is_ours(entry):
            kept.append(entry)
            continue
        others = [h for h in install._hook_entries(entry)
                  if not (isinstance(h, dict) and "context_check.py" in str(h.get("command", "")))]
        if others:
            entry = dict(entry)
            entry["hooks"] = others
            kept.append(entry)
    return kept


def undo_settings(settings, template, record):
    """Undo the install in settings (in place); return (changes, notices)."""
    changes, notices = [], []
    has_record = record is not None
    record = record or {}
    replaced = record.get("replaced", {})
    added = record.get("added_keys", [])

    for key, value in template.items():
        if key in ("hooks", "permissions") or key not in settings:
            continue
        if settings[key] != value:
            if key in replaced or key in added or not has_record:
                notices.append(f"{key} is {settings[key]!r}, not the installed value; left as is")
            continue
        if key in replaced:
            settings[key] = replaced[key]
            changes.append(f"{key}: restored {replaced[key]!r}")
        elif key in added or not has_record:
            del settings[key]
            changes.append(f"{key}: removed")

    permissions = settings.get("permissions")
    if isinstance(permissions, dict) and isinstance(permissions.get("deny"), list):
        ours = record.get("deny_added", [])
        deny = [tool for tool in permissions["deny"] if tool not in ours]
        if deny != permissions["deny"]:
            changes.append("permissions.deny: removed " + ", ".join(t for t in permissions["deny"] if t in ours))
            if deny:
                permissions["deny"] = deny
            else:
                del permissions["deny"]
                if not permissions:
                    del settings["permissions"]
    if not has_record:
        notices.append("no install record; permissions.deny left as is")

    hooks = settings.get("hooks")
    if isinstance(hooks, dict):
        for event in list(hooks):
            entries = hooks[event]
            if not isinstance(entries, list):
                continue
            kept = _without_our_hooks(entries)
            if kept != entries:
                changes.append(f"hooks.{event}: Ideal-Umbrella hook removed")
                if kept:
                    hooks[event] = kept
                else:
                    del hooks[event]
        if not hooks:
            del settings["hooks"]
    return changes, notices


def _read_record(path):
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def uninstall(home, dry_run=False):
    paths = install.layout(home)
    record = _read_record(paths["record"])
    changes, notices = [], []

    if paths["settings"].exists():
        settings = install._read_json(paths["settings"])
        template = install._read_json(install.USER_SETTINGS)
        setting_changes, notices = undo_settings(settings, template, record)
        changes.extend(setting_changes)
        if setting_changes and not dry_run:
            backup = install._backup(paths["settings"])
            changes.append(f"settings backup: {backup.name}")
            install._write_json(paths["settings"], settings)

    if paths["hook"].exists():
        changes.append("hook deleted")
        if not dry_run:
            paths["hook"].unlink()

    claude_md = paths["claude_md"]
    entry = (record or {}).get("claude_md")
    if claude_md.exists():
        ours = claude_md.read_text(encoding="utf-8") == install.CLAUDE_MD.read_text(encoding="utf-8")
        backup = claude_md.with_name(entry["backup"]) if entry and entry.get("backup") else None
        if not ours:
            notices.append("CLAUDE.md differs from config/CLAUDE.md; left as is")
        elif backup is not None and backup.exists():
            changes.append(f"CLAUDE.md restored from {backup.name}")
            if not dry_run:
                backup.replace(claude_md)
        elif record is None or entry is not None:
            changes.append("CLAUDE.md deleted")
            if not dry_run:
                claude_md.unlink()

    if record is not None and not dry_run:
        paths["record"].unlink()
    return changes, notices


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.strip(),
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--home", default=str(Path.home()), help="home folder to uninstall from (default: current home)")
    parser.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
    args = parser.parse_args(argv)

    try:
        changes, notices = uninstall(Path(args.home), dry_run=args.dry_run)
    except ValueError as e:
        print(f"Error: {e}; nothing written", file=sys.stderr)
        return 1
    if changes:
        print("Would change:" if args.dry_run else "Changes:")
        for change in changes:
            print(f"  - {change}")
    else:
        print("Nothing to undo.")
    for notice in notices:
        print(f"  note: {notice}")
    if args.dry_run:
        print("\n--dry-run: nothing written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
