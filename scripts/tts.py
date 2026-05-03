#!/usr/bin/env python3
"""Render chunks.json into a single MP3 via ElevenLabs, Sarvam, or Kokoro.

Usage: tts.py <chunks.json> <output.mp3> [--provider {elevenlabs,sarvam,kokoro}]
              [--language {en,hi,kn,ta,te,bn,ml,mr,gu,pa,od}]

Provider default comes from env TTS_PROVIDER (or 'elevenlabs').
Language default comes from env SARVAM_LANGUAGE (or 'en-IN'). Sarvam only.

ElevenLabs env: ELEVENLABS_API_KEY, HOST_A_VOICE_ID, HOST_B_VOICE_ID,
  ELEVENLABS_MODEL (default eleven_multilingual_v2).
Sarvam env: SARVAM_API_KEY, SARVAM_HOST_A_SPEAKER, SARVAM_HOST_B_SPEAKER,
  SARVAM_NARRATOR_SPEAKER, SARVAM_MODEL (default bulbul:v2),
  SARVAM_LANGUAGE (default en-IN).
  For Indian languages: set SARVAM_MODEL=bulbul:v3 for best quality (43 speakers).
Kokoro env: KOKORO_NARRATOR_VOICE, KOKORO_HOST_A_VOICE, KOKORO_HOST_B_VOICE,
  KOKORO_LANG_CODE (default 'a' = American English), KOKORO_SPEED (default 1.0).
  No API key needed — runs fully locally. Does NOT support Indian languages.

Speaker codes in chunks.json:
  "A" -> Host A voice
  "B" -> Host B voice
  "N" -> Narrator voice (monologue mode)

Cache: <chunks_dir>/.audio_cache_<provider>/piece_NNNN.mp3 — persistent, resumable.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from pydub import AudioSegment

SKILL_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(SKILL_ROOT / ".env")

GAP_MS = 250
MAX_RETRIES = 4
RETRY_BACKOFF_S = 5

# Supported Indian language codes (short → full BCP-47)
LANG_CODES: dict[str, str] = {
    "en": "en-IN", "hi": "hi-IN", "kn": "kn-IN",
    "ta": "ta-IN", "te": "te-IN", "bn": "bn-IN",
    "ml": "ml-IN", "mr": "mr-IN", "gu": "gu-IN",
    "pa": "pa-IN", "od": "od-IN",
}

# Default bulbul:v3 speakers per language
LANG_SPEAKER_DEFAULTS: dict[str, dict[str, str]] = {
    "en-IN": {"A": "anushka", "B": "abhilash", "N": "arya"},
    "hi-IN": {"A": "kavya",   "B": "rohan",    "N": "priya"},
    "kn-IN": {"A": "shruti",  "B": "mani",     "N": "kavya"},
    "ta-IN": {"A": "kavitha", "B": "rehan",    "N": "shruti"},
    "te-IN": {"A": "suhani",  "B": "soham",    "N": "neha"},
    "bn-IN": {"A": "priya",   "B": "rahul",    "N": "neha"},
    "ml-IN": {"A": "simran",  "B": "kabir",    "N": "pooja"},
    "mr-IN": {"A": "ishita",  "B": "varun",    "N": "kavya"},
    "gu-IN": {"A": "pooja",   "B": "amit",     "N": "priya"},
    "pa-IN": {"A": "ritu",    "B": "dev",      "N": "manisha"},
    "od-IN": {"A": "shreya",  "B": "manan",    "N": "neha"},
}

SSML_RE = re.compile(r"<[^>]+>")


def strip_ssml(text: str) -> str:
    """Remove SSML tags for providers that do not support them."""
    return SSML_RE.sub("", text).strip()


# ---------- ElevenLabs ----------

def render_elevenlabs(text: str, speaker: str) -> bytes:
    from elevenlabs.client import ElevenLabs

    api_key = os.environ["ELEVENLABS_API_KEY"]
    voice_a = os.environ["HOST_A_VOICE_ID"]
    voice_b = os.environ["HOST_B_VOICE_ID"]
    model = os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")

    if speaker == "A":
        voice = voice_a
    elif speaker == "B":
        voice = voice_b
    else:  # "N" — narrator falls back to host A voice
        voice = voice_a

    client = ElevenLabs(api_key=api_key)
    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            audio = client.text_to_speech.convert(
                voice_id=voice,
                model_id=model,
                text=text,
                output_format="mp3_44100_128",
            )
            return b"".join(audio)
        except (httpx.ReadError, httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadTimeout) as e:
            last_err = e
            wait = RETRY_BACKOFF_S * (2 ** attempt)
            print(f"  network error ({e}); retry {attempt+1}/{MAX_RETRIES} in {wait}s", file=sys.stderr, flush=True)
            time.sleep(wait)
    raise RuntimeError(f"elevenlabs render failed after {MAX_RETRIES} retries: {last_err}")


# ---------- Kokoro ----------

# Module-level pipeline cache so we load the model once across all chunks.
_kokoro_pipeline: dict = {}


def _get_kokoro_pipeline(lang_code: str):
    if lang_code not in _kokoro_pipeline:
        try:
            from kokoro import KPipeline
        except ImportError:
            sys.exit("kokoro not installed: pip install kokoro soundfile")
        print(f"loading Kokoro model (lang={lang_code})...", file=sys.stderr, flush=True)
        _kokoro_pipeline[lang_code] = KPipeline(lang_code=lang_code)
    return _kokoro_pipeline[lang_code]


def render_kokoro(text: str, speaker: str) -> bytes:
    from io import BytesIO
    import numpy as np

    try:
        import soundfile as sf
    except ImportError:
        sys.exit("soundfile not installed: pip install soundfile")

    lang_code = os.environ.get("KOKORO_LANG_CODE", "a")
    speed = float(os.environ.get("KOKORO_SPEED", "1.0"))
    voice_a = os.environ.get("KOKORO_HOST_A_VOICE", "af_heart")
    voice_b = os.environ.get("KOKORO_HOST_B_VOICE", "am_adam")
    voice_n = os.environ.get("KOKORO_NARRATOR_VOICE", "am_michael")

    voice = {"A": voice_a, "B": voice_b}.get(speaker, voice_n)
    clean_text = strip_ssml(text)

    pipeline = _get_kokoro_pipeline(lang_code)
    audio_chunks = []
    for _, _, audio in pipeline(clean_text, voice=voice, speed=speed):
        audio_chunks.append(audio)

    if not audio_chunks:
        raise RuntimeError("kokoro returned no audio")

    full_audio = np.concatenate(audio_chunks)

    # Kokoro outputs float32 at 24000 Hz — convert to MP3 via WAV intermediary.
    wav_buf = BytesIO()
    sf.write(wav_buf, full_audio, 24000, format="WAV")
    wav_buf.seek(0)
    seg = AudioSegment.from_file(wav_buf, format="wav")
    mp3_buf = BytesIO()
    seg.export(mp3_buf, format="mp3", bitrate="64k")
    return mp3_buf.getvalue()


# ---------- Sarvam ----------

SARVAM_URL = "https://api.sarvam.ai/text-to-speech"


def render_sarvam(text: str, speaker: str) -> bytes:
    api_key = os.environ["SARVAM_API_KEY"]
    speaker_a = os.environ.get("SARVAM_HOST_A_SPEAKER", "anushka")
    speaker_b = os.environ.get("SARVAM_HOST_B_SPEAKER", "abhilash")
    speaker_n = os.environ.get("SARVAM_NARRATOR_SPEAKER", "arya")
    model = os.environ.get("SARVAM_MODEL", "bulbul:v3")
    lang = os.environ.get("SARVAM_LANGUAGE", "en-IN")

    if speaker == "A":
        sarvam_speaker = speaker_a
    elif speaker == "B":
        sarvam_speaker = speaker_b
    else:
        sarvam_speaker = speaker_n

    # Strip SSML — Sarvam does not support it.
    clean_text = strip_ssml(text)

    payload: dict = {
        "inputs": [clean_text],
        "target_language_code": lang,
        "speaker": sarvam_speaker,
        "model": model,
        "pace": 1.0,
        "speech_sample_rate": 22050,
        "enable_preprocessing": True,
    }
    # bulbul:v3 rejects pitch and loudness parameters
    if not model.startswith("bulbul:v3"):
        payload["pitch"] = 0
        payload["loudness"] = 1.0
    headers = {
        "api-subscription-key": api_key,
        "Content-Type": "application/json",
    }

    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            with httpx.Client(timeout=60.0) as client:
                r = client.post(SARVAM_URL, json=payload, headers=headers)
            if r.status_code == 200:
                data = r.json()
                if not data.get("audios"):
                    raise RuntimeError(f"sarvam returned no audio: {data}")
                # Sarvam returns base64-encoded WAV.
                wav_bytes = base64.b64decode(data["audios"][0])
                # Convert WAV -> MP3 in memory via pydub.
                from io import BytesIO
                seg = AudioSegment.from_file(BytesIO(wav_bytes), format="wav")
                buf = BytesIO()
                seg.export(buf, format="mp3", bitrate="64k")
                return buf.getvalue()
            elif r.status_code in (429, 500, 502, 503, 504):
                last_err = RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
                wait = RETRY_BACKOFF_S * (2 ** attempt)
                print(f"  sarvam {r.status_code}; retry {attempt+1}/{MAX_RETRIES} in {wait}s", file=sys.stderr, flush=True)
                time.sleep(wait)
            else:
                # Non-retryable (auth, quota, validation)
                raise RuntimeError(f"sarvam HTTP {r.status_code}: {r.text[:300]}")
        except (httpx.ReadError, httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadTimeout) as e:
            last_err = e
            wait = RETRY_BACKOFF_S * (2 ** attempt)
            print(f"  network error ({e}); retry {attempt+1}/{MAX_RETRIES} in {wait}s", file=sys.stderr, flush=True)
            time.sleep(wait)
    raise RuntimeError(f"sarvam render failed after {MAX_RETRIES} retries: {last_err}")


# ---------- Main ----------

def _resolve_lang_code(lang: str) -> str:
    """Accept short code (hi) or full code (hi-IN), return full BCP-47 code."""
    if "-" in lang:
        return lang
    return LANG_CODES.get(lang.lower(), lang)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("chunks")
    p.add_argument("output")
    p.add_argument("--provider", choices=["elevenlabs", "sarvam", "kokoro"],
                   default=os.environ.get("TTS_PROVIDER", "elevenlabs"))
    p.add_argument(
        "--language",
        metavar="LANG",
        default=None,
        help="Output language code: en hi kn ta te bn ml mr gu pa od (Sarvam only).",
    )
    args = p.parse_args()

    # Resolve and apply language override
    if args.language:
        lang_code = _resolve_lang_code(args.language)
        if args.provider == "kokoro":
            print(
                "error: Kokoro does not support Indian languages. "
                "Use --provider sarvam instead.",
                file=sys.stderr,
            )
            return 2
        if args.provider == "elevenlabs":
            print(
                "warning: ElevenLabs multilingual quality for Indian languages is "
                "inconsistent. Sarvam (--provider sarvam) gives better results.",
                file=sys.stderr,
            )
        # Override env language
        os.environ["SARVAM_LANGUAGE"] = lang_code
        # Apply per-language speaker defaults for bulbul:v3 (only if not set in env)
        model = os.environ.get("SARVAM_MODEL", "bulbul:v2")
        if lang_code != "en-IN" and model.startswith("bulbul:v2"):
            print(
                f"warning: SARVAM_MODEL=bulbul:v2 has only 7 speakers. "
                f"Set SARVAM_MODEL=bulbul:v3 in .env for better Indian language quality.",
                file=sys.stderr,
            )
        defaults = LANG_SPEAKER_DEFAULTS.get(lang_code, {})
        if defaults and not model.startswith("bulbul:v2"):
            if not os.environ.get("SARVAM_HOST_A_SPEAKER"):
                os.environ["SARVAM_HOST_A_SPEAKER"] = defaults["A"]
            if not os.environ.get("SARVAM_HOST_B_SPEAKER"):
                os.environ["SARVAM_HOST_B_SPEAKER"] = defaults["B"]
            if not os.environ.get("SARVAM_NARRATOR_SPEAKER"):
                os.environ["SARVAM_NARRATOR_SPEAKER"] = defaults["N"]
        print(
            f"language: {lang_code}  "
            f"host_a={os.environ.get('SARVAM_HOST_A_SPEAKER', '?')}  "
            f"host_b={os.environ.get('SARVAM_HOST_B_SPEAKER', '?')}  "
            f"narrator={os.environ.get('SARVAM_NARRATOR_SPEAKER', '?')}",
            file=sys.stderr,
        )

    chunks_path = Path(args.chunks).expanduser().resolve()
    out_path = Path(args.output).expanduser().resolve()
    chunks = json.loads(chunks_path.read_text(encoding="utf-8"))

    cache_dir = chunks_path.parent / f".audio_cache_{args.provider}"
    cache_dir.mkdir(exist_ok=True)

    if args.provider == "elevenlabs":
        if not (os.environ.get("ELEVENLABS_API_KEY") and os.environ.get("HOST_A_VOICE_ID") and os.environ.get("HOST_B_VOICE_ID")):
            print("missing env: ELEVENLABS_API_KEY / HOST_A_VOICE_ID / HOST_B_VOICE_ID", file=sys.stderr)
            return 2
        render = render_elevenlabs
    elif args.provider == "sarvam":
        if not os.environ.get("SARVAM_API_KEY"):
            print("missing env: SARVAM_API_KEY", file=sys.stderr)
            return 2
        render = render_sarvam
    else:  # kokoro
        render = render_kokoro

    combined = AudioSegment.silent(duration=300)
    gap = AudioSegment.silent(duration=GAP_MS)

    cached_count = 0
    rendered_count = 0
    for c in chunks:
        piece_path = cache_dir / f"piece_{c['index']:04d}.mp3"
        if piece_path.exists() and piece_path.stat().st_size > 0:
            cached_count += 1
        else:
            print(f"[{c['index']+1}/{len(chunks)}] {args.provider} speaker={c['speaker']} ({len(c['text'])} chars)", file=sys.stderr, flush=True)
            audio_bytes = render(c["text"], c["speaker"])
            piece_path.write_bytes(audio_bytes)
            rendered_count += 1
        piece = AudioSegment.from_file(piece_path, format="mp3")
        combined += piece + gap

    print(f"cached: {cached_count}, rendered: {rendered_count}", file=sys.stderr, flush=True)

    combined = combined.set_channels(1)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    combined.export(out_path, format="mp3", bitrate="64k")

    print(json.dumps({
        "provider": args.provider,
        "out": str(out_path),
        "duration_seconds": round(len(combined) / 1000, 1),
        "chunks_rendered": rendered_count,
        "chunks_cached": cached_count,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
