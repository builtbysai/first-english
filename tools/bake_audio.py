#!/usr/bin/env python3
"""Bake natural-voice MP3s for the First English app.

The app's fixed vocabulary (sight words, level words, story sentences, UI
phrases) is synthesized once with a neural voice and shipped as static files.
At runtime the app plays the baked MP3 when present and falls back to the
browser's speechSynthesis otherwise.

Requires a normal (unproxied) network connection — the edge TTS websocket
does not survive the hatch egress proxy, so run this on your own machine:

    pip install edge-tts
    python3 tools/bake_audio.py

Output: english-app/audio/<slug>.mp3 + english-app/audio/manifest.json
Commit the audio/ directory; the app picks it up automatically.
"""

import asyncio
import json
import re
import sys
from pathlib import Path

import edge_tts

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "first_english_v11.html"
OUT = ROOT / "audio"
VOICE = "en-US-AvaNeural"   # warm, clear neural voice; good for young learners
RATE = "-8%"                # slightly slow for clarity

# Fixed UI phrases the app speaks (must be the EXACT utterance passed to say();
# dynamic "Find: X" / "Say: X" / "Listen: X" prompts bake per-word audio only)
PHRASES = [
    "Try again!", "Yes!", "Amazing!", "Great!", "Wonderful!",
    "Good trying! Practice makes perfect!",
    "Hello! I am Ollie. Tap a picture to start.",
    "Tap the word you hear!",
    "Amazing! You are a sight word star!",
    "Amazing! You are a listening star!",
    "Amazing! You are a word star!",
    "Amazing! You read a story!",
    "Great talking! You are a super talker!",
    "Wow! You finished every level! You are a reading star!",
    "Hello! The cat sat on the mat.",
]


def slugify(w: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", w.lower()).strip("-")
    return s or "x"


def extract_vocab(html: str):
    texts = set()
    for w in re.findall(r'\{w:"([^"]+)"', html):
        texts.add(w)
    # story sentences: {t:"..",e:".."} (t-first; accept either order)
    for t in re.findall(r'\{t:"([^"]+)",e:', html):
        texts.add(t)
    for t in re.findall(r'\{e:"[^"]*",t:"([^"]+)"\}', html):
        texts.add(t)
    # speak sentences: {t:"..",k:"..",e:".."}
    for t in re.findall(r'\{t:"([^"]+)",k:"[^"]+",e:', html):
        texts.add(t)
    # dialog prompts: {k:"tap",q:"..",...} and expand:".."
    for t in re.findall(r'\{k:"(?:tap|grownup)",q:"([^"]+)"', html):
        texts.add(t.replace('___', '...'))
    for t in re.findall(r'expand:"([^"]+)"', html):
        texts.add(t)
    # letter-sound keywords live in LEVELS letters arrays as {l:"s",w:"sun"}
    # (l can be a digraph/trigraph: ai, sh, igh ...)
    for w in re.findall(r'\{l:"[^"]+",w:"([^"]+)"\}', html):
        texts.add(w)
    texts.update(PHRASES)
    # "Find: X" / "Listen: X" prompts are dynamic; bake the per-word audio only.
    return sorted(texts)


async def bake_one(sem, voice, text, path):
    async with sem:
        c = edge_tts.Communicate(text, voice, rate=RATE)
        await c.save(str(path))


async def main():
    html = HTML.read_text(encoding="utf-8")
    texts = extract_vocab(html)
    print(f"{len(texts)} utterances to bake with {VOICE} @ {RATE}")
    OUT.mkdir(exist_ok=True)
    manifest = {}
    sem = asyncio.Semaphore(6)
    done = 0
    seen_slugs = {}
    collisions = []

    async def one(text):
        nonlocal done
        slug = slugify(text)
        # Slug collisions between DIFFERENT texts (e.g. "Hello!" vs "Hello")
        # would make the runtime play the wrong clip. Fail loudly instead of
        # silently writing unreachable files.
        if slug in seen_slugs and seen_slugs[slug] != text:
            collisions.append((seen_slugs[slug], text))
            return
        seen_slugs[slug] = text
        fn = f"{slug}.mp3"
        path = OUT / fn
        if not path.exists():
            await bake_one(sem, VOICE, text, path)
        manifest[slug] = fn
        done += 1
        if done % 25 == 0:
            print(f"  {done}/{len(texts)}")

    await asyncio.gather(*(one(t) for t in texts))
    if collisions:
        print("SLUG COLLISIONS (different texts, same file) — fix slugify before shipping:")
        for a, b in collisions:
            print(f"  {a!r}  vs  {b!r}")
        sys.exit(1)
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    total_mb = sum(p.stat().st_size for p in OUT.glob("*.mp3")) / 1e6
    print(f"done: {len(manifest)} clips, {total_mb:.1f} MB -> {OUT}/")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
