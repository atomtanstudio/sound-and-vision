"""The Influence Engine: from "this needs more of a sound" to a trained influence in the library.

    research (net)  a writer picks the artists and songs that define the sound (popular, with variety) and says why
                    that many; each song is looked for in your music (SV_MUSIC: a folder, or a network share)
    [the user looks over the plan, adds the audio for any song that isn't in their music, and starts it]
    gather   (net)  your music is looked through again, then every song with its audio (from your music, or added to
                    the run) becomes FLAC in the trainer's input folder
    listen   (gpu)  MOSS-Music writes each song's caption and lyrics sidecars (the lyrics never leave those files)
    train    (gpu)  FL YuE2's own trainer (not AI-Toolkit): its standard recipe plus the sound branch, 1,000 steps,
                    a checkpoint and a short preview every 100, followed live
    [the user listens to the previews and picks one]
    keep     (net)  the chosen checkpoint is converted for our ComfyUI and filed in the library as an influence

Each stage is a job; a finished stage queues the next. The run is one record (influence_runs) published on every
change as "influenceRun".
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import time
import unicodedata
import uuid
from pathlib import Path
from typing import Any

import httpx

from . import influences, media, songs
from .jobs import Cancelled, Context, JobError, Scheduler
from .music import yue2
from .songs import lyrics_text
from .writers import Writers, WriterError

log = logging.getLogger("sv.influence")

STEPS, SAVE_EVERY, PREVIEW_SECONDS = 1000, 100, 60
AUDIO = (".m4a", ".flac", ".mp3", ".ogg", ".opus", ".wav", ".aac")
SKIP = re.compile(r"\b(live|remix|mix\)|karaoke|instrumental|demo|commentary|interview|acoustic version|re-?recorded|"
                  r"sped up|slowed)\b", re.I)
CONTAINER_ROOT = "/opt/ComfyUI-YuE2"


# ---- names ------------------------------------------------------------------------------

def norm(text: str) -> str:
    """For matching titles and names: accents, case, brackets, 'feat.', remaster notes and punctuation removed."""
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    t = re.sub(r"\s[-–]\s.*(remaster|version|edit|mono|stereo|mix).*$", "", t)
    t = re.sub(r"[(\[].*?[)\]]", "", t)
    t = re.sub(r"\b(feat|ft)\b.*$", "", t)
    t = re.sub(r"^the\s+", "", t)
    t = t.replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "", t)


def lrc_words(text: str) -> str:
    """Lyrics from an .lrc file or a lyrics tag: one sung line per line, without time stamps or the .lrc's own tags.
    Empty unless there are enough words to be a song's lyrics."""
    lines = []
    for raw in (text or "").splitlines():
        if re.match(r"^\s*\[(ar|ti|al|by|offset|length|re|ve|au|la|id|#)\b[^\]]*\]\s*$", raw, re.I):
            continue
        line = " ".join(re.sub(r"\[\d{1,2}:\d{2}(?:[.:]\d{1,3})?\]|<\d{1,2}:\d{2}(?:[.:]\d{1,3})?>", "", raw).split())
        if line:
            lines.append(line)
    return "\n".join(lines) if len(" ".join(lines).split()) >= 12 else ""


def file_title(name: str, artist: str) -> str:
    """'03 - Title.m4a', 'Artist - Title.flac', '1-03 Title.mp3' -> 'Title'."""
    stem = name.rsplit(".", 1)[0]
    stem = re.sub(r"^\d{1,2}[-.]?\d{0,2}\s*[-.]?\s+", "", stem)
    if " - " in stem and norm(stem.split(" - ", 1)[0]) == norm(artist):
        stem = stem.split(" - ", 1)[1]
    return stem


# ---- your music: a folder on this machine or a network share, laid out Artist/…/Song --------------------------

def library(spec: str) -> "Folder | Share | None":
    """SV_MUSIC: a folder (`/mnt/music`), or smb://host/share/path (read anonymously); empty: none."""
    if not spec:
        return None
    if spec.startswith("smb://"):
        host, _, rest = spec[len("smb://"):].partition("/")
        share, _, root = rest.partition("/")
        return Share(f"//{host}/{share}", root.strip("/"))
    return Folder(Path(spec).expanduser())


class Folder:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self._artists: dict[str, str] | None = None

    async def artists(self) -> dict[str, str]:
        if self._artists is None:
            if not self.root.is_dir():
                raise JobError(f"Your music folder isn't there: {self.root}")
            self._artists = await asyncio.to_thread(lambda: {norm(d.name): d.name for d in self.root.iterdir() if d.is_dir()})
        return self._artists

    async def songs_of(self, artist: str) -> list[dict]:
        """Every audio file in the artist's folder: {title, path} (path relative to the folder)."""
        folder = (await self.artists()).get(norm(artist))
        if not folder:
            return []
        files = await asyncio.to_thread(lambda: sorted(f for f in (self.root / folder).rglob("*")
                                                       if f.is_file() and f.suffix.lower() in AUDIO))
        return [{"title": file_title(f.name, artist), "path": str(f.relative_to(self.root))} for f in files]

    async def fetch(self, path: str, dest: Path, small: bool = False) -> None:
        src = (self.root / path).resolve()
        if not src.is_relative_to(self.root) or not src.is_file():
            raise JobError(f"{Path(path).name} isn't in your music folder.")
        await asyncio.to_thread(shutil.copyfile, src, dest)


