#!/usr/bin/env python3
"""Extract plain text + metadata from epub or pdf.

Usage: extract.py <input.epub|input.pdf> <output_dir>

Writes <output_dir>/book.txt with chapter markers like:

    @@CHAPTER@@ Chapter 3: Title

Prints metadata JSON to stdout.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def extract_epub(path: Path) -> tuple[dict, str]:
    from ebooklib import epub, ITEM_DOCUMENT
    from bs4 import BeautifulSoup

    book = epub.read_epub(str(path))
    title = (book.get_metadata("DC", "title") or [("Unknown",)])[0][0]
    creator = (book.get_metadata("DC", "creator") or [("Unknown",)])[0][0]

    parts: list[str] = []
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        heading = soup.find(["h1", "h2"])
        if heading:
            parts.append(f"@@CHAPTER@@ {heading.get_text(strip=True)}")
        text = soup.get_text("\n", strip=True)
        if text:
            parts.append(text)

    full = "\n\n".join(parts)
    return {"title": title, "author": creator, "format": "epub"}, full


def extract_pdf(path: Path) -> tuple[dict, str]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    info = reader.metadata or {}
    title = info.get("/Title") or path.stem
    author = info.get("/Author") or "Unknown"

    pages = []
    for i, page in enumerate(reader.pages):
        try:
            txt = page.extract_text() or ""
        except Exception:
            txt = ""
        pages.append(txt)
    full = "\n\n".join(pages)
    full = guess_chapters_from_text(full)
    return {"title": str(title), "author": str(author), "format": "pdf"}, full


CHAPTER_PATTERNS = [
    re.compile(r"^\s*Chapter\s+\d+[\.:]?\s*(.*)$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*CHAPTER\s+[IVXLCM]+[\.:]?\s*(.*)$", re.MULTILINE),
]


def guess_chapters_from_text(text: str) -> str:
    for pat in CHAPTER_PATTERNS:
        if len(pat.findall(text)) >= 3:
            return pat.sub(lambda m: f"@@CHAPTER@@ {m.group(0).strip()}", text)
    return text


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: extract.py <input> <output_dir>", file=sys.stderr)
        return 2

    src = Path(sys.argv[1]).expanduser().resolve()
    out_dir = Path(sys.argv[2]).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if src.suffix.lower() == ".epub":
        meta, text = extract_epub(src)
    elif src.suffix.lower() == ".pdf":
        meta, text = extract_pdf(src)
    else:
        print(f"unsupported format: {src.suffix}", file=sys.stderr)
        return 2

    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    word_count = len(text.split())
    chapter_count = text.count("@@CHAPTER@@")

    book_path = out_dir / "book.txt"
    book_path.write_text(text, encoding="utf-8")

    meta.update(
        word_count=word_count,
        chapter_count=chapter_count,
        source_path=str(src),
        book_text_path=str(book_path),
    )
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
