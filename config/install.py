#!/usr/bin/env python3
"""Ideal-Umbrella: install user-level settings, hook, and CLAUDE.md.

Idempotent: running again updates only what changed. Existing keys, other hook
entries, sibling hooks and permission rules are preserved. In CLAUDE.md only the
lines between two marker lines are the installer's; the rest of the file is the
user's and is never changed (the file is backed up before the section is added,
and before a section the user edited is replaced). The hook command records the
Python executable that ran the installer, so it does not depend on `python3`
being on PATH.

Usage:
  python -I config/install.py [--home PATH] [--force] [--verify-only]

What it does:
  1. Merges config/user-settings.json into <home>/.claude/settings.json
  2. Adds config/CLAUDE.md to <home>/.claude/CLAUDE.md as a marked section, or
     updates that section (the text outside it is left as it is)
  3. Copies hooks/context_check.py to <home>/.claude/ballast/context_check.py
  4. Verifies the files and prints a command to run in a new session.

What it changed is recorded in <home>/.claude/ballast/install-record.json, so
config/uninstall.py can put back the values that were there before.
"""
import argparse
import datetime
import errno
import glob
import hashlib
import json
import math
import os
import re
import shlex
import shutil
import stat
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
USER_SETTINGS = HERE / "user-settings.json"
CLAUDE_MD = HERE / "CLAUDE.md"
HOOK_SRC = HERE.parent / "hooks" / "context_check.py"

# The installer's part of ~/.claude/CLAUDE.md lies between these two lines. A whole line each,
# not a heading: config/CLAUDE.md itself has two H1 headings.
SECTION_BEGIN = "<!-- Ideal-Umbrella rules: begin -->"
SECTION_END = "<!-- Ideal-Umbrella rules: end -->"
FENCE = re.compile(r" {0,3}(`{3,}|~{3,})(.*)")

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
    if home_arg is not None:
        if not home_arg:
            # An unset variable in a script (--home "$DIR"): the current home is not what was meant.
            raise ValueError("--home is empty")
        # A relative or literal "~" home would put a relative path in the hook command, which
        # Claude Code runs from the project folder.
        return _absolute(home_arg), None
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    if config is not None:
        if not Path(config).is_absolute():
            # Claude Code takes the value as it is: it does not expand "~", it does not take an
            # empty value for unset, and it reads a relative one from each project folder.
            raise ValueError(f"CLAUDE_CONFIG_DIR={config!r} is empty or not an absolute path, and Claude Code "
                             "does not expand ~; set it to an absolute path or unset it")
        # layout() does not use the home then, so a home that cannot be found does not matter;
        # --home would install into <home>/.claude, which Claude Code does not read.
        return None, _absolute(config)
    try:
        home = Path.home()
    except RuntimeError:
        # No HOME and no passwd entry for this user (some containers and CI images).
        raise ValueError("cannot find your home folder; give it with --home") from None
    # Through _absolute, as --home: a HOME that is a symlink to a missing folder (an unmounted
    # volume) must reach refuse_dangling() as a link, not be resolved and created.
    return _absolute(_own_home(home)), None


HOME_VARIABLE = "USERPROFILE" if os.name == "nt" else "HOME"


def _own_home(home):
    """home, the result of Path.home() or of "~", unless the value it comes from is empty or
    relative: Path.home() takes an empty HOME (or, with no HOME, an empty home in the passwd
    entry) for "/" and an empty or relative one for the current folder, and Claude Code would
    read a relative .claude, so neither is where it looks."""
    source, value = HOME_VARIABLE, os.environ.get(HOME_VARIABLE)
    if value is None and os.name != "nt":
        import pwd
        try:
            source, value = "the home in your passwd entry", pwd.getpwuid(os.getuid()).pw_dir
        except KeyError:
            pass
    if value == "" or not home.is_absolute():
        raise ValueError(f"{source} is empty or not an absolute path; give the home with --home")
    return home


def _absolute(path):
    """path made absolute and resolved, except when it or a folder above it is a symlink to a
    missing target: resolving would drop the link, and refuse_dangling() could no longer see it."""
    raw = os.fspath(path)
    if not raw.startswith("~"):
        # Not expanded: "./~name" is a folder named "~name", but pathlib drops the "./".
        path = Path(raw)
    else:
        head = Path(raw).parts[0]
        try:
            home = Path(head).expanduser()
            path = Path(raw).expanduser()
        except RuntimeError:
            # "~name" for a user that does not exist (bash leaves it as typed), or "~" with no home.
            raise ValueError(f"cannot find the home folder in {raw}") from None
        if head == "~":
            _own_home(home)
        if not home.is_dir():
            # A home folder that is not there. On Windows "~name" is the folder beside your own
            # home whether or not that user exists, so expanduser() does not refuse it.
            raise ValueError(f"cannot find the home folder in {raw}")
    if any(_is_link(p) and not p.exists() for p in (path, *path.parents)):
        return Path(os.path.abspath(path))
    return path.resolve()


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


