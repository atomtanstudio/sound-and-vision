"""ACE-Step 1.5 and MiniMax Music 3, beside YuE2. The same song (its words and its sound) goes to each in the form it
reads, in one ComfyUI stage:

- ACE-Step 1.5 reads comma tags and the lyrics with section tags, and has real controls for tempo, key, time
  signature and language; its language model plans the song first. The fastest (about 14 s a minute of song), and
  the only one besides YuE2 that takes influences (ACE LoRAs).
- MiniMax Music 3 reads a caption in sentences and the lyrics; it chooses its own length up to a limit, and is the
  slowest (about 90 s a minute). Guidance is its one setting worth turning.
"""

from __future__ import annotations

from typing import Any

from .yue2 import LENGTH_SECONDS, SongError, SongRequest, sung_words, tidy_lyrics

MODELS = {"yue2": "YuE2", "ace15": "ACE-Step 1.5", "music3": "MiniMax Music 3"}
LANGS = {"english": "en", "spanish": "es", "french": "fr", "german": "de", "italian": "it", "portuguese": "pt",
         "japanese": "ja", "korean": "ko", "chinese": "zh", "mandarin": "zh", "russian": "ru", "dutch": "nl",
         "swedish": "sv", "polish": "pl", "arabic": "ar", "hindi": "hi"}
VOICE_TAGS = {"female": "female vocals", "male": "male vocals", "duet": "male and female duet"}
VOICE_WORDS = {"female": "a female singer", "male": "a male singer", "duet": "a male and female duet"}
MUSIC3_MAX = 360.0


def _sound(r: SongRequest) -> list[str]:
    parts = [g.strip() for g in r.genres if g.strip()] + [m.strip() for m in r.moods if m.strip()]
    if r.instruments.strip():
        parts.append(r.instruments.strip())
    if r.extra.strip():
        parts.append(r.extra.strip())
    if not parts and not (r.style_override or "").strip():
        raise SongError("Give the song a sound: at least a genre, a mood or some instruments.")
    return parts


def ace_tags(r: SongRequest, words: list[str] | None = None) -> str:
    """`words`: influences it can't load, described (sv/influences.py's in_words)."""
    if r.style_override and r.style_override.strip():
        return " ".join(r.style_override.split())
    parts = _sound(r) + list(words or [])
    parts.append(VOICE_TAGS.get(r.voice or "", "vocals") if r.sung else "instrumental")
    return ", ".join(dict.fromkeys(p for p in parts if p))


def music3_caption(r: SongRequest, words: list[str] | None = None) -> str:
    """A caption the way Music 3 was taught: what it is, who sings, what plays, how it feels, tempo and key (and
    `words`, influences it can't load, described)."""
    if r.style_override and r.style_override.strip():
        return " ".join(r.style_override.split())
    _sound(r)
    genre = " / ".join(g.strip() for g in r.genres if g.strip()) or "song"
    moods = ", ".join(m.strip() for m in r.moods if m.strip())
    lead = f"A {moods + ' ' if moods else ''}{genre} {'song' if r.sung else 'instrumental'}"
    bits = [lead + (f" with {VOICE_WORDS[r.voice]}" if r.sung and r.voice in VOICE_WORDS else "") + "."]
    if r.instruments.strip():
        bits.append(f"Instruments: {r.instruments.strip()}.")
    if r.extra.strip():
        bits.append(f"Production: {r.extra.strip()}.")
    if r.tempo or r.key:
        bits.append(" ".join(x for x in [f"{r.tempo} BPM" if r.tempo else "", f"in {r.key}" if r.key else ""] if x) + ".")
    if words:
        bits.append("In the spirit of " + "; ".join(words) + ".")
    return " ".join(bits)


def prepare(model: str, r: SongRequest, library: dict[str, dict]) -> dict[str, Any]:
    """Everything one take of ACE-Step 1.5 or Music 3 sends (the take's "What the model got")."""
    if model not in ("ace15", "music3"):
        raise SongError("Unknown song model.")
    if r.sung:
        lyrics = tidy_lyrics(r.lyrics)
        if sung_words(lyrics) < 4:
            raise SongError("A sung song needs lyrics. Write some, or let the writer draft them.")
    else:
        lyrics = "[Instrumental]"
    seconds = float(r.engine.seconds or LENGTH_SECONDS.get(r.length, 210.0))
    from ..influences import sort_out
    influences, words = sort_out(r.influences, library, model)  # trained for it, or described in words
    if model == "ace15":
        params = {"style": ace_tags(r, words), "lyrics": lyrics, "seconds": min(seconds, 600.0), "bpm": r.tempo or 120,
                  "key": r.key or "C major", "time_signature": r.time_signature or "4",
                  "language": LANGS.get(r.language.strip().lower(), "en"),
                  "temperature": round(0.85 * r.creativity, 3), "guidance": 2.0}
    else:
        g = r.engine.guidance
        params = {"style": music3_caption(r, words), "lyrics": lyrics, "seconds": min(seconds, MUSIC3_MAX),
                  "guidance": g if g is not None and 1.0 <= g <= 4.0 else 1.7}
    return {"model": model, "style": params["style"], "lyrics": lyrics, "influences": influences, "params": params,
            "sung": r.sung, "plan": None, "sketch": None}
