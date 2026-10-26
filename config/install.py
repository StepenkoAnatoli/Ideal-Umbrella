#!/usr/bin/env python3
"""Ideal-Umbrella: install user-level settings, hook, and CLAUDE.md.

Idempotent: running again updates only what changed. Existing keys, other hook
entries, sibling hooks and permission rules are preserved. A differing
CLAUDE.md is backed up before it is replaced. The hook command records the
Python executable that ran the installer, so it does not depend on `python3`
being on PATH.

Usage:
  python -I config/install.py [--home PATH] [--force] [--verify-only]

What it does, in write order (everything is read and checked first):
  1. Writes an interim install record to <home>/.claude/ballast/install-record.json: the
     record step 5 will write (the old record, or the leftovers of the marker an uninstall
     left, merged with what this run adds, replaces or creates) marked "unfinished", with the
     CLAUDE.md change and its backup when step 3 writes one, and the name of the copy of
     settings.json made for step 4 (a backup or copy whose record could not be written is
     removed again; one an interrupted install recorded is reused when it still equals the
     file); a key the run changes without replacing it is listed with the value it holds
     until step 4
  2. Copies hooks/context_check.py to <home>/.claude/ballast/context_check.py
  3. Copies config/CLAUDE.md to <home>/.claude/CLAUDE.md (backup on change)
  4. Merges config/user-settings.json into <home>/.claude/settings.json
  5. Writes the full install record
  6. Verifies the files and prints a command to run in a new session.

What it changed is recorded in <home>/.claude/ballast/install-record.json, so
config/uninstall.py can put back the values that were there before. An install interrupted
after step 1 and before step 5 leaves the interim record, marked unfinished: the uninstall
restores what it lists (a replaced value the run never got to write is left as it is; a listed
key holding the template value was written by the run), removes the copy of settings.json the
run never replaced, judges the keys it does not list from the evidence (our hook entry), and
the next install completes the record (the template values it finds in settings.json are
recorded as installed, a replacement the run never wrote is dropped).
"""
import argparse
import datetime
import errno
import hashlib
import json
import os
import shlex
import shutil
import sys
from pathlib import Path

# The fields of an install record that hold settings.json data; a record with none of them is
# an uninstall's marker or the interim record of an install from before it carried data.
INSTALL_DATA = ("added_keys", "replaced", "deny_added", "installed")

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


def layout(home, config_dir=None):
    """The files under <home>/.claude, or under config_dir when Claude Code reads its files
    from there (CLAUDE_CONFIG_DIR) instead of ~/.claude."""
    claude = Path(config_dir) if config_dir else Path(home) / ".claude"
    return {
        "claude": claude,
        "settings": claude / "settings.json",
        "claude_md": claude / "CLAUDE.md",
        "hook": claude / "ballast" / "context_check.py",
        "record": claude / "ballast" / "install-record.json",
        "state": claude / "ballast" / "state",
        "log": claude / "ballast" / "context_check.log",
    }


def target(home_arg):
    """(home, config_dir) for a --home argument. An explicit --home installs under
    <home>/.claude; without it, CLAUDE_CONFIG_DIR (the folder Claude Code reads instead of
    ~/.claude when it is set) is the target, else the current home."""
    if home_arg:
        # A relative or literal "~" home would put a relative path in the hook command, which
        # Claude Code runs from the project folder.
        return Path(home_arg).expanduser().resolve(), None
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path.home().resolve(), (Path(config).expanduser().resolve() if config else None)


def quote(value):
    if os.name == "nt":
        # Double quotes work in cmd.exe, PowerShell and the bash Claude Code uses for hooks. A
        # double quote cannot appear in a Windows path, so the escape below never triggers in
        # practice; it only keeps a quoted value from ending the string early.
        return '"' + str(value).replace('"', '\\"') + '"'
    return shlex.quote(str(value))


