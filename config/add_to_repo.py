"""Ideal-Umbrella: give a repository's cloud sessions the hook and the two keys,
and a learnings file.

Cloud sessions read only the repository's committed .claude/settings.json, not
~/.claude/. This copies hooks/context_check.py to <repo>/.claude/hooks/ and
merges config/repo-settings.json into <repo>/.claude/settings.json. Other keys,
other hook entries and sibling hooks inside the same entry are preserved. A
scalar value the repository already sets (for example its own autoCompactWindow)
is kept and reported unless --force is given. An existing Ideal-Umbrella hook is
updated in place, not duplicated. Running it again changes nothing.

It also copies config/learnings.md (the Keyline template with the headings
decided, tried and ruled out, watch out) to <repo>/notes/learnings.md when that
file is absent. The file is the repository's own data from then on: later runs,
--force included, never touch it, and nothing removes it.

The hook exits at once unless CLAUDE_CODE_REMOTE is true, so local sessions keep
only the user-level hook. Stdlib only; run with
`python -I config/add_to_repo.py [--force] <repo>`, then commit the files it
names in that repository.
"""
import errno
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "repo-settings.json")
SCRIPT = os.path.join(os.path.dirname(HERE), "hooks", "context_check.py")
LEARNINGS = os.path.join(HERE, "learnings.md")


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


def _in_git_repo(repo):
    """True when git would look for a repository here: GIT_DIR is set, or `repo` or a folder
    above it, short of a GIT_CEILING_DIRECTORIES entry, holds a .git entry (a folder, or the
    file of a worktree or submodule)."""
    if os.environ.get("GIT_DIR"):
        return True
    ceilings = {os.path.realpath(c) for c in
                os.environ.get("GIT_CEILING_DIRECTORIES", "").split(os.pathsep) if c}
    folder = os.path.realpath(repo)
    while True:
        if os.path.exists(os.path.join(folder, ".git")):
            return True
        parent = os.path.dirname(folder)
        if parent == folder or parent in ceilings:
            return False
        folder = parent


def _git_ignored(repo, relatives):
    """{path: True when git ignores it, False when it does not or `repo` is in no repository,
    None when git cannot say (git missing, a timeout, an exit other than 0 or 1)}, from one
    `git check-ignore` call. Its input and output are files, not pipes, so a timed-out git
    child cannot hold the run on Windows."""
    if not relatives:
        return {}
    if not _in_git_repo(repo):
        return dict.fromkeys(relatives, False)
    try:
        with tempfile.TemporaryFile() as given, tempfile.TemporaryFile() as out:
            given.write("\0".join(relatives).encode("utf-8") + b"\0")
            given.seek(0)
            result = subprocess.run(["git", "-C", repo, "check-ignore", "-z", "--stdin"],
                                    stdin=given, stdout=out, stderr=subprocess.DEVNULL,
                                    timeout=10)
            out.seek(0)
            listed = set(out.read().decode("utf-8", "surrogateescape").split("\0"))
    except (OSError, subprocess.SubprocessError):
        return dict.fromkeys(relatives, None)
    if result.returncode not in (0, 1):
        return dict.fromkeys(relatives, None)
    return {r: r in listed for r in relatives}


def _repo_path(repo, full):
    """Where `full` really lands, symlinks resolved, relative to the real `repo` with "/"
    separators (the path git knows it by); None when that is outside the repository."""
    try:
        rel = os.path.relpath(os.path.realpath(full), os.path.realpath(repo))
    except ValueError:   # another drive on Windows
        return None
    if rel == os.pardir or rel.startswith(os.pardir + os.sep):
        return None
    return rel.replace(os.sep, "/")


def _unsure(relative):
    return f"git could not say whether {relative} is ignored; check that git tracks it"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")   # the repo path may not fit the ANSI code page
    force = "--force" in argv
    argv = [a for a in argv if a != "--force"]
    if len(argv) != 1 or not os.path.isdir(argv[0]):
        sys.exit("usage: python -I config/add_to_repo.py [--force] <repo folder>")
    progress, commit = [], []
    try:
        changes, notices = _add(argv[0], force, progress=progress, commit=commit)
    except ValueError as e:
        # Raised while reading or merging, before any write.
        print(f"Error: {e}; nothing written", file=sys.stderr)
        return 1
    except OSError as e:
        # e.g. <repo>/.claude is a regular file, or the folder is read-only. Every file is
        # written whole or not at all; name what was done before the error.
        print(f"Error: {e}", file=sys.stderr)
        if progress:
            print("Done before the error:", file=sys.stderr)
            for name in progress:
                print(f"  - {name} written", file=sys.stderr)
        return 1
    print("\n".join(changes) or "already up to date")
    for notice in notices:
        print(f"note: {notice}")
    # Name only the files written this run that git can take: an untouched one has nothing to
    # commit, an ignored one or one outside the repository has its own note.
    files = commit
    if files:
        names = files[0] if len(files) == 1 else ", ".join(files[:-1]) + " and " + files[-1]
        print(f"Commit {names} in that repository.")
    return 0


