"""The Library: everything made, songs and the videos made from them, in folders the person makes.

An item is a song ("s:<pid>") or one video ("v:<pid>:<kind>:<id>": a living cover's render, a Motion Graphics film or a
music video). Folders and which item is in which live in the "library" setting: {"folders": [{id, name}], "placed":
{item key: folder id}}; an item is in one folder or none.

Every video gets a thumbnail: the poster Claude chose when there is one, otherwise the best-looking of a few frames
(lit, sharp, colourful; a fade from black never wins). The person can make their own, for YouTube and the like: a
frame they pick, with the title, the artist and their logos laid over it in their look (look.py), at the size the
platforms want.
"""

from __future__ import annotations

import io
import subprocess
import time
import uuid
from pathlib import Path

import numpy as np
from PIL import Image

from . import covers as covers_mod, look as look_mod
from .jobs import JobError
from .paths import under

KINDS = {"living": "Living Album Cover", "motion": "Motion Graphics", "music": "Music Video", "clip": "Clip"}
ASPECT = {"square": 1.0, "wide": 16 / 9, "story": 9 / 16, "portrait": 4 / 5}
THUMB_SIZE = {"wide": (1280, 720), "story": (1080, 1920), "square": (1080, 1080), "portrait": (1080, 1350)}  # YouTube's, a phone's
SAMPLES = (0.04, 0.1, 0.18, 0.27, 0.36, 0.45, 0.55, 0.66, 0.78)


