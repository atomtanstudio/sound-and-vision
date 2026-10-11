"""Starting songs: the shared path from a request to takes on the GPU queue (used by the Music page's
Make button and by the Home prompt), and the Home prompt's own job, which reads whatever was typed,
fills in the whole song, and starts two takes at once (as Suno does)."""

from __future__ import annotations

import re
import time
import uuid

from . import influences
from .jobs import Context, JobError, Scheduler
from .music import eleven, others, yue2
from .writers import Writers, WriterError
from .writers.tasks import split_prompt

KIND_OF = {"intro": "intro", "verse": "verse", "pre-chorus": "pre-chorus", "prechorus": "pre-chorus", "chorus": "chorus",
           "refrain": "chorus", "post-chorus": "post-chorus", "bridge": "bridge", "hook": "hook",
           "instrumental": "instrumental", "interlude": "instrumental", "outro": "outro"}


def focus(items: str, most: int) -> str:
    """The first few items of a comma list: a long style dilutes what YuE2 hears (it reads the start best)."""
    return ", ".join([x.strip() for x in (items or "").split(",") if x.strip()][:most])


def sid() -> str:
    return "s" + uuid.uuid4().hex[:10]


def parse_lyrics(text: str) -> list[dict]:
    """Pasted lyrics into the sheet's sections ({id, kind, text}); tags kept, plain stanzas become verses."""
    out: list[dict] = []
    cur: dict | None = None
    for raw in (text or "").splitlines():
        line = raw.strip()
        m = re.fullmatch(r"\[([^\]]+)\]", line)
        if m:
            key = re.sub(r"\s*\d+\s*$", "", m.group(1).strip().lower()).replace(" ", "-")
            cur = {"id": sid(), "kind": KIND_OF.get(key, "verse"), "text": ""}
            out.append(cur)
        elif line:
            if cur is None:
                cur = {"id": sid(), "kind": "verse", "text": ""}
                out.append(cur)
            cur["text"] += ("\n" if cur["text"] else "") + line
        elif cur is not None and cur["text"]:
            cur = None
    return out


def lyrics_text(sections: list[dict]) -> str:
    def label(k: str) -> str:
        return {"pre-chorus": "Pre-Chorus", "post-chorus": "Post-Chorus"}.get(k, k.title())
    return "\n\n".join(f"[{label(s['kind'])}]\n" + "\n".join(l.strip() for l in s.get("text", "").splitlines() if l.strip())
                       for s in sections)


def start_takes(app, pid: str, req: yue2.SongRequest) -> dict:
    """Queue `req.takes` YuE2 takes for a song. `app` carries cfg, store, hub and sched."""
    sent = yue2.prepare(req, influences.library(app.cfg.loras))
    request = req.model_dump()
    made = []
    for seed in yue2.seeds(req):
        take = app.store.create_take(pid, "yue2", {"seed": seed, "sent": sent, "request": request})
        job = app.sched.submit("song.yue2", {"message": "Waiting its turn"}, pid, take["id"])
        take = app.store.update_take(take["id"], jobId=job["id"])
        app.hub.publish("take", take)
        made.append(take)
    return {"takes": made, "style": sent["style"], "lyrics": sent["lyrics"]}


def start_other_takes(app, pid: str, model: str, req: yue2.SongRequest) -> dict:
    """Queue takes from ACE-Step 1.5 or MiniMax Music 3."""
    sent = others.prepare(model, req, influences.library(app.cfg.loras))
    made = []
    for seed in yue2.seeds(req):
        take = app.store.create_take(pid, model, {"seed": seed, "sent": sent, "request": req.model_dump()})
        job = app.sched.submit("song.other", {"message": "Waiting its turn"}, pid, take["id"])
        take = app.store.update_take(take["id"], jobId=job["id"])
        app.hub.publish("take", take)
        made.append(take)
    return {"takes": made, "style": sent["style"], "lyrics": sent["lyrics"]}


def start_eleven_takes(app, pid: str, offer: dict, req: yue2.SongRequest, options: dict | None) -> dict:
    """Queue takes of ElevenLabs Music on the person's MCP server (`offer`, from eleven.offered): each take is one run
    there, charged to their plan on that server."""
    sid = eleven.server_of(offer["id"])
    sent = eleven.prepare(req, sid, options, offer.get("fields"), influences.library(app.cfg.loras))
    made = []
    for seed in yue2.seeds(req):
        take = app.store.create_take(pid, "eleven", {"seed": seed, "sent": sent, "request": req.model_dump()})
        job = app.sched.submit("song.eleven", {"message": "Waiting its turn"}, pid, take["id"])
        take = app.store.update_take(take["id"], jobId=job["id"])
        app.hub.publish("take", take)
        made.append(take)
    return {"takes": made, "style": sent["style"], "lyrics": sent["lyrics"]}


