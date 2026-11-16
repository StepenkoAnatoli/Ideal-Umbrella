"""Small reversible installer. No approval bypass, tool removal or model changes."""
import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shlex
import sys
import time
import tomllib
from . import __version__
from .storage import atomic_write, read_json, write_json

SOURCE = Path(__file__).resolve().parent.parent
MANIFEST = "gpt-umbrella/install-record.json"
RUNTIME_FILES = {"gpt-umbrella/runtime/umbrella.py", "gpt-umbrella/runtime/templates/rules.md"} | {
    f"gpt-umbrella/runtime/gpt_umbrella/{name}.py"
    for name in ("__init__", "analyze", "audit", "cli", "install", "monitor", "storage", "usage")}
OWNED_FILES = RUNTIME_FILES | {"config.toml", "AGENTS.md", "hooks.json"}


def load_record(home):
    """The journal is data, never authority to touch arbitrary Codex-home files."""
    record = read_json(safe_path(home, MANIFEST))
    if not isinstance(record, dict) or record.get("version") != 1 or record.get("status") not in ("pending", "installed"):
        raise ValueError("invalid installation record")
    files = record.get("files")
    if not isinstance(files, dict) or set(files) - OWNED_FILES or not RUNTIME_FILES.issubset(files):
        raise ValueError("installation record contains unowned or missing runtime paths")
    if not {"AGENTS.md", "hooks.json"}.issubset(files):
        raise ValueError("installation record is missing owned configuration files")
    is_hash = lambda value: isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    for name, info in files.items():
        if not isinstance(info, dict) or not is_hash(info.get("after")):
            raise ValueError("invalid recorded file checksum")
        before, backup = info.get("before"), info.get("backup")
        if before is None:
            if backup is not None:
                raise ValueError("unexpected backup for a newly created file")
        else:
            if not is_hash(before) or not isinstance(backup, str):
                raise ValueError("invalid recorded backup")
            parts = backup.split("/")
            if len(parts) < 4 or parts[:2] != ["gpt-umbrella", "backups"] or not parts[2].isascii() or not parts[2].isdigit() or "/".join(parts[3:]) != name:
                raise ValueError("backup is outside its owned namespace")
        safe_path(home, name)
    blocks = record.get("blocks")
    if not isinstance(blocks, list) or len(blocks) > 3:
        raise ValueError("invalid managed block list")
    allowed = {"AGENTS.md": ("<!-- GPT Umbrella rules: begin -->", "<!-- GPT Umbrella rules: end -->"),
               "output": ("# GPT Umbrella output: begin", "# GPT Umbrella output: end"),
               "skills": ("# GPT Umbrella skills: begin", "# GPT Umbrella skills: end")}
    for block in blocks:
        if not isinstance(block, dict) or block.get("file") not in ("config.toml", "AGENTS.md") or not isinstance(block.get("text"), str):
            raise ValueError("invalid owned instruction/config block")
        lines = block["text"].strip().splitlines()
        choices = [allowed["AGENTS.md"]] if block["file"] == "AGENTS.md" else [allowed["output"], allowed["skills"]]
        if len(lines) < 3 or not any(lines[0] == start and lines[-1] == end for start, end in choices):
            raise ValueError("recorded block lacks owned markers")
    hooks = record.get("hooks")
    if not isinstance(hooks, dict) or "UserPromptSubmit" not in hooks or set(hooks) - {"UserPromptSubmit", "PostModelRequest", "PostCompact"}:
        raise ValueError("invalid recorded hook events")
    for entry in hooks.values():
        if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list) or len(entry["hooks"]) != 1:
            raise ValueError("invalid owned hook group")
        hook = entry["hooks"][0]
        if not isinstance(hook, dict) or hook.get("type") != "command" or hook.get("statusMessage") != "GPT Umbrella context monitor" or not isinstance(hook.get("command"), str):
            raise ValueError("invalid owned hook definition")
    return record


