#!/usr/bin/env python3
"""Seamless joins between clips that continue one another (copied into a music video's folder as tools/joins.py).

H3 starts every clip from its first picture at rest and sets off its own way, so where one clip carries on from
another the motion changes at the join: the camera stops and lurches, or turns, and a cut that trims a clip can skip
frames or show one twice. This finds those places and smooths the ones that can be smoothed.

  python3 tools/joins.py check out/final.mp4 --joins out/joins.json [--json]
      Measures each join listed in out/joins.json (the seconds in the video where one clip carries on from another)
      and says whether it passes: not a cut, no frame shown twice, no frames skipped, and the camera's motion going
      on as it was. Exits 1 if any fails. This is the check the app runs on what you hand back.

  python3 tools/joins.py check out/final.mp4 [--from SECONDS] [--to SECONDS] [--json]
      Without --joins: scans the whole video for any place the picture carries on but the motion doesn't (a frame
      shown twice, frames skipped, the camera lurching, stopping or turning), cuts to a new picture left alone. It
      also lists H3's own changes of motion inside a clip, so read it as a list of places to look at.

  python3 tools/joins.py smooth --out clips/smooth CLIP:FIRST:COUNT[:rev] CLIP:FIRST:COUNT[:rev] ...
      Makes a chain of clips that continue one another play as one move. Each argument is what the video shows of a
      clip, in order: the file, the first frame shown and how many (add ":rev" when it plays backwards; FIRST then
      counts in the backwards order). Each clip after the first must begin on the picture the one before ends on.
      Around each join the frames are re-timed so the camera's speed flows on (frames that would be skipped are played
      through, a frame shown twice is shown once), and the camera's path is smoothed; only the clips' own frames are
      used (in-between frames come from optical flow), with one slight steady reframe across the chain to hide the
      edges. Writes <clip>-smooth.mp4 into --out for each, exactly COUNT frames: play each from its first frame where
      that clip's part of the video was. A join where the camera turns can't be hidden this way: it says so (exit 3),
      and that move belongs in one clip.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

try:
    import cv2
    import numpy as np
except ImportError:  # the folder's own Python packages (pip is set up in .local/): install what's missing once
    subprocess.run([sys.executable, "-m", "pip", "install", "--user", "-q", "--disable-pip-version-check",
                    "opencv-python-headless", "numpy"], check=True)
    import site, importlib
    importlib.reload(site)
    import cv2
    import numpy as np

SW, SH = 384, 216          # analysis size
FPS = 24
DIP_FAIL = 0.65           # a join fails the check when the camera slows below 65% of its speed either side
DIP = 0.12                 # how much slower than either side the camera may get through a join (12%)
LIMIT = 0.05               # the largest reframe a join may need (5%) before it counts as a turn (the window join, approved, needed 3.3%)


# ---- the camera between two frames ---------------------------------------------------------------------------

_yy, _xx = np.mgrid[0:SH, 0:SW].astype(np.float32)
_cx, _cy = _xx - SW / 2, _yy - SH / 2
_G = np.vstack([np.array([np.ones_like(_cx).ravel(), np.zeros_like(_cx).ravel(), _cx.ravel(), -_cy.ravel()]).T,
                np.array([np.zeros_like(_cx).ravel(), np.ones_like(_cx).ravel(), _cy.ravel(), _cx.ravel()]).T])[::7]
_dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)


def camera(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, int]:
    """(pan x, pan y, zoom, roll) from a to b, at the analysis size (pixels, fraction, radians), and how many tracked
    points agreed. Points are tracked and fitted with RANSAC, so things moving on their own (birds, rain, bubbles)
    don't count as the camera; with too few points, a fit to the whole frame's flow."""
    p0 = cv2.goodFeaturesToTrack(a, 900, 0.005, 5)
    if p0 is not None and len(p0) >= 40:
        p1, st, _ = cv2.calcOpticalFlowPyrLK(a, b, p0, None, winSize=(21, 21), maxLevel=3)
        good = st.ravel() == 1
        # lettering held still over a moving picture (a title) isn't the camera: where some points hold dead still
        # and most of the rest move, leave the still ones out (a still camera has nearly every point still)
        step = np.linalg.norm((p1 - p0).reshape(-1, 2), axis=1)
        still, moving = good & (step < 0.08), good & (step > 0.15)
        if still.sum() >= 0.1 * good.sum() and moving.sum() >= 0.4 * good.sum() and moving.sum() >= 30:
            good = good & ~still
        if good.sum() >= 30:
            c = np.array([SW / 2, SH / 2], np.float32)
            M, inl = cv2.estimateAffinePartial2D(p0[good].reshape(-1, 2) - c, p1[good].reshape(-1, 2) - c,
                                                 method=cv2.RANSAC, ransacReprojThreshold=0.6, maxIters=3000,
                                                 confidence=0.995)
            if M is not None and inl is not None and inl.sum() >= 25:
                return np.array([M[0, 2], M[1, 2], math.hypot(M[0, 0], M[1, 0]) - 1, math.atan2(M[1, 0], M[0, 0])]), int(inl.sum())
    fl = _dis.calc(a, b, None)
    sol = np.linalg.lstsq(_G, np.concatenate([fl[..., 0].ravel(), fl[..., 1].ravel()])[::7], rcond=None)[0]
    return np.array(sol, dtype=np.float64), 0


def amount(v: np.ndarray) -> float:
    """How far the picture moves on average for a camera move (pixels at the analysis size)."""
    tx, ty, s, w = v
    return float(np.sqrt((tx + s * _cx - w * _cy) ** 2 + (ty + s * _cy + w * _cx) ** 2).mean())


def as_vector(v: np.ndarray) -> np.ndarray:
    """A camera move as one vector: pan in pixels, zoom and roll as the pixels they move at a third of the width."""
    r = SW / 2
    return np.array([v[0], v[1], v[2] * r, v[3] * r])


def small(f: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(cv2.resize(f, (SW, SH), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)


def read(path: str) -> list[np.ndarray]:
    cap = cv2.VideoCapture(path)
    out = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        out.append(f)
    if not out:
        raise SystemExit(f"Couldn't read {path}.")
    return out


# ---- check ----------------------------------------------------------------------------------------------------

def slowing(moves: list, k: int, fps: float) -> float | None:
    """A dip at the join: the camera slows down and then speeds up again. Its slowest speed (how far the picture
    moves, zoom included) within about a second of pair k, as a share of the lower of its top speeds on either side
    (up to 3 s away); None when there's no dip worth feeling, or too little motion to tell."""
    sp = np.array([amount(v) for v in moves])
    sp = np.array([np.median(sp[max(0, i - 2):i + 3]) for i in range(len(sp))])  # one odd frame isn't a dip
    near, edge, far = int(round(1.2 * fps)), int(round(0.3 * fps)), int(round(3 * fps))
    before, after = sp[max(0, k - far):max(0, k - edge)], sp[k + edge:k + far]
    if len(before) < 6 or len(after) < 6:
        return None
    top = min(float(np.percentile(before, 90)), float(np.percentile(after, 90)))
    low = float(sp[max(0, k - near):k + near + 1].min())
    if top < 0.6:            # the camera barely moves on one side: nothing to dip from
        return None
    # only a camera going the same way on both sides dips: slowing where it changes direction is taking a corner
    # (a turn that's too sudden is the jump test's)
    V = np.array([as_vector(v) for v in moves])
    vb, va = V[max(0, k - far):max(0, k - edge)].mean(0), V[k + edge:k + far].mean(0)
    same_way = float(vb @ va) / max(float(np.linalg.norm(vb) * np.linalg.norm(va)), 1e-9)
    if same_way < 0.8:
        return None
    return low / top if low < DIP_FAIL * top else None


