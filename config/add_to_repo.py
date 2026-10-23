"""Ideal-Umbrella: give a repository's cloud sessions the hook and the two keys.

Cloud sessions read only the repository's committed .claude/settings.json, not
~/.claude/. This copies hooks/context_check.py to <repo>/.claude/hooks/ and
merges config/repo-settings.json into <repo>/.claude/settings.json, keeping the
file's other keys and hooks. Running it again changes nothing. The hook exits
at once unless CLAUDE_CODE_REMOTE is true, so local sessions keep only the
user-level hook. Stdlib only; run with `python -I config/add_to_repo.py <repo>`,
then commit the two files in that repository.
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "repo-settings.json")
SCRIPT = os.path.join(os.path.dirname(HERE), "hooks", "context_check.py")


def is_ours(entry):
    return any("context_check.py" in h.get("command", "") for h in entry.get("hooks", []))


def merge(settings, template):
    changes = []
    for key, value in template.items():
        if key != "hooks" and settings.get(key) != value:
            changes.append(f"{key}: {settings.get(key)} -> {value}")
            settings[key] = value
    hooks = settings.setdefault("hooks", {})
    for event, entries in template["hooks"].items():
        current = hooks.setdefault(event, [])
        kept = [e for e in current if not is_ours(e)]
        if kept + entries != current:
            changes.append(f"hooks.{event}: Ideal-Umbrella entry {'updated' if len(kept) < len(current) else 'added'}")
            hooks[event] = kept + entries
    return changes


def main():
    if len(sys.argv) != 2 or not os.path.isdir(sys.argv[1]):
        sys.exit("usage: python -I config/add_to_repo.py <repo folder>")
    claude_dir = os.path.join(sys.argv[1], ".claude")
    path = os.path.join(claude_dir, "settings.json")
    settings = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            try:
                settings = json.load(f)
            except ValueError as e:
                sys.exit(f"{path} is not valid JSON ({e}); fix it first, nothing written")
    with open(TEMPLATE, encoding="utf-8") as f:
        changes = merge(settings, json.load(f))
    if changes:
        os.makedirs(claude_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(settings, f, indent=2)
            f.write("\n")
    target = os.path.join(claude_dir, "hooks", "context_check.py")
    old = b""
    if os.path.exists(target):
        with open(target, "rb") as f:
            old = f.read()
    with open(SCRIPT, "rb") as f:
        if f.read() != old:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(SCRIPT, target)
            changes.append(".claude/hooks/context_check.py written")
    print("\n".join(changes) or "already up to date")
    if changes:
        print("Commit .claude/settings.json and .claude/hooks/context_check.py in that repository.")


if __name__ == "__main__":
    main()