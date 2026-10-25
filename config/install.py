#!/usr/bin/env python3
"""Ideal-Umbrella: install user-level settings, hook, and CLAUDE.md.

Idempotent: running again updates only what changed. Existing keys, other hook
entries, sibling hooks and permission rules are preserved. A differing
CLAUDE.md is backed up before it is replaced. The hook command records the
Python executable that ran the installer, so it does not depend on `python3`
being on PATH.

Usage:
  python -I config/install.py [--home PATH] [--force] [--verify-only]

What it does:
  1. Merges config/user-settings.json into <home>/.claude/settings.json
  2. Copies config/CLAUDE.md to <home>/.claude/CLAUDE.md (backup on change)
  3. Copies hooks/context_check.py to <home>/.claude/ballast/context_check.py
  4. Verifies the files and prints a command to run in a new session.

What it changed is recorded in <home>/.claude/ballast/install-record.json, so
config/uninstall.py can put back the values that were there before.
"""
import argparse
import datetime
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
USER_SETTINGS = HERE / "user-settings.json"
CLAUDE_MD = HERE / "CLAUDE.md"
HOOK_SRC = HERE.parent / "hooks" / "context_check.py"

REQUIRED_TOOLS = (
    "Artifact",
    "ScheduleWakeup",
    "ReportFindings",
    "SearchPlugins",
    "SuggestPluginInstall",
    "SuggestSkills",
)


def layout(home):
    claude = Path(home) / ".claude"
    return {
        "claude": claude,
        "settings": claude / "settings.json",
        "claude_md": claude / "CLAUDE.md",
        "hook": claude / "ballast" / "context_check.py",
        "record": claude / "ballast" / "install-record.json",
    }


def quote(value):
    if os.name == "nt":
        return '"' + str(value).replace('"', '\\"') + '"'
    import shlex

    return shlex.quote(str(value))


def hook_command(home):
    return f"{quote(sys.executable)} -I {quote(layout(home)['hook'])}"


def _hook_entries(entry):
    hooks = entry.get("hooks", []) if isinstance(entry, dict) else []
    return hooks if isinstance(hooks, list) else []


def _is_ours(entry):
    return any(isinstance(h, dict) and "context_check.py" in str(h.get("command", ""))
               for h in _hook_entries(entry))


def _template_hook(entries):
    for entry in entries:
        for hook in _hook_entries(entry):
            if isinstance(hook, dict) and "context_check.py" in str(hook.get("command", "")):
                return hook
    return None


def merge_settings(existing, template, home, force=False, record=None):
    """Merge template into existing; return (changes, notices).

    When record is a dict, it is filled with what was added or replaced so it can be undone.
    """
    if record is None:
        record = {}
    record.setdefault("added_keys", [])
    record.setdefault("replaced", {})
    record.setdefault("deny_added", [])
    record.setdefault("installed", {})
    if not isinstance(existing, dict):
        raise ValueError("settings must be a JSON object")
    if not isinstance(template, dict):
        raise ValueError("template must be a JSON object")
    changes, notices = [], []

    for key, value in template.items():
        if key in ("hooks", "permissions"):
            continue
        if key not in existing:
            existing[key] = value
            record["added_keys"].append(key)
            record["installed"][key] = value
            changes.append(f"{key}: added {value!r}")
        elif existing[key] != value:
            if force:
                old = existing[key]
                existing[key] = value
                record["replaced"][key] = old
                record["installed"][key] = value
                changes.append(f"{key}: {old!r} -> {value!r}")
            else:
                notices.append(f"{key} is {existing[key]!r}, template has {value!r}; left unchanged (use --force)")

    template_permissions = template.get("permissions", {})
    if template_permissions:
        permissions = existing.setdefault("permissions", {})
        if not isinstance(permissions, dict):
            raise ValueError("permissions must be an object")
        wanted = template_permissions.get("deny", [])
        deny = permissions.setdefault("deny", [])
        if not isinstance(deny, list):
            raise ValueError("permissions.deny must be a list")
        added = [tool for tool in wanted if tool not in deny]
        if added:
            deny.extend(added)
            record["deny_added"].extend(added)
            changes.append("permissions.deny: added " + ", ".join(added))

    template_hooks = template.get("hooks", {})
    if template_hooks:
        hooks = existing.setdefault("hooks", {})
        if not isinstance(hooks, dict):
            raise ValueError("hooks must be an object")
        for event, entries in template_hooks.items():
            if not isinstance(entries, list):
                raise ValueError(f"hooks.{event} must be a list")
            current = hooks.setdefault(event, [])
            if not isinstance(current, list):
                raise ValueError(f"hooks.{event} must be a list")
            replacement = _template_hook(entries)
            if replacement is None:
                continue
            replacement = dict(replacement)
            replacement["command"] = hook_command(home)
            ours = [entry for entry in current if _is_ours(entry)]
            if not ours:
                new_entry = {"hooks": [replacement]}
                if any(isinstance(entry, dict) and entry.get("matcher") for entry in entries):
                    new_entry["matcher"] = next(
                        entry["matcher"] for entry in entries if isinstance(entry, dict) and entry.get("matcher")
                    )
                current.append(new_entry)
                changes.append(f"hooks.{event}: Ideal-Umbrella hook added")
                continue
            updated = False
            for entry in ours:
                for hook in _hook_entries(entry):
                    if isinstance(hook, dict) and "context_check.py" in str(hook.get("command", "")):
                        if hook.get("command") != replacement["command"]:
                            hook["command"] = replacement["command"]
                            updated = True
            if updated:
                changes.append(f"hooks.{event}: Ideal-Umbrella hook updated")
    return changes, notices


