#!/usr/bin/env python3
"""Ideal-Umbrella: undo what config/install.py did.

Puts back the settings values that were there before the install, removes only the
permissions.deny tools and the hook entry the installer added, deletes the copied hook with
the state folder and log it wrote (<home>/.claude/ballast/state/, context_check.log), and
removes the marked Ideal-Umbrella section from CLAUDE.md (the rest of the file stays; a file
left with nothing but that section is deleted if the install created it, or replaced by the
backup an earlier whole-file install made). settings.json is backed up before it is rewritten.

It works from <home>/.claude/ballast/install-record.json, which install.py writes, and
compares against the values the install wrote (not the current templates). Afterwards the
record is kept as a marker, so running uninstall again changes nothing. Without a record
(installs made before it existed) it removes the two keys only if they still hold the
template values and the Ideal-Umbrella hook is installed, keeps a backup of CLAUDE.md
before removing the section (or the whole file, from a whole-file install), removes the
hook, and leaves permissions.deny alone.

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
        if key in replaced and settings[key] == replaced[key] and settings[key] != expected:
            # The value from before the install is still there: the install recorded it, then
            # stopped before its settings.json write. Nothing to undo.
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


def _backup_of(claude_md, name):
    """The backup file a record names, beside CLAUDE.md; None when the name is not one the
    installer gives (install.backup_of)."""
    return install.backup_of(claude_md, name)


def _rest_without_section(current, found, entry):
    """CLAUDE.md as it was before the install added its section: the marker lines go, and
    unless the install only wrapped a copy the user had, the rules between them and the
    separator the install put before them (when the section is still at the end)."""
    start, body_start, body_end, end = found
    if entry.get("wrapped") is True:
        return current[:start] + current[body_start:body_end] + current[end:]
    before, after = current[:start], current[end:]
    joined = entry.get("joined")
    if not after and isinstance(joined, str) and joined and not joined.strip("\r\n"):
        # The separator is a number of line breaks, not the bytes recorded: an editor or git
        # may have changed the file's line endings since the install.
        cut = before
        for _ in range(joined.count("\n")):
            if not cut.endswith("\n"):
                break
            cut = cut[:-2] if cut.endswith("\r\n") else cut[:-1]
        else:
            # A single break is added only after text that already ends in one (install.py), so
            # when the text is left without one, the break was the user's: the blank line is gone.
            if joined.count("\n") > 1 or cut.endswith("\n"):
                before = cut
    return before + after


def _blank(text):
    """True when text holds nothing but whitespace and a BOM, which no editor shows."""
    return not text.lstrip("\ufeff").strip()


def _is_file(path):
    """A backup that can hold the user's file: a file, not a symlink or a folder."""
    return path is not None and path.is_file() and not path.is_symlink()


def _is_target(backup, claude_md):
    """True when CLAUDE.md is a link to this backup (put back with `ln -s` rather than a copy):
    deleting the backup would delete the file. When it cannot be told, the backup is kept."""
    return install.same_file(backup, claude_md)


def _empty(claude_md):
    """Delete CLAUDE.md, or empty it through a symlink (dotfiles, stow): the file
    the link points at would otherwise keep what is being removed, and the next stow would put
    it back. Returns the change to report."""
    if install._is_link(claude_md):
        return "CLAUDE.md emptied (it is a link; the link is kept)", lambda: install._write_bytes(claude_md, b"")
    return "CLAUDE.md deleted", claude_md.unlink


