"""YuE2, the default song model, through sv-comfy in two stages:

1. Sketch: YuE2 writes the song's plan in ABC notation (melody, and chords unless "melody only").
   The plan is checked against the lyrics (a plan that runs past them is trimmed, see guard()),
   kept with the take, and shown to the user as the song's sketch.
2. Sing: YuE2 sings the lyrics to that sketch, and the audio comes back.

"Free" skips the sketch (YuE2's no-plan mode). A cover replaces YuE2's own sketch with a song's melody (and its
chords, with "full") written down by SheetSage2 from the song you're covering (the song's `reference`). Influences (LoRAs) apply to both stages and need a
sketch: without one an influenced take can run on without ending (found by the old app).

What the user chooses in plain words becomes the style text in YuE2's own order: language, voice,
genre, instruments, mood, extra words, then tempo and key as hints (YuE2 reads them as text; they
are not controls).
"""

from __future__ import annotations

import random
import re
from typing import Any

from pydantic import BaseModel, Field

SECTION_TAGS = ["Intro", "Verse", "Pre-Chorus", "Chorus", "Bridge", "Outro", "Instrumental", "Hook"]
LENGTH_SECONDS = {"short": 150.0, "song": 270.0, "long": 360.0}
INSTRUMENTAL_FORMS = {
    "short": ["Intro", "Verse", "Chorus", "Outro"],
    "song": ["Intro", "Verse", "Chorus", "Verse", "Chorus", "Bridge", "Chorus", "Outro"],
    "long": ["Intro", "Verse", "Chorus", "Verse", "Chorus", "Instrumental", "Bridge", "Chorus", "Chorus", "Outro"],
}
VOICES = {"female": "female vocal", "male": "male vocal", "duet": "male and female duet vocals"}
# "YuE2-instrumental-cot-full-loras" by Mothersuperior (huggingface.co/Mothersuperior/YuE2-instrumental-cot-full-loras),
# CC BY-NC 4.0: the published ComfyUI file, unmodified (scripts/install.sh downloads it; CREDITS.md)
INSTRUMENTAL_INFLUENCE = "soundandvision/yue2/ar_lora_inst_v3abc_comfyui.safetensors"


class InfluenceChoice(BaseModel):
    id: str
    strength: float = Field(ge=0.0, le=1.0)


class Engine(BaseModel):
    """Exact YuE2 settings (the "Engine room"). None means YuE2's own default."""

    plan_temperature: float | None = Field(None, ge=0.05, le=2.0)
    plan_top_p: float | None = Field(None, ge=0.05, le=1.0)
    plan_top_k: int | None = Field(None, ge=1, le=1000)
    plan_repetition_penalty: float | None = Field(None, ge=1.0, le=2.0)
    plan_penalty_window: int | None = Field(None, ge=1, le=2000)
    plan_max_tokens: int | None = Field(None, ge=256, le=20000)
    top_p: float | None = Field(None, ge=0.05, le=1.0)
    top_k: int | None = Field(None, ge=1, le=5000)
    guidance: float | None = Field(None, ge=0.0, le=20.0)
    steps: int | None = Field(None, ge=8, le=128)
    seconds: float | None = Field(None, ge=10, le=900)


class CoverChoice(BaseModel):
    """Cover a song: its melody ("melody") or its melody and chords ("full"), sung with your words and style. The
    app fills in the file and its length from the song's reference; what the browser sends there is ignored."""

    keep: str = Field("melody", pattern=r"^(melody|full)$")
    reference: str = ""
    seconds: float | None = None


class SongRequest(BaseModel):
    sung: bool = True
    voice: str | None = None  # female | male | duet | None (YuE2 decides)
    language: str = "English"
    genres: list[str] = []
    moods: list[str] = []
    instruments: str = ""
    extra: str = ""
    tempo: int | None = Field(None, ge=40, le=240)
    key: str | None = None
    style_override: str | None = None  # the exact style text, replacing the composed one
    lyrics: str = ""
    length: str = "song"  # short | song | long
    influences: list[InfluenceChoice] = []
    takes: int = Field(2, ge=1, le=4)
    plan: str = "full"  # full | melody | free
    creativity: float = Field(1.0, ge=0.3, le=1.6)  # the singing stage's temperature
    repetition: float = Field(1.2, ge=1.0, le=1.6)  # the singing stage's repetition penalty
    seed: int | None = Field(None, ge=0, le=2**63 - 1)
    engine: Engine = Engine()
    time_signature: str | None = Field(None, pattern=r"^[2346]$")  # ACE-Step 1.5 only
    cover: CoverChoice | None = None  # YuE2 only: sing to a song's written-down melody


