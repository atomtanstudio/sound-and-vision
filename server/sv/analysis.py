"""Listening to the chosen take, on the GPU, in one sv-analysis container (holds no VRAM after):
stems (MelBand RoFormer vocals; drums, bass, guitar, piano, other), the words timed against the
vocals (wav2vec2 CTC on the known lyrics), and the song map (beats, bars, sections). The result is
saved as the take's analysis.json, in the shape the interface draws, plus AAC stems to play."""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

from . import media
from .jobs import Context, JobError

LABELS = {"stems": "Separating the vocals and instruments", "hear": "Listening for the words",
          "listen": "Listening to the vocals", "align": "Placing every word", "rhythm": "Finding the beat and the sections"}
SPANS = {"stems": (0.02, 0.4), "hear": (0.4, 0.55), "listen": (0.55, 0.65), "align": (0.65, 0.78), "rhythm": (0.78, 0.95)}
STEM_NAMES = ("vocals", "drums", "bass", "guitar", "piano", "other", "instrumental")


def sections_of(lyrics: str) -> list[dict]:
    out: list[dict] = []
    for line in (lyrics or "").splitlines():
        m = re.fullmatch(r"\s*\[([^\]]+)\]\s*", line)
        if m:
            out.append({"id": f"s{len(out)}", "label": m.group(1).strip(), "lines": []})
        elif line.strip() and out:
            out[-1]["lines"].append(line.strip())
    verse = 0
    for s in out:
        if s["label"].lower() == "verse":
            verse += 1
            s["label"] = f"Verse {verse}"
    return [s for s in out if s["lines"]]


def shape(timing: dict | None, songmap: dict | None) -> dict:
    """The aligner's timing and the song map, as the interface uses them."""
    lines, sections = [], []
    if timing:
        label = {s.get("section"): s.get("label") for s in timing.get("sections") or []}
        words: dict[tuple, list] = {}
        for w in timing.get("words") or []:
            words.setdefault((w.get("section"), w.get("line")), []).append(
                {"text": w["text"], "start": w["start"], "end": w["end"], **({"score": w["score"]} if "score" in w else {})})
        for i, ln in enumerate(timing.get("lines") or []):
            lines.append({"id": f"l{i + 1}", "text": ln["text"], "start": ln["start"], "end": ln["end"],
                          "section": label.get(ln.get("section")) or "", **({"score": ln["score"]} if "score" in ln else {}),
                          "words": words.get((ln.get("section"), ln.get("line")), [])})
    sm = songmap or {}
    tempo = sm.get("tempo") or (timing or {}).get("tempo")
    bpm = tempo.get("bpm") if isinstance(tempo, dict) else tempo
    for s in sm.get("segments") or []:
        sections.append({"label": s.get("label") or "", "start": s.get("start"), "end": s.get("end")})
    return {"tempo": bpm, "tempoCurve": tempo.get("curve") if isinstance(tempo, dict) else None, "beats": sm.get("beats") or (timing or {}).get("beats") or [],
            "downbeat": sm.get("downbeat"), "bars": sm.get("bars") or [], "sections": sections, "lines": lines}