def _undo_section(claude_md, current, utf8, found, entry, apply, notices):
    """Remove the section install added to CLAUDE.md; return True when the file is left as
    is with the record entry kept, so a later run can still undo it."""
    legacy = entry.get("legacy_backup")
    legacy_path = _backup_of(claude_md, legacy) if legacy else None
    safety = _backup_of(claude_md, entry.get("safety_backup"))
    on_disk = claude_md.read_bytes()
    # A backup CLAUDE.md is a link to (put back with `ln -s`) is the file itself, not a copy of
    # it: it is never compared with the file, restored from, deleted or named as kept.
    linked = legacy_linked = None
    if _is_file(safety) and _is_target(safety, claude_md):
        safety, linked = None, safety.name
    if _is_file(legacy_path) and _is_target(legacy_path, claude_md):
        legacy, legacy_path, linked = None, None, legacy
        legacy_linked = linked

    def leave():
        # The file stays as it is and the record entry goes, so no later run looks at the
        # backups again: delete one that holds the same bytes as the file, and name the rest.
        # A run that stopped after its CLAUDE.md step never printed its notes; this gives them.
        if _is_file(safety):
            if safety.read_bytes() == on_disk:
                apply(f"CLAUDE.md backup {safety.name} deleted (CLAUDE.md holds the same bytes)",
                      lambda: install.remove(safety))
            else:
                notices.append(f"your CLAUDE.md from before the install is kept in {safety.name}; "
                               "it differs from the file now, so delete it once you no longer need it")
        if _is_file(legacy_path) and legacy_path != safety:   # one file in both roles: done above
            if legacy_path.read_bytes() == on_disk:
                apply(f"CLAUDE.md backup {legacy} deleted (CLAUDE.md holds the same bytes)",
                      lambda: install.remove(legacy_path))
            else:
                notices.append(f"your CLAUDE.md from before the first install is still in {legacy}")
        return False

    if _is_file(safety) and safety.read_bytes() == on_disk:
        # The install recorded its section and made this backup, then stopped before its
        # CLAUDE.md write (or the user put the file back as it was): the file is the backup,
        # and a section in it is one the user had before the install.
        return leave()
    if found is None:
        if linked:
            # The user put the file back by linking it to its backup.
            pass
        elif safety is not None and not (safety.exists() or safety.is_symlink()):
            # The install recorded its section, then stopped before it made the backup it
            # named, so CLAUDE.md was never touched; or an earlier uninstall removed the
            # section and the backup with the same bytes, then stopped before its last step.
            pass
        elif _is_file(legacy_path) and legacy_path.read_bytes() == on_disk:
            # An earlier uninstall restored the file from this backup, then stopped before it
            # deleted the backup.
            pass
        elif legacy and not (legacy_path is not None and (legacy_path.exists() or legacy_path.is_symlink())):
            # An earlier uninstall restored the file from this backup and deleted it, then
            # stopped before it wrote the record: nothing is left to undo.
            pass
        else:
            # Or the user took the section out by hand.
            notices.append("CLAUDE.md has no Ideal-Umbrella section; left as is")
        return leave()
    if entry.get("hand_section") is True:
        # The user added the section by hand before the install updated its rules: it is theirs,
        # and it stays whole, marker lines included.
        notices.append("CLAUDE.md's Ideal-Umbrella section was added by hand; left as is"
                       + (f" (your file from before the install changed its rules is in {safety.name})"
                          if _is_file(safety) else ""))
        return False
    number = install.fenced_line(current, found)
    if number is not None:
        notices.append(f"{install.fence_advice(number)}, and run uninstall again; left as is")
        return True
    if install.text_hash(install.section_text(install.section_body(current, found))) != entry.get("sha256"):
        notices.append("the Ideal-Umbrella section of CLAUDE.md differs from what was installed; left as is"
                       + (f" (your file from before the install is in {safety.name})" if _is_file(safety) else ""))
        edited = _backup_of(claude_md, entry.get("edited_backup"))
        if _is_file(edited) and edited.read_bytes() == on_disk and not _is_target(edited, claude_md):
            # The install backed up the user's edits, then stopped before its CLAUDE.md write:
            # the file still holds those edits, so the copy names nothing that is not in it.
            apply(f"CLAUDE.md backup {edited.name} deleted (CLAUDE.md holds the same bytes)",
                  lambda: install.remove(edited))
        return True
    if not utf8:
        # The text was decoded with replacement characters; writing it back would change the
        # bytes that are not UTF-8.
        notices.append("CLAUDE.md is not UTF-8; left as is with its Ideal-Umbrella section")
        return True
    rest = _rest_without_section(current, found, entry)

    def finish(change, final, action):
        # The copy install made before adding the section is deleted once the file ends up
        # with the same bytes; one that differs (the user changed their own text since) is kept.
        if _is_file(safety) and safety.read_bytes() != final:
            notices.append(f"your CLAUDE.md from before the install is kept in {safety.name}; "
                           "it differs from the file now, so delete it once you no longer need it")

        def act():
            action()
            if _is_file(safety) and safety.read_bytes() == final:
                install.remove(safety)
        apply(change, act)
        return False

    if _blank(rest):
        if legacy_linked:
            # The file from before the first install holds nothing but the section, and it is
            # CLAUDE.md: taking the section out would leave nothing of it.
            notices.append(f"CLAUDE.md is a link to {legacy_linked}, your file from before the first "
                           "install, and holds nothing but the Ideal-Umbrella section; left as is")
            return leave()
        if legacy:
            if not _is_file(legacy_path):
                # The install replaced a file of yours and its backup is gone: removing the
                # section would leave nothing of it, so keep the file and say so.
                notices.append(f"CLAUDE.md left as is: the backup {legacy} it should be restored from is missing")
                return True
            old = legacy_path.read_bytes()

            def restore():
                # Whole or not at all, and through a symlinked CLAUDE.md rather than over the
                # link; a copy that fails part way must not leave a truncated file.
                install._write_bytes(claude_md, old)
                install.remove(legacy_path)
            return finish(f"CLAUDE.md restored from {legacy}", old, restore)
        if entry.get("created") is True:
            change, delete = _empty(claude_md)
            return finish(change, b"", delete)
    data = rest.encode("utf-8")
    finish("CLAUDE.md: Ideal-Umbrella section removed", data, lambda: install._write_bytes(claude_md, data))
    if _is_file(legacy_path) and legacy_path != safety:   # finish() named or deleted it
        notices.append(f"your CLAUDE.md from before the first install is still in {legacy}")
    return False


