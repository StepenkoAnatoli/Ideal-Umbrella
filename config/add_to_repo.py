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
import posixpath
import re
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


def _git_ignored(repo, relatives):
    """{path: True when git ignores it, False when it does not or `repo` is in no repository
    (git says so), None when git cannot say (git missing, a timeout, any other failure:
    dubious ownership, a broken GIT_DIR)}, from one `git check-ignore` call; git itself finds
    the repository. Input, output and errors are files, not pipes, so a timed-out git child
    cannot hold the run on Windows. Paths go over as file-system bytes, so a folder name that
    is not UTF-8 reaches git as it is on disk."""
    if not relatives:
        return {}
    # Untranslated messages: "not a git repository" is read from stderr.
    env = dict(os.environ, LC_ALL="C", LANGUAGE="C")
    try:
        with tempfile.TemporaryFile() as given, tempfile.TemporaryFile() as out, \
                tempfile.TemporaryFile() as err:
            # "./" keeps a name that starts with ":" from being read as pathspec magic; git
            # echoes each path as given.
            given.write(b"".join(os.fsencode("./" + r) + b"\0" for r in relatives))
            given.seek(0)
            result = subprocess.run(["git", "-C", repo, "check-ignore", "-z", "--stdin"],
                                    stdin=given, stdout=out, stderr=err, env=env, timeout=10)
            out.seek(0)
            err.seek(0)
            listed = {os.fsdecode(p) for p in out.read().split(b"\0")}
            errors = err.read()
    except (OSError, ValueError, subprocess.SubprocessError):
        return dict.fromkeys(relatives, None)
    if result.returncode not in (0, 1):
        # Only discovery's own message: a broken GIT_DIR or a stale .git file says
        # "not a git repository: '<path>'", and git cannot answer then.
        no_repo = result.returncode == 128 and b"not a git repository (or any" in errors
        return dict.fromkeys(relatives, False if no_repo else None)
    return {r: "./" + r in listed for r in relatives}


def _relative(real_repo, full):
    """`full` relative to `real_repo` with "/" separators; None outside it (or on another
    drive on Windows)."""
    try:
        rel = os.path.relpath(full, real_repo)
    except ValueError:
        return None
    if rel == os.pardir or rel.startswith(os.pardir + os.sep):
        return None
    return rel.replace(os.sep, "/")


def _nested(real_repo, relative):
    """True when a folder on the way to `relative` has its own .git (a submodule or nested
    repository): git add refuses the path, and a clone does not have it."""
    folder = posixpath.dirname(relative)
    while folder:
        if os.path.lexists(os.path.join(real_repo, *folder.split("/"), ".git")):
            return True
        folder = posixpath.dirname(folder)
    return False


def _repo_path(real_repo, real_full):
    """`real_full` (symlinks resolved) as the path git knows it by; None when it is outside
    the repository or in a submodule or nested repository."""
    rel = _relative(real_repo, real_full)
    return None if rel is None or _nested(real_repo, rel) else rel


SEPARATORS = re.compile(r"[\\/]" if os.name == "nt" else "/")


def _links(real_repo, name):
    """Every symlink followed on the way to `name` (a "/" path in the repository): links to
    links and links in the middle of a target included, resolved one step at a time as the
    file system does. {the link's own path in the repository: "ok", "absolute" (its target is
    absolute or climbs out of the repository, so it points nowhere in a clone elsewhere) or
    "nested" (the link is in a submodule or nested repository, so a clone lacks it)}, in the
    order followed. Links outside the repository are left out."""
    links, current, parts, hops = {}, real_repo, name.split("/"), 0
    while parts:
        piece = parts.pop(0)
        if piece in ("", "."):
            continue
        if piece == "..":
            current = os.path.dirname(current)
            continue
        step = os.path.join(current, piece)
        if not _is_link(step):
            current = step
            continue
        hops += 1
        rel = _relative(real_repo, step)
        try:
            to = os.readlink(step) if hops <= 40 else None
        except OSError:
            to = None
        if to is None:   # a loop, or a junction readlink cannot read: realpath copes
            current = os.path.realpath(step)
            if rel is not None:
                links.setdefault(rel, "nested" if _nested(real_repo, rel) else "ok")
            continue
        if to.startswith("\\\\?\\UNC\\"):
            to = "\\\\" + to[8:]
        elif to.startswith("\\\\?\\"):
            to = to[4:]
        drive, rest = os.path.splitdrive(to)
        # Rooted ("\\Users\\u" on Windows, which 3.13's isabs no longer calls absolute) or with a
        # drive: either way it names a place outside any clone.
        absolute = os.path.isabs(to) or bool(drive) or bool(SEPARATORS.match(to))
        if rel is not None:
            if _nested(real_repo, rel):
                state = "nested"
            else:
                lexical = posixpath.normpath(posixpath.join(posixpath.dirname(rel),
                                                            to.replace(os.sep, "/")))
                out = lexical == ".." or lexical.startswith("../")
                state = "absolute" if absolute or out else "ok"
            links.setdefault(rel, state)
        if absolute:
            current = (drive or os.path.splitdrive(current)[0]) + os.sep
        parts = [p for p in SEPARATORS.split(rest) if p] + parts
    return links


