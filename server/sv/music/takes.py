"""Making a take: the job that runs YuE2's sketch and singing stages on sv-comfy, brings the audio
back, and gets it ready to play (AAC copy, waveform peaks). The take record moves through
queued → sketching → singing → finishing → ready (or failed / stopped), and every step is
published, so the takes list fills in live."""

from __future__ import annotations

import asyncio
from pathlib import Path

from .. import media
from ..comfy.client import Result
from ..comfy.registry import Influence
from ..jobs import Context, JobError
from .yue2 import guard


async def _run(ctx: Context, graph: dict, spans: dict[str, tuple[float, float]]) -> Result:
    """Run a graph, mapping each node's own progress into the job's overall progress."""

    def on(ev: dict) -> None:
        if ev["type"] == "queued":
            ctx.prompt_id = ev["prompt_id"]
        elif ev["type"] == "progress" and ev.get("max"):
            lo, hi = spans.get(str(ev.get("node")), (None, None))
            if lo is not None:
                ctx.update(progress=lo + (hi - lo) * ev["value"] / ev["max"])
        elif ev["type"] == "node":
            lo, _ = spans.get(str(ev.get("node")), (None, None))
            if lo is not None:
                ctx.update(progress=lo, force=True)

    try:
        return await ctx.comfy.run(graph, on)
    finally:
        ctx.prompt_id = None


def _publish_take(ctx: Context, tid: str, status: str | None = None, **fields) -> dict:
    t = ctx.store.update_take(tid, status, **fields)
    ctx.take_changed(t)
    return t


async def run_yue2_take(ctx: Context) -> dict:
    tid = ctx.job["takeId"]
    take = ctx.store.take(tid)
    if take is None:
        raise JobError("That take was deleted.")
    sent, seed = take["sent"], take["seed"]
    infl = [Influence(i["file"], i["strength"]) for i in sent["influences"]]
    folder = ctx.cfg.projects / take["projectId"] / "takes" / tid
    folder.mkdir(parents=True, exist_ok=True)

    abc = ""
    if sent["sketch"] and sent["sketch"].get("reference"):
        abc = await _cover_sketch(ctx, take, sent, folder)
    elif sent["sketch"]:
        ctx.update(stage="sketch", message="Writing the melody" + (" and chords" if sent["plan"] == "full" else ""), progress=0.02)
        _publish_take(ctx, tid, "sketching")
        g = ctx.registry["song.yue2.plan"].bind({**sent["sketch"], "seed": seed}, influences=infl)
        res = await _run(ctx, g, {"abc": (0.02, 0.22)})
        text = ((res.outputs.get("show") or {}).get("text") or [""])[0]
        if not text.strip():
            raise JobError("YuE2 didn't write a sketch for this one. Try again (a new seed usually fixes it).")
        fitted, report = guard(text, sent["lyrics"])
        abc = fitted or text
        (folder / "sketch.abc").write_text(abc)
        _publish_take(ctx, tid, sketch=abc, sketchTrimmed=report or None)

    ctx.update(stage="sing", message="Singing" if sent["sung"] else "Playing", progress=0.24)
    _publish_take(ctx, tid, "singing")
    g = ctx.registry["song.yue2.sing"].bind({**sent["sing"], "abc": abc, "seed": seed}, influences=infl,
                                           prefix=f"sv/{take['projectId']}/{tid}")
    res = await _run(ctx, g, {"music": (0.24, 0.86), "sample": (0.86, 0.95), "decode": (0.95, 0.96)})
    refs = res.files("save")
    if not refs:
        raise JobError("YuE2 finished without any audio.", detail=res.outputs)

    planned = ((res.outputs.get("seconds") or {}).get("text") or [None])[0]
    cap = float(sent["sing"]["seconds"])
    truncated = planned is not None and float(planned) >= cap - 0.5
    return await _finish(ctx, tid, folder, res, refs[0], truncated, {"sketch": "sketch.abc"} if abc else {})