def uninstall(home, dry_run=False, progress=None, config_dir=None):
    """Undo the install; return (changes, notices). Each change is appended to `progress`
    (when given) once it is done, so an OSError part way can still name the backups made."""
    paths = install.layout(home, config_dir)
    # As install refuses them: read as missing files, they would lose their undo for good.
    install.refuse_dangling(paths[name] for name in ("settings", "claude_md", "hook", "record"))
    record = install.read_record(paths["record"])
    changes, notices = [], []
    if progress is None:
        progress = []

    def done(change):
        changes.append(change)
        progress.append(change)

    def apply(change, action):
        if dry_run:
            changes.append(change)
        else:
            action()
            done(change)

    # Read everything first, so a read error leaves every file as it was.
    settings = install._read_json(paths["settings"]) if paths["settings"].exists() else None
    template = install._read_json(install.USER_SETTINGS)
    claude_md = paths["claude_md"]
    # A CLAUDE.md that is not UTF-8 cannot be the one install wrote; decoding it with
    # replacement characters makes it compare as "not ours" instead of blocking the undo.
    # Line ends are kept as they are, so the text outside the section is written back unchanged.
    try:
        raw_md = claude_md.read_bytes() if claude_md.exists() else None
    except OSError as e:
        raise ValueError(f"cannot read {claude_md} ({e.strerror or e})") from e
    current_md = raw_md.decode("utf-8", errors="replace") if raw_md is not None else None
    md_utf8 = raw_md is not None and current_md.encode("utf-8") == raw_md
    record = install.settle_record(record, settings, current_md)
    try:
        entry = (record or {}).get("claude_md")
        recorded = entry.get("sha256") if isinstance(entry, dict) and entry.get("format") == "section" else None
        found = install.find_section(current_md, recorded) if current_md is not None else None
    except ValueError as e:
        raise ValueError(f"{claude_md}: {e}") from None
    template_md = install._read_text(install.CLAUDE_MD)
    evidence = paths["hook"].exists() or (settings is not None and has_our_hook(settings))

    left, setting_changes = [], []
    if settings is not None:
        setting_changes, notices, left = undo_settings(settings, template, record, evidence)

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
            install.remove(paths["log"])
            done("log deleted")

    claude_md_left = False
    if current_md is None:
        # Nothing is left to undo in it and the record entry goes, so no later run names the
        # backups that hold a file of the user's: name them now.
        if isinstance(entry, dict):
            kept = (("safety_backup", "the install"), ("legacy_backup", "the first install")) \
                if entry.get("format") == "section" else (("backup", "the install"),)
            named = set()
            for key, which in kept:
                path = _backup_of(claude_md, entry.get(key))
                if _is_file(path) and path not in named:   # one file in both roles is named once
                    named.add(path)
                    notices.append(f"CLAUDE.md is gone; your file from before {which} is still in {path.name}")
    elif isinstance(entry, dict) and entry.get("format") == "section":
        claude_md_left = _undo_section(claude_md, current_md, md_utf8, found, entry, apply, notices)
    elif found is not None and not isinstance(entry, dict):
        ours = install.section_text(install.section_body(current_md, found)) == install.section_text(template_md)
        if record is not None:
            if ours:
                # The record says this install never wrote the section (it was already there),
                # so it is the user's own: say so rather than pass over it in silence.
                notices.append("CLAUDE.md's Ideal-Umbrella section matches the template but was not "
                               "written by this install; left as is")
            else:
                notices.append("the Ideal-Umbrella section of CLAUDE.md differs from config/CLAUDE.md "
                               "and was not written by this install; left as is")
        elif evidence and not ours:
            notices.append("the Ideal-Umbrella section of CLAUDE.md differs from config/CLAUDE.md; left as is")
        elif evidence and not md_utf8:
            notices.append("CLAUDE.md is not UTF-8; left as is with its Ideal-Umbrella section")
        elif evidence:
            # Without a record it may be the user's own copy: keep one.
            rest = _rest_without_section(current_md, found, {})
            if dry_run:
                changes.append("CLAUDE.md: Ideal-Umbrella section removed (a backup is kept)")
            else:
                backup = install._backup(claude_md)
                progress.append(f"CLAUDE.md backup: {backup.name}")
                if not _blank(rest):
                    install._write_bytes(claude_md, rest.encode("utf-8"))
                    done(f"CLAUDE.md: Ideal-Umbrella section removed (copy kept as {backup.name})")
                else:
                    change, delete = _empty(claude_md)
                    delete()
                    done(f"{change} (copy kept as {backup.name})")
    elif record is not None and entry is None:
        # The record names no CLAUDE.md change: this install never wrote it (the file already
        # matched the template), or an earlier uninstall undid it. Either way it is the user's.
        if install._lf(current_md) == install._lf(template_md):
            notices.append("CLAUDE.md matches the template but was not written by this install; left as is")
    else:
        # A record of the whole-file installer (or none, from before records existed): the
        # whole file was the rules.
        if isinstance(entry, dict) and entry.get("sha256"):
            ours = install.text_hash(install._lf(current_md)) == entry["sha256"]
        else:
            ours = install._lf(current_md) == install._lf(template_md)
        backup = _backup_of(claude_md, entry.get("backup") if isinstance(entry, dict) else None)
        if _is_file(backup) and backup.read_bytes() == raw_md:
            # An earlier uninstall restored the file from this backup, then stopped before it
            # deleted the backup (or the user copied it back by hand, or linked it).
            if not _is_target(backup, claude_md):
                apply(f"CLAUDE.md backup {backup.name} deleted (CLAUDE.md holds the same bytes)",
                      lambda: install.remove(backup))
        elif not ours and backup is not None and not (backup.exists() or backup.is_symlink()):
            # The file is not the one installed and there is no backup to give back: an earlier
            # uninstall restored it and stopped before it wrote the record, or the user replaced
            # both. Nothing is left to undo; say so once, and the record entry goes.
            notices.append(f"CLAUDE.md is not the file the install wrote, and the backup {backup.name} "
                           "is gone; left as is")
        elif not ours and record is None:
            # Without a record nothing says what was installed: a file with no section that is
            # not the rules is the user's, or one an earlier run took the section out of.
            if evidence:
                notices.append("CLAUDE.md has no Ideal-Umbrella section and is not the rules file; left as is")
        elif not ours and backup is None and record is not None and _blank(current_md):
            # An earlier run emptied the file through its link (_empty), then stopped before its
            # last step: nothing is left to undo, and the record entry goes.
            pass
        elif not ours:
            claude_md_left = True
            notices.append("CLAUDE.md differs from what was installed; left as is"
                           + (f" (your earlier file is in {backup.name})" if _is_file(backup) else ""))
        elif _is_file(backup):
            if dry_run:
                changes.append(f"CLAUDE.md restored from {backup.name}")
            else:
                # Whole or not at all, and through a symlinked CLAUDE.md rather than over the
                # link; a copy that fails part way must not leave a truncated file.
                install._write_bytes(claude_md, backup.read_bytes())
                done(f"CLAUDE.md restored from {backup.name}")
                install.remove(backup)
        elif backup is not None:
            # The install replaced a file of yours and its backup is gone: deleting now would
            # lose the only copy left, so keep it and say so.
            claude_md_left = True
            notices.append(f"CLAUDE.md left as is: the backup {backup.name} it should be restored "
                           "from is missing")
        elif record is not None:
            apply(*_empty(claude_md))
        elif evidence:
            # Without a record it may be the user's own copy: keep one.
            change, delete = _empty(claude_md)
            if dry_run:
                changes.append(f"{change} (a backup is kept)")
            else:
                backup = install._backup(claude_md)
                progress.append(f"CLAUDE.md backup: {backup.name}")
                delete()
                done(f"{change} (copy kept as {backup.name})")

    # Without a record the hook entry in settings.json and the hook file are the only evidence
    # of an install, so both stay until the CLAUDE.md step is done, and the hook file goes last:
    # a rerun after a failure before this point still finds one.
    if setting_changes:
        changes.extend(setting_changes)
        if not dry_run:
            backup = install._backup(paths["settings"])
            done(f"settings backup: {backup.name}")
            install._write_json(paths["settings"], settings)
            progress.append("settings.json written")
    if paths["hook"].exists():
        if dry_run:
            changes.append("hook deleted")
        else:
            install.remove(paths["hook"])
            done("hook deleted")

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
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

    try:
        home, config_dir = install.target(args.home)
    except (ValueError, OSError) as e:
        # An empty --home, a home that cannot be found, or a folder of the path that may not be
        # looked at.
        install.report_error(e, [], before_writes=True)
        return 1
    progress = []
    try:
        changes, notices = uninstall(home, dry_run=args.dry_run, progress=progress, config_dir=config_dir)
    except ValueError as e:
        # Raised while reading and checking, before any write; or, rarely, by a write.
        install.report_error(e, progress, before_writes=True,
                             stopped="; the undo stopped part way, fix the cause and run again")
        return 1
    except OSError as e:
        # e.g. the hook path is a folder, or a file is read-only. Files already undone stay
        # undone; a second run after fixing the cause finishes the rest. With no step done the
        # error may still have come from reading, so "part way" is not said (a folder removed
        # part way is not a step done, so "nothing written" is not said either).
        install.report_error(e, progress, stopped="; the undo stopped part way, fix the cause and run again"
                             if progress else "; fix the cause and run uninstall again")
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
