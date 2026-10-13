"""Motion Graphics (kept as "kinetic" in the code and the routes): a music video, with the lyrics or without, written and
rendered in code by Claude in the studio container, made the way the user's best films were made in Claude Code chats
(No One Knows, Go, Propellerheads, Crass, Pyramid Song). The request is the one they typed there, word for word ("make
a dynamic motion graphics music video with lyrics that shows what an incredible motion designer you are, like it's your
showreel for a résumé. go all out."); the folder's CLAUDE.md (KINETIC.md + MACHINE.md) only says what's there, the
lyrics limit and what to hand back (memory: free-rein-films). Opus 5.5 at extra high reasoning by default (Settings →
Who does what → Making videos in code).

A film is one Claude Code conversation in projects/<pid>/kinetic/<fid>/work: the first run makes it; each note the
person sends continues the same conversation (--resume) and may leave a new version. Every finished out/final.mp4 is
checked (size, length), laid under the song again, and kept as a version.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from .. import covers as covers_mod, studio
from ..jobs import Context, JobError
from . import folder, loops
from .finish import _about

HERE = Path(__file__).resolve().parent
RULES = HERE / "KINETIC.md"
SHAPES = {"wide": (1920, 1080), "story": (1080, 1920), "square": (1080, 1080)}
FPS = 60
TIMEOUT = 4 * 3600  # a whole film with its review rounds (the old app's first took ~90 min)
MAX_TURNS = 1000
# The person's own chat prompts, word for word, with where the song (and its words) are in this folder
OPENING = {True: ('Make a dynamic motion graphics music video with lyrics for "{title}"{by} that shows what an incredible '
                  "motion designer you are, like it's your showreel for a résumé. Go all out. The song is song/song.m4a, "
                  "and its lyrics, timed to the singing, are in song/timing.json."),
           False: ('Make a dynamic motion graphics music video for "{title}"{by}, using the song in song/song.m4a, that shows '
                   "what an incredible motion designer you are. Go all out.")}
IDEA_FIRST = ("Before you build the film, show the person the idea: write plan/CONCEPT.md (one page in plain words: the "
              "idea, the scenes with their times, the look and the motion) and render four to six stills of key moments "
              "into out/plan/. Look at them, then stop and ask the person to approve the idea or say what to change.")
GO = "The person likes the idea. Now make the film, all the way to the finished video. Go all out."
HARD = ("CLAUDE.md says what's in this folder, what's installed and what to hand back. One hard limit: never type out the "
        "song's lyrics (in code, notes or messages); the API blocks replies that reproduce them. Your code loads any words "
        "it shows from the timing files when it renders.")


class Kinetic:
    """A film made by one Claude Code conversation in the studio. Music videos (music.py) are the same machine with
    their own notes, request, connectors and a helper that runs beside the session."""
    KEY, JOB = "kinetic", "kinetic.film"  # the project doc's field (and folder), and the job kind
    RULES = RULES
    CONNECTORS: list[str] = []  # claude.ai connectors the session may use
    PEEK = ("out",)  # where the newest pictures are found while Claude works
    META_KIND = "motion graphics music video"
    GO = GO  # what an approval says (the person's "go" after the idea)

    def __init__(self, app, writers):
        self.app, self.writers = app, writers
        self.cfg = app.cfg

    # ---- the record (project doc KEY: {film, videos}) ---------------------------------------------------
    def get(self, p: dict) -> dict:
        k = dict(p.get(self.KEY) or {})
        k.setdefault("film", None)
        k.setdefault("videos", [])
        return k

    def put(self, pid: str, publish: bool = True, **changes: Any) -> dict:
        p = self.app.store.project(pid)
        if p is None:
            raise JobError("That song isn't here any more.")
        p = self.app.store.patch_project(pid, **{self.KEY: {**self.get(p), **changes}})
        if publish:
            self.app.hub.publish("project", p)
        return p

    def film_changed(self, pid: str, publish: bool = True, **fields: Any) -> dict:
        k = self.get(self.app.store.project(pid) or {})
        return self.put(pid, publish, film={**(k["film"] or {}), **fields})

    def folder(self, pid: str, fid: str) -> Path:
        return self.cfg.projects / pid / self.KEY / fid

    def _ready(self, pid: str) -> tuple[dict, dict]:
        p = self.app.store.project(pid)
        if p is None:
            raise JobError("That song isn't here any more.")
        take = self.app.store.take(p.get("masterTake") or "")
        if not take or take.get("status") != "ready":
            raise JobError("Choose the song's take first (“Use this one” on the song page).")
        if (take.get("analysis") or {}).get("status") != "ready":
            raise JobError("The app is still listening to the song (its beat and its words): try again when that's done.")
        return p, take

    def _busy(self, pid: str) -> bool:
        return any(j["kind"] == self.JOB for j in self.app.store.jobs(("queued", "running"), project_id=pid))

    # ---- the person's actions -------------------------------------------------------------------------------------
    def start(self, pid: str, request: str = "", feel: str = "", shape: str = "wide", idea_first: bool = False,
              model: str | None = None, effort: str | None = None, lyrics: bool = True) -> dict:
        """A new film. `request`: the words Claude gets (empty: the default, the person's own chat prompt, with the lyrics
        or without)."""
        return self._new(pid, request, feel, shape, model, effort, ideaFirst=bool(idea_first), lyrics=bool(lyrics))

    def _new(self, pid: str, request: str, feel: str, shape: str, model: str | None, effort: str | None, **extra: Any) -> dict:
        self._ready(pid)
        if self._busy(pid):
            raise JobError("A film is already being made for this song.")
        who = self.writers.film()
        fid = uuid.uuid4().hex[:8]
        film = {"id": fid, "status": "queued", "request": " ".join((request or "").split())[:2000],
                "feel": (feel or "").strip()[:1500], "shape": shape if shape in SHAPES else "wide", "ideaFirst": False,
                **extra, "model": model or who["model"], "effort": effort or who["effort"], "session": None, "runs": 0,
                "lines": [], "message": "Waiting its turn", "error": None, "concept": None, "stills": [], "at": time.time()}
        self.folder(pid, fid).mkdir(parents=True, exist_ok=True)
        job = self.app.sched.submit(self.JOB, {"filmId": fid, "stage": "start", "message": "Waiting its turn"}, pid)
        film["jobId"] = job["id"]
        self.put(pid, film=film)
        return job

    def note(self, pid: str, text: str, go: bool = False) -> dict:
        """A note to Claude, continuing the film's conversation (`go`: the idea is approved, make the film)."""
        p, _ = self._ready(pid)
        film = self.get(p)["film"]
        if not film or not film.get("session"):
            raise JobError("There's no film conversation to continue: make one first.")
        if self._busy(pid):
            raise JobError("It's still working on it: send the note when it's done, or stop it first.")
        text = (text or "").strip()[:4000]
        if not text and not go:
            raise JobError("Write the note first.")
        job = self.app.sched.submit(self.JOB, {"filmId": film["id"], "stage": "note", "text": text, "go": go,
                                                     "message": "Waiting its turn"}, pid)
        self.film_changed(pid, status="queued", jobId=job["id"], error=None, message="Waiting its turn", fixRounds=0,
                          notes=[*(film.get("notes") or []), {"text": text, "go": go, "at": time.time()}])
        return job

    async def stop(self, pid: str) -> dict:
        p = self.app.store.project(pid)
        film = self.get(p or {})["film"]
        if not film or not film.get("jobId"):
            raise JobError("Nothing is being made.")
        await self.app.sched.cancel(film["jobId"])
        return self.film_changed(pid, status="stopping", message="Stopping…")

    def peek(self, pid: str) -> list[dict]:
        """The newest pictures Claude has made in out/ while it works (it looks at them as it goes)."""
        film = self.get(self.app.store.project(pid) or {})["film"]
        if not film:
            return []
        work = self.folder(pid, film["id"]) / "work"
        found = [f for d in self.PEEK if (work / d).is_dir() for f in (work / d).rglob("*")
                 if f.suffix.lower() in (".png", ".jpg", ".jpeg") and f.is_file() and "tmp" not in f.relative_to(work / d).parts[:1]]
        pics = sorted(found, key=lambda f: f.stat().st_mtime, reverse=True)[:6]
        root = self.cfg.projects / pid
        return [{"file": str(f.relative_to(root)), "at": f.stat().st_mtime} for f in pics]

    # ---- the job (studio lane) ---------------------------------------------------------------------------------
    async def refresh(self, ctx: Context, p: dict, film: dict, work: Path) -> None:
        """Before a note continues the film: bring what the app owns in the folder up to date (nothing, here)."""

    async def verify(self, ctx: Context, p: dict, film: dict, work: Path, video: Path) -> str | None:
        """After a video is handed back: what the app's own check found that must be fixed, as a note for the director,
        or None (nothing is checked, here)."""
        return None

    FIX_ROUNDS = 2  # times the app sends the director back on its own before the person sees what's left

    async def _send_back(self, ctx: Context, p: dict, film: dict, work: Path, video: Path) -> bool:
        """The app's check, and when it fails and rounds are left, the director sent back to fix it (a note of the
        app's own, queued after this job). True when it was sent back."""
        fix = await self.verify(ctx, p, film, work, video)
        if not fix:
            return False
        now = self.get(self.app.store.project(p["id"]) or {})["film"] or film
        rounds = int(now.get("fixRounds") or 0)
        if rounds >= self.FIX_ROUNDS:
            return False
        job = self.app.sched.submit(self.JOB, {"filmId": film["id"], "stage": "note", "text": fix, "go": False, "app": True,
                                               "message": "Waiting its turn"}, p["id"])
        self.film_changed(p["id"], status="queued", jobId=job["id"], fixRounds=rounds + 1, error=None,
                          message="The app's check found joins to fix: sending it back to fix them")
        return True

    async def job(self, ctx: Context) -> dict:
        pid, fid = ctx.job["projectId"], ctx.job["filmId"]
        p, take = self._ready(pid)
        film = self.get(p)["film"]
        if not film or film["id"] != fid:
            raise JobError("That film isn't this song's any more.")
        work = self.folder(pid, fid) / "work"
        if ctx.job.get("stage") == "start":
            self.film_changed(pid, status="preparing", message="Setting up the studio")
            ctx.update(stage="prepare", message="Setting up the studio", progress=0.01)
            await self.setup(ctx, p, take, film, work)
            parts = [film["request"] or self.opening(p, film, work)]
            if film.get("feel"):
                parts.append("The person's guidance:\n" + film["feel"])
            parts += self.prompt_parts(film)
            parts.append(HARD)
            prompt, resume = "\n\n".join(parts), None
        else:
            await self.refresh(ctx, p, film, work)
            prompt = "\n\n".join(x for x in (self.GO if ctx.job.get("go") else "", ctx.job.get("text") or "") if x)
            resume = film.get("session")

        started = time.time()
        last = [0.0]
        said: list[dict] = list(film.get("lines") or [])[-30:]
        self.film_changed(pid, status="running", message="Reading the song", error=None, runAt=started)

        def on_line(line: dict) -> None:
            say = studio.plain(line)
            if not say:
                return
            if line["kind"] == "say":
                said.append({"text": line["text"][:600], "at": time.time()})
            ctx.update(stage="claude", message=say[:240], progress=None)
            if time.time() - last[0] > 12 or line["kind"] == "say":  # the page follows along, without a storm of saves
                last[0] = time.time()
                self.film_changed(pid, message=say[:240], lines=said[-30:])
        helper = asyncio.create_task(self.helper(ctx, pid, work))
        servers = self.writers.mcp.for_directing(self.chosen_servers(film))
        try:
            r = await studio.run(self.cfg.studio_sh, work, prompt, model=film.get("model"), effort=film.get("effort"),
                                 max_turns=self.max_turns(film), timeout=self.timeout(film), on_line=on_line,
                                 is_cancelled=lambda: ctx.cancelled, resume=resume,
                                 connectors=[*self.connectors(film), *self.writers.mcp.allowed(servers)] or None,
                                 mcp=await self.writers.mcp.claude_config(servers))
        finally:
            helper.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await helper
        runs = int(film.get("runs") or 0) + 1
        self.film_changed(pid, publish=False, session=r.get("session") or film.get("session"), runs=runs, lines=said[-30:])
        (self.folder(pid, fid) / f"run-{runs}.json").write_text(json.dumps({k: r[k] for k in ("state", "lines", "seconds")}, indent=1))
        if r["state"] == "cancelled":
            raise JobError("Stopped. Send a note to carry on from where it was.")
        if r["state"] == "limit":
            raise JobError("Your Claude plan's usage limit was reached. Send a note after it resets to carry on.")
        if r["state"] == "timeout":
            raise JobError(f"It ran past {self.timeout(film) / 3600:g} hours and was stopped. Send a note to carry on.")
        reply = next((x["text"] for x in reversed(r["lines"]) if x["kind"] in ("result", "say")), "")

        final = work / "out" / "final.mp4"
        concept = work / "plan" / "CONCEPT.md"
        if final.exists() and final.stat().st_mtime >= started:
            rec = await self._keep(ctx, p, take, film, work, final, runs)
            self.film_changed(pid, reply=reply, video=rec["id"], error=None)
            if await self._send_back(ctx, p, film, work, final):
                return {"video": rec["id"], "seconds": r["seconds"], "sentBack": True}
            self.film_changed(pid, status="done", message=self.done_message(pid))
            return {"video": rec["id"], "seconds": r["seconds"]}
        handed = await self.handback(ctx, p, take, film, work, started, runs, reply)
        if handed:
            return {**handed, "seconds": r["seconds"]}
        if concept.exists() and concept.stat().st_mtime >= started:
            stills = sorted((work / "out" / "plan").glob("*.png")) + sorted((work / "out" / "plan").glob("*.jpg"))
            root = self.cfg.projects / pid
            self.film_changed(pid, status="waiting", message="The idea is ready", reply=reply,
                              concept=concept.read_text()[:8000], stills=[str(f.relative_to(root)) for f in stills[:8]])
            return {"waiting": True, "seconds": r["seconds"]}
        if r["state"] != "done":
            why = next((x["text"] for x in reversed(r["lines"]) if x["kind"] == "error"), "")
            raise JobError("The director stopped before the film was done" + (f": {why[:240]}" if why else ".") + " Send a note to carry on.")
        if ctx.job.get("app") and film.get("video"):
            # the app sent it back after its check and it left the video as it was (a choice the person made): the
            # video stands, so it's done, with what the check still finds
            self.film_changed(pid, status="done", message=self.done_message(pid), reply=reply)
            return {"reply": True, "seconds": r["seconds"]}
        # it answered without a new video (a question, or a reply to a note): the person reads it and answers
        self.film_changed(pid, status="waiting", message="Replied", reply=reply)
        return {"reply": True, "seconds": r["seconds"]}

    def done_message(self, pid: str) -> str:
        """What the person reads when the video is done: what's left that the app's check found, if anything."""
        film = self.get(self.app.store.project(pid) or {})["film"] or {}
        check = film.get("joinsCheck") or {}
        failed = check.get("failed") or []
        if failed and check.get("at", 0) >= (film.get("runAt") or 0):
            when = ", ".join(f"{int(x['at'] // 60)}:{x['at'] % 60:04.1f}" for x in failed[:6])
            return f"Done, but {len(failed)} join{'s' if len(failed) != 1 else ''} still didn't pass the app's check: {when}"
        return "Done"

    async def _keep(self, ctx: Context, p: dict, take: dict, film: dict, work: Path, final: Path, runs: int,
                    opening: bool = False) -> dict:
        """The finished film, checked and laid under the song again (the picture as Claude rendered it; the sound is the
        song, unchanged), kept as a version; a lighter copy for sharing when the master is big. `opening`: only the
        start of the song (a music video's first 30 seconds, to see the direction)."""
        pid = p["id"]
        info = await asyncio.to_thread(loops.probe, str(final), self.cfg.ffmpeg)
        w, h = SHAPES[film["shape"]]
        length = info["frames"] / info["fps"]
        song = float(take.get("duration") or 0)
        part = film.get("part") if opening else None  # a chosen part of the song: its sound starts there
        total = part["end"] - part["start"] if part else min(length, song) if opening else song
        if (info["w"], info["h"]) != (w, h) or abs(length - total) > 1.5:
            raise JobError(f"The film came out {info['w']}×{info['h']}, {length:.1f} s (the song is {total:.1f} s at {w}×{h}). "
                           "Send a note asking for the whole song at that size.")
        ctx.update(stage="mux", message="Laying the song under it", progress=0.97)
        vid = uuid.uuid4().hex[:8]
        root = self.cfg.projects / pid
        out = self.folder(pid, film["id"]) / f"film-{vid}.mp4"
        await folder.ff(self.cfg, "-i", str(final), *(["-ss", f"{part['start']:.3f}"] if part else []),
                        "-i", str(root / take["files"]["flac"]), "-map", "0:v:0", "-map", "1:a:0",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-t", f"{total:.3f}", "-movflags", "+faststart", str(out))
        share = None
        if out.stat().st_size > 400_000_000:  # too big to post: a capped copy beside it
            ctx.update(stage="share", message="Making a lighter copy for sharing", progress=0.98)
            share = out.with_name(f"film-{vid}-share.mp4")
            await folder.ff(self.cfg, "-i", str(out), "-map", "0", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                            "-maxrate", "12M", "-bufsize", "24M", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart",
                            str(share))
        poster = None
        if (work / "out" / "poster.png").exists():
            poster = self.folder(pid, film["id"]) / f"poster-{vid}.png"
            shutil.copyfile(work / "out" / "poster.png", poster)
        readme = (work / "README.md").read_text()[:3000] if (work / "README.md").exists() else ""
        k0 = self.get(self.app.store.project(pid) or p)
        earlier = [*k0["videos"], *(k0.get("trash") or [])]  # the trash too, so a number is never used twice
        version = max([int(v.get("version") or 0) for v in earlier] + [0]) + 1  # counted across every attempt
        rec = {"id": vid, "film": film["id"], "version": version, "file": str(out.relative_to(root)),
               "share": str(share.relative_to(root)) if share else None, "poster": str(poster.relative_to(root)) if poster else None,
               "shape": film["shape"], "seconds": round(total, 2), "bytes": out.stat().st_size, "about": _about(readme),
               "model": film.get("model"), "effort": film.get("effort"), "opening": opening, "part": part, "at": time.time()}
        k = self.get(self.app.store.project(pid) or p)
        self.put(pid, videos=[rec, *k["videos"]][:12])
        return rec

    # ---- what makes this kind of film its own ---------------------------------------------------------------
    async def setup(self, ctx: Context, p: dict, take: dict, film: dict, work: Path) -> None:
        """The folder: the notes and tools (folder.seed), the song, and the app's measurements."""
        await folder.seed(self.cfg, work, self.rules(film))
        w, h = SHAPES[film["shape"]]
        await folder.song(self.cfg, p, take, work, {
            "title": p.get("title"), "artist": self.artist(p), "kind": self.META_KIND, "width": w, "height": h,
            "fps": self.fps(film), "duration": round(float(take.get("duration") or 0), 3), "genres": p.get("genres") or [],
            "moods": p.get("moods") or [], "feel": film.get("feel") or "", "about": (p.get("idea") or "")[:800]})
        ctx.update(stage="prepare", message="Reading the song's beat, sections and words", progress=0.03)
        self.film_changed(p["id"], message="Reading the song's beat, sections and words")
        await folder.measure(self.cfg, work)

    def artist(self, p: dict) -> str:
        return covers_mod.artist_of(p, self.app.covers.house_artist())

    def fps(self, film: dict) -> int:
        return FPS

    def timeout(self, film: dict) -> float:
        """How long one run may go on (a whole film with its review rounds)."""
        return TIMEOUT

    def max_turns(self, film: dict) -> int:
        return MAX_TURNS

    def rules(self, film: dict) -> Path:
        """The folder's notes (its CLAUDE.md, with MACHINE.md under them)."""
        return self.RULES

    def prompt_parts(self, film: dict) -> list[str]:
        """What follows the request in the first message (before the lyrics limit)."""
        return [IDEA_FIRST] if film.get("ideaFirst") else []

    def opening(self, p: dict, film: dict, work: Path) -> str:
        """The request when the person didn't write their own: their chat prompt, with the lyrics if the song has words."""
        by = f" by {self.artist(p)}" if self.artist(p) else ""
        sung = bool(json.loads((work / "song" / "timing.json").read_text()).get("lines"))
        return OPENING[film.get("lyrics", True) and sung].format(title=p.get("title"), by=by)

    def connectors(self, film: dict) -> list[str]:
        """The claude.ai connectors this film's session may use (the person's own MCP servers come on top)."""
        return self.CONNECTORS

    def chosen_servers(self, film: dict) -> list[str]:
        """MCP servers this film was set to make its pictures or clips with (they're given to it whatever else)."""
        return []

    async def helper(self, ctx: Context, pid: str, work: Path) -> None:
        """Runs beside the session (a music video's H3 renders); nothing for a motion graphics film."""

    async def handback(self, ctx: Context, p: dict, take: dict, film: dict, work: Path, started: float, runs: int,
                       reply: str) -> dict | None:
        """Something else the session may have left instead of the finished film (a music video's opening)."""
        return None

    async def after(self, ctx: Context, job: dict) -> None:
        if job["status"] in ("failed", "cancelled"):
            p = ctx.store.project(job["projectId"])
            film = self.get(p or {})["film"]
            if p and film and film.get("id") == job.get("filmId"):
                self.film_changed(job["projectId"], status="failed" if job["status"] == "failed" else "stopped",
                                  error=job.get("message"), message=job.get("message") or "Stopped.")


def register(sched, app, writers) -> Kinetic:
    k = Kinetic(app, writers)

    async def run(ctx: Context) -> dict:
        return await k.job(ctx)
    run.after = k.after  # type: ignore[attr-defined]
    sched.register(k.JOB, "studio", run)
    return k
