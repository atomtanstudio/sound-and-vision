"""Share: clips of a song or a video, made for where they'll be posted (TikTok, Reels, Shorts, a square or 4:5 post,
16:9 for X and YouTube): the best moment, reframed for the shape, the title and logos in the house look, the sung
words as captions if wanted, and the sound levelled the way the platforms play it (−14 LUFS, −1 dBTP).

The clip's time is the song's time: every video starts with the song at 0, so a moment chosen on the song is the same
moment in any of its videos. The sound always comes from the song's master (the chosen take), never re-encoded twice.

The best moments: the song's loudness (measured once from the master, 4 frames a second) over windows of the clip's
length that start on a bar, with a little extra for starting where a section starts and for having the voice in it.
"""

from __future__ import annotations

import asyncio
import io
import json
import re
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import covers as covers_mod, look as look_mod
from .jobs import Context, JobError
from .paths import drop

PRESETS: dict[str, dict[str, Any]] = {
    "tiktok": {"name": "TikTok", "size": (1080, 1920), "most": 180, "best": 30},
    "reels": {"name": "Instagram Reels", "size": (1080, 1920), "most": 90, "best": 30},
    "shorts": {"name": "YouTube Shorts", "size": (1080, 1920), "most": 180, "best": 30},
    "portrait": {"name": "Portrait post (4:5)", "size": (1080, 1350), "most": 90, "best": 30},
    "square": {"name": "Square post", "size": (1080, 1080), "most": 90, "best": 30},
    "wide": {"name": "Wide (X, YouTube)", "size": (1920, 1080), "most": 140, "best": 45},
}
FRAMES = ("blur", "fill", "bars")
LOUD = {"I": -14.0, "TP": -1.0, "LRA": 11.0}  # what TikTok, Instagram and YouTube normalise to
RATE = 4  # loudness frames a second


def shape_of(W: int, H: int) -> str:
    r = W / H
    return "wide" if r > 1.3 else "square" if r > 0.95 else "portrait" if r > 0.7 else "story"


