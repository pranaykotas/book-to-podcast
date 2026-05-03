---
name: book-to-podcast
description: Convert a non-fiction epub or pdf into a 45-minute two-host podcast (Empire-style co-hosts), generate audio via ElevenLabs or Sarvam, and publish to a private RSS feed on Cloudflare R2. Use when the user says "make a podcast from this book", "convert epub to podcast", "/book-to-podcast", or hands you an .epub/.pdf with intent to listen on commute.
---

# book-to-podcast

End-to-end pipeline: book file → 45-min two-host script → ElevenLabs or Sarvam MP3 → private RSS feed on Cloudflare R2 → user subscribes once in any podcast app.

## When to invoke

User says any of:
- "make a podcast from this book"
- "turn this epub into a podcast"
- "/book-to-podcast <path>"
- drops an `.epub` or `.pdf` path with clear intent to consume it as audio

## One-time setup (check before first run)

The skill expects `~/.claude/skills/book-to-podcast/.env` to exist with:

```
TTS_PROVIDER=sarvam
DEFAULT_FORMAT=monologue

ELEVENLABS_API_KEY=...      # only if using elevenlabs
HOST_A_VOICE_ID=...
HOST_B_VOICE_ID=...

SARVAM_API_KEY=...
SARVAM_HOST_A_SPEAKER=anushka
SARVAM_HOST_B_SPEAKER=abhilash
SARVAM_NARRATOR_SPEAKER=arya

R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_ENDPOINT=https://<account>.r2.cloudflarestorage.com
R2_BUCKET=podcast
R2_PUBLIC_BASE=https://pub-<random>.r2.dev
```

If `.env` is missing, walk the user through copying `config.example.env`, picking two ElevenLabs voices, and choosing a random unguessable slug (e.g. `python -c "import secrets; print(secrets.token_urlsafe(12))"`).

Python deps (install once into a venv at `~/.claude/skills/book-to-podcast/.venv`):
```
ebooklib pypdf beautifulsoup4 elevenlabs pydub feedgen python-dotenv
```

No Quarto setup needed. MP3s and feed.xml go directly to Cloudflare R2 via `publish.py`. The subscribe URL is `$R2_PUBLIC_BASE/feed.xml`.

## Workflow

1. Resolve input path. Fail clearly if not `.epub` or `.pdf`.
2. Ask the user three quick questions before proceeding:
   - **Format**: monologue (single narrator) or conversation (two-host Empire style)?
   - **Provider**: Sarvam (cheap, Indian voices) or ElevenLabs (premium)?
   - **Language**: English (default) / Hindi (हिंदी) / Kannada (ಕನ್ನಡ) / Tamil (தமிழ்) / Telugu (తెలుగు) / other Indian language?
     - Non-English + Kokoro → block: "Kokoro does not support Indian languages. Use Sarvam."
     - Non-English + ElevenLabs → warn: "ElevenLabs multilingual quality for Indian languages is inconsistent. Sarvam is recommended — continue anyway?"
     - Non-English + Sarvam + `SARVAM_MODEL=bulbul:v2` → warn: "bulbul:v2 has limited speakers. Set `SARVAM_MODEL=bulbul:v3` in .env for best quality."
3. Run `scripts/extract.py <input>` → prints title, author, chapter list, word count, and writes `out/<slug>/book.txt`.
4. Generate the script yourself (do NOT shell out — use Claude's own context):
   - Read `out/<slug>/book.txt`.
   - For conversation mode: read `prompts/script-empire.md`. Format every line as `[Host A]: ...` or `[Host B]: ...`.
   - For monologue mode: read `prompts/script-monologue.md`. Format every line as `[Narrator]: ...`.
   - **If language ≠ English**: apply the "Indian language output" section at the bottom of the relevant prompt. Write the entire script in the target language.
   - If word count > ~110k words, use the two-pass fallback described in the prompt template.
   - Write the script to `out/<slug>/script.md`. Target 6,500–7,200 words.
   - Run an anti-AI-tells pass. Use writing-anti-ai skill if available; otherwise self-edit.
5. Run `scripts/chunk.py out/<slug>/script.md [--max-chars N]`:
   - For ElevenLabs: default `--max-chars 4500`.
   - For Sarvam (English): `--max-chars 500`.
   - For Sarvam (Indian language): `--max-chars 450` (extra margin for multibyte characters).
6. Run `scripts/tts.py out/<slug>/chunks.json out/<slug>/episode.mp3 [--provider P] [--language L]`:
   - Pass `--language <code>` when language ≠ English (e.g. `--language hi` for Hindi).
   - Language codes: `hi` Hindi · `kn` Kannada · `ta` Tamil · `te` Telugu · `bn` Bengali · `ml` Malayalam · `mr` Marathi · `gu` Gujarati · `pa` Punjabi · `od` Odia.
   - Cache is persistent and per-provider; safe to retry.
7. Run `scripts/publish.py out/<slug>/episode.mp3 --title "<book title>" --author "<author>" --summary "<2-line blurb>"`. This:
   - Uploads MP3 to Cloudflare R2 bucket `$R2_BUCKET`.
   - Pulls existing `feed.xml` from R2, appends the new episode, pushes back.
   - Both MP3 and feed.xml live on R2 only — no GitHub commit needed.
8. Print the subscribe URL: `$R2_PUBLIC_BASE/feed.xml`. On first episode, instruct user to add it once in Pocket Casts / AntennaPod on Android.

## Important constraints

- Do not ask before the TTS step. Sarvam runs are cheap (~₹40/book); ElevenLabs runs are pricier but the user picks the provider via env, not per-run.
- Output dir is `$WORK_DIR/<slug>/` (from `.env`). Create if missing.
- If the book is fiction or under 30k words, warn the user — pipeline is tuned for non-fiction books of substantial length.

## File layout

```
~/.claude/skills/book-to-podcast/
  SKILL.md
  config.example.env
  prompts/script-empire.md
  scripts/extract.py
  scripts/chunk.py
  scripts/tts.py
  scripts/publish.py
```

Output (per book):
```
$WORK_DIR/<slug>/
  book.txt
  script.md
  chunks.json
  episode.mp3
```
