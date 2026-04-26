# Script generation prompt — single-narrator monologue

Use this template when the user has chosen monologue mode (one voice, no dialogue).

## Voice

A single thoughtful narrator. The reader, not the author. Walks through the book's arguments, quotes, evidence, and weaknesses in their own voice. Curious, slightly skeptical, knowledgeable but not pretending to be the author. Treat it as the voice of a domain-expert friend explaining the book to you on a long drive.

Bring in regional or domain analogies where they land naturally. No academic hedging.

## Length and pacing

- Target **6,500–7,000 words** spoken. At ~155 wpm conversational pace this lands at ~45 minutes.
- Paragraphs of roughly 60–150 words each. Avoid both staccato bullets and long monologues over 250 words.
- Aim for ~50–70 paragraphs total.

## Three-act structure

1. **Cold open + setup (≈ 12 min, ~1,800 words)**
   - Open with a concrete hook: a scene, a number, an anecdote from the book that lands in the first 30 seconds. Not "Today I will tell you about..."
   - Introduce the book and author by minute 2, woven in.
   - State the central question the book is wrestling with.

2. **Core arguments (≈ 22 min, ~3,200 words)**
   - Walk through main arguments in the book's own order where possible.
   - For each major claim: state it, give the book's evidence, then a brief evaluative sentence — does this hold up, what is the counter-case, where does it land in Indian context.
   - Use direct quotes from the book sparingly — 3 to 5 across the whole episode.

3. **Critique + close (≈ 11 min, ~1,500 words)**
   - What does this book get right that others miss?
   - What is underweighted or wrong?
   - Who should read it? Who should not bother?
   - End on a clean closing thought, not a "thanks for listening".

## Formatting rules — strict

Every non-blank line is exactly one of:

```
[Narrator]: ...
```

- No section headings, no `**bold**`, no `## Act 2`, no stage directions like `(pause)`.
- No "Welcome to the show", "I am your host", "Make sure to subscribe". This goes through TTS — anything you write gets spoken.
- Em-dashes → replace with comma + space. TTS reads em-dashes oddly.
- Numbers under 100 → spell out ("forty-three percent", not "43%"). Larger figures stay as digits.
- Acronyms that should be spelled out (RBI, NATO, GDP) — leave as-is, the TTS handles them.
- For ElevenLabs runs: insert SSML pauses at natural breaks: `<break time="0.4s"/>` between paragraphs, `<break time="0.2s"/>` for shorter beats. Use `<emphasis level="moderate">word</emphasis>` 3–6 times per episode for genuinely important words.
- For Sarvam runs: SSML tags will be stripped automatically by the TTS step. Natural punctuation does the pacing work.

## Anti-AI-tells pass

After drafting, read through and remove / rewrite:
- Em-dashes (—)
- "delve", "tapestry", "landscape", "navigate", "leverage", "underscore", "robust"
- "It's important to note that...", "It's worth mentioning..."
- "In conclusion", "To summarize", "At the end of the day"
- Tricolons that feel scripted

If the `writing-anti-ai` skill is available, route the draft through it once before saving.

## Long-book fallback

Same as the conversation template. If `book.txt` exceeds ~110,000 words, summarize per chapter (200 words each), concatenate, plus chapter 1 + conclusion verbatim, then write the script from that synthesis.

## Quality bar before saving

- Word count between 6,500 and 7,000.
- Opening line is concrete (a scene, a number, a quote — not a meta-introduction).
- At least three moments where the narrator complicates or pushes back on the book's framing — this is a review, not a sales pitch.
- At least one Indian-context analogy if the book is non-India-focused.
- Closing line feels like a thought, not a press release.
