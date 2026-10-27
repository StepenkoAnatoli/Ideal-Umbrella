#!/usr/bin/env python3
"""verify-tokens.py - Calibrate tiktoken proxy counts against Anthropic's count_tokens.

Usage:
  python -I config/verify-tokens.py --model MODEL [--api-key KEY] [FILE ...]
  python -I config/verify-tokens.py --list-models

The count_tokens endpoint is model-specific, so MODEL is required (or set
ANTHROPIC_MODEL); no retired model id is baked in. If no files are given, the
keyline test fixtures are used. Requires the `anthropic` package and an API key
(via --api-key or ANTHROPIC_API_KEY).
"""
import argparse
import os
import sys
from pathlib import Path

try:
    import anthropic
except ImportError:
    anthropic = None

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent / "keyline" / "tests"

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


def count_tiktoken(text: str) -> tuple[int, int]:
    """Return (o200k_base, cl100k_base) token counts."""
    try:
        import tiktoken
    except ImportError:
        raise ImportError("tiktoken is not installed; run: pip install tiktoken") from None
    o200k = tiktoken.get_encoding("o200k_base")
    cl100k = tiktoken.get_encoding("cl100k_base")
    return (
        len(o200k.encode(text, disallowed_special=())),
        len(cl100k.encode(text, disallowed_special=())),
    )


def count_anthropic(client, text: str, model: str) -> int:
    """Call Anthropic's count_tokens endpoint."""
    response = client.messages.count_tokens(
        model=model,
        messages=[{"role": "user", "content": text}],
    )
    return response.input_tokens


def list_models(client) -> None:
    """List models the API reports, rather than a stale hard-coded list."""
    for model in client.models.list():
        print(model.id)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.strip())
    parser.add_argument("--api-key", default=os.environ.get("ANTHROPIC_API_KEY"),
                        help="Anthropic API key (or set ANTHROPIC_API_KEY)")
    parser.add_argument("--model", default=os.environ.get("ANTHROPIC_MODEL"),
                        help="model id for count_tokens (or set ANTHROPIC_MODEL)")
    parser.add_argument("--list-models", action="store_true",
                        help="list models reported by the API and exit")
    parser.add_argument("files", nargs="*", help="files to analyze (default: keyline test fixtures)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")   # -I ignores PYTHONUTF8: set UTF-8 output here

    if not anthropic:
        print("Error: anthropic package not installed. Install with: pip install anthropic", file=sys.stderr)
        return 1
    if not args.api_key:
        print("Error: Anthropic API key required (--api-key or ANTHROPIC_API_KEY)", file=sys.stderr)
        return 1

    client = anthropic.Anthropic(api_key=args.api_key)

    if args.list_models:
        try:
            list_models(client)
        except Exception as e:
            print(f"Error listing models: {e}", file=sys.stderr)
            return 1
        return 0

    if not args.model:
        print(
            "Error: --model (or ANTHROPIC_MODEL) is required; count_tokens is model-specific "
            "and model ids change.",
            file=sys.stderr,
        )
        return 1

    files = [Path(f) for f in args.files] if args.files else [FIXTURES / f for f in DEFAULT_FIXTURES]

    print(f"{'file':30} {'o200k':>7} {'cl100k':>7} {'anthropic':>10} {'o200k ratio':>11} {'cl100k ratio':>11}")
    print("-" * 85)

    ratios_o200k = []
    ratios_cl100k = []

    for path in files:
        if not path.exists():
            print(f"Warning: {path} not found, skipping", file=sys.stderr)
            continue

        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as e:
            print(f"Error reading {path}: {e}", file=sys.stderr)
            continue
        try:
            o200k, cl100k = count_tiktoken(text)
        except ImportError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        except Exception as e:
            # tiktoken itself failed (its encoding download, most often): the same for every
            # file, so say it once and stop.
            print(f"Error: tiktoken failed on {path.name}: {e}", file=sys.stderr)
            return 1

        try:
            anth = count_anthropic(client, text, args.model)
        except Exception as e:
            print(f"Error counting {path.name}: {e}", file=sys.stderr)
            anth = None

        if anth is not None:
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
        return 0
    print("Error: no file was counted by the API; see the errors above", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
