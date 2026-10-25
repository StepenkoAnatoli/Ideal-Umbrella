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
`python -I config/add_to_repo.py [--force] <repo>`, then commit the two files in
that repository.
"""
import json
import os
import sys
import tempfile

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
        if key == "hooks":
            continue
        if key not in settings:
            changes.append(f"{key}: added {value!r}")
            settings[key] = value
        elif settings[key] != value:
            if force:
                changes.append(f"{key}: {settings[key]!r} -> {value!r}")
                settings[key] = value
            else:
                notices.append(f"{key} is {settings[key]!r}, template has {value!r}; "
                               "left unchanged (use --force)")

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


def _write_bytes(path, data):
    """Write whole or not at all (temp file beside the target, then rename), through a
    symlink instead of replacing the link, keeping the file's mode."""
    path = os.path.realpath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{os.path.basename(path)}-", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        if os.path.exists(path):
            os.chmod(tmp, os.stat(path).st_mode & 0o7777)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _write_json(path, data):
    _write_bytes(path, (json.dumps(data, indent=2) + "\n").encode("utf-8"))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")   # the repo path may not fit the ANSI code page
    force = "--force" in argv
    argv = [a for a in argv if a != "--force"]
    if len(argv) != 1 or not os.path.isdir(argv[0]):
        sys.exit("usage: python -I config/add_to_repo.py [--force] <repo folder>")
    try:
        changes, notices = _add(argv[0], force)
    except ValueError as e:
        # Raised while reading or merging, before any write.
        print(f"Error: {e}; nothing written", file=sys.stderr)
        return 1
    except OSError as e:
        # e.g. <repo>/.claude is a regular file, or the folder is read-only.
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print("\n".join(changes) or "already up to date")
    for notice in notices:
        print(f"note: {notice}")
    if changes:
        print("Commit .claude/settings.json and .claude/hooks/context_check.py in that repository.")
    return 0


def _add(repo, force):
    """Merge the template into <repo>/.claude/settings.json and copy the hook; return
    (changes, notices)."""
    claude_dir = os.path.join(repo, ".claude")
    path = os.path.join(claude_dir, "settings.json")
    target = os.path.join(claude_dir, "hooks", "context_check.py")
    for p in (path, target):
        if os.path.islink(p) and not os.path.exists(p):
            raise ValueError(f"{p} is a symlink to a missing target; fix or remove it first")
    settings = _read_json(path) if os.path.exists(path) else {}
    template = _read_json(TEMPLATE)
    try:
        changes, notices = merge(settings, template, force=force)
    except ValueError as e:
        raise ValueError(f"{path}: {e}") from None

    if changes:
        _write_json(path, settings)

    old = b""
    if os.path.exists(target):
        with open(target, "rb") as f:
            old = f.read()
    with open(SCRIPT, "rb") as f:
        source = f.read()
    if source != old:
        _write_bytes(target, source)
        changes.append(".claude/hooks/context_check.py written")
    return changes, notices


if __name__ == "__main__":
    sys.exit(main())