class Share:
    def __init__(self, app):
        self.app = app
        self.cfg = app.cfg

    # ---- the song and its moments ---------------------------------------------------------------------------------
    def _song(self, pid: str) -> tuple[dict, dict]:
        p = self.app.store.project(pid)
        if not p:
            raise JobError("That song isn't here any more.")
        take = self.app.store.take(p.get("masterTake") or "")
        if not take or take.get("status") != "ready":
            raise JobError("Choose the song's take first (“Use this one” on the song page).")
        return p, take

    def _analysis(self, pid: str, take: dict) -> dict:
        f = self.cfg.projects / pid / "takes" / take["id"] / "analysis" / "analysis.json"
        try:
            return json.loads(f.read_text())
        except (OSError, ValueError):
            return {}

    def loudness(self, pid: str, take: dict) -> np.ndarray:
        """The master's loudness in dB, RATE frames a second (measured once, kept beside the analysis)."""
        cache = self.cfg.projects / pid / "takes" / take["id"] / "loudness.json"
        if cache.exists():
            try:
                return np.asarray(json.loads(cache.read_text())["db"], np.float32)
            except (OSError, ValueError, KeyError):
                pass
        src = self.cfg.projects / pid / take["files"]["flac"]
        r = subprocess.run([self.cfg.ffmpeg, "-v", "error", "-i", str(src), "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                           capture_output=True, timeout=300)
        x = np.frombuffer(r.stdout, np.int16).astype(np.float32) / 32768
        n = 8000 // RATE
        frames = x[: len(x) // n * n].reshape(-1, n)
        db = 20 * np.log10(np.sqrt((frames ** 2).mean(1)) + 1e-6)
        cache.write_text(json.dumps({"rate": RATE, "db": [round(float(v), 2) for v in db]}))
        return db

    def moments(self, pid: str, seconds: float, upto: float | None = None, since: float | None = None) -> dict:
        """The three best stretches of `seconds` (or the whole song when it's shorter), each with why. `upto`: they
        end by then (a video shorter than the song: its opening); `since`: they start from then (a video of a part of
        the song). Times are the song's."""
        p, take = self._song(pid)
        total = float(take.get("duration") or 0)
        limit = min(total, float(upto)) if upto else total
        since = max(0.0, min(float(since or 0), limit - 1))
        seconds = max(5.0, min(float(seconds), limit - since))
        db = self.loudness(pid, take)
        if not len(db):  # the loudness couldn't be measured (no master here): the sections and the voice still choose
            db = np.zeros(int(total * RATE) + 1, np.float32)
        ana = self._analysis(pid, take)
        bars = [float(b["start"] if isinstance(b, dict) else b) for b in ana.get("bars") or []]
        starts = [b for b in bars if b >= since - 0.01 and b + seconds <= limit + 0.01] or [since]
        sections = ana.get("sections") or []
        lines = ana.get("lines") or []
        lo, hi = np.percentile(db, 10), np.percentile(db, 98)
        level = np.clip((db - lo) / max(1e-3, hi - lo), 0, 1)
        voice = np.zeros(len(db), bool)
        for ln in lines:
            voice[int(ln["start"] * RATE): int(ln["end"] * RATE) + 1] = True
        scored = []
        for s in starts:
            a, b = int(s * RATE), max(int(s * RATE) + 1, int((s + seconds) * RATE))
            score = float(level[a:b].mean())
            sec = next((x for x in sections if abs(float(x["start"]) - s) < 1.5), None)
            why = []
            if sec:
                score += 0.08
                why.append(f"starts with {sec.get('label') or 'a new part'}".replace("starts with Verse", "starts with verse")
                           .replace("starts with Chorus", "starts with the chorus"))
                if re.search(r"chorus|hook|drop", str(sec.get("label") or ""), re.I):
                    score += 0.12
            if lines:
                share = float(voice[a:b].mean())
                score += 0.1 * share
                if share > 0.5:
                    why.append("the voice all through" if share > 0.85 else "with the voice")
            scored.append((score, s, why))
        scored.sort(key=lambda t: -t[0])
        picks: list[dict] = []
        for score, s, why in scored:
            if all(abs(s - q["start"]) >= seconds * 0.75 for q in picks):
                peak = float(level[int(s * RATE): int((s + seconds) * RATE)].mean())
                picks.append({"start": round(s, 3), "end": round(min(total, s + seconds), 3),
                              "why": ", ".join(["the strongest stretch" if not picks else "strong" if peak > 0.6 else "calmer",
                                                *why]), "score": round(score, 3)})
            if len(picks) == 3:
                break
        step = max(1, -(-len(level) // 600))  # for the timeline: at most 600 points
        env = level[::step]
        return {"duration": total, "seconds": seconds, "moments": picks, "bars": bars,
                "sections": [{"label": x.get("label") or "", "start": x["start"], "end": x["end"]} for x in sections],
                "lines": [{"start": x["start"], "end": x["end"]} for x in lines],
                "level": [round(float(v), 3) for v in env], "levelRate": RATE / step}

    # ---- making a clip ------------------------------------------------------------------------------------------
    def start(self, pid: str, body: dict) -> dict:
        return self.app.sched.submit("share.clip", self._doc(pid, body), pid)

    def _doc(self, pid: str, body: dict) -> dict:
        p, take = self._song(pid)
        preset = body.get("preset") if body.get("preset") in PRESETS else "tiktok"
        total = float(take.get("duration") or 0)
        start = max(0.0, min(float(body.get("start") or 0), total - 1))
        end = max(start + 1, min(float(body.get("end") or start + 30), total, start + PRESETS[preset]["most"]))
        src = body.get("source") or {}
        offset = 0.0  # where in the song the video starts (a video of a part of it starts there)
        if src.get("type") == "video":
            rec = self.app.library.video(pid, str(src.get("kind")), str(src.get("vid")))[1]  # (it must exist)
            vlen = float(rec.get("seconds") or total)
            offset = float((rec.get("part") or {}).get("start") or 0)
            if not offset - 0.05 <= start < offset + vlen - 1:
                a, b = offset, offset + vlen
                raise JobError(f"That video covers {int(a // 60)}:{int(a % 60):02d} to {int(b // 60)}:{int(b % 60):02d} of the song: "
                               "choose a moment inside it.")
            start = max(start, offset)
            end = min(end, offset + vlen)
        elif not p.get("cover"):
            raise JobError("This song has no cover or video to show: make one first.")
        doc = {"preset": preset, "start": round(start, 3), "end": round(end, 3),
               "source": {"type": "video", "kind": src.get("kind"), "vid": src.get("vid")} if src.get("type") == "video" else {"type": "cover"},
               "frame": body.get("frame") if body.get("frame") in FRAMES else "blur",
               "focus": min(1.0, max(0.0, float(body.get("focus", 0.5)))),
               "words": bool(body.get("words")), "logos": bool(body.get("logos")), "captions": bool(body.get("captions")),
               "level": body.get("level", True) is not False, "offset": round(offset, 3), "message": "Waiting its turn"}
        return doc

    # ---- one frame of it, exactly as the clip will have it --------------------------------------------------------
    def _source(self, p: dict, doc: dict) -> tuple[Path, bool]:
        """The picture's file, and whether it's a still (the cover, moving in slowly)."""
        src = doc["source"]
        if src["type"] == "video":
            return self.app.library.video(p["id"], src["kind"], src["vid"])[2], False
        return self.cfg.projects / p["id"] / p["cover"]["art"], True

    def _layers(self, p: dict, take: dict, doc: dict, first: Path, folder: Path, start: float, dur: float,
                only_at: float | None = None) -> list[tuple[Path, float, float]]:
        """What's laid over the picture: the title and logos (one layer, all through) and each sung line while it's
        sung. `only_at`: just what shows at that moment of the clip (a preview)."""
        W, H = PRESETS[doc["preset"]]["size"]
        layers: list[tuple[Path, float, float]] = []
        if doc["words"] or doc["logos"]:
            look = look_mod.normalize(self.app.brand.house(), p.get("layout"))
            if not doc["words"]:
                look["title"]["show"] = look["artist"]["show"] = False
            if not doc["logos"]:
                for lg in look["logos"].values():
                    lg["show"] = False
            if H > W * 1.4 and look["title"]["place"] == "auto":  # a phone's buttons and captions cover its bottom
                look["title"].update(place="manual", anchor="tc", dx=0, dy=14)
            artist = covers_mod.artist_of(p, self.app.covers.house_artist())
            with Image.open(first) as im:
                layer, _ = look_mod.render(im.convert("RGB"), p.get("title") or "", artist, self.app.brand.logos(), look,
                                           self.app.brand.fonts)
            layer.save(folder / "look.png")
            layers.append((folder / "look.png", 0.0, dur))
        if doc["captions"]:
            for i, ln in enumerate(self._analysis(p["id"], take).get("lines") or []):
                a, b = float(ln["start"]) - start, float(ln["end"]) - start
                if b <= 0 or a >= dur or not str(ln.get("text") or "").strip():
                    continue
                a, b = max(0.0, a - 0.05), min(dur, b + 0.25)
                if only_at is not None and not a <= only_at <= b:
                    continue
                png = folder / f"cap-{i}.png"
                _caption(str(ln["text"]), W, H, self.app.brand.fonts, png)
                layers.append((png, a, b))
        return layers

    async def preview(self, pid: str, body: dict, at: float | None = None) -> bytes:
        """One frame of the clip as it will be made (at `at` seconds into the song; the moment's middle by default)."""
        doc = self._doc(pid, body)
        p, take = self._song(pid)
        W, H = PRESETS[doc["preset"]]["size"]
        start, end = doc["start"], doc["end"]
        at = min(end, max(start, at if at is not None else (start + end) / 2))
        src, still = self._source(p, doc)
        tmp = self.cfg.projects / pid / "clips" / f".preview-{uuid.uuid4().hex[:6]}"
        tmp.mkdir(parents=True)
        try:
            first = tmp / "first.png"
            frame = _reframe(W, H, doc["frame"], doc["focus"])
            await _run(self.cfg.ffmpeg, *([] if still else ["-ss", f"{at - doc['offset']:.3f}"]), "-i", str(src), "-frames:v", "1",
                       "-filter_complex", f"[0:v]{'scale=-2:2048,' if still else ''}{frame}[v]", "-map", "[v]", str(first))
            if not first.exists():
                raise JobError("No frame could be read there: choose a moment inside the video.")
            pic = Image.open(first).convert("RGBA")
            for png, _, _ in self._layers(p, take, doc, first, tmp, start, end - start, only_at=at - start):
                with Image.open(png) as layer:
                    pic = Image.alpha_composite(pic, layer.convert("RGBA"))
            pic.thumbnail((720, 720) if W >= H else (540, 960), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            pic.convert("RGB").save(buf, "JPEG", quality=86)
            return buf.getvalue()
        finally:
            for f in tmp.glob("*"):
                f.unlink(missing_ok=True)
            tmp.rmdir()

    def remove(self, pid: str, cid: str) -> dict:
        p = self.app.store.project(pid)
        clips = list((p or {}).get("clips") or [])
        c = next((c for c in clips if c["id"] == cid), None)
        if not p or not c:
            raise JobError("That clip isn't here any more.")
        for f in (c.get("file"), c.get("poster")):
            drop(self.cfg.projects / pid, f)
        return self.app.store.patch_project(pid, clips=[x for x in clips if x["id"] != cid])

    def all_clips(self) -> list[dict]:
        out = []
        for p in self.app.store.projects():
            for c in p.get("clips") or []:
                out.append({**c, "pid": p["id"], "title": p.get("title") or ""})
        return sorted(out, key=lambda c: -c.get("at", 0))

    async def job(self, ctx: Context) -> dict:
        pid, doc = ctx.job["projectId"], ctx.job
        p, take = self._song(pid)
        preset = PRESETS[doc["preset"]]
        W, H = preset["size"]
        start, end = float(doc["start"]), float(doc["end"])
        offset = float(doc.get("offset") or 0)  # the picture's own time is the song's minus this
        dur = end - start
        root = self.cfg.projects / pid
        folder = root / "clips"
        folder.mkdir(exist_ok=True)
        cid = uuid.uuid4().hex[:8]
        tmp = folder / f".{cid}"
        tmp.mkdir(exist_ok=True)
        try:
            # the picture: a video of the song, or its cover moving in slowly
            src, still = self._source(p, doc)
            fps = 30.0 if still else min(60.0, await asyncio.to_thread(_fps, src))
            vin = ["-i", str(src)] if still else ["-ss", f"{start - offset:.3f}", "-t", f"{dur:.3f}", "-i", str(src)]
            ctx.update(stage="frame", message="Setting the frame", progress=0.05)
            frame = _reframe(W, H, doc["frame"], doc["focus"])
            pre = (f"scale=-2:2400,zoompan=z='1+0.06*on/{max(1, int(dur * fps))}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                   f":d={int(dur * fps) + 1}:s=2048x2048:fps={fps:g}," if still else f"fps={fps:g},")
            # one frame of it, for the overlay's colours (the title's colours come from what's behind it)
            first = tmp / "first.png"
            await _run(self.cfg.ffmpeg, *([] if still else ["-ss", f"{start - offset + min(1.0, dur / 2):.3f}"]), "-i", str(src),
                       "-frames:v", "1", "-filter_complex", f"[0:v]{pre}{frame}[v]", "-map", "[v]", str(first))
            layers = self._layers(p, take, doc, first, tmp, start, dur)  # (png, from, to) in the clip's time

            # the sound: the master, levelled for the platforms (measured first, then set exactly)
            ain = ["-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(root / take["files"]["flac"])]
            fades = f"afade=t=in:st=0:d=0.15,afade=t=out:st={max(0.0, dur - 1.2):.3f}:d=1.2"
            audio = fades
            if doc.get("level", True):
                ctx.update(stage="level", message="Measuring the loudness", progress=0.1)
                m = await _measure(self.cfg.ffmpeg, ain, fades)
                if m:
                    audio = (f"{fades},loudnorm=I={LOUD['I']}:TP={LOUD['TP']}:LRA={LOUD['LRA']}:measured_I={m['input_i']}"
                             f":measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
                             f":offset={m['target_offset']}:linear=true")
            audio += ",aresample=48000"

            # the picture's chain: the frame, the layers (each only while it's on), a short fade in and out
            inputs = [*vin, *ain]
            for png, _, _ in layers:
                inputs += ["-i", str(png)]
            chain = f"[0:v]{pre}{frame},format=yuv420p,setsar=1[f0]"
            last = "f0"
            for k, (_, a, b) in enumerate(layers):
                chain += f";[{last}][{k + 2}:v]overlay=0:0:enable='between(t,{a:.3f},{b:.3f})'[f{k + 1}]"
                last = f"f{k + 1}"
            chain += f";[{last}]fade=t=in:st=0:d=0.25,fade=t=out:st={max(0.0, dur - 0.5):.3f}:d=0.5,format=yuv420p[vout]"
            chain += f";[1:a]{audio}[aout]"
            out = folder / f"clip-{cid}.mp4"
            ctx.update(stage="make", message=f"Making the {preset['name']} clip", progress=0.2)
            await _run(self.cfg.ffmpeg, *inputs, "-filter_complex", chain, "-map", "[vout]", "-map", "[aout]",
                       "-t", f"{dur:.3f}", "-r", f"{fps:g}", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                       "-maxrate", "16M", "-bufsize", "32M", "-profile:v", "high", "-pix_fmt", "yuv420p",
                       "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-movflags", "+faststart", str(out), timeout=3600)
            poster = folder / f"clip-{cid}.jpg"
            await _run(self.cfg.ffmpeg, "-ss", f"{dur * 0.4:.3f}", "-i", str(out), "-frames:v", "1", "-vf", "scale=720:-2",
                       str(poster))
        finally:
            for f in tmp.glob("*"):
                f.unlink(missing_ok=True)
            tmp.rmdir()
        rec = {"id": cid, "preset": doc["preset"], "presetName": preset["name"], "file": str(out.relative_to(root)),
               "poster": str(poster.relative_to(root)), "shape": shape_of(W, H), "size": [W, H], "start": start, "end": end,
               "seconds": round(dur, 3), "source": doc["source"], "frame": doc["frame"], "words": doc["words"],
               "logos": doc["logos"], "captions": doc["captions"], "level": doc.get("level", True),
               "bytes": out.stat().st_size, "at": time.time()}
        p = self.app.store.project(pid) or p
        p = self.app.store.patch_project(pid, clips=[rec, *(p.get("clips") or [])][:40])
        ctx.hub.publish("project", p)
        return {"clip": cid, "file": rec["file"]}


def _reframe(W: int, H: int, how: str, focus: float) -> str:
    """The filter that fits a picture into W x H: over a blurred copy of itself, filling (cropped, `focus` from left to
    right), or between black bars."""
    if how == "fill":
        return f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}:x='(iw-{W})*{focus:.3f}':y='(ih-{H})/2'"
    if how == "bars":
        return f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black"
    return (f"split[a][b];[a]scale={W // 4}:{H // 4}:force_original_aspect_ratio=increase,crop={W // 4}:{H // 4},"
            f"gblur=sigma=12,eq=brightness=-0.06:saturation=1.1,scale={W}:{H}[bg];"
            f"[b]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2")


def _caption(text: str, W: int, H: int, fonts: Path, out: Path) -> None:
    """One sung line, read from the timing file, set big and clear a little below the middle (above a phone's buttons)."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    px = round(min(W, H) * (0.062 if H > W else 0.05))
    font = look_mod.load_font(fonts, "Inter-Medium", px)
    words = " ".join(text.split())
    lines = look_mod.split(font, words, 0, W * 0.84)
    lead = px * 1.25
    top = H * (0.64 if H > W * 1.2 else 0.72) - lead * len(lines) / 2
    ink = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(ink)
    for i, ln in enumerate(lines):
        w = look_mod.tracked_width(font, ln, 0)
        d.text(((W - w) / 2, top + i * lead), ln, font=font, fill=255)
    shadow = ink.filter(ImageFilter.GaussianBlur(px * 0.18))
    layer.paste((0, 0, 0, 255), None, Image.eval(shadow, lambda v: min(255, int(v * 1.6))))
    layer.paste((0, 0, 0, 255), None, ink.filter(ImageFilter.MaxFilter(3)))  # a thin dark edge, so it reads on anything
    layer.paste((255, 255, 255, 255), None, ink)
    layer.save(out)


def _fps(f: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                        "-of", "csv=p=0", str(f)], capture_output=True, text=True, timeout=30)
    try:
        a, _, b = r.stdout.strip().partition("/")
        return float(a) / float(b or 1)
    except (ValueError, ZeroDivisionError):
        return 30.0


async def _run(ffmpeg: str, *args: str, timeout: float = 600) -> None:
    proc = await asyncio.create_subprocess_exec(ffmpeg, "-v", "error", "-y", *args, stdout=asyncio.subprocess.DEVNULL,
                                                stderr=asyncio.subprocess.PIPE)
    try:
        _, err = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError:
        proc.kill()
        raise JobError("Making the clip took too long.") from None
    if proc.returncode != 0:
        raise JobError("The clip couldn't be made.", err.decode(errors="replace")[-2000:])


async def _measure(ffmpeg: str, ain: list[str], fades: str) -> dict | None:
    """loudnorm's first pass: what the stretch measures, for the second pass to land exactly on the target."""
    proc = await asyncio.create_subprocess_exec(
        ffmpeg, "-hide_banner", "-nostats", *ain, "-af",
        f"{fades},loudnorm=I={LOUD['I']}:TP={LOUD['TP']}:LRA={LOUD['LRA']}:print_format=json", "-f", "null", "-",
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
    _, err = await proc.communicate()
    text = err.decode(errors="replace")
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", text, re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except ValueError:
        return None


def register(sched, app) -> Share:
    s = Share(app)

    async def run(ctx: Context) -> dict:
        return await s.job(ctx)
    sched.register("share.clip", "cpu", run)
    return s
