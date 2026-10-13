"""Music Video: the third kind of video, made like the Motion Graphics film (kinetic.py: one Claude Code conversation in
the studio, free rein, notes continue it), with pictures as the person chose and motion from MiniMax H3 on the GPU.

Three kinds, as the user defined them (2026-10-09): a performance video, a hybrid (performance or lip-sync with a story,
like the Dub Pistols' "Rapture"), and Surreal: no story and no performance, a stream of gorgeous imagery drawn from the
song, its words and the art and ideas behind it, people only as silhouettes, a title screen, no lyrics on screen.
Surreal comes first; the other two follow once its direction is right.

Claude makes the pictures the way the person chose (tools/picture.py, which the app answers, or one of their MCP
servers) and sends stills to H3 with tools/h3.py, which drops
a request in h3/queue/; the helper beside the session (Music.helper) renders them one at a time on our ComfyUI and
writes the clip and h3/done/<id>.json. By default Claude plans the whole video, makes the first 30 seconds
(out/opening.mp4) and stops; the person watches it, and "Make the rest" continues the same conversation.
"""

from __future__ import annotations

import asyncio
import io
import json
import math
import os
import random
import re
import shutil
import time
from pathlib import Path

import numpy as np
from PIL import Image

from ..catalog import choice_words
from ..comfy.client import ComfyError
from .. import localpics
from ..jobs import Context, JobError
from ..writers import WriterError, grok_media
from . import folder, h3
from .kinetic import Kinetic

HERE = Path(__file__).resolve().parent
KINDS = ("surreal", "performance", "hybrid")
SINGING = ("performance", "hybrid")  # made with VRGameDevGirl's Video Builder, the song locked into H3 so mouths sing it
SINGING_HOURS = 10  # at least; Rapture took about 4.5 hours of rendering
HOURS_PER_MINUTE = 2  # of song, for a whole film: Ahead (5 minutes, 49 scenes, 18 re-rolls) took 7.7 hours
VRGDG_SCRIPTS = {"song_plan.py", "build_prompts.py", "render_scenes.py", "qa_music.py", "cut_sheet.py", "assemble.py",
                 "continuity_frame.py", "retrim.py", "adopt_render.py", "save_refs.py", "check_env.py", "sync_check.py",
                 "gen_refs.py"}
VRGDG_GPU = {"render_scenes.py", "gen_refs.py"}  # one at a time
OPENING_SECONDS = 30
SIZE = (1344, 768)  # H3's 16:9 at its native detail (the film is scaled to 1920 × 1080)
# The person's brief for each kind, in their words (2026-10-09). Surreal's first wording ("draw it from the song itself:
# its words … and the art, literature and ideas behind it") made a literal, conventional video (a night river, a
# rowboat, Böcklin's island): good for a hybrid, they said, but Surreal is a visual treat, tangential to the song.
OPENINGS = {
    "surreal": ('Make a music video for "{title}"{by}, using the song in song/song.m4a, that is a pure visual treat and '
                "shows what an incredible visual artist you are. Not a conventional video: no story, no performance, no "
                "one singing, and no illustrating the lyrics or what the song is about. A surreal, visually stunning "
                "stream of imagination, with rich, complex, impossible images that move and transform into one another "
                "to the music. Let the music lead: its mood, its rhythm, its texture. Any link to the words or the "
                "ideas behind the song is tangential, a spark at most, never the subject. People appear only as "
                "silhouettes, shadows or shapes, never as realistic people. Open on a title screen with the song's "
                "title and the artist; no lyrics on screen. Make the pictures (see Pictures in your notes) and bring them to "
                "life with MiniMax H3 (tools/h3.py). Go all out."),
    # the user's words (2026-10-09): "primarily a performance piece", on a stage or not
    "performance": ('Make a performance music video for "{title}"{by}, using the song in song/: an original performer or '
                    "band performing the whole song, lip-syncing every sung line in time with the real vocal, filmed the "
                    "way a great music video is, with a look, a place and camera work all of your choosing, on a stage or "
                    "anywhere, cut to the music. Invent the performers: never the real artist. The place, the look and "
                    "anything around the performance come from the music and an idea of your own, not from acting out "
                    "the words: a line about rain is not a rainy street. Open on a title screen with the song's title and "
                    "the artist; no lyrics on screen. Make the pictures (see Pictures in your notes) and "
                    "the scenes with VRGameDevGirl's Video Builder and MiniMax H3 (tools/vrgdg.py, its guide in "
                    "reference/SKILL.md), the way the Rapture video was made. Go all out."),
    # "performances, or at least lip syncing, along with maybe a story": the Dub Pistols' "Rapture"
    "hybrid": ('Make a hybrid music video for "{title}"{by}, using the song in song/: a story, or striking imagery, '
               "intercut with an original performer lip-syncing the song in time with the real vocal, the way the Dub "
               "Pistols' \"Rapture\" does it. The story and the look are yours to invent; never the real artist. Don't "
               "translate the lyrics into pictures: the words are a spark, never a script. Don't build the world out of "
               "their nouns (a line about rain is not a rainy street), and don't let the first verse set the story for "
               "the whole song. Find something less on the nose, an idea or a feeling the song suggests sideways, that "
               "still feels right with it. Open on a title screen with the song's title and the artist; no lyrics on screen. Make the pictures (see Pictures in your notes) "
               "and the scenes with VRGameDevGirl's Video Builder and MiniMax H3 (tools/vrgdg.py, its guide in "
               "reference/SKILL.md), the way the Rapture video was made. Go all out."),
}
# A video the person loves for its level of imagination (data/references/<kind>-example.mp4), given as a benchmark
EXAMPLE = ("\n## An example the person loves\n\n`reference/example.mp4` is a short video the person loves for its level "
           "of imagination: not a conventional video, every shot a visual treat, one thing becoming another. It's a "
           "benchmark for how far to go, not a look to copy: make something entirely yours, with its own world, "
           "materials, palette and motifs. (Look at it through frames: `ffmpeg -i reference/example.mp4 -vf fps=1 "
           "out/tmp/ex%02d.png`.)\n")
# A part of the song on its own (a trailer's, or a clip's): made first, like the opening, and "Make the rest" carries on
PART = ("Plan the whole video for the whole song first, so this part belongs to it. Then make only the part of the "
        "song from {a} to {b} ({where}), {seconds} seconds, as out/opening.mp4: its picture is that stretch of the "
        "video, and its sound is song/song.m4a from {a} to {b}. This part will be shown on its own (in a trailer for "
        "the app), so skip the title screen and start right on the music. Stop there: the person will watch it before "
        "you make the rest.")