def _add(repo, force, progress=None, commit=None):
    """Merge the template into <repo>/.claude/settings.json, copy the hook and, when the
    repository has no notes/learnings.md, the learnings template; return (changes, notices).
    The repository-relative path of each file written is appended to `progress` (when given)
    as it is done; `commit` gets the path git knows each written file by (symlinks resolved),
    unless git ignores it or it lands outside the repository. settings.json is written after
    the hook: a hook entry that points at a hook file that was never copied would exit 2 on
    every prompt. A hook or settings file that git ignores, or that a symlink puts outside the
    repository, is written all the same (local sessions use it) and gets a notice on every run.
    The learnings file is a courtesy and comes last: a failure there (a `notes` file in the
    way, a dangling link) is a notice, not an error, and a `notes/` that git ignores or that
    leads outside the repository gets no copy (cloud sessions would never see it)."""
    if progress is None:
        progress = []
    if commit is None:
        commit = []
    claude_dir = os.path.join(repo, ".claude")
    path = os.path.join(claude_dir, "settings.json")
    target = os.path.join(claude_dir, "hooks", "context_check.py")
    learnings = os.path.join(repo, "notes", "learnings.md")
    # A dangling link, on a file or on a folder above it, would be written through: the
    # missing target would be created outside the repository. For the core files that is an
    # error; for the courtesy file it means no copy.
    for p in (claude_dir, os.path.dirname(target), path, target):
        if _is_link(p) and not os.path.exists(p):
            raise ValueError(f"{p} is a symlink to a missing target; fix or remove it first")
    dangling = next((p for p in (os.path.dirname(learnings), learnings)
                     if _is_link(p) and not os.path.exists(p)), None)
    settings = _read_json(path) if os.path.exists(path) else {}
    template = _read_json(TEMPLATE)
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
    # An existing notes/learnings.md is the repository's own, whatever it holds: never replaced.
    copy_learnings = dangling is None and not os.path.exists(learnings)
    learnings_template = b""
    if copy_learnings:
        with open(LEARNINGS, "rb") as f:
            learnings_template = f.read()
    hook_changed = source != old
    # Where each file lands and what git says of it, asked once before anything is written.
    core = {".claude/hooks/context_check.py": target, ".claude/settings.json": path}
    real = {name: _repo_path(repo, full) for name, full in core.items()}
    real["notes/learnings.md"] = _repo_path(repo, learnings) if copy_learnings else None
    asked = [r for name, r in real.items() if r is not None and
             (name != "notes/learnings.md" or copy_learnings)]
    ignored = _git_ignored(repo, asked)

    if hook_changed:
        _write_bytes(target, source)
        progress.append(".claude/hooks/context_check.py")
    if changes:
        _write_json(path, settings)
        progress.append(".claude/settings.json")
    if hook_changed:
        changes.append(".claude/hooks/context_check.py written")
    for name, full in core.items():
        if real[name] is None:
            notices.append(f"{name} lands outside the repository through a symlink "
                           f"({os.path.realpath(full)}), so cloud sessions will not see it")
        elif ignored[real[name]]:
            notices.append(f"{name} is ignored by git, so cloud sessions will not see it; "
                           "unignore it or commit it with git add -f")
        else:
            if ignored[real[name]] is None:
                notices.append(_unsure(real[name]))
            if name in progress:
                commit.append(real[name])
    if dangling is not None:
        notices.append(f"notes/learnings.md not copied: {dangling} is a symlink to a missing target")
    elif copy_learnings and real["notes/learnings.md"] is None:
        copy_learnings = False
        notices.append("notes/learnings.md not copied: a symlink puts it outside the repository "
                       f"({os.path.realpath(learnings)}), so cloud sessions would not see it")
    elif copy_learnings and ignored[real["notes/learnings.md"]]:
        copy_learnings = False
        notices.append("notes/learnings.md not copied: git ignores it, so cloud sessions "
                       "would not see it")
    if copy_learnings:
        try:
            _write_bytes(learnings, learnings_template)
        except OSError as e:
            notices.append(f"notes/learnings.md not written ({e}); the hook and settings are "
                           "installed")
        else:
            progress.append("notes/learnings.md")
            commit.append(real["notes/learnings.md"])
            if ignored[real["notes/learnings.md"]] is None:
                notices.append(_unsure(real["notes/learnings.md"]))
            changes.append("notes/learnings.md written (the learnings template; it is yours "
                           "now, later runs leave it)")
    return changes, notices


if __name__ == "__main__":
    sys.exit(main())
