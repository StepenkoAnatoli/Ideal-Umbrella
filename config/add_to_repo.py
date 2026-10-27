"""Ideal-Umbrella: give a repository's cloud sessions the hook and the two keys.

Cloud sessions read only the repository's committed .claude/settings.json, not
~/.claude/. This copies hooks/context_check.py to <repo>/.claude/hooks/ and
merges config/repo-settings.json into <repo>/.claude/settings.json. Other keys,
other hook entries and sibling hooks inside the same entry are preserved. A
scalar value the repository already sets (for example its own autoCompactWindow)
is kept and reported unless --force is given. An existing Ideal-Umbrella hook is
updated in place, not duplicated. Running it again changes nothing.

The hook exits at once unless CLAUDE_CODE_REMOTE is true, so local sessions keep
only the user-level hook. Stdlib only; run with
`python -I config/add_to_repo.py [--force] [--handoff-at TOKENS] <repo>`, then
commit the two files in that repository. --handoff-at sets the repository's own
hand-off threshold as env.IDEAL_UMBRELLA_HANDOFF_AT (other env keys stay).
"""
import errno
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "repo-settings.json")
SCRIPT = os.path.join(os.path.dirname(HERE), "hooks", "context_check.py")


def _hook_command(hook):
    return str(hook.get("command", "")) if isinstance(hook, dict) else ""


def is_ours(entry):
    if not isinstance(entry, dict):
        return False
    hooks = entry.get("hooks", [])
    return isinstance(hooks, list) and any("context_check.py" in _hook_command(h) for h in hooks)


def _template_hook(entries):
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for hook in entry.get("hooks", []):
            if isinstance(hook, dict) and "context_check.py" in _hook_command(hook):
                return hook
    return None


def _replace_hook(entry, replacement):
    """Replace only our hook object, leaving sibling hooks in the same entry alone."""
    changed = False
    for hook in entry.get("hooks", []):
        if isinstance(hook, dict) and "context_check.py" in _hook_command(hook):
            if hook.get("command") != replacement.get("command"):
                hook["command"] = replacement.get("command")
                changed = True
    return changed


def _merge_value(settings, key, value, force, changes, notices, label):
    """Merge one template key. An object value (env) is merged key by key, so a repository's
    own keys in it stay; any other value the repository already sets differently is kept
    unless force is true."""
    if isinstance(value, dict):
        if not isinstance(settings.setdefault(key, {}), dict):
            raise ValueError(f"settings {label} must be an object")
        for sub, sub_value in value.items():
            _merge_value(settings[key], sub, sub_value, force, changes, notices, f"{label}.{sub}")
    elif key not in settings:
        changes.append(f"{label}: added {value!r}")
        settings[key] = value
    elif settings[key] != value:
        if force:
            changes.append(f"{label}: {settings[key]!r} -> {value!r}")
            settings[key] = value
        else:
            notices.append(f"{label} is {settings[key]!r}, template has {value!r}; "
                           "left unchanged (use --force)")


def merge(settings, template, force=False):
    """Merge template into settings in place; return (changes, notices), both human-readable.

    A scalar key the settings already hold with another value is left alone and reported in
    notices, unless force is true: the repository's own choice wins over the template."""
    if not isinstance(settings, dict):
        raise ValueError("settings must be a JSON object")
    if not isinstance(template, dict):
        raise ValueError("template must be a JSON object")
    changes, notices = [], []
    for key, value in template.items():
        if key != "hooks":
            _merge_value(settings, key, value, force, changes, notices, key)

    template_hooks = template.get("hooks", {})
    if not isinstance(template_hooks, dict):
        raise ValueError("template hooks must be an object")
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("settings hooks must be an object")

    for event, entries in template_hooks.items():
        if not isinstance(entries, list):
            raise ValueError(f"template hooks.{event} must be a list")
        current = hooks.setdefault(event, [])
        if not isinstance(current, list):
            raise ValueError(f"settings hooks.{event} must be a list")
        replacement = _template_hook(entries)
        existing = [entry for entry in current if is_ours(entry)]
        if existing and replacement is not None:
            updated = False
            for entry in existing:
                updated = _replace_hook(entry, replacement) or updated
            if updated:
                changes.append(f"hooks.{event}: Ideal-Umbrella entry updated")
        elif not existing:
            current.extend(entries)
            changes.append(f"hooks.{event}: Ideal-Umbrella entry added")
    return changes, notices


JSON_DEPTH = 100


def _check_json(data, path):
    """Raise ValueError when data, as json.load gave it, cannot be written back: nested more
    than JSON_DEPTH levels (json.dumps(indent=2) can run out of stack well below what
    json.loads reads) or holding a lone surrogate (valid JSON, but not encodable as UTF-8).
    The same check as config/install.py's (this script runs on its own, without it)."""
    stack = [(data, 1)]
    while stack:
        value, depth = stack.pop()
        if isinstance(value, str):
            try:
                value.encode("utf-8")
            except UnicodeEncodeError:
                raise ValueError(f"{path} holds text that is not valid Unicode (a lone surrogate "
                                 "such as \\ud800); fix it first") from None
        elif isinstance(value, (dict, list)):
            if depth > JSON_DEPTH:
                raise ValueError(f"{path} is nested more than {JSON_DEPTH} levels deep; fix it first")
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
    """A symlink, or on Windows a junction (os.path.islink does not see a junction)."""
    if os.path.islink(path):
        return True
    isjunction = getattr(os.path, "isjunction", None)   # Python 3.12+, Windows only
    return bool(isjunction and isjunction(path))


