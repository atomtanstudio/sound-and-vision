"""ElevenLabs Music, as a fourth song model beside YuE2, ACE-Step 1.5 and MiniMax Music 3, made on one of the person's
MCP servers that runs it: Mitte's `music` node, ElevenLabs' model under their Mitte plan. No ElevenLabs key: the
server has it.

The app calls the server itself (no language model in between): `run_node` with the song, then `get_task` until the
run has started and `get_node_run` until it's done, then the audio is fetched from the address the run gives
(public https only, sv/net.py) and becomes a take like any other (the FLAC, an AAC copy, the waveform).

What's sent, from the song:
- sung, with lyrics: a composition plan (ElevenLabs' music_v1 form): the style as global styles, and each lyric
  section as a section with its lines and a length worked out from its words, scaled to the length chosen;
- instrumental: the style as the prompt, instrumental forced, and the length in minutes.
Everything else the node takes (its audio quality, keeping each section to its length, …) is offered as it says,
from its own input schema, under the model on the song page."""

from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from .. import media, net
from ..jobs import Context, JobError
from ..mcp import MCPError, Session
from .yue2 import LENGTH_SECONDS, SongError, SongRequest, sung_words, tidy_lyrics

if TYPE_CHECKING:
    from ..mcp import Servers

NODE = "music"
NEEDS = {"get_node", "run_node", "get_task", "get_node_run"}  # a server that runs nodes the way Mitte does
MAPPED = {"prompt", "composition_plan", "force_instrumental", "music_length_min"}  # filled in from the song
SECTION_MS = (3000, 120000)
LINES, LINE_CHARS = 30, 200
VOICE_WORDS = {"female": "female vocals", "male": "male vocals", "duet": "male and female duet vocals"}
FOLLOW_EVERY, MOST_SECONDS = 5.0, 900.0
# the node's own settings in plain words (one it adds later still shows, in its own words)
PLAIN = {"output_format": ("Audio quality", "Higher sounds fuller and makes a larger file."),
         "respect_sections_durations": ("Keep each section to its length",
                                        "On: each part lasts as planned. Off: ElevenLabs may stretch or shorten parts, "
                                        "keeping the total.")}
_offers: dict[str, tuple[float, dict | None]] = {}  # server id → (when, its music node or None), kept ten minutes


def model_id(sid: str) -> str:
    return f"mcp:{sid}:{NODE}"


def server_of(model: str) -> str | None:
    m = re.fullmatch(r"mcp:([a-z0-9]+):" + NODE, model or "")
    return m.group(1) if m else None


def _first(obj: Any, *keys: str) -> Any:
    """The first value under any of `keys`, anywhere inside a nested answer."""
    if isinstance(obj, dict):
        for k in keys:
            if obj.get(k) not in (None, "", []):
                return obj[k]
        for v in obj.values():
            if (got := _first(v, *keys)) is not None:
                return got
    elif isinstance(obj, list):
        for v in obj:
            if (got := _first(v, *keys)) is not None:
                return got
    return None


async def _call(mcp: "Servers", sid: str, tool: str, args: dict, timeout: float = 60) -> dict:
    """One tool call on the server: its structured answer (or its text, as {"text": …})."""
    rec = mcp.get(sid)
    if rec is None:
        raise JobError("That MCP server isn't in Settings any more.")
    async with Session(rec["url"], await mcp._headers(rec), timeout=timeout, transport=mcp.transport) as s:
        r = await s.call("tools/call", {"name": tool, "arguments": args})
    if r.get("isError"):
        text = " ".join(c.get("text", "") for c in r.get("content") or [] if isinstance(c, dict))
        raise JobError(f"{rec['name']} said: {' '.join(text.split())[:300] or 'it failed'}")
    return r.get("structuredContent") or {"text": " ".join(c.get("text", "") for c in r.get("content") or [] if isinstance(c, dict))}