JSON_DEPTH = 100


def _check_json(data, path, fix="fix it first"):
    """Raise ValueError when data, as json.load gave it, cannot be written back: nested more
    than JSON_DEPTH levels (json.dumps(indent=2) can run out of stack well below what
    json.loads reads) or holding a lone surrogate (valid JSON, but not encodable as UTF-8) or a number
    json.dumps would write as Infinity or NaN.
    Called right after reading, so the run stops before its first write."""
    stack = [(data, 1)]
    while stack:
        value, depth = stack.pop()
        if isinstance(value, str):
            try:
                value.encode("utf-8")
            except UnicodeEncodeError:
                raise ValueError(f"{path} holds text that is not valid Unicode (a lone surrogate "
                                 f"such as \\ud800); {fix}") from None
        elif isinstance(value, float) and not math.isfinite(value):
            # json.loads reads 1e400 as inf and NaN as nan; json.dumps would write them back as
            # Infinity and NaN, which are not JSON, so the next reader fails on the file.
            raise ValueError(f"{path} holds a number that is not a JSON number ({value!r}, from "
                             f"1e400, NaN or Infinity); {fix}")
        elif isinstance(value, (dict, list)):
            if depth > JSON_DEPTH:
                raise ValueError(f"{path} is nested more than {JSON_DEPTH} levels deep; {fix}")
            items = value.items() if isinstance(value, dict) else ((None, v) for v in value)
            for key, item in items:
                if key is not None:
                    stack.append((key, depth))
                stack.append((item, depth + 1))


