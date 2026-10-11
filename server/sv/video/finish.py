"""Claude's finish for a living cover: an Opus session in the studio container that writes and renders whatever it likes
in code over the animated cover, for the whole song (a treatment, an overlay, motion graphics, type, something that
answers the music). Free rein, like the films the user liked (memory: free-rein-films): only hard constraints, in
FINISH.md, which becomes the folder's CLAUDE.md.

The folder (projects/<pid>/living/finish-<id>/work) is set up by folder.py, like a film's (the tools, no rules), plus
song/ (the song, its timing, the picture, the sleeve, the brief), living/ (the loops, when each plays, and the whole
moving picture as base.mp4) and analysis/ (the app's measurements). Claude leaves out/final.mp4;
the app checks it, lays the song under it with the usual fade, and keeps it as the square video.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from .. import covers as covers_mod
from .. import studio
from ..jobs import Context, JobError
from . import folder, loops

HERE = Path(__file__).resolve().parent
RULES = HERE / "FINISH.md"
TIMEOUT = 75 * 60  # a whole session, rendering included
OPENING = ('Finish the living album cover for "{title}" in this folder. Read CLAUDE.md first, then song/brief.md, '
           "song/meta.json and analysis/listening.md, and look at song/picture.png and a few frames of living/base.mp4. "
           "Then make it: build the finish, render the whole song to out/final.mp4, look at it, and make it better until "
           "you're proud of it. Go all out, and keep it something people can listen to the song with.")


class Finish:
    def __init__(self, app, living):
        self.app, self.living = app, living
        self.cfg = app.cfg

    def _brief(self, p: dict, lv: dict) -> str:
        auto = lv.get("auto") or {}
        cover = p.get("cover") or {}
        loops_ = lv["loops"][: lv["settings"]["count"]]
        parts = [f"# {p.get('title')}", "",
                 "## The art director's idea", auto.get("idea") or "", "", auto.get("why") or "", "",
                 "## The finish", auto.get("finish") or "Your call.", ""]
        if auto.get("note"):
            parts += ["## What the person asked for", auto["note"], ""]
        parts += ["## The picture", "Painted by GPT Image 2.5 from this prompt:", "", cover.get("prompt") or "(their own picture)", "",
                  "## The loops (MiniMax H3)"]
        parts += [f"- loop {x['id']}: {x.get('motion') or ''}" for x in loops_]
        parts += ["", f"Movement: {lv['settings']['feel']}; each loop about {lv['settings']['seconds']} s; the app changes "
                  f"between them with \"{lv['settings']['transition']}\" (see living/schedule.json)."]
        return "\n".join(parts) + "\n"

    async def job(self, ctx: Context) -> dict:
        pid = ctx.job["projectId"]
        p, take, art = self.living.ready(pid)
        lv = self.living.get(p)
        root = self.cfg.projects / pid
        fid = uuid.uuid4().hex[:8]
        base = self.living.folder(pid) / f"finish-{fid}"
        work = base / "work"
        base.mkdir(parents=True)
        total = float(take.get("duration") or 0)
        self.living.put(pid, auto={**(lv.get("auto") or {}), "finishId": fid})

        ctx.update(stage="prepare", message="Setting up the studio", progress=0.02)
        await folder.seed(self.cfg, work, RULES)
        song = work / "song"
        (song / "logos").mkdir(parents=True, exist_ok=True)
        (work / "living").mkdir(exist_ok=True)
        cover = p["cover"]
        logos = self.app.covers.logos()

        def pictures() -> None:
            picture = covers_mod.square(art, 1080)
            picture.save(song / "picture.png")
            covers_mod.sleeve(picture, p["title"], cover.get("artist") or "", logos, self.app.covers.look(p),
                              self.app.covers.fonts)[0].save(song / "sleeve.png")
            for slot, src in logos.items():
                shutil.copyfile(src, song / "logos" / f"{slot}{src.suffix.lower()}")
        await asyncio.to_thread(pictures)
        await folder.song(self.cfg, p, take, work, {
            "title": p.get("title"), "artist": cover.get("artist") or "", "kind": "living album cover",
            "width": 1080, "height": 1080, "fps": 24, "duration": round(total, 3), "genres": p.get("genres") or [],
            "moods": p.get("moods") or [], "feel": (lv.get("auto") or {}).get("note") or ""})
        (song / "brief.md").write_text(self._brief(p, lv))

        ctx.update(stage="prepare", message="Putting the loops together", progress=0.04)
        made = await self.living.compose(ctx, pid, "square", work / "living" / "base.mp4", sleeve=False, report=False)
        for x in made["loops"]:
            shutil.copyfile(root / x["video"], work / "living" / f"loop-{x['id']}.mp4")
        (work / "living" / "schedule.json").write_text(json.dumps({
            "duration": round(total, 3), "fps": 24, "transition": lv["settings"]["transition"],
            "loops": {x["id"]: {"file": f"living/loop-{x['id']}.mp4", "seconds": x.get("seconds"), "motion": x.get("motion")}
                      for x in made["loops"]},
            "stretches": [{"loop": made["loops"][st["loop"]]["id"], "start": round(st["start"], 3), "end": round(st["end"], 3),
                           "blendIntoNext": round(st.get("xf") or 0.0, 3)} for st in made["plan"]]}, indent=1))
        ctx.update(stage="prepare", message="Reading the song's beat and levels", progress=0.06)
        await folder.measure(self.cfg, work)

        ctx.update(stage="claude", message="Claude is looking at the cover and the song", progress=0.08)
        started = time.monotonic()

        def on_line(line: dict) -> None:
            say = studio.plain(line)
            if say:
                ctx.update(message=say[:240], progress=min(0.95, 0.08 + 0.87 * (time.monotonic() - started) / TIMEOUT))
        who = self.living.writers.film()  # Settings → Who does what → Making videos in code
        r = await studio.run(self.cfg.studio_sh, work, OPENING.format(title=p.get("title")), model=who["model"],
                             effort=who["effort"], timeout=TIMEOUT, on_line=on_line, is_cancelled=lambda: ctx.cancelled)
        (base / "result.json").write_text(json.dumps({k: r[k] for k in ("state", "lines", "seconds")}, indent=1))
        final = work / "out" / "final.mp4"
        if r["state"] == "limit":
            raise JobError("Your Claude plan's usage limit was reached during the finish; the video without it is kept.")
        if r["state"] == "cancelled":
            raise JobError("Stopped.")
        if not final.exists():
            why = next((x["text"] for x in reversed(r["lines"]) if x["kind"] in ("error", "result")), "")
            raise JobError("The finish in code didn't leave a video" + (f": {why[:200]}" if why else "."))
        info = await asyncio.to_thread(loops.probe, str(final), self.cfg.ffmpeg)
        length = info["frames"] / info["fps"]
        if (info["w"], info["h"]) != (1080, 1080) or abs(length - total) > 1.5:
            raise JobError(f"The finish in code came out {info['w']}×{info['h']}, {length:.1f} s (the song is {total:.1f} s): "
                           "the video without it is kept.")

        ctx.update(stage="mux", message="Laying the song under it", progress=0.97)
        rid = uuid.uuid4().hex[:8]
        out = self.living.folder(pid) / f"living-square-{rid}.mp4"
        fade = f"st={max(0.0, total - 2.0):.3f}:d=2"
        await folder.ff(self.cfg, "-i", str(final), "-i", str(root / take["files"]["flac"]), "-map", "0:v:0", "-map", "1:a:0",
                       "-vf", f"fade=t=out:{fade},format=yuv420p", "-af", f"afade=t=out:{fade}", "-t", f"{total:.3f}",
                       "-r", "24", "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-maxrate", "8M", "-bufsize", "16M",
                       "-c:a", "aac", "-b:a", "256k",
                       "-movflags", "+faststart", str(out))
        poster = work / "out" / "poster.png"
        kept_poster = None
        if poster.exists():
            kept_poster = self.living.folder(pid) / f"poster-{rid}.png"
            shutil.copyfile(poster, kept_poster)
        readme = (work / "README.md").read_text()[:2000] if (work / "README.md").exists() else ""
        summary: dict = {}
        try:
            summary = json.loads((work / "out" / "summary.json").read_text())
        except (OSError, ValueError):
            pass
        left_out = {str(k)[:4]: " ".join(str(v).split())[:300] for k, v in (summary.get("leftOut") or {}).items()} \
            if isinstance(summary.get("leftOut"), dict) else {}
        about = " ".join(str(summary.get("about") or "").split())[:600] or _about(readme)
        lv = self.living.get(self.app.store.project(pid) or p)
        rec = {"id": rid, "file": str(out.relative_to(root)), "shape": "square", "seconds": round(total, 2),
               "bytes": out.stat().st_size, "loops": [x["id"] for x in made["loops"]], "stretches": len(made["plan"]),
               "transition": lv["settings"]["transition"], "feel": lv["settings"]["feel"], "cover": cover["n"],
               "made": {x["id"]: x.get("rev") for x in made["loops"]}, "finish": fid,
               "poster": str(kept_poster.relative_to(root)) if kept_poster else None,
               "renderSeconds": r["seconds"], "at": time.time()}
        self.living.keep_render(pid, rec)
        auto = self.living.get(self.app.store.project(pid) or p).get("auto") or {}
        self.living.put(pid, auto={**auto, "status": "done", "render": rid,
                                   "finished": {"id": fid, "about": about, "leftOut": left_out, "seconds": r["seconds"]}})
        return {"render": rid, "seconds": r["seconds"]}

    async def after(self, ctx: Context, job: dict) -> None:
        """A finish that didn't work leaves the video without it, saying why."""
        if job["status"] in ("failed", "cancelled"):
            p = ctx.store.project(job["projectId"])
            auto = self.living.get(p or {}).get("auto") or {}
            if p and auto.get("status") == "finishing":
                self.living.put(job["projectId"], auto={**auto, "status": "done",
                                                        "finishError": job.get("message") or "The finish stopped."})


def _about(readme: str) -> str:
    """The first plain paragraph of Claude's README: what it made, for the person. A paragraph that leads into a list
    ("The finish only answers the low end:") takes the list's lead-ins along."""
    blocks = re.split(r"\n\s*\n", readme)
    for i, block in enumerate(blocks):
        text = " ".join(line.strip() for line in block.splitlines() if not line.strip().startswith(("#", "```", "|", "-")))
        if len(text) <= 40:
            continue
        if text.endswith(":") and i + 1 < len(blocks):
            items = [re.sub(r"\*\*(.+?)\*\*.*", r"\1", line.strip()[2:]).strip().rstrip(".:")
                     for line in blocks[i + 1].splitlines() if line.strip().startswith("- ")]
            text = f"{text} {'; '.join(x for x in items if x)}." if items else text[:-1] + "."
        return text[:700]
    return ""


def register(sched, app, living) -> Finish:
    f = Finish(app, living)

    async def run(ctx: Context) -> dict[str, Any]:
        return await f.job(ctx)
    run.after = f.after  # type: ignore[attr-defined]
    sched.register("living.finish", "studio", run)
    return f