async def _node(mcp: "Servers", sid: str) -> dict | None:
    """The server's ElevenLabs music node (its name, description, input schema), or None."""
    when, node = _offers.get(sid, (0.0, None))
    if time.monotonic() - when < 600:
        return node
    try:
        got = await _call(mcp, sid, "get_node", {"slug": NODE}, timeout=30)
        data = got.get("result", got)
        data = data.get("data", data) if isinstance(data, dict) else {}
        node = data if "eleven" in f"{data.get('name', '')} {data.get('desc', '')} {data.get('assistant_instructions', '')}".lower() else None
    except (MCPError, JobError, httpx.HTTPError):
        node = None
    _offers[sid] = (time.monotonic(), node)
    return node


def fields(schema: dict) -> list[dict]:
    """The node's own settings beyond what the song fills in, as the song page shows them: a choice, a switch or a
    number, each with its default and its words."""
    out = []
    for key, p in (schema.get("properties") or {}).items():
        if key in MAPPED or not isinstance(p, dict):
            continue
        label, help_ = PLAIN.get(key, (key.replace("_", " ").capitalize(), " ".join(str(p.get("description") or "").split())[:200]))
        base = {"key": key, "label": label, "help": help_, "default": p.get("default")}
        types = p.get("type") if isinstance(p.get("type"), list) else [p.get("type")]
        if p.get("enum"):
            values = [v for v in p["enum"] if v is not None][:40]
            out.append({**base, "type": "choice", "values": values, "labels": {str(v): value_label(v) for v in values}})
        elif "boolean" in types:
            out.append({**base, "type": "switch"})
        elif ("number" in types or "integer" in types) and "minimum" in p and "maximum" in p:
            out.append({**base, "type": "number", "min": p["minimum"], "max": p["maximum"], "integer": "integer" in types})
    return out


def value_label(v: Any) -> str:
    """A value in plain words: "mp3_44100_128" is "MP3 · 128 kbps"."""
    m = re.fullmatch(r"(mp3|opus|pcm|ulaw|alaw)_(\d+)(?:_(\d+))?", str(v))
    if m:
        kind, rate, kbps = m.groups()
        return f"{kind.upper()} · {kbps} kbps" if kbps else f"{kind.upper()} · {int(rate) / 1000:g} kHz"
    return str(v)


async def offered(mcp: "Servers") -> list[dict]:
    """The ElevenLabs Music the person's MCP servers run, as song models: {id, name, via, paid, fields, maxSeconds}."""
    out = []
    for s in mcp.listed():
        tools = {t.get("name") for t in s.get("tools") or []}
        if not s.get("ok") or not NEEDS <= tools:
            continue
        node = await _node(mcp, s["id"])
        if node:
            out.append({"id": model_id(s["id"]), "name": "ElevenLabs Music", "via": s["name"], "paid": bool(s.get("paid")),
                        "paidOnly": bool(node.get("is_paid_only")), "fields": fields(node.get("input_schema") or {}),
                        "maxSeconds": 600, "note": f"ElevenLabs' music model, on your {s['name']} account."})
    return out


# ---- the song, in ElevenLabs' terms -----------------------------------------------------------------------------

def styles(r: SongRequest, words: list[str] | None = None) -> list[str]:
    """The song's sound as short style phrases (its genres, moods, instruments, voice, language, tempo and key), and
    `words`: its influences, described (ElevenLabs can't load one)."""
    if r.style_override and r.style_override.strip():
        return [x.strip() for x in r.style_override.split(",") if x.strip()][:12]
    out = [g.strip() for g in r.genres if g.strip()] + [m.strip() for m in r.moods if m.strip()]
    out += [x.strip() for x in r.instruments.split(",") if x.strip()]
    out += [x.strip() for x in r.extra.split(",") if x.strip()]
    if r.sung:
        out += [VOICE_WORDS.get(r.voice or "", "vocals"), f"sung in {r.language}"]
    else:
        out.append("instrumental")
    if r.tempo:
        out.append(f"{r.tempo} BPM")
    if r.key:
        out.append(f"in {r.key}")
    out += list(words or [])
    if not out:
        raise SongError("Give the song a sound: at least a genre, a mood or some instruments.")
    return list(dict.fromkeys(out))[:20]