FIRST = ("Plan the whole video for the whole song first. Then make only its first {seconds} seconds, title screen "
         "included, as out/opening.mp4, and stop there: the person will watch it to see the direction before you make "
         "the rest.")


# How the pictures are made, as the person chose for this video (Settings → Pictures for music videos), written into
# the notes' Pictures section when the video starts: tools/picture.py (ChatGPT's image tool, Grok Imagine, or one of
# the image models on the GPU, made by the app), one of their MCP servers (Claude uses its tools), or, where the owner
# turned it on, their Mitte.
PICTURE_SIZES = {"16:9": (1344, 768), "1:1": (1280, 1280), "9:16": (768, 1344), "4:5": (1024, 1280), "3:2": (1344, 896)}
PICTURE_TOOL = """The person chose {name} for this video's pictures (in Settings), so make every picture with `tools/picture.py`.
The app makes it and puts it where you say:

    python3 tools/picture.py "PROMPT" --out shots/s01.png [--shape 16:9] [--ref characters/lead.png ...]

Send several with `--no-wait`, then collect them with `--wait ID ...`; `python3 tools/picture.py --help` has the rest.
{refs} {cost}"""
REFS_KEPT = "`--ref` keeps a person, place or thing the same across pictures (up to five references)."
NO_REFS = ("{name} takes no reference pictures, so describe a recurring person or place the same way, in detail, every "
           "time.")


def picture_maker(by: str) -> tuple[str, str, str] | None:
    """Who makes a video's pictures through tools/picture.py: (their name in the notes, what --ref does, what they
    cost); None when the app doesn't make them (an MCP server or Mitte: Claude does)."""
    if by == "openai":
        return ("ChatGPT's image tool (GPT Image 2), on their ChatGPT plan", REFS_KEPT,
                "They come from the person's ChatGPT plan, which has a limit on pictures: make the ones you need.")
    if by == "grok":
        return ("Grok Imagine, on their Grok plan", REFS_KEPT.replace("up to five", "up to three"),
                "They come from the person's Grok plan, which has limits: make the ones you need.")
    if by == "local" or by.startswith("local:"):
        m = localpics.of(by)
        return (f"{m.name} on this machine's GPU", REFS_KEPT if m.refs else NO_REFS.format(name=m.name),
                "They're free, and take about a quarter to half a minute each on the GPU (between H3 clips).")
    return None
PICTURE_MCP = """The person chose their MCP server "{name}" for this video's pictures (in Settings): its tools are yours
(`mcp__{slug}__…`). Make every picture with its tool that makes pictures from a prompt; if that starts a job, follow the
job with the server's other tools until the picture is ready, then download it into this folder with `curl`.{paid}"""
MITTE = {"surreal": """Your Mitte tools are the person's Mitte account, connected to Claude: `search_nodes` and `get_node` show the models
and their inputs, `run_node` makes a picture, `get_task` and `get_node_run` follow it until it's done, and the run's
asset versions carry the file URLs (download them with `curl`). `upload_files` sends a picture of yours to Mitte, for
models that take references. The person usually uses GPT Image 2.5 (slug `gpt-image-25`). Every picture costs the
person money (GPT Image 2.5 at 2K: about $0.07 at high quality, about $0.28 at max), so make the ones you need.""",
         "singing": """Your Mitte tools are the person's Mitte account, connected to Claude: `search_nodes` and `get_node` show the models
and their inputs, `run_node` makes a picture, `get_task` and `get_node_run` follow it until it's done, and the run's
asset versions carry the file URLs. `save_refs.py` files them into the project (see the guide). The person usually uses
GPT Image 2.5 (slug `gpt-image-25`). The guide notes that Nano Banana 2.1 holds a person across pictures. Every picture
costs the person money (GPT Image 2.5 at 2K: about $0.07 at high quality, about $0.28 at max), so make the ones you
need."""}
PICTURE_WHERE = {"surreal": "Keep your pictures in `shots/`: the person sees the newest ones there while you work.",
                 "singing": "The performers are original characters you invent: never the real artist, never a real person."}


# How the clips are made (Surreal), as the person chose (Settings → Animating scenes): MiniMax H3 on the GPU through
# tools/h3.py, one of their MCP servers, or, where the owner turned it on, hosted H3 through their Mitte.
H3_MOTION = """H3 runs on the machine's GPU through the app. A still is the clip's first frame, and the prompt says what happens:

    python3 tools/h3.py shots/s01.png "what happens, how the camera moves" --seconds 6 --out clips/s01.mp4

- It waits and prints the result as JSON. `--no-wait` sends it and prints an id at once, and `--wait ID …` collects
  them. `--prompt-file` takes the prompt from a file, and `python3 tools/h3.py --help` shows the rest.
- `--end shots/s02.png` pins the last frame too, so the clip travels from one picture to the other: one thing
  turning into another, or a transition.
- 1 to 15 seconds (`--seconds`). Clips are 1344 × 768 by default (`--size`; multiples of 32, up to 1536 a side), at
  24 fps, with no sound. Stills are
  scaled and centre-cropped to that size. The app renders one clip at a time, in the order sent: about 90 seconds for
  a 6-second clip.
- What's been seen of H3:
  - Given more than about 8 seconds, it tends to cut to a new shot partway through: 7 of 12 twelve-second clips cut,
    against 1 of 9 six-second clips. For a long take, say it's one continuous shot with no cuts, look through it, and
    render it again with another `--seed` if it cut.
  - It follows plain descriptions of motion and camera moves.
  - It can add things that weren't asked for, such as faces, hands or lettering.
  - Each render is different: the same still and prompt with another `--seed` gives another take."""
MITTE_MOTION = """The person chose hosted H3 through Mitte for this video's clips (in Settings), so make each clip with your Mitte
tools, not tools/h3.py:

- `run_node` with slug `h3-max`, in frame mode: `{"frame_mode": true, "image_url": "<the still's https address>",
  "prompt": "what happens, how the camera moves", "duration": 5, "resolution": "768P"}`. Add `"end_image_url"` to pin
  the last frame too (one thing turning into another). The clip takes the still's shape.
- Mitte fetches the still from its address, so it must be a picture Mitte made (its asset version's URL): keep each
  picture's URL beside it (`shots/urls.json`). A still that exists only as a file here can't be sent: animate those
  with `python3 tools/h3.py` on the GPU instead.
- Follow the run with `get_task` and `get_node_run` until it's done, then download the video into `clips/` with `curl`.
- 5 to 15 seconds, whole seconds. The clip comes with sound of its own: drop it (the music goes in at the end).
  It costs the person money: about $0.04 a
  second at 768P, $0.025 at 480P, so a 5-second clip is about 20¢. Make the clips you need, and keep them short."""