def check_joins(a) -> int:
    """Each listed join, measured: is it a cut, is a frame shown twice, are frames skipped, does the motion change."""
    try:
        listed = json.loads(Path(a.joins).read_text())
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Couldn't read {a.joins}: {exc}")
    times = [float(x["at"] if isinstance(x, dict) else x) for x in (listed.get("joins") if isinstance(listed, dict) else listed)]
    cap = cv2.VideoCapture(a.video)
    fps = cap.get(cv2.CAP_PROP_FPS) or FPS
    results = []
    wide = int(round(3 * fps))  # 3 s either side, for a slowing that's spread out (a dip), not only a jump
    for t in times:
        j = int(round(t * fps))
        first = max(0, j - wide)
        cap.set(cv2.CAP_PROP_POS_FRAMES, first)
        fr = []
        for _ in range(j + wide + 1 - first):
            ok, f = cap.read()
            if not ok:
                break
            fr.append(small(f))
        r = {"at": round(t, 3)}
        k = j - 1 - first                                      # the pair from the last frame before the join to the first after
        if k < 6 or len(fr) - 1 < k + 8:
            r.update(ok=False, why="too near the start or end of the video to measure")
            results.append(r); continue
        moves = [camera(fr[i], fr[i + 1])[0] for i in range(len(fr) - 1)]
        d = [float(np.abs(fr[i + 1].astype(np.float32) - fr[i].astype(np.float32)).mean()) for i in range(len(fr) - 1)]
        V = [as_vector(v) for v in moves]
        med = float(np.median(d[max(0, k - 13):k + 14]))
        around = d[k - 3:k] + d[k + 1:k + 4]
        sp = [float(np.linalg.norm(v)) for v in V]
        before, after = np.mean(V[k - 6:k], 0), np.mean(V[k + 1:k + 7], 0)
        speed = max(float(np.linalg.norm(before)), float(np.linalg.norm(after)), 0.25)
        jump = float(np.linalg.norm(after - before)) / speed
        r.update(jump=round(jump, 2), speed=[round(float(np.linalg.norm(before)), 2), round(float(np.linalg.norm(after)), 2)])
        if d[k] > max(18.0, 5 * med):
            r.update(ok=False, why="it's a cut to a new picture, not a join (leave it off the list, or join the clips)")
        elif d[k] < 0.3 * float(np.median(around)):
            r.update(ok=False, why="the same picture is shown twice")
        elif sp[k] > 2.5 * float(np.median(sp[k - 4:k] + sp[k + 1:k + 5])) and sp[k] > 1.0:
            r.update(ok=False, why="frames are skipped: the picture jumps")
        elif jump >= 0.6:
            r.update(ok=False, why=f"the camera's motion changes (by {jump:.2f} of its speed): it stops, lurches or turns")
        elif (dip := slowing(moves, k, fps)) is not None:
            r.update(ok=False, dip=round(dip, 2),
                     why=f"the camera slows to {round(100 * dip)}% of its speed around the join and picks up again")
        else:
            r.update(ok=True)
        results.append(r)
    bad = [r for r in results if not r["ok"]]
    if a.json:
        print(json.dumps({"joins": results, "failed": len(bad)}, indent=1))
    else:
        for r in results:
            m, s = divmod(r["at"], 60)
            print(f"{int(m)}:{s:05.2f}  " + ("passes" if r["ok"] else f"FAILS: {r['why']}"))
        print(f"{len(results) - len(bad)} of {len(results)} joins pass.")
    return 1 if bad else 0