def _read_json(path):
    """Read a JSON object; a file that is not UTF-8, not JSON, not an object or not writable
    back is a ValueError naming the file, which main() reports as one line before anything is
    written."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except UnicodeDecodeError as e:
        raise ValueError(f"{path} is not UTF-8 ({e.reason} at byte {e.start}); save it as UTF-8 first") from None
    except ValueError as e:
        raise ValueError(f"{path} is not valid JSON ({e}); fix it first") from None
    except RecursionError:
        raise ValueError(f"{path} is nested too deeply to be read; fix it first") from None
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object, not {type(data).__name__}")
    _check_json(data, path)
    return data


# Only names this installer gives a backup: a <name>.bak-something the user made by hand is
# never taken for one of ours (and then deleted by uninstall).
_BACKUP_NAME = r"\.bak-[0-9]{8}-[0-9]{6}(-[0-9]+)?"  # [0-9], not \d, which also matches other scripts' digits


def _backup_name(path):
    """The backup path _backup would use for path, without copying: an earlier backup of ours
    already holding the same bytes (a run that failed after its backup would otherwise leave
    one that no record names and no uninstall removes), else a new timestamped name."""
    data = path.read_bytes()
    ours = re.compile(re.escape(path.name) + _BACKUP_NAME)
    for earlier in sorted(path.parent.glob(glob.escape(path.name) + ".bak-*")):
        # Not the file itself: path linked to a backup (put back with `ln -s`) holds its bytes,
        # and the install then writes through the link into what it takes for the copy.
        if ours.fullmatch(earlier.name) and earlier.is_file() and not earlier.is_symlink() \
                and _holds(earlier, data) and not same_file(earlier, path):
            return earlier
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.bak-{stamp}")
    n = 1
    while backup.exists():
        backup = path.with_name(f"{path.name}.bak-{stamp}-{n}")
        n += 1
    return backup


def _holds(path, data):
    """True when path holds data; False when it cannot be read (an old backup left
    root-owned by a sudo run is no match, and must not stop every install)."""
    try:
        return path.read_bytes() == data
    except OSError:
        return False


def backup_of(path, name):
    """The backup of path a record names, beside it; None unless name is one this installer
    gives (a record edited by hand or by a sync tool may name "..", a folder, or a file of
    the user's, and the uninstall deletes what it names)."""
    if not isinstance(name, str) or not re.fullmatch(re.escape(path.name) + _BACKUP_NAME, name):
        return None
    return path.with_name(name)


def _backup(path, backup=None):
    """Copy path to a timestamped backup beside it (or to backup, from _backup_name) and
    return the backup's path. An existing backup with the same bytes is not copied again."""
    backup = backup or _backup_name(path)
    data = path.read_bytes()
    if not (backup.is_file() and not backup.is_symlink() and backup.read_bytes() == data):
        # Whole or not at all, like every other write: a copy cut short by a full disk would
        # leave a truncated backup that no record names and no uninstall removes.
        _write_bytes(backup, data)
        shutil.copystat(path, backup)
        # The backup is the installer's to delete: a read-only mode copied from a read-only
        # file would stop every uninstall at it on Windows, which cannot delete such a file.
        os.chmod(backup, backup.stat().st_mode | stat.S_IWUSR)
    return backup


def remove(path):
    """Delete a file of the installer's (a backup, the hook, the log). Windows cannot delete
    a read-only file, so when the delete is refused, a read-only bit set by an earlier version,
    the user or a sync tool is cleared and the delete tried once more (and the bit set back if
    that fails too). The delete comes first: on Linux and macOS it needs only the folder, and a
    file another user owns (a log left by `sudo claude`) cannot be chmodded. A symlink is
    removed, and its target left as it is. When the chmod fails too, the refused delete is
    what is reported: its cause (a folder that is not writable) is the one to fix."""
    path = Path(path)
    try:
        path.unlink()
        return
    except PermissionError as refused:
        if path.is_symlink() or os.access(path, os.W_OK):
            raise
        first = refused
    mode = path.stat().st_mode
    try:
        os.chmod(path, mode | stat.S_IWUSR)
    except OSError:
        raise first from None
    try:
        path.unlink()
    except OSError:
        os.chmod(path, mode)
        raise


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


def same_file(a, b):
    """True when a and b are one file (a symlink to the other, or the same name on a file
    system that ignores case); True also when it cannot be told, so that no caller deletes,
    reuses or skips a copy on a guess."""
    try:
        return os.path.samefile(a, b)
    except (OSError, ValueError):
        return True


def refuse_dangling(paths):
    """Raise ValueError when one of paths, or a folder above it, is a symlink whose target is
    missing (a dotfiles folder moved or not mounted): read as a missing file, it would be
    written over (into the missing target), or its undo dropped."""
    for path in paths:
        for part in (path, *path.parents):
            if _is_link(part) and not part.exists():
                raise ValueError(f"{part} is a symlink to a missing target; fix or remove it first")


def _is_link(path):
    """A symlink, or on Windows a junction: Path.is_symlink() does not see a junction, while
    shutil.rmtree refuses one and a write through a dangling one fails like a dangling symlink."""
    if Path(path).is_symlink():
        return True
    isjunction = getattr(os.path, "isjunction", None)   # Python 3.12+, Windows only
    return bool(isjunction and isjunction(path))


def refuse_read_only(path):
    """Raise PermissionError when path (through a symlink) is a file that cannot be written."""
    path = Path(path).resolve()
    if path.exists() and not os.access(path, os.W_OK):
        raise PermissionError(errno.EACCES, "the file is read-only; make it writable first", str(path))


def _write_bytes(path, data):
    """Write a user file whole or not at all: to a temp file beside it, then rename over it.
    A write that fails part way (disk full, a killed process) leaves the old file as it was
    instead of a truncated one. Writes through a symlink (dotfiles, stow)
    instead of replacing the link, and keeps the file's mode; a new file gets the mode a
    plain write would give it. A read-only target is refused, as a plain write refuses it.
    A hard-linked target becomes a new file: the other links keep the old content."""
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    refuse_read_only(path)
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
    _write_bytes(path, (json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))


def _read_text(path):
    """Read a UTF-8 file with its line ends as they are; any failure is a ValueError naming
    the file."""
    try:
        with open(path, encoding="utf-8", newline="") as f:
            return f.read()
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


def _lf(text):
    return text.replace("\r\n", "\n")


def section_text(rules):
    """The marked section holding rules, with LF line ends."""
    rules = _lf(rules)
    if rules and not rules.endswith("\n"):
        rules += "\n"
    return f"{SECTION_BEGIN}\n{rules}{SECTION_END}\n"


def _lines(text):
    """text split at "\n", with a BOM before line 1 taken off; returns (lines, BOM length)."""
    lines = text.split("\n")
    if lines[0].startswith("\ufeff"):
        lines[0] = lines[0][1:]
        return lines, 1
    return lines, 0


def _fenced(lines):
    """Numbers of the lines inside a closed Markdown code fence (``` or ~~~), fence lines
    included. An opening fence that is never closed is ordinary text and the scan goes on at
    the next line: read as Markdown it would run to the end of the file and swallow the
    section install appends there, and it must not hide a closed fence after it either."""
    fences = []   # (number, character, length, closes: no info string)
    for number, line in enumerate(lines, 1):
        match = FENCE.match(line)
        if match:
            fences.append((number, match.group(1)[0], len(match.group(1)), not match.group(2).strip(),
                           match.group(2)))
    # longest[char][i]: the longest closing fence of that character at fences[i] or later, so
    # an opener with no closer is skipped without scanning to the end (no quadratic run).
    longest = {"`": [0] * (len(fences) + 1), "~": [0] * (len(fences) + 1)}
    for i in range(len(fences) - 1, -1, -1):
        for char in longest:
            longest[char][i] = longest[char][i + 1]
        _, char, length, closes, _ = fences[i]
        if closes:
            longest[char][i] = max(longest[char][i], length)
    inside, i = set(), 0
    while i < len(fences):
        number, char, length, _, info = fences[i]
        # A backtick fence's info string holds no backtick (CommonMark).
        if (char == "`" and "`" in info) or longest[char][i + 1] < length:
            i += 1
            continue
        j = i + 1
        while not (fences[j][1] == char and fences[j][2] >= length and fences[j][3]):
            j += 1
        inside.update(range(number, fences[j][0] + 1))
        i = j + 1
    return inside


def find_section(text, recorded=None):
    """Where the Ideal-Umbrella section is in text: (start, body_start, body_end, end) as
    offsets, from the begin marker line to past the end marker line's line break; None when
    text has no marker line. A marker is a whole line (trailing whitespace ignored), so a line
    that only mentions one is not one, and neither is a marker line inside a code fence (an
    example the user wrote). A BOM before a begin marker on line 1 stays outside the section.
    A marker without its pair, a second section, or an end before the begin is a ValueError:
    guessing where the section ends could delete the user's text.

    recorded is the sha256 the install record holds for the section. When every marker line
    is inside a fence and exactly one begin and one end line are found with fences ignored,
    holding exactly the recorded section, that pair is the section: a fence line the user
    left open before it and closed after it (a code block added below) does not hide it."""
    lines, bom = _lines(text)
    fenced = _fenced(lines)
    begins, ends, all_begins, all_ends = [], [], [], []
    offset = bom
    for number, line in enumerate(lines, 1):
        bare = line.rstrip()
        found = (number, offset, min(offset + len(line) + 1, len(text)))
        if bare == SECTION_BEGIN:
            all_begins.append(found)
            if number not in fenced:
                begins.append(found)
        elif bare == SECTION_END:
            all_ends.append(found)
            if number not in fenced:
                ends.append(found)
        offset += len(line) + 1
    if not begins and not ends:
        if recorded is None or len(all_begins) != 1 or len(all_ends) != 1 or all_ends[0][0] < all_begins[0][0]:
            return None
        pair = all_begins[0][1], all_begins[0][2], all_ends[0][1], all_ends[0][2]
        return pair if text_hash(section_text(section_body(text, pair))) == recorded else None
    if len(begins) != 1 or len(ends) != 1 or ends[0][0] < begins[0][0]:
        def numbers(found):
            return ", ".join(str(n) for n, _, _ in found) or "none"
        raise ValueError(f"the Ideal-Umbrella marker lines are not one begin line followed by one end "
                         f"line (begin on line {numbers(begins)}, end on line {numbers(ends)}); "
                         "fix them by hand first")
    return begins[0][1], begins[0][2], ends[0][1], ends[0][2]


def fenced_line(text, found):
    """The line number of the begin marker when the section find_section found is inside a
    code fence (found by the recorded hash), else None. Such a section is either the
    installed one behind a fence line the user left open, or a fenced example of it the user
    kept after deleting the live one; no tool can tell which, so none of them changes it."""
    number = text.count("\n", 0, found[0]) + 1
    return number if number in _fenced(_lines(text)[0]) else None


def fence_advice(number):
    return (f"the Ideal-Umbrella section of CLAUDE.md (line {number}) is inside a code fence, so it "
            "may be an example you wrote; if it is the installed section, close the code fence "
            "opened above it")


def section_body(text, found):
    """The rules between the marker lines found by find_section, with LF line ends."""
    return _lf(text[found[1]:found[2]])


def plan_claude_md(current, rules, old):
    """What install does to CLAUDE.md; reads nothing and writes nothing.

    current is the file's text (None when there is none), rules the template, old the
    record's claude_md entry from an earlier install. Returns None when the section is
    already the template, else a dict: text (the whole new file; None when only the record
    changes), entry (for the record), backup ("user" for the file before the section is
    added, "edited" for a section the user changed, None), change (the line to report) and,
    when there is something to tell, notice. Raises ValueError for broken markers.
    """
    old = old if isinstance(old, dict) else None
    old_format = old is not None and "format" not in old   # the whole-file installer's entry
    section = section_text(rules)
    entry = {"format": "section", "sha256": text_hash(section), "created": False, "joined": ""}
    if old_format:
        # The whole-file installer created the file when it made no backup of one.
        entry["created"] = old.get("backup") is None
        if old.get("backup"):
            entry["legacy_backup"] = old["backup"]
    elif old is not None:
        entry.update({k: old[k] for k in ("created", "legacy_backup", "safety_backup", "wrapped", "hand_section")
                      if k in old})
    if current is None:
        entry["created"] = True
        entry.pop("wrapped", None)   # the copy that was the user's is gone with the file
        entry.pop("hand_section", None)
        return {"text": section, "entry": entry, "backup": None, "change": "CLAUDE.md written"}

    newline = "\r\n" if "\r\n" in current else "\n"
    ours = section.replace("\n", newline)
    found = find_section(current, None if old is None or old_format else old.get("sha256"))
    if found:
        start, _, _, end = found
        present = section_text(section_body(current, found))
        number = fenced_line(current, found)
        if number is not None and present != section:
            raise ValueError(f"{fence_advice(number)}; nothing is changed until then")
        if present == section:
            if not old_format:
                return None
            # The user put the markers around the whole-file install by hand: nothing to
            # write, but the record must move to the section format, or uninstall would
            # compare the whole file and never give back the file that install moved aside.
            return {"text": None, "entry": entry, "backup": None, "change": "CLAUDE.md section recorded"}
        still_ours = not old_format and old is not None and old.get("sha256") == text_hash(present)
        if not old_format and old is not None:
            entry["joined"] = old.get("joined", "")
        plan = {"text": current[:start] + ours + current[end:], "entry": entry,
                "backup": None if still_ours else "edited", "change": "CLAUDE.md section updated"}
        if old is None or entry.get("hand_section") is True:
            # No record names this section, or it names one the user added by hand (README "By
            # hand"): it stays theirs, as a hand copy of the rules does. It now holds the new
            # rules, uninstall leaves it whole, and a first run backs the file up as it is now.
            entry["hand_section"] = True
            if old is None:
                plan["backup"] = "user"
            plan["notice"] = ("the Ideal-Umbrella section of CLAUDE.md was added by hand, not by the installer; "
                              "it now holds the new rules, and uninstall leaves it in place")
        elif entry.get("wrapped") is True:
            # The section was the user's own copy of the rules; it now holds the new rules,
            # and uninstall leaves them (only the marker lines go). The file from before the
            # first install is the backup the record names.
            kept = entry.get("safety_backup")
            plan["notice"] = ("the Ideal-Umbrella section of CLAUDE.md was your own copy of the rules; it now "
                              "holds the new rules, which uninstall leaves in place"
                              + (f" (your file from before the first install is in {kept})" if kept else ""))
        return plan

    if old_format and old.get("sha256") == text_hash(_lf(current)):
        # The whole file is what the whole-file installer wrote: it becomes the section, and
        # the file it replaced (if any) is still the one an uninstall puts back.
        return {"text": ours, "entry": entry, "backup": None,
                "change": "CLAUDE.md converted to a marked section"}

    copy = _lf(rules)
    copy = (copy if copy.endswith("\n") else copy + "\n").replace("\n", newline)
    at = _unfenced_copy(current, copy)
    if copy.strip() and at is not None:
        # An unmarked copy of the rules is wrapped in the marker lines, not added a second
        # time. With a record it is the installer's own (the whole-file install, or a section
        # whose marker lines were deleted), unless the record says the copy was the user's to
        # begin with: uninstall removes it, and only marker lines are added, so no backup is
        # needed. Without one it is a hand copy and the user's: backed up, and uninstall takes
        # only the marker lines away again.
        entry["wrapped"] = old is None or entry.get("wrapped") is True or entry.get("hand_section") is True
        entry.pop("hand_section", None)   # its marker lines are gone; the copy is wrapped again
        if old is not None and not old_format:
            entry["joined"] = old.get("joined", "")
        text = current[:at] + SECTION_BEGIN + newline + copy + SECTION_END + newline + current[at + len(copy):]
        return {"text": text, "entry": entry, "backup": "user" if old is None else None,
                "change": "CLAUDE.md rules marked as a section"}

    entry.pop("wrapped", None)   # a new section holds no copy of the user's
    entry.pop("hand_section", None)
    if current:
        entry["joined"] = ("" if current.endswith("\n") else newline) + newline
    return {"text": current + entry["joined"] + ours, "entry": entry,
            "backup": "user" if current else None, "change": "CLAUDE.md section added"}


def _unfenced_copy(current, copy):
    """Offset of the one copy of the rules in current that starts a line and has no line
    inside a code fence (a fenced copy is an example the user wrote); None when there is no
    such copy or more than one."""
    lines, bom = _lines(current)
    fenced = _fenced(lines)
    span = copy.count("\n")
    found, at, counted, line = [], current.find(copy), 0, 1
    while at >= 0 and len(found) < 2:
        line += current.count("\n", counted, at)   # counted once over the whole text
        counted = at
        if (at == 0 or (at == 1 and current[0] == "\ufeff") or current[at - 1] == "\n") \
                and not fenced.intersection(range(line, line + span)):
            found.append(at)
        at = current.find(copy, at + 1)
    return found[0] if len(found) == 1 else None


# The record holds the values uninstall puts back, so deleting it is never the advice.
RECORD_ADVICE = "fix it first (deleting it loses what uninstall puts back)"


def read_record(path):
    """The saved install record, or None when there is none.

    A record that exists but cannot be read is an error, not "no record": it holds the values
    an uninstall must put back, so neither install nor uninstall may silently overwrite it, and
    the error does not advise deleting it. A BOM (an editor that saves UTF-8 with one) is read
    as settings.json's is.
    """
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except ValueError as e:
        raise ValueError(f"{path} is not valid JSON ({e}); {RECORD_ADVICE}") from e
    except RecursionError:
        raise ValueError(f"{path} is nested too deeply to be read; {RECORD_ADVICE}") from None
    except OSError as e:
        raise ValueError(f"cannot read {path} ({e.strerror or e})") from e
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a JSON object; {RECORD_ADVICE}")
    _check_json(data, path, RECORD_ADVICE)
    _check_record_fields(data, path)
    if "pending" in data:
        _check_record_fields(data["pending"], path, "pending.")
    return data


# The shape of each field install writes; a field that is missing is fine (older records).
_RECORD_FIELDS = {
    "added_keys": ("a list of setting names", lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v)),
    "deny_added": ("a list of tool names", lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v)),
    "created": ("a list of setting names", lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v)),
    "replaced": ("an object", lambda v: isinstance(v, dict)),
    "installed": ("an object", lambda v: isinstance(v, dict)),
    "pending": ("an object", lambda v: isinstance(v, dict)),
    "claude_md": ("an object or null", lambda v: v is None or isinstance(v, dict)),
}