async def _cover_sketch(ctx: Context, take: dict, sent: dict, folder: Path) -> str:
    """A cover's sketch: the song being covered, its melody (and chords, in "full") written down by SheetSage2. Kept
    beside the reference, once per mode, so a cover's takes share it; then fitted to the lyrics like YuE2's own."""
    tid, mode = take["id"], sent["sketch"]["mode"]
    root = ctx.cfg.projects / take["projectId"]
    ref = root / sent["sketch"]["reference"]
    if not ref.exists():
        raise JobError("The song to cover isn't there any more: choose it again.")
    cached = ref.with_name(f"{ref.stem}-{mode}.abc")
    ctx.update(stage="sketch", message="Writing down the melody" + (" and chords" if mode == "full" else "") + " of the song you're covering",
               progress=0.02)
    _publish_take(ctx, tid, "sketching")
    if cached.exists():
        text = cached.read_text()
    else:
        # LoadAudio lists only the top of ComfyUI's input folder
        name = await ctx.comfy.upload(ref, subfolder="")
        g = ctx.registry["song.yue2.transcribe"].bind({"audio": name, "mode": mode})
        res = await _run(ctx, g, {"abc": (0.02, 0.22)})
        text = ((res.outputs.get("show") or {}).get("text") or [""])[0]
        if not text.strip():
            raise JobError("The melody couldn't be written down from that song. Try another, or another part of it.")
        cached.write_text(text)
    fitted, report = guard(text, sent["lyrics"])
    abc = fitted or text
    (folder / "sketch.abc").write_text(abc)
    _publish_take(ctx, tid, sketch=abc, sketchTrimmed=report or None, coverOf=sent["sketch"]["reference"])
    return abc


async def _finish(ctx: Context, tid: str, folder: Path, res: Result, ref: dict, truncated: bool, more: dict) -> dict:
    """The audio back from ComfyUI, made ready to play: the FLAC, an AAC copy and the waveform."""
    ctx.update(stage="finish", message="Getting it ready to play", progress=0.96)
    _publish_take(ctx, tid, "finishing")
    flac = await ctx.comfy.download(ref, folder / "song.flac")
    ffmpeg = ctx.cfg.ffmpeg
    await asyncio.to_thread(media.to_m4a, flac, folder / "song.m4a", ffmpeg)
    await asyncio.to_thread(media.peaks, flac, folder / "peaks.json", ffmpeg)
    seconds = await asyncio.to_thread(media.duration, flac, ffmpeg)
    rel = lambda p: str(Path("takes") / tid / p)  # noqa: E731
    _publish_take(ctx, tid, "ready", duration=seconds, truncated=truncated,
                  files={"flac": rel("song.flac"), "audio": rel("song.m4a"), "peaks": rel("peaks.json"),
                         **{k: rel(v) for k, v in more.items()}},
                  comfySeconds=res.seconds, error=None)
    return {"takeId": tid, "duration": seconds}


async def run_other_take(ctx: Context) -> dict:
    """An ACE-Step 1.5 or MiniMax Music 3 take: one stage, the whole song at once."""
    tid = ctx.job["takeId"]
    take = ctx.store.take(tid)
    if take is None:
        raise JobError("That take was deleted.")
    sent, seed, model = take["sent"], take["seed"], take["model"]
    infl = [Influence(i["file"], i["strength"]) for i in sent["influences"]]
    folder = ctx.cfg.projects / take["projectId"] / "takes" / tid
    folder.mkdir(parents=True, exist_ok=True)
    name = {"ace15": "ACE-Step", "music3": "Music 3"}.get(model, model)
    ctx.update(stage="sing", message=f"{name} is {'singing' if sent['sung'] else 'playing'}", progress=0.05)
    _publish_take(ctx, tid, "singing")
    g = ctx.registry[f"song.{model}"].bind({**sent["params"], "seed": seed % (2**32 if model == "music3" else 2**63)},
                                          influences=infl, prefix=f"sv/{take['projectId']}/{tid}")
    res = await _run(ctx, g, {"enc": (0.05, 0.35), "sample": (0.35, 0.92), "decode": (0.92, 0.95)})
    refs = res.files("save")
    if not refs:
        raise JobError(f"{name} finished without any audio.", detail=res.outputs)
    return await _finish(ctx, tid, folder, res, refs[0], False, {})


async def _after(ctx: Context, job: dict) -> None:
    """When a take's job ends without a song, the take says why."""
    if job["status"] in ("failed", "cancelled"):
        t = ctx.store.take(job["takeId"])
        if t and t["status"] != "ready":
            _publish_take(ctx, t["id"], "failed" if job["status"] == "failed" else "stopped", error=job.get("message"))


run_yue2_take.after = _after  # type: ignore[attr-defined]
run_other_take.after = _after  # type: ignore[attr-defined]