def _unsure(relative):
    return f"git could not say whether {relative} is ignored; check that git tracks it"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if hasattr(sys.stdout, "reconfigure"):
        # The repo path may not fit the ANSI code page. A folder name that is not UTF-8
        # (POSIX) is printed as its bytes on disk, so it can be pasted into `git add`.
        for stream in (sys.stdout, sys.stderr):
            stream.reconfigure(encoding="utf-8", errors="surrogateescape" if os.name != "nt"
                               else "backslashreplace")
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
    if commit:
        names = commit[0] if len(commit) == 1 else ", ".join(commit[:-1]) + " and " + commit[-1]
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
    real_repo = os.path.realpath(repo)
    resolved = {name: os.path.realpath(full) for name, full in core.items()}
    resolved["notes/learnings.md"] = os.path.realpath(learnings)
    real = {name: _repo_path(real_repo, full) for name, full in resolved.items()}
    if not copy_learnings:
        real["notes/learnings.md"] = None
    # A symlink on the way is what a clone goes through: it is committed, and checked, too.
    links = {name: _links(real_repo, name) for name in real if real[name] is not None}
    asked = {r for r in real.values() if r is not None}
    asked.update(k for found in links.values() for k, state in found.items() if state != "nested")
    ignored = _git_ignored(repo, sorted(asked))
    unsure = set()

    def missing(name):
        """Why a clone would not have `name`: (reason, fix or None), or None when it would."""
        if real[name] is None:
            rel = _relative(real_repo, resolved[name])
            if rel is None:
                return f"it lands outside the repository ({resolved[name]})", None
            return f"it lands in a submodule or nested repository ({rel})", None
        unignore = "unignore it or commit it with git add -f"
        if ignored[real[name]]:
            return "git ignores it", unignore
        for link, state in links[name].items():
            if state == "nested":
                return (f"it is reached through the symlink {link}, which lies in a submodule "
                        "or nested repository"), None
            if state == "absolute":
                return (f"it is reached through the symlink {link}, whose target is an "
                        "absolute path or lies outside the repository"), None
            if ignored[link]:
                return f"it is reached through the symlink {link}, which git ignores", unignore
        return None

    def check(name, take):
        for p in (real[name], *links[name]):
            if take and p not in commit:
                commit.append(p)
            if ignored[p] is None and p not in unsure:
                unsure.add(p)
                notices.append(_unsure(p))

    if hook_changed:
        _write_bytes(target, source)
        progress.append(".claude/hooks/context_check.py")
    if changes:
        _write_json(path, settings)
        progress.append(".claude/settings.json")
    if hook_changed:
        changes.append(".claude/hooks/context_check.py written")
    for name in core:
        why = missing(name)
        if why is None:
            check(name, take=name in progress)
        else:
            notices.append(f"{name} is installed, but {why[0]}, so cloud sessions will not "
                           "see it" + (f"; {why[1]}" if why[1] else ""))
    if dangling is not None:
        notices.append(f"notes/learnings.md not copied: {dangling} is a symlink to a missing target")
    elif copy_learnings:
        why = missing("notes/learnings.md")
        if why is not None:
            copy_learnings = False
            notices.append(f"notes/learnings.md not copied: {why[0]}, so cloud sessions would "
                           "not see it" + (f"; {why[1]}" if why[1] else ""))
    if copy_learnings:
        try:
            _write_bytes(learnings, learnings_template)
        except OSError as e:
            notices.append(f"notes/learnings.md not written ({e}); the hook and settings are "
                           "installed")
        else:
            progress.append("notes/learnings.md")
            check("notes/learnings.md", take=True)
            changes.append("notes/learnings.md written (the learnings template; it is yours "
                           "now, later runs leave it)")
    return changes, notices


if __name__ == "__main__":
    sys.exit(main())
