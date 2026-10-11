"""Song art that looks like a real record sleeve. A picture is made for the song (GPT Image 2.5 through Mitte, or
Krea 2 on your GPU), then the sleeve is set here: the title in widely spaced capitals in colors taken from the
picture, the artist under it when there is one, the label's logo and the app's. Words and logos are laid on by
us, never drawn by the model, so they are always spelled right and always the real logos.

The picture is kept beside the finished cover, so changing the title or the artist re-sets the sleeve in a
second without making a new picture.

Ported from the old app's title look (web/src/render/album.ts, titlelook.ts) and branding (server/sv/branding.py).
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import random
import re
import time
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

from . import look as look_mod, net
from . import localpics
from .catalog import choice_words, summary
from .writers import grok_media
from .config import ROOT
from .paths import under
from .jobs import Context, JobError, Scheduler
from .writers import Writers, WriterError

log = logging.getLogger("sv.covers")
SIZE = 3000
SMALL = 640
KINDS = {"mitte": "cover.mitte", "openai": "cover.openai", "grok": "cover.grok", "local": "cover.local"}
# ("local:<model>": cover.local too; anything else, "mcp:<id>": cover.mcp)
MITTE_TOOLS = ["mcp__claude_ai_Mitte__run_node", "mcp__claude_ai_Mitte__get_task", "mcp__claude_ai_Mitte__get_node_run"]
MITTE_INPUT = {"quality": "high", "size": "2K", "aspect_ratio": "1:1", "num_images": 1, "speed": "flare", "output_format": "png"}
MITTE_COST = 0.071  # USD, high at 2K, one picture (Mitte's price list, 2026-10)
MITTE_TRIES, MITTE_WAIT = 4, (5, 15, 40)  # when Mitte isn't connected yet: try again after 5 s, 15 s, 40 s
NOT_CONNECTED = re.compile(r"tools? (are|is) not available|not available in this session|still connecting|"
                           r"no (run_node|mitte) tool|not (been )?announced", re.I)
FONTS_DIR = Path(os.environ.get("SV_DATA") or ROOT / "data") / "fonts"  # (the Covers below pass the app's own)
STYLE_TAIL = " Square album cover art. No text, no letters, no logos, no watermark, no border."


# ---- the sleeve -------------------------------------------------------------------------------
# (the title, the artist and the logos are laid out by look.py, from the brand's look and the song's own: brand.py)

def square(art: Path, size: int) -> Image.Image:
    """The picture's middle square at size x size."""
    img = Image.open(art).convert("RGB")
    side = min(img.size)
    img = img.crop(((img.width - side) // 2, (img.height - side) // 2, (img.width + side) // 2, (img.height + side) // 2))
    return img.resize((size, size), Image.Resampling.LANCZOS)


def sleeve(picture: Image.Image, title: str, artist: str, logos: dict[str, Path], look: dict | None = None,
           fonts: Path | None = None) -> tuple[Image.Image, dict]:
    """Everything set over the picture, as one transparent layer the size of the picture: a soft scrim, the title, the
    artist and the logos (look.render). Laid over the still it's the cover; over the moving picture, a living cover's
    fixed top."""
    return look_mod.render(picture, title, artist, logos, look, fonts or FONTS_DIR)


def compose(art: Path, out: Path, title: str, artist: str, logos: dict[str, Path], small: Path | None = None,
            look: dict | None = None, fonts: Path | None = None) -> dict:
    """Set the sleeve: the picture at 3000 px with the sleeve laid over it."""
    picture = square(art, SIZE)
    layer, look = sleeve(picture, title, artist, logos, look, fonts)
    rgb = Image.alpha_composite(picture.convert("RGBA"), layer).convert("RGB")
    out.parent.mkdir(parents=True, exist_ok=True)
    rgb.save(out, "JPEG", quality=92, optimize=True, progressive=True)
    if small:
        rgb.resize((SMALL, SMALL), Image.Resampling.LANCZOS).save(small, "JPEG", quality=86, optimize=True)
    return look


# ---- making the picture ---------------------------------------------------------------------------

def artist_of(p: dict, house: str = "") -> str:
    """The song's artist: its own when one was set (blank included), else what its cover or its file said, else your
    artist name from Brand (songs made here)."""
    if isinstance(p.get("artist"), str):
        return p["artist"]
    return (p.get("cover") or {}).get("artist") or (p.get("source") or {}).get("artist") or house


class Covers:
    def __init__(self, app, writers: Writers):
        self.app, self.writers = app, writers
        self.cfg = app.cfg

    def logos(self) -> dict[str, Path]:
        return self.app.brand.logos()

    def look(self, p: dict | None) -> dict:
        """How this song's title, artist and logos sit: the brand's look with the song's own over it."""
        return self.app.brand.look(p)

    @property
    def fonts(self) -> Path:
        return self.cfg.data / "fonts"

    def house_artist(self) -> str:
        """Your artist name (Brand): on every song that has no artist of its own."""
        return self.settings()["artist"]

    def settings(self, statuses: dict[str, dict] | None = None) -> dict:
        """The covers' settings and the choices for pictures and clips; with `statuses` (the sign-ins), each choice says
        whether it's connected, so the interface offers only what works."""
        s = self.app.store.setting("covers") or {}
        choices = self.writers.image_choices(statuses)
        ids = [c["id"] for c in choices]
        covers = next((c for c in choices if c["id"] == self.writers.picture_by("covers")), {})
        return {"engine": self.writers.picture_by("covers"), "artist": s.get("artist") or "",  # Settings → Pictures
                # a cover with every song made from the Home prompt ("on" unless turned off), made as Settings says for
                # album covers: not when that may cost money (each paid job is asked about first)
                "auto": "off" if s.get("auto") == "off" else "on", "autoPaid": bool(covers.get("paid")),
                # exactly what Settings has chosen for each, in words (the interface shows it, nothing else)
                "madeWith": {role: self.writers.made_with(role) for role in ("covers", "scenes", "motion")},
                "choices": choices, "scenes": self.writers.picture_by("scenes"),  # (for the music video form)
                "motion": self.writers.motion_by(), "motionChoices": self.writers.motion_choices(statuses),
                # the model and settings chosen on an MCP server, for the "may charge your account" question
                "using": {role: self.writers.using(role) for role in ("covers", "scenes", "motion")}}

    def set_settings(self, engine: str | None = None, artist: str | None = None, auto: str | None = None) -> dict:
        s = self.app.store.setting("covers") or {}
        ids = self.writers.image_ids()
        if engine in ids and engine != self.writers.picture_by("covers"):  # (the same one keeps its model and settings)
            self.writers.set_who("covers", [{"provider": engine}])
        if auto in (*ids, "on", "off"):
            s["auto"] = "off" if auto == "off" else "on"
        if artist is not None:
            s["artist"] = artist.strip()[:60]
        self.app.store.set_setting("covers", s)
        return self.settings()

    def auto_engine(self) -> str | None:
        """What a song from the Home prompt gets its cover from: the album covers' choice in Settings, unless covers
        with every song are off, or that choice may cost money."""
        s = self.settings()
        return None if s["auto"] == "off" or s["autoPaid"] else s["engine"]

    def start(self, pid: str, engine: str | None = None, note: str = "", prompt: str = "", moving: bool = False,
              for_living: bool = False, auto: bool = False, by: dict | None = None, concept: str = "") -> dict:
        """A new picture. `moving`: designed to be brought to life (a living cover); `for_living`: it becomes the
        living cover's picture as soon as it's made; `auto`: painted for "Let Claude make it", which carries on
        when it's done."""
        engine = engine if engine in self.writers.image_ids() else self.writers.picture_by("covers")
        kind = "cover.local" if engine.startswith("local:") else KINDS.get(engine, "cover.mcp")
        return self.app.sched.submit(kind, {"message": "Imagining the picture" if moving else "Imagining the cover",
                                            "engine": engine, "note": note[:600], "prompt": prompt[:1400], "moving": moving,
                                            "forLiving": for_living, "auto": auto, "promptBy": by, "concept": concept[:300]}, pid)

    def upload(self, pid: str, src: Path, for_living: bool) -> dict:
        """Your own picture as the cover: brought up to 3000 px and set like any other."""
        return self.app.sched.submit("cover.upload", {"message": "Getting your picture ready", "upload": str(src),
                                                      "forLiving": for_living}, pid)

    def use(self, pid: str, n: int, for_living: bool = False) -> dict:
        """An earlier picture of this song becomes its cover again (the sleeve set with today's title)."""
        p = self.app.store.project(pid)
        old = next((c for c in (p or {}).get("covers") or [] if int(c.get("n", 0)) == n), None)
        if not p or not old or not self.own(pid, old["art"]).exists():
            raise JobError("That picture isn't here any more.")
        artist = artist_of(p, self.house_artist())
        root = self.cfg.projects / pid
        rev = int(time.time())
        out, small = self.folder(pid) / f"cover-{n}-{rev}.jpg", self.folder(pid) / f"cover-{n}-{rev}-sm.jpg"
        look = compose(self.own(pid, old["art"]), out, p["title"], artist, self.logos(), small, self.look(p), self.fonts)
        prev = p.get("cover") or {}
        for f in (prev.get("file"), prev.get("small")):
            if f:
                self.own(pid, f).unlink(missing_ok=True)
        cover = {**old, "rev": rev, "file": str(out.relative_to(root)), "small": str(small.relative_to(root)),
                 "title": p["title"], "artist": artist, "look": look}
        extra = {"living": living_picture(p.get("living"), n)} if for_living else {}
        return self.app.store.patch_project(pid, cover=cover, **extra)  # (runs in a thread: the caller publishes it)

    def thumb(self, pid: str, n: int) -> Path:
        """A picture of this song, small and without its title (for choosing between them)."""
        p = self.app.store.project(pid)
        c = next((c for c in (p or {}).get("covers") or [] if int(c.get("n", 0)) == n), None)
        if not c or not self.own(pid, c["art"]).exists():
            raise JobError("That picture isn't here any more.")
        out = self.folder(pid) / f"thumb-{n}.jpg"
        if not out.exists():
            square(self.own(pid, c["art"]), 480).save(out, "JPEG", quality=85)
        return out

    def folder(self, pid: str) -> Path:
        return self.cfg.projects / pid / "covers"

    def own(self, pid: str, rel: str) -> Path:
        """A file of this song's, by its path in the song's record: never one outside the song's folder."""
        f = under(self.cfg.projects / pid, rel)
        if f is None:
            raise JobError("That picture isn't this song's.")
        return f

    def reset(self, pid: str, artist: str | None = None) -> dict:
        """Set the sleeve again from the kept picture: after the title or the artist changed. Returns the project."""
        p = self.app.store.project(pid)
        cover = (p or {}).get("cover")
        if not cover:
            raise JobError("This song has no cover yet.")
        artist = artist_of(p, self.house_artist()) if artist is None else artist.strip()[:60]
        n = int(cover["n"])
        rev = int(cover.get("rev", 0)) + 1
        out = self.folder(pid) / f"cover-{n}-{rev}.jpg"
        small = self.folder(pid) / f"cover-{n}-{rev}-sm.jpg"
        look = compose(self.own(pid, cover["art"]), out, p["title"], artist, self.logos(), small, self.look(p),
                       self.fonts)
        for old in (cover.get("file"), cover.get("small")):
            if old and old not in (str(out.relative_to(self.cfg.projects / pid)), str(small.relative_to(self.cfg.projects / pid))):
                self.own(pid, old).unlink(missing_ok=True)
        cover = {**cover, "rev": rev, "artist": artist, "title": p["title"], "look": look,
                 "file": str(out.relative_to(self.cfg.projects / pid)), "small": str(small.relative_to(self.cfg.projects / pid))}
        return self.app.store.patch_project(pid, cover=cover)  # (runs in a thread: the caller publishes it)

    async def _prompt(self, ctx: Context, p: dict) -> tuple[str, dict]:
        if ctx.job.get("prompt"):  # yours, or written by Claude as art director ("Claude makes it")
            by = ctx.job.get("promptBy") or {"provider": "you"}
            return ctx.job["prompt"], {**by, **({"concept": ctx.job["concept"]} if ctx.job.get("concept") else {})}
        song = {"title": p.get("title"), "idea": p.get("idea"),
                "sound": ", ".join(x for x in (p.get("instruments"), p.get("extra")) if x)}
        try:
            r = await self.writers.write("cover", {"song": song, "genres": ", ".join(p.get("genres") or []),
                                                   "moods": ", ".join(p.get("moods") or []), "note": ctx.job.get("note"),
                                                   "moving": bool(ctx.job.get("moving"))})
        except WriterError as exc:
            raise JobError(f"Couldn't imagine the cover: {exc}") from None
        return r["result"]["prompt"], {**r["by"], "concept": r["result"]["concept"]}

    async def _mitte(self, ctx: Context, prompt: str, dest: Path) -> dict:
        """GPT Image 2.5 through Mitte, driven by Claude in the studio container (Mitte is connected to the user's
        Claude account there). Claude may call only Mitte's three run tools, and run_node only once.

        Self-healing: Claude waits for the connector before starting (providers.Claude), and if Mitte's tools still
        aren't there it says so without calling anything ("unavailable"), so trying again can't paint (or charge)
        twice: up to MITTE_TRIES times, waiting a little longer each time."""
        if not self.cfg.mitte:
            raise JobError("Mitte isn't turned on here: choose another way to make pictures in Settings.")
        claude = self.writers.providers["claude"]
        task_input = {**MITTE_INPUT, "prompt": prompt + STYLE_TAIL}
        schema = {"type": "object", "additionalProperties": False, "required": ["status", "urls", "error"],
                  "properties": {"status": {"type": "string", "enum": ["done", "error", "unavailable"]},
                                 "urls": {"type": "array", "items": {"type": "string"}}, "error": {"type": "string"}}}
        ask = ("Make exactly one picture with Mitte, then report where it is.\n"
               "0. If the Mitte tools (run_node, get_task, get_node_run) are not available to you, call nothing and "
               'answer {"status": "unavailable", "urls": [], "error": "the Mitte tools are not available"}.\n'
               f'1. Call run_node once, with slug "gpt-image-25" and exactly this input: {json.dumps(task_input)}\n'
               "2. Call get_task with the task id it returns, again and again, until the task has a node_run_id (or an error).\n"
               "3. Call get_node_run with that id, again and again, until its status is done, error or stopped.\n"
               "Never call run_node a second time, even if something seems slow or fails.\n"
               'Answer with {"status": "done", "urls": [the image file urls from the run\'s asset versions], "error": ""}, '
               'or {"status": "error", "urls": [], "error": "what Mitte said"}.')
        r: dict = {}
        for n in range(MITTE_TRIES):
            ctx.update(stage="paint", message="GPT Image 2.5 is painting it (Mitte)" if not n else
                       f"Mitte wasn't connected yet: trying again ({n + 1} of {MITTE_TRIES})", progress=0.3)
            try:
                r = await claude.complete("You operate the Mitte image service for an app. Use only the Mitte tools you are "
                                          "given, exactly as instructed, and answer only with the JSON asked for.",
                                          ask, schema, "claude-haiku-5-5", timeout=420, tools=MITTE_TOOLS, turns=60)
            except WriterError as exc:
                raise JobError(f"Mitte didn't make the picture: {exc}") from None
            if r.get("status") == "error" and not r.get("urls") and NOT_CONNECTED.search(str(r.get("error") or "")):
                r["status"] = "unavailable"  # said in words rather than with the status (as before 2026-10-09)
            if r.get("status") != "unavailable":
                break
            log.warning("Mitte's tools weren't available (try %d of %d)", n + 1, MITTE_TRIES)
            if n + 1 < MITTE_TRIES:
                await asyncio.sleep(MITTE_WAIT[n])
        if r.get("status") == "unavailable":
            raise JobError("Mitte didn't connect after several tries. Check that Mitte is still connected to your Claude "
                           "account (claude.ai → Settings → Connectors), then try again; or make this picture with Krea 2 on your GPU.")
        urls = [u for u in r.get("urls") or [] if isinstance(u, str) and u.startswith("https://")]
        if r.get("status") != "done" or not urls:
            raise JobError(f"Mitte didn't make the picture: {r.get('error') or 'no picture came back'}")
        ctx.update(stage="fetch", message="Fetching the picture", progress=0.8)
        try:
            res = await net.get(urls[0], most=40_000_000, timeout=60)
        except (net.UnsafeURL, httpx.HTTPError):
            raise JobError("The picture Mitte made couldn't be fetched.") from None
        if res.status_code != 200 or not res.headers.get("content-type", "").startswith("image/"):
            raise JobError("The picture Mitte made couldn't be fetched.")
        dest.write_bytes(res.content)
        return {"engine": "mitte", "model": "GPT Image 2.5", "cost": MITTE_COST, "source": urls[0]}

    async def _mcp(self, ctx: Context, prompt: str, dest: Path) -> dict:
        """One of the person's MCP servers: Claude (the small-chores model) uses its tools to make the picture, following
        a job to the end if the server works that way, and says where the picture is."""
        sid = str(ctx.job.get("engine") or "").removeprefix("mcp:")
        server = self.writers.mcp.get(sid)
        if server is None:
            raise JobError("That MCP server isn't in Settings any more: choose another for album covers.")
        step = self.writers.step("covers")  # the model and settings chosen there, when covers use this server
        step = step if step.get("provider") == f"mcp:{sid}" else {}
        ctx.update(stage="paint", message=f"{server['name']} is painting it", progress=0.3)
        url = await make_picture_with(self.writers, server, prompt + STYLE_TAIL, "1:1",
                                      choice_words(self.writers.catalogs, sid, "image", step))
        ctx.update(stage="fetch", message="Fetching the picture", progress=0.8)
        await fetch_picture(url, dest)
        made = summary(self.writers.catalogs, sid, "image", step)
        return {"engine": f"mcp:{sid}", "model": f"{server['name']}: {made}" if made else server["name"], "source": url}

    async def _openai(self, ctx: Context, prompt: str, dest: Path) -> dict:
        """ChatGPT's own image tool, under the user's ChatGPT plan (Sign in with ChatGPT, in Settings)."""
        ctx.update(stage="paint", message="ChatGPT is painting it", progress=0.3)
        try:
            dest.write_bytes(await self.writers.providers["openai"].picture(prompt + STYLE_TAIL, shape="1:1"))
        except WriterError as exc:
            raise JobError(f"ChatGPT didn't make the picture: {exc}") from None
        return {"engine": "openai", "model": "GPT Image 2 (ChatGPT)", "cost": 0}

    async def _grok(self, ctx: Context, prompt: str, dest: Path) -> dict:
        """Grok Imagine, under the person's Grok plan (Sign in with Grok, in Settings)."""
        ctx.update(stage="paint", message="Grok Imagine is painting it", progress=0.3)
        model = self.writers.grok_model("covers")
        try:
            data, _ = await grok_media.picture(self.writers.providers["grok"], prompt + STYLE_TAIL, "1:1", model=model)
        except WriterError as exc:
            raise JobError(f"Grok didn't make the picture: {exc}") from None
        await asyncio.to_thread(lambda: Image.open(io.BytesIO(data)).convert("RGB").save(dest))
        return {"engine": "grok", "model": self.writers.using("covers") or model, "cost": 0}

    async def _local(self, ctx: Context, prompt: str, dest: Path) -> dict:
        """One of the image models on this machine's GPU (sv/localpics.py): Krea 2 unless the choice names another."""
        m = localpics.of(str(ctx.job.get("engine") or "local"))
        seed = random.randrange(2**31)
        side = m.size("1:1")
        graph = m.graph(prompt + STYLE_TAIL, side[0], side[1], seed, "sv/cover")
        ctx.update(stage="paint", message=f"{m.name} is painting it", progress=0.3)

        def follow(ev: dict) -> None:
            if ev["type"] == "queued":
                ctx.prompt_id = ev["prompt_id"]
            elif ev["type"] == "progress" and ev.get("max") and ev.get("node") == m.sampler:
                ctx.update(progress=0.3 + 0.6 * ev["value"] / ev["max"])

        result = await ctx.comfy.run(graph, follow)
        files = result.files(m.out, "images")
        if not files:
            raise JobError(f"{m.name} didn't return a picture.")
        await ctx.comfy.download(files[0], dest)
        return {"engine": m.engine, "model": f"{m.name} Turbo", "seed": seed, "cost": 0}

    async def _upscale(self, ctx: Context, art: Path) -> Path:
        """Pictures come back at 1-1.5K; the sleeve is 3000 px. A 4x model (as the old app used) brings out real
        detail; if our ComfyUI can't do it now, the sleeve is scaled up the plain way instead."""
        try:
            if min(Image.open(art).size) >= SIZE:
                return art
            ctx.update(stage="upscale", message="Bringing it up to 3000 px", progress=0.85)
            name = await ctx.comfy.upload(art, subfolder="sv-covers")
            graph = {
                "1": {"class_type": "LoadImage", "inputs": {"image": name}},
                "2": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": "4x-ClearRealityV1.pth"}},
                "3": {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["2", 0], "image": ["1", 0]}},
                "4": {"class_type": "ImageScale", "inputs": {"image": ["3", 0], "upscale_method": "lanczos", "width": SIZE,
                                                             "height": SIZE, "crop": "center"}},
                "5": {"class_type": "SaveImage", "inputs": {"images": ["4", 0], "filename_prefix": "sv/cover-up"}},
            }
            result = await asyncio.wait_for(ctx.comfy.run(graph), 180)
            files = result.files("5", "images")
            if not files:
                return art
            up = art.with_name(art.stem + "-3000.png")
            await ctx.comfy.download(files[0], up)
            return up
        except Exception:  # the plain way still makes a good cover
            log.warning("upscaling %s failed; using the picture as it is", art, exc_info=True)
            return art

    async def run(self, ctx: Context) -> dict:
        pid = ctx.job["projectId"]
        p = ctx.store.project(pid)
        if p is None:
            raise JobError("That song was deleted.")
        folder = self.folder(pid)
        folder.mkdir(parents=True, exist_ok=True)
        n = max([int(c.get("n", 0)) for c in p.get("covers") or []] + [0]) + 1
        art = folder / f"art-{n}.png"
        if ctx.job.get("upload"):
            src = Path(ctx.job["upload"])
            try:
                await asyncio.to_thread(lambda: Image.open(src).convert("RGB").save(art))
            except (OSError, ValueError):
                raise JobError("That file couldn't be read as a picture.") from None
            finally:
                src.unlink(missing_ok=True)
            prompt, by, made = "", {"provider": "you"}, {"engine": "upload", "model": "Your picture", "cost": 0}
        else:
            ctx.update(stage="imagine", message="Imagining the picture", progress=0.05)
            prompt, by = await self._prompt(ctx, p)
            paint = {"cover.mitte": self._mitte, "cover.openai": self._openai, "cover.grok": self._grok,
                     "cover.mcp": self._mcp}.get(ctx.job["kind"], self._local)
            made = await paint(ctx, prompt, art)
            made["moving"] = bool(ctx.job.get("moving"))
        art = await self._upscale(ctx, art)
        ctx.update(stage="set", message="Setting the sleeve", progress=0.9)
        p = ctx.store.project(pid) or p
        artist = artist_of(p, self.house_artist())
        out, small = folder / f"cover-{n}-0.jpg", folder / f"cover-{n}-0-sm.jpg"
        look = await asyncio.to_thread(compose, art, out, p["title"], artist, self.logos(), small, self.look(p), self.fonts)
        root = self.cfg.projects / pid
        cover = {"n": n, "rev": 0, "art": str(art.relative_to(root)), "file": str(out.relative_to(root)),
                 "small": str(small.relative_to(root)), "title": p["title"], "artist": artist, "prompt": prompt,
                 "by": by, "made": made, "look": look, "at": time.time()}
        keep = ("n", "art", "prompt", "made", "by", "at")
        history = [{k: c[k] for k in keep if k in c} for c in (p.get("covers") or [])][-11:]
        extra = {"living": living_picture(p.get("living"), n)} if ctx.job.get("forLiving") else {}
        p = ctx.store.patch_project(pid, cover=cover, covers=[*history, {k: cover[k] for k in keep if k in cover}], **extra)
        ctx.hub.publish("project", p)
        return {"cover": cover["file"], "engine": made["engine"]}


PICTURE_ASK = """Make exactly one picture with the tools of the MCP server "{name}", then say where it is.
- The picture: {shape}, from this prompt (use it as it is):
<<<
{prompt}
>>>
{use}- Use the tool that makes a picture from a text prompt. If it starts a job rather than returning the picture, follow
  the job with the server's other tools until the picture is ready. Make one picture only, even if something seems
  slow or fails; never start a second one.
- If the server has no tools, or none that makes pictures, call nothing and answer with status "unavailable".
Answer with {{"status": "done", "url": "<the picture's https address>", "error": ""}}, or
{{"status": "error", "url": "", "error": "what went wrong"}}. If the picture came back only inside the tool's answer
(not as an address), say so in the error."""
USE = """- Make it with {choice}. The person chose these in Settings to control what it costs: use no other model and
  no other values for these settings (leave the rest at the server's defaults).
"""
PICTURE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["status", "url", "error"],
                  "properties": {"status": {"type": "string", "enum": ["done", "error", "unavailable"]},
                                 "url": {"type": "string"}, "error": {"type": "string"}}}
