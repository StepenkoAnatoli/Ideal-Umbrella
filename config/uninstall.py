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
before deleting it, removes the hook, and leaves permissions.deny alone. An unfinished record
(an install interrupted before its last write) restores the values it lists, is handled the
same way for the other template keys and for permissions.deny, and the run says so.

A value you changed after installing is left as it is and reported.

Usage:
  python -I config/uninstall.py [--home PATH] [--dry-run]
"""
import argparse
import os
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


def _is_unfinished(record):
    """Whether the record is of an install interrupted before its last write: marked so, or
    one with no settings data that is not the marker an uninstall leaves."""
    return record is not None and (bool(record.get("unfinished")) or (
        not record.get("uninstalled") and not any(k in record for k in install.INSTALL_DATA)))


def undo_settings(settings, template, record, evidence=None):
    """Undo the install in settings (in place); return (changes, notices, keys left as is).

    Values are compared with what the install wrote (kept in the record), falling back to
    the template for older records. Without a record, the keys are removed only when there
    is evidence of an install (evidence; by default, our hook entry in settings).
    """
    changes, notices, left = [], [], []
    # An unfinished record says nothing about the keys it does not list: those are judged as
    # without a record, from the evidence, instead of being trusted as "nothing added". What
    # it lists (this run's data, the leftovers of an earlier run) is restored as from a full
    # record, except a replaced key still holding the value to put back: the interrupted
    # install never got to write it, or the user put it back, and nothing is left to undo.
    has_record = record is not None and any(k in record for k in install.INSTALL_DATA)
    unfinished = _is_unfinished(record)
    no_record = record is None
    record = record or {}
    replaced = record.get("replaced", {})
    added = record.get("added_keys", [])
    installed = record.get("installed", {})
    pre_write = record.get("pre_write", [])     # listed with the value held before the write
    # Containers (permissions, permissions.deny, hooks, hooks.<event>) are removed when the
    # undo empties them only if the install created them; one the user had stays, empty. A
    # record from before "created" was written, or no record, says nothing, so those are removed
    # as before.
    created = record.get("created")

    def made(container):
        return not isinstance(created, list) or container in created
    if evidence is None:
        evidence = has_our_hook(settings)

    recorded = list(dict.fromkeys([*added, *replaced]))
    unlisted = [k for k in template if k not in recorded and k not in ("hooks", "permissions")]
    judged = []     # unlisted keys removed from the evidence under an unfinished record
    if has_record and not unfinished:
        keys = recorded
    elif evidence:
        keys = recorded + unlisted
    else:
        keys = recorded
        if unfinished:
            held = [k for k in unlisted if k in settings and settings[k] == template[k]]
            if held:
                notices.append("the install record is of an install that did not finish, and there "
                               "is no Ideal-Umbrella hook; settings values it does not list are "
                               "left as is: " + ", ".join(held))
        elif no_record:
            notices.append("no install record and no Ideal-Umbrella hook; settings values left as is")
    for key in keys:
        if key not in settings:
            if key in replaced and unfinished:
                notices.append(f"{key} is not there; the value {replaced[key]!r} an install that "
                               "did not finish listed as replaced is not put back")
            elif key in replaced:
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
            if unfinished and key in replaced and settings[key] == replaced[key]:
                continue    # the value to put back is in place: the write never happened
            if unfinished and key in pre_write and key in template and settings[key] == template[key]:
                # An unfinished record lists a key it changes with the value it held before
                # the settings write, and names it in pre_write; the template value in its
                # place is the interrupted run's write. For any other listed key the template
                # value is the user's own, set by hand: the run never wrote it.
                pass
            elif unfinished and key in unlisted:
                # Judged from the evidence, as without a record: the record never claimed it,
                # so there is nothing of it to keep in the marker.
                notices.append(f"{key} is {settings[key]!r}, not the template value, and the record "
                               "of the install that did not finish does not list it; left as is")
                continue
            else:
                notices.append(f"{key} is {settings[key]!r}, not the installed value; left as is")
                left.append(key)
                continue
        if key in replaced:
            settings[key] = replaced[key]
            changes.append(f"{key}: restored {replaced[key]!r}")
        else:
            del settings[key]
            changes.append(f"{key}: removed")
            if unfinished and key in unlisted:
                judged.append(key)
    if judged:
        notices.append("the install record is of an install that did not finish; template values "
                       "it does not list are removed as without a record: " + ", ".join(judged))

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
        # Only template tools can be the interrupted install's; the user's own are theirs.
        wanted = template.get("permissions", {}).get("deny", [])
        deny = permissions.get("deny") if isinstance(permissions, dict) else None
        unclaimed = ([t for t in deny if t in wanted and t not in record.get("deny_added", [])]
                     if isinstance(deny, list) else [])
        if unclaimed:
            notices.append("the install record is of an install that did not finish; permissions.deny "
                           "tools it does not list are left as is: " + ", ".join(unclaimed))

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


def _leftover_record(record, left, claude_md_left, unfinished=False):
    """What an uninstall keeps of the record: a marker that it ran, plus anything left as is,
    so a second run neither falls back to no-record mode nor forgets a pending backup. With
    `unfinished` (an unfinished record whose settings.json was not there to undo) the flag
    stays, so the run that finds the file back still judges the keys it does not list."""
    leftover = {"uninstalled": True}
    if unfinished:
        leftover["unfinished"] = True
    if record and left:
        # Only the fields the record holds: a record with no settings data (an interrupted
        # install) keeps none, since empty ones would read as a full record on the next run.
        # Only the fields the record holds, and only with something in them: an empty one
        # says nothing a later run needs.
        for field in ("added_keys", "replaced", "installed"):
            if field in record:
                kept = ([k for k in record[field] if k in left] if field == "added_keys"
                        else {k: v for k, v in record[field].items() if k in left})
                if kept:
                    leftover[field] = kept
        if "permissions.deny" in left and record.get("deny_added"):
            leftover["deny_added"] = record["deny_added"]
        if isinstance(record.get("created"), list):
            # Whatever a later run still empties, it must know who made the container.
            leftover["created"] = record["created"]
    if record and claude_md_left and record.get("claude_md"):
        leftover["claude_md"] = record["claude_md"]
    if unfinished and isinstance(record.get("settings_backup"), str):
        leftover["settings_backup"] = record["settings_backup"]
    if unfinished and "installed" in leftover:
        # The keys listed with their pre-write value stay named as such, or the run that finds
        # settings.json back reads the template value the interrupted run wrote as the user's.
        pre_write = [k for k in record.get("pre_write", []) if k in leftover["installed"]]
        if pre_write:
            leftover["pre_write"] = pre_write
    return leftover


def _clear_read_only(path):
    """Clear a read-only mode: Windows refuses to delete a file with the read-only attribute
    (a POSIX unlink needs only the folder, so there this changes nothing). A symlink is left
    as it is: a chmod would reach through it."""
    if not path.is_symlink():
        try:
            path.chmod(path.stat().st_mode | stat.S_IWRITE)
        except OSError:
            pass


def _remove(path):
    """Delete a file, clearing a read-only mode first (see _clear_read_only)."""
    _clear_read_only(path)
    path.unlink()


def _remove_tree(path):
    """Delete a folder and what it holds, clearing a read-only mode on the folder, each
    sub-folder and each file first: shutil.rmtree does not, and on Windows stops at the first
    read-only file or folder (RemoveDirectory refuses the attribute as DeleteFile does). On
    POSIX a folder that holds entries and lacks the write bit was refused by
    _refuse_unremovable_tree before the first write, so the chmod changes nothing there."""
    for folder, _, names in os.walk(path):
        _clear_read_only(Path(folder))
        for name in names:
            _clear_read_only(Path(folder, name))
    shutil.rmtree(path)


def _refuse_unremovable_tree(root):
    """What shutil.rmtree needs of the folder tree under root, checked before the first write,
    as a ValueError naming the folder: every folder must be listable (rmtree opens and lists
    each one; a folder with no read bit or no search bit is passed over by a plain os.walk
    without a word), and a folder that holds entries must be writable and searchable (each
    entry is unlinked or removed inside it; the write bit alone, mode 0o644, is not enough).
    An empty folder is refused without its read bit like any other (rmtree opens it before
    it finds it empty); one that is read-only but listable needs nothing of its own, since
    rmdir needs only its parent, which the caller checks for root. The state folder itself is
    checked the same way. The message names the missing bit (read, write or search), so a folder
    that is writable but cannot be entered (0o644) is not called read-only. On Windows
    os.access sees no folder as read-only, so this checks nothing;
    _remove_tree clears the read-only attribute there. A symlinked sub-folder is unlinked, not
    walked, so what it points at is not checked."""
    def unlistable(error):
        raise ValueError(f"{error.filename or root} cannot be read; make it readable first") from error
    for folder, dirs, names in os.walk(root, onerror=unlistable):
        if (dirs or names) and not os.access(folder, os.W_OK):
            raise ValueError(f"{folder} is read-only; make it writable first")
        if (dirs or names) and not os.access(folder, os.X_OK):
            raise ValueError(f"{folder} cannot be entered; make it searchable first")


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
    backup = install._backup_of(claude_md, named)
    if current_md is None:
        ours = False
    elif isinstance(entry, dict) and entry.get("sha256"):
        ours = install.text_hash(current_md) == entry["sha256"]
    else:
        ours = current_md == template_md
    # A backup is restored over the install's own text, or where the file was when the user
    # has deleted it since: the install's write is gone, the backup is what remains to undo.
    restore = backup is not None and backup.exists() and (ours or current_md is None)
    # The copy an install made of the user's file before it was interrupted, with the file
    # never replaced: the file is the user's own and the copy has nothing to restore.
    orphan_copy = False
    if backup is not None and current_md is not None and not ours and backup.exists():
        try:
            orphan_copy = backup.read_bytes() == claude_md.read_bytes()
        except OSError as e:
            raise ValueError(f"cannot read {backup} ({e.strerror or e})") from e

    # The copy an interrupted install made of settings.json before a write it never got to:
    # still equal to the file, or differing while the file shows nothing of that write (the
    # user edited it since), it has nothing to restore and is removed. One that differs after
    # the write is a backup of the file the run did replace, and stays. A name the installer
    # never writes (the file itself, a sibling, a path) names no copy, and a copy that is gone
    # is named, as a missing CLAUDE.md backup is.
    orphan_settings_copy, settings_copy_notice = None, None
    if settings is not None and _is_unfinished(record) and "settings_backup" in record:
        named_settings_copy = record["settings_backup"]
        candidate = install._backup_of(paths["settings"], named_settings_copy)
        if candidate is None:
            settings_copy_notice = (f"the record names a copy of settings.json that is not a name the "
                                    f"installer writes ({named_settings_copy!r}); nothing removed")
        elif not candidate.is_file():
            settings_copy_notice = (f"the copy of settings.json the record names ({candidate.name}) is "
                                    "missing; nothing removed")
        else:
            try:
                same = candidate.read_bytes() == paths["settings"].read_bytes()
            except OSError as e:
                raise ValueError(f"cannot read {candidate} ({e.strerror or e})") from e
            if same or install._settings_write_pending(record, settings):
                orphan_settings_copy = candidate

    left = []
    setting_changes = []
    if settings is not None:
        setting_changes, setting_notices, left = undo_settings(settings, template, record, evidence)
        changes.extend(setting_changes)
        notices.extend(setting_notices)
    elif record:
        # Absent is not "nothing to undo": the file may be back later (a sync, a restore), so
        # every recorded key stays in the record for that run.
        left = list(dict.fromkeys([*record.get("added_keys", []), *record.get("replaced", {})]))
        if record.get("deny_added"):
            left.append("permissions.deny")
        if left:
            notices.append(f"{paths['settings']} is missing; the values recorded for it are kept "
                           "in the record for a later run")
    if settings_copy_notice is not None:
        notices.append(settings_copy_notice)
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
        if restore or orphan_copy:
            removals.append(backup)
        elif (current_md is not None and ours and named is None
              and (entry is not None if record is not None else evidence)):
            removals.append(claude_md)             # the delete branches below
        if orphan_settings_copy is not None:
            removals.append(orphan_settings_copy)
        for path in removals:
            install._refuse_unwritable_folder(path, through_link=False)
        # The state folder's own tree too: rmtree lists it and its sub-folders and unlinks
        # inside the ones that hold entries.
        if paths["state"] in removals and not install._is_link(paths["state"]):
            _refuse_unremovable_tree(paths["state"])
    if orphan_settings_copy is not None:
        change = (f"settings.json backup {orphan_settings_copy.name} removed (settings.json was "
                  "never replaced)")
        if dry_run:
            changes.append(change)
        else:
            _remove(orphan_settings_copy)
            done(change)
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
            _remove_tree(paths["state"])
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
            notices.append(f"{where}: the record names a backup that is not a name the installer "
                           f"writes ({named!r}); fix the record first")
        else:
            notices.append(f"{where}: the backup {backup.name} it should be restored from is missing")
    elif current_md is None:
        pass    # deleted by the user, and the install made it: nothing left to undo
    elif orphan_copy:
        if dry_run:
            changes.append(f"CLAUDE.md backup {backup.name} removed (CLAUDE.md is still your own file)")
        else:
            _remove(backup)
            done(f"CLAUDE.md backup {backup.name} removed (CLAUDE.md is still your own file)")
    elif not ours and record is not None and entry is None:
        pass    # the record says the install never wrote CLAUDE.md: the file is the user's own
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
        install._write_json(paths["record"], _leftover_record(
            record, left, claude_md_left, unfinished=settings is None and _is_unfinished(record)))
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