def _check_record_fields(record, path, prefix=""):
    """Raise ValueError when a field of the record has a type install never writes (a hand
    edit, a sync tool): read on, it would stop install or uninstall with a traceback, or make
    uninstall match tool names by substring."""
    for field, (shape, fits) in _RECORD_FIELDS.items():
        if field in record and not fits(record[field]):
            raise ValueError(f'{path}: "{prefix}{field}" must be {shape}; {RECORD_ADVICE}')


def _describes(entry, text):
    """True when the record's claude_md entry matches CLAUDE.md as text holds it."""
    if not isinstance(entry, dict) or text is None:
        return False
    if "format" not in entry:   # the whole-file installer's entry: the hash of the whole file
        return entry.get("sha256") == text_hash(_lf(text))
    try:
        found = find_section(text, entry.get("sha256"))
    except ValueError:
        return False
    return found is not None and text_hash(section_text(section_body(text, found))) == entry.get("sha256")


def settle_record(record, settings, claude_md_text):
    """The record as it describes the files on disk now.

    install writes its record before its other writes, so that a write that fails still
    leaves every change named; the record it replaces goes in "pending" until the run ends.
    When a write failed, a part of the new record may describe a change that never landed:
    for that part the earlier description is used when it is the one the files match (an
    installed value still in settings.json, a CLAUDE.md that is still the earlier section or
    whole-file install). settings is the parsed settings.json (None when there is none).
    """
    if not isinstance(record, dict) or not isinstance(record.get("pending"), dict):
        return record
    earlier = record["pending"]
    settled = {key: value for key, value in record.items() if key != "pending"}
    installed, before = settled.get("installed"), earlier.get("installed")
    if isinstance(installed, dict) and isinstance(before, dict) and isinstance(settings, dict):
        installed = dict(installed)
        for key, value in before.items():
            if key in settings and settings[key] == value and installed.get(key) != value:
                installed[key] = value
        settled["installed"] = installed
    entry, before = settled.get("claude_md"), earlier.get("claude_md")
    if isinstance(before, dict) and not _describes(entry, claude_md_text) and _describes(before, claude_md_text):
        settled["claude_md"] = before
    return settled


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
    if old.get("uninstalled"):
        # After an uninstall only the containers this install sees are ours to delete; the
        # leftover list may name one the uninstall deleted and the user then made by hand.
        created = list(new.get("created", []))
    else:
        created = list(old.get("created", []))
        created += [c for c in new.get("created", []) if c not in created]
    installed = dict(old_installed) if isinstance(old_installed, dict) else {}
    installed.update(new.get("installed", {}))
    merged = {"added_keys": added, "replaced": replaced, "deny_added": deny, "installed": installed}
    install_data = ("added_keys", "replaced", "deny_added", "installed")
    if "created" in old or not any(k in old for k in install_data):
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

    command = hook_command(home, config_dir)
    try:
        command.encode("utf-8")
    except UnicodeEncodeError:
        # A path holding bytes that are not UTF-8 (possible on Linux): settings.json is UTF-8,
        # so the hook command could never be written, after the other files were.
        raise ValueError(f"the hook command {command!r} holds a path that is not UTF-8, and "
                         "settings.json can only hold UTF-8; install from, and into, folders whose "
                         "names are UTF-8") from None

    # Read and check everything before writing anything, and write settings.json after the
    # hook file: its hook entry must never point at a hook file that was not copied (a missing
    # hook file exits 2, which blocks every prompt).
    refuse_dangling(paths[name] for name in ("settings", "claude_md", "hook", "record"))
    existing = _read_json(paths["settings"]) if paths["settings"].exists() else {}
    template = _read_json(USER_SETTINGS)
    claude_md = _read_text(CLAUDE_MD)
    current_md = _read_text(paths["claude_md"]) if paths["claude_md"].exists() else None
    raw_record = read_record(paths["record"]) or {}
    old_record = settle_record(raw_record, existing, current_md)
    try:
        md_plan = plan_claude_md(current_md, claude_md, old_record.get("claude_md"))
    except ValueError as e:
        raise ValueError(f"{paths['claude_md']}: {e}") from None
    hook_bytes = _read_bytes(HOOK_SRC)
    hook_exists = paths["hook"].exists()
    current_hook = _read_bytes(paths["hook"]) if hook_exists else None
    setting_changes, setting_notices = merge_settings(existing, template, home, force, record,
                                                      old_record.get("installed"), config_dir)
    notices.extend(setting_notices)

    hook_changed = current_hook != hook_bytes
    md_backup = None
    if md_plan is not None:
        entry = md_plan["entry"]
        if md_plan.get("notice"):
            notices.append(md_plan["notice"])
        kept = backup_of(paths["claude_md"], (old_record.get("claude_md") or {}).get("safety_backup"))
        if md_plan["backup"] == "edited" and kept is not None and kept.is_file() and not kept.is_symlink() \
                and kept.read_bytes() == paths["claude_md"].read_bytes() \
                and not same_file(kept, paths["claude_md"]):
            # An earlier run backed the file up before adding its section, then stopped before
            # its CLAUDE.md write: the section is the one that was there, and the backup holds it.
            md_backup = None
        elif md_plan["backup"]:
            md_backup = _backup_name(paths["claude_md"])
            if md_plan["backup"] == "edited":
                notices.append(f"the Ideal-Umbrella section of CLAUDE.md had edits; they are kept in {md_backup.name}")
                # Named so that uninstall can delete it when the CLAUDE.md write then fails
                # (the file still holds the same edits); otherwise it is the user's to keep.
                entry["edited_backup"] = md_backup.name
            else:
                # The file as it is now, before the section: the bytes an uninstall gives back.
                entry["safety_backup"] = md_backup.name
        record["claude_md"] = entry

    # The record comes first: it names every change this run makes, so a write that fails
    # after it still leaves a record the undo works from; a change it did not name would be
    # stranded (a rerun sees the section or the values already in place and records nothing
    # for them). Until the last write is done it also keeps the record it replaces, as
    # "pending": a change it names that never landed is then undone by the earlier description
    # (settle_record), or is harmless to undo (a key that still holds its value from before the
    # first install is skipped, a backup that equals the file is deleted).
    merged = _merge_record(old_record, record)
    changing = hook_changed or md_plan is not None or setting_changes
    # A read-only file is refused before the first write, not at its own write after others.
    for path, written in ((paths["record"], changing or "pending" in raw_record),
                          (paths["hook"], hook_changed),
                          (paths["claude_md"], md_plan is not None and md_plan["text"] is not None),
                          (paths["settings"], setting_changes)):
        if written:
            refuse_read_only(path)
    if changing:
        _write_json(paths["record"], dict(merged, pending=old_record) if old_record else merged)
        progress.append("install record written")

    if hook_changed:
        _write_bytes(paths["hook"], hook_bytes)
        changes.append(f"hook {'updated' if hook_exists else 'written'}")
        progress.append(changes[-1])

    if md_plan is not None:
        if md_backup is not None:
            _backup(paths["claude_md"], md_backup)
            changes.append(f"CLAUDE.md backup: {md_backup.name}")
            progress.append(changes[-1])
        if md_plan["text"] is not None:
            _write_bytes(paths["claude_md"], md_plan["text"].encode("utf-8"))
        changes.append(md_plan["change"])
        progress.append(changes[-1])

    if setting_changes:
        if paths["settings"].exists():
            backup = _backup(paths["settings"])
            setting_changes.append(f"settings backup: {backup.name}")
            progress.append(setting_changes[-1])
        _write_json(paths["settings"], existing)
        progress.append("settings.json written")
    if changing and old_record:
        _write_json(paths["record"], merged)   # every write landed: nothing is pending
    elif "pending" in raw_record:
        # An earlier run stopped at its last write. Its pending part is settled now; left in
        # place, it would later take a value the user set by hand for the installer's.
        _write_json(paths["record"], {k: v for k, v in old_record.items() if k != "pending"})
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

    # Only the marked section is the installer's; text outside it is the user's.
    if not paths["claude_md"].exists():
        issues.append(f"Missing: {paths['claude_md']}")
    else:
        text = paths["claude_md"].read_bytes().decode("utf-8", errors="replace")
        try:
            entry = (settle_record(read_record(paths["record"]), None, text) or {}).get("claude_md")
        except ValueError:
            entry = None   # the record is checked by install and uninstall, not here
        recorded = entry.get("sha256") if isinstance(entry, dict) and entry.get("format") == "section" else None
        try:
            found = find_section(text, recorded)
        except ValueError as e:
            issues.append(f"CLAUDE.md: {e}")
        else:
            if found is None:
                issues.append("CLAUDE.md has no Ideal-Umbrella section; run install.py")
            elif section_text(section_body(text, found)) != section_text(_read_text(CLAUDE_MD)):
                issues.append("the Ideal-Umbrella section of CLAUDE.md differs from config/CLAUDE.md")
            if found is not None and fenced_line(text, found) is not None:
                warnings.append(fence_advice(fenced_line(text, found)))

    if not paths["hook"].exists():
        issues.append(f"Missing: {paths['hook']}")
    elif paths["hook"].read_bytes() != HOOK_SRC.read_bytes():
        issues.append("Hook content differs from hooks/context_check.py")

    return len(issues) == 0, issues, warnings


