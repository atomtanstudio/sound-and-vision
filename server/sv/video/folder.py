"""A work folder for a Claude session in the studio container (a motion graphics film, a living cover's finish), set up
the way the person's chat-made films started: an empty folder with the song in it. What the app adds is material, never
rules: song/ (the song, its stems, its timed words, what's known about it), analysis/ (the app's measurements, by the
kit's import_song.py, run from outside the folder), node_modules/ and fonts/ copied in, pip set up in .local/, and the
folder's CLAUDE.md: the job's own notes plus MACHINE.md (what this machine has). Nothing else from the old film kit
(its engine, manual, method, skills) comes in: those were the rules that made the app's films look alike.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from ..jobs import JobError
from ..studio import machine_trouble


async def studio(cfg, *args: str, timeout: float = 1800) -> None:
    proc = await asyncio.create_subprocess_exec(str(cfg.studio_sh), *args, stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError:
        proc.kill()
        raise JobError(f"Setting up the studio took too long ({args[0]}).") from None
    if proc.returncode != 0:
        text = out.decode(errors="replace")
        raise JobError(machine_trouble(text) or f"Setting up the studio didn't work ({args[0]}).", text[-2000:])


async def ff(cfg, *args: str) -> None:
    proc = await asyncio.create_subprocess_exec(cfg.ffmpeg, "-v", "error", "-y", *args,
                                                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
    _, err = await proc.communicate()
    if proc.returncode != 0:
        raise JobError("A video step didn't work.", err.decode(errors="replace")[-2000:])


MACHINE = Path(__file__).resolve().parent / "MACHINE.md"

# Run in the container with the folder as /work: the kit's npm packages and fonts copied in (copies, so `npm install`
# can add to them), and pip set up for the folder (the image's Python has none). pip needs the network; without it the
# notes say how Claude can set it up later.
_SETUP = r"""
set -e
cp -r /opt/kit/node_modules /work/node_modules
cp -r /opt/kit/fonts /work/fonts
node -e 'const d = require("/opt/kit/package.json").dependencies; require("fs").writeFileSync("/work/package.json",
  JSON.stringify({name: "film", version: "1.0.0", private: true, dependencies: d}, null, 2) + "\n")'
if curl -fsSL --max-time 60 https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py; then
  PYTHONUSERBASE=/work/.local PIP_BREAK_SYSTEM_PACKAGES=1 python3 /tmp/get-pip.py --user -q --no-warn-script-location || true
fi
"""


async def seed(cfg, work: Path, claude_md: Path) -> None:
    """The folder, ready for Claude: `claude_md` (and MACHINE.md under it) as its CLAUDE.md, out/, and the tools."""
    (work / "out").mkdir(parents=True, exist_ok=True)
    (work / "CLAUDE.md").write_text(claude_md.read_text().rstrip() + "\n\n" + MACHINE.read_text())
    await studio(cfg, "exec", str(work), "sh", "-c", _SETUP, timeout=600)


async def song(cfg, p: dict, take: dict, work: Path, meta: dict) -> None:
    """song/: the master as AAC, the stems the listening made, the timing (in the shape import_song.py reads) and
    meta.json; then analysis/ from them."""
    root = cfg.projects / p["id"]
    folder = work / "song"
    folder.mkdir(parents=True, exist_ok=True)
    await ff(cfg, "-i", str(root / take["files"]["flac"]), "-vn", "-c:a", "aac", "-b:a", "320k", str(folder / "song.m4a"))
    ana_dir = root / "takes" / take["id"] / "analysis"
    for stem, name in (("vocals", "vocals.m4a"), ("drums", "stems/drums.m4a"), ("bass", "stems/bass.m4a"),
                       ("other", "stems/other.m4a")):
        if (ana_dir / f"{stem}.m4a").exists():
            (folder / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ana_dir / f"{stem}.m4a", folder / name)
    try:
        ana = json.loads((ana_dir / "analysis.json").read_text())
    except (OSError, ValueError):
        ana = {}
    tempo = ana.get("tempo")
    if isinstance(tempo, dict):  # an older analysis kept the tempo with its curve
        tempo = tempo.get("bpm")
    timing = {"version": 1, "tempo": float(tempo) if isinstance(tempo, (int, float)) and tempo > 0 else None,
              "beats": ana.get("beats") or [],
              "downbeat": (ana.get("downbeat") or {}).get("first", 0),
              "sections": [{"name": s.get("label") or f"part {i + 1}", "start": s["start"], "end": s["end"]}
                           for i, s in enumerate(ana.get("sections") or []) if "start" in s and "end" in s],
              "lines": ana.get("lines") or []}
    (folder / "timing.json").write_text(json.dumps(timing))
    (folder / "meta.json").write_text(json.dumps(meta, indent=1))


async def measure(cfg, work: Path) -> None:
    """analysis/ from song/, by the kit's import_song.py, run from a scratch copy so the kit stays out of the folder."""
    (work / "analysis").mkdir(exist_ok=True)
    await studio(cfg, "exec", str(work), "sh", "-c",
                 "mkdir -p /tmp/m/tools && cp /opt/kit/tools/import_song.py /tmp/m/tools/ && ln -s /work/song /tmp/m/song "
                 "&& ln -s /work/analysis /tmp/m/analysis && python3 /tmp/m/tools/import_song.py", timeout=1800)
