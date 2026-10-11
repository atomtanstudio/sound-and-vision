"""QA on a rendered file: hard cuts, single-frame glitches (A-B-A pops), and when each sung word lands.

  python3 tools/qa.py out/film.mp4 [--no-cues] [--tol 1]

The render's sidecar (<file>.json, written by tools/render.mjs) says which frame of the song the file starts at; without
it the file is taken to start at song time 0. Times are song times; positions are bar.beat.

Word landing (a heuristic, made for type that appears on its cue): for each lyric word cued inside the file, the frame
where the light arriving in the picture around its cue frame passes half of what arrives in that window
(in linear light), compared with the word's cue frame (the first frame whose centre is at or after the cue). With motion
blur a word cued just after a frame's centre is partly visible on the frame before; that is expected. Anything else that
lights up at the same moment (a flash, a plate, a graphic on the same drum hit) can pull the measure a frame off: look at
a strip (node tools/shot.mjs strip <t>) when a word reports a miss.
"""

import argparse
import json
import subprocess
import sys
from math import ceil
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--no-cues", action="store_true", help="skip the word-landing check")
    ap.add_argument("--tol", type=int, default=1, help="frames a landing may be off and still pass (default 1)")
    a = ap.parse_args()
    path = Path(a.video)
    side = Path(str(path) + ".json")
    info = json.loads(side.read_text()) if side.exists() else {}
    an = json.loads((ROOT / "analysis/analysis.json").read_text())
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate",
                            "-of", "json", str(path)], capture_output=True, text=True)
    st = json.loads(probe.stdout or "{}").get("streams") or [{}]
    if not st[0]:
        sys.exit(f"can't read {path}")
    num, den = st[0]["r_frame_rate"].split("/")
    fps = info.get("fps") or round(int(num) / int(den), 3)
    f0 = info.get("firstFrame", 0)
    w, h = max(16, st[0]["width"] // 8 // 2 * 2), max(16, st[0]["height"] // 8 // 2 * 2)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"scale={w}:{h}:flags=area,format=gray", "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    g = np.frombuffer(raw, np.uint8).reshape(-1, h, w).astype(np.int16)
    n = len(g)
    bars = np.array(an["bars"])
    meter = an.get("meter", 4)

    def song_t(j: int) -> float:
        return (f0 + j + 0.5) / fps

    def pos(t: float) -> str:
        i = int(np.clip(np.searchsorted(bars, t, side="right") - 1, 0, len(bars) - 2))
        return f"{i + 1}.{(t - bars[i]) / (bars[i + 1] - bars[i]) * meter + 1:3.1f}"

    print(f"{path}: {n} frames at {fps} fps, song {song_t(0) - 0.5 / fps:.3f}–{song_t(n - 1) + 0.5 / fps:.3f} s"
          + ("" if side.exists() else " (no sidecar: taken to start at 0)"))
    # ---- cuts and pops, on a coarse copy
    c = g.reshape(n, h // 2, 2, w // 2, 2).mean((2, 4)).reshape(n, -1).astype(np.float32)
    d1 = np.abs(c[1:] - c[:-1]).mean(1)
    d2 = np.abs(c[2:] - c[:-2]).mean(1)
    print(f"median frame difference {np.median(d1):.2f}" if len(d1) else "one frame only")
    pops = [i + 1 for i in range(n - 2) if d1[i] > 6 and d1[i + 1] > 6 and d2[i] < 0.35 * min(d1[i], d1[i + 1])]
    print("single-frame pops:", [(round(song_t(p), 3), pos(song_t(p)), round(float(d1[p - 1]), 1)) for p in pops][:60] or "none")
    cuts = [i + 1 for i in range(2, n - 3) if d1[i] > 14 and d1[i] > 4 * (np.median(d1[max(0, i - 6):i + 7]) + 0.5)]
    print(f"hard cuts: {len(cuts)}")
    row = [f"{song_t(j):8.3f} ({pos(song_t(j))})" for j in cuts]
    for i in range(0, len(row), 6):
        print("  " + "  ".join(row[i:i + 6]))
    if a.no_cues:
        return
    # ---- word landings
    words = [(l["id"], i, wd[0], wd[1], wd[3], wd[4]) for l in an.get("lyrics", []) for i, wd in enumerate(l["words"])]
    inside = []
    for lid, i, text, sung, cue, how in words:
        k = ceil(cue * fps - 0.5 - 1e-9)
        if f0 + 1 <= k <= f0 + n - 2:
            inside.append((lid, i, text, sung, cue, how, k))
    if not inside:
        print("no sung words cued inside this file")
        return
    # light that arrives, in linear light (as the engine averages sub-frames), above the grain
    lin = (g.astype(np.float32) / 255) ** 2.2
    rise = np.clip(lin[1:] - lin[:-1] - 0.004, 0, None)
    new = np.zeros(n)
    new[1:] = rise.reshape(n - 1, -1).sum(1)
    ks = [x[-1] for x in inside]
    print(f"\nwords cued in this file: {len(inside)} (cue frame = first frame whose centre is at or after the cue)")
    print(f"{'line':>6} {'#':>2}  {'word':<16} {'sung':>9} {'cue':>9} {'how':>6} {'cue fr':>7} {'landed':>7} {'off':>4}")
    offs = []
    for m, (lid, i, text, sung, cue, how, k) in enumerate(inside):
        lo = max(f0 + 1, k - 4, (ks[m - 1] + k) // 2 + 1 if m > 0 and ks[m - 1] < k else f0 + 1)
        hi = min(n + f0 - 1, k + 4, (k + ks[m + 1]) // 2 if m + 1 < len(ks) and ks[m + 1] > k else k + 4)
        seg = new[lo - f0:hi - f0 + 1]
        tot = seg.sum()
        if tot < 8:                         # about 10 fully lit pixels at 1/8 size: nothing arrived
            landed, off = None, None
        else:
            # more than half of it: a word cued right at a frame centre is half there one frame early (motion blur)
            j = int(np.argmax(np.cumsum(seg) > 0.55 * tot))
            landed = lo + j
            off = landed - k
            offs.append(off)
        shown = text if len(text) <= 16 else text[:15] + "…"
        print(f"{lid:>6} {i:>2}  {shown:<16} {sung:9.3f} {cue:9.3f} {how:>6} {k:>7} {landed if landed is not None else '—':>7} "
              f"{'' if off is None else f'{off:+d}':>4}")
    ok = sum(1 for o in offs if abs(o) <= a.tol)
    exact = sum(1 for o in offs if o == 0)
    print(f"landed on the cue frame: {exact}/{len(inside)}; within ±{a.tol}: {ok}/{len(inside)}; no landing seen: {len(inside) - len(offs)}")


if __name__ == "__main__":
    main()
