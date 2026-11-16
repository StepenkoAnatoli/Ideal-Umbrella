import argparse
import json
import sys
from pathlib import Path
from . import __version__
from .analyze import analyze, discover, compare
from .audit import inventory, request_audit
from .install import install, uninstall, verify
from .monitor import run
from .storage import home_path, read_json, write_json


def parser():
    p = argparse.ArgumentParser(description="GPT Umbrella: measured context hygiene for local Codex")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("analyze", help="read local Codex JSONL or saved Responses JSON")
    a.add_argument("paths", nargs="*")
    a.add_argument("--latest", type=int)
    a.add_argument("--rates", help="JSON map of model IDs to per-million API rates")
    a.add_argument("--output")
    a.add_argument("--home")
    a = sub.add_parser("compare", help="compare measured report averages")
    a.add_argument("before")
    a.add_argument("after")
    a.add_argument("--output")
    a = sub.add_parser("audit", help="rank instruction and skill source sizes")
    a.add_argument("folder")
    a.add_argument("--output")
    a = sub.add_parser("audit-requests", help="offline API request cache/tool advice")
    a.add_argument("files", nargs="+")
    a.add_argument("--output")
    for action in ("install", "uninstall", "verify", "hook"):
        a = sub.add_parser(action)
        a.add_argument("--home", help="absolute Codex configuration directory, not the user home")
        if action in ("install", "uninstall"):
            a.add_argument("--dry-run", action="store_true")
        if action == "install":
            a.add_argument("--preset", choices=("balanced", "observe"), default="balanced")
        if action == "hook":
            a.add_argument("--threshold", type=float, default=0.75)
    return p


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    args = parser().parse_args(argv)
    try:
        if args.command == "hook":
            return run(home_path(args.home) / "gpt-umbrella/state", args.threshold)
        if args.command == "analyze":
            paths = args.paths or [home_path(args.home) / "sessions"]
            result = analyze(discover(paths, args.latest), read_json(args.rates) if args.rates else None)
        elif args.command == "compare":
            result = compare(read_json(args.before), read_json(args.after))
        elif args.command == "audit":
            result = inventory(args.folder)
        elif args.command == "audit-requests":
            result = request_audit([read_json(path) for path in args.files])
        elif args.command == "install":
            result = install(home_path(args.home), args.preset, args.dry_run)
        elif args.command == "uninstall":
            result = uninstall(home_path(args.home), args.dry_run)
        elif args.command == "verify":
            issues = verify(home_path(args.home))
            print(json.dumps({"files_match_install": not issues, "issues": issues,
                              "hook_trust": "Not inspected; check Codex Settings > Hooks or /hooks."}, indent=2))
            return int(bool(issues))
        if getattr(args, "output", None):
            write_json(Path(args.output), result)
            print(f"Wrote {Path(args.output).resolve()}")
        else:
            print(json.dumps(result, indent=2, ensure_ascii=True, allow_nan=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as error:
        message = " ".join(str(error).splitlines())
        print(f"GPT Umbrella: {message}", file=sys.stderr)
        return 1