def request_from_doc(doc: dict, takes: int = 2) -> yue2.SongRequest:
    return yue2.SongRequest(
        sung=doc.get("sung", True), voice=doc.get("voice"), language=doc.get("language") or "English",
        genres=doc.get("genres") or [], moods=doc.get("moods") or [], instruments=doc.get("instruments") or "",
        extra=doc.get("extra") or "", tempo=doc.get("tempo"), key=doc.get("key"),
        lyrics=lyrics_text(doc.get("sections") or []), length=doc.get("length") or "song",
        influences=doc.get("influences") or [], takes=takes, plan=doc.get("plan") or "full",
        creativity=doc.get("creativity") or 1.0, repetition=doc.get("repetition") or 1.2)


class Quick:
    """The Home prompt's job (network lane): read → fill in the song → start two takes."""

    def __init__(self, app, writers: Writers):
        self.app, self.writers = app, writers

    async def __call__(self, ctx: Context) -> dict:
        pid = ctx.job["projectId"]
        typed = ctx.job.get("prompt") or ""
        description, own = split_prompt(typed)
        own_sections = parse_lyrics(own) if own else []
        ctx.update(stage="read", message="Reading your idea", progress=0.1)
        t0 = time.monotonic()
        try:
            r = await self.writers.write("interpret", {"text": description, "ownSections": len(own_sections)})
        except WriterError as exc:
            raise JobError(f"Couldn't read the idea: {exc}") from None
        plan, by = r["result"], r["by"]
        sections = own_sections or [{"id": sid(), "kind": s["kind"], "text": "\n".join(s["lines"])} for s in plan["sections"]]
        if plan["sung"] and not sections:
            raise JobError("The idea came back without words. Try again, or write a line or two of lyrics.")
        p = ctx.store.project(pid)
        if p is None:
            raise JobError("That song was deleted.")
        doc = {k: v for k, v in p.items() if k not in ("id", "title", "rev", "createdAt", "updatedAt")}
        doc.update(idea=plan["idea"] or description[:400], sung=plan["sung"], voice=plan["voice"], language=plan["language"],
                   genres=plan["genres"] or ["pop"], moods=plan["moods"], instruments=focus(plan["instruments"], 6),
                   extra=", ".join(x for x in (focus(plan["production"], 4), focus(plan["vocalStyle"], 1)) if x), tempo=plan["tempo"],
                   key=plan["key"], length=plan["length"], sections=sections, prompt=typed,
                   writtenBy={"provider": by["provider"], "model": by.get("model"), "seconds": round(time.monotonic() - t0, 1),
                              "ownLyrics": bool(own_sections)})
        p = ctx.store.save_project(pid, plan["title"], doc, None)
        ctx.hub.publish("project", p)
        ctx.update(stage="start", message="Starting two takes", progress=0.8)
        try:
            made = start_takes(self.app, pid, request_from_doc(doc, takes=int(ctx.job.get("takes") or 2)))
        except yue2.SongError as exc:
            raise JobError(str(exc)) from None
        covers = getattr(self.app, "covers", None)
        if covers and (auto := covers.auto_engine()):
            covers.start(pid, auto)  # the sleeve, made while the takes sing
        return {"projectId": pid, "takes": [t["id"] for t in made["takes"]], "style": made["style"], "by": by}


UNTITLED = ("", "Untitled song", "New song")


class Title:
    """An untitled song gets a title from its words when its first takes are made (the user can change it)."""

    def __init__(self, app, writers: Writers):
        self.app, self.writers = app, writers

    async def __call__(self, ctx: Context) -> dict:
        p = ctx.store.project(ctx.job["projectId"])
        if p is None or p["title"].strip() not in UNTITLED:
            return {"skipped": True}
        song = {"idea": p.get("idea"), "sections": [{"kind": s.get("kind"), "lines": s.get("text", "").splitlines()}
                                                     for s in p.get("sections") or []]}
        try:
            r = await self.writers.write("titles", {"song": song})
        except WriterError:
            return {"skipped": True}
        title = next((t for t in r["result"]["titles"] if t.strip()), None)
        p = ctx.store.project(p["id"])
        if not title or p is None or p["title"].strip() not in UNTITLED:
            return {"skipped": True}
        p = ctx.store.patch_project(p["id"], title=title[:80])
        ctx.hub.publish("project", p)
        return {"title": title}


def name_if_untitled(app, pid: str) -> None:
    p = app.store.project(pid)
    if p and p["title"].strip() in UNTITLED and (p.get("idea") or p.get("sections")):
        app.sched.submit("title", {"message": "Naming the song"}, pid)


def register(sched: Scheduler, app, writers: Writers) -> None:
    sched.register("quick", "net", Quick(app, writers))
    sched.register("title", "net", Title(app, writers))
