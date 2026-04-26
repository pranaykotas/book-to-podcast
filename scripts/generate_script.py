#!/usr/bin/env python3
"""Generate a podcast script from book.txt using an LLM API.

Usage:
  generate_script.py <out_dir> --format monologue|conversation
                     [--provider anthropic|openai|ollama]
                     [--model MODEL]
                     [--pause-after-script]

Reads prompts from ../prompts/. Writes <out_dir>/script.md.
LLM provider is configured via .env:
  - Anthropic: ANTHROPIC_API_KEY
  - OpenAI:    OPENAI_API_KEY
  - Ollama:    OLLAMA_URL (default http://localhost:11434)
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

SKILL_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(SKILL_ROOT / ".env")

PROMPTS = SKILL_ROOT / "prompts"

# Token limits: most non-fiction books fit in 200k context.
# Two-pass fallback (summarise-per-chapter) is the caller's responsibility
# for very long books; this script just sends the text as-is.
MAX_BOOK_CHARS = 800_000  # ~200k tokens; warn above this


def load_prompt(fmt: str) -> str:
    fname = "script-monologue.md" if fmt == "monologue" else "script-empire.md"
    path = PROMPTS / fname
    if not path.exists():
        sys.exit(f"prompt file not found: {path}")
    return path.read_text()


def build_messages(book_text: str, prompt_template: str, fmt: str) -> list[dict]:
    system = (
        "You are an expert podcast scriptwriter. "
        "Follow the template instructions exactly, including the formatting rules and anti-AI-tells pass. "
        "Output only the script — no preamble, no explanation."
    )
    user = (
        f"{prompt_template}\n\n"
        f"---\n\n"
        f"Here is the full book text to turn into a {fmt} podcast script:\n\n"
        f"{book_text}"
    )
    return [{"role": "user", "content": user}], system


def call_anthropic(messages: list[dict], system: str, model: str) -> str:
    try:
        import anthropic
    except ImportError:
        sys.exit("anthropic package not installed: pip install anthropic")
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model=model or "claude-opus-4-7",
        max_tokens=8192,
        system=system,
        messages=messages,
    )
    return resp.content[0].text


def call_openai(messages: list[dict], system: str, model: str) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        sys.exit("openai package not installed: pip install openai")
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    full = [{"role": "system", "content": system}] + messages
    resp = client.chat.completions.create(
        model=model or "gpt-4o",
        messages=full,
        max_tokens=8192,
    )
    return resp.choices[0].message.content


def call_ollama(messages: list[dict], system: str, model: str) -> str:
    try:
        import httpx
    except ImportError:
        sys.exit("httpx package not installed: pip install httpx")
    base = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
    full = [{"role": "system", "content": system}] + messages
    resp = httpx.post(
        f"{base}/api/chat",
        json={"model": model or "llama3.1:70b", "messages": full, "stream": False},
        timeout=600,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("out_dir", help="directory containing book.txt; script.md written here")
    p.add_argument("--format", choices=["monologue", "conversation"], default="monologue")
    p.add_argument("--provider", choices=["anthropic", "openai", "ollama"],
                   default=os.environ.get("LLM_PROVIDER", "anthropic"))
    p.add_argument("--model", default=os.environ.get("LLM_MODEL", ""))
    p.add_argument("--pause-after-script", action="store_true",
                   help="pause after writing script.md so you can review before TTS")
    args = p.parse_args()

    out = Path(args.out_dir).expanduser().resolve()
    book_txt = out / "book.txt"
    script_md = out / "script.md"

    if not book_txt.exists():
        sys.exit(f"book.txt not found in {out} — run extract.py first")

    book_text = book_txt.read_text()
    if len(book_text) > MAX_BOOK_CHARS:
        print(
            f"warning: book is {len(book_text)/1000:.0f}k chars "
            f"(>{MAX_BOOK_CHARS/1000:.0f}k). Consider two-pass summarisation.",
            file=sys.stderr,
        )

    prompt_template = load_prompt(args.format)
    messages, system = build_messages(book_text, prompt_template, args.format)

    print(f"generating {args.format} script via {args.provider}...", file=sys.stderr, flush=True)

    if args.provider == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            sys.exit("ANTHROPIC_API_KEY not set in .env")
        script = call_anthropic(messages, system, args.model)
    elif args.provider == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            sys.exit("OPENAI_API_KEY not set in .env")
        script = call_openai(messages, system, args.model)
    elif args.provider == "ollama":
        script = call_ollama(messages, system, args.model)
    else:
        sys.exit(f"unknown provider: {args.provider}")

    script_md.write_text(script)
    word_count = len(script.split())
    print(f"script written: {script_md} ({word_count:,} words)", file=sys.stderr)

    if args.pause_after_script:
        input("\nReview script.md, then press Enter to continue to TTS... ")

    return 0


if __name__ == "__main__":
    sys.exit(main())