GROK_MOTION = """The person chose Grok Imagine for this video's clips (in Settings). The app makes them with Grok, through the
same tool as H3 (`tools/h3.py`), and puts each where you say:

    python3 tools/h3.py shots/s01.png "what happens, how the camera moves" --seconds 6 --out clips/s01.mp4

- A still is the clip's first frame. `--end shots/s02.png` pins the last frame too, for one thing turning into another.
- 1 to 15 whole seconds. Clips are 720p (1280 × 720 at 16:9), at 24 fps; the shape follows `--size` (16:9, 9:16,
  1:1, 4:3 or 3:4, the nearest), and the clip's own sound is dropped (the music goes in at the end).
- About 40 seconds a clip, one at a time, in the order sent. `--no-wait` and `--wait ID …` work as they do for H3.
- They come from the person's Grok plan, which has limits: make the clips you need, and keep them short."""
MCP_MOTION = """The person chose their MCP server "{name}" for this video's clips (in Settings): its tools are yours
(`mcp__{slug}__…`). Make each clip with its tool that turns a still into video, with the still as the first frame. If
it needs the still at an address and you have only a file here, try a `data:` URL; if that's refused, animate that
still with `python3 tools/h3.py` on the GPU instead and say so. Follow any job to the end, and download each clip into
`clips/` with `curl`.{paid}"""


# The person's finding on "Tears" (2026-10-13): wherever one clip carried on from another (29 joins), the motion
# shifted at the join. H3 starts each clip from its still at rest; pinned ends slow to a stop; trims skipped frames or
# showed the shared picture twice. Smoothing the film's own frames fixed joins where the camera kept going (they
# approved the window join); where it turned, only one clip for the whole move hides it.
JOINS = """## Joins

H3 starts every clip from its first picture at rest and sets off its own way. So wherever one clip carries on from
another, the motion changes at the join: the camera stops and lurches, or turns. The person sees every one of these,
and they spoil the video. The app checks every join you hand back.

- Keep a continuous camera move in one clip: up to 15 seconds is one clip. A turn, a stop or a change of speed
  happens inside a clip, never at a join.
- Where a move has to go on into another clip, the camera must keep going the same way. Start the next clip on the
  exact last frame the video shows of the one before, and show every frame across the join: don't trim the end of one
  or the start of the next, don't show the shared picture twice, and don't play a clip backwards there. A clip pinned
  to end on a picture slows to a stop on it, so a move that goes on past that picture needs its join smoothed.
- Smooth each chain of clips that continue one another with `python3 tools/joins.py smooth` (`--help` says how). It
  re-times the frames through each join so the speed flows on, and smooths the camera's path, using the clips' own
  frames; play the clips it writes in their place. If it says the camera turns at a join, make that move one clip.
- A cut to a new picture is fine. A join that looks continuous and isn't is never fine.
- With every video you hand back, write `out/joins.json`: `{"joins": [12.5, 36.917]}`, the second in that video of
  every place where one clip carries on from another (the first frame of the one that carries on), and nothing for
  cuts. Check them with `python3 tools/joins.py check out/final.mp4 --joins out/joins.json` (or `out/opening.mp4`)
  before you hand back: the app runs the same check and sends you back to fix any that fail."""


NO_JOINS_LIST = ("There's no out/joins.json for the video you handed back (or it can't be read), so the app couldn't check "
                 "its joins. Write it as the Joins notes say (the second of every place one clip carries on from another; "
                 "an empty list if there are none), check them with tools/joins.py, and hand the video back again.")
FIX_JOINS = ("The app checked the joins in {video}: {failed} of the {checked} listed don't pass.\n{lines}\n"
             "Fix each as the Joins notes say (smooth it, or make that move one clip), keep everything else as it is, "
             "and hand the video back again with out/joins.json up to date.")


USE = """

Make every {what} with {choice}. The person chose these in Settings to control what the video costs: use no other model
and no other values for these settings (leave the rest at the server's defaults). If a {what} needs something they
don't allow, say so in your notes rather than changing them."""


def motion_section(by: str, server: dict | None = None, use: str = "") -> str:
    """The Surreal notes' Motion section for this video. `use`: the model and settings the person chose on their MCP
    server (sv/catalog.py's choice_words)."""
    return _motion_section(by, server, use)


def _motion_section(by: str, server: dict | None = None, use: str = "") -> str:
    if by == "mitte":
        return f"## Motion: hosted H3 (Mitte)\n\n{MITTE_MOTION}\n"
    if by == "grok":
        return f"## Motion: Grok Imagine (`tools/h3.py`)\n\n{GROK_MOTION}\n"
    if server:
        from ..mcp import slug
        return "## Motion: " + server["name"] + "\n\n" + MCP_MOTION.format(
            name=server["name"], slug=slug(server["name"]),
            paid=" Every clip may cost the person money, so make the ones you need." if server.get("paid") else "") + \
            (USE.format(what="clip", choice=use) if use else "") + "\n"
    return f"## Motion: MiniMax H3 (`tools/h3.py`)\n\n{H3_MOTION}\n"


def with_joins(notes: str) -> str:
    """The notes with the Joins section as it is now: in place of the old one, or before Hand back."""
    head, sep, rest = notes.partition("\n## Joins")
    if sep:
        tail = rest[rest.find("\n## "):] if "\n## " in rest else ""
        return head + "\n" + JOINS + "\n" + tail
    head, sep, rest = notes.partition("\n## Hand back")
    if sep:
        return head.rstrip("\n") + "\n\n" + JOINS + "\n" + sep + rest
    return notes.rstrip("\n") + "\n\n" + JOINS + "\n"


def pictures_section(by: str, singing: bool, server: dict | None = None, use: str = "") -> str:
    """The notes' Pictures section for this video. `use`: as motion_section's."""
    kind = "singing" if singing else "surreal"
    if (maker := picture_maker(by)):
        body = PICTURE_TOOL.format(name=maker[0], refs=maker[1], cost=maker[2])
        if singing:
            body += "\n\nPictures land as files in this folder: file them into the project where the guide puts downloaded references."
    elif by == "mitte":
        body = MITTE[kind]
    elif server:
        from ..mcp import slug
        body = PICTURE_MCP.format(name=server["name"], slug=slug(server["name"]),
                                  paid=" Every picture may cost the person money, so make the ones you need." if server.get("paid") else "")
        if use:
            body += USE.format(what="picture", choice=use)
    else:
        maker = picture_maker("local")
        assert maker
        body = PICTURE_TOOL.format(name=maker[0], refs=maker[1], cost=maker[2])
    return f"## Pictures\n\n{body}\n\n{PICTURE_WHERE[kind]}\n"