SHAPE_WORDS = {"1:1": "square", "16:9": "16:9 landscape", "9:16": "9:16 portrait", "4:5": "4:5 portrait", "3:2": "3:2 landscape"}


async def make_picture_with(writers: Writers, server: dict, prompt: str, shape: str, choice: str = "") -> str:
    """A picture from one of the person's MCP servers, made by Claude with that server's tools: its address. `choice`:
    the model and settings the person chose for it (sv/catalog.py's choice_words; "" for the server's default)."""
    step = (writers.who().get("chores") or [{}])[0]  # the small-chores model, when it's a Claude one
    try:
        r = await writers.providers["claude"].complete(
            "You make one picture for an app with the MCP tools you are given, exactly as asked, and answer only with the "
            "JSON asked for.", PICTURE_ASK.format(name=server["name"], shape=SHAPE_WORDS.get(shape, shape), prompt=prompt,
                                                 use=USE.format(choice=choice) if choice else ""),
            PICTURE_SCHEMA, step.get("model") if step.get("provider") == "claude" else None,
            timeout=600, tools=writers.mcp.allowed([server["id"]]), turns=60, mcp=await writers.mcp.claude_config([server["id"]]))
    except WriterError as exc:
        raise JobError(f"{server['name']} didn't make the picture: {exc}") from None
    if r.get("status") == "unavailable":
        raise JobError(f"{server['name']} has no tool that makes pictures (or it didn't connect).")
    url = str(r.get("url") or "")
    if r.get("status") != "done" or not url.startswith("https://"):
        raise JobError(f"{server['name']} didn't make the picture: {r.get('error') or 'no address came back'}")
    return url