class SongError(ValueError):
    pass


def compose_style(r: SongRequest) -> str:
    if r.style_override and r.style_override.strip():
        return " ".join(r.style_override.split())
    parts: list[str] = []
    if r.sung:
        parts.append(r.language)
        if r.voice in VOICES:
            parts.append(VOICES[r.voice])
    parts += [g.strip() for g in r.genres if g.strip()]
    if r.instruments.strip():
        parts.append(r.instruments.strip())
    parts += [m.strip() for m in r.moods if m.strip()]
    if r.extra.strip():
        parts.append(r.extra.strip())
    if not r.sung:
        parts.append("instrumental, no vocals")
    if r.tempo:
        parts.append(f"{r.tempo} BPM")
    if r.key:
        parts.append(r.key)
    style = ", ".join(dict.fromkeys(p for p in parts if p))
    if not any(p for p in (r.genres + r.moods + [r.instruments, r.extra]) if str(p).strip()):
        raise SongError("Give the song a sound: at least a genre, a mood or some instruments.")
    return style


def tidy_lyrics(text: str) -> str:
    """YuE2's lyric form: a [Tag] line, the sung lines, a blank line between sections; no numbering
    ("Verse 2" becomes "Verse"), no stray blank lines inside a section."""
    out: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        m = re.fullmatch(r"\[([^\]]+)\]", line)
        if m:
            name = re.sub(r"\s*\d+\s*$", "", m.group(1)).strip().title().replace("Pre Chorus", "Pre-Chorus")
            if out:
                out.append("")
            out.append(f"[{name}]")
        elif line:
            out.append(line)
    return "\n".join(out).strip()


def instrumental_lyrics(lyrics: str, length: str) -> str:
    tags = [f"[{t}]" for t in re.findall(r"^\s*\[([^\]\n]+)\]\s*$", lyrics or "", re.M)]
    return "\n\n".join(tags or [f"[{t}]" for t in INSTRUMENTAL_FORMS.get(length, INSTRUMENTAL_FORMS["song"])])


def sung_words(lyrics: str) -> int:
    return sum(len(l.split()) for l in lyrics.splitlines() if l.strip() and not l.strip().startswith("["))


def prepare(r: SongRequest, library: dict[str, dict]) -> dict[str, Any]:
    """Everything one take sends, worked out once: the style, lyrics, influences and settings.
    `library` is the influence library (id -> record with "file")."""
    style = compose_style(r)
    if r.sung:
        lyrics = tidy_lyrics(r.lyrics)
        if sung_words(lyrics) < 4:
            raise SongError("A sung song needs lyrics. Write some, or let the writer draft them.")
    else:
        lyrics = instrumental_lyrics(r.lyrics, r.length)
    influences: list[dict] = []
    for c in r.influences:
        rec = library.get(c.id)
        if not rec:
            raise SongError(f"The influence '{c.id}' isn't in the library.")
        if "yue2" not in rec.get("models", []):
            raise SongError(f"'{rec['name']}' doesn't work with YuE2.")
        if c.strength > 0:
            influences.append({"id": c.id, "name": rec["name"], "file": rec["file"], "strength": c.strength})
    if not r.sung:
        influences.append({"id": "instrumental", "name": "Instrumental", "file": INSTRUMENTAL_INFLUENCE, "strength": 1.0})
    # an influence trained with a trigger word hears it at the start of every caption: the style leads with it too
    triggers = [library[i["id"]]["trigger"] for i in influences if library.get(i["id"], {}).get("trigger")]
    if triggers and not (r.style_override and r.style_override.strip()):
        style = ", ".join([*dict.fromkeys(triggers), style])
    plan = r.cover.keep if r.cover else r.plan
    if plan == "free" and influences:
        raise SongError("Influences need YuE2 to sketch the song first: choose “Melody and chords” or “Melody only”.")
    e = r.engine
    if r.cover:
        if not r.cover.reference:
            raise SongError("Choose the song to cover first.")
        sketch: dict | None = {"reference": r.cover.reference, "mode": plan}
    else:
        sketch = None if plan == "free" else {k: v for k, v in {
            "style": style, "lyrics": lyrics, "plan": plan,
            "plan_temperature": e.plan_temperature, "plan_top_p": e.plan_top_p, "plan_top_k": e.plan_top_k,
            "plan_repetition_penalty": e.plan_repetition_penalty, "plan_penalty_window": e.plan_penalty_window,
            "plan_max_tokens": e.plan_max_tokens}.items() if v is not None}
    # a cover runs as long as the song it covers (plus room to end), unless the engine room says otherwise
    cover_seconds = min(900.0, float(r.cover.seconds) + 20.0) if r.cover and r.cover.seconds else None
    sing = {k: v for k, v in {
        "style": style, "lyrics": lyrics, "plan": "full" if plan == "free" else plan,
        "seconds": e.seconds or cover_seconds or LENGTH_SECONDS.get(r.length, 270.0),
        "temperature": r.creativity, "repetition_penalty": r.repetition,
        "top_p": e.top_p, "top_k": e.top_k, "guidance": e.guidance, "steps": e.steps}.items() if v is not None}
    return {"style": style, "lyrics": lyrics, "influences": influences, "sketch": sketch, "sing": sing,
            "plan": plan, "sung": r.sung}