class Library:
    def __init__(self, app):
        self.app = app
        self.cfg = app.cfg

    # ---- what's in it -----------------------------------------------------------------------------------------------
    def _saved(self) -> dict:
        s = self.app.store.setting("library")
        return s if isinstance(s, dict) else {"folders": [], "placed": {}}

    def get(self) -> dict:
        s = self._saved()
        return {"folders": s.get("folders") or [], "placed": s.get("placed") or {}, "items": self.items(),
                "trash": len(self.trashed())}

    def items(self) -> list[dict]:
        out: list[dict] = []
        for p in self.app.store.projects():
            out.append(self._song_item(p))
            out += [self._video_item(p, kind, vid, rec) for kind, vid, rec in self._videos(p)]
        return out

    def _song_item(self, p: dict) -> dict:
        pid = p["id"]
        takes = self.app.store.takes(pid)
        master = next((t for t in takes if t["id"] == p.get("masterTake")), None)
        cover = p.get("cover") or {}
        return {"key": f"s:{pid}", "type": "song", "pid": pid, "title": p.get("title") or "Untitled song",
                "artist": self._artist(p), "art": cover.get("small") or None, "aspect": 1.0,
                "seconds": (master or {}).get("duration"), "takes": len(takes), "ready": bool(master),
                "genres": p.get("genres") or [], "at": p.get("updatedAt") or 0, "created": p.get("createdAt") or 0}

    def _video_item(self, p: dict, kind: str, vid: str, rec: dict) -> dict:
        pid = p["id"]
        thumb = (p.get("thumbs") or {}).get(f"{kind}:{vid}") or {}
        return {"key": f"v:{pid}:{kind}:{vid}", "type": "video", "kind": kind,
                "kindName": f"Clip · {rec.get('presetName')}" if kind == "clip" else KINDS[kind],
                "pid": pid, "vid": vid, "title": p.get("title") or "Untitled song", "artist": self._artist(p),
                "file": rec["file"], "shape": rec.get("shape") or "square",
                "aspect": ASPECT.get(rec.get("shape") or "square", 1.0), "seconds": rec.get("seconds"),
                "version": rec.get("version"), "opening": bool(rec.get("opening")), "finish": bool(rec.get("finish")),
                "part": rec.get("part"),
                "thumb": f"/api/library/thumb/{pid}/{kind}/{vid}?v={int(thumb.get('at') or 0)}",
                "custom": bool(thumb), "at": rec.get("at") or p.get("updatedAt") or 0, "created": rec.get("at") or 0}

    def _artist(self, p: dict) -> str:
        return covers_mod.artist_of(p, self.app.covers.house_artist())

    # ---- the trash: nothing is erased; songs and videos go out of sight until they're restored -------------------
    @staticmethod
    def _shelf(p: dict, kind: str) -> tuple[str | None, str, str]:
        """Where a kind of video is kept in its song: (section, its list, the trash beside it)."""
        return {"living": ("living", "renders", "trash"), "motion": ("kinetic", "videos", "trash"),
                "music": ("music", "videos", "trash"), "clip": (None, "clips", "clipsTrash")}[kind]

    def _shift(self, pid: str, kind: str, vid: str, to_trash: bool) -> bool:
        p = self.app.store.project(pid)
        if not p or kind not in KINDS:
            return False
        section, live, gone = self._shelf(p, kind)
        box = dict(p.get(section) or {}) if section else p
        src, dst = (live, gone) if to_trash else (gone, live)
        have = list(box.get(src) or [])
        rec = next((r for r in have if r.get("id") == vid), None)
        if rec is None:
            return False
        moved = {**rec, "trashedAt": time.time()} if to_trash else {k: v for k, v in rec.items() if k != "trashedAt"}
        rest = [r for r in have if r.get("id") != vid]
        into = sorted([moved, *(box.get(dst) or [])], key=lambda r: -(r.get("trashedAt") if to_trash else r.get("at") or 0))
        if section:
            self.app.store.patch_project(pid, **{section: {**box, src: rest, dst: into}})
        else:
            self.app.store.patch_project(pid, **{src: rest, dst: into})
        return True

    def trash(self, keys: list[str]) -> dict:
        """Songs and videos out of the library and their pages, kept on disk with everything they had."""
        done, kept = 0, []
        for key in keys[:500]:
            part = str(key).split(":")
            if part[0] == "s" and len(part) == 2 and self.app.store.project(part[1]):
                if self.app.store.jobs(("queued", "running"), part[1]):
                    kept.append(key)  # something is being made for it right now
                    continue
                self.app.store.trash_project(part[1])
                done += 1
            elif part[0] == "v" and len(part) == 4:
                done += self._shift(part[1], part[2], part[3], True)
        return {"trashed": done, "busy": kept}

    def restore(self, keys: list[str]) -> dict:
        done = 0
        for key in keys[:500]:
            part = str(key).split(":")
            if part[0] == "s" and len(part) == 2:
                done += self.app.store.restore_project(part[1])
            elif part[0] == "v" and len(part) == 4:
                done += self._shift(part[1], part[2], part[3], False)
        return {"restored": done}

    def trashed(self) -> list[dict]:
        """What's in the trash: whole songs (with their videos), and single videos of songs still here."""
        out = [{**self._song_item(p), "trashedAt": p["trashedAt"]} for p in self.app.store.trashed_projects()]
        for p in self.app.store.projects():
            for kind in KINDS:
                section, _, gone = self._shelf(p, kind)
                for rec in ((p.get(section) or {}) if section else p).get(gone) or []:
                    if rec.get("file"):
                        out.append({**self._video_item(p, kind, rec["id"], rec), "trashedAt": rec.get("trashedAt") or 0})
        return sorted(out, key=lambda i: -i["trashedAt"])

    @staticmethod
    def _videos(p: dict):
        for r in (p.get("living") or {}).get("renders") or []:
            if r.get("file"):
                yield "living", r["id"], r
        for kind, key in (("motion", "kinetic"), ("music", "music")):
            for v in (p.get(key) or {}).get("videos") or []:
                if v.get("file"):
                    yield kind, v["id"], v
        for c in p.get("clips") or []:  # clips made in Share
            if c.get("file"):
                yield "clip", c["id"], c

    def video(self, pid: str, kind: str, vid: str) -> tuple[dict, dict, Path, Path | None]:
        p = self.app.store.project(pid)
        rec = next((r for k, i, r in self._videos(p or {}) if k == kind and i == vid), None) if p else None
        if not p or not rec:
            raise JobError("That video isn't here any more.")
        root = self.cfg.projects / pid
        file = root / rec["file"]
        if not file.exists():
            raise JobError("That video's file isn't here any more.")
        poster = root / rec["poster"] if rec.get("poster") and (root / rec["poster"]).exists() else None
        return p, rec, file, poster

    # ---- thumbnails ---------------------------------------------------------------------------------------------
    def _thumbs(self, pid: str) -> Path:
        d = self.cfg.projects / pid / "thumbs"
        d.mkdir(exist_ok=True)
        return d

    def thumb(self, pid: str, kind: str, vid: str) -> Path:
        """The video's thumbnail: the person's own, else the poster, else the best of a few frames (made once)."""
        p = self.app.store.project(pid) or {}
        own = (p.get("thumbs") or {}).get(f"{kind}:{vid}")
        mine = under(self.cfg.projects / pid, own.get("file")) if own else None
        if mine and mine.exists():
            return mine
        out = self.cfg.projects / pid / "thumbs" / f"{kind}-{vid}.jpg"
        if out.exists():
            return out
        p, rec, file, poster = self.video(pid, kind, vid)
        self._thumbs(pid)
        if poster:
            with Image.open(poster) as im:
                pic = im.convert("RGB")
        else:
            at = self.best_moment(file, float(rec.get("seconds") or self.duration(file)))
            pic = Image.open(io.BytesIO(self.frame_bytes(file, at, 960)))
        pic.thumbnail((960, 960), Image.Resampling.LANCZOS)
        pic.save(out, "JPEG", quality=86)
        return out

    def duration(self, file: Path) -> float:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(file)],
                           capture_output=True, text=True, timeout=30)
        try:
            return float(r.stdout.strip())
        except ValueError:
            return 0.0

    def frame_bytes(self, file: Path, at: float, width: int = 1280) -> bytes:
        r = subprocess.run([self.cfg.ffmpeg, "-v", "error", "-ss", f"{max(0.0, at):.3f}", "-i", str(file), "-frames:v", "1",
                            "-vf", f"scale={width}:-2", "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "3", "pipe:1"],
                           capture_output=True, timeout=60)
        if r.returncode != 0 or not r.stdout:
            raise JobError("A frame couldn't be read from that video.")
        return r.stdout

    def best_moment(self, file: Path, seconds: float) -> float:
        """The best-looking of a few moments: lit, sharp and colourful (a fade from black or a white flash never wins)."""
        best, at_best = -1e9, max(0.0, seconds * 0.1)
        for f in SAMPLES:
            at = seconds * f
            try:
                im = Image.open(io.BytesIO(self.frame_bytes(file, at, 320))).convert("RGB")
            except (JobError, OSError, subprocess.TimeoutExpired):
                continue
            score = frame_score(np.asarray(im, np.float32) / 255)
            if score > best:
                best, at_best = score, at
        return at_best

    def frame(self, pid: str, kind: str, vid: str, at: float, width: int = 1280) -> bytes:
        _, _, file, _ = self.video(pid, kind, vid)
        return self.frame_bytes(file, at, max(160, min(1920, width)))

    def thumb_picture(self, pid: str, kind: str, vid: str, at: float) -> tuple[dict, Image.Image]:
        """The frame at `at`, at the platform size for the video's shape (what a thumbnail is set on)."""
        p, rec, file, _ = self.video(pid, kind, vid)
        W, H = THUMB_SIZE.get(rec.get("shape") or "square", (1080, 1080))
        pic = Image.open(io.BytesIO(self.frame_bytes(file, at, 1920))).convert("RGB")
        scale = max(W / pic.width, H / pic.height)
        pic = pic.resize((max(W, round(pic.width * scale)), max(H, round(pic.height * scale))), Image.Resampling.LANCZOS)
        return p, pic.crop(((pic.width - W) // 2, (pic.height - H) // 2, (pic.width - W) // 2 + W, (pic.height - H) // 2 + H))

    def make_thumb(self, pid: str, kind: str, vid: str, at: float, layout: dict | None, show: dict | None = None) -> dict:
        """The person's own thumbnail: the frame at `at`, at the platform size for the video's shape, with the title,
        the artist and the logos laid over it in `layout` (over the brand's look). Returns the project."""
        p, pic = self.thumb_picture(pid, kind, vid, at)
        W, H = pic.size
        look = look_mod.normalize(self.app.brand.house(), layout)
        cover = p.get("cover") or {}
        title = (show or {}).get("title", p.get("title") or "")
        artist = (show or {}).get("artist", self._artist(p))
        layer, _ = look_mod.render(pic, str(title)[:120], str(artist)[:80], self.app.brand.logos(), look, self.app.brand.fonts)
        out = self._thumbs(pid) / f"{kind}-{vid}-own-{uuid.uuid4().hex[:6]}.jpg"
        Image.alpha_composite(pic.convert("RGBA"), layer).convert("RGB").save(out, "JPEG", quality=92)
        thumbs = dict(p.get("thumbs") or {})
        old = thumbs.get(f"{kind}:{vid}")
        if old:
            (self.cfg.projects / pid / old["file"]).unlink(missing_ok=True)
        thumbs[f"{kind}:{vid}"] = {"file": str(out.relative_to(self.cfg.projects / pid)), "frame": round(at, 3),
                                   "layout": layout or {}, "show": show or {}, "size": [W, H], "at": time.time()}
        return self.app.store.patch_project(pid, thumbs=thumbs)

    def forget_thumb(self, pid: str, kind: str, vid: str) -> dict:
        p, _, _, _ = self.video(pid, kind, vid)
        thumbs = dict(p.get("thumbs") or {})
        old = thumbs.pop(f"{kind}:{vid}", None)
        if old:
            (self.cfg.projects / pid / old["file"]).unlink(missing_ok=True)
        return self.app.store.patch_project(pid, thumbs=thumbs)

    # ---- folders ------------------------------------------------------------------------------------------------
    def _save(self, s: dict) -> dict:
        self.app.store.set_setting("library", s)
        return {"folders": s.get("folders") or [], "placed": s.get("placed") or {}}

    def add_folder(self, name: str) -> dict:
        name = " ".join(name.split())[:60]
        if not name:
            raise JobError("Give the folder a name.")
        s = self._saved()
        s.setdefault("folders", []).append({"id": uuid.uuid4().hex[:8], "name": name, "at": time.time()})
        return self._save(s)

    def rename_folder(self, fid: str, name: str) -> dict:
        s = self._saved()
        f = next((f for f in s.get("folders") or [] if f["id"] == fid), None)
        if not f:
            raise JobError("That folder isn't here any more.")
        f["name"] = " ".join(name.split())[:60] or f["name"]
        return self._save(s)

    def remove_folder(self, fid: str) -> dict:
        """The folder goes; what was in it stays in the Library, in no folder."""
        s = self._saved()
        s["folders"] = [f for f in s.get("folders") or [] if f["id"] != fid]
        s["placed"] = {k: v for k, v in (s.get("placed") or {}).items() if v != fid}
        return self._save(s)

    def order_folders(self, ids: list[str]) -> dict:
        s = self._saved()
        by = {f["id"]: f for f in s.get("folders") or []}
        s["folders"] = [by[i] for i in ids if i in by] + [f for i, f in by.items() if i not in ids]
        return self._save(s)

    def move(self, keys: list[str], folder: str | None) -> dict:
        s = self._saved()
        if folder and not any(f["id"] == folder for f in s.get("folders") or []):
            raise JobError("That folder isn't here any more.")
        placed = dict(s.get("placed") or {})
        for k in keys[:500]:
            if folder:
                placed[str(k)[:200]] = folder
            else:
                placed.pop(str(k), None)
        s["placed"] = placed
        return self._save(s)


def frame_score(x: np.ndarray) -> float:
    """How good a frame looks as a thumbnail: lit (not black, not blown out), sharp, colourful, with some contrast."""
    lum = x @ np.array([0.299, 0.587, 0.114], np.float32)
    mean = float(lum.mean())
    sharp = float(np.abs(np.diff(lum, axis=0)).mean() + np.abs(np.diff(lum, axis=1)).mean())
    rg, yb = x[..., 0] - x[..., 1], 0.5 * (x[..., 0] + x[..., 1]) - x[..., 2]
    colour = float(np.sqrt(rg.std() ** 2 + yb.std() ** 2) + 0.3 * np.sqrt(rg.mean() ** 2 + yb.mean() ** 2))
    dark = max(0.0, 0.14 - mean) * 12 + max(0.0, mean - 0.88) * 12
    return sharp * 6 + colour * 2 + float(lum.std()) * 2 - dark