# smbclient -c separates commands with ; (and a command starting with ! runs in a shell): with no ; or " in a name,
# nothing in it can start a command of its own ("Panic! at the Disco" is fine)
UNSAFE_SMB = re.compile(r'[";\r\n\\]')


class Share:
    """A read-only network share (smbclient, as a guest). Names that could be read as smbclient commands are never
    put into one: a folder or file called that is skipped."""

    def __init__(self, share: str, root: str):
        self.share, self.root = share, root
        self._artists: dict[str, str] | None = None

    async def _smb(self, command: str, timeout: float = 60) -> str:
        try:
            proc = await asyncio.create_subprocess_exec("smbclient", self.share, "-N", "-c", command,
                                                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        except FileNotFoundError:
            raise JobError("Reading a network share needs smbclient on this machine.") from None
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout)
        except TimeoutError:
            proc.kill()
            raise JobError("Your music share didn't answer.") from None
        if proc.returncode != 0:
            raise JobError("Couldn't read your music share.", err.decode(errors="replace")[-500:])
        return out.decode(errors="replace")

    @staticmethod
    def _entries(text: str):
        """smbclient 'ls' lines -> (folder or None, name, is_dir)."""
        folder = None
        for line in text.splitlines():
            if line.startswith("\\"):
                folder = line.strip()
                continue
            m = re.match(r"^\s{2}(.+?)\s+([DAHSRN]+)\s+\d+\s+\w{3} \w{3}\s+\d+ [\d:]+ \d{4}\s*$", line)
            if m and m.group(1) not in (".", ".."):
                yield folder, m.group(1), "D" in m.group(2)

    async def artists(self) -> dict[str, str]:
        if self._artists is None:
            if UNSAFE_SMB.search(self.root):
                raise JobError("The music share's folder name has characters smbclient can't take.")
            text = await self._smb(f'cd "{self.root}"; ls')
            self._artists = {norm(name): name for _, name, d in self._entries(text) if d}
        return self._artists

    async def songs_of(self, artist: str) -> list[dict]:
        """Every audio file in the artist's folder: {title, path} (path relative to the share)."""
        folder = (await self.artists()).get(norm(artist))
        if not folder or UNSAFE_SMB.search(folder) or UNSAFE_SMB.search(self.root):
            return []
        text = await self._smb(f'recurse ON; cd "{self.root}/{folder}"; ls', timeout=90)
        base = "\\" + self.root.replace("/", "\\") + "\\" + folder
        out = []
        for where, name, is_dir in self._entries(text):
            if is_dir or not name.lower().endswith(AUDIO) or UNSAFE_SMB.search(name):
                continue
            sub = (where or base)[1:].replace("\\", "/")
            out.append({"title": file_title(name, artist), "path": f"{sub}/{name}"})
        return out

    async def fetch(self, path: str, dest: Path, small: bool = False) -> None:
        folder, name = path.rsplit("/", 1)
        if UNSAFE_SMB.search(path.replace("/", "")):
            raise JobError(f"Can't copy {name} (its name has characters smbclient can't take).")
        await self._smb(f'cd "{folder}"; get "{name}" "{dest}"', timeout=300)
        if not dest.exists() or dest.stat().st_size < (20 if small else 10000):
            raise JobError(f"Copying {name} from your music share failed.")


def guess_song(filename: str, tags: dict[str, str]) -> tuple[str, str]:
    """An added file's (artist, title): its tags, else its name ('Artist - Title.flac', '03 Title.mp3')."""
    stem = re.sub(r"^\d{1,2}[-.]?\d{0,2}\s*[-.]?\s+", "", filename.rsplit(".", 1)[0])
    artist, _, title = stem.partition(" - ") if " - " in stem else ("", "", stem)
    return (tags.get("artist") or tags.get("album_artist") or artist).strip(), (tags.get("title") or title).strip()


def match_song(songs: list[dict], artist: str, title: str) -> dict | None:
    """The run's song this file is: same title, and the same artist when the file names one."""
    hits = [s for s in songs if norm(s["title"]) == norm(title)]
    return next((s for s in hits if not artist or norm(s["artist"]) == norm(artist)), None)


