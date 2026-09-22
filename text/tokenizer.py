#!/usr/bin/env python3
"""Estimate token counts for a file or provided text using optional tiktoken."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from shared.config import ToolConfig


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def read_stdin() -> str:
    return sys.stdin.read()


def fallback_count(text: str, ascii_chars_per_token: int, non_ascii_chars_per_token: int) -> tuple[int, int, int]:
    ascii_count = sum(1 for ch in text if ord(ch) < 128)
    non_ascii_count = len(text) - ascii_count
    if len(text) == 0:
        return 0, 0, 0

    min_tokens = math.ceil(ascii_count / ascii_chars_per_token + non_ascii_count / non_ascii_chars_per_token)
    max_tokens = max(min_tokens, math.ceil(ascii_count / max(1, ascii_chars_per_token - 1) + non_ascii_count))
    mid_tokens = math.ceil((min_tokens + max_tokens) / 2)
    return min_tokens, max_tokens, mid_tokens


def tokenize_with_tiktoken(text: str, encoding_name: str) -> int:
    import tiktoken

    encoding = tiktoken.get_encoding(encoding_name)
    return len(encoding.encode(text))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Input text file")
    parser.add_argument("--text", help="Inline text to estimate")
    parser.add_argument("--encoding", help="tiktoken encoding name")
    parser.add_argument("--env-file", type=Path, help="Optional TOOL_* env file path")
    parser.add_argument("--ascii-chars-per-token", type=float, dest="ascii_ratio", help="ASCII fallback chars per token")
    parser.add_argument("--non-ascii-chars-per-token", type=float, dest="non_ascii_ratio",
                        help="Non-ASCII fallback chars per token")
    parser.add_argument("--json", action="store_true", help="Output JSON payload")

    args = parser.parse_args(argv)

    cfg = ToolConfig(args.env_file)
    encoding = cfg.value("TOOL_TOKENIZER_ENCODING", "cl100k_base")
    ascii_ratio = cfg.positive_float("TOOL_TOKENIZER_ASCII_CHARS_PER_TOKEN", 4)
    non_ascii_ratio = cfg.positive_float("TOOL_TOKENIZER_NONASCII_CHARS_PER_TOKEN", 2)
    cfg.emit_warnings()

    if args.encoding is not None:
        encoding = args.encoding
    if args.ascii_ratio is not None:
        ascii_ratio = args.ascii_ratio
    if args.non_ascii_ratio is not None:
        non_ascii_ratio = args.non_ascii_ratio

    if any(not math.isfinite(value) or value <= 0 for value in (ascii_ratio, non_ascii_ratio)):
        print("error: fallback character ratios must be finite and greater than 0", file=sys.stderr)
        return 2

    if args.input is not None and args.text is not None:
        print("error: --input and --text cannot be used together", file=sys.stderr)
        return 2

    source = "stdin"
    if args.input is not None:
        if not args.input.is_file():
            print(f"error: input file not found: {args.input}", file=sys.stderr)
            return 2
        source = str(args.input)
        try:
            text = read_text(args.input)
        except (OSError, UnicodeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    elif args.text is not None:
        source = "inline"
        text = args.text
    else:
        if sys.stdin.isatty():
            print("error: provide --input/--text or pipe text via stdin", file=sys.stderr)
            return 2
        text = read_stdin()

    result = {
        "source": source,
        "encoding": encoding,
        "chars": len(text),
        "words": len(text.split()),
    }

    try:
        tokens = tokenize_with_tiktoken(text, encoding)
        result.update({"method": "tiktoken", "tokens": tokens, "min_tokens": tokens, "max_tokens": tokens})
    except Exception:
        result["method"] = "fallback"
        min_tokens, max_tokens, mid_tokens = fallback_count(text, max(1, int(math.ceil(ascii_ratio))),
                                                            max(1, int(math.ceil(non_ascii_ratio))))
        result.update({"min_tokens": min_tokens, "max_tokens": max_tokens, "mid_tokens": mid_tokens})

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["method"] == "tiktoken":
            print(f"source: {result['source']}")
            print(f"method: {result['method']}")
            print(f"encoding: {result['encoding']}")
            print(f"chars: {result['chars']}")
            print(f"words: {result['words']}")
            print(f"tokens: {result['tokens']}")
        else:
            print(f"source: {result['source']}")
            print(f"method: {result['method']} (encoding={result['encoding']})")
            print(f"chars: {result['chars']}")
            print(f"words: {result['words']}")
            print(f"token_min: {result['min_tokens']}")
            print(f"token_mid: {result['mid_tokens']}")
            print(f"token_max: {result['max_tokens']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