def _read_json(path):
    with open(path, encoding="utf-8-sig") as f:
        try:
            data = json.load(f)
        except ValueError as e:
            sys.exit(f"{path} is not valid JSON ({e}); fix it first, nothing written")
    if not isinstance(data, dict):
        sys.exit(f"{path} must contain a JSON object, not {type(data).__name__}; nothing written")
    return data


def _backup(path):
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.bak-{stamp}")
    n = 1
    while backup.exists():
        backup = path.with_name(f"{path.name}.bak-{stamp}-{n}")
        n += 1
    shutil.copy2(path, backup)
    return backup


def _write_json(path, data):
    # Write through a symlink (dotfiles, stow, home-manager) instead of replacing the link.
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".settings-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _read_text(path):
    """Read a UTF-8 file; any failure is a ValueError naming the file."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(f"{path} is not UTF-8 ({e}); save it as UTF-8 first") from e
    except OSError as e:
        raise ValueError(f"cannot read {path} ({e.strerror or e})") from e


def _read_bytes(path):
    try:
        return path.read_bytes()
    except OSError as e:
        raise ValueError(f"cannot read {path} ({e.strerror or e})") from e


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_record(path):
    """The saved install record, or None when there is none or it is unreadable."""
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (ValueError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _merge_record(old, new):
    """Fold this run's record into the saved one.

    What was there before the first install wins, so a second install never overwrites it,
    unless the user changed an installed value since: then their newer value is what an
    uninstall puts back. Records from before "installed" existed keep first-wins.
    """
    old_installed = old.get("installed")
    tracked = list(old.get("added_keys", [])) + list(old.get("replaced", {}))
    replaced = dict(old.get("replaced", {}))
    added = list(old.get("added_keys", []))
    for key, value in new.get("replaced", {}).items():
        if key in tracked and (not isinstance(old_installed, dict) or key not in old_installed
                               or old_installed[key] == value):
            continue  # value is one an earlier install wrote
        replaced[key] = value
        if key in added:
            added.remove(key)
    added += [k for k in new.get("added_keys", []) if k not in added and k not in replaced]
    deny = list(old.get("deny_added", []))
    deny += [t for t in new.get("deny_added", []) if t not in deny]
    installed = dict(old_installed) if isinstance(old_installed, dict) else {}
    installed.update(new.get("installed", {}))
    merged = {"added_keys": added, "replaced": replaced, "deny_added": deny, "installed": installed}
    if "claude_md" in new:
        merged["claude_md"] = new["claude_md"]
    elif "claude_md" in old:
        merged["claude_md"] = old["claude_md"]
    return merged


def install(home, force=False, verify_only=False):
    paths = layout(home)
    changes, notices = [], []
    record = {}

    # Read and check everything before writing anything, and write settings.json last: its
    # hook entry must never point at a hook file that was not copied (a missing hook file
    # exits 2, which blocks every prompt).
    existing = _read_json(paths["settings"]) if paths["settings"].exists() else {}
    template = _read_json(USER_SETTINGS)
    old_record = read_record(paths["record"]) or {}
    claude_md = _read_text(CLAUDE_MD)
    claude_md_exists = paths["claude_md"].exists()
    current_md = _read_text(paths["claude_md"]) if claude_md_exists else None
    hook_bytes = _read_bytes(HOOK_SRC)
    hook_exists = paths["hook"].exists()
    current_hook = _read_bytes(paths["hook"]) if hook_exists else None
    setting_changes, setting_notices = merge_settings(existing, template, home, force, record)
    notices.extend(setting_notices)
    if verify_only:
        if current_hook != hook_bytes:
            changes.append(f"hook {'updated' if hook_exists else 'written'}")
        if current_md != claude_md:
            changes.append(f"CLAUDE.md {'updated' if claude_md_exists else 'written'}")
        return setting_changes + changes, notices

    if current_hook != hook_bytes:
        paths["hook"].parent.mkdir(parents=True, exist_ok=True)
        paths["hook"].write_bytes(hook_bytes)
        changes.append(f"hook {'updated' if hook_exists else 'written'}")

    if current_md != claude_md:
        paths["claude_md"].parent.mkdir(parents=True, exist_ok=True)
        backup = None
        if claude_md_exists:
            backup = _backup(paths["claude_md"])
            changes.append(f"CLAUDE.md backup: {backup.name}")
        old_md = old_record.get("claude_md")
        # Keep the first backup when the file is still what an earlier install wrote. If the
        # user edited it since, their edits are what an uninstall should put back.
        if isinstance(old_md, dict) and (current_md is None or "sha256" not in old_md
                                         or old_md["sha256"] == text_hash(current_md)):
            record["claude_md"] = dict(old_md, sha256=text_hash(claude_md))
        else:
            record["claude_md"] = {"backup": backup.name if backup else None, "sha256": text_hash(claude_md)}
            if isinstance(old_md, dict) and backup is not None:
                notices.append(f"CLAUDE.md had edits made after the last install; uninstall will restore {backup.name}")
        paths["claude_md"].write_text(claude_md, encoding="utf-8", newline="\n")
        changes.append(f"CLAUDE.md {'updated' if claude_md_exists else 'written'}")

    if setting_changes or changes:
        _write_json(paths["record"], _merge_record(old_record, record))

    if setting_changes:
        if paths["settings"].exists():
            backup = _backup(paths["settings"])
            setting_changes.append(f"settings backup: {backup.name}")
        _write_json(paths["settings"], existing)
    return setting_changes + changes, notices


def verify(home):
    """Return (ok, issues, warnings). Warnings do not fail verification."""
    paths = layout(home)
    issues, warnings = [], []

    if not paths["settings"].exists():
        issues.append(f"Missing: {paths['settings']}")
    else:
        settings = _read_json(paths["settings"])
        # install keeps a user's own value for these unless --force, so a different value is a
        # warning; a missing one means the install did not happen.
        for key, expected in (("autoCompactWindow", 250000), ("skillListingBudgetFraction", 0.005)):
            if key not in settings:
                issues.append(f"{key} is missing, expected {expected!r}")
            elif settings[key] != expected:
                warnings.append(f"{key} is {settings[key]!r}, template has {expected!r}; "
                                "kept as your own value (use --force to replace it)")
        permissions = settings.get("permissions")
        if not isinstance(permissions, dict):
            issues.append("permissions is not an object")
            deny = []
        else:
            deny = permissions.get("deny") or []
        missing_tools = [tool for tool in REQUIRED_TOOLS if tool not in deny]
        if missing_tools:
            issues.append("permissions.deny is missing: " + ", ".join(missing_tools))
        hooks_obj = settings.get("hooks")
        if not isinstance(hooks_obj, dict):
            issues.append("hooks is not an object")
            hooks = []
        else:
            hooks = hooks_obj.get("UserPromptSubmit", [])
        found = False
        for entry in hooks:
            for hook in _hook_entries(entry):
                if not isinstance(hook, dict):
                    continue
                command = str(hook.get("command", ""))
                if "context_check.py" in command:
                    found = True
                    if str(paths["hook"]) not in command:
                        issues.append(f"Hook command does not point at {paths['hook']}: {command}")
        if not found:
            issues.append("Ideal-Umbrella hook not found in UserPromptSubmit")

    if not paths["claude_md"].exists():
        issues.append(f"Missing: {paths['claude_md']}")
    elif paths["claude_md"].read_text(encoding="utf-8", errors="replace") != CLAUDE_MD.read_text(encoding="utf-8"):
        issues.append("CLAUDE.md content differs from config/CLAUDE.md")

    if not paths["hook"].exists():
        issues.append(f"Missing: {paths['hook']}")
    elif paths["hook"].read_bytes() != HOOK_SRC.read_bytes():
        issues.append("Hook content differs from hooks/context_check.py")

    return len(issues) == 0, issues, warnings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.strip())
    parser.add_argument("--home", default=str(Path.home()), help="home folder to install into (default: current home)")
    parser.add_argument("--force", action="store_true", help="replace differing scalar settings")
    parser.add_argument("--verify-only", action="store_true", help="check the installation without writing")
    args = parser.parse_args(argv)
    # A relative or literal "~" home would put a relative path in the hook command, which
    # Claude Code runs from the project folder.
    home = Path(args.home).expanduser().resolve()

    if not args.verify_only:
        print("Installing Ideal-Umbrella user-level configuration...")
        try:
            changes, notices = install(home, force=args.force)
        except ValueError as e:
            print(f"Error: {e}; nothing written", file=sys.stderr)
            return 1
        if changes:
            print("Changes:")
            for change in changes:
                print(f"  - {change}")
        else:
            print("Already up to date.")
        for notice in notices:
            print(f"  note: {notice}")
    else:
        print("Verifying installation...")

    ok, issues, warnings = verify(home)
    if ok:
        print("\n[OK] Installation verified successfully.")
    else:
        print("\n[FAIL] Verification failed:")
        for issue in issues:
            print(f"  - {issue}")
    for warning in warnings:
        print(f"  warning: {warning}")
    if not ok:
        return 1

    print("\nTo verify in a new Claude Code session, run:")
    print('  claude -p "Call get_usage and list every context category with its tokens."')
    print("\nExpected: context categories should include 'cache_read', 'cache_creation',")
    print("'input', 'output' with totals reflecting the compact window (250k) and")
    print("reduced skill listing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
