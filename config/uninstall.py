#!/usr/bin/env python3
"""Ideal-Umbrella: undo what config/install.py did.

Puts back the settings values that were there before the install, removes only the
permissions.deny tools and the hook entry the installer added, deletes the copied hook with
the state folder and log it wrote (<home>/.claude/ballast/state/, context_check.log), and
restores the CLAUDE.md backup (or removes a CLAUDE.md the installer created).
settings.json is backed up before it is rewritten.

It works from <home>/.claude/ballast/install-record.json, which install.py writes, and
compares against the values the install wrote (not the current templates). Afterwards the
record is kept as a marker, so running uninstall again changes nothing. Without a record
(installs made before it existed) it removes the two keys only if they still hold the
template values and the Ideal-Umbrella hook is installed, keeps a backup of CLAUDE.md
before deleting it, removes the hook, and leaves permissions.deny alone. A record that holds
no settings data (an install interrupted before its last write) is handled the same way for
the settings, and the run says so.

A value you changed after installing is left as it is and reported.

Usage:
  python -I config/uninstall.py [--home PATH] [--dry-run]
"""
import argparse
import shutil
import stat
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
    # A record with no settings data (an install interrupted before its last write, or the
    # marker an uninstall leaves) says nothing about settings.json: the keys are then judged
    # as without a record, from the evidence, instead of being trusted as "nothing added".
    has_record = record is not None and any(k in record for k in ("added_keys", "replaced", "installed"))
    unfinished = record is not None and not has_record and not record.get("uninstalled")
    no_record = record is None
    record = record or {}
    replaced = record.get("replaced", {})
    added = record.get("added_keys", [])
    installed = record.get("installed", {})
    # Containers (permissions, permissions.deny, hooks, hooks.<event>) are removed when the
    # undo empties them only if the install created them; one the user had stays, empty. A
    # record from before "created" was written, or no record, says nothing, so those are removed
    # as before.
    created = record.get("created")

    def made(container):
        return not isinstance(created, list) or container in created
    if evidence is None:
        evidence = has_our_hook(settings)

    if has_record:
        keys = list(dict.fromkeys([*added, *replaced]))
    elif evidence:
        keys = list(template)
        if unfinished:
            notices.append("the install record holds no settings data (the install did not finish); "
                           "the template values are removed as without a record")
    else:
        keys = []
        if unfinished:
            notices.append("the install record holds no settings data (the install did not finish) "
                           "and there is no Ideal-Umbrella hook; settings values left as is")
        elif no_record:
            notices.append("no install record and no Ideal-Umbrella hook; settings values left as is")
    for key in keys:
        if key in ("hooks", "permissions"):
            continue
        if key not in settings:
            if key in replaced:
                notices.append(f"{key} was removed after the install; its earlier value "
                               f"{replaced[key]!r} is not put back")
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
            permissions["deny"] = deny
            if not deny and made("permissions.deny"):
                del permissions["deny"]
            if not permissions and made("permissions"):
                del settings["permissions"]
    elif isinstance(permissions, dict) and "deny" in permissions and record.get("deny_added"):
        # A deny that is not a list (a hand edit, a sync tool) holds nothing of ours we can
        # take out; say so and keep deny_added so a later run can still remove the tools.
        notices.append(f"permissions.deny is not a list ({permissions['deny']!r}); left as is")
        left.append("permissions.deny")
    if no_record:
        notices.append("no install record; permissions.deny left as is")
    elif unfinished:
        notices.append("the install record holds no settings data (the install did not finish); "
                       "permissions.deny left as is")

    hooks = settings.get("hooks")
    if isinstance(hooks, dict):
        for event in list(hooks):
            entries = hooks[event]
            if not isinstance(entries, list):
                continue
            kept = _without_our_hooks(entries)
            if kept != entries:
                changes.append(f"hooks.{event}: Ideal-Umbrella hook removed")
                hooks[event] = kept
                if not kept and made(f"hooks.{event}"):
                    del hooks[event]
        if not hooks and made("hooks"):
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
        if "permissions.deny" in left and record.get("deny_added"):
            leftover["deny_added"] = record["deny_added"]
        if isinstance(record.get("created"), list):
            # Whatever a later run still empties, it must know who made the container.
            leftover["created"] = record["created"]
    if record and claude_md_left and record.get("claude_md"):
        leftover["claude_md"] = record["claude_md"]
    return leftover