def seeds(r: SongRequest) -> list[int]:
    """One seed per take: the chosen seed and the ones after it, or fresh random ones."""
    if r.seed is not None:
        return [(r.seed + i) % (2**63) for i in range(r.takes)]
    return [random.randrange(0, 2**53) for _ in range(r.takes)]


# ---- the plan guard (ported from the old app's workers/yue2_plan_guard.py) ------------------

SUNG = {"verse", "chorus", "pre-chorus", "prechorus", "bridge", "hook", "rap", "refrain", "post-chorus"}
_LYRIC_TAG = re.compile(r"^\s*\[([^\]]+)\]\s*$", re.M)


def _kind(marker: str) -> str:
    name = marker.lstrip("%").strip().lower()
    return re.sub(r"[\s_]+", "-", re.sub(r"\d+$", "", name).strip())


def lyric_sections(lyrics: str) -> list[str]:
    kinds = [_kind(t) for t in _LYRIC_TAG.findall(lyrics or "")]
    return [k for k in kinds if k in SUNG or not k.startswith(("inst", "intro", "outro", "solo", "break"))]


def guard(abc: str | None, lyrics: str, truncated: bool = False) -> tuple[str | None, dict]:
    """A sketch fitted to the lyrics, or None when it already fits. An influence can make YuE2 plan a
    whole song's worth of sections for a few lines; a plan that overran keeps at most an intro, the
    sung sections the lyrics have, and an outro."""
    if not abc:
        return None, {}
    header: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    for line in abc.splitlines():
        if line.startswith("%"):
            sections.append((line, []))
        elif sections:
            sections[-1][1].append(line)
        else:
            header.append(line)
    wanted = len(lyric_sections(lyrics))
    before = [_kind(m) or "?" for m, _ in sections]
    if not truncated and (wanted == 0 or sum(1 for k in before if k in SUNG) <= wanted):
        return None, {}
    parts = sections[:-1] if truncated and sections else list(sections)
    kept: list[tuple[str, list[str]]] = []
    count = lead = tail = 0
    for marker, lines in parts:
        k = _kind(marker)
        if k in SUNG:
            if count >= max(wanted, 1):
                if tail or not wanted:
                    break
                continue
            kept.append((marker, lines))
            count += 1
        elif count == 0:
            if lead == 0:
                kept.append((marker, lines))
            lead += 1
        elif count < wanted:
            kept.append((marker, lines))
        elif tail == 0:
            kept.append((marker, lines))
            tail += 1
            break
    if not kept:
        return None, {}
    text = "\n".join(header + [ln for m, ls in kept for ln in [m, *ls]]).rstrip() + "\n"
    report = {"planned": before, "kept": [_kind(m) or "?" for m, _ in kept], "lyricSections": wanted}
    return (text if text.strip() != abc.strip() else None), report