def _write_bytes(path, data):
    """Write whole or not at all (temp file beside the target, then rename), through a
    symlink instead of replacing the link, keeping the file's mode; a new file gets the mode a
    plain write would give it. A read-only target is refused, as a plain write refuses it."""
    path = os.path.realpath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path) and not os.access(path, os.W_OK):
        raise PermissionError(errno.EACCES, "the file is read-only; make it writable first", str(path))
    fd, tmp = _new_temp(os.path.dirname(path), f".{os.path.basename(path)}-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        if os.path.exists(path):
            os.chmod(tmp, os.stat(path).st_mode & 0o7777)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.chmod(tmp, 0o600)   # Windows cannot remove a read-only file
            except OSError:
                pass
            os.remove(tmp)


def _write_json(path, data):
    _write_bytes(path, (json.dumps(data, indent=2) + "\n").encode("utf-8"))


USAGE = "usage: python -I config/add_to_repo.py [--force] [--handoff-at TOKENS] <repo folder>"


def _take_handoff_at(argv):
    """Return (tokens or None, the other arguments). TOKENS is a whole number above 0 in ASCII
    digits, the values hooks/context_check.py accepts; anything else is a ValueError."""
    rest, values = [], []
    args = iter(argv)
    for arg in args:
        if arg == "--handoff-at":
            values.append(next(args, ""))
        elif arg.startswith("--handoff-at="):
            values.append(arg[len("--handoff-at="):])
        else:
            rest.append(arg)
    if not values:
        return None, rest
    if len(values) > 1:
        raise ValueError("--handoff-at is given more than once")
    value = values[0]
    if value.isascii() and value.isdigit() and len(value.lstrip("0")) > 15:
        # int() refuses more than 4300 digits with its own message; no context window is near.
        raise ValueError(f"--handoff-at {value[:20]}... is too large; give a whole number of tokens")
    if not (value.isascii() and value.isdigit() and int(value) > 0):
        raise ValueError(f"--handoff-at needs a whole number of tokens above 0, not {value!r}")
    return int(value), rest


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")   # the repo path may not fit the ANSI code page
    force = "--force" in argv
    argv = [a for a in argv if a != "--force"]
    try:
        handoff_at, argv = _take_handoff_at(argv)
    except ValueError as e:
        sys.exit(f"{e}\n{USAGE}")
    if len(argv) != 1 or not os.path.isdir(argv[0]):
        sys.exit(USAGE)
    progress = []
    try:
        changes, notices = _add(argv[0], force, progress=progress, handoff_at=handoff_at)
    except (ValueError, OSError) as e:
        # A ValueError is raised while reading or merging, before any write; an OSError means
        # e.g. <repo>/.claude is a regular file, or the folder is read-only. Every file is
        # written whole or not at all; name what was done before the error.
        if isinstance(e, ValueError) and not progress:
            print(f"Error: {e}; nothing written", file=sys.stderr)
            return 1
        print(f"Error: {e}", file=sys.stderr)
        if progress:
            print("Done before the error:", file=sys.stderr)
            for line in progress:
                print(f"  - {line}", file=sys.stderr)
        return 1
    print("\n".join(changes) or "already up to date")
    for notice in notices:
        print(f"note: {notice}")
    if changes:
        print("Commit .claude/settings.json and .claude/hooks/context_check.py in that repository.")
    return 0


def _add(repo, force, progress=None, handoff_at=None):
    """Merge the template into <repo>/.claude/settings.json and copy the hook; return
    (changes, notices). Each file written is appended to `progress` (when given) as it is
    done. The hook is copied before settings.json is written: a hook entry that points at a
    hook file that was never copied would exit 2 on every prompt."""
    if progress is None:
        progress = []
    claude_dir = os.path.join(repo, ".claude")
    path = os.path.join(claude_dir, "settings.json")
    target = os.path.join(claude_dir, "hooks", "context_check.py")
    for p in (path, target):
        if _is_link(p) and not os.path.exists(p):
            raise ValueError(f"{p} is a symlink to a missing target; fix or remove it first")
    settings = _read_json(path) if os.path.exists(path) else {}
    template = _read_json(TEMPLATE)
    if handoff_at is not None:
        # Claude Code passes `env` to the session and its hooks; its values are strings.
        template["env"] = {"IDEAL_UMBRELLA_HANDOFF_AT": str(handoff_at)}
    try:
        changes, notices = merge(settings, template, force=force)
    except ValueError as e:
        raise ValueError(f"{path}: {e}") from None

    old = b""
    if os.path.exists(target):
        with open(target, "rb") as f:
            old = f.read()
    with open(SCRIPT, "rb") as f:
        source = f.read()
    hook_changed = source != old
    if hook_changed:
        _write_bytes(target, source)
        progress.append(".claude/hooks/context_check.py written")
    if changes:
        _write_json(path, settings)
        progress.append(".claude/settings.json written")
    if hook_changed:
        changes.append(".claude/hooks/context_check.py written")
    return changes, notices


if __name__ == "__main__":
    sys.exit(main())
