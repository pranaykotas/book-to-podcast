#!/usr/bin/env python3
"""Standalone pipeline: epub/pdf → script → MP3 → R2 feed.

Usage:
  python run.py ~/Downloads/some-book.epub [options]

Options:
  --format      monologue | conversation  (default: env DEFAULT_FORMAT or monologue)
  --tts         sarvam | elevenlabs       (default: env TTS_PROVIDER or sarvam)
  --llm         anthropic | openai | ollama  (default: env LLM_PROVIDER or anthropic)
  --llm-model   model name override
  --pause       pause after script generation for review before TTS
  --skip-tts    stop after script (no audio rendered)
  --skip-publish  render audio but don't upload to R2

Does NOT require Claude Code. Bring your own LLM API key.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

from dotenv import load_dotenv

SKILL_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(SKILL_ROOT / ".env")

SCRIPTS = SKILL_ROOT / "scripts"


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[-\s]+", "-", value)[:48] or "episode"


def run(cmd: list[str], **kwargs) -> None:
    result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        sys.exit(result.returncode)


def main() -> int:
    p = argparse.ArgumentParser(description="book-to-podcast standalone pipeline")
    p.add_argument("input", help="path to .epub or .pdf")
    p.add_argument("--format", choices=["monologue", "conversation"],
                   default=os.environ.get("DEFAULT_FORMAT", "monologue"))
    p.add_argument("--tts", choices=["sarvam", "elevenlabs", "kokoro"],
                   default=os.environ.get("TTS_PROVIDER", "sarvam"))
    p.add_argument("--llm", choices=["anthropic", "openai", "ollama"],
                   default=os.environ.get("LLM_PROVIDER", "anthropic"))
    p.add_argument("--llm-model", default=os.environ.get("LLM_MODEL", ""))
    p.add_argument("--pause", action="store_true", help="pause after script for review")
    p.add_argument("--skip-tts", action="store_true")
    p.add_argument("--skip-publish", action="store_true")
    args = p.parse_args()

    src = Path(args.input).expanduser().resolve()
    if not src.exists():
        sys.exit(f"file not found: {src}")
    if src.suffix.lower() not in (".epub", ".pdf"):
        sys.exit(f"unsupported format: {src.suffix} — need .epub or .pdf")

    work_dir = Path(os.environ.get("WORK_DIR", "~/book-podcasts/out")).expanduser().resolve()

    # ── Step 1: extract ──────────────────────────────────────────────────────
    print(f"\n[1/5] extracting {src.name}...", flush=True)
    tmp_dir = work_dir / "_extract_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "extract.py"), str(src), str(tmp_dir)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    meta = json.loads(result.stdout)
    title = meta.get("title", src.stem)
    author = meta.get("author", "Unknown")
    word_count = meta.get("word_count", 0)
    print(f"    title:  {title}")
    print(f"    author: {author}")
    print(f"    words:  {word_count:,}")

    if word_count < 30_000:
        print("warning: book is under 30k words — pipeline tuned for longer non-fiction", file=sys.stderr)

    slug = slugify(title)
    out = work_dir / slug
    out.mkdir(parents=True, exist_ok=True)

    # move book.txt from tmp to final dir
    book_txt = tmp_dir / "book.txt"
    (out / "book.txt").write_text(book_txt.read_text())

    # ── Step 2: generate script ───────────────────────────────────────────────
    script_md = out / "script.md"
    print(f"\n[2/5] generating {args.format} script via {args.llm}...", flush=True)
    gen_cmd = [
        sys.executable, str(SCRIPTS / "generate_script.py"),
        str(out),
        "--format", args.format,
        "--provider", args.llm,
    ]
    if args.llm_model:
        gen_cmd += ["--model", args.llm_model]
    if args.pause:
        gen_cmd.append("--pause-after-script")
    run(gen_cmd)

    if args.skip_tts:
        print(f"\nscript at: {script_md}")
        print("(--skip-tts set, stopping here)")
        return 0

    # ── Step 3: chunk ─────────────────────────────────────────────────────────
    chunks_json = out / "chunks.json"
    # Sarvam has a tight per-call char limit; ElevenLabs and Kokoro handle larger chunks.
    max_chars = "500" if args.tts == "sarvam" else "4500"
    print(f"\n[3/5] chunking for {args.tts} (--max-chars {max_chars})...", flush=True)
    run([sys.executable, str(SCRIPTS / "chunk.py"), str(script_md), "--max-chars", max_chars])

    # ── Step 4: TTS ───────────────────────────────────────────────────────────
    episode_mp3 = out / "episode.mp3"
    print(f"\n[4/5] rendering audio via {args.tts}...", flush=True)
    run([
        sys.executable, str(SCRIPTS / "tts.py"),
        str(chunks_json), str(episode_mp3),
        "--provider", args.tts,
    ])

    if args.skip_publish:
        print(f"\nepisode at: {episode_mp3}")
        print("(--skip-publish set, stopping here)")
        return 0

    # ── Step 5: publish ───────────────────────────────────────────────────────
    summary = f"{title} by {author}. A {args.format} podcast episode."
    print(f"\n[5/5] publishing to R2...", flush=True)
    run([
        sys.executable, str(SCRIPTS / "publish.py"),
        str(episode_mp3),
        "--title", title,
        "--author", author,
        "--summary", summary,
    ])

    return 0


if __name__ == "__main__":
    sys.exit(main())
