"""Songs from outside the app.

- Your own finished song (made in Suno, or anywhere): uploaded with its lyrics or an LRC if you have them, it becomes a
  song in the library with one ready take, already chosen, and the usual listening (stems, beats, sections, words;
  Whisper hears the words when there are none). From there it's like any song: a living cover, a lyric video, a
  music video.
- A song to cover (YuE2 "cover a song"): uploaded, or one of your songs, it's kept on the song as `reference`; each
  cover take writes its melody down with SheetSage2 and sings your lyrics to it (music/takes.py).
"""

from __future__ import annotations

import asyncio
import re
import shutil
import uuid
from pathlib import Path

from . import media
from .jobs import Context, JobError
from .songs import lyrics_text, parse_lyrics, sid

AUDIO = (".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".aif", ".aiff", ".webm", ".mp4")
IMAGES = (".png", ".jpg", ".jpeg", ".webp")
MAX_BYTES = 250_000_000
_STAMP = re.compile(r"\[(\d{1,3}):(\d{1,2}(?:[.:]\d{1,3})?)\]")
_META = re.compile(r"^\[[a-z]+:.*\]$", re.I)


def parse_lrc(text: str) -> tuple[list[dict], str]:
    """An LRC file: its timed lines ([{text, start, end}], in time order) and its words as a lyric sheet (a new part
    wherever the singing rests for a while). Lines that are only tags ([ar:…], [ti:…]) are skipped."""
    timed: list[tuple[float, str]] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or _META.match(line):
            continue
        stamps = _STAMP.findall(line)
        words = _STAMP.sub("", line).strip()
        words = re.sub(r"<\d{1,3}:\d{1,2}(?:[.:]\d{1,3})?>", "", words).strip()  # enhanced LRC's word stamps
        for m, s in stamps:
            timed.append((int(m) * 60 + float(s.replace(":", ".")), words))
    timed.sort(key=lambda x: x[0])
    lines = []
    for i, (t, words) in enumerate(timed):
        if not words:
            continue
        nxt = next((u for u, _ in timed[i + 1:] if u > t), t + 6.0)
        lines.append({"text": words, "start": round(t, 2), "end": round(min(nxt, t + 8.0), 2)})
    sections: list[list[str]] = []
    last = None
    for ln in lines:
        if last is None or ln["start"] - last > 4.0:
            sections.append([])
        sections[-1].append(ln["text"])
        last = ln["end"]
    sheet = "\n\n".join("[Verse]\n" + "\n".join(s) for s in sections)
    return lines, sheet


def safe_suffix(name: str, allowed: tuple[str, ...]) -> str | None:
    suffix = Path(name or "").suffix.lower()
    return suffix if suffix in allowed else None


class Imports:
    def __init__(self, app):
        self.app = app
        self.cfg = app.cfg

    # ---- your own finished song -------------------------------------------------------------
    def song(self, src: Path, filename: str, title: str = "", artist: str = "", lyrics: str = "", lrc: str = "",
             cover: Path | None = None, language: str = "") -> dict:
        """A new song from an uploaded file; the import job does the rest. `src` (and `cover`) are moved in."""
        timed, sheet = parse_lrc(lrc) if lrc.strip() else ([], "")
        words = lyrics.strip() or sheet
        sections = parse_lyrics(words) if words else []
        name = " ".join((title or "").split())[:120]
        doc = {"sung": True, "sections": sections, "idea": "", "genres": [], "moods": [],
               "source": {"kind": "upload", "file": Path(filename).name[:200], **({"artist": artist[:120]} if artist else {})},
               **({"language": language} if language else {})}
        p = self.app.store.create_project(name or Path(filename).stem[:120] or "My song", doc)
        sent = {"upload": {"file": Path(filename).name[:200]}, "lyrics": lyrics_text(sections) if sections else "",
                "sung": True if sections else None, "lrc": timed or None, "style": "", "influences": [],
                **({"language": language} if language else {})}
        take = self.app.store.create_take(p["id"], "upload", {"seed": 0, "sent": sent, "request": {}, "label": "Your song"})
        folder = self.cfg.projects / p["id"] / "takes" / take["id"]
        folder.mkdir(parents=True, exist_ok=True)
        kept = folder / f"original{safe_suffix(filename, AUDIO) or '.audio'}"
        shutil.move(str(src), kept)
        art = None
        if cover:
            art = folder / f"cover-upload{cover.suffix.lower()}"
            shutil.move(str(cover), art)
        job = self.app.sched.submit("song.import", {"message": "Getting your song ready", "original": kept.name,
                                                    "titled": bool(name), "artist": artist[:120],
                                                    "cover": art.name if art else None}, p["id"], take["id"])
        take = self.app.store.update_take(take["id"], jobId=job["id"])
        self.app.hub.publish("project", p)
        self.app.hub.publish("take", take)
        return {"project": p, "take": take, "job": job}

    async def run(self, ctx: Context) -> dict:
        """The upload as a take: FLAC master, AAC to play, peaks; its title, artist and art from the file's tags when
        none were given; chosen as the song's take; then the listening."""
        pid, tid = ctx.job["projectId"], ctx.job["takeId"]
        folder = self.cfg.projects / pid / "takes" / tid
        original = folder / ctx.job["original"]
        ff = self.cfg.ffmpeg
        ctx.store.update_take(tid, "finishing")
        ctx.update(stage="convert", message="Reading your song", progress=0.1)
        try:
            await asyncio.to_thread(media.to_flac, original, folder / "song.flac", ff)
        except Exception:  # noqa: BLE001  ffmpeg couldn't read it
            raise JobError("That file couldn't be read as audio. Try an MP3, WAV, FLAC or M4A.") from None
        await asyncio.to_thread(media.to_m4a, folder / "song.flac", folder / "song.m4a", ff)
        await asyncio.to_thread(media.peaks, folder / "song.flac", folder / "peaks.json", ff)
        seconds = await asyncio.to_thread(media.duration, folder / "song.flac", ff)
        if seconds < 5:
            raise JobError("That's too short to be a song (under five seconds).")
        tags = await asyncio.to_thread(media.tags, original, ff)
        ctx.update(stage="tags", message="Reading its title and artwork", progress=0.6)
        p = ctx.store.project(pid) or {}
        changes: dict = {}
        if not ctx.job.get("titled") and tags.get("title"):
            changes["title"] = tags["title"][:120]
        source = dict(p.get("source") or {})
        artist = ctx.job.get("artist") or tags.get("artist") or tags.get("album_artist") or ""
        if artist:
            source["artist"] = artist[:120]
        source["tags"] = {k: tags[k][:200] for k in ("album", "date", "genre", "bpm", "tbpm") if tags.get(k)}
        changes["source"] = source
        if tags.get("genre") and not p.get("genres"):
            changes["genres"] = [g.strip().lower() for g in re.split(r"[;,/]", tags["genre"]) if g.strip()][:3]
        lyrics_tag = tags.get("lyrics") or tags.get("unsyncedlyrics") or ""
        if lyrics_tag.strip() and not any((s.get("text") or "").strip() for s in p.get("sections") or []):
            # the file came with its words: they're the lyrics (and the listening places them)
            sections = parse_lyrics(lyrics_tag)
            changes.update(sections=sections, sung=True)
            t = ctx.store.take(tid)
            ctx.store.update_take(tid, sent={**t["sent"], "lyrics": lyrics_text(sections), "sung": True})
        rel = lambda name: str(Path("takes") / tid / name)  # noqa: E731
        take = ctx.store.update_take(tid, "ready", duration=seconds, truncated=False, error=None,
                                     files={"flac": rel("song.flac"), "audio": rel("song.m4a"), "peaks": rel("peaks.json"),
                                            "original": rel(original.name)})
        ctx.take_changed(take)
        p = ctx.store.patch_project(pid, masterTake=tid, **changes)
        ctx.hub.publish("project", p)

        art = folder / ctx.job["cover"] if ctx.job.get("cover") else None
        if not art or not art.exists():
            art = await asyncio.to_thread(media.artwork, original, folder / "cover-embedded.png", ff)
        if art and not p.get("cover"):
            staged = self.cfg.data / "incoming" / f"cover-{uuid.uuid4().hex[:8]}{art.suffix}"
            staged.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(art, staged)
            self.app.covers.upload(pid, staged, False)
        ctx.store.update_take(tid, analysis={"status": "queued"})
        ctx.take_changed(ctx.store.take(tid))
        self.app.sched.submit("analysis", {"message": "Waiting its turn"}, pid, tid)
        return {"takeId": tid, "duration": seconds, "title": p.get("title")}

    async def after(self, ctx: Context, job: dict) -> None:
        if job["status"] in ("failed", "cancelled"):
            t = ctx.store.take(job["takeId"])
            if t and t["status"] != "ready":
                ctx.take_changed(ctx.store.update_take(t["id"], "failed" if job["status"] == "failed" else "stopped",
                                                       error=job.get("message")))

    # ---- a song to cover -------------------------------------------------------------------------------
    def reference(self, pid: str, src: Path, filename: str) -> dict:
        """An uploaded song to cover: kept on this song as its reference (FLAC), replacing the one before."""
        p = self.app.store.project(pid)
        if p is None:
            raise JobError("That song isn't here any more.")
        folder = self.cfg.projects / pid / "reference"
        folder.mkdir(parents=True, exist_ok=True)
        rid = uuid.uuid4().hex[:8]
        dest = folder / f"ref-{rid}.flac"
        try:
            media.to_flac(src, dest, self.cfg.ffmpeg)
        except Exception:  # noqa: BLE001
            raise JobError("That file couldn't be read as audio. Try an MP3, WAV, FLAC or M4A.") from None
        finally:
            src.unlink(missing_ok=True)
        return self._keep(p, dest, {"name": Path(filename).name[:200], "from": "upload"})

    def reference_from(self, pid: str, other: str) -> dict:
        """One of your songs (its chosen take) as the song to cover."""
        p = self.app.store.project(pid)
        q = self.app.store.project(other)
        if p is None or q is None:
            raise JobError("That song isn't here any more.")
        take = self.app.store.take(q.get("masterTake") or "")
        if not take or take.get("status") != "ready":
            raise JobError(f"“{q['title']}” has no chosen take to cover yet.")
        folder = self.cfg.projects / pid / "reference"
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / f"ref-{uuid.uuid4().hex[:8]}.flac"
        shutil.copyfile(self.cfg.projects / other / take["files"]["flac"], dest)
        return self._keep(p, dest, {"name": q["title"], "from": "song", "projectId": other, "takeId": take["id"],
                                    "hasWords": any((s.get("text") or "").strip() for s in q.get("sections") or [])})

    def _keep(self, p: dict, dest: Path, about: dict) -> dict:
        root = self.cfg.projects / p["id"]
        old = (p.get("reference") or {}).get("file")
        seconds = media.duration(dest, self.cfg.ffmpeg)
        if seconds < 10:
            dest.unlink(missing_ok=True)
            raise JobError("That's too short to cover (under ten seconds).")
        ref = {**about, "file": str(dest.relative_to(root)), "seconds": seconds, "id": dest.stem}
        p = self.app.store.patch_project(p["id"], reference=ref)
        if old and old != ref["file"]:
            (root / old).unlink(missing_ok=True)
            for abc in (root / "reference").glob(f"{Path(old).stem}-*.abc"):
                abc.unlink(missing_ok=True)
        self.app.hub.publish("project", p)
        return p

    def forget_reference(self, pid: str) -> dict:
        p = self.app.store.project(pid)
        if p is None:
            raise JobError("That song isn't here any more.")
        ref = p.get("reference") or {}
        if ref.get("file"):
            (self.cfg.projects / pid / ref["file"]).unlink(missing_ok=True)
        p = self.app.store.patch_project(pid, reference=None)
        self.app.hub.publish("project", p)
        return p

    def words_of_reference(self, pid: str) -> dict:
        """The covered song's own words, onto this song's lyric sheet (when the reference is one of your songs)."""
        p = self.app.store.project(pid)
        ref = (p or {}).get("reference") or {}
        q = self.app.store.project(ref.get("projectId") or "")
        if not p or not q:
            raise JobError("Only one of your own songs brings its words along.")
        sections = [{**s, "id": sid()} for s in q.get("sections") or [] if (s.get("text") or "").strip()]
        if not sections:
            raise JobError(f"“{q['title']}” has no words on its lyric sheet.")
        p = self.app.store.patch_project(pid, sections=sections, sung=True)
        self.app.hub.publish("project", p)
        return p


def register(sched, app) -> Imports:
    imp = Imports(app)

    async def run(ctx: Context) -> dict:
        return await imp.run(ctx)
    run.after = imp.after  # type: ignore[attr-defined]
    sched.register("song.import", "cpu", run)
    return imp
