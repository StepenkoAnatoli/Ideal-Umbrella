"""Estimate what each installed Claude Desktop plugin adds to the skill listing.

Usage: python -I scripts/plugin_cost.py <output.json> [Claude app folder]
The Claude app folder holds the installed plugins (each with a .claude-plugin/plugin.json).
Default: CLAUDE_APP_DIR if set, else %APPDATA%\\Claude on Windows,
~/Library/Application Support/Claude on macOS, ~/.config/Claude elsewhere.
Token counts use tiktoken o200k_base as a proxy, with the cache under keyline/cache/tiktoken.
"""
import glob
import io
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIKTOKEN_CACHE = ROOT / "keyline" / "cache" / "tiktoken"
DESCRIPTION_LIMIT = 1536


def default_app_dir():
    env = os.environ.get("CLAUDE_APP_DIR")
    if env:
        return Path(env)
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "Claude"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude"
    return Path.home() / ".config" / "Claude"


def desc_of(md):
    try:
        t = open(md, encoding="utf-8-sig", errors="ignore").read()
    except OSError:
        return ""
    m = re.match(r"---\s*\n(.*?)\n---", t, re.S)
    if not m:
        return ""
    fm = m.group(1)
    d = re.search(r"^description:\s*(.*?)(?=^\w[\w-]*:|\Z)", fm, re.S | re.M)
    return re.sub(r"\s+", " ", d.group(1)).strip().strip("'\"") if d else ""


def plugin_roots(app_dir):
    pattern = os.path.join(glob.escape(str(app_dir)), "**", ".claude-plugin", "plugin.json")
    return sorted({os.path.dirname(os.path.dirname(p)) for p in glob.glob(pattern, recursive=True)})


def plugin_rows(app_dir, enc):
    rows = []
    for r in plugin_roots(app_dir):
        try:
            man = json.load(open(os.path.join(r, ".claude-plugin", "plugin.json"), encoding="utf-8"))
        except (OSError, ValueError, RecursionError):
            man = {}
        if not isinstance(man, dict):
            man = {}
        name = man.get("name") or os.path.basename(r)
        skills = glob.glob(os.path.join(glob.escape(r), "skills", "*", "SKILL.md")) + \
            glob.glob(os.path.join(glob.escape(r), "commands", "*.md"))
        tok = 0
        names = []
        for s in skills:
            sk = os.path.basename(os.path.dirname(s)) if s.endswith("SKILL.md") else os.path.splitext(os.path.basename(s))[0]
            names.append(sk)
            d = desc_of(s)[:DESCRIPTION_LIMIT]
            tok += len(enc.encode(f"- {name}:{sk}: {d}\n", disallowed_special=()))
        mcp = 0
        mf = os.path.join(r, ".mcp.json")
        if os.path.isfile(mf):
            try:
                mcp = len(json.load(open(mf, encoding="utf-8")).get("mcpServers") or {})
            except (OSError, ValueError, RecursionError, AttributeError):
                pass
        hooks = os.path.isfile(os.path.join(r, "hooks", "hooks.json")) or bool(man.get("hooks"))
        agents = len(glob.glob(os.path.join(glob.escape(r), "agents", "*.md")))
        rows.append((name, len(skills), tok, mcp, hooks, agents, sorted(names)))
    return rows


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")   # -I ignores PYTHONUTF8: set UTF-8 output here
    if not 1 <= len(argv) <= 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    out = Path(argv[0])
    app_dir = Path(argv[1]) if len(argv) == 2 else default_app_dir()
    if not app_dir.is_dir():
        print(f"Error: {app_dir} is not a folder (pass the Claude app folder as the second argument)",
              file=sys.stderr)
        return 1
    os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(TIKTOKEN_CACHE))
    try:
        import tiktoken
    except ImportError:
        print("tiktoken is not installed; run: pip install tiktoken", file=sys.stderr)
        return 1
    enc = tiktoken.get_encoding("o200k_base")

    rows = plugin_rows(app_dir, enc)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rows, f)
    tot = sum(x[2] for x in rows)
    print(f"{len(rows)} plugins, {sum(x[1] for x in rows)} skills/commands, "
          f"full listing would be {tot} tokens (o200k proxy)")
    print(f"{'plugin':28} {'skills':>6} {'list tok':>8} {'mcp':>4} {'hooks':>5} {'agents':>6}")
    for n, k, t, m, h, a, _ in sorted(rows, key=lambda x: -x[2]):
        print(f"{n:28} {k:6} {t:8} {m:4} {'yes' if h else '':>5} {a:6}")
    return 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.exit(main())