class Music(Kinetic):
    KEY, JOB = "music", "music.film"
    RULES = HERE / "SURREAL.md"
    CONNECTORS = ["mcp__claude_ai_Mitte"]
    PEEK = ("out", "shots", "frames", "characters", "storyboard", "logs/qa")  # (the Builder's pictures and review sheets)
    META_KIND = "music video"
    GO = ("The person likes the direction. Now make the rest, all the way to the finished video for the whole song "
          "(out/final.mp4). Go all out.")

    def start(self, pid: str, request: str = "", feel: str = "", kind: str = "surreal", opening: bool = True,
              model: str | None = None, effort: str | None = None, part: dict | None = None) -> dict:  # type: ignore[override]
        if kind not in KINDS:
            raise JobError("Choose a kind of music video: performance, hybrid or surreal.")
        extra: dict = {"kind": kind, "opening": bool(opening or part)}
        if part:
            _, take = self._ready(pid)
            a, b = float(part.get("start") or 0), float(part.get("end") or 0)
            length = float(take.get("duration") or 0)
            if not (0 <= a < b <= length + 0.05) or not 5 <= b - a <= 120:
                raise JobError("Choose a part of the song between 5 seconds and 2 minutes long.")
            extra["part"] = {"start": round(a, 3), "end": round(min(b, length), 3), "label": str(part.get("label") or "")[:60]}
        extra["pictures"] = self.writers.picture_by("scenes")  # fixed for this film, notes and all
        extra["picturesWith"] = self._with("scenes")
        if kind not in SINGING:  # (the singing kinds film every scene through the Video Builder)
            extra["motion"] = self.writers.motion_by()
            extra["motionWith"] = self._with("motion")
        return self._new(pid, request, feel, "wide", model, effort, **extra)

    def _with(self, role: str) -> dict:
        """The model and settings chosen for a role on an MCP server ({} for its own default, or another provider)."""
        step = self.writers.step(role)
        keep = str(step.get("provider")).startswith("mcp:") or step.get("provider") == "grok"
        return {k: step[k] for k in ("model", "options") if step.get(k)} if keep else {}

    def pictures(self, film: dict) -> str:
        """Who makes this video's pictures: as chosen when it started (a film from before the choice existed: Mitte where
        it's on, else the GPU)."""
        by = film.get("pictures") or ("mitte" if self.cfg.mitte else "local")
        return by if by != "mitte" or self.cfg.mitte else "local"

    def motion(self, film: dict) -> str:
        """Who makes this video's clips (Surreal): as chosen when it started; H3 on the GPU before the choice existed."""
        by = film.get("motion") or "local"
        return by if by != "mitte" or self.cfg.mitte else "local"

    def connectors(self, film: dict) -> list[str]:
        return self.CONNECTORS if "mitte" in (self.pictures(film), self.motion(film)) else []

    def chosen_servers(self, film: dict) -> list[str]:
        return [by.removeprefix("mcp:") for by in (self.pictures(film), self.motion(film)) if by.startswith("mcp:")]

    def rules(self, film: dict) -> Path:
        return HERE / ("VRGDG.md" if film.get("kind") in SINGING else "SURREAL.md")

    def timeout(self, film: dict) -> float:
        if film.get("kind") not in SINGING:
            return super().timeout(film)
        return max(SINGING_HOURS, HOURS_PER_MINUTE * float(film.get("songSeconds") or 0) / 60) * 3600

    def max_turns(self, film: dict) -> int:
        return 2000 if film.get("kind") in SINGING else super().max_turns(film)

    def fps(self, film: dict) -> int:
        return h3.FPS

    def opening(self, p: dict, film: dict, work: Path | None = None) -> str:
        by = f" by {self.artist(p)}" if self.artist(p) else ""
        return OPENINGS[film.get("kind") or "surreal"].format(title=p.get("title"), by=by)

    def prompt_parts(self, film: dict) -> list[str]:
        part = film.get("part")
        if part:
            a, b = part["start"], part["end"]
            return [PART.format(a=_clock(a), b=_clock(b), seconds=round(b - a, 1), where=part.get("label") or "the part chosen")]
        return [FIRST.format(seconds=OPENING_SECONDS)] if film.get("opening") else []

    async def setup(self, ctx: Context, p: dict, take: dict, film: dict, work: Path) -> None:
        singing = film.get("kind") in SINGING
        film["songSeconds"] = float(take.get("duration") or 0)  # the time limit grows with the song
        self.film_changed(p["id"], songSeconds=film["songSeconds"])
        if singing:  # the folder is a Video Builder project, where her ComfyUI can see it
            await self._vrgdg_project(ctx, p, film, work)
        await super().setup(ctx, p, take, film, work)
        if singing:
            await self._vrgdg_song(ctx, p, take, film, work)
        example = self.cfg.data / "references" / f"{film.get('kind') or 'surreal'}-example.mp4"
        if example.is_file():
            (work / "reference").mkdir(exist_ok=True)
            shutil.copyfile(example, work / "reference" / "example.mp4")
            notes = (work / "CLAUDE.md").read_text()
            head, sep, rest = notes.partition("\n## Pictures")
            (work / "CLAUDE.md").write_text(head + EXAMPLE + sep + rest)
        by = self.pictures(film)
        notes = (work / "CLAUDE.md").read_text()
        head, sep, rest = notes.partition("\n## Pictures")
        if sep:
            tail = rest[rest.find("\n## "):] if "\n## " in rest else ""
            server = self.writers.mcp.get(by.removeprefix("mcp:")) if by.startswith("mcp:") else None
            use = choice_words(self.writers.catalogs, server["id"], "image", film.get("picturesWith")) if server else ""
            (work / "CLAUDE.md").write_text(head + "\n" + pictures_section(by, singing, server, use) + tail)
        self._app_parts(film, work)
        for d in ("shots", "clips", "h3/queue", "h3/done", "pictures/queue", "pictures/done"):
            (work / d).mkdir(parents=True, exist_ok=True)
        if singing:
            for d in ("vrgdg/queue", "vrgdg/done", "vrgdg/logs"):
                (work / d).mkdir(parents=True, exist_ok=True)

    async def verify(self, ctx: Context, p: dict, film: dict, work: Path, video: Path) -> str | None:
        """The app's own check of a video handed back: every join listed in out/joins.json, measured by
        tools/joins.py. A note for the director when something must be fixed, or None."""
        listed = work / "out" / "joins.json"
        if not listed.exists() or listed.stat().st_mtime < video.stat().st_mtime - 3600:
            return NO_JOINS_LIST
        ctx.update(stage="check", message="Checking the joins", progress=None)
        self.film_changed(p["id"], message="Checking the joins")
        report = work / "out" / "tmp" / "joins-check.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.unlink(missing_ok=True)
        try:
            await folder.studio(self.cfg, "exec", str(work), "sh", "-c",
                                f"cd /work && PYTHONUSERBASE=/work/.local python3 tools/joins.py check "
                                f"{video.relative_to(work)} --joins out/joins.json --json > out/tmp/joins-check.json || true",
                                timeout=1800)
            data = json.loads(report.read_text())
            joins = data["joins"]
        except (JobError, OSError, ValueError, KeyError, TypeError):
            if listed.exists():
                try:
                    json.loads(listed.read_text())
                except ValueError:
                    return NO_JOINS_LIST
            self.film_changed(p["id"], joinsCheck={"error": "The joins couldn't be checked.", "at": time.time()})
            return None  # the check itself didn't work: the video isn't held back for that
        bad = [j for j in joins if not j.get("ok")]
        self.film_changed(p["id"], joinsCheck={"checked": len(joins), "failed": [{"at": j["at"], "why": j.get("why")} for j in bad],
                                               "at": time.time()})
        if not bad:
            return None
        return FIX_JOINS.format(failed=len(bad), checked=len(joins), video=video.relative_to(work),
                                lines="\n".join(f"- {_clock(j['at'])} ({j['at']} s): {j.get('why')}" for j in bad))

    async def refresh(self, ctx: Context, p: dict, film: dict, work: Path) -> None:
        """Before a note: the app's own tools and Motion notes as they are now, so a video made earlier gets what has
        been learned since (the Joins notes and tools/joins.py came after "Tears" was made)."""
        if (work / "CLAUDE.md").exists():
            self._app_parts(film, work)

    def _app_parts(self, film: dict, work: Path) -> None:
        """What the app owns in the folder: the Motion and Joins notes and the tools it answers or ships."""
        clips = self.motion(film)
        notes = (work / "CLAUDE.md").read_text()
        head, sep, rest = notes.partition("\n## Motion")
        if sep:
            tail = rest[rest.find("\n## "):] if "\n## " in rest else ""
            server = self.writers.mcp.get(clips.removeprefix("mcp:")) if clips.startswith("mcp:") else None
            use = choice_words(self.writers.catalogs, server["id"], "video", film.get("motionWith")) if server else ""
            notes = head + "\n" + motion_section(clips, server, use) + tail
        (work / "CLAUDE.md").write_text(with_joins(notes))
        (work / "tools").mkdir(exist_ok=True)
        shutil.copyfile(HERE / "h3tool.py", work / "tools" / "h3.py")
        shutil.copyfile(HERE / "picturetool.py", work / "tools" / "picture.py")
        shutil.copyfile(HERE / "jointool.py", work / "tools" / "joins.py")
        if film.get("kind") in SINGING:
            shutil.copyfile(HERE / "vrgdgtool.py", work / "tools" / "vrgdg.py")

    async def handback(self, ctx: Context, p: dict, take: dict, film: dict, work: Path, started: float, runs: int,
                       reply: str) -> dict | None:
        first = work / "out" / "opening.mp4"
        if not (first.exists() and first.stat().st_mtime >= started):
            return None
        rec = await self._keep(ctx, p, take, film, work, first, runs, opening=True)
        self.film_changed(p["id"], reply=reply, video=rec["id"], error=None)
        if await self._send_back(ctx, p, film, work, first):
            return {"video": rec["id"], "opening": True, "sentBack": True}
        ready = "The part is ready" if film.get("part") else "The opening is ready"
        self.film_changed(p["id"], status="waiting", message=ready + self.done_message(p["id"]).removeprefix("Done"))
        return {"video": rec["id"], "opening": True}

    # ---- H3 and the Video Builder, beside the session --------------------------------------------------------
    async def helper(self, ctx: Context, pid: str, work: Path) -> None:
        film = self.get(self.app.store.project(pid) or {})["film"] or {}
        pictures = self._picture_loop(ctx, pid, work, self.pictures(film), film.get("picturesWith") or {})
        if film.get("kind") not in SINGING:
            return await asyncio.gather(self._h3_loop(ctx, pid, work, self.motion(film)), pictures)
        try:
            await asyncio.gather(self._h3_loop(ctx, pid, work, "local"), pictures, self._vrgdg_loop(work, film))
        finally:  # the session is over (or stopped): nothing of it keeps running in her ComfyUI
            await self._vrgdg_stop(film)

    async def _h3_loop(self, ctx: Context, pid: str, work: Path, by: str = "local") -> None:
        """Renders what tools/h3.py asks for, one clip at a time, in the order asked, for as long as the session runs:
        with H3 on our ComfyUI, or with Grok Imagine when the video's clips are Grok's (`by`)."""
        queue, done = work / "h3" / "queue", work / "h3" / "done"
        while True:
            asks = sorted(queue.glob("*.json"), key=lambda f: f.stat().st_mtime) if queue.is_dir() else []
            if not asks:
                await asyncio.sleep(2)
                continue
            ask = asks[0]
            rid = ask.stem
            try:
                req = json.loads(ask.read_text())
            except (OSError, ValueError):
                req = None
            ask.unlink(missing_ok=True)
            try:
                if not isinstance(req, dict):
                    raise JobError("The request wasn't readable JSON.")
                answer = {"ok": True, **await (self._grok_clip(pid, work, rid, req) if by == "grok" else
                                               self._render(ctx, pid, work, rid, req))}
            except (JobError, ComfyError) as exc:
                answer = {"ok": False, "error": exc.message}
            except OSError as exc:
                answer = {"ok": False, "error": f"A file couldn't be read or written: {exc}"}
            reply(work, done, f"{rid}.json", answer)

    async def _picture_loop(self, ctx: Context, pid: str, work: Path, by: str, use: dict | None = None) -> None:
        """Makes what tools/picture.py asks for, one picture at a time, in the order asked, while the session runs."""
        queue, done = work / "pictures" / "queue", work / "pictures" / "done"
        while True:
            asks = sorted(queue.glob("*.json"), key=lambda f: f.stat().st_mtime) if queue.is_dir() else []
            if not asks:
                await asyncio.sleep(2)
                continue
            ask = asks[0]
            try:
                req = json.loads(ask.read_text())
            except (OSError, ValueError):
                req = None
            ask.unlink(missing_ok=True)
            try:
                if not isinstance(req, dict):
                    raise JobError("The request wasn't readable JSON.")
                answer = {"ok": True, **await self._picture(ctx, pid, work, ask.stem, req, by, use or {})}
            except (JobError, ComfyError) as exc:
                answer = {"ok": False, "error": exc.message}
            except WriterError as exc:
                answer = {"ok": False, "error": str(exc)}
            except OSError as exc:
                answer = {"ok": False, "error": f"A file couldn't be read or written: {exc}"}
            reply(work, done, f"{ask.stem}.json", answer)

    async def _picture(self, ctx: Context, pid: str, work: Path, rid: str, req: dict, by: str, use: dict | None = None) -> dict:
        use = use or {}  # the model chosen for them in Settings (Grok's), fixed when the video started
        root = work.resolve()

        def inside(rel: object, what: str, must_exist: bool = True) -> Path:
            path = (root / str(rel or "")).resolve()
            if root not in path.parents:
                raise JobError(f"The {what} must be a file in this folder.")
            if must_exist and not path.is_file():
                raise JobError(f"There's no {what} at {rel}.")
            return path
        if not picture_maker(by):
            raise JobError("This video's pictures aren't made by the app: make them as the Pictures notes say.")
        out = inside(req.get("out"), "output", must_exist=False)
        if out.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            raise JobError("The output must be a .png or .jpg file.")
        shape = req.get("shape") if req.get("shape") in PICTURE_SIZES else "16:9"
        refs = [inside(r, "reference picture") for r in (req.get("refs") or [])[:5]]
        text = " ".join(str(req.get("prompt") or "").split())
        if not text or len(text) > 6000:
            raise JobError("The prompt must be some words (at most 6000 characters).")
        self.film_changed(pid, message=f"Painting {out.relative_to(root)}")
        out.parent.mkdir(parents=True, exist_ok=True)
        made = out.with_suffix(".made.png")
        if by == "openai":
            made.write_bytes(await self.writers.providers["openai"].picture(text, shape=shape, references=refs))
            said = {"by": "ChatGPT"}
        elif by == "grok":
            data, _ = await grok_media.picture(self.writers.providers["grok"], text, shape, refs[:3],
                                               model=use.get("model") or "grok-imagine-image-2.0")
            await asyncio.to_thread(lambda: Image.open(io.BytesIO(data)).convert("RGB").save(made))
            said = {"by": "Grok Imagine"}
        else:
            m = localpics.of(by)
            await ctx.sched.free_gpu()
            width, height = m.size(shape)
            names = [await ctx.comfy.upload(r, subfolder=f"sv-music-{pid}") for r in refs[:m.refs]] if m.refs else []

            def on(ev: dict) -> None:
                if ev["type"] == "queued":
                    ctx.prompt_id = ev["prompt_id"]
            try:
                res = await ctx.comfy.run(m.graph(text, width, height, random.randrange(2**31), f"sv/{pid}/picture-{rid}",
                                                  refs=names), on)
            finally:
                ctx.prompt_id = None
            files = res.files(m.out, "images")
            if not files:
                raise JobError(f"{m.name} finished without a picture.")
            await ctx.comfy.download(files[0], made)
            said = {"by": m.name, **({"note": f"{m.name} takes no references: they weren't used."} if refs and not m.refs else {})}
        if out.suffix.lower() == ".png":
            made.replace(out)
        else:
            await asyncio.to_thread(lambda: Image.open(made).convert("RGB").save(out, "JPEG", quality=93))
            made.unlink(missing_ok=True)
        return {"out": str(out.relative_to(root)), "shape": shape, **said}

    def _box(self, *args: str) -> list[str]:
        return ["docker", "exec", "-w", "/tmp", self.cfg.vrgdg_box, *args]

    def _inside(self, film: dict) -> str:
        return f"{self.cfg.vrgdg_films_in}/{film['vrgdg']}"

    async def _vrgdg_project(self, ctx: Context, p: dict, film: dict, work: Path) -> None:
        """A Video Builder project for this film (new_project.py --kind music_video, in her container), and the work
        folder as a link to it: Claude's studio and her ComfyUI then work in the same folder."""
        ctx.update(stage="prepare", message="Setting up the Video Builder project", progress=0.01)
        name = _vrgdg_name(p, film)
        film["vrgdg"] = name
        self.film_changed(p["id"], vrgdg=name, message="Setting up the Video Builder project")
        host = self.cfg.vrgdg_films / name
        if not host.exists():
            code, out = await _exec(self._box(self.cfg.vrgdg_python, f"{self.cfg.vrgdg_skill}/scripts/new_project.py",
                                              self._inside(film), "--kind", "music_video", "--aspect", "16:9"), timeout=300)
            if code != 0 or not host.exists():
                raise JobError("The Video Builder project couldn't be made (is her ComfyUI container running?).", out[-2000:])
        if work.is_symlink() or not work.exists():
            work.unlink(missing_ok=True)
            work.symlink_to(host, target_is_directory=True)

    async def _vrgdg_song(self, ctx: Context, p: dict, take: dict, film: dict, work: Path) -> None:
        """The song in the shapes her scripts read (import_song.py from the app's master, vocal stem and timed words),
        a song map from the app's beats, bars, sections and loudness, and her guide beside it."""
        ctx.update(stage="prepare", message="Bringing the song into the Video Builder", progress=0.04)
        root = self.cfg.projects / p["id"]
        ana = self.app.share._analysis(p["id"], take)
        sin = work / "song_in"
        sin.mkdir(exist_ok=True)
        shutil.copyfile(root / take["files"]["flac"], sin / "song.flac")
        lines = [{k: ln.get(k) for k in ("id", "text", "start", "end", "section", "words")} for ln in ana.get("lines") or []]
        (sin / "lyrics.json").write_text(json.dumps({"lines": lines}))
        app_meta = json.loads((work / "song" / "meta.json").read_text())
        base = self._inside(film)
        cmd = [self.cfg.vrgdg_python, f"{self.cfg.vrgdg_skill}/scripts/import_song.py", base, "--audio", f"{base}/song_in/song.flac",
               "--lyrics", f"{base}/song_in/lyrics.json", "--title", p.get("title") or "", "--artist", app_meta.get("artist") or ""]
        if (work / "song" / "vocals.m4a").exists():
            cmd += ["--vocals", f"{base}/song/vocals.m4a"]
        code, out = await _exec(self._box(*cmd), timeout=900)
        if code != 0:
            raise JobError("The song couldn't be brought into the Video Builder.", out[-2000:])
        # what the film kit (for a motion-graphics pass) and the notes expect, beside what her scripts wrote
        timing = json.loads((work / "song" / "timing.json").read_text())
        timing["downbeat"] = (ana.get("downbeat") or {}).get("first", 0)
        (work / "song" / "timing.json").write_text(json.dumps(timing))
        meta = json.loads((work / "song" / "meta.json").read_text())
        (work / "song" / "meta.json").write_text(json.dumps({**meta, **{k: app_meta[k] for k in app_meta if k not in meta}}, indent=1))
        db = await asyncio.to_thread(self.app.share.loudness, p["id"], take)
        lo, hi = float(np.percentile(db, 10)), float(np.percentile(db, 98))
        rate = 4

        def energy(a: float, b: float) -> float:
            seg = db[int(a * rate): max(int(a * rate) + 1, int(b * rate))]
            return round(float(np.clip((seg.mean() - lo) / max(1e-3, hi - lo), 0, 1)), 2) if len(seg) else 0.0
        sections = ana.get("sections") or []
        songmap = {"duration": timing.get("duration"), "tempo": ana.get("tempo"), "meter": 4, "beats": ana.get("beats") or [],
                   "bars": ana.get("bars") or [], "phrases": [{"start": s["start"]} for s in sections],
                   "segments": [{"start": s["start"], "end": s["end"], "label": s.get("label") or "",
                                 "sung": any(ln["start"] < s["end"] and ln["end"] > s["start"] for ln in lines),
                                 "energy": energy(float(s["start"]), float(s["end"]))} for s in sections]}
        (work / "song" / "songmap.json").write_text(json.dumps(songmap))
        guide = Path(str(self.cfg.vrgdg_skill).replace("/vrgdg/profile", str(self.cfg.vrgdg_films.parent.parent))) / "SKILL.md"
        (work / "reference").mkdir(exist_ok=True)
        if guide.exists():
            shutil.copyfile(guide, work / "reference" / "SKILL.md")

    async def _vrgdg_loop(self, work: Path, film: dict) -> None:
        """Runs what tools/vrgdg.py asks for: her scripts, in her container, on this project. Renders one at a time."""
        queue, done, logs = work / "vrgdg" / "queue", work / "vrgdg" / "done", work / "vrgdg" / "logs"
        gpu = asyncio.Lock()
        running: set[asyncio.Task] = set()
        try:
            while True:
                for ask in sorted(queue.glob("*.json"), key=lambda f: f.stat().st_mtime) if queue.is_dir() else []:
                    try:
                        req = json.loads(ask.read_text())
                    except (OSError, ValueError):
                        req = {}
                    ask.unlink(missing_ok=True)
                    t = asyncio.create_task(self._vrgdg_run(film, ask.stem, req, gpu, done, logs))
                    running.add(t)
                    t.add_done_callback(running.discard)
                await asyncio.sleep(2)
        finally:
            for t in running:
                t.cancel()

    async def _vrgdg_run(self, film: dict, rid: str, req: dict, gpu: asyncio.Lock, done: Path, logs: Path) -> None:
        script, args = str(req.get("script") or ""), [str(a) for a in req.get("args") or []]
        base = self._inside(film)

        def inside(a: str) -> str:
            if a in (".", "/work"):
                return base
            if a.startswith("./"):
                return base + a[1:]
            if a.startswith("/work/"):
                return base + a[5:]
            return a
        work = done.parent.parent
        if not inside_work(work, done) or not inside_work(work, logs):
            return  # (a folder replaced with a link: nothing is written through it)
        log = logs / f"{rid}.log"
        if script not in VRGDG_SCRIPTS:
            reply(work, done, f"{rid}.json", {"ok": False, "code": 2, "error": f"{script} isn't one of the "
                                                          f"skill's scripts here: {', '.join(sorted(VRGDG_SCRIPTS))}"})
            return
        cmd = self._box(self.cfg.vrgdg_python, "-u", f"{self.cfg.vrgdg_skill}/scripts/{script}", *[inside(a) for a in args])
        log.write_text(f"$ {script} {' '.join(args)}\n")
        if script in VRGDG_GPU:
            log.open("a").write("(waiting for the GPU: renders run one at a time)\n") if gpu.locked() else None
            async with gpu:
                await self._free_others()
                code, _ = await _exec(cmd, log, timeout=8 * 3600)
        else:
            code, _ = await _exec(cmd, log, timeout=3600)
        reply(work, done, f"{rid}.json", {"ok": code == 0, "code": code})

    async def _free_others(self) -> None:
        """Before a render: the app's own ComfyUI and the others drop idle models, so H3 has the GPU's memory."""
        import httpx
        async with httpx.AsyncClient(timeout=4) as http:
            for base in (self.cfg.comfy, *self.cfg.other_comfys):
                if base.rstrip("/") == self.cfg.vrgdg_url.rstrip("/"):
                    continue
                try:
                    await http.post(f"{base}/free", json={"unload_models": True, "free_memory": True})
                except httpx.HTTPError:
                    pass

    async def _vrgdg_stop(self, film: dict) -> None:
        """Stops whatever this film still has running in her container, and the render in her ComfyUI."""
        if not film.get("vrgdg"):
            return
        import httpx
        await _exec(self._box("pkill", "-f", self._inside(film)), timeout=30)
        try:
            async with httpx.AsyncClient(timeout=4) as http:
                await http.post(f"{self.cfg.vrgdg_url}/interrupt")
        except httpx.HTTPError:
            pass

    async def _grok_clip(self, pid: str, work: Path, rid: str, req: dict) -> dict:
        """One clip from Grok Imagine, asked for the way H3's are (tools/h3.py): 1 to 15 seconds at 720p, the shape the
        nearest to the size asked, its own sound dropped."""
        root = work.resolve()

        def inside(rel: object, what: str, must_exist: bool = True) -> Path:
            path = (root / str(rel or "")).resolve()
            if root not in path.parents:
                raise JobError(f"The {what} must be a file in this folder.")
            if must_exist and not path.is_file():
                raise JobError(f"There's no {what} at {rel}.")
            return path
        image = inside(req.get("image"), "still")
        end = inside(req["end"], "end still") if req.get("end") else None
        out = inside(req.get("out"), "output", must_exist=False)
        if out.suffix.lower() != ".mp4":
            raise JobError("The output must be an .mp4 file.")
        seconds = float(req.get("seconds") or 6)
        if not 1 <= seconds <= 15:
            raise JobError("A Grok clip can be 1 to 15 seconds.")
        text = " ".join(str(req.get("prompt") or "").split())
        if not text or len(text) > 6000:
            raise JobError("The prompt must be some words (at most 6000 characters).")
        ratio = int(req.get("width") or SIZE[0]) / max(1, int(req.get("height") or SIZE[1]))
        shape = min(("16:9", 16 / 9), ("9:16", 9 / 16), ("1:1", 1.0), ("4:3", 4 / 3), ("3:4", 3 / 4),
                    key=lambda x: abs(math.log(x[1] / ratio)))[0]
        self.film_changed(pid, message=f"Grok is animating {out.relative_to(root)}")
        try:
            data, suffix = await grok_media.clip(self.writers.providers["grok"], image, text, round(seconds), end, shape)
        except WriterError as exc:
            raise JobError(f"Grok didn't make the clip: {exc}") from None
        out.parent.mkdir(parents=True, exist_ok=True)
        raw = out.with_suffix(f".grok{suffix}")
        raw.write_bytes(data)
        try:  # only the moving picture: Grok's file also carries its own sound and a still
            await _exec([self.cfg.ffmpeg, "-v", "error", "-y", "-i", str(raw), "-map", "0:v:0", "-an", "-c", "copy",
                         "-movflags", "+faststart", str(out)], timeout=120)
        finally:
            raw.unlink(missing_ok=True)
        if not out.is_file():
            raise JobError("Grok's clip couldn't be saved.")
        return {"out": str(out.relative_to(root)), "seconds": round(seconds), "shape": shape, "by": "Grok Imagine"}

    async def _render(self, ctx: Context, pid: str, work: Path, rid: str, req: dict) -> dict:
        root = work.resolve()

        def inside(rel: object, what: str, must_exist: bool = True) -> Path:
            path = (root / str(rel or "")).resolve()
            if root not in path.parents:
                raise JobError(f"The {what} must be a file in this folder.")
            if must_exist and not path.is_file():
                raise JobError(f"There's no {what} at {rel}.")
            return path
        image = inside(req.get("image"), "still")
        end = inside(req["end"], "end still") if req.get("end") else None
        out = inside(req.get("out"), "output", must_exist=False)
        if out.suffix.lower() != ".mp4":
            raise JobError("The output must be an .mp4 file.")
        width, height = int(req.get("width") or SIZE[0]), int(req.get("height") or SIZE[1])
        if width % 32 or height % 32 or not (256 <= width <= 1536 and 256 <= height <= 1536):
            raise JobError("The size must be multiples of 32, from 256 to 1536 a side (1344x768 is 16:9).")
        seconds = float(req.get("seconds") or 6)
        if not 1 <= seconds <= 15:  # H3's trained range reaches 362 frames: a whole move can be one take
            raise JobError("A clip can be 1 to 15 seconds.")
        text = " ".join(str(req.get("prompt") or "").split())
        if not text or len(text) > 6000:
            raise JobError("The prompt must be some words (at most 6000 characters).")
        seed = int(req["seed"]) if isinstance(req.get("seed"), int) else random.randrange(2**31)
        length = h3.snap_length(seconds)

        await ctx.sched.free_gpu()
        folder = f"sv-music-{pid}"
        sized = root / "h3" / "sized"
        name = await ctx.comfy.upload(await asyncio.to_thread(_fit, image, width, height, sized / f"{rid}-first.png"), subfolder=folder)
        end_name = (await ctx.comfy.upload(await asyncio.to_thread(_fit, end, width, height, sized / f"{rid}-last.png"), subfolder=folder)
                    if end else None)
        self.film_changed(pid, message=f"H3 is animating {out.relative_to(root)}")

        def on(ev: dict) -> None:
            if ev["type"] == "queued":
                ctx.prompt_id = ev["prompt_id"]
        try:
            res = await ctx.comfy.run(h3.graph(name, text, width, length, seed, f"sv/{pid}/music-{rid}", end=end_name,
                                               height=height), on)
        finally:
            ctx.prompt_id = None
        files = res.files("15", "images") or res.files("15", "videos")
        if not files:
            raise JobError("H3 finished without a video.")
        out.parent.mkdir(parents=True, exist_ok=True)
        await ctx.comfy.download(files[0], out)
        return {"out": str(out.relative_to(root)),
                "seconds": round(length / h3.FPS, 3), "frames": length, "fps": h3.FPS, "width": width,
                "height": height, "seed": seed, "renderSeconds": round(res.seconds, 1)}


