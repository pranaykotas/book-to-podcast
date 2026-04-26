#!/usr/bin/env python3
"""Upload MP3 to Cloudflare R2 and update feed.xml on R2.

Usage:
  publish.py <episode.mp3> --title "Book Title" --author "Book Author" \
             --summary "two-line blurb"

Reads R2 credentials from ~/.claude/skills/book-to-podcast/.env.
The feed.xml itself lives on R2, so the entire podcast leaves no trace
on any public-facing GitHub repo.
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from feedgen.feed import FeedGenerator

SKILL_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(SKILL_ROOT / ".env")

FEED_KEY = "feed.xml"


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[-\s]+", "-", value)[:64] or "episode"


def r2_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def fetch_existing_feed(client, bucket: str) -> list[dict]:
    """Pull current feed.xml from R2 and parse out existing items."""
    try:
        resp = client.get_object(Bucket=bucket, Key=FEED_KEY)
        body = resp["Body"].read()
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return []
        raise
    items = []
    try:
        root = ET.fromstring(body)
        channel = root.find("channel")
        for item in channel.findall("item") if channel is not None else []:
            enclosure = item.find("enclosure")
            items.append({
                "title": (item.findtext("title") or "").strip(),
                "description": (item.findtext("description") or "").strip(),
                "guid": (item.findtext("guid") or "").strip(),
                "pubDate": (item.findtext("pubDate") or "").strip(),
                "enclosure_url": enclosure.get("url") if enclosure is not None else "",
                "enclosure_length": enclosure.get("length") if enclosure is not None else "0",
            })
    except ET.ParseError as e:
        print(f"warning: existing feed.xml unparseable ({e}); starting fresh", file=sys.stderr)
    return items


def build_feed(public_base: str, items: list[dict]) -> bytes:
    owner_name = os.environ.get("FEED_OWNER_NAME", "My Book Podcast")
    owner_email = os.environ.get("FEED_OWNER_EMAIL", "")
    feed_title = os.environ.get("FEED_TITLE", f"{owner_name}'s Book Podcast")
    feed_desc = os.environ.get("FEED_DESCRIPTION", "Private feed: 45-minute book conversations and monologues for commute listening.")

    fg = FeedGenerator()
    fg.load_extension("podcast")
    fg.title(feed_title)
    fg.link(href=f"{public_base}/{FEED_KEY}", rel="self")
    fg.link(href=public_base, rel="alternate")
    fg.description(feed_desc)
    fg.language("en")
    fg.author({"name": owner_name, "email": owner_email})
    fg.podcast.itunes_category("Society & Culture", "Documentary")
    fg.podcast.itunes_explicit("no")
    fg.podcast.itunes_author(owner_name)
    fg.podcast.itunes_owner(name=owner_name, email=owner_email)
    fg.podcast.itunes_block(True)  # tell directories not to index this feed

    for it in items:
        fe = fg.add_entry()
        fe.id(it["guid"] or it["enclosure_url"])
        fe.title(it["title"])
        fe.description(it["description"] or it["title"])
        if it["enclosure_url"]:
            fe.enclosure(it["enclosure_url"], it["enclosure_length"], "audio/mpeg")
        if it["pubDate"]:
            try:
                fe.pubDate(parsedate_to_datetime(it["pubDate"]))
            except Exception:
                pass

    return fg.rss_str(pretty=True)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("mp3")
    p.add_argument("--title", required=True)
    p.add_argument("--author", required=True)
    p.add_argument("--summary", required=True)
    args = p.parse_args()

    bucket = os.environ.get("R2_BUCKET")
    public_base = os.environ.get("R2_PUBLIC_BASE")
    if not (bucket and public_base and os.environ.get("R2_ACCESS_KEY_ID")):
        print("missing env: R2_BUCKET / R2_PUBLIC_BASE / R2_ACCESS_KEY_ID", file=sys.stderr)
        return 2

    src_mp3 = Path(args.mp3).expanduser().resolve()
    if not src_mp3.exists():
        print(f"missing mp3: {src_mp3}", file=sys.stderr)
        return 2

    now = datetime.now(timezone.utc)
    slug = f"{now:%Y%m%d}-{slugify(args.title)}"
    mp3_key = f"{slug}.mp3"
    public_url = f"{public_base.rstrip('/')}/{mp3_key}"
    size_bytes = src_mp3.stat().st_size

    client = r2_client()

    # Upload MP3.
    print(f"uploading {src_mp3.name} ({size_bytes/1024/1024:.1f} MB) to R2...", file=sys.stderr, flush=True)
    client.upload_file(
        str(src_mp3), bucket, mp3_key,
        ExtraArgs={"ContentType": "audio/mpeg"},
    )

    # Pull existing feed, append new item, push back.
    items = fetch_existing_feed(client, bucket)
    items.append({
        "title": f"{args.title} — {args.author}",
        "description": args.summary,
        "guid": public_url,
        "pubDate": now.strftime("%a, %d %b %Y %H:%M:%S +0000"),
        "enclosure_url": public_url,
        "enclosure_length": str(size_bytes),
    })
    feed_bytes = build_feed(public_base.rstrip("/"), items)
    client.put_object(
        Bucket=bucket, Key=FEED_KEY,
        Body=feed_bytes,
        ContentType="application/rss+xml",
    )

    feed_url = f"{public_base.rstrip('/')}/{FEED_KEY}"
    print(f"Episode published: {public_url}")
    print(f"Subscribe URL:     {feed_url}")
    print(f"Size:              {size_bytes/1024/1024:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
