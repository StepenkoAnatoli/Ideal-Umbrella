#!/usr/bin/env python3
"""verify-tokens.py - Calibrate tiktoken proxy counts against Anthropic's count_tokens.

Usage:
  python -I verify-tokens.py [--api-key KEY] [--model MODEL] [FILE ...]
  python -I verify-tokens.py --list-models

Requires Anthropic API key (via --api-key or ANTHROPIC_API_KEY env var).
If no files given, uses keyline test fixtures.
"""
import argparse
import json
import os
import sys
from pathlib import Path

try:
    import anthropic
except ImportError:
    anthropic = None

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "keyline" / "tests"

DEFAULT_FIXTURES = [
    "incident.prose.md",
    "incident.keyline.txt",
    "incident.keyline.he.txt",
    "incident.prose.he.txt",
    "incident.glyph.txt",
    "notes.markdown.md",
    "notes.keyline.txt",
    "notes.keyline.he.txt",
]

PANEL_COUNTS = {
    "incident.prose.md": (301, 302),
    "incident.keyline.txt": (204, 206),
    "incident.keyline.he.txt": (308, 594),
    "incident.prose.he.txt": (375, 742),
    "incident.glyph.txt": (182, 180),
    "notes.markdown.md": (104, 106),
    "notes.keyline.txt": (66, 68),
    "notes.keyline.he.txt": (89, 162),
}


def count_tiktoken(text: str) -> tuple[int, int]:
    """Return (o200k_base, cl100k_base) token counts."""
    import tiktoken
    o200k = tiktoken.get_encoding("o200k_base")
    cl100k = tiktoken.get_encoding("cl100k_base")
    return len(o200k.encode(text, disallowed_special=())), len(cl100k.encode(text, disallowed_special=()))


def count_anthropic(client, text: str, model: str) -> int:
    """Call Anthropic's count_tokens endpoint."""
    # The count_tokens endpoint expects messages format
    response = client.messages.count_tokens(
        model=model,
        messages=[{"role": "user", "content": text}]
    )
    return response.input_tokens


def list_models(client) -> None:
    """List available models (for reference)."""
    # Anthropic doesn't have a list-models endpoint; these are known models
    known = [
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
        "claude-3-sonnet-20240229",
        "claude-3-haiku-20240307",
    ]
    for m in known:
        print(m)


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip())
    parser.add_argument("--api-key", default=os.environ.get("ANTHROPIC_API_KEY"),
                        help="Anthropic API key (or set ANTHROPIC_API_KEY env var)")
    parser.add_argument("--model", default="claude-3-5-sonnet-20241022",
                        help="Model to use for count_tokens (default: claude-3-5-sonnet-20241022)")
    parser.add_argument("--list-models", action="store_true",
                        help="List known models and exit")
    parser.add_argument("files", nargs="*", help="Files to analyze (default: keyline test fixtures)")
    args = parser.parse_args()

    if args.list_models:
        if not anthropic:
            print("anthropic package not installed", file=sys.stderr)
            sys.exit(1)
        client = anthropic.Anthropic(api_key=args.api_key or "dummy")
        list_models(client)
        return

    if not anthropic:
        print("Error: anthropic package not installed. Install with: pip install anthropic", file=sys.stderr)
        sys.exit(1)

    if not args.api_key:
        print("Error: Anthropic API key required (--api-key or ANTHROPIC_API_KEY env var)", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=args.api_key)

    files = args.files if args.files else [FIXTURES / f for f in DEFAULT_FIXTURES]

    print(f"{'file':30} {'o200k':>7} {'cl100k':>7} {'anthropic':>10} {'o200k ratio':>11} {'cl100k ratio':>11}")
    print("-" * 85)

    ratios_o200k = []
    ratios_cl100k = []

    for f in files:
        path = Path(f)
        if not path.exists():
            print(f"Warning: {path} not found, skipping", file=sys.stderr)
            continue

        text = path.read_text(encoding="utf-8-sig")
        o200k, cl100k = count_tiktoken(text)

        try:
            anth = count_anthropic(client, text, args.model)
        except Exception as e:
            print(f"Error counting {path.name}: {e}", file=sys.stderr)
            anth = None

        if anth:
            ratio_o = o200k / anth
            ratio_c = cl100k / anth
            ratios_o200k.append(ratio_o)
            ratios_cl100k.append(ratio_c)
            print(f"{path.name:30} {o200k:>7} {cl100k:>7} {anth:>10} {ratio_o:>10.2f}x {ratio_c:>10.2f}x")
        else:
            print(f"{path.name:30} {o200k:>7} {cl100k:>7} {'ERROR':>10}")

    if ratios_o200k:
        avg_o = sum(ratios_o200k) / len(ratios_o200k)
        avg_c = sum(ratios_cl100k) / len(ratios_cl100k)
        print("-" * 85)
        print(f"{'AVERAGE':30} {'':>7} {'':>7} {'':>10} {avg_o:>10.2f}x {avg_c:>10.2f}x")
        print(f"\nInterpretation: tiktoken o200k_base is ~{avg_o:.0%} of Claude tokens")
        print(f"                tiktoken cl100k_base is ~{avg_c:.0%} of Claude tokens")
        print(f"\nSo multiply o200k counts by ~{1/avg_o:.2f} to estimate Claude tokens.")
        print(f"   Multiply cl100k counts by ~{1/avg_c:.2f} to estimate Claude tokens.")


if __name__ == "__main__":
    main()