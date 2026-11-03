"""What does each skill cost? Always-on listing cost and per-invocation cost.

Usage:
  python -I scripts/skill_bill.py [FOLDER ...]

Each FOLDER is searched for skill folders (a folder holding SKILL.md). Default: ~/.claude/skills
and the Claude app folder (installed plugins; CLAUDE_APP_DIR, else the folder for your OS, as in
plugin_cost.py).
  always-on    tokens of the skill's line in the skill listing ("- name: description"), which
               is in context on every call
  invocation   tokens of SKILL.md without its frontmatter, plus each other file in the skill
               folder that SKILL.md names by its relative path
A skill with `disable-model-invocation: true` is flagged user-only and has no always-on cost (its
description is not in context). A skill whose frontmatter sets `model` (other than `inherit`) is flagged: per the skills docs
at code.claude.com the override applies for the rest of the turn, and switching models
recomputes the whole request.
Token counts use tiktoken o200k_base as a proxy, like plugin_cost.py; Claude's tokenizer is not
public, so the numbers are directional.
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # -I leaves the script folder off
import plugin_cost as pc                                          # noqa: E402

MAX_SKILLS = 400
MAX_REFERENCED_FILES = 200
SKIP_FOLDERS = {"node_modules", ".git"}


def load_counter():
    """A function counting the tokens of a text (tiktoken o200k_base). Raises RuntimeError with a
    one-line reason."""
    os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(pc.TIKTOKEN_CACHE))
    try:
        import tiktoken
    except ImportError:
        raise RuntimeError("tiktoken is not installed; run: pip install tiktoken")
    try:
        enc = tiktoken.get_encoding("o200k_base")
    except Exception as e:   # offline on first use, a proxy, a corrupt cache: any of them
        raise RuntimeError(f"tiktoken could not load o200k_base: {e}")
    return lambda text: len(enc.encode(text, disallowed_special=()))


def read_text(path):
    with open(path, encoding="utf-8-sig", errors="ignore") as f:
        return f.read()


def split_frontmatter(text):
    """(frontmatter text, body); no frontmatter gives ("", text)."""
    m = re.match(r"---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", text, re.S)
    return (m.group(1), text[m.end():]) if m else ("", text)


def front_value(front, key):
    m = re.search(rf"^{key}:[ \t]*(.*)$", front, re.M)
    return m.group(1).strip().strip("'\"") if m else None


def _raise(error):
    raise error


def skill_folders(folder):
    """Folders under `folder` (itself included) that hold SKILL.md, not looking inside one."""
    found, seen = [], set()
    top = os.path.realpath(str(folder))
    for root, dirs, names in os.walk(str(folder), followlinks=True, onerror=_raise):
        real = os.path.realpath(root)
        try:
            above = real != top and os.path.commonpath([real, top]) == real
        except ValueError:
            above = False      # another drive on Windows: not above the folder
        if real in seen or above:   # a link back into a folder already walked, or up to one holding it
            dirs[:] = []
            continue
        seen.add(real)
        if "SKILL.md" in names:
            found.append(root)
            dirs[:] = []
        else:
            dirs[:] = sorted(d for d in dirs if d not in SKIP_FOLDERS)
        if len(found) >= MAX_SKILLS:
            print(f"note: stopped after {MAX_SKILLS} skills in {folder}", file=sys.stderr)
            break
    return sorted(found)


def referenced_files(folder, body):
    """Files in the skill folder (not SKILL.md) whose relative path SKILL.md mentions."""
    out, seen = [], 0
    for root, dirs, names in os.walk(folder, onerror=_raise):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_FOLDERS)
        for name in sorted(names):
            path = os.path.join(root, name)
            rel = os.path.relpath(path, folder).replace(os.sep, "/")
            seen += 1
            if seen > MAX_REFERENCED_FILES:
                return out
            if rel != "SKILL.md" and rel in body:
                out.append(path)
    return out


def analyse(folders, count):
    rows, seen = [], set()
    for folder in folders:
        for skill in skill_folders(folder):
            real = os.path.realpath(skill)
            if real in seen:
                continue
            seen.add(real)
            text = read_text(os.path.join(skill, "SKILL.md"))
            front, body = split_frontmatter(text)
            name = front_value(front, "name") or os.path.basename(skill)
            description = pc.desc_of(os.path.join(skill, "SKILL.md"))[:pc.DESCRIPTION_LIMIT]
            model = front_value(front, "model")
            user_only = (front_value(front, "disable-model-invocation") or "").lower() == "true"
            invocation = count(body) + sum(count(read_text(p)) for p in referenced_files(skill, body))
            rows.append({"name": name, "user_only": user_only,
                         "always_on": 0 if user_only else count(f"- {name}: {description}\n"),
                         "invocation": invocation, "model": model if model and model != "inherit" else None})
    return sorted(rows, key=lambda r: (-r["invocation"], r["name"]))


def default_folders():
    """~/.claude/skills and each installed plugin. The app's desktop-session folders hold copies
    Claude Code does not load, so they are left out."""
    app = pc.default_app_dir()
    plugins = [str(r) for r in pc.plugin_roots(app) if "local-agent-mode-sessions" not in Path(r).parts]         if os.path.isdir(app) else []
    config = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    cli_plugins = [str(r) for r in pc.plugin_roots(config / "plugins")] if (config / "plugins").is_dir() else []
    return [str(config / "skills"), *cli_plugins, *plugins]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if hasattr(sys.stdout, "reconfigure"):
        # -I ignores PYTHONUTF8: set UTF-8 output here
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    folders = argv
    if folders:
        for folder in folders:
            if not os.path.isdir(folder):
                sys.exit(f"{folder} is not a folder")
    else:
        folders = [f for f in default_folders() if os.path.isdir(f)]
    try:
        count = load_counter()
    except RuntimeError as e:
        sys.exit(str(e))
    try:
        rows = analyse(folders, count)
    except OSError as e:
        sys.exit(f"cannot read {e.filename or 'a skill folder'} ({e.strerror or e})")
    if not rows:
        sys.exit("no SKILL.md found in " + ", ".join(folders or ["the default folders"]))
    print(f"{len(rows)} skills; always-on listing {sum(r['always_on'] for r in rows):,} tokens "
          "(o200k proxy: Claude's tokenizer is not public, so these are directional)")
    print(f"{'skill':36} {'always-on':>9} {'per use':>8}  flag")
    for r in rows:
        flag = ", ".join(f for f in (f"model: {r['model']}" if r["model"] else "",
                                     "user-only" if r["user_only"] else "") if f)
        print(f"{r['name'][:36]:36} {r['always_on']:>9,} {r['invocation']:>8,}  {flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
