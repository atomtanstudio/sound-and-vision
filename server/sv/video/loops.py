"""Making a clip loop without a seam, and measuring how much it moves. Ported from the old app's loop worker
(soundandvision.old/server/workers/loop_worker.py), where these numbers were measured; runs in the app (numpy, with
ffmpeg reading and writing the pictures), from a thread.

- close: a clip that only moves forward (H3 from the still, its end left free), made a little longer than the loop:
  the extra frames are blended into its first ones, so its last frame flows into its first. Nothing plays backwards.
  (Pinning the still at both ends, as before 2026-10-09, made every motion slow to a stop at the cover and start off
  again, and the scene undo itself on the way back: the user saw it as playing forward, then in reverse.)
- join: pieces played one after another, each starting a little before the end of the one before, the shared moment
  blended (frame_at gives the next piece its first frame).
- hold: the people in the picture held exactly as painted (a mask from SAM3), so only the world around them moves,
  the way a cinemagraph does it. A video model can't keep a figure caught mid-step from moving, and a loop has to come
  back to the cover, so a figure that moves at all ends up dancing backwards.
- report: how far the clip strays from the still, how much of the picture changes, whether it cuts, and a verdict.
"""

from __future__ import annotations

import json
import subprocess

import numpy as np
from PIL import Image, ImageFilter

# How much a loop moves, from the frame that strays furthest from the still: the share of the picture changed there
# (by more than 24 gray levels of 255). Measured 2026-10-04: quiet H3 loops 0.05-0.15, lively ones 0.2-0.26, a woman
# who walked backwards out of the cover 0.72.
CHANGED = 24
LIVELY, TOO_MUCH = 0.18, 0.35
# A cut (the model editing the clip like a scene): one frame-to-frame step of more than 15 gray levels and ten
# ordinary steps. The biggest natural step seen (a lamp flickering) was 10; cuts were 31-35.
CUT, CUT_RATIO = 15.0, 10.0


def probe(path: str, ffmpeg: str = "ffmpeg") -> dict:
    ffprobe = ffmpeg.replace("ffmpeg", "ffprobe") if ffmpeg.endswith("ffmpeg") else "ffprobe"
    out = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                          "stream=width,height,r_frame_rate,nb_read_frames", "-of", "json", path],
                         capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    n, d = s["r_frame_rate"].split("/")
    return {"w": int(s["width"]), "h": int(s["height"]), "fps": float(n) / float(d), "frames": int(s["nb_read_frames"])}


def read_frames(path: str, ffmpeg: str = "ffmpeg", size: tuple[int, int] | None = None, gray: bool = False) -> np.ndarray:
    info = probe(path, ffmpeg)
    w, h = size or (info["w"], info["h"])
    vf = ([f"scale={w}:{h}:flags=lanczos"] if size else []) + (["format=gray"] if gray else ["format=rgb24"])
    raw = subprocess.run([ffmpeg, "-v", "error", "-i", path, "-map", "0:v:0", "-vf", ",".join(vf), "-f", "rawvideo", "-"],
                         capture_output=True, check=True).stdout
    arr = np.frombuffer(raw, dtype=np.uint8)
    return arr.reshape(-1, h, w) if gray else arr.reshape(-1, h, w, 3)


def write_frames(frames, dest: str, fps: float, w: int, h: int, ffmpeg: str = "ffmpeg", crf: int = 12) -> None:
    """Near-lossless h264: the loop is an intermediate the finished video reads."""
    p = subprocess.Popen([ffmpeg, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", f"{fps:g}",
                          "-i", "-", "-an", "-c:v", "libx264", "-preset", "slow", "-crf", str(crf), "-pix_fmt", "yuv420p",
                          "-movflags", "+faststart", dest], stdin=subprocess.PIPE)
    assert p.stdin
    for f in frames:
        p.stdin.write(np.ascontiguousarray(f, dtype=np.uint8).tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError("ffmpeg couldn't write the loop")


def report(path: str, ffmpeg: str = "ffmpeg") -> dict:
    """The seam (mean gray difference between the last frame and the first), an ordinary frame step, how far the clip
    travels and how much of it comes back, the share of the picture changed at its furthest, the number of cuts, and
    the verdict: calm, lively, too much, or cuts."""
    f = read_frames(path, ffmpeg, size=(128, 128), gray=True).astype(np.float32)
    steps = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))
    d = np.abs(f - f[0])
    dist = d.mean(axis=(1, 2))
    travel = float(dist.max())
    changed = float((d[int(dist.argmax())] > CHANGED).mean())
    step = float(np.median(steps))
    cuts = int((steps > max(CUT, CUT_RATIO * step)).sum())
    return {"seam": round(float(np.abs(f[-1] - f[0]).mean()), 2), "step": round(step, 2), "travel": round(travel, 1),
            "returns": round(1 - float(dist[-1]) / travel, 2) if travel > 0 else 1.0, "changed": round(changed, 3),
            "cuts": cuts, "motion": "cuts" if cuts else "too much" if changed > TOO_MUCH else "lively" if changed > LIVELY else "calm"}