# ---- VRGameDevGirl's Video Builder (performance and hybrid) -------------------------------------------------------

def _clock(t: float) -> str:
    """2:59.2, the way a time in the song is said."""
    return f"{int(t // 60)}:{t % 60:04.1f}"


def _vrgdg_name(p: dict, film: dict) -> str:
    return f"sv-{p['id']}-{film['id']}"


def project_file(projects: Path, builder_films: Path, pid: str, path: str) -> Path | None:
    """A file the app may serve for this project: one inside its folder, or one inside its own music videos' Video
    Builder projects (sv-<pid>-<film>), which their work folders link to. Nothing else, wherever a link points."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", pid):
        return None
    root = (projects / pid).resolve()
    asked = root / path
    if not Path(os.path.normpath(asked)).is_relative_to(root):
        return None
    f = asked.resolve()
    films = builder_films.resolve()
    mine = f.is_relative_to(films) and f.relative_to(films).parts[:1] and f.relative_to(films).parts[0].startswith(f"sv-{pid}-")
    if not (f.is_relative_to(root) or mine):
        return None
    return f if f.is_file() else None


async def _exec(cmd: list[str], log: Path | None = None, timeout: float = 1800) -> tuple[int, str]:
    """A command, its output to `log` (appended) or returned."""
    out = log.open("ab") if log else None
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=out or asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        try:
            data, _ = await asyncio.wait_for(proc.communicate(), timeout)
        except TimeoutError:
            proc.kill()
            return 124, f"still running after {timeout:.0f} s: stopped"
        return proc.returncode or 0, (data or b"").decode(errors="replace")
    finally:
        if out:
            out.close()


def inside_work(work: Path, folder: Path) -> bool:
    """The folder is really in the session's folder: Claude can replace one with a link to anywhere."""
    return not folder.is_symlink() and folder.resolve().is_relative_to(work.resolve())


def reply(work: Path, folder: Path, name: str, data: dict) -> None:
    """An answer for the session (h3/done, pictures/done, vrgdg/done), never written through a link."""
    folder.mkdir(parents=True, exist_ok=True)
    if not inside_work(work, folder):
        return
    fd = os.open(folder / name, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, "w") as out:
        out.write(json.dumps(data))


def _fit(src: Path, width: int, height: int, dest: Path) -> Path:
    """The still at the clip's size: scaled to cover it and centre-cropped (H3 takes the first frame as it is)."""
    with Image.open(src) as im:
        im = im.convert("RGB")
        scale = max(width / im.width, height / im.height)
        im = im.resize((max(width, round(im.width * scale)), max(height, round(im.height * scale))), Image.LANCZOS)
        left, top = (im.width - width) // 2, (im.height - height) // 2
        dest.parent.mkdir(parents=True, exist_ok=True)
        im.crop((left, top, left + width, top + height)).save(dest)
    return dest


def register(sched, app, writers) -> Music:
    m = Music(app, writers)

    async def run(ctx: Context) -> dict:
        return await m.job(ctx)
    run.after = m.after  # type: ignore[attr-defined]
    sched.register(m.JOB, "studio", run)
    return m