async def fetch_picture(url: str, dest: Path) -> None:
    """A picture from where an image service put it: public https only, redirects checked (sv/net.py)."""
    try:
        res = await net.get(url, most=60_000_000)
    except (net.UnsafeURL, httpx.HTTPError):
        raise JobError("The picture couldn't be fetched from where the server put it.") from None
    if res.status_code != 200 or not res.headers.get("content-type", "").startswith("image/"):
        raise JobError("The picture couldn't be fetched from where the server put it.")
    dest.write_bytes(res.content)


krea_graph = localpics.krea_graph  # (moved to sv/localpics.py)


def living_picture(living: dict | None, n: int) -> dict:
    from .video.living import with_picture  # (living builds on covers: imported here, when it's needed)
    return with_picture(living, n)


def register(sched: Scheduler, app, writers: Writers) -> Covers:
    covers = Covers(app, writers)

    async def run(ctx: Context) -> dict:
        return await covers.run(ctx)

    async def after(ctx: Context, job: dict) -> None:
        # a picture painted for "Let Claude make it": the living cover carries on from here
        if job.get("auto") and job.get("projectId") and getattr(app, "living", None):
            app.living.auto_picture_done(job["projectId"], job)
    run.after = after  # type: ignore[attr-defined]
    sched.register("cover.mitte", "net", run)
    sched.register("cover.openai", "net", run)
    sched.register("cover.grok", "net", run)
    sched.register("cover.mcp", "net", run)
    sched.register("cover.local", "gpu", run)
    sched.register("cover.upload", "gpu", run)  # (the 4x upscale runs on our ComfyUI)
    return covers