def close(src: str, dest: str, overlap: int, ffmpeg: str = "ffmpeg") -> int:
    """The loop: all but the last `overlap` frames, with those last frames (the clip carrying on) blended into the
    first ones, so the end flows straight into the start and the motion never stops or turns back. Returns its length."""
    info = probe(src, ffmpeg)
    f = read_frames(src, ffmpeg)
    overlap = max(2, min(overlap, len(f) // 3))
    n = len(f) - overlap
    out = f[:n].copy()
    for i in range(overlap):
        t = (i + 0.5) / overlap
        w = t * t * (3 - 2 * t)  # 0: the clip carrying on from its last frame; 1: its own beginning
        out[i] = np.clip(f[n + i].astype(np.float32) * (1 - w) + f[i].astype(np.float32) * w, 0, 255).astype(np.uint8)
    write_frames(out, dest, info["fps"], info["w"], info["h"], ffmpeg)
    return n


def frame_at(src: str, dest: str, back: int, ffmpeg: str = "ffmpeg") -> None:
    """The frame `back` frames before the clip's end, as a picture: the next piece starts there (see join)."""
    f = read_frames(src, ffmpeg)
    Image.fromarray(f[max(0, len(f) - 1 - back)]).save(dest)


def join(dest: str, pieces: list[str], blend: int, ffmpeg: str = "ffmpeg") -> int:
    """Pieces one after another. Each after the first starts on the frame `blend` frames before its predecessor's end
    (frame_at), so those last frames and its first ones are the same moment made twice: they're blended, because a video
    model's first frames never quite match the picture it started from (a 12 s loop showed a jump of 7 ordinary steps
    at a plain join, 2026-10-09)."""
    info = probe(pieces[0], ffmpeg)
    count = 0

    def frames():
        nonlocal count
        tail = None
        for k, piece in enumerate(pieces):
            f = read_frames(piece, ffmpeg, size=(info["w"], info["h"]))
            begin = 0
            if tail is not None:
                b = min(len(tail), len(f))
                for i in range(b):
                    t = (i + 0.5) / b
                    w = t * t * (3 - 2 * t)
                    count += 1
                    yield np.clip(tail[i].astype(np.float32) * (1 - w) + f[i].astype(np.float32) * w, 0, 255).astype(np.uint8)
                begin = b
            end = len(f) - 1 - blend if k < len(pieces) - 1 else len(f)  # frame_at's frame starts the tail
            for fr in f[begin:end]:
                count += 1
                yield fr
            tail = f[end:] if k < len(pieces) - 1 else None
    write_frames(frames(), dest, info["fps"], info["w"], info["h"], ffmpeg)
    return count


def hold(src: str, dest: str, still: str, mask_png: str, ffmpeg: str = "ffmpeg") -> float:
    """The people held as painted. Holding only their outline isn't enough: the model moves a figure caught mid-step
    and its moved limbs show beside the held ones. So everything near them that the clip moved (within their box, made
    larger) is held too, and the rest of the picture keeps its motion. Measured on a dancer caught mid-spin
    (2026-10-09): 19% of the picture changed before, 8% after, and no ghosting. Returns the share of the picture held."""
    info = probe(src, ffmpeg)
    f = read_frames(src, ffmpeg)
    w, h = info["w"], info["h"]
    base = np.asarray(Image.open(still).convert("RGB").resize((w, h), Image.Resampling.LANCZOS), dtype=np.float32)
    person = np.asarray(Image.open(mask_png).convert("L").resize((w, h), Image.Resampling.BILINEAR)) > 127
    held = person.copy()
    if person.any():
        ys, xs = np.nonzero(person)
        pw, ph = xs.max() - xs.min(), ys.max() - ys.min()
        # around the figure, and further below and beside it, where its shadow falls (a held figure whose shadow
        # moves gives it away: seen 2026-10-09)
        box = np.zeros_like(person)
        box[max(0, ys.min() - int(ph * 0.15)):ys.max() + int(ph * 0.6),
            max(0, xs.min() - int(pw * 1.2)):xs.max() + int(pw * 1.2)] = True
        moved = np.zeros((h, w), dtype=np.float32)
        for fr in f:
            # a shadow shifting on a dark floor is a small change (12 levels), so near a figure that counts as moved
            moved += np.abs(fr.astype(np.float32) - base).mean(axis=2) > 12
        held |= box & (moved / len(f) > 0.05)
    m = Image.fromarray((held * 255).astype(np.uint8))
    m = m.filter(ImageFilter.MaxFilter(15)).filter(ImageFilter.GaussianBlur(max(2.0, 0.01 * w)))
    m = (np.asarray(m, dtype=np.float32) / 255.0)[..., None]
    keep = base * m
    write_frames((np.clip(fr.astype(np.float32) * (1 - m) + keep, 0, 255).astype(np.uint8) for fr in f),
                 dest, info["fps"], w, h, ffmpeg)
    return round(float(m.mean()), 3)