def _remove(path):
    """Delete a file, clearing a read-only mode first: Windows refuses to delete a file with
    the read-only attribute (a POSIX unlink needs only the folder, so there this changes
    nothing). A symlink is unlinked as it is: a chmod would reach through it."""
    if not path.is_symlink():
        try:
            path.chmod(path.stat().st_mode | stat.S_IWRITE)
        except OSError:
            pass
    path.unlink()


def _backup_of(claude_md, name):
    """The backup file a record names, beside CLAUDE.md; None when the name is not a plain
    file name (not a string, empty, or holding a separator), which the install never writes."""
    if not isinstance(name, str) or not name or Path(name).name != name:
        return None
    try:
        return claude_md.with_name(name)
    except ValueError:
        return None


def uninstall(home, dry_run=False, progress=None, config_dir=None):
    """Undo the install; return (changes, notices). Each change is appended to `progress`
    (when given) once it is done, so an OSError part way can still name the backups made."""
    paths = install.layout(home, config_dir)
    record = install.read_record(paths["record"])
    changes, notices = [], []
    if progress is None:
        progress = []

    def done(change):
        changes.append(change)
        progress.append(change)

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

    # What happens to CLAUDE.md is decided here, before any write, so a read-only file can be
    # refused while nothing has been touched.
    entry = (record or {}).get("claude_md")
    named = entry.get("backup") if isinstance(entry, dict) else None
    backup = _backup_of(claude_md, named)
    if current_md is None:
        ours = False
    elif isinstance(entry, dict) and entry.get("sha256"):
        ours = install.text_hash(current_md) == entry["sha256"]
    else:
        ours = current_md == template_md
    # A backup is restored over the install's own text, or where the file was when the user
    # has deleted it since: the install's write is gone, the backup is what remains to undo.
    restore = backup is not None and backup.exists() and (ours or current_md is None)

    left = []
    setting_changes = []
    if settings is not None:
        setting_changes, notices, left = undo_settings(settings, template, record, evidence)
        changes.extend(setting_changes)
    elif record:
        # Absent is not "nothing to undo": the file may be back later (a sync, a restore), so
        # every recorded key stays in the record for that run.
        left = list(dict.fromkeys([*record.get("added_keys", []), *record.get("replaced", {})]))
        if record.get("deny_added"):
            left.append("permissions.deny")
        if left:
            notices.append(f"{paths['settings']} is missing; the values recorded for it are kept "
                           "in the record for a later run")
    if not dry_run:
        # A read-only target is refused before the settings backup; refusing it at its own
        # write left one more orphan settings.json.bak-* on every run.
        if setting_changes:
            install._refuse_read_only(paths["settings"])
        if restore:
            install._refuse_read_only(claude_md)
        if record is not None or paths["record"].exists():
            install._refuse_read_only(paths["record"])
        # The folder of each file this run removes, for the same reason: a hook folder that
        # cannot be written was found by the unlink, after settings.json was backed up and
        # rewritten ("the undo stopped part way" on every run).
        removals = [paths["hook"]] if paths["hook"].exists() else []
        if install._is_link(paths["state"]) or paths["state"].is_dir():
            removals.append(paths["state"])
        if paths["log"].is_file():
            removals.append(paths["log"])
        if restore:
            removals.append(backup)
        elif (current_md is not None and ours and named is None
              and (entry is not None if record is not None else evidence)):
            removals.append(claude_md)             # the delete branches below
        for path in removals:
            install._refuse_unwritable_folder(path, through_link=False)
    if setting_changes and not dry_run:
        backup_settings = install._backup(paths["settings"])
        done(f"settings backup: {backup_settings.name}")
        install._write_json(paths["settings"], settings)
        progress.append("settings.json written")

    if paths["hook"].exists():
        if dry_run:
            changes.append("hook deleted")
        else:
            _remove(paths["hook"])
            done("hook deleted")
    # What the hook wrote while it ran: the per-session state files and its log. A state folder
    # that is a symlink, or a junction on Windows, is unlinked, not followed (shutil.rmtree
    # refuses both; Path.is_symlink() sees only the symlink).
    if install._is_link(paths["state"]):
        if dry_run:
            changes.append("state link removed")
        else:
            paths["state"].unlink()
            done("state link removed")
    elif paths["state"].is_dir():
        if dry_run:
            changes.append("state folder deleted")
        else:
            shutil.rmtree(paths["state"])
            done("state folder deleted")
    if paths["log"].is_file():
        if dry_run:
            changes.append("log deleted")
        else:
            _remove(paths["log"])
            done("log deleted")

    claude_md_left = False
    if restore:
        if dry_run:
            changes.append(f"CLAUDE.md restored from {backup.name}")
        else:
            # Whole or not at all, and through a symlinked CLAUDE.md rather than over the
            # link; a copy that fails part way must not leave a truncated file.
            install._write_bytes(claude_md, backup.read_bytes())
            done(f"CLAUDE.md restored from {backup.name}")
            _remove(backup)
    elif named is not None and (ours or current_md is None):
        # The install replaced a file of yours and the record names its backup, but the backup
        # is gone or the name is not a plain file name: deleting now would lose the only copy
        # left, so keep the file and the record entry, and say so.
        claude_md_left = True
        where = "CLAUDE.md left as is" if current_md is not None else "CLAUDE.md is already gone"
        if backup is None:
            notices.append(f"{where}: the record names a backup that is not a plain file name "
                           f"({named!r}); fix the record first")
        else:
            notices.append(f"{where}: the backup {backup.name} it should be restored from is missing")
    elif current_md is None:
        pass    # deleted by the user, and the install made it: nothing left to undo
    elif not ours:
        claude_md_left = True
        notices.append("CLAUDE.md differs from what was installed; left as is"
                       + (f" (your earlier file is in {backup.name})" if backup and backup.exists() else ""))
    else:
        if record is not None and entry is not None:
            if dry_run:
                changes.append("CLAUDE.md deleted")
            else:
                _remove(claude_md)
                done("CLAUDE.md deleted")
        elif record is not None and entry is None:
            # The record says this install never wrote CLAUDE.md (the file already matched the
            # template), so it is the user's own: say so rather than pass over it in silence.
            notices.append("CLAUDE.md matches the template but was not written by this install; left as is")
        elif record is None and evidence:
            # Without a record it may be the user's own copy: keep one.
            if dry_run:
                changes.append("CLAUDE.md deleted (a backup is kept)")
            else:
                copy = install._backup(claude_md)
                _remove(claude_md)
                done(f"CLAUDE.md deleted (copy kept as {copy.name})")

    if (record is not None or paths["record"].exists()) and not dry_run:
        install._write_json(paths["record"], _leftover_record(record, left, claude_md_left))
    return changes, notices


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.strip(),
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--home", default=None, help="home folder to uninstall from (default: current home, "
                                                     "or CLAUDE_CONFIG_DIR when it is set)")
    parser.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
    args = parser.parse_args(argv)
    # Paths in the output may hold characters outside the Windows ANSI code page.
    if hasattr(sys.stdout, "reconfigure"):
        # errors= too: reconfigure(encoding=...) alone resets it to strict, and a path from
        # --home or a listing can hold a byte that is no UTF-8 (a surrogate escape).
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

    home, config_dir = install.target(args.home)
    progress = []
    try:
        changes, notices = uninstall(home, dry_run=args.dry_run, progress=progress, config_dir=config_dir)
    except ValueError as e:
        # Raised while reading, before any write.
        print(f"Error: {e}; nothing written", file=sys.stderr)
        return 1
    except OSError as e:
        # e.g. the hook path is a folder, or a file is read-only. Files already undone stay
        # undone; a second run after fixing the cause finishes the rest.
        print(f"Error: {e}; the undo stopped part way, fix the cause and run again", file=sys.stderr)
        if progress:
            print("Done before the error:", file=sys.stderr)
            for line in progress:
                print(f"  - {line}", file=sys.stderr)
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