def shell_risk(value, windows=None):
    """What bash would change inside the double quotes a Windows hook command uses around a
    path: $name and `cmd` expand, and \\ becomes one backslash (a UNC path). Returns the
    characters found, or None; a POSIX path is single-quoted by shlex and safe as it is."""
    if windows is None:
        windows = os.name == "nt"
    if not windows:
        return None
    found = [c for c in ("$", "`", "\\\\") if c in str(value)]
    return found or None


def hook_command(home, config_dir=None):
    # "|| exit 0": if this settings.json is synced to a machine without the hook file or this
    # interpreter, the shell's failure (exit 2 or 127) must not block every prompt there.
    return f"{quote(sys.executable)} -I {quote(layout(home, config_dir)['hook'])} || exit 0"


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


def merge_settings(existing, template, home, force=False, record=None, previous=None,
                   config_dir=None):
    """Merge template into existing; return (changes, notices).

    When record is a dict, it is filled with what was added or replaced so it can be undone.
    previous holds the values an earlier install wrote; a key still holding one of those is
    updated to a changed template value without --force, since it is not the user's own.
    """
    previous = previous if isinstance(previous, dict) else {}
    if record is None:
        record = {}
    record.setdefault("added_keys", [])
    record.setdefault("replaced", {})
    record.setdefault("deny_added", [])
    record.setdefault("installed", {})
    record.setdefault("created", [])    # containers this install made, for the undo to remove
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
            if key in previous and existing[key] == previous[key]:
                old = existing[key]
                existing[key] = value
                record["installed"][key] = value
                changes.append(f"{key}: {old!r} -> {value!r} (template changed)")
            elif force:
                old = existing[key]
                existing[key] = value
                record["replaced"][key] = old
                record["installed"][key] = value
                changes.append(f"{key}: {old!r} -> {value!r}")
            else:
                notices.append(f"{key} is {existing[key]!r}, template has {value!r}; left unchanged (use --force)")

    template_permissions = template.get("permissions", {})
    if template_permissions:
        if "permissions" not in existing:
            record["created"].append("permissions")
        permissions = existing.setdefault("permissions", {})
        if not isinstance(permissions, dict):
            raise ValueError("permissions must be an object")
        wanted = template_permissions.get("deny", [])
        if "deny" not in permissions:
            record["created"].append("permissions.deny")
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
        if "hooks" not in existing:
            record["created"].append("hooks")
        hooks = existing.setdefault("hooks", {})
        if not isinstance(hooks, dict):
            raise ValueError("hooks must be an object")
        for event, entries in template_hooks.items():
            if not isinstance(entries, list):
                raise ValueError(f"hooks.{event} must be a list")
            if event not in hooks:
                record["created"].append(f"hooks.{event}")
            current = hooks.setdefault(event, [])
            if not isinstance(current, list):
                raise ValueError(f"hooks.{event} must be a list")
            replacement = _template_hook(entries)
            if replacement is None:
                continue
            replacement = dict(replacement)
            replacement["command"] = hook_command(home, config_dir)
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
    """Read a JSON object; a file that is not UTF-8, not JSON or not an object is a ValueError
    naming the file, which main() reports as one line before anything is written."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except UnicodeDecodeError as e:
        raise ValueError(f"{path} is not UTF-8 ({e.reason} at byte {e.start}); save it as UTF-8 first") from None
    except ValueError as e:
        raise ValueError(f"{path} is not valid JSON ({e}); fix it first") from None
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object, not {type(data).__name__}")
    return data


def _refuse_read_only(path):
    """A target that exists but cannot be written, or a folder its write needs that cannot be,
    is a ValueError, raised in the read-and-check phase: refusing it when its turn came (as
    _write_bytes still does) left its backup and the files written before it behind on every
    attempt. os.access sees a POSIX mode or the Windows read-only attribute, not a Windows ACL
    that denies the write: that write fails at its own turn, as before."""
    path = Path(path)
    if path.exists() and not os.access(path, os.W_OK):
        raise ValueError(f"{path} is read-only; make it writable first")
    _refuse_unwritable_folder(path)


def _refuse_unwritable_folder(path, through_link=True):
    """A folder that a write or a removal of path needs but that cannot be written is a
    ValueError: the target's own folder (its temp file, the rename, a backup and an unlink
    happen there), the nearest folder that exists when the target is new, and, for a write
    through a symlinked target, the folder of the file it points at (not for a removal, which
    takes the link itself). A folder on Windows is never read-only to os.access, so there this
    checks nothing; a file in the way of a folder is left to the write to report."""
    path = Path(os.path.abspath(path))
    folders = [path.parent]
    if through_link:
        folders.append(path.resolve().parent)
    for folder in folders:
        while not folder.exists() and folder.parent != folder:
            folder = folder.parent
        if folder.is_dir() and not os.access(folder, os.W_OK):
            raise ValueError(f"{folder} is read-only; make it writable first")


def _backup(path):
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.bak-{stamp}")
    n = 1
    while backup.exists():
        backup = path.with_name(f"{path.name}.bak-{stamp}-{n}")
        n += 1
    shutil.copy2(path, backup)
    return backup


def _new_temp(directory, prefix):
    """Create a new file in directory with the mode a plain write gives (0666 less the umask,
    applied by the kernel), not mkstemp's private 0600; returns (fd, path). The umask is not
    read: reading it means setting it, which leaves a window where another thread's files are
    created unmasked."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    for _ in range(100):
        tmp = os.path.join(directory, prefix + os.urandom(4).hex())
        try:
            return os.open(tmp, flags, 0o666), tmp
        except FileExistsError:
            continue
    raise FileExistsError(errno.EEXIST, "no free temp file name", os.path.join(directory, prefix))