async def run_analysis(ctx: Context) -> dict:
    tid = ctx.job["takeId"]
    take = ctx.store.take(tid)
    if take is None or take["status"] != "ready":
        raise JobError("That take isn't ready to listen to.")
    folder = ctx.cfg.projects / take["projectId"] / "takes" / tid
    out = folder / "analysis"
    out.mkdir(parents=True, exist_ok=True)
    sent = take["sent"]
    sections = sections_of(sent.get("lyrics") or "") if sent.get("sung") else []
    if sent.get("upload"):  # your own song: its lyric sheet as it is now (words you've corrected included)
        from .songs import lyrics_text
        sheet = [x for x in (ctx.store.project(take["projectId"]) or {}).get("sections") or [] if (x.get("text") or "").strip()]
        if sheet:
            sections = sections_of(lyrics_text(sheet))
    spec: dict = {"song": "/take/song.flac", "out": "/take/analysis", "sections": sections}
    snapshot = next(iter(sorted((ctx.cfg.whisper / "snapshots").glob("*"))), None) if (ctx.cfg.whisper / "snapshots").is_dir() else None
    # your own uploaded song: without its lyrics, Whisper hears them first; an LRC's times keep each line near its place
    hearing = bool(sent.get("upload") and sent.get("sung") is not False and not sections and snapshot)
    if hearing:
        spec["hear"] = {"model": f"/whisper/snapshots/{snapshot.name}", **({"language": sent["language"]} if sent.get("language") else {})}
    if sections and sent.get("lrc"):
        spec.update(heard=sent["lrc"], heardFrom="the LRC file has it")
    (out / "spec.json").write_text(json.dumps(spec))
    ctx.store.update_take(tid, analysis={"status": "running"})
    ctx.take_changed(ctx.store.take(tid))

    cmd = ["docker", "run", "--rm", "--gpus", "all", "--user", f"{os.getuid()}:{os.getgid()}", "--shm-size", "4g",
           "--name", f"sv-analysis-{ctx.job['id']}", "-e", "HOME=/tmp", "-e", "TORCH_HOME=/models/torch",
           "-v", f"{ctx.cfg.analysis_models}:/models", "-v", f"{ctx.cfg.analysis_worker}:/worker:ro",
           *(["-v", f"{ctx.cfg.whisper}:/whisper:ro"] if hearing else []),
           "-v", f"{folder}:/take", ctx.cfg.analysis_image, "/worker/analyze.py", "/take/analysis/spec.json"]
    ctx.update(stage="stems", message=LABELS["stems"], progress=0.02)
    ctx.proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    done: dict | None = None
    error: str | None = None
    tail: list[str] = []
    assert ctx.proc.stdout
    async for raw in ctx.proc.stdout:
        line = raw.decode(errors="replace").strip()
        if not line.startswith("{"):
            tail = [*tail[-20:], line]
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        kind = ev.get("event")
        if kind == "stage" and ev.get("stage") in SPANS:
            ctx.update(stage=ev["stage"], message=LABELS[ev["stage"]], progress=SPANS[ev["stage"]][0])
        elif kind == "progress" and ev.get("stage") in SPANS and ev.get("total"):
            lo, hi = SPANS[ev["stage"]]
            ctx.update(progress=lo + (hi - lo) * ev["done"] / ev["total"])
        elif kind == "done":
            done = ev
        elif kind == "error":
            error = ev.get("message")
    code = await ctx.proc.wait()
    if ctx.cancelled:
        await asyncio.create_subprocess_exec("docker", "stop", "-t", "2", f"sv-analysis-{ctx.job['id']}")
        raise JobError("Stopped.")
    if code != 0 or done is None:
        raise JobError("Listening to the song didn't finish." + (f" {error}" if error else ""), detail="\n".join(tail))

    ctx.update(stage="finish", message="Getting the stems ready to play", progress=0.96)
    stems = {}
    for name in STEM_NAMES:
        src = out / f"{name}.flac"
        if src.exists():
            await asyncio.to_thread(media.to_m4a, src, out / f"{name}.m4a", ctx.cfg.ffmpeg)
            stems[name] = str(Path("takes") / tid / "analysis" / f"{name}.m4a")
    if (out / "vocals.flac").exists():
        await asyncio.to_thread(media.peaks, out / "vocals.flac", out / "vocals.peaks.json", ctx.cfg.ffmpeg)
    timing = json.loads((out / "timing.json").read_text()) if (out / "timing.json").exists() else None
    songmap = json.loads((out / "songmap.json").read_text()) if (out / "songmap.json").exists() else None
    shaped = shape(timing, songmap)
    (out / "analysis.json").write_text(json.dumps(shaped))
    heard = None
    if (out / "heard.json").exists():
        heard = json.loads((out / "heard.json").read_text())
        _words_heard(ctx, take, heard)
    ctx.store.update_take(tid, analysis={
        "status": "ready", **({"heard": {"lines": len(heard["lines"]), "language": heard.get("language")}} if heard else {}), "file": str(Path("takes") / tid / "analysis" / "analysis.json"), "stems": stems,
        "vocalsPeaks": str(Path("takes") / tid / "analysis" / "vocals.peaks.json") if (out / "vocals.peaks.json").exists() else None,
        "tempo": shaped["tempo"], "lines": len(shaped["lines"]), "warnings": done.get("warnings") or [],
        "seconds": done.get("seconds")})
    ctx.take_changed(ctx.store.take(tid))
    return {"takeId": tid, "lines": len(shaped["lines"]), "stems": list(stems)}


def _words_heard(ctx: Context, take: dict, heard: dict) -> None:
    """The words Whisper heard become the song's lyric sheet (a draft to check), when it has none of its own."""
    p = ctx.store.project(take["projectId"])
    if not p or any((s.get("text") or "").strip() for s in p.get("sections") or []):
        return
    from .songs import sid
    groups: list[list[str]] = []
    last_end = None
    for ln in heard.get("lines") or []:
        if last_end is None or ln["start"] - last_end > 3.5:
            groups.append([])
        groups[-1].append(ln["text"])
        last_end = ln["end"]
    sections = [{"id": sid(), "kind": "verse", "text": "\n".join(g)} for g in groups if g]
    if sections:
        p = ctx.store.patch_project(p["id"], sections=sections, lyricsHeard=True, sung=True)
        ctx.hub.publish("project", p)


async def _after(ctx: Context, job: dict) -> None:
    if job["status"] in ("failed", "cancelled"):
        t = ctx.store.take(job["takeId"])
        if t:
            ctx.store.update_take(t["id"], analysis={"status": job["status"], "error": job.get("message")})
            ctx.take_changed(ctx.store.take(t["id"]))


run_analysis.after = _after  # type: ignore[attr-defined]