@contextmanager
def mutation_lock(home):
    path = safe_path(home, "gpt-umbrella/mutation.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError("another install/uninstall is active; inspect mutation.lock if a previous process crashed")
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        path.unlink(missing_ok=True)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(home, relative):
    p = home / relative
    if p.resolve().is_relative_to(home.resolve()) is False:
        raise ValueError("install path escapes Codex home")
    current = p
    while current != home.parent:
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise ValueError(f"linked install path is not supported: {current}")
        current = current.parent
    if p.exists() and not p.is_file():
        raise ValueError(f"expected a file: {p}")
    return p


def command_quote(value):
    # Quote the explicit PowerShell payload on Windows, independent of the host shell.
    if os.name == "nt":
        return "'" + str(value).replace("'", "''") + "'"
    return shlex.quote(str(value))


def hook_entries(home):
    script = home / "gpt-umbrella/runtime/umbrella.py"
    parts = [sys.executable, "-I", script, "hook", "--home", home]
    command = ("& " if os.name == "nt" else "") + " ".join(command_quote(p) for p in parts)
    if os.name == "nt":
        payload = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
        command = "powershell.exe -NoProfile -NonInteractive -EncodedCommand " + payload
    return {event: {"hooks": [{"type": "command", "command": command, "timeout": 5,
                               "statusMessage": "GPT Umbrella context monitor"}]}
            for event in ("UserPromptSubmit",)}


def marked(label, body, newline="\n", markdown=False):
    start = f"<!-- GPT Umbrella {label}: begin -->" if markdown else f"# GPT Umbrella {label}: begin"
    end = f"<!-- GPT Umbrella {label}: end -->" if markdown else f"# GPT Umbrella {label}: end"
    return newline.join((start, body.strip().replace("\n", newline), end, ""))


def plan(home, preset):
    if (home / MANIFEST).exists():
        record = load_record(home)
        if record.get("status") == "installed":
            issues = verify(home)
            if issues:
                raise ValueError("installation was changed; uninstall before reinstalling: " + "; ".join(issues))
            if record.get("preset") != preset:
                raise ValueError("uninstall before selecting a different preset")
            if record.get("package_version", "0.1.0") != __version__:
                raise ValueError("installed version differs; uninstall and reinstall to update")
            return {}, record
        raise ValueError("incomplete install record; run uninstall to recover before reinstalling")
    changes, blocks = {}, []
    config = safe_path(home, "config.toml")
    raw = config.read_bytes() if config.exists() else b""
    text = raw.decode("utf-8-sig")
    bom = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
    nl = "\r\n" if "\r\n" in text else "\n"
    settings = tomllib.loads(text)
    if "GPT Umbrella" in text:
        raise ValueError("untracked GPT Umbrella config markers; resolve before installation")
    notices = []
    if preset == "balanced":
        if "tool_output_token_limit" not in settings:
            block = marked("output", "tool_output_token_limit = 6000", nl)
            text = block + text
            blocks.append({"file": "config.toml", "text": block})
        else:
            notices.append("Existing tool_output_token_limit preserved.")
        if "skills" not in settings:
            block = nl + marked("skills", "[skills]\nmax_context_tokens = 5000", nl)
            text += block
            blocks.append({"file": "config.toml", "text": block})
        else:
            notices.append("Existing skills configuration preserved; skill budget not changed.")
    tomllib.loads(text)
    if bom + text.encode() != raw:
        changes["config.toml"] = bom + text.encode()
    agents = safe_path(home, "AGENTS.md")
    raw = agents.read_bytes() if agents.exists() else b""
    body = raw.decode("utf-8-sig")
    if "GPT Umbrella rules:" in body:
        raise ValueError("untracked GPT Umbrella instruction markers")
    nl = "\r\n" if "\r\n" in body else "\n"
    rules = (SOURCE / "templates/rules.md").read_text(encoding="utf-8")
    block = (nl if body and not body.endswith("\n") else "") + marked("rules", rules, nl, True)
    blocks.append({"file": "AGENTS.md", "text": block})
    changes["AGENTS.md"] = raw + block.encode()
    hooks_path = safe_path(home, "hooks.json")
    hooks = read_json(hooks_path) if hooks_path.exists() else {}
    if not isinstance(hooks, dict) or not isinstance(hooks.get("hooks", {}), dict):
        raise ValueError("hooks.json must contain an object with an optional hooks object")
    if "hooks" in settings:
        notices.append("Inline hooks already exist; Codex will merge both hook sources.")
    entries = hook_entries(home)
    for event, entry in entries.items():
        target = hooks.setdefault("hooks", {}).setdefault(event, [])
        if not isinstance(target, list):
            raise ValueError("hook event must contain an array")
        target.append(entry)
    changes["hooks.json"] = (json.dumps(hooks, indent=2, ensure_ascii=True) + "\n").encode()
    runtime = [SOURCE / "umbrella.py", *sorted((SOURCE / "gpt_umbrella").glob("*.py")), SOURCE / "templates/rules.md"]
    for path in runtime:
        relative = "gpt-umbrella/runtime/" + path.relative_to(SOURCE).as_posix()
        dest = safe_path(home, relative)
        if dest.exists():
            raise ValueError(f"untracked runtime file: {dest}")
        changes[relative] = path.read_bytes()
    record = {"version": 1, "package_version": __version__, "preset": preset, "status": "pending", "blocks": blocks,
              "hooks": entries, "notices": notices, "files": {}}
    return changes, record


def install(home, preset="balanced", dry_run=False):
    home = Path(home).absolute()
    # Preflight first, so invalid inputs and previews do not create a lock directory.
    plan(home, preset)
    if dry_run:
        return _install(home, preset, True)
    with mutation_lock(home):
        return _install(home, preset, False)


def _install(home, preset="balanced", dry_run=False):
    home = Path(home).absolute()
    changes, record = plan(home, preset)
    result = {"home": str(home), "preset": preset, "changes": list(changes),
              "notices": record.get("notices", []), "hook_trust": "Codex must review and trust these exact hooks before they run."}
    if dry_run or not changes:
        result["dry_run"] = dry_run
        return result
    # Validate every path and existing file before the first write.
    originals = {}
    for name in changes:
        path = safe_path(home, name)
        if path.exists() and not path.stat().st_mode & 0o200:
            raise ValueError(f"read-only file: {path}")
        originals[name] = path.read_bytes() if path.exists() else None
    stamp = str(time.time_ns())
    for name, data in changes.items():
        old = originals[name]
        backup = f"gpt-umbrella/backups/{stamp}/{name}" if old is not None else None
        if backup:
            atomic_write(safe_path(home, backup), old)
        record["files"][name] = {"before": digest(old) if old is not None else None,
                                 "after": digest(data), "backup": backup}
    write_json(safe_path(home, MANIFEST), record)  # durable rollback information first
    applied = []
    try:
        for name, data in changes.items():
            target = safe_path(home, name)
            current = target.read_bytes() if target.exists() else None
            if current != originals[name]:
                raise ValueError(f"file changed during installation: {name}")
            atomic_write(target, data)
            applied.append(name)
        record["status"] = "installed"
        write_json(home / MANIFEST, record)
    except Exception:
        complete = True
        for name in reversed(applied):
            target = safe_path(home, name)
            if not target.exists() or digest(target.read_bytes()) != record["files"][name]["after"]:
                complete = False  # preserve edits made by another process
                continue
            old = originals[name]
            if old is not None:
                atomic_write(target, old)
            else:
                target.unlink(missing_ok=True)
        if complete:
            (home / MANIFEST).unlink(missing_ok=True)
        raise
    result["installed"] = True
    return result


def verify(home):
    path = home / MANIFEST
    if not path.exists():
        return ["not installed"]
    record = load_record(home)
    issues = []
    if record.get("status") != "installed":
        issues.append("incomplete installation")
    for name, info in record["files"].items():
        target = safe_path(home, name)
        if not target.exists() or digest(target.read_bytes()) != info["after"]:
            issues.append(f"changed or missing: {name}")
    return issues


def uninstall(home, dry_run=False):
    home = Path(home).absolute()
    preview = _uninstall(home, True)
    if dry_run or not (home / MANIFEST).exists():
        return preview
    with mutation_lock(home):
        return _uninstall(home, False)


def _uninstall(home, dry_run=False):
    path = safe_path(home, MANIFEST)
    if not path.exists():
        return {"changes": [], "notices": ["Not installed."]}
    record = load_record(home)
    changes, notices = {}, []
    keep_runtime = False
    hook_file = safe_path(home, "hooks.json")
    # A previously restored hooks file means an interrupted uninstall already did this step.
    if hook_file.exists() and digest(hook_file.read_bytes()) != record["files"]["hooks.json"]["before"]:
        current_hooks = read_json(hook_file)
        for event, entry in record["hooks"].items():
            if entry not in current_hooks.get("hooks", {}).get(event, []):
                keep_runtime = True
                break
    if keep_runtime:
        notices.append("Runtime retained because a registered hook was changed or removed; inspect hooks before deleting it.")
    originals = {}
    for name, info in record["files"].items():
        if keep_runtime and name.startswith("gpt-umbrella/runtime/"):
            continue
        target = safe_path(home, name)
        if not target.exists():
            continue
        current = target.read_bytes()
        originals[name] = current
        if digest(current) == info["after"]:
            if info["backup"]:
                old = safe_path(home, info["backup"]).read_bytes()
                if digest(old) != info["before"]:
                    raise ValueError("backup checksum mismatch")
                changes[name] = old
            else:
                changes[name] = None
        elif digest(current) == info["before"]:
            continue  # pending transaction did not write this file
        elif name in ("config.toml", "AGENTS.md"):
            edited = current
            for block in record["blocks"]:
                needle = block["text"].encode()
                if block["file"] == name and edited.count(needle) == 1:
                    replacement = b""
                    if name == "config.toml" and "[skills]" in block["text"]:
                        settings = tomllib.loads(edited.decode("utf-8-sig"))
                        if set(settings.get("skills", {})) - {"max_context_tokens"}:
                            replacement = b"\n[skills]\n"
                    edited = edited.replace(needle, replacement, 1)
                elif block["file"] == name:
                    notices.append(f"Preserved edited/missing managed block in {name}.")
            if name == "config.toml":
                tomllib.loads(edited.decode("utf-8-sig"))
            if edited != current:
                changes[name] = edited
        elif name == "hooks.json":
            hooks = read_json(target)
            for event, entry in record["hooks"].items():
                values = hooks.get("hooks", {}).get(event, [])
                if entry in values:
                    values.remove(entry)
                    if not values:
                        del hooks["hooks"][event]
                else:
                    notices.append(f"Preserved changed/missing hook for {event}.")
            changes[name] = (json.dumps(hooks, indent=2) + "\n").encode()
        else:
            notices.append(f"Preserved edited runtime file: {name}.")
    result = {"changes": list(changes), "notices": notices, "dry_run": dry_run,
              "retained": "Backups and numeric monitor state are retained under gpt-umbrella/."}
    if not dry_run:
        # The manifest remains until every write succeeds; rerunning finishes an interrupted undo.
        for name, data in changes.items():
            target = safe_path(home, name)
            if not target.exists() or target.read_bytes() != originals[name]:
                raise ValueError(f"file changed during uninstall: {name}")
            if data is None:
                target.unlink(missing_ok=True)
            else:
                atomic_write(target, data)
        path.unlink()
    return result