async def _smi(*query: str) -> str:
    proc = await asyncio.create_subprocess_exec("nvidia-smi", *query, "--format=csv,noheader,nounits",
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    out, _ = await proc.communicate()
    return out.decode()


async def gpu_free_gb() -> float:
    try:
        return float((await _smi("--query-gpu=memory.free")).split()[0]) / 1024
    except (IndexError, ValueError, OSError):
        return 0.0


async def gpu_users() -> str:
    """Who holds the card: process id, memory, and its command line (to name the container)."""
    rows = []
    for line in (await _smi("--query-compute-apps=pid,used_memory")).splitlines():
        pid, mib = [x.strip() for x in line.split(",")[:2]]
        try:
            cmd = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")[:120]
        except OSError:
            cmd = "?"
        rows.append(f"{pid}: {mib} MiB {cmd}")
    return "\n".join(rows)


# ---- the run ----------------------------------------------------------------------------------

class Engine:
    def __init__(self, app, writers: Writers):
        self.app, self.writers = app, writers
        self.cfg = app.cfg
        self.lengths: dict[str, float] = {}  # preview file -> seconds

    # where things live
    def folder(self, run: dict) -> Path:
        """The training set, in the trainer's input folder (it reads input/<folder>)."""
        return self.cfg.trainer_root / "input" / run["folder"]

    def files(self, rid: str) -> Path:
        return self.cfg.data / "influence" / rid

    def save(self, rid: str, status: str | None = None, **fields: Any) -> dict:
        run = self.app.store.update_run(rid, status, **fields)
        self.app.hub.publish("influenceRun", run)
        return run

    def song(self, rid: str, sid: str, **fields: Any) -> dict:
        run = self.app.store.run(rid)
        songs = [dict(s, **fields) if s["id"] == sid else s for s in run["songs"]]
        return self.save(rid, songs=songs)

    # the user's actions
    def create(self, text: str, heard: str = "", project_id: str | None = None, take_id: str | None = None) -> dict:
        run = self.app.store.create_run("researching", {"ask": {"text": text.strip()[:3000], "heard": heard[:600],
                                                                 "projectId": project_id, "takeId": take_id},
                                                         "message": "Researching the sound", "songs": [], "artists": []})
        job = self.app.sched.submit("influence.research", {"runId": run["id"]})
        run = self.save(run["id"], jobId=job["id"])
        return run

    def start(self, rid: str, drop: list[str] | None = None) -> dict:
        run = self.app.store.run(rid)
        if run is None or run["status"] not in ("planned", "failed", "stopped"):
            raise JobError("That run can't start now.")
        if (run.get("train") or {}).get("status") == "complete" and run.get("sources"):
            # training finished: whatever failed later (keeping, trying), carrying on means choosing again
            return self.save(rid, "kept" if run.get("kept") else "choosing", message="Listen and choose a checkpoint")
        songs = [dict(s, use=s["id"] not in drop) for s in run["songs"]] if drop is not None else run["songs"]
        if sum(1 for s in songs if s["use"]) < 8:
            raise JobError("Keep at least 8 songs.")
        # gather first, always: it skips what's done, retries what failed, and hands on to listen and train
        job = self.app.sched.submit("influence.gather", {"runId": rid})
        return self.save(rid, "gathering", songs=songs, jobId=job["id"], message="Waiting its turn")

    def keep(self, rid: str, step: int, name: str | None = None) -> dict:
        run = self.app.store.run(rid)
        if run is None or run["status"] not in ("choosing", "kept"):
            raise JobError("Training hasn't finished yet.")
        if step not in [c["step"] for c in run.get("train", {}).get("checkpoints", [])]:
            raise JobError("There's no checkpoint at that step.")
        job = self.app.sched.submit("influence.keep", {"runId": rid, "step": step, "name": (name or run["name"]).strip()[:40]})
        return self.save(rid, jobId=job["id"], message=f"Keeping step {step}")

    # ---- research --------------------------------------------------------------------------
    async def research(self, ctx: Context) -> dict:
        rid = ctx.job["runId"]
        run = ctx.store.run(rid)
        ctx.update(stage="research", message="Choosing the artists and songs", progress=0.05)
        t0 = time.monotonic()
        try:
            r = await self.writers.write("research", {"text": run["ask"]["text"], "heard": run["ask"].get("heard")})
        except WriterError as exc:
            raise JobError(f"Couldn't research the sound: {exc}") from None
        plan, by = r["result"], r["by"]
        slug = influences.slug(plan["trigger"])[:24]
        tag = rid[-6:]
        self.save(rid, name=plan["name"], kind=plan["kind"], trigger=f"sv_{slug}", about=plan["about"],
                  howMany=plan["howMany"], style=plan["style"], voice=plan["voice"], previewLyrics=plan["previewLyrics"],
                  researchedBy={**by, "seconds": round(time.monotonic() - t0, 1)},
                  folder=f"training/sv-{slug}-{tag}", runName=f"sv_{slug}_{tag}", message="Finding the songs")
        lib, missing_music = library(self.cfg.music), None
        artists, songs = [], []
        per = max(2, round(36 / len(plan["artists"]))) if plan["kind"] != "Artist" else 25
        for i, a in enumerate(plan["artists"]):
            ctx.update(message=f"Looking for {a['name']} in your music" if lib else f"Listing {a['name']}",
                       progress=0.2 + 0.75 * i / len(plan["artists"]))
            owned: list[dict] = []
            if lib and not missing_music:
                try:
                    owned = await lib.songs_of(a["name"])
                except JobError as exc:  # the plan still stands: the audio can be added by hand
                    missing_music = exc.message
            artists.append({"name": a["name"], "why": a["why"], "inLibrary": bool(owned)})
            for k, title in enumerate(a["songs"]):  # best first; the last one or two are spares
                have = next((o for o in owned if norm(o["title"]) == norm(title)), None)
                songs.append({"id": f"track-{len(songs) + 1:03d}", "artist": a["name"], "title": title,
                              "source": "library" if have else "needed", "path": have and have["path"],
                              "use": k < per, "state": "waiting"})
        if sum(s["use"] for s in songs) < 8:
            raise JobError("Not enough songs were picked. Try describing the sound differently.")
        self.save(rid, "planned", artists=artists, songs=songs, musicNote=missing_music,
                  message="Add the audio for the songs, then start")
        return {"songs": len(songs), "inLibrary": sum(s["source"] == "library" for s in songs)}

    # ---- the audio you add -------------------------------------------------------------------
    def uploads(self, rid: str) -> Path:
        return self.files(rid) / "yours"

    async def add_audio(self, rid: str, files: list[tuple[str, Path]], song_id: str | None = None) -> dict:
        """Audio you added to the run, as (file name, temporary file): for one song, or matched to the list by its tags
        or its name. The run's songs that have it are used; files that match none are said."""
        run = self.app.store.run(rid)
        if run is None or run["status"] not in ("planned", "failed", "stopped"):
            raise JobError("Audio can be added before the run starts.")
        folder = self.uploads(rid)
        folder.mkdir(parents=True, exist_ok=True)
        added, unmatched = [], []
        for name, tmp in files:
            suffix = Path(name).suffix.lower()
            if suffix not in AUDIO:
                unmatched.append(name)
                continue
            if song_id:
                song = next((x for x in run["songs"] if x["id"] == song_id), None)
            else:
                tags = await asyncio.to_thread(media.tags, tmp, self.cfg.ffmpeg)
                song = match_song(run["songs"], *guess_song(name, tags))
            if song is None:
                unmatched.append(name)
                continue
            for old in folder.glob(f"{song['id']}.*"):
                old.unlink()
            shutil.move(str(tmp), folder / f"{song['id']}{suffix}")
            (self.folder(run) / f"{song['id']}.flac").unlink(missing_ok=True)  # gathered again from this file
            run = self.song(rid, song["id"], source="yours", path=None, use=True, state="waiting", note=None,
                            lyricsChecked=False, file=name[:200])
            added.append(song["id"])
        return {"run": run, "added": added, "unmatched": unmatched}

    # ---- gather ----------------------------------------------------------------------------
    async def gather(self, ctx: Context) -> dict:
        rid = ctx.job["runId"]
        run = self.save(rid, "gathering", message="Gathering the songs", resumeAt="gather")
        folder = self.folder(run)
        folder.mkdir(parents=True, exist_ok=True)
        for s in run["songs"]:  # the trainer takes every recording in the folder: a song left out leaves it
            if not s.get("use"):
                for f in folder.glob(f"{s['id']}.*"):
                    f.unlink()
        tmp = self.files(rid) / "incoming"
        tmp.mkdir(parents=True, exist_ok=True)
        lib = library(self.cfg.music)
        if lib:  # songs still without audio: you may have put them in your music since
            ctx.update(stage="look", message="Looking through your music again", progress=0.02)
            owned: dict[str, list[dict]] = {}
            for s in [x for x in run["songs"] if x.get("use") and x["source"] not in ("library", "yours")]:
                try:
                    if s["artist"] not in owned:
                        owned[s["artist"]] = await lib.songs_of(s["artist"])
                except JobError:
                    break
                have = next((o for o in owned[s["artist"]] if norm(o["title"]) == norm(s["title"])), None)
                if have:
                    self.song(rid, s["id"], source="library", path=have["path"], state="waiting", note=None)
        run = ctx.store.run(rid)
        todo = [s for s in run["songs"] if s.get("use") and not (folder / f"{s['id']}.flac").exists()]
        for i, s in enumerate(todo):
            ctx.update(stage="copy", message=f"Getting {s['artist']} – {s['title']} ready", progress=0.05 + 0.9 * i / max(1, len(todo)))
            yours = next(iter(self.uploads(rid).glob(f"{s['id']}.*")), None) if s["source"] == "yours" else None
            if not yours and not (s["source"] == "library" and s.get("path") and lib):
                self.song(rid, s["id"], state="needed", note="Add its audio")
                continue
            self.song(rid, s["id"], state="copying")
            src = yours or tmp / f"{s['id']}{Path(s['path']).suffix.lower()}"
            try:
                if not yours:
                    await lib.fetch(s["path"], src)
                await self._to_flac(src, folder / f"{s['id']}.flac")
                (folder / f"{s['id']}.song.txt").write_text(f"{s['artist']} - {s['title']}\n", encoding="utf-8")
                words = await self._published_lyrics(None if yours else lib, s.get("path"), src, tmp)
                if words:  # the song's published words beat a transcription; they go only to the sidecar
                    (folder / f"{s['id']}.lyrics.txt").write_text(words + "\n", encoding="utf-8")
                self.song(rid, s["id"], state="ready", lyricsFrom="published" if words else None, lyricsChecked=True, note=None)
            except (JobError, OSError) as exc:
                self.song(rid, s["id"], state="failed", note=str(exc)[:200])
            finally:
                if not yours:
                    src.unlink(missing_ok=True)
        run = ctx.store.run(rid)
        ready = [s for s in run["songs"] if s.get("use") and (folder / f"{s['id']}.flac").exists()]
        if len(ready) < 8:
            need = sum(1 for s in run["songs"] if s.get("use") and s.get("state") == "needed")
            raise JobError(f"Only {len(ready)} songs have their audio; at least 8 are needed."
                           + (f" Add the audio for {min(need, 8 - len(ready))} more." if need else ""))
        job = ctx.sched.submit("influence.listen", {"runId": rid})
        self.save(rid, "listening", message="Waiting to listen", jobId=job["id"], resumeAt="listen")
        return {"ready": len(ready)}

    async def _published_lyrics(self, lib: "Folder | Share | None", path: str | None, audio: Path, tmp: Path) -> str:
        """The words as published: an .lrc beside the file in your music, or a lyrics tag in it. Time stamps and the
        .lrc's own tags are removed. Empty when there are none."""
        text = ""
        lrc = tmp / (audio.stem + ".lrc")
        try:
            if not (lib and path):
                raise JobError("no music to look in")
            await lib.fetch(path.rsplit(".", 1)[0] + ".lrc", lrc, small=True)
            text = lrc.read_text(encoding="utf-8", errors="replace")
        except (JobError, OSError):
            probe = await asyncio.create_subprocess_exec(
                self.cfg.ffmpeg.replace("ffmpeg", "ffprobe"), "-v", "error", "-show_entries", "format_tags=lyrics",
                "-of", "default=nw=1:nk=1", str(audio), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            out, _ = await probe.communicate()
            text = out.decode(errors="replace")
        finally:
            lrc.unlink(missing_ok=True)
        return lrc_words(text)

    async def _to_flac(self, src: Path, dest: Path) -> None:
        proc = await asyncio.create_subprocess_exec(
            self.cfg.ffmpeg, "-v", "error", "-y", "-i", str(src), "-map", "0:a:0", "-vn", "-ac", "2", "-ar", "44100",
            "-sample_fmt", "s16", "-c:a", "flac", str(dest.with_suffix(".tmp.flac")),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        _, err = await proc.communicate()
        if proc.returncode != 0:
            raise JobError(f"Couldn't convert {src.name}.", err.decode(errors="replace")[-300:])
        dest.with_suffix(".tmp.flac").replace(dest)

    # ---- listen ----------------------------------------------------------------------------
    async def free_all(self, ctx: Context, need_gb: float) -> None:
        """Training and MOSS each need most of the card: every ComfyUI drops its models, then this waits until the
        memory is really free (a ComfyUI lets go a moment after it's asked)."""
        async with httpx.AsyncClient(timeout=5) as http:
            for base in (self.cfg.comfy, *self.cfg.other_comfys):
                try:
                    await http.post(f"{base}/free", json={"unload_models": True, "free_memory": True})
                except httpx.HTTPError:
                    pass
        free = 0.0
        for _ in range(45):
            free = await gpu_free_gb()
            if free >= need_gb:
                return
            ctx.update(message=f"Waiting for the GPU to free up ({free:.0f} of {need_gb:.0f} GB free)")
            await asyncio.sleep(2)
        raise JobError(f"The GPU didn't free up: {free:.0f} GB free, {need_gb:.0f} GB needed. Something else on "
                       f"{self.cfg.machine} is holding it; try again when it's done.", await gpu_users())

    async def listen(self, ctx: Context) -> dict:
        rid = ctx.job["runId"]
        run = self.save(rid, "listening", message="Listening to each song", resumeAt="listen")
        folder = self.folder(run)
        names = [s["id"] for s in run["songs"] if s.get("use") and (folder / f"{s['id']}.flac").exists()
                 and not (folder / f"{s['id']}.caption.txt").exists()]
        heard = 0
        if names:
            await self.free_all(ctx, 20)
            ctx.update(stage="listen", message="Loading MOSS-Music", progress=0.02)
            ctx.proc = await asyncio.create_subprocess_exec(
                str(self.cfg.listen_python), str(self.cfg.influence_tools / "listen.py"), str(folder), "--only", *names,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            assert ctx.proc.stdout
            async for raw in ctx.proc.stdout:
                try:
                    line = json.loads(raw)
                except ValueError:
                    continue
                if "i" in line:
                    heard = line["i"]
                    self.song(rid, line["name"], instrumental=line["instrumental"], lyricLines=line["lyricLines"])
                    ctx.update(message=f"Listened to {line['i']} of {line['n']}", progress=line["i"] / line["n"])
            err = (await ctx.proc.stderr.read()).decode(errors="replace") if ctx.proc.stderr else ""
            if await ctx.proc.wait() != 0:
                useful = [l for l in err.splitlines() if l.strip() and "pad_token_id" not in l and "it/s]" not in l]
                raise JobError("MOSS-Music stopped while listening.", "\n".join(useful)[-3000:])
        job = ctx.sched.submit("influence.train", {"runId": rid})
        self.save(rid, "training", message="Waiting to train", jobId=job["id"], resumeAt="train")
        return {"heard": heard}

    # ---- train -----------------------------------------------------------------------------
    def graph(self, run: dict) -> dict:
        lyrics = lyrics_text([{"kind": s["kind"], "text": "\n".join(s["lines"])} for s in run.get("previewLyrics") or []])
        return {
            "1": {"class_type": "FL_YuE2_TrainingModels", "inputs": {
                "tokenizer_head": "tokenizer_head_joint_v4.pt", "regularizer": "minted_regularizer_pack.pt", "download_missing": False}},
            "2": {"class_type": "FL_YuE2_DatasetMaker", "inputs": {
                "audio_directory": run["folder"], "trigger": run["trigger"], "default_style": run.get("style") or "",
                "validation_fraction": 0.1, "seed": 42}},
            "3": {"class_type": "FL_YuE2_PrepareDataset", "inputs": {
                "dataset": ["2", 0], "assets": ["1", 0], "align_lyrics": False, "cache_directory": run["runName"] + "_features"}},
            "4": {"class_type": "FL_YuE2_TrainConfig", "inputs": {
                "rank": 32, "learning_rate": 0.0001, "generated_fraction": 0.2, "cursor_weight": 0.0, "sequence_tokens": 24576,
                "allow_truncation": True, "steps": STEPS, "save_every": SAVE_EVERY, "schedule_steps": STEPS, "warmup_steps": 50,
                "accumulation": 1, "seed": 42, "train_acoustic": True, "training_recipe": "upstream"}},
            "5": {"class_type": "FL_YuE2_LoRATrainer", "inputs": {
                "action": "train", "output_name": run["runName"], "resume": "", "selected_step": 0, "render_previews": True,
                "preview_style": f"{run['trigger']}, {run.get('style') or ''}".strip(", "), "preview_lyrics": lyrics,
                "preview_seed": 42, "preview_seconds": PREVIEW_SECONDS,
                "assets": ["1", 0], "dataset": ["3", 0], "config": ["4", 0]}},
        }

    async def _cat(self, path: str) -> bytes:
        """Read a file the trainer wrote (they belong to root inside its container)."""
        proc = await asyncio.create_subprocess_exec("docker", "exec", self.cfg.trainer_container, "cat", path,
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        out, _ = await proc.communicate()
        if proc.returncode != 0:
            raise FileNotFoundError(path)
        return out

    async def _live(self, run: dict) -> dict:
        """The trainer's latest event for this run (its run record is only written at checkpoints; every step and
        each preview's progress is in its worker's log)."""
        name = run.get("runName") or ""
        if not re.fullmatch(r"[a-z0-9_]+", name):
            return {}
        # the newest worker job of this run (training or a preview), then the end of its log
        script = ("cd " + CONTAINER_ROOT + "/output/yue2_training/jobs 2>/dev/null || exit 0; "
                  "f=$(ls -t *.json 2>/dev/null | head -6 | xargs -r grep -l -e '/" + name + "/' -e '/" + name + "\"' | head -1); "
                  '[ -n "$f" ] && tail -c 3000 "${f%.json}.log"')
        proc = await asyncio.create_subprocess_exec("docker", "exec", self.cfg.trainer_container, "sh", "-c", script,
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        out, _ = await proc.communicate()
        for line in reversed(out.decode(errors="replace").splitlines()):
            if line.startswith("YUE2_EVENT "):
                try:
                    return json.loads(line[len("YUE2_EVENT "):])
                except ValueError:
                    continue
        return {}

    async def _record(self, run: dict) -> dict | None:
        try:
            return json.loads(await self._cat(f"{CONTAINER_ROOT}/output/yue2_training/{run['runName']}/run.json"))
        except (FileNotFoundError, ValueError):
            return None

    async def _previews(self, rid: str, run: dict, record: dict) -> list[dict]:
        """Copy each new preview out of the trainer as an AAC file the browser plays."""
        out = self.files(rid) / "previews"
        out.mkdir(parents=True, exist_ok=True)
        rows = []
        for c in [record.get("baseline") or {}, *record.get("checkpoints", [])]:
            if not c.get("preview"):
                continue
            step = int(c.get("step") or 0)
            m4a = out / f"step-{step:04d}.m4a"
            if not m4a.exists():
                raw = out / f"step-{step:04d}.flac"
                raw.write_bytes(await self._cat(f"{CONTAINER_ROOT}/output/yue2_training/{run['runName']}/{c['preview']}"))
                await asyncio.to_thread(media.to_m4a, raw, m4a, self.cfg.ffmpeg)
                raw.unlink(missing_ok=True)
            if str(m4a) not in self.lengths:
                self.lengths[str(m4a)] = round(await asyncio.to_thread(media.duration, m4a, self.cfg.ffmpeg), 1)
            rows.append({"step": step, "preview": f"/files/influence/{rid}/previews/{m4a.name}", "seconds": self.lengths[str(m4a)]})
        return rows

    async def _attach(self, http: httpx.AsyncClient, run: dict) -> str | None:
        """The training this run already started, if the trainer is still on it (or finished it): after the app
        restarts, the job follows it again instead of starting a second one."""
        pid = run.get("trainPrompt")
        if not pid:
            return None
        try:
            q = (await http.get("/queue")).json()
            waiting = [item[1] for item in q.get("queue_running", []) + q.get("queue_pending", [])]
            if pid in waiting:
                return pid
            h = (await http.get(f"/history/{pid}")).json().get(pid)
            if h and h.get("status", {}).get("completed"):
                return pid
        except (httpx.HTTPError, ValueError, IndexError):
            pass
        return None

    async def train(self, ctx: Context) -> dict:
        rid = ctx.job["runId"]
        run = self.save(rid, "training", message="Preparing to train", resumeAt="train")
        client = "sv-app-" + uuid.uuid4().hex[:8]
        async with httpx.AsyncClient(base_url=self.cfg.trainer, timeout=30) as http:
            pid = await self._attach(http, run)
            if pid is None:
                await self.free_all(ctx, 18)
                try:
                    r = await http.post("/prompt", json={"prompt": self.graph(run), "client_id": client})
                except httpx.HTTPError as exc:
                    raise JobError("The trainer (FL YuE2 on :8196) isn't running.") from exc
                if r.status_code != 200:
                    raise JobError("The trainer refused the training graph.", r.text[:2000])
                pid = r.json()["prompt_id"]
                self.save(rid, trainPrompt=pid)
            ctx.update(stage="prepare", message="Reading the songs (MERT features)", progress=0.01, promptId=pid)
            started, rate, prev = time.monotonic(), 0.0, None
            try:
                while True:
                    await asyncio.sleep(5)
                    if ctx.cancelled:
                        raise Cancelled()
                    h = (await http.get(f"/history/{pid}")).json().get(pid)
                    record = await self._record(run)
                    live = await self._live(run)
                    if (record and record.get("signature")) or live:
                        record = record or {}
                        step = max(int(record.get("step") or 0), int(live.get("step") or 0) if live.get("type") == "progress" else 0)
                        metrics = live if live.get("type") == "progress" else (record.get("metrics") or [{}])[-1]
                        if live.get("type") == "progress":
                            # seconds a step, between two readings of the trainer's clock (it restarts after each preview)
                            now = (int(live.get("step") or 0), float(live.get("seconds") or 0))
                            if prev and now[0] > prev[0] and now[1] > prev[1]:
                                inst = (now[1] - prev[1]) / (now[0] - prev[0])
                                rate = inst if not rate else 0.7 * rate + 0.3 * inst
                            prev = now
                        checkpoints = await self._previews(rid, run, record) if record else []
                        previewing = live.get("type") == "preview_progress"
                        eta = rate * (STEPS - step) + 150 * max(0, (STEPS - step) // SAVE_EVERY) if rate else None
                        self.save(rid, train={"step": step, "steps": STEPS, "loss": metrics.get("loss"),
                                              "status": "preview" if previewing else "train", "checkpoints": [c for c in checkpoints if c["step"]],
                                              "baseline": next((c for c in checkpoints if c["step"] == 0), None),
                                              "eta": round(eta) if eta else None,
                                              "minutes": round((time.monotonic() - started) / 60, 1)})
                        what = (f" (the {'untrained' if not live.get('step') else 'step ' + str(live.get('step'))} preview, "
                                f"{round(100 * (live.get('done') or 0) / max(1, live.get('total') or 1))}%)") if previewing else ""
                        ctx.update(stage="train", message=f"Training: step {step} of {STEPS}{what}",
                                   progress=0.05 + 0.95 * step / STEPS)
                    if h is None:
                        continue
                    status = h.get("status", {})
                    if status.get("status_str") == "error" or (status.get("completed") is False and status.get("messages")):
                        err = next((m[1] for m in status.get("messages", []) if m[0] == "execution_error"), {})
                        raise JobError("Training stopped: " + str(err.get("exception_message") or "an error in the trainer")[:300],
                                       json.dumps(err)[:3000])
                    if status.get("completed"):
                        break
            except (Exception, Cancelled):
                # stopped by the user, or the training failed: make sure the trainer lets go of it
                try:
                    await http.post("/queue", json={"delete": [pid]})
                    await http.post("/interrupt", json={"prompt_id": pid})
                except httpx.HTTPError:
                    pass
                self.save(rid, trainPrompt=None)
                raise
            finally:
                try:
                    await http.post("/free", json={"unload_models": True, "free_memory": True})
                except httpx.HTTPError:
                    pass
        record = await self._record(run) or {}
        checkpoints = [c for c in await self._previews(rid, run, record) if c["step"]]
        sources = {int(c["step"]): {"ar": c["adapter"], "nar": c.get("acoustic_adapter")} for c in record.get("checkpoints", [])}
        self.save(rid, "choosing", message="Listen and choose a checkpoint", resumeAt=None, sources=sources,
                  train={**(ctx.store.run(rid).get("train") or {}), "step": record.get("step"), "status": "complete",
                         "checkpoints": checkpoints, "eta": 0})
        return {"checkpoints": len(checkpoints)}

    # ---- keep, or try one on a song ------------------------------------------------------------
    async def export(self, run: dict, step: int) -> Path:
        """Convert a checkpoint for our ComfyUI (inside the trainer's container: its files belong to root there).
        Returns the converted file; done once per checkpoint."""
        exported = self.cfg.trainer_root / "output" / "sv-export" / run["runName"] / f"step-{step:04d}.safetensors"
        if exported.exists():
            return exported
        src = (run.get("sources") or {}).get(str(step)) or (run.get("sources") or {}).get(step)
        if not src:
            raise JobError("That checkpoint's files weren't found.")
        out = f"{CONTAINER_ROOT}/output/sv-export/{run['runName']}/step-{step:04d}.safetensors"
        meta = {"trigger": run["trigger"], "name": run.get("name"), "step": step, "source_run": run["runName"]}
        args = ["docker", "exec", "-i", self.cfg.trainer_container, "python", "-", "--ar", src["ar"],
                *(["--nar", src["nar"]] if src.get("nar") else []), "--out", out, "--meta", json.dumps(meta)]
        proc = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.PIPE)
        _, stderr = await proc.communicate((self.cfg.influence_tools / "convert.py").read_bytes())
        if proc.returncode != 0 or not exported.exists():
            raise JobError("Converting the checkpoint failed.", stderr.decode(errors="replace")[-2000:])
        return exported

    def try_step(self, rid: str, step: int, pid: str, strength: float) -> dict:
        run = self.app.store.run(rid)
        if run is None or step not in [c["step"] for c in run.get("train", {}).get("checkpoints", [])]:
            raise JobError("There's no checkpoint at that step.")
        if run["status"] not in ("choosing", "kept"):
            raise JobError("Training hasn't finished yet.")
        if self.app.store.project(pid) is None:
            raise JobError("That song isn't here any more.")
        return self.app.sched.submit("influence.try", {"runId": rid, "step": step, "strength": strength,
                                                       "message": f"Getting step {step} ready"}, pid)

    async def try_job(self, ctx: Context) -> dict:
        """One YuE2 take of the user's song with this checkpoint as an influence, so they can judge it on their own
        song through the same path the app will use. The checkpoint goes in the library hidden, only for trying."""
        rid, step, strength, pid = ctx.job["runId"], int(ctx.job["step"]), float(ctx.job.get("strength") or 0.7), ctx.job["projectId"]
        run = ctx.store.run(rid)
        ctx.update(stage="convert", message=f"Converting step {step}", progress=0.2)
        exported = await self.export(run, step)
        iid = f"try_{run['runName']}_{step:04d}"
        folder = self.cfg.loras / "soundandvision" / "yue2"
        dest = folder / f"{iid}.safetensors"
        if not dest.exists():
            await asyncio.to_thread(shutil.copyfile, exported, dest)
            dest.chmod(0o644)
        (folder / f"{iid}.json").write_text(json.dumps({
            "name": f"{run['name']} · step {step}", "kind": run.get("kind") or "Style", "hidden": True, "trial": rid,
            "trigger": run["trigger"], "recommended": strength, "max": 1.0}, indent=2))
        p = ctx.store.project(pid)
        if p is None:
            raise JobError("That song isn't here any more.")
        doc = {k: v for k, v in p.items() if k not in ("id", "title", "rev", "createdAt", "updatedAt")}
        doc["influences"] = [i for i in (doc.get("influences") or []) if not str(i.get("id", "")).startswith("try_")] \
            + [{"id": iid, "strength": strength}]
        if doc.get("plan") == "free":  # influences need YuE2's sketch
            doc["plan"] = "full"
        try:
            made = songs.start_takes(self.app, pid, songs.request_from_doc(doc, takes=1))
        except yue2.SongError as exc:
            raise JobError(f"Couldn't make the take: {exc}") from None
        tries = {**(run.get("tries") or {}), str(step): [*(run.get("tries") or {}).get(str(step), []),
                                                         {"projectId": pid, "takeId": made["takes"][0]["id"]}]}
        self.save(rid, tries=tries)
        return {"takeId": made["takes"][0]["id"], "influence": iid}

    def tidy(self, run: dict, everything: bool = False) -> None:
        """Remove the checkpoints copied for trying (about 640 MB each); with everything, also the converted copies
        in the trainer's folder (the trainer's own checkpoints and previews stay)."""
        folder = self.cfg.loras / "soundandvision" / "yue2"
        for f in folder.glob(f"try_{run.get('runName')}_*"):
            f.unlink(missing_ok=True)
        if everything and run.get("runName"):
            asyncio.get_running_loop().create_task(asyncio.create_subprocess_exec(
                "docker", "exec", self.cfg.trainer_container, "rm", "-rf",
                f"{CONTAINER_ROOT}/output/sv-export/{run['runName']}"))

    # ---- keep ------------------------------------------------------------------------------
    async def keep_job(self, ctx: Context) -> dict:
        rid, step, name = ctx.job["runId"], int(ctx.job["step"]), ctx.job.get("name")
        run = ctx.store.run(rid)
        ctx.update(stage="keep", message=f"Converting step {step}", progress=0.2)
        exported = await self.export(run, step)
        if (old := (run.get("kept") or {}).get("influenceId")):  # "Keep this instead": the new one replaces it
            for f in (self.cfg.loras / "soundandvision" / "yue2").glob(f"{old}.*"):
                f.unlink(missing_ok=True)
        staged = self.cfg.loras / "soundandvision" / "yue2" / f".keep-{rid}-{step:04d}.safetensors"  # same disk as the library
        await asyncio.to_thread(shutil.copyfile, exported, staged)
        ctx.update(message="Adding it to your influences", progress=0.8)
        about = run.get("about") or ""
        rec = influences.add(self.cfg.loras, staged, name=name or run["name"], kind=run.get("kind") or "Style",
                             about=f"{about} Trained here from {sum(1 for s in run['songs'] if s.get('state') == 'ready')} songs, step {step}.".strip(),
                             model="yue2", source=f"Influence Engine {run['runName']} step {step}", recommended=0.7)
        side = self.cfg.loras / rec["file"]
        sidecar = side.with_suffix(".json")
        data = json.loads(sidecar.read_text())
        data.update(trigger=run["trigger"], max=1.0, step=step, run=rid)
        sidecar.write_text(json.dumps(data, indent=2))
        self.tidy(run)
        self.save(rid, "kept", message=f"Kept step {step} as “{rec['name']}”", kept={"step": step, "influenceId": rec["id"]})
        ctx.hub.publish("influences", {"changed": rec["id"]})
        return {"influence": rec["id"]}


def register(sched: Scheduler, app, writers: Writers) -> Engine:
    eng = Engine(app, writers)

    def runner(fn):
        async def run(ctx: Context) -> dict:
            try:
                return await fn(ctx)
            except Exception as exc:
                msg = exc.message if isinstance(exc, JobError) else "Something went wrong on the server."
                if ctx.cancelled:
                    eng.save(ctx.job["runId"], "stopped", message="Stopped. Start it again to carry on.")
                else:
                    eng.save(ctx.job["runId"], "failed", message=msg)
                raise
        return run

    sched.register("influence.research", "net", runner(eng.research))
    sched.register("influence.gather", "net", runner(eng.gather))
    sched.register("influence.listen", "gpu", runner(eng.listen))
    sched.register("influence.train", "gpu", runner(eng.train))
    def choosing(fn, what):
        """Keeping or trying a checkpoint can fail without undoing the training: the run stays in Choose."""
        async def run(ctx: Context) -> dict:
            try:
                return await fn(ctx)
            except Exception as exc:
                r = ctx.store.run(ctx.job["runId"])
                msg = exc.message if isinstance(exc, JobError) else "something went wrong on the server"
                if r:
                    eng.save(r["id"], "kept" if r.get("kept") else "choosing",
                             message=f"Couldn't {what} step {ctx.job.get('step')}: {msg}")
                raise
        return run

    sched.register("influence.keep", "net", choosing(eng.keep_job, "keep"))
    sched.register("influence.try", "net", choosing(eng.try_job, "try"))
    return eng
