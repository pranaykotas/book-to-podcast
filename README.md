# book-to-podcast

Turn a non-fiction epub or pdf into a 35–45 minute podcast episode and publish it to a private RSS feed you can subscribe to from any podcast app.

Two formats: **two-host conversation** (Empire-style co-hosts) or **single-narrator monologue**.  
Three TTS providers: **ElevenLabs** (premium, ~$0.30/1k chars), **Sarvam** (Indian voices, ~10x cheaper), or **Kokoro** (fully local, zero cost, no API key).

This is a [Claude Code skill](https://docs.anthropic.com/en/docs/claude-code/skills) — it runs inside Claude Code sessions. Claude generates the script itself from the book, then shells out to Python scripts for TTS and publishing.

---

## Quick start

In any Claude Code session:

```
/book-to-podcast ~/Downloads/some-book.epub
```

Claude will extract the book, generate a ~45-minute script, render MP3 via your configured TTS provider, upload to Cloudflare R2, and print your subscribe URL.

---

## One-time setup

### 1. Python deps

Core deps (always needed):

```sh
python3 -m pip install --user --break-system-packages \
  ebooklib pypdf beautifulsoup4 pydub feedgen python-dotenv \
  boto3 audioop-lts httpx
```

Provider-specific (install only what you use):

```sh
# ElevenLabs
pip install elevenlabs

# Sarvam — no extra package, uses httpx (already above)

# Kokoro (local, free, no API key)
pip install kokoro soundfile
# First run downloads the model (~300 MB, cached in ~/.cache/huggingface/)
```

`audioop-lts` is required on Python 3.13+ (stdlib `audioop` was removed).

### 2. ffmpeg

```sh
brew install ffmpeg   # macOS
# or: sudo apt install ffmpeg
```

### 3. Cloudflare R2 bucket

Create a free R2 bucket at [dash.cloudflare.com](https://dash.cloudflare.com), enable public access, note the public `r2.dev` subdomain. Generate an API token with Object Read & Write on that bucket.

### 4. `.env` file

Copy `config.example.env` to `.env` in this directory and fill in:

```
TTS_PROVIDER=sarvam          # or elevenlabs
DEFAULT_FORMAT=monologue     # or conversation

ELEVENLABS_API_KEY=...
HOST_A_VOICE_ID=...
HOST_B_VOICE_ID=...
ELEVENLABS_MODEL=eleven_multilingual_v2

SARVAM_API_KEY=...
SARVAM_HOST_A_SPEAKER=anushka
SARVAM_HOST_B_SPEAKER=abhilash
SARVAM_NARRATOR_SPEAKER=arya
SARVAM_MODEL=bulbul:v2
SARVAM_LANGUAGE=en-IN

FEED_OWNER_NAME=Your Name
FEED_OWNER_EMAIL=you@example.com
FEED_TITLE=My Book Podcast          # optional, defaults to "<FEED_OWNER_NAME>'s Book Podcast"
FEED_DESCRIPTION=...                # optional

R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_ENDPOINT=https://<account>.r2.cloudflarestorage.com
R2_BUCKET=podcast
R2_PUBLIC_BASE=https://pub-<random>.r2.dev

WORK_DIR=~/book-podcasts/out        # where intermediate artifacts go
```

### 5. Register the skill in Claude Code

Copy this directory into your Claude Code skills folder:

```sh
cp -r . ~/.claude/skills/book-to-podcast/
```

Claude Code auto-loads skills from `~/.claude/skills/`. No further config needed.

### 6. Subscribe

After the first episode, copy the subscribe URL printed by Claude and add it once in any podcast app (Pocket Casts, AntennaPod, Apple Podcasts → "Add by URL").

---

## File layout

```
~/.claude/skills/book-to-podcast/
  SKILL.md                          # read by Claude when the skill triggers
  README.md                         # this file
  config.example.env
  prompts/
    script-empire.md                # two-host conversation template
    script-monologue.md             # single narrator template
  scripts/
    extract.py                      # epub/pdf → text + chapter markers
    chunk.py                        # script → TTS-ready chunks
    tts.py                          # chunks → MP3 (ElevenLabs or Sarvam)
    publish.py                      # MP3 → Cloudflare R2 + feed.xml

$WORK_DIR/<book-slug>/
  book.txt                          # extracted text
  script.md                         # generated podcast script
  chunks.json                       # TTS-ready chunks
  episode.mp3                       # final stitched audio
  .audio_cache_elevenlabs/          # per-chunk cache (resumable)
  .audio_cache_sarvam/              # per-chunk cache (resumable)
```

The cache directories let you safely retry a failed render without spending credits twice.

---

## Manual usage (without Claude)

```sh
SKILL=~/.claude/skills/book-to-podcast
OUT=~/book-podcasts/out/my-book
mkdir -p "$OUT"

# 1. Extract
python3 $SKILL/scripts/extract.py ~/Downloads/some-book.epub "$OUT"

# 2. Write $OUT/script.md, or have Claude do it.

# 3. Chunk (500 chars for Sarvam; 4500 for ElevenLabs)
python3 $SKILL/scripts/chunk.py "$OUT/script.md" --max-chars 500

# 4. Render
python3 $SKILL/scripts/tts.py "$OUT/chunks.json" "$OUT/episode.mp3" --provider sarvam

# 5. Publish
python3 $SKILL/scripts/publish.py "$OUT/episode.mp3" \
  --title "Some Book" --author "Some Author" \
  --summary "Two-line description."
```

---

## Cost reference (per book, ~43k chars)

| Provider | Per book | For 4 books/week | Notes |
|---|---|---|---|
| ElevenLabs Creator | ~$13 | needs $99+/month plan | Best quality |
| Sarvam bulbul:v2 | ~₹40 (~$0.50) | ~₹160/month | Good Indian English |
| Kokoro | free | free | Local only, American/British English voices |

Kokoro requires no API key and runs on your machine. On Apple Silicon a 45-min episode renders in roughly 15–25 minutes (CPU/MPS). On a machine with a CUDA GPU it's much faster. Voice quality is competitive with Sarvam for English narration.

---

## Troubleshooting

**TTS crashed mid-render.** Rerun the same `tts.py` command. Per-chunk audio is cached; only missing chunks re-render.

**ElevenLabs quota exceeded.** Top up at elevenlabs.io, then rerun.

**Sarvam returns garbled audio for a name.** Try a different speaker: `manisha`, `vidya`, `karun` are alternatives. Full list in Sarvam docs.

**MP3 is too long/short.** ElevenLabs paces at ~155 wpm, Sarvam at ~187 wpm. To lengthen a Sarvam episode, target 8,000+ words in the script.

**Want a different voice for one book.** Override at run time:

```sh
SARVAM_HOST_A_SPEAKER=manisha python3 ~/.claude/skills/book-to-podcast/scripts/tts.py ...
```

**Long books (>110k words).** The prompt template has a two-pass fallback: per-chapter summaries, then synthesized script. See `prompts/script-empire.md`.

---

## Privacy

MP3s and `feed.xml` live on your Cloudflare R2 bucket, served at a `r2.dev` URL. Security is by URL obscurity — the path is an unguessable random slug, and the feed tells podcast directories not to index it. Don't share the subscribe URL publicly.

If you want stronger privacy: signed R2 URLs or Cloudflare Workers basic-auth on the bucket are straightforward extensions (not implemented here).
