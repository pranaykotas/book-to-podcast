# Script generation prompt — Empire-style two-host podcast

Use this template when turning `book.txt` into `script.md`.

## Voices

- **Host A** — curious lead. Sets up each idea, asks the framing question, summarizes where they are. Often the one quoting the book directly.
- **Host B** — reactive co-host. Reacts, pushes back, brings in analogies (regional context, connects to other books or recent news). Slightly more skeptical.

Both speak as informed generalists who have read the book carefully. They are NOT the author. They are not interviewing the author. They are two friends working through the book's ideas out loud.

Reference podcasts in tone: *Empire* (Anita Anand + William Dalrymple) for the narrating-and-reacting structure. Less meandering than *Seen & Unseen*. Less academic than *Ideas of India*.

## Length and pacing

- Target **6,800–7,200 words**. At ~155 wpm conversational pace this lands at ~45 minutes.
- Roughly equal speaking time. Aim for turns of 40–120 words each. Avoid monologues over 200 words.
- ~80–120 turns total.

## Three-act structure

1. **Cold open + setup (≈ 12 min, ~1,800 words)**
   - Open with a concrete hook: a scene, a number, an anecdote from the book that lands in the first 30 seconds. Not "Today we're talking about..."
   - Introduce the book and author by minute 2, but woven in, not announced.
   - Establish the central question the book is wrestling with.

2. **Core arguments (≈ 22 min, ~3,400 words)**
   - Walk through the main arguments in the book's own order where possible.
   - For each major claim: state it, give the book's evidence, then have Host B react / push back / extend.
   - Use direct quotes from the book sparingly — 3 to 5 across the whole episode, no more.
   - Indian context analogies welcome but never forced.

3. **Implications + critique + close (≈ 11 min, ~1,700 words)**
   - What does this book get right that others miss?
   - What's underweighted or wrong?
   - Who should read it? Who shouldn't bother?
   - End on a clean exchange — not a sermon, not a wrap-up speech. The last line is a co-host's reaction, not a "thanks for listening".

## Formatting rules — strict

Every non-blank line is exactly one of:

```
[Host A]: ...
[Host B]: ...
```

- No section headings, no `**bold**`, no `## Act 2`, no stage directions like `(laughs)`.
- No "Welcome to the show", "I'm your host", "Make sure to subscribe". This goes through TTS — anything you write gets spoken.
- Em-dashes → replace with comma + space. ElevenLabs reads em-dashes oddly.
- Numbers under 100 → spell out ("forty-three percent", not "43%"). Larger figures stay as digits.
- Acronyms that should be spelled out (RBI, NATO, GDP) — leave as-is, ElevenLabs handles them.
- Insert SSML pauses at natural breaks: `<break time="0.4s"/>` between paragraphs of the same speaker, `<break time="0.2s"/>` for shorter beats. Don't overdo — a pause every few turns is plenty.
- Use `<emphasis level="moderate">word</emphasis>` 3–6 times per episode for genuinely important words. Never on more than two words at once.

## Anti-AI-tells pass

After drafting, read through and remove / rewrite:
- Em-dashes (—)
- "delve", "tapestry", "landscape", "navigate", "leverage", "underscore", "robust"
- "It's important to note that...", "It's worth mentioning..."
- "In conclusion", "To summarize", "At the end of the day"
- Tricolons that feel scripted ("the good, the bad, and the ugly" patterns)
- Symmetrical sentences where both hosts sound the same — vary rhythm.

If the `writing-anti-ai` skill is available, route the draft through it once before saving.

## Long-book fallback

If the source `book.txt` exceeds ~110,000 words (≈ 150k tokens):

1. Split by chapter (extract.py emits chapter boundaries).
2. For each chapter, write a tight 200-word analytical summary capturing argument + key evidence + author's voice.
3. Concatenate the summaries into a synthesis document.
4. Use the synthesis (plus chapter 1 and the conclusion verbatim) as input for the script. This preserves opening tone and final conclusions while compressing the middle.

## Quality bar before saving

- Word count between 6,800 and 7,200.
- Opening line is concrete (a scene, a number, a quote — not a meta-introduction).
- At least three moments where Host B genuinely disagrees or complicates Host A's framing.
- At least one Indian-context analogy if the book is non-India-focused.
- No author-voice errors: hosts never say "as I argue in chapter 4" — they're not the author.
- Closing exchange feels like a conversation pausing, not a press release ending.
