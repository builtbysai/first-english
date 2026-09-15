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

# Fixed UI phrases the app speaks (must match say() call sites)
PHRASES = [
    "Try again!", "Yes!", "Amazing!", "Great!", "Wonderful!",
    "Good trying! Practice makes perfect!",
    "Hello! I am Ollie. Tap a picture to start.",
    "Hello! I'm Ollie. Tap a level to begin.",
    "Tap the word you hear!",
    "You are a sight word star!",
    "You are a word star!",
    "Amazing! You are a reading star!",
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
    # story sentences: {e:"..",t:".."}
    for t in re.findall(r'\{e:"[^"]*",t:"([^"]+)"\}', html):
        texts.add(t)
    # letter-sound keywords live in LEVELS letters arrays as {l:"s",w:"sun"}
    for w in re.findall(r'\{l:"[^"]",w:"([^"]+)"\}', html):
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
    seen_slugs = set()

    async def one(text):
        nonlocal done
        slug = slugify(text)
        # de-dupe slugs ("a" the letter vs "a" the word etc.)
        base, i = slug, 2
        while slug in seen_slugs:
            slug = f"{base}-{i}"
            i += 1
        seen_slugs.add(slug)
        fn = f"{slug}.mp3"
        path = OUT / fn
        if not path.exists():
            await bake_one(sem, VOICE, text, path)
        manifest[slug] = fn
        done += 1
        if done % 25 == 0:
            print(f"  {done}/{len(texts)}")

    await asyncio.gather(*(one(t) for t in texts))
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    total_mb = sum(p.stat().st_size for p in OUT.glob("*.mp3")) / 1e6
    print(f"done: {len(manifest)} clips, {total_mb:.1f} MB -> {OUT}/")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
