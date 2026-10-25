#!/usr/bin/env python3
"""Ideal-Umbrella: undo what config/install.py did.

Puts back the settings values that were there before the install, removes only the
permissions.deny tools and the hook entry the installer added, deletes the copied hook,
and restores the CLAUDE.md backup (or removes a CLAUDE.md the installer created).
settings.json is backed up before it is rewritten.

It works from <home>/.claude/ballast/install-record.json, which install.py writes, and
compares against the values the install wrote (not the current templates). Afterwards the
record is kept as a marker, so running uninstall again changes nothing. Without a record
(installs made before it existed) it removes the two keys only if they still hold the
template values and the Ideal-Umbrella hook is installed, keeps a backup of CLAUDE.md
before deleting it, removes the hook, and leaves permissions.deny alone.

A value you changed after installing is left as it is and reported.

Usage:
  python -I config/uninstall.py [--home PATH] [--dry-run]
"""
import argparse
import shutil
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


def has_our_hook(settings):
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return False
    return any(install._is_ours(entry) for entries in hooks.values() if isinstance(entries, list)
               for entry in entries)


def undo_settings(settings, template, record, evidence=None):
    """Undo the install in settings (in place); return (changes, notices, keys left as is).

    Values are compared with what the install wrote (kept in the record), falling back to
    the template for older records. Without a record, the keys are removed only when there
    is evidence of an install (evidence; by default, our hook entry in settings).
    """
    changes, notices, left = [], [], []
    has_record = record is not None
    record = record or {}
    replaced = record.get("replaced", {})
    added = record.get("added_keys", [])
    installed = record.get("installed", {})
    if evidence is None:
        evidence = has_our_hook(settings)

    if has_record:
        keys = list(dict.fromkeys([*added, *replaced]))
    elif evidence:
        keys = list(template)
    else:
        keys = []
        notices.append("no install record and no Ideal-Umbrella hook; settings values left as is")
    for key in keys:
        if key in ("hooks", "permissions") or key not in settings:
            continue
        if key in installed:
            expected = installed[key]
        elif key in template:
            expected = template[key]
        else:
            continue
        if settings[key] != expected:
            notices.append(f"{key} is {settings[key]!r}, not the installed value; left as is")
            left.append(key)
            continue
        if key in replaced:
            settings[key] = replaced[key]
            changes.append(f"{key}: restored {replaced[key]!r}")
        else:
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
    return changes, notices, left


def _leftover_record(record, left, claude_md_left):
    """What an uninstall keeps of the record: a marker that it ran, plus anything left as is,
    so a second run neither falls back to no-record mode nor forgets a pending backup."""
    leftover = {"uninstalled": True}
    if record and left:
        leftover["added_keys"] = [k for k in record.get("added_keys", []) if k in left]
        leftover["replaced"] = {k: v for k, v in record.get("replaced", {}).items() if k in left}
        leftover["installed"] = {k: v for k, v in record.get("installed", {}).items() if k in left}
    if record and claude_md_left and record.get("claude_md"):
        leftover["claude_md"] = record["claude_md"]
    return leftover


def uninstall(home, dry_run=False):
    paths = install.layout(home)
    record = install.read_record(paths["record"])
    changes, notices = [], []

    # Read everything first, so a read error leaves every file as it was.
    settings = install._read_json(paths["settings"]) if paths["settings"].exists() else None
    template = install._read_json(install.USER_SETTINGS)
    claude_md = paths["claude_md"]
    # A CLAUDE.md that is not UTF-8 cannot be the one install wrote; decoding it with
    # replacement characters makes it compare as "not ours" instead of blocking the undo.
    try:
        current_md = claude_md.read_text(encoding="utf-8", errors="replace") if claude_md.exists() else None
    except OSError as e:
        raise ValueError(f"cannot read {claude_md} ({e.strerror or e})") from e
    template_md = install._read_text(install.CLAUDE_MD)
    evidence = paths["hook"].exists() or (settings is not None and has_our_hook(settings))

    left = []
    if settings is not None:
        setting_changes, notices, left = undo_settings(settings, template, record, evidence)
        changes.extend(setting_changes)
        if setting_changes and not dry_run:
            backup = install._backup(paths["settings"])
            changes.append(f"settings backup: {backup.name}")
            install._write_json(paths["settings"], settings)

    if paths["hook"].exists():
        changes.append("hook deleted")
        if not dry_run:
            paths["hook"].unlink()

    entry = (record or {}).get("claude_md")
    claude_md_left = False
    if current_md is not None:
        if isinstance(entry, dict) and entry.get("sha256"):
            ours = install.text_hash(current_md) == entry["sha256"]
        else:
            ours = current_md == template_md
        backup = claude_md.with_name(entry["backup"]) if isinstance(entry, dict) and entry.get("backup") else None
        if not ours:
            claude_md_left = True
            notices.append("CLAUDE.md differs from what was installed; left as is"
                           + (f" (your earlier file is in {backup.name})" if backup and backup.exists() else ""))
        elif backup is not None and backup.exists():
            changes.append(f"CLAUDE.md restored from {backup.name}")
            if not dry_run:
                # Copy, not rename, so a symlinked CLAUDE.md is written through, not replaced.
                shutil.copyfile(backup, claude_md)
                backup.unlink()
        elif backup is not None:
            # The install replaced a file of yours and its backup is gone: deleting now would
            # lose the only copy left, so keep it and say so.
            claude_md_left = True
            notices.append(f"CLAUDE.md left as is: the backup {backup.name} it should be restored "
                           "from is missing")
        elif record is not None and entry is not None:
            changes.append("CLAUDE.md deleted")
            if not dry_run:
                claude_md.unlink()
        elif record is None and evidence:
            # Without a record it may be the user's own copy: keep one.
            if dry_run:
                changes.append("CLAUDE.md deleted (a backup is kept)")
            else:
                backup = install._backup(claude_md)
                claude_md.unlink()
                changes.append(f"CLAUDE.md deleted (copy kept as {backup.name})")

    if (record is not None or paths["record"].exists()) and not dry_run:
        install._write_json(paths["record"], _leftover_record(record, left, claude_md_left))
    return changes, notices


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.strip(),
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--home", default=str(Path.home()), help="home folder to uninstall from (default: current home)")
    parser.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
    args = parser.parse_args(argv)

    try:
        changes, notices = uninstall(Path(args.home).expanduser().resolve(), dry_run=args.dry_run)
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