def check(a) -> int:
    if a.joins:
        return check_joins(a)
    cap = cv2.VideoCapture(a.video)
    fps = cap.get(cv2.CAP_PROP_FPS) or FPS
    first = int(round(a.start * fps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, first)
    last = int(round(a.end * fps)) if a.end else None
    diffs, moves, points, light, prev, n = [], [], [], [], None, first
    while last is None or n < last:
        ok, f = cap.read()
        if not ok:
            break
        g = small(f)
        if prev is not None:
            diffs.append(float(np.abs(g.astype(np.float32) - prev.astype(np.float32)).mean()))
            light.append(float(g.mean()) - float(prev.mean()))
            v, k = camera(prev, g)
            moves.append(v); points.append(k)
        prev, n = g, n + 1
    if len(moves) < 20:
        raise SystemExit("Too short to check.")
    d, V, P = np.array(diffs), np.array([as_vector(v) for v in moves]), np.array(points)
    sp = np.linalg.norm(V, axis=1)
    med = np.median(d)
    cut = (d > max(18.0, 5 * med)) | ((P < 15) & (d > 3 * med))
    found = []

    def near_cut(i, r=7):  # wider than the 6 frames averaged either side, so a cut's own jump never lands in them
        return cut[max(0, i - r):i + r + 1].any()

    # fading in at the start or out at the end: the picture's light changes, not the camera
    near_end = np.zeros(len(V), bool); near_end[:int(2 * fps)] = first < 2 * fps; near_end[-int(2 * fps):] = a.end is None
    fade = (np.abs(np.array(light)) > 0.8) & near_end
    for i in range(6, len(V) - 6):
        if near_cut(i) or fade[max(0, i - 6):i + 7].any():
            continue
        around = np.r_[sp[i - 4:i], sp[i + 1:i + 5]]
        ad = np.r_[d[i - 3:i], d[i + 1:i + 4]]
        t = round((first + i + 1) / fps, 2)
        if d[i] < 0.3 * np.median(ad) and np.median(around) > 0.3:
            found.append({"at": t, "what": "a frame shown twice", "score": round(float(np.median(ad) / max(d[i], 0.05)), 1)})
            continue
        if sp[i] > 2.5 * np.median(around) and sp[i] > 1.0:
            found.append({"at": t, "what": "frames skipped (the picture jumps)", "score": round(float(sp[i] / max(np.median(around), 0.1)), 1)})
            continue
        before, after = V[i - 6:i].mean(0), V[i + 1:i + 7].mean(0)
        jump = float(np.linalg.norm(after - before))
        speed = max(float(np.linalg.norm(before)), float(np.linalg.norm(after)), 0.25)
        if jump > 0.2 and jump / speed > 0.6:
            b2, a2 = before[:2], after[:2]
            turn = None
            if np.linalg.norm(b2) > 0.3 and np.linalg.norm(a2) > 0.3:
                turn = math.degrees(math.acos(max(-1.0, min(1.0, float(b2 @ a2 / (np.linalg.norm(b2) * np.linalg.norm(a2)))))))
            what = ("the camera turns" if turn and turn > 45 else
                    "the camera lurches" if np.linalg.norm(after) > np.linalg.norm(before) else "the camera stops")
            found.append({"at": t, "what": what, "score": round(jump / speed, 2), **({"turn_deg": round(turn)} if turn else {})})
    keep = []
    for f in sorted(found, key=lambda x: -x["score"]):  # one per half second, the strongest
        if all(abs(f["at"] - k["at"]) > 0.5 for k in keep):
            keep.append(f)
    keep.sort(key=lambda x: x["at"])
    if a.json:
        print(json.dumps(keep, indent=1))
    else:
        if not keep:
            print("No seams found.")
        for f in keep:
            m, s = divmod(f["at"], 60)
            print(f"{int(m)}:{s:05.2f}  {f['what']}" + (f" ({f['turn_deg']}°)" if f.get("turn_deg") else ""))
        print(f"{len(keep)} place(s) where the motion breaks without a cut ({int(cut.sum())} cuts left alone).")
    return 1 if keep else 0


# ---- smooth ---------------------------------------------------------------------------------------------------

def smooth(a) -> int:
    segs = []
    for spec in a.segments:
        bits = spec.split(":")
        if len(bits) not in (3, 4) or (len(bits) == 4 and bits[3] != "rev"):
            raise SystemExit(f"{spec}: give CLIP:FIRST:COUNT, or CLIP:FIRST:COUNT:rev.")
        segs.append({"path": bits[0], "first": int(bits[1]), "count": int(bits[2]), "rev": len(bits) == 4})
    if len(segs) < 2:
        raise SystemExit("Give at least two clips that continue one another.")
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)

    # one source: every frame of the first clip as it plays, then each next clip from its second frame
    played = []
    for s in segs:
        fr = read(s["path"])
        played.append(fr[::-1] if s["rev"] else fr)
    src, start = [], []
    for k, fr in enumerate(played):
        if k == 0:
            start.append(0); src += fr
        else:
            gap = float(np.abs(small(src[-1]).astype(np.float32) - small(fr[0]).astype(np.float32)).mean())
            step = float(np.abs(small(fr[1]).astype(np.float32) - small(fr[0]).astype(np.float32)).mean())
            if gap > max(6.0, 1.5 * step):
                raise SystemExit(f"{segs[k]['path']} doesn't begin on the picture {segs[k - 1]['path']} ends on "
                                 f"(they differ by {gap:.1f}): that's a cut, not a join.")
            start.append(len(src) - 1); src += fr[1:]
        s = segs[k]
        if s["first"] < 0 or s["first"] + s["count"] > len(fr):
            raise SystemExit(f"{s['path']}: frames {s['first']}–{s['first'] + s['count'] - 1} aren't all in the clip ({len(fr)} frames).")
    H, W = src[0].shape[:2]
    lo = [small(f) for f in src]
    moves = [camera(lo[i], lo[i + 1])[0] for i in range(len(lo) - 1)]
    m = np.array([amount(v) for v in moves])
    k7 = np.exp(-0.5 * (np.arange(-3, 4) / 1.5) ** 2); k7 /= k7.sum()
    ms = np.maximum(np.convolve(np.pad(m, 3, mode="edge"), k7, "valid"), 0.02 * max(np.median(m), 1e-3))
    C = np.concatenate([[0.0], np.cumsum(ms)])
    P = np.zeros((len(src), 4))
    for i, (tx, ty, sz, w) in enumerate(moves):
        P[i + 1] = P[i] + [tx * W / SW, ty * H / SH, sz, w]

    offs = np.cumsum([0] + [s["count"] for s in segs])
    total = int(offs[-1])

    def tau0(n):
        k = int(np.searchsorted(offs, n, side="right") - 1)
        return start[k] + segs[k]["first"] + (n - offs[k])

    def speed_near(p, side):
        """The camera's usual speed just outside a window (the median of a dozen frames), not the slow part inside."""
        lo, hi = (max(0, p - 12), max(1, p)) if side < 0 else (min(len(ms) - 1, p), min(len(ms), p + 12))
        return float(np.median(ms[lo:max(hi, lo + 1)]))

    def path_at(t):
        return np.array([np.interp(t, np.arange(len(P)), P[:, c]) for c in range(4)])

    def plan(short: set):
        """The re-timing and the smoothed camera path for every join; joins in `short` keep the 3 s window."""
        tau = {n: float(tau0(n)) for n in range(total)}
        windows = []
        for k in range(1, len(segs)):
            j = int(offs[k])
            most_before = int(segs[k - 1]["count"] * (0.45 if k > 1 else 0.8))
            most_after = int(segs[k]["count"] * (0.45 if k < len(segs) - 1 else 0.8))
            before, after = min(30, most_before), min(42, most_after)
            while True:
                # H3 eases off at the end of a take and starts the next from rest, so the clips can hold less movement
                # around a join than the camera's speed either side: squeezed into 3 s that's a dip you feel. Widen
                # the re-timing until the shortfall is a slowing nobody notices (DIP), as far as the clips allow.
                n0, n1 = j - before, j + after
                p0, p1 = tau0(n0), tau0(n1)
                # a widened window takes the speed either side as it usually is (just outside, a dozen frames); the
                # short one, as it always has, at its edges
                v0, v1 = (ms[max(0, p0 - 1)], ms[min(len(ms) - 1, p1)]) if k in short else (speed_near(p0, -1), speed_near(p1, 1))
                D, need = n1 - n0, C[p1] - C[p0]
                dip = 1 - (need / D) / max((v0 + v1) / 2, 1e-6)
                if k in short or dip <= DIP or (before >= most_before and after >= most_after):
                    break
                before, after = min(most_before, before + 12), min(most_after, after + 24)
            u = (np.arange(D) + 0.5) / D
            b = 2 * (need / D - (v0 + v1) / 2)
            v = v0 + (v1 - v0) * (u * u * (3 - 2 * u)) + b * np.sin(np.pi * u) ** 2
            v = np.maximum(v, 0.05 * min(v0, v1) + 1e-6)
            v *= need / v.sum()
            target = C[p0] + np.concatenate([[0.0], np.cumsum(v)])
            for q, c in enumerate(target):
                tau[n0 + q] = float(np.interp(c, C, np.arange(len(C))))
            # the re-timing spreads over the whole window; the camera path is smoothed only right around the join,
            # where the motion changes (over a wide window the real path curves, and one smooth curve can't follow it)
            windows.append((k, n0, n1, j - min(30, before), j + min(42, after), round(100 * max(dip, 0.0), 1)))
        O = {n: path_at(tau[n]) for n in range(total)}
        delta, report = {}, []
        for k, n0, n1, s0, s1, dip in windows:
            e0, e1 = max(3, s0), min(total - 4, s1)
            d0 = (O[e0 + 3] - O[e0 - 3]) / 6 * (e1 - e0)
            d1 = (O[e1 + 3] - O[e1 - 3]) / 6 * (e1 - e0)
            worst = 0.0
            for n in range(e0, e1 + 1):
                x = (n - e0) / (e1 - e0)
                h = (2*x**3 - 3*x**2 + 1) * O[e0] + (x**3 - 2*x**2 + x) * d0 + (-2*x**3 + 3*x**2) * O[e1] + (x**3 - x**2) * d1
                delta[n] = h - O[n]
                dd = delta[n]
                worst = max(worst, max(abs(dd[0]) / W, abs(dd[1]) / H) * 2 + abs(dd[2]) + abs(dd[3]) * 0.6)
            report.append({"join": f"{Path(segs[k - 1]['path']).name} -> {Path(segs[k]['path']).name}",
                           "at_frame": int(offs[k]), "reframe_needed_pct": round(100 * worst, 2),
                           "smoothed_over_s": round((n1 - n0) / a.fps, 1), "slowing_left_pct": dip,
                           "ok": bool(worst <= a.limit), "k": k})
        return tau, delta, report

    # a wide re-timing keeps the camera's speed through a join; where the camera turns there, that would swing the
    # frame round the corner (too much reframe), so that join keeps the short one: slowing through a turn is natural
    short: set = set()
    while True:
        tau, delta, report = plan(short)
        widened_and_failing = {r["k"] for r in report if not r["ok"] and r["k"] not in short and r["smoothed_over_s"] > 3.0}
        if not widened_and_failing:
            break
        short |= widened_and_failing
    for r in report:
        r.pop("k")
    print(json.dumps(report, indent=1))
    turns = [r for r in report if not r["ok"]]
    if turns and not a.force:
        for r in turns:
            print(f"{r['join']}: the camera turns here (it would need a {r['reframe_needed_pct']}% reframe). Make that "
                  "move one clip instead, or pass --force.", file=sys.stderr)
        return 3
    margin = 1 + max([r["reframe_needed_pct"] / 100 for r in report] + [0.0]) + 0.004

    flows = {}
    grid = np.dstack(np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32)))

    def frame_at(t):
        i = int(math.floor(t)); x = t - i
        if x < 1e-3 or i + 1 >= len(src):
            return src[min(i, len(src) - 1)]
        if x > 1 - 1e-3:
            return src[i + 1]
        if i not in flows:
            g0, g1 = cv2.cvtColor(src[i], cv2.COLOR_BGR2GRAY), cv2.cvtColor(src[i + 1], cv2.COLOR_BGR2GRAY)
            flows[i] = (_dis_full.calc(g0, g1, None), _dis_full.calc(g1, g0, None))
        f01, f10 = flows[i]
        m0, m1 = grid - x * f01, grid - (1 - x) * f10
        w0 = cv2.remap(src[i], m0[..., 0], m0[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        w1 = cv2.remap(src[i + 1], m1[..., 0], m1[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        return cv2.addWeighted(w0, 1 - x, w1, x, 0)

    def reframe(f, n):
        d = delta.get(n, np.zeros(4))
        A2 = cv2.getRotationMatrix2D((W / 2, H / 2), -math.degrees(float(d[3])), float(math.exp(d[2]) * margin))
        A2[0, 2] += d[0]; A2[1, 2] += d[1]
        return cv2.warpAffine(f, A2, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)

    for k, s in enumerate(segs):
        dest = out / f"{Path(s['path']).stem}-smooth.mp4"
        enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                                "-r", str(a.fps), "-i", "-", "-c:v", "libx264", "-crf", "10", "-preset", "slow",
                                "-pix_fmt", "yuv420p", str(dest)], stdin=subprocess.PIPE)
        for n in range(int(offs[k]), int(offs[k + 1])):
            enc.stdin.write(np.ascontiguousarray(reframe(frame_at(tau[n]), n)).tobytes())
        enc.stdin.close(); enc.wait()
        print(f"wrote {dest} ({s['count']} frames)")
    print(f"one steady reframe across the chain: {100 * (margin - 1):.1f}% closer")
    return 0


_dis_full = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("\n\n", 2)[2])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check"); c.add_argument("video"); c.add_argument("--from", dest="start", type=float, default=0.0)
    c.add_argument("--to", dest="end", type=float, default=None); c.add_argument("--json", action="store_true")
    c.add_argument("--joins", help="out/joins.json: the seconds of every join in the video, to measure each one")
    s = sub.add_parser("smooth"); s.add_argument("segments", nargs="+"); s.add_argument("--out", required=True)
    s.add_argument("--fps", type=int, default=FPS); s.add_argument("--limit", type=float, default=LIMIT)
    s.add_argument("--force", action="store_true")
    a = ap.parse_args()
    return check(a) if a.cmd == "check" else smooth(a)


if __name__ == "__main__":
    sys.exit(main())
