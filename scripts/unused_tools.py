"""Report which tools were never called across Claude Code transcripts.

Useful for keeping permissions.deny honest: Anthropic adds/renames tools, and a
denied tool that is actually called would silently break sessions.

Usage: python scripts/unused_tools.py <transcripts-dir> [--top N]
Transcripts are the *.jsonl files Claude Code writes under ~/.claude/projects.
"""
import argparse
import collections
import glob
import json
import os
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--top", type=int, default=40)
    args = ap.parse_args()

    called = collections.Counter()
    sessions = 0
    for path in glob.glob(os.path.join(args.dir, "**", "*.jsonl"), recursive=True):
        sessions += 1
        with open(path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                m = e.get("message") or {}
                for b in m.get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        called[b.get("name")] += 1

    print(f"{sessions} transcripts, {sum(called.values())} tool calls")
    print(f"{len(called)} distinct tools called\n")
    print("Tools that were called (name: count):")
    for name, n in called.most_common(args.top):
        print(f"  {name}: {n}")
    if len(called) > args.top:
        print(f"  ... and {len(called) - args.top} more")

    denied = ["Artifact", "ScheduleWakeup", "ReportFindings", "SearchPlugins",
              "SuggestPluginInstall", "SuggestSkills"]
    print("\nDenied tools check:")
    for t in denied:
        n = called.get(t, 0)
        print(f"  {t}: called {n} time(s)" + ("  <- REVIEW (was used)" if n else ""))


if __name__ == "__main__":
    sys.exit(main())