def _is_link(path):
    """A symlink, or on Windows a junction: Path.is_symlink() does not see a junction, while
    shutil.rmtree refuses one and a write through a dangling one fails like a dangling symlink."""
    if Path(path).is_symlink():
        return True
    isjunction = getattr(os.path, "isjunction", None)   # Python 3.12+, Windows only
    return bool(isjunction and isjunction(path))


def _write_bytes(path, data):
    """Write a user file whole or not at all: to a temp file beside it, then rename over it.
    A write that fails part way (disk full, a killed process) leaves the old file as it was
    instead of a truncated one. Writes through a symlink (dotfiles, stow, home-manager)
    instead of replacing the link, and keeps the file's mode; a new file gets the mode a
    plain write would give it. A read-only target is refused, as a plain write refuses it.
    A hard-linked target becomes a new file: the other links keep the old content."""
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not os.access(path, os.W_OK):
        raise PermissionError(errno.EACCES, "the file is read-only; make it writable first", str(path))
    fd, tmp = _new_temp(path.parent, f".{path.name}-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        if path.exists():
            os.chmod(tmp, path.stat().st_mode & 0o7777)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.chmod(tmp, 0o600)   # Windows cannot remove a read-only file
            except OSError:
                pass
            os.remove(tmp)


def _write_json(path, data):
    _write_bytes(path, (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


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
    """The saved install record, or None when there is none.

    A record that exists but cannot be read is an error, not "no record": it holds the values
    an uninstall must put back, so neither install nor uninstall may silently overwrite it.
    """
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except UnicodeDecodeError as e:
        raise ValueError(f"{path} is not UTF-8 ({e.reason} at byte {e.start}); fix it or delete it first") from None
    except ValueError as e:
        raise ValueError(f"{path} is not valid JSON ({e}); fix it or delete it first") from e
    except OSError as e:
        raise ValueError(f"cannot read {path} ({e.strerror or e})") from e
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a JSON object; fix it or delete it first")
    _check_record(path, data)
    return data


def _check_record(path, data):
    """Every field the two scripts read from the record has the type they expect, or the
    record is refused before anything is written: a wrong-typed field used to raise a TypeError
    in _merge_record after CLAUDE.md was replaced, or to be read as something else (a string
    added_keys as its letters). The backup name inside claude_md is left to the uninstall,
    which keeps the file and says so when the name is not usable."""
    def refuse(field, expected, value):
        raise ValueError(f"{path}: {field} must be {expected}, not {value!r}; fix it or delete it first")
    for field in ("added_keys", "deny_added", "created"):
        if field in data and not (isinstance(data[field], list)
                                  and all(isinstance(v, str) for v in data[field])):
            refuse(field, "a list of strings", data[field])
    for field in ("replaced", "installed", "claude_md"):
        if field in data and not isinstance(data[field], dict):
            refuse(field, "an object", data[field])
    for field in ("uninstalled", "unfinished"):
        if field in data and not isinstance(data[field], bool):
            refuse(field, "true or false", data[field])
    if "settings_backup" in data and not isinstance(data["settings_backup"], str):
        refuse("settings_backup", "a string", data["settings_backup"])
    claude_md = data.get("claude_md", {})
    if "sha256" in claude_md and not isinstance(claude_md["sha256"], str):
        refuse("claude_md.sha256", "a string", claude_md["sha256"])


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
    if old.get("uninstalled") and not old.get("unfinished"):
        # After an uninstall only the containers this install sees are ours to delete; the
        # leftover list may name one the uninstall deleted and the user then made by hand. A
        # marker that stayed unfinished never undid settings.json (the file was missing), so
        # the containers it lists are still the interrupted install's.
        created = list(new.get("created", []))
    else:
        created = list(old.get("created", []))
        created += [c for c in new.get("created", []) if c not in created]
    installed = dict(old_installed) if isinstance(old_installed, dict) else {}
    installed.update(new.get("installed", {}))
    merged = {"added_keys": added, "replaced": replaced, "deny_added": deny, "installed": installed}
    if "created" in old or not any(k in old for k in INSTALL_DATA):
        # A record from before "created" was written says nothing about who made the containers;
        # an empty list would say "the install made none", and the uninstall would keep them. A
        # marker record from a clean uninstall ({"uninstalled": true}) holds no install data, so
        # this install's list is written.
        merged["created"] = created
    if "claude_md" in new:
        merged["claude_md"] = new["claude_md"]
    elif "claude_md" in old:
        merged["claude_md"] = old["claude_md"]
    return merged


def install(home, force=False, progress=None, config_dir=None):
    """Install into home (or config_dir, see layout); return (changes, notices). Every
    file-level change is also appended to `progress` (when given) as it happens, so a later
    OSError can still name the backups and files written before it."""
    paths = layout(home, config_dir)
    changes, notices = [], []
    if progress is None:
        progress = []
    record = {}

    # Read and check everything before writing anything, and write settings.json after the
    # hook file: its hook entry must never point at a hook file that was not copied (a missing
    # hook file exits 2, which blocks every prompt).
    for name in ("settings", "claude_md", "hook", "record"):
        if _is_link(paths[name]) and not paths[name].exists():
            raise ValueError(f"{paths[name]} is a symlink to a missing target; fix or remove it first")
    existing = _read_json(paths["settings"]) if paths["settings"].exists() else {}
    template = _read_json(USER_SETTINGS)
    raw_record = read_record(paths["record"])
    old_record = raw_record or {}
    claude_md = _read_text(CLAUDE_MD)
    claude_md_exists = paths["claude_md"].exists()
    current_md = _read_text(paths["claude_md"]) if claude_md_exists else None
    old_md = old_record.get("claude_md")
    # The copy an interrupted install made and recorded, still equal to the file it was taken
    # from (the install never got to replace it): the one to keep, not to make again.
    recorded_copy = None
    if isinstance(old_md, dict) and current_md is not None:
        name = old_md.get("backup")
        if isinstance(name, str) and name and Path(name).name == name:
            candidate = paths["claude_md"].with_name(name)
            if candidate.is_file() and _read_bytes(candidate) == _read_bytes(paths["claude_md"]):
                recorded_copy = candidate
    hook_bytes = _read_bytes(HOOK_SRC)
    hook_exists = paths["hook"].exists()
    current_hook = _read_bytes(paths["hook"]) if hook_exists else None
    settings_before = dict(existing)
    setting_changes, setting_notices = merge_settings(existing, template, home, force, record,
                                                      old_record.get("installed"), config_dir)
    notices.extend(setting_notices)
    hook_changed = current_hook != hook_bytes
    md_changed = current_md != claude_md
    # A record that says the install did not finish (an interrupt before its last write), or
    # that holds no install data without being a marker: the template values settings.json
    # holds are this install's as far as anyone can tell, so they are recorded as installed
    # (the values the uninstall removed "as without a record" until now; a key the record
    # already lists gets its installed value refreshed, since the interrupted run may have
    # written a changed template value over the one recorded) and the record is completed.
    # Template deny tools the record does not list are not claimed: a tool the user denied on
    # their own would be removed by the uninstall, so they are named for the user to check.
    unfinished_old = raw_record is not None and (
        bool(raw_record.get("unfinished"))
        or (not raw_record.get("uninstalled") and not any(k in raw_record for k in INSTALL_DATA)))
    if unfinished_old:
        # A replacement the interrupted run recorded for a key that still holds the replaced
        # value, and that this run does not make (no --force): the write never happened, and
        # keeping the claim would make the undo call the user's own value "not the installed
        # value" and the marker carry the claim for good.
        stale = [k for k, v in old_record.get("replaced", {}).items()
                 if k not in record["replaced"] and existing.get(k) == v]
        if stale:
            old_record = dict(
                old_record,
                replaced={k: v for k, v in old_record["replaced"].items() if k not in stale},
                installed={k: v for k, v in old_record.get("installed", {}).items() if k not in stale})
        known = set(record["added_keys"]) | set(record["replaced"]) | set(record["installed"])
        for field in ("added_keys", "replaced", "installed"):
            known.update(old_record.get(field, ()))
        old_installed = old_record.get("installed")
        old_installed = old_installed if isinstance(old_installed, dict) else {}
        recorded = []
        for key, value in template.items():
            if key in ("hooks", "permissions") or existing.get(key) != value:
                continue
            if key not in known:
                record["added_keys"].append(key)
            if record["installed"].get(key, old_installed.get(key, object())) != value:
                recorded.append(key)
            record["installed"][key] = value
        if not (hook_changed or md_changed or setting_changes):
            changes.append("install record completed")
        permissions = existing.get("permissions")
        deny = permissions.get("deny") if isinstance(permissions, dict) else None
        wanted = template.get("permissions", {}).get("deny", [])
        claimed = set(record["deny_added"]) | set(old_record.get("deny_added", ()))
        unclaimed = ([t for t in deny if t in wanted and t not in claimed]
                     if isinstance(deny, list) else [])
        if recorded or unclaimed:
            what = []
            if recorded:
                what.append("the template values in settings.json are recorded as installed: "
                            + ", ".join(recorded))
            if unclaimed:
                what.append("permissions.deny tools it does not list are not claimed, remove any "
                            "that are not yours by hand: " + ", ".join(unclaimed))
            notices.append("the install record did not finish (an earlier install stopped before "
                           "its last write); " + "; ".join(what))
    writes_record = hook_changed or md_changed or bool(setting_changes) or unfinished_old
    # A read-only target is refused now, while nothing is written yet, not when its turn comes
    # after its backup and the files before it; only the files this run will write are checked,
    # so a read-only file that is already up to date does not stop a re-run.
    for name, will_write in (("hook", hook_changed), ("claude_md", md_changed),
                             ("settings", bool(setting_changes)), ("record", writes_record)):
        if will_write:
            _refuse_read_only(paths[name])

    backup = None
    if md_changed:
        # A file still holding what an earlier install wrote is the installer's own: no backup
        # of it (nothing would restore one), and the first backup stays the one to restore.
        still_ours = (isinstance(old_md, dict) and current_md is not None
                      and old_md.get("sha256") == text_hash(current_md))
        if claude_md_exists and not still_ours and recorded_copy is not None:
            backup = recorded_copy
        elif claude_md_exists and not still_ours:
            backup = _backup(paths["claude_md"])
            changes.append(f"CLAUDE.md backup: {backup.name}")
            progress.append(changes[-1])
        # Keep the first backup when the file is still what an earlier install wrote. If the
        # user edited it since, their edits are what an uninstall should put back.
        if isinstance(old_md, dict) and (current_md is None or "sha256" not in old_md or still_ours):
            record["claude_md"] = dict(old_md, sha256=text_hash(claude_md))
            if backup is not None and "sha256" not in old_md:
                # A record from before the content hash cannot tell the user's edits from the
                # installer's own text, so the first backup stays the one to restore; say so,
                # and name the copy of today's file.
                earlier = old_md.get("backup")
                outcome = (f"uninstall will restore {earlier}" if isinstance(earlier, str) and earlier
                           else "uninstall will delete CLAUDE.md")
                notices.append(f"CLAUDE.md differed from the last install (the record has no content "
                               f"hash, so edits cannot be told apart); today's file is in {backup.name}; "
                               f"{outcome}")
        else:
            record["claude_md"] = {"backup": backup.name if backup else None, "sha256": text_hash(claude_md)}
            if isinstance(old_md, dict) and backup is not None and backup is not recorded_copy:
                notices.append(f"CLAUDE.md had edits made after the last install; uninstall will restore {backup.name}")

    # The record this run writes last: the old one (the data of an earlier, finished install,
    # or the leftovers of the marker an uninstall leaves; the marker key itself is not an
    # install's record) merged with what this run adds, replaces and creates.
    final = _merge_record(old_record, record)
    if unfinished_old and "created" not in old_record and not record["created"]:
        # Who made the containers the interrupted install filled is not known; without the
        # field the uninstall removes the ones it empties, as for a record from before it.
        # The containers this run makes are its own and stay listed.
        final.pop("created", None)
    # The interim record: the same, marked unfinished. It is the run's first write whenever the
    # run writes a file, so an interrupt at any later point leaves a record the uninstall reads
    # as unfinished: it restores what the record lists (a replaced value the run never got to
    # write is left as it is), judges the keys it does not list from the hook evidence, and
    # says so. An interim record without the flag that said "added nothing" was believed by the
    # uninstall after an interrupt at the final record; one without this run's data lost a
    # value --force replaced, or a container this run made, to that interrupt.
    # A key this run changes without replacing it (a changed template value over the one an
    # earlier install wrote) is listed with the value it holds until the settings write: the
    # undo of an interrupt before that write removes the key as it finds it, and one after it
    # tells the write from the template value.
    pre_write = {k: settings_before[k] for k in record["installed"]
                 if k in settings_before and settings_before[k] != existing[k]
                 and k not in record["replaced"]}
    interim = dict(final, installed={**final["installed"], **pre_write}, unfinished=True)
    settings_backup, fresh_settings_backup = None, False
    if setting_changes and paths["settings"].exists():
        # The copy of settings.json is made before the interim record and named in it, so an
        # interrupt before the settings write leaves a copy the undo knows to remove; the copy
        # an interrupted install recorded is reused while it still equals the file.
        name = old_record.get("settings_backup")
        if isinstance(name, str) and name and Path(name).name == name:
            candidate = paths["settings"].with_name(name)
            if candidate.is_file() and _read_bytes(candidate) == _read_bytes(paths["settings"]):
                settings_backup = candidate
        fresh_settings_backup = settings_backup is None
        if fresh_settings_backup:
            settings_backup = _backup(paths["settings"])
        setting_changes.append(f"settings backup: {settings_backup.name}")
        progress.append(setting_changes[-1])
        interim["settings_backup"] = settings_backup.name

    if hook_changed or md_changed or setting_changes:
        # Record the CLAUDE.md change before the file is replaced, and before the hook and
        # settings.json: an interruption between the record and the write leaves the old file,
        # which the next install backs up and installs again; the other order left a template
        # CLAUDE.md with no record of its backup, which the next install saw as already
        # matching and the undo never restored, or a hook beside an untouched marker.
        try:
            _write_json(paths["record"], interim)
        except OSError:
            if backup is not None and backup is not recorded_copy:
                # Nothing records this copy, and the file it copies is still in place: remove
                # it, or the next install makes a second copy of the same file.
                try:
                    backup.unlink()
                except OSError:
                    pass
                else:
                    changes.remove(f"CLAUDE.md backup: {backup.name}")
                    progress.remove(f"CLAUDE.md backup: {backup.name}")
            if settings_backup is not None and fresh_settings_backup:
                try:
                    settings_backup.unlink()
                except OSError:
                    pass
                else:
                    setting_changes.remove(f"settings backup: {settings_backup.name}")
                    progress.remove(f"settings backup: {settings_backup.name}")
            raise

    if hook_changed:
        _write_bytes(paths["hook"], hook_bytes)
        changes.append(f"hook {'updated' if hook_exists else 'written'}")
        progress.append(changes[-1])

    if md_changed:
        paths["claude_md"].parent.mkdir(parents=True, exist_ok=True)
        _write_bytes(paths["claude_md"], claude_md.encode("utf-8"))
        changes.append(f"CLAUDE.md {'updated' if claude_md_exists else 'written'}")
        progress.append(changes[-1])

    if setting_changes:
        _write_json(paths["settings"], existing)
        progress.append("settings.json written")

    # The record describes what was written, so it comes after settings.json: a record of an
    # install that failed would make uninstall report values it never installed. Without a
    # record, uninstall still works from the hook entry as evidence.
    if writes_record:
        _write_json(paths["record"], final)
    return setting_changes + changes, notices


def _interpreter(command):
    """The first word of a hook command: the interpreter it runs. Empty when unreadable."""
    command = command.strip()
    if os.name == "nt":
        if command.startswith('"'):
            end = command.find('"', 1)
            return command[1:end] if end > 0 else ""
        return command.split(" ", 1)[0]
    try:
        words = shlex.split(command)
    except ValueError:
        return ""
    return words[0] if words else ""


def _runnable(exe):
    """True when exe is a path that exists or a bare name found on PATH. ~ and $VAR are expanded
    as the shell would; a Git-Bash path (/c/Users/...) on Windows cannot be checked and passes."""
    exe = os.path.expanduser(os.path.expandvars(exe))
    if os.name == "nt" and exe.startswith("/"):
        return True
    if os.sep in exe or (os.altsep and os.altsep in exe):
        return os.path.exists(exe)
    return shutil.which(exe) is not None


def verify(home, config_dir=None):
    """Return (ok, issues, warnings). Warnings do not fail verification. The hook command
    embeds the interpreter that ran install.py; a deleted venv or a pyenv bump leaves a
    command that "|| exit 0" silences, so the interpreter is checked too."""
    paths = layout(home, config_dir)
    issues, warnings = [], []

    if not paths["settings"].exists():
        issues.append(f"Missing: {paths['settings']}")
    else:
        settings = _read_json(paths["settings"])
        # install keeps a user's own value for these unless --force, so a different value is a
        # warning; a missing one means the install did not happen.
        template = _read_json(USER_SETTINGS)
        for key in ("autoCompactWindow", "skillListingBudgetFraction"):
            expected = template.get(key)
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
            deny = permissions.get("deny")
            if deny is None:
                deny = []
            elif not isinstance(deny, list):
                issues.append(f"permissions.deny is not a list: {deny!r}")
                deny = []
        missing_tools = [tool for tool in REQUIRED_TOOLS if tool not in deny]
        if missing_tools:
            issues.append("permissions.deny is missing: " + ", ".join(missing_tools))
        hooks_obj = settings.get("hooks")
        if not isinstance(hooks_obj, dict):
            issues.append("hooks is not an object")
            hooks = []
        else:
            hooks = hooks_obj.get("UserPromptSubmit", [])
            if not isinstance(hooks, list):
                issues.append(f"hooks.UserPromptSubmit is not a list: {hooks!r}")
                hooks = []
        found = False
        for entry in hooks:
            for hook in _hook_entries(entry):
                if not isinstance(hook, dict):
                    continue
                command = str(hook.get("command", ""))
                if "context_check.py" in command:
                    found = True
                    # The installer writes the path quoted, so a path with a quote in it
                    # (it's/.claude/...) only appears in its quoted form.
                    if str(paths["hook"]) not in command and quote(paths["hook"]) not in command:
                        issues.append(f"Hook command does not point at {paths['hook']}: {command}")
                    exe = _interpreter(command)
                    if exe and not _runnable(exe):
                        issues.append(f"Hook interpreter not found: {exe}; run install.py again "
                                      "to point the hook at the current Python")
        if not found:
            issues.append("Ideal-Umbrella hook not found in UserPromptSubmit")
        risk = shell_risk(paths["hook"])
        if risk:
            warnings.append(f"the hook path holds {' and '.join(risk)}, which bash changes inside the "
                            "double quotes of the hook command; if the hook does not run, install "
                            "from a home path without them")

    if not paths["claude_md"].exists():
        issues.append(f"Missing: {paths['claude_md']}")
    elif paths["claude_md"].read_text(encoding="utf-8", errors="replace") != _read_text(CLAUDE_MD):
        issues.append("CLAUDE.md content differs from config/CLAUDE.md")

    if not paths["hook"].exists():
        issues.append(f"Missing: {paths['hook']}")
    elif paths["hook"].read_bytes() != HOOK_SRC.read_bytes():
        issues.append("Hook content differs from hooks/context_check.py")

    return len(issues) == 0, issues, warnings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.strip())
    parser.add_argument("--home", default=None, help="home folder to install into (default: current home, "
                                                     "or CLAUDE_CONFIG_DIR when it is set)")
    parser.add_argument("--force", action="store_true", help="replace differing scalar settings")
    parser.add_argument("--verify-only", action="store_true", help="check the installation without writing")
    args = parser.parse_args(argv)
    # Paths in the output may hold characters outside the Windows ANSI code page.
    if hasattr(sys.stdout, "reconfigure"):
        # errors= too: reconfigure(encoding=...) alone resets it to strict, and a path from
        # --home or a listing can hold a byte that is no UTF-8 (a surrogate escape).
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    home, config_dir = target(args.home)

    if not args.verify_only:
        print("Installing Ideal-Umbrella user-level configuration...")
        progress = []
        try:
            changes, notices = install(home, force=args.force, progress=progress, config_dir=config_dir)
        except ValueError as e:
            print(f"Error: {e}; nothing written", file=sys.stderr)
            return 1
        except OSError as e:
            # e.g. ~/.claude/ballast exists as a regular file, or a folder is read-only. Every
            # file is written whole or not at all; name what was done so the backups are findable.
            print(f"Error: {e}", file=sys.stderr)
            if progress:
                print("Done before the error:", file=sys.stderr)
                for line in progress:
                    print(f"  - {line}", file=sys.stderr)
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

    try:
        ok, issues, warnings = verify(home, config_dir)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        # e.g. the hook path is a folder: the same one-line report as a failed install.
        print(f"Error: {e}", file=sys.stderr)
        return 1
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
