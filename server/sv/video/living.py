"""Living Album Cover: the song's cover, gently alive, for as long as the song plays. It must never pull attention from
the music, so it is subtle by default.

- 1-4 loops, each a separate MiniMax H3 clip that starts on the cover's picture (without its title) and only moves
  forward; its extra second is blended into its start (loops.close), so it repeats without a seam and never plays back
  on itself. Claude (the "Directing videos" writer) gives each loop a
  different small motion: dust in a beam of light, water, a flame, haze.
- People in the picture may be held exactly as painted (SAM3 finds them; loops.hold), so only the world around them
  moves. Off unless asked for ("keepPeople"): a still figure in a moving world looked odd to the user (2026-10-09), so
  by default the words ask figures to hold their pose and only breathe.
- Each clip is measured: one that cuts, or moves too much (on "barely moving", anything lively), is made again with
  another seed, up to three times, and the calmest kept. Loops longer than 8 s are 6 s pieces played in turn.
- The video: the loops take turns at the song's section starts with a soft dissolve, the title, the artist and the
  logos fixed on top (the same layer as the cover's), the chosen take as the sound. Square, 9:16 or 16:9.

"Let Claude make it" (`auto`): Claude, as director, reads the song and decides everything: a new picture made to move
(always new: the user's choice; the old cover is only shown so it isn't repeated), how many loops, how much they move,
how long, the transition. It writes the motions looking at the new picture, and the loops and the video follow by
themselves. A chain of jobs: living.auto (decide) -> cover.* (the picture) -> living.auto (motion) -> living.loop x n
-> living.render.

Everything is kept on the song as `living` (settings, loops, renders, plan, auto); files in projects/<pid>/living/.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageFilter

from .. import covers as covers_mod
from ..jobs import Context, JobError, Scheduler
from ..writers import Writers, WriterError
from . import h3, loops
from ..paths import drop

SIDE = 1024
TRIES = 3
FADE_OUT = 2.0
OVERLAP = 1.0  # seconds the clip runs past the loop, blended into its start (loops.close)
JOIN = 0.5  # seconds two pieces of a long loop share, blended (loops.join)
SECONDS = (4, 6, 8, 12)
SHAPES = {"square": (1080, 1080), "story": (1080, 1920), "wide": (1920, 1080)}
DEFAULTS = {"count": 2, "seconds": 6, "feel": "subtle", "keepPeople": False, "transition": "seamless", "shape": "square"}
# Between loops, always as a loop comes round (snap). "Seamless" is a one-second blend there: loops made forward-only
# don't end exactly on the cover any more, so a plain cut could show; the others are soft, never busy (the point is to
# not pull attention from the music).
TRANSITIONS = {"seamless": ("fade", 1.0), "dissolve": ("fade", 1.5), "slow": ("fade", 4.0), "dark": ("dip", 2.4)}
# "Dip to dark": a cross-fade whose brightness sinks halfway and comes back (only the brightness plane, so the colors
# don't tint). P runs from 1 to 0 across the transition.
DIP = "custom:expr='if(eq(PLANE,0),(A*P+B*(1-P))*(1-0.5*sin(PI*P)),A*P+B*(1-P))'"
IDS = ("a", "b", "c", "d")


def settings_of(living: dict | None) -> dict:
    s = {**DEFAULTS, **((living or {}).get("settings") or {})}
    s["count"] = max(1, min(4, int(s["count"])))
    s["seconds"] = s["seconds"] if s["seconds"] in SECONDS else 6
    s["feel"] = s["feel"] if s["feel"] in h3.FEEL else "subtle"
    s["keepPeople"] = bool(s["keepPeople"])
    s.pop("hold", None)  # the old setting (on by default): its saved True was never a choice anyone made
    s["transition"] = s["transition"] if s["transition"] in TRANSITIONS else "seamless"
    s["shape"] = s["shape"] if s["shape"] in SHAPES else "square"
    return s


def acceptable(rep: dict, feel: str) -> bool:
    """Which clips to keep: never one that cuts or moves too much; "Barely" only calm ones; "A little" calm or just
    lively; "Gentle" calm or lively."""
    if rep["motion"] == "calm":
        return True
    return rep["motion"] == "lively" and (feel == "gentle" or (feel == "subtle" and rep.get("changed", 1) <= 0.24))


def with_picture(living: dict | None, n: int) -> dict:
    """The living cover now animates picture n. Words written for another picture are cleared (they describe things
    that aren't in this one), and so is Claude's plan for it; loops made from it stay until they're made again."""
    lv = dict(living or {})
    if lv.get("picture") != n or (lv.get("plan") or {}).get("cover") not in (None, n):
        lv["loops"] = [x if x.get("cover") == n and x.get("madeWith") == x.get("motion") else
                       {**x, "motion": "", "edited": False} for x in lv.get("loops") or []]
        lv.pop("plan", None)
    lv["picture"] = n
    return lv


def badness(rep: dict) -> tuple:
    return (rep.get("cuts") or 0, rep.get("changed") or 0.0)


def snap(plan: list[dict], total: float, lengths: list[float]) -> list[dict]:
    """Every change of loop moved onto a moment when the loop playing comes round (a whole number of its own loops
    in), so the next one blends in from its start while this one flows into its own."""
    out, t = [], 0.0
    for k, st in enumerate(plan):
        loop_s = lengths[st["loop"]]
        if k == len(plan) - 1:
            end = total
        else:
            end = t + max(1, round((st["end"] - t) / loop_s)) * loop_s
            if total - end < min(lengths):  # too little left for the next: this one plays to the end
                out.append({**st, "start": t, "end": total})
                return out
        out.append({**st, "start": t, "end": end})
        t = end
    return out


def schedule(total: float, n: int, starts: list[float]) -> list[dict]:
    """Which loop plays when: the song's sections take turns (section k gets loop k mod n); sections under 8 s join
    the one before; without sections, stretches of about 20 s. Neighbours with the same loop are one stretch."""
    cuts = sorted({round(t, 2) for t in starts if 0 < t < total - 4})
    if not cuts:
        k = max(1, round(total / 20))
        cuts = [total * i / k for i in range(1, k)]
    bounds = [0.0]
    for t in cuts:
        if t - bounds[-1] >= 8:
            bounds.append(t)
    if total - bounds[-1] < 8 and len(bounds) > 1:
        bounds.pop()
    out: list[dict] = []
    for i, start in enumerate(bounds):
        end = bounds[i + 1] if i + 1 < len(bounds) else total
        loop = i % n
        if out and out[-1]["loop"] == loop:
            out[-1]["end"] = end
        else:
            out.append({"loop": loop, "start": start, "end": end})
    return out


class Living:
    def __init__(self, app, writers: Writers):
        self.app, self.writers = app, writers
        self.cfg = app.cfg

    # ---- the record ----------------------------------------------------------------------
    def folder(self, pid: str) -> Path:
        return self.cfg.projects / pid / "living"

    def get(self, p: dict) -> dict:
        lv = dict(p.get("living") or {})
        lv["settings"] = settings_of(lv)
        lv.setdefault("loops", [])
        lv.setdefault("renders", [])
        return lv

    def put(self, pid: str, **changes: Any) -> dict:
        p = self.app.store.project(pid)
        if p is None:
            raise JobError("That song isn't here any more.")
        lv = {**self.get(p), **changes}
        p = self.app.store.patch_project(pid, living=lv)
        self.app.hub.publish("project", p)
        return p

    def loop_changed(self, pid: str, lid: str, **fields: Any) -> dict:
        p = self.app.store.project(pid)
        lv = self.get(p)
        lv["loops"] = [{**x, **fields} if x["id"] == lid else x for x in lv["loops"]]
        return self.put(pid, loops=lv["loops"])

    def ready(self, pid: str) -> tuple[dict, dict, Path]:
        """The song, its chosen take and its cover's picture: what a living cover needs."""
        p = self.app.store.project(pid)
        if p is None:
            raise JobError("That song isn't here any more.")
        take = self.app.store.take(p.get("masterTake") or "")
        if not take or take.get("status") != "ready":
            raise JobError("Choose the song's take first (“Use this one” on the song page).")
        cover = p.get("cover")
        art = self.cfg.projects / pid / cover["art"] if cover and cover.get("art") else None
        if not art or not art.exists():
            raise JobError("The song needs a cover first: make one from the song page.")
        return p, take, art

    def layer(self, pid: str) -> Path:
        """The sleeve as a transparent picture (title, artist, logos) for the page's preview, kept per cover and words."""
        p = self.app.store.project(pid)
        cover = (p or {}).get("cover")
        art = self.cfg.projects / pid / cover["art"] if cover and cover.get("art") else None
        if not art or not art.exists():
            raise JobError("The song needs a cover first.")
        key = hashlib.sha1(f"{cover['n']}|{p['title']}|{cover.get('artist') or ''}".encode()).hexdigest()[:10]
        out = self.folder(pid) / f"layer-{key}.png"
        if not out.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
            for old in self.folder(pid).glob("layer-*.png"):
                if len(old.stem) == 16:  # an earlier preview layer (render layers carry 8-letter ids)
                    old.unlink(missing_ok=True)
            sleeve, _ = covers_mod.sleeve(covers_mod.square(art, 1080), p["title"], cover.get("artist") or "",
                                          self.app.covers.logos(), self.app.covers.look(p), self.app.covers.fonts)
            sleeve.save(out)
        return out

    def picture(self, pid: str) -> Path:
        """The cover's picture (no title) at 1080 px, for the page's preview."""
        p = self.app.store.project(pid)
        cover = (p or {}).get("cover")
        art = self.cfg.projects / pid / cover["art"] if cover and cover.get("art") else None
        if not art or not art.exists():
            raise JobError("The song needs a cover first.")
        out = self.folder(pid) / f"picture-{cover['n']}.jpg"
        if not out.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
            covers_mod.square(art, 1080).save(out, "JPEG", quality=88)
        return out

    # ---- the user's actions ------------------------------------------------------------------
    def update(self, pid: str, settings: dict | None, motions: dict[str, str] | None, mode: str | None = None,
               keep: bool = False) -> dict:
        p = self.app.store.project(pid)
        if p is None:
            raise JobError("That song isn't here any more.")
        lv = self.get(p)
        s = settings_of({"settings": {**lv["settings"], **(settings or {})}})
        loops_ = [dict(x) for x in lv["loops"]]
        for x in loops_:
            if motions and x["id"] in motions and motions[x["id"]].strip() != x.get("motion"):
                x["motion"] = " ".join(motions[x["id"]].split())[:600]
                x["edited"] = True
        while len(loops_) < s["count"]:
            loops_.append({"id": next(i for i in IDS if i not in {x["id"] for x in loops_}), "motion": "", "status": "new"})
        for gone in loops_[s["count"]:]:  # fewer loops: the ones dropped go, files and all
            drop(self.cfg.projects / pid, gone.get("video"))
        before = lv["settings"]
        extra: dict[str, Any] = {"mode": mode} if mode in ("auto", "direct") else {}
        if keep and (lv.get("auto") or {}).get("status") == "done":  # you kept the video Claude made
            extra["auto"] = {**lv["auto"], "kept": True}
        p = self.put(pid, settings=s, loops=loops_[: s["count"]], **extra)
        # the video follows its own settings (the loops need making again for the others)
        if (s["transition"], s["shape"], s["count"]) != (before["transition"], before["shape"], before["count"]):
            try:
                self.auto_render(pid)
            except JobError:
                pass
        return p

    async def plan(self, pid: str, note: str = "") -> dict:
        """Claude writes one subtle motion per loop, looking at the picture. Every loop gets new words (asked for
        explicitly, so nothing old survives); a loop already made shows as changed until it's made again."""
        p, _, art = self.ready(pid)
        lv = self.get(p)
        s = lv["settings"]
        cover = p["cover"]
        song = {"title": p.get("title"), "idea": p.get("idea")}
        look = self.folder(pid) / f"look-{cover['n']}.jpg"  # the picture Claude looks at, small
        if not look.exists():
            look.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(lambda: covers_mod.square(art, 768).save(look, "JPEG", quality=88))
        try:
            r = await self.writers.write("motion", {"song": song, "count": s["count"], "picture": cover.get("prompt"),
                                                   "genres": ", ".join(p.get("genres") or []), "holdPeople": s["keepPeople"],
                                                   "note": note, "feel": s["feel"], "seen": True}, images=[look])
        except WriterError as exc:
            raise JobError(f"Couldn't write the motion: {exc}") from None
        ideas = r["result"]["loops"]
        old = {x["id"]: x for x in lv["loops"]}
        made = []
        for i, lid in enumerate(IDS[: s["count"]]):
            prev = old.get(lid) or {"id": lid, "status": "new"}
            motion = ideas[i] if i < len(ideas) else ideas[-1]
            made.append({**prev, "motion": motion, "edited": False})
        return self.put(pid, loops=made, picture=cover["n"], steer=note,
                        plan={"risk": r["result"]["risk"], "people": r["result"]["people"], "cover": cover["n"],
                              "by": r["by"], "at": time.time()})

    def confirm(self, pid: str) -> dict:
        """'Use this cover': the song's current cover is the living cover's picture."""
        p = self.app.store.project(pid)
        if not (p or {}).get("cover"):
            raise JobError("The song needs a cover first.")
        p = self.app.store.patch_project(pid, living=with_picture(p.get("living"), p["cover"]["n"]))
        self.app.hub.publish("project", p)
        return p

    def make(self, pid: str, lid: str) -> dict:
        p, _, _ = self.ready(pid)
        loop = next((x for x in self.get(p)["loops"] if x["id"] == lid), None)
        if loop is None:
            raise JobError("That loop isn't there.")
        if not (loop.get("motion") or "").strip():
            raise JobError("Say what moves first (or let the AI write it).")
        job = self.app.sched.submit("living.loop", {"loopId": lid, "message": "Waiting its turn"}, pid)
        self.loop_changed(pid, lid, status="queued", jobId=job["id"], error=None)
        return job

    def render(self, pid: str, shape: str | None = None) -> dict:
        p, _, _ = self.ready(pid)
        lv = self.get(p)
        loops_ = [x for x in lv["loops"][: lv["settings"]["count"]] if x.get("video")]
        if not loops_:
            raise JobError("Make at least one loop first.")
        if all(x.get("usable") is False for x in loops_):
            raise JobError("Every loop cut away to a different shot: change what moves and make them again.")
        shape = shape or lv["settings"]["shape"]
        if shape not in SHAPES:
            raise JobError("Choose square, 9:16 or 16:9.")
        for j in self.app.store.jobs(("queued",), project_id=pid):  # a newer request replaces one still waiting
            if j["kind"] == "living.render" and j.get("shape") == shape:
                self.app.hub.publish("job", self.app.store.update_job(j["id"], "cancelled", message="Replaced by a newer one."))
        return self.app.sched.submit("living.render", {"shape": shape, "message": "Waiting its turn"}, pid)

    def auto_render(self, pid: str) -> None:
        """When every loop is made (from the current picture), the video makes itself, in the chosen shape, unless
        the one there already has exactly these loops and this transition."""
        p = self.app.store.project(pid)
        lv = self.get(p or {})
        s = lv["settings"]
        loops_ = lv["loops"][: s["count"]]
        cover_n = ((p or {}).get("cover") or {}).get("n")
        busy = any(x["status"] in ("queued", "making") for x in loops_)
        if not (p and loops_ and not busy and all(x.get("video") and x.get("cover") == cover_n for x in loops_)):
            return
        auto = lv.get("auto") or {}
        if all(x.get("usable") is False for x in loops_):
            if auto.get("status") == "animating":  # "Claude makes it": nothing to put together; carrying on rewrites the motion
                self.put(pid, auto={**auto, "status": "failed", "failedAt": "motion",
                                    "error": "every loop cut away to a different shot"})
            return
        current = next((r for r in lv["renders"] if r.get("shape") == s["shape"] and not r.get("finish")), None)
        if current and current.get("transition") == s["transition"] and current.get("cover") == cover_n and \
                current.get("made") == {x["id"]: x.get("rev") for x in loops_}:
            return
        self.render(pid)

    # ---- "Let Claude make it" -----------------------------------------------------------------
    def auto(self, pid: str, note: str = "", again: bool = False, resume: str | None = None) -> dict:
        """Claude makes the whole living cover. `again`: another idea, clearly different from the last one.
        `resume`: after a stop, carry on from where it stopped with the same idea (a picture source, as Settings lists
        them, for a picture that wasn't painted; anything else: the album covers' own choice)."""
        p = self.app.store.project(pid)
        if p is None:
            raise JobError("That song isn't here any more.")
        take = self.app.store.take(p.get("masterTake") or "")
        if not take or take.get("status") != "ready":
            raise JobError("Choose the song's take first (“Use this one” on the song page).")
        lv = self.get(p)
        busy = [j for j in self.app.store.jobs(("queued", "running"), project_id=pid)
                if j["kind"] in ("living.auto", "living.loop", "living.finish") or j["kind"].startswith("cover.")]
        if busy:
            raise JobError("Something is still being made for this video: wait for it to finish.")
        before = lv.get("auto") or {}
        if resume and before.get("status") in ("failed", "stopped") and before.get("idea"):
            return self._resume(pid, before, resume)
        avoid = before.get("idea", "") if again else ""
        note = " ".join((note or "").split())[:400]
        job = self.app.sched.submit("living.auto", {"stage": "decide", "note": note, "avoid": avoid,
                                                     "message": "Listening to the song"}, pid)
        self.put(pid, mode="auto", auto={"status": "deciding", "jobId": job["id"], "note": note, "at": time.time()})
        return job

    def _resume(self, pid: str, auto: dict, engine: str) -> dict:
        """Carry on with the same idea from the step that stopped: the picture, or the motion (deciding again is a
        new run)."""
        # (a stop recorded before failedAt existed: a painted-picture run that has a brief stopped at the picture)
        at = auto.get("failedAt") or ("paint" if auto.get("coverJob") and (auto.get("prompt") or auto.get("brief")) else "decide")
        if at == "paint":
            engine = engine if engine in self.writers.image_ids() else None
            job = (self.app.covers.start(pid, engine, prompt=auto["prompt"], moving=True, for_living=True, auto=True,
                                         by=auto.get("by"), concept=auto.get("idea") or "") if auto.get("prompt") else
                   self.app.covers.start(pid, engine, note=auto.get("brief") or "", moving=True, for_living=True, auto=True))
            self.put(pid, auto={**auto, "status": "painting", "coverJob": job["id"], "error": None, "failedAt": None})
            return job
        if at == "motion":
            job = self.app.sched.submit("living.auto", {"stage": "motion", "message": "Choosing what moves"}, pid)
            self.put(pid, auto={**auto, "status": "writing", "jobId": job["id"], "error": None, "failedAt": None})
            return job
        return self.auto(pid, auto.get("note") or "")

    def recent_looks(self, n: int = 14) -> list[str]:
        """What the app's covers have looked like lately (each one's idea, else the start of its prompt), newest
        first: Claude is shown them so a new cover looks nothing like them."""
        seen: list[str] = []
        for p in self.app.store.projects():
            for c in reversed(p.get("covers") or []):
                text = " ".join(str((c.get("by") or {}).get("concept") or c.get("prompt") or "").split())
                if text and text not in seen:
                    seen.append(text[:220])
            if len(seen) >= n:
                break
        return seen[:n]

    async def auto_job(self, ctx: Context) -> dict:
        pid = ctx.job["projectId"]
        if ctx.job.get("stage") == "motion":
            return await self._auto_motion(ctx, pid)
        p = self.app.store.project(pid)
        if p is None:
            raise JobError("That song isn't here any more.")
        take = self.app.store.take(p.get("masterTake") or "")
        lv = self.get(p)
        total = float((take or {}).get("duration") or 0)
        sections = 0
        af = self.cfg.projects / pid / "takes" / (take or {}).get("id", "-") / "analysis" / "analysis.json"
        if af.exists():
            try:
                sections = len(json.loads(af.read_text()).get("sections") or [])
            except (ValueError, TypeError):
                sections = 0
        shape = ", ".join(x for x in (f"{int(total // 60)}:{int(total % 60):02d} long" if total else "",
                                      f"{sections} sections" if sections else "",
                                      f"about {p['tempo']} BPM" if p.get("tempo") else "") if x)
        ctx.update(stage="decide", message="Listening to the song and imagining its cover", progress=0.2)
        song = {"title": p.get("title"), "idea": p.get("idea"),
                "sound": ", ".join(x for x in (p.get("instruments"), p.get("extra")) if x)}
        try:
            r = await self.writers.write("living", {"song": song, "genres": ", ".join(p.get("genres") or []),
                                                   "moods": ", ".join(p.get("moods") or []), "shape": shape,
                                                   "made": self.recent_looks(), "note": ctx.job.get("note"),
                                                   "avoid": ctx.job.get("avoid")})
        except WriterError as exc:
            raise JobError(f"Couldn't decide: {exc}") from None
        d = r["result"]
        s = settings_of({"settings": {**lv["settings"], "count": d["count"], "feel": d["feel"], "seconds": d["seconds"],
                                      "transition": d["transition"], "keepPeople": False}})
        auto = {**(lv.get("auto") or {}), "status": "painting", "idea": d["idea"], "why": d["why"], "picture": "new",
                "prompt": d["prompt"], "finish": d["finish"], "brief": None, "finished": None, "finishError": None,
                "choices": {k: s[k] for k in ("count", "feel", "seconds", "transition")}, "by": r["by"], "at": time.time()}
        loops_ = [{**x, "motion": "", "edited": False} for x in lv["loops"][: s["count"]]]
        while len(loops_) < s["count"]:
            loops_.append({"id": next(i for i in IDS if i not in {x["id"] for x in loops_}), "motion": "", "status": "new"})
        for gone in lv["loops"][s["count"]:]:
            drop(self.cfg.projects / pid, gone.get("video"))
        # always a new picture, painted from Claude's own prompt; when it's done, the cover job's after-hook carries on
        # (auto_picture_done)
        self.put(pid, settings=s, loops=loops_, auto=auto)
        ctx.update(stage="paint", message="A new picture is on its way", progress=0.9)
        job = self.app.covers.start(pid, None, prompt=d["prompt"], moving=True, for_living=True, auto=True, by=r["by"],
                                    concept=d["idea"])
        self.put(pid, auto={**auto, "coverJob": job["id"]})
        return {"picture": "new", "coverJob": job["id"]}

    async def _auto_motion(self, ctx: Context, pid: str) -> dict:
        """The picture is settled: Claude writes each loop's motion looking at it, and the loops are made."""
        p = self.app.store.project(pid)
        auto = self.get(p or {}).get("auto") or {}
        self.put(pid, auto={**auto, "status": "writing"})
        ctx.update(stage="motion", message="Choosing what moves", progress=0.5)
        note = " ".join(x for x in (f"The director's idea for this video: {auto['idea']}" if auto.get("idea") else "",
                                    f"The artist asked: {auto['note']}" if auto.get("note") else "") if x)
        await self.plan(pid, note)
        p = self.app.store.project(pid)
        lv = self.get(p)
        for x in lv["loops"][: lv["settings"]["count"]]:
            self.make(pid, x["id"])
        self.put(pid, auto={**(self.get(self.app.store.project(pid)).get("auto") or {}), "status": "animating"})
        return {"loops": lv["settings"]["count"]}

    def auto_picture_done(self, pid: str, job: dict) -> None:
        """A picture painted for "Let Claude make it" has finished: on to the motion (or say what went wrong)."""
        p = self.app.store.project(pid)
        auto = self.get(p or {}).get("auto") or {}
        if not p or auto.get("coverJob") != job["id"] or auto.get("status") != "painting":
            return
        if job["status"] == "done":
            nxt = self.app.sched.submit("living.auto", {"stage": "motion", "message": "Choosing what moves"}, pid)
            self.put(pid, auto={**auto, "status": "writing", "jobId": nxt["id"]})
        else:
            self.put(pid, auto={**auto, "status": "failed", "failedAt": "paint",
                                "error": job.get("message") or "The picture wasn't made."})

    async def auto_after(self, ctx: Context, job: dict) -> None:
        if job["status"] in ("failed", "cancelled"):
            p = ctx.store.project(job["projectId"])
            auto = self.get(p or {}).get("auto") or {}
            if p and auto.get("jobId") == job["id"]:
                self.put(job["projectId"], auto={**auto, "status": "failed" if job["status"] == "failed" else "stopped",
                                                 "failedAt": job.get("stage") or "decide", "error": job.get("message")})

    # ---- a loop (GPU) -----------------------------------------------------------------------
    async def _still(self, pid: str, cover: dict, art: Path) -> Path:
        still = self.folder(pid) / f"still-{cover['n']}.png"
        if not still.exists():
            still.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(lambda: covers_mod.square(art, SIDE).save(still))
        return still

    async def _people(self, ctx: Context, pid: str, cover: dict, still: Path, name: str) -> Path | None:
        """Where the people are (SAM3, "person"), kept per cover; None when there's nobody."""
        mask = self.folder(pid) / f"people-{cover['n']}-t60.png"
        if not mask.exists():
            ctx.update(stage="look", message="Finding the people to hold still", progress=0.03)
            g = {
                "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sam3.1_multiplex_fp16.safetensors"}},
                "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": "person"}},
                "3": {"class_type": "LoadImage", "inputs": {"image": name}},
                "4": {"class_type": "SAM3_Detect", "inputs": {"model": ["1", 0], "image": ["3", 0], "conditioning": ["2", 0],
                                                               "threshold": 0.6, "refine_iterations": 2, "individual_masks": False}},
                "5": {"class_type": "MaskToImage", "inputs": {"mask": ["4", 0]}},
                "6": {"class_type": "SaveImage", "inputs": {"images": ["5", 0], "filename_prefix": "sv/living-people"}},
            }
            res = await self._run(ctx, g, None)
            files = res.files("6", "images")
            if not files:
                raise JobError("Looking for people in the picture didn't work.")
            await ctx.comfy.download(files[0], mask)
        share = await asyncio.to_thread(lambda: float((np.asarray(Image.open(mask).convert("L")) > 127).mean()))
        return mask if share > 0.002 else None

    async def _run(self, ctx: Context, graph: dict, span: tuple[float, float] | None):
        def on(ev: dict) -> None:
            if ev["type"] == "queued":
                ctx.prompt_id = ev["prompt_id"]
            elif span and ev["type"] == "progress" and ev.get("max") and str(ev.get("node")) == "12":
                ctx.update(progress=span[0] + (span[1] - span[0]) * ev["value"] / ev["max"])
        try:
            return await ctx.comfy.run(graph, on)
        finally:
            ctx.prompt_id = None

    async def loop_job(self, ctx: Context) -> dict:
        pid, lid = ctx.job["projectId"], ctx.job["loopId"]
        p, _, art = self.ready(pid)
        lv = self.get(p)
        s, cover = lv["settings"], p["cover"]
        loop = next((x for x in lv["loops"] if x["id"] == lid), None)
        if loop is None:
            raise JobError("That loop isn't there any more.")
        self.loop_changed(pid, lid, status="making", error=None)
        folder = self.folder(pid)
        folder.mkdir(parents=True, exist_ok=True)
        still = await self._still(pid, cover, art)
        name = await ctx.comfy.upload(still, subfolder="sv-living")
        hold = s["keepPeople"]
        # SAM3 can take a pale curtain for a person (seen 2026-10-09; 0.6 is past it): when Claude, who looked at the
        # picture while planning, says there's nobody in it, nothing is held
        nobody = (lv.get("plan") or {}).get("people") is False and (lv.get("plan") or {}).get("cover") == cover["n"]
        people = await self._people(ctx, pid, cover, still, name) if hold and not nobody else None
        # Forward only: each piece starts on the cover (later pieces on the last frame of the one before) with its end
        # free, and the last runs OVERLAP seconds past the loop; loops.close blends that into the start, so the end
        # flows into the beginning and nothing slows to a stop or plays back on itself.
        pieces = 1 if s["seconds"] <= h3.PIECE_MAX else max(2, round(s["seconds"] / h3.PIECE))
        text = h3.prompt(loop["motion"], s["feel"])
        work = folder / f"work-{lid}-{uuid.uuid4().hex[:6]}"
        work.mkdir()
        ff = self.cfg.ffmpeg
        tried: list[dict] = []
        kept: list[Path] = []
        cut_away = False  # every try of some piece cut to another shot: the loop isn't this picture any more
        start = name
        try:
            for k in range(pieces):
                part = f" (part {k + 1} of {pieces})" if pieces > 1 else ""
                last = k == pieces - 1
                length = h3.snap_length(s["seconds"] / pieces + (OVERLAP if last else JOIN))
                best = None
                for n in range(TRIES):
                    seed = random.randrange(2**31)
                    # The last try, after forward ones that all moved too much, is anchored: its end pinned (to the cover
                    # on the loop's last piece), so it can't wander off. A free H3 clip of an abstract picture can
                    # reinvent it (a sand pattern grew a cone, 2026-10-09), and closing the loop then shows a ghost.
                    anchored = n == TRIES - 1 and all(t["motion"] in ("too much", "cuts") for t in tried if t["piece"] == k)
                    again = f", try {n + 1}" + (" (held to the cover)" if anchored else "") if n else ""
                    span = ((k + n / TRIES) / pieces, (k + (n + 1) / TRIES) / pieces)
                    ctx.update(stage="animate", message=f"H3 is animating it{part}{again}", progress=0.05 + 0.85 * span[0])
                    g = h3.graph(start, text, SIDE, length, seed, f"sv/{pid}/living-{lid}",
                                 end=(name if last else start) if anchored else None)
                    res = await self._run(ctx, g, (0.05 + 0.85 * span[0], 0.05 + 0.85 * span[1]))
                    files = res.files("15", "images") or res.files("15", "videos")
                    if not files:
                        raise JobError("H3 finished without a video.")
                    raw = work / f"raw-{k}-{n}.mp4"
                    await ctx.comfy.download(files[0], raw)
                    clip = raw
                    held = None
                    if people:
                        ctx.update(stage="hold", message=f"Holding the people still{part}")
                        clip = work / f"held-{k}-{n}.mp4"
                        held = await asyncio.to_thread(loops.hold, str(raw), str(clip), str(still), str(people), ff)
                    rep = await asyncio.to_thread(loops.report, str(clip), ff)
                    tried.append({"seed": seed, "piece": k, "held": held, "anchored": anchored,
                                  **{x: rep[x] for x in ("motion", "changed", "cuts")}})
                    if best is None or badness(rep) < badness(best[1]):
                        best = (clip, rep, seed)
                    if acceptable(rep, s["feel"]):
                        break
                kept.append(best[0])
                cut_away = cut_away or bool(best[1].get("cuts"))
                if not last:  # the next piece carries on from JOIN before this one's end (loops.join blends the two)
                    edge = work / f"edge-{k}.png"
                    fps = (await asyncio.to_thread(loops.probe, str(best[0]), ff))["fps"]
                    await asyncio.to_thread(loops.frame_at, str(best[0]), str(edge), round(JOIN * fps), ff)
                    start = await ctx.comfy.upload(edge, subfolder="sv-living")
            rev = int(loop.get("rev") or 0) + 1
            final = folder / f"loop-{lid}-{rev}.mp4"
            whole = kept[0]
            if len(kept) > 1:
                whole = work / "whole.mp4"
                fps = (await asyncio.to_thread(loops.probe, str(kept[0]), ff))["fps"]
                await asyncio.to_thread(loops.join, str(whole), [str(x) for x in kept], round(JOIN * fps), ff)
            ctx.update(stage="close", message="Closing the loop so it flows straight on", progress=0.93)
            fps = (await asyncio.to_thread(loops.probe, str(whole), ff))["fps"]
            await asyncio.to_thread(loops.close, str(whole), str(final), round(OVERLAP * fps), ff)
            rep = await asyncio.to_thread(loops.report, str(final), ff)
            info = await asyncio.to_thread(loops.probe, str(final), ff)
        finally:
            for f in work.glob("*"):
                f.unlink(missing_ok=True)
            work.rmdir()
        old = loop.get("video")
        self.loop_changed(pid, lid, status="ready", video=str(final.relative_to(self.cfg.projects / pid)), rev=rev,
                          cover=cover["n"], seconds=round(info["frames"] / info["fps"], 2), verdict=rep["motion"],
                          changed=rep["changed"], held=bool(people), tries=tried, madeWith=loop["motion"],
                          madeFeel=s["feel"], madeSeconds=s["seconds"], madeHold=hold, way="forward", at=time.time(),
                          usable=not cut_away,
                          unusable=("H3 cut away to a different shot in every try, so it's left out of the video. Change "
                                    "what moves (small details like antennae or fingers invite a close-up) and make it "
                                    "again.") if cut_away else None)
        if old and old != str(final.relative_to(self.cfg.projects / pid)):
            drop(self.cfg.projects / pid, old)
        try:
            self.auto_render(pid)
        except JobError:
            pass
        return {"loop": lid, "verdict": rep["motion"], "tries": len(tried)}

    async def loop_after(self, ctx: Context, job: dict) -> None:
        if job["status"] in ("failed", "cancelled"):
            p = ctx.store.project(job["projectId"])
            loop = next((x for x in self.get(p)["loops"] if x["id"] == job["loopId"]), None) if p else None
            if loop:
                self.loop_changed(job["projectId"], job["loopId"], status="ready" if loop.get("video") else "new",
                                  error=job.get("message") if job["status"] == "failed" else None)

    # ---- the video (CPU) ---------------------------------------------------------------------
    async def render_job(self, ctx: Context) -> dict:
        pid, shape = ctx.job["projectId"], ctx.job["shape"]
        rid = uuid.uuid4().hex[:8]
        out = self.folder(pid) / f"living-{shape}-{rid}.mp4"
        started = time.monotonic()
        made = await self.compose(ctx, pid, shape, out)
        root = self.cfg.projects / pid
        lv, total, cover = made["lv"], made["total"], made["cover"]
        rec = {"id": rid, "file": str(out.relative_to(root)), "shape": shape, "seconds": round(total, 2),
               "bytes": out.stat().st_size, "loops": [x["id"] for x in made["loops"]], "stretches": len(made["plan"]),
               "transition": lv["settings"]["transition"], "feel": lv["settings"]["feel"], "cover": cover["n"],
               "made": {x["id"]: x.get("rev") for x in made["loops"]},
               "renderSeconds": round(time.monotonic() - started, 1), "at": time.time()}
        p = ctx.store.project(pid)
        self.keep_render(pid, rec)
        now = self.get(ctx.store.project(pid) or p)
        auto = now.get("auto") or {}
        if auto.get("status") == "animating" and shape == now["settings"]["shape"]:  # "Claude makes it"
            if auto.get("finish") and shape == "square":  # Claude's finish in code comes next
                job = self.app.sched.submit("living.finish", {"message": "Waiting its turn"}, pid)
                self.put(pid, auto={**auto, "status": "finishing", "render": rid, "finishJob": job["id"]})
            else:
                self.put(pid, auto={**auto, "status": "done", "render": rid})
        return rec

    def keep_render(self, pid: str, rec: dict) -> None:
        """One video per shape, and one with Claude's finish: the newest replaces the one before it."""
        root = self.cfg.projects / pid
        keep = []
        for r in self.get(self.app.store.project(pid) or {})["renders"]:
            if r.get("shape") == rec["shape"] and bool(r.get("finish")) == bool(rec.get("finish")):
                if r.get("file") != rec["file"]:
                    drop(root, r.get("file"))
            else:
                keep.append(r)
        self.put(pid, renders=[rec, *keep])

    async def compose(self, ctx: Context, pid: str, shape: str, out: Path, sleeve: bool = True, report: bool = True) -> dict:
        """The loops through the whole song in `shape`: with the title and logos on top, the song and a fade out
        (sleeve), or the moving picture alone (for Claude's finish to work over)."""
        p, take, art = self.ready(pid)
        lv = self.get(p)
        # a loop that cut away to another shot (usable False) stays on the page to see, but out of the video
        made = [x for x in lv["loops"][: lv["settings"]["count"]] if x.get("video") and x.get("usable", True) is not False
                and (self.cfg.projects / pid / x["video"]).exists()]
        if not made:
            raise JobError("No loop is usable: every one cut away to a different shot. Change what moves and make them again.")
        root = self.cfg.projects / pid
        audio = root / take["files"]["flac"]
        total = float(take.get("duration") or 0)
        if total < 2:
            raise JobError("The song's length isn't known.")
        starts: list[float] = []
        af = root / "takes" / take["id"] / "analysis" / "analysis.json"
        if af.exists():
            try:
                starts = [float(s["start"]) for s in json.loads(af.read_text()).get("sections") or [] if s.get("start")]
            except (ValueError, TypeError, KeyError):
                starts = []
        plan = snap(schedule(total, len(made), starts), total, [float(x.get("seconds") or 6) for x in made])
        kind, xf = TRANSITIONS[lv["settings"]["transition"]]
        W, H = SHAPES[shape]
        side = min(W, H)
        folder = self.folder(pid)
        rid = uuid.uuid4().hex[:8]
        if report:
            ctx.update(stage="layer", message="Setting the title and logos", progress=0.02)
        cover = p["cover"]
        layer = folder / f"layer-{rid}.png"
        bg = folder / f"bg-{rid}.png"

        def prepare() -> None:
            if sleeve:
                picture = covers_mod.square(art, side)
                covers_mod.sleeve(picture, p["title"], cover.get("artist") or "", self.app.covers.logos(),
                                  self.app.covers.look(p), self.app.covers.fonts)[0].save(layer)
            if (W, H) != (side, side):
                big = covers_mod.square(art, max(W, H)).filter(ImageFilter.GaussianBlur(max(W, H) / 40))
                big = Image.eval(big, lambda v: int(v * 0.45))
                big.crop(((big.width - W) // 2, (big.height - H) // 2, (big.width + W) // 2, (big.height + H) // 2)).save(bg)
        await asyncio.to_thread(prepare)

        cmd = [self.cfg.ffmpeg, "-v", "error", "-nostats", "-y", "-progress", "pipe:1"]
        for k, st in enumerate(plan):
            st["xf"] = min(xf, (st["end"] - st["start"]) / 2, (plan[k + 1]["end"] - plan[k + 1]["start"]) / 2) if k + 1 < len(plan) and xf else 0.0
            cmd += ["-stream_loop", "-1", "-t", f"{st['end'] - st['start'] + st['xf']:.3f}", "-i", str(root / made[st["loop"]]["video"])]
        n = len(plan)
        if sleeve:
            cmd += ["-loop", "1", "-framerate", "24", "-t", f"{total:.3f}", "-i", str(layer)]
        if (W, H) != (side, side):
            cmd += ["-loop", "1", "-framerate", "24", "-t", f"{total:.3f}", "-i", str(bg)]
        if sleeve:
            cmd += ["-i", str(audio)]
        f = [f"[{k}:v]fps=24,scale={side}:{side}:flags=lanczos,setsar=1,format=yuv420p[s{k}]" for k in range(n)]
        if kind == "cut" or n == 1:  # one after another (one loop: nothing to change between)
            f.append("".join(f"[s{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=0[x]")
            cur = "x"
        else:
            cur, t = "s0", 0.0
            for k in range(1, n):
                t += plan[k - 1]["end"] - plan[k - 1]["start"]
                how = DIP if kind == "dip" else kind
                f.append(f"[{cur}][s{k}]xfade=transition={how}:duration={plan[k - 1]['xf']:.3f}:offset={t:.3f}[x{k}]")
                cur = f"x{k}"
        nxt = n
        if sleeve:
            f.append(f"[{nxt}:v]format=rgba[lay]")
            f.append(f"[{cur}][lay]overlay=0:0:format=auto[sq]")
            cur, nxt = "sq", nxt + 1
        if (W, H) != (side, side):
            f.append(f"[{nxt}:v]format=yuv420p[bg]")
            f.append(f"[bg][{cur}]overlay=(W-w)/2:(H-h)/2:format=auto[cv]")
            cur, nxt = "cv", nxt + 1
        if sleeve:
            f.append(f"[{cur}]fade=t=out:st={max(0.0, total - FADE_OUT):.3f}:d={FADE_OUT:g},format=yuv420p[v]")
        else:
            f.append(f"[{cur}]format=yuv420p[v]")
        part = out.with_suffix(".part.mp4")
        cmd += ["-filter_complex", ";".join(f), "-map", "[v]"]
        if sleeve:
            cmd += ["-map", f"{nxt}:a", "-af", f"afade=t=out:st={max(0.0, total - FADE_OUT):.3f}:d={FADE_OUT:g}",
                    "-c:a", "aac", "-b:a", "256k"]
        cmd += ["-t", f"{total:.3f}", "-r", "24", "-c:v", "libx264", "-preset", "medium", "-crf", "18" if sleeve else "14",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(part)]
        if report:
            ctx.update(stage="render", message="Putting the video together", progress=0.05)
        ctx.proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            assert ctx.proc.stdout
            async for raw in ctx.proc.stdout:
                line = raw.decode(errors="replace").strip()
                if report and line.startswith("out_time_us="):
                    try:
                        ctx.update(progress=0.05 + 0.93 * min(1.0, int(line.split("=")[1]) / 1e6 / total))
                    except ValueError:
                        pass
            err = (await ctx.proc.stderr.read()).decode(errors="replace") if ctx.proc.stderr else ""
            if await ctx.proc.wait() != 0:
                raise JobError("The video couldn't be put together.", err[-2000:])
            part.replace(out)
        finally:
            part.unlink(missing_ok=True)
            layer.unlink(missing_ok=True)
            bg.unlink(missing_ok=True)
        return {"plan": plan, "loops": made, "total": total, "cover": cover, "lv": lv, "kind": kind}


def register(sched: Scheduler, app, writers: Writers) -> Living:
    lv = Living(app, writers)

    async def loop(ctx: Context) -> dict:
        return await lv.loop_job(ctx)
    loop.after = lv.loop_after  # type: ignore[attr-defined]
    sched.register("living.loop", "gpu", loop)
    sched.register("living.render", "cpu", lv.render_job)

    async def auto(ctx: Context) -> dict:
        return await lv.auto_job(ctx)
    auto.after = lv.auto_after  # type: ignore[attr-defined]
    sched.register("living.auto", "net", auto)
    return lv