def plan(lyrics: str, global_styles: list[str], seconds: float) -> dict:
    """A composition plan from the lyrics: a section for each [Tag], its lines, and a length from its words (about
    two words a second, a breath around them), all scaled together to `seconds`."""
    sections: list[dict] = []
    cur: dict | None = None
    counts: dict[str, int] = {}
    for raw in lyrics.splitlines():
        line = raw.strip()
        tag = re.fullmatch(r"\[([^\]]+)\]", line)
        if tag:
            kind = tag.group(1).strip().title()
            counts[kind] = counts.get(kind, 0) + 1
            cur = {"section_name": kind if counts[kind] == 1 else f"{kind} {counts[kind]}", "positive_local_styles": [],
                   "negative_local_styles": [], "lines": []}
            sections.append(cur)
        elif line:
            if cur is None:
                cur = {"section_name": "Verse", "positive_local_styles": [], "negative_local_styles": [], "lines": []}
                sections.append(cur)
            if len(cur["lines"]) < LINES:
                cur["lines"].append(line[:LINE_CHARS])
    sections = [s for s in sections if s["lines"] or re.match(r"(intro|outro|instrumental|interlude|solo|break)", s["section_name"], re.I)]
    if not sections:
        raise SongError("A sung song needs lyrics. Write some, or let the writer draft them.")
    want = [max(6.0, sum(len(l.split()) for l in s["lines"]) / 2.0 + 3.0) if s["lines"] else 10.0 for s in sections]
    scale = seconds / sum(want) if seconds else 1.0
    for s, w in zip(sections, want):
        s["duration_ms"] = int(min(SECTION_MS[1], max(SECTION_MS[0], w * scale * 1000)) // 100 * 100)
    return {"positive_global_styles": global_styles, "negative_global_styles": [], "sections": sections}


def prepare(r: SongRequest, sid: str, options: dict | None, known: list[dict] | None = None,
            library: dict[str, dict] | None = None) -> dict[str, Any]:
    """Everything one take sends (the take's "What the model got"). `options`: the node's own settings, as chosen
    (only the ones it lists, `known`, and only values they allow). `library`: the influences, described in words."""
    from ..influences import sort_out
    _, words = sort_out(r.influences, library or {}, "eleven")
    tags = styles(r, words)
    seconds = float(r.engine.seconds or LENGTH_SECONDS.get(r.length, 210.0))
    seconds = min(600.0, max(10.0, seconds))
    prompt = (" ".join(r.style_override.split()) if r.style_override and r.style_override.strip() else
              "A " + ", ".join(tags) + (" song." if r.sung else " piece."))
    if r.sung:
        lyrics = tidy_lyrics(r.lyrics)
        if sung_words(lyrics) < 4:
            raise SongError("A sung song needs lyrics. Write some, or let the writer draft them.")
        # (only one of a prompt or a plan may be given, but Mitte's node requires the prompt field: it goes empty, and the
        # style rides in the plan's global styles)
        # (and its default length, 1 minute, would go with it: the plan's sections set the length, so it's sent empty)
        inp: dict[str, Any] = {"prompt": "", "force_instrumental": False, "music_length_min": None,
                               "composition_plan": plan(lyrics, tags, seconds)}
    else:
        lyrics = "[Instrumental]"
        inp = {"prompt": prompt[:2000], "force_instrumental": True, "music_length_min": round(seconds / 60, 2)}
    for f in known or []:
        v = (options or {}).get(f["key"])
        if v is None:
            continue
        if f["type"] == "choice" and v in f["values"]:
            inp[f["key"]] = v
        elif f["type"] == "switch" and isinstance(v, bool):
            inp[f["key"]] = v
        elif f["type"] == "number" and isinstance(v, (int, float)) and f["min"] <= v <= f["max"]:
            inp[f["key"]] = int(v) if f.get("integer") else v
    return {"model": "eleven", "server": sid, "style": prompt, "lyrics": lyrics, "input": inp, "params": inp,
            "influences": [], "sung": r.sung, "plan": None, "sketch": None}


# ---- the take ---------------------------------------------------------------------------------------------------

async def make(mcp: "Servers", sid: str, inp: dict, progress=lambda f, m: None) -> tuple[str, str]:
    """Run the node and follow it to the end: (the audio's address, its content type)."""
    started = await _call(mcp, sid, "run_node", {"slug": NODE, "input": inp})
    task = _first(started, "task_id", "queue_task_id") or _first(started, "id")
    if not task:
        raise JobError("The server didn't say which run it started.")
    began = time.monotonic()
    run = None
    while run is None:
        await asyncio.sleep(FOLLOW_EVERY)
        t = await _call(mcp, sid, "get_task", {"task_id": str(task)})
        if err := _first(t, "error"):  # refused (not enough credits, a plan that doesn't include it, …)
            raise JobError(f"It was refused: {str(err)[:300]}")
        run = _first(t, "node_run_id")
        progress(0.1, "Waiting for ElevenLabs to start")
        if time.monotonic() - began > MOST_SECONDS:
            raise JobError("ElevenLabs didn't start the song in time.")
    while True:
        await asyncio.sleep(FOLLOW_EVERY)
        r = await _call(mcp, sid, "get_node_run", {"id": str(run)})
        data = r.get("result", r)
        data = data.get("data", data) if isinstance(data, dict) else {}
        status = str(data.get("status") or "").lower()
        if status in ("error", "stopped", "failed"):
            raise JobError(f"ElevenLabs didn't make it: {str(data.get('error') or status)[:300]}")
        if status == "done":
            for a in _all(r, "assets") + _all(r, "links"):
                for x in a if isinstance(a, list) else [a]:
                    d = x.get("data", x) if isinstance(x, dict) else {}
                    url = d.get("url") or d.get("src")
                    if isinstance(url, str) and url.startswith("https://") and str(d.get("content_type", "audio")).startswith("audio"):
                        return url, str(d.get("content_type") or "audio/mpeg")
            raise JobError("ElevenLabs finished, but no audio came back.")
        progress(min(0.9, 0.2 + (time.monotonic() - began) / 400), "ElevenLabs is making the song")
        if time.monotonic() - began > MOST_SECONDS:
            raise JobError("ElevenLabs took too long to make the song.")


def _all(obj: Any, key: str) -> list:
    """Every value under `key`, anywhere inside a nested answer."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                out.append(v)
            out += _all(v, key)
    elif isinstance(obj, list):
        for v in obj:
            out += _all(v, key)
    return out


def register(sched, mcp: "Servers") -> None:
    """The job that makes an ElevenLabs take (network lane: nothing runs on our GPU)."""
    from .takes import _publish_take

    async def run(ctx: Context) -> dict:
        tid = ctx.job["takeId"]
        take = ctx.store.take(tid)
        if take is None:
            raise JobError("That take was deleted.")
        sent = take["sent"]
        folder = ctx.cfg.projects / take["projectId"] / "takes" / tid
        folder.mkdir(parents=True, exist_ok=True)
        ctx.update(stage="sing", message="Sending it to ElevenLabs", progress=0.05)
        _publish_take(ctx, tid, "singing")
        url, kind = await make(mcp, sent["server"], sent["input"],
                               lambda f, m: ctx.update(stage="sing", message=m, progress=f))
        ctx.update(stage="finish", message="Getting it ready to play", progress=0.94)
        _publish_take(ctx, tid, "finishing")
        try:
            res = await net.get(url, most=200_000_000)
        except (net.UnsafeURL, httpx.HTTPError) as exc:
            raise JobError(f"The song couldn't be fetched: {exc}") from None
        got = folder / ("got.wav" if "wav" in kind else "got.mp3")
        got.write_bytes(res.content)
        ffmpeg = ctx.cfg.ffmpeg
        flac = await asyncio.to_thread(media.to_flac, got, folder / "song.flac", ffmpeg)
        got.unlink(missing_ok=True)
        await asyncio.to_thread(media.to_m4a, flac, folder / "song.m4a", ffmpeg)
        await asyncio.to_thread(media.peaks, flac, folder / "peaks.json", ffmpeg)
        seconds = await asyncio.to_thread(media.duration, flac, ffmpeg)
        rel = lambda p: str(Path("takes") / tid / p)  # noqa: E731
        _publish_take(ctx, tid, "ready", duration=seconds, truncated=False, error=None,
                      files={"flac": rel("song.flac"), "audio": rel("song.m4a"), "peaks": rel("peaks.json")})
        return {"takeId": tid, "duration": seconds}

    from .takes import _after
    run.after = _after  # type: ignore[attr-defined]
    sched.register("song.eleven", "net", run)