def report_error(error, progress, before_writes=False, stopped=""):
    """Print the error, then what was done before it. "nothing written" is said only for an
    error the run raises before its first write (before_writes) when progress shows none was
    made: a ValueError can also come from a write, after others were done."""
    if before_writes and not progress:
        print(f"Error: {error}; nothing written", file=sys.stderr)
        return
    print(f"Error: {error}{stopped}", file=sys.stderr)
    if not progress:
        return
    print("Done before the error:", file=sys.stderr)
    for line in progress:
        print(f"  - {line}", file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.strip())
    parser.add_argument("--home", default=None, help="home folder to install into (default: current home, "
                                                     "or CLAUDE_CONFIG_DIR when it is set)")
    parser.add_argument("--force", action="store_true", help="replace differing scalar settings")
    parser.add_argument("--verify-only", action="store_true", help="check the installation without writing")
    args = parser.parse_args(argv)
    # Paths in the output may hold characters outside the Windows ANSI code page.
    if hasattr(sys.stdout, "reconfigure"):
        # A path that is not UTF-8 (Linux) is printed escaped rather than ending in a traceback.
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    try:
        home, config_dir = target(args.home)
    except (ValueError, OSError) as e:
        # An empty --home, a home that cannot be found, or a folder of the path that may not be
        # looked at.
        report_error(e, [], before_writes=True)
        return 1

    if not args.verify_only:
        print("Installing Ideal-Umbrella user-level configuration...")
        progress = []
        try:
            changes, notices = install(home, force=args.force, progress=progress, config_dir=config_dir)
        except ValueError as e:
            # Raised while reading and checking, before any write; or, rarely, by a write.
            report_error(e, progress, before_writes=True)
            return 1
        except OSError as e:
            # e.g. ~/.claude/ballast exists as a regular file, or a folder is read-only. Every
            # file is written whole or not at all; name what was done so the backups are findable.
            report_error(e, progress)
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
