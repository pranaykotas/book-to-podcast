#!/usr/bin/env python3
"""Split a script into TTS-ready chunks.

Input: script.md with lines like:
    [Host A]: text...      (two-host conversation mode)
    [Host B]: text...
or
    [Narrator]: text...    (monologue mode)

Output: chunks.json — list of {speaker: "A"|"B"|"N", text: str, index: int}.

Each chunk's text stays under max_chars. Chunks split on speaker turn first,
then on sentence boundaries within a turn if a single turn is too long.

Usage: chunk.py <script.md> [--max-chars N]
  Default max_chars = 4500 (ElevenLabs). Use 500 for Sarvam.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SPEAKER_RE = re.compile(r"^\[(?:Host\s+(A|B)|(Narrator))\]:\s*(.*)$", re.IGNORECASE)


def parse_turns(text: str) -> list[tuple[str, str]]:
    turns: list[tuple[str, str]] = []
    current_speaker: str | None = None
    buffer: list[str] = []

    for raw in text.splitlines():
        line = raw.rstrip()
        m = SPEAKER_RE.match(line)
        if m:
            if current_speaker is not None and buffer:
                turns.append((current_speaker, " ".join(buffer).strip()))
            host_letter = m.group(1)
            narrator = m.group(2)
            body = m.group(3)
            if narrator:
                current_speaker = "N"
            else:
                current_speaker = host_letter.upper()
            buffer = [body] if body else []
        elif line.strip() == "":
            continue
        else:
            if current_speaker is None:
                continue
            buffer.append(line.strip())

    if current_speaker is not None and buffer:
        turns.append((current_speaker, " ".join(buffer).strip()))

    return [(s, t) for s, t in turns if t]


# Handles English (. ? !) and Devanagari danda (।) sentence endings.
# Lookahead covers ASCII uppercase, Devanagari, Tamil, Telugu, Kannada script starts.
SENT_SPLIT = re.compile(
    r"(?<=[\.\?\!।])\s+"
    r"(?=[A-Zऀ-ॿ஀-௿ఀ-౿ಀ-೿\"\'<])"
)


def split_long_turn(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    sentences = SENT_SPLIT.split(text)
    out: list[str] = []
    cur = ""
    for s in sentences:
        if len(cur) + len(s) + 1 <= max_chars:
            cur = (cur + " " + s).strip() if cur else s
        else:
            if cur:
                out.append(cur)
            if len(s) <= max_chars:
                cur = s
            else:
                # Hard split inside an over-long sentence at a comma or space.
                while len(s) > max_chars:
                    cut = s.rfind(",", 0, max_chars)
                    if cut < max_chars // 2:
                        cut = s.rfind(" ", 0, max_chars)
                    if cut < 0:
                        cut = max_chars
                    out.append(s[:cut].strip())
                    s = s[cut:].strip()
                cur = s
    if cur:
        out.append(cur)
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("script")
    p.add_argument("--max-chars", type=int, default=4500,
                   help="max chars per chunk (default 4500 for ElevenLabs; use 500 for Sarvam)")
    args = p.parse_args()

    script_path = Path(args.script).expanduser().resolve()
    text = script_path.read_text(encoding="utf-8")

    turns = parse_turns(text)
    if not turns:
        print("no [Host A/B] or [Narrator] turns parsed from script", file=sys.stderr)
        return 1

    chunks: list[dict] = []
    for speaker, body in turns:
        for piece in split_long_turn(body, args.max_chars):
            chunks.append({"index": len(chunks), "speaker": speaker, "text": piece})

    out_path = script_path.parent / "chunks.json"
    out_path.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")

    total_chars = sum(len(c["text"]) for c in chunks)
    print(json.dumps({
        "chunks": len(chunks),
        "turns": len(turns),
        "total_chars": total_chars,
        "max_chunk_chars": max(len(c["text"]) for c in chunks),
        "out": str(out_path),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
