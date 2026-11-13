"""Cast: the person's own characters, saved once and used in any lip-synced music video (a singer, a band, a figure
who comes back), so the same faces carry through a video and through a whole series. Each is a name, a few words
about them, who they are, and one to four pictures, kept in data/cast/<id>/ (the first is the main one).

When a video uses a cast (members from here, or the cast of an earlier video), place() copies their pictures into the
video's characters/ folder as its references and returns "Your cast" for the director's notes: it uses them as they
are instead of inventing performers.

A picture of a real person needs their say-so, so a character can't be saved without the person confirming who it is:
an invented character, themselves, or someone who agreed to appear in AI-made videos. A cast reused from an earlier
video keeps what that video was told.
"""

from __future__ import annotations

import io
import json
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from PIL import Image

from .jobs import JobError

WHO = {"invented": "an invented character",
       "me": "a real person: the person themselves",
       "permission": "a real person who agreed to appear in AI-made videos"}
MOST = 4  # pictures a character
MAX_SIDE = 2048
BACKDROP = (128, 128, 128)  # what shows through a transparent picture: the plain grey the Video Builder asks for
MAIN = re.compile(r"REF_([A-Za-z0-9_-]+)\.png")  # a video's cast: characters/REF_<key>.png, more of them REF_<key>.2.png
MORE = re.compile(r"REF_([A-Za-z0-9_-]+)\.(\d+)\.png")
RECORD = "cast.json"  # beside the pictures: who each is, so a video's cast can be used again


def key_of(name: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:24] or "lead"
    key, n = base, 2
    while key in taken:
        key, n = f"{base}_{n}", n + 1
    taken.add(key)
    return key


def _picture(data: bytes) -> Image.Image:
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except (OSError, Image.DecompressionBombError):
        raise JobError("That file isn't a picture the app can read (PNG, JPEG or WebP).") from None
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        flat = Image.new("RGB", im.size, BACKDROP)
        flat.paste(im, mask=im.getchannel("A"))
        im = flat
    im = im.convert("RGB")
    if max(im.size) > MAX_SIDE:
        im.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    if min(im.size) < 256:
        raise JobError("That picture is too small to keep a face by (at least 256 pixels a side).")
    return im


class Cast:
    def __init__(self, app):
        self.app = app
        self.cfg = app.cfg
        self.root = self.cfg.data / "cast"

    # ---- the saved characters ---------------------------------------------------------------------------------
    def _saved(self) -> list[dict]:
        s = self.app.store.setting("cast")
        return [dict(m) for m in s] if isinstance(s, list) else []

    def _save(self, members: list[dict]) -> None:
        self.app.store.set_setting("cast", members)

    def _find(self, members: list[dict], cid: str) -> dict:
        m = next((m for m in members if m["id"] == cid), None)
        if m is None:
            raise JobError("That character isn't in your Cast any more.")
        return m

    def _public(self, m: dict) -> dict:
        folder = self.root / m["id"]
        pics = [{"name": f, "url": f"/api/cast/{m['id']}/{f}?v={int((folder / f).stat().st_mtime)}"}
                for f in m["pictures"] if (folder / f).is_file()]
        return {**m, "pictures": pics, "whoSays": WHO.get(m.get("who"), WHO["invented"])}

    def list(self) -> dict:
        return {"members": [self._public(m) for m in self._saved()], "who": WHO, "most": MOST}

    def _keep(self, cid: str, images: list[Image.Image]) -> list[str]:
        folder = self.root / cid
        folder.mkdir(parents=True, exist_ok=True)
        names = []
        for im in images:
            name = f"{uuid.uuid4().hex[:8]}.png"
            im.save(folder / name)
            names.append(name)
        return names

    def add(self, name: str, about: str, who: str, confirmed: bool, pictures: list[bytes], source: str = "upload") -> dict:
        """A new character from one to four pictures. `confirmed`: the person ticked the box saying who it is."""
        if not confirmed:
            raise JobError("Tick the box to confirm who's in the pictures first.")
        if who not in WHO:
            raise JobError("Say who this is: an invented character, you, or someone who agreed to it.")
        if not 1 <= len(pictures) <= MOST:
            raise JobError(f"Give a character between 1 and {MOST} pictures.")
        images = [_picture(d) for d in pictures]  # every picture checked before any is kept
        members = self._saved()
        cid = uuid.uuid4().hex[:8]
        now = time.time()
        m = {"id": cid, "name": " ".join(name.split())[:60] or "Unnamed", "about": " ".join(about.split())[:600],
             "who": who, "confirmedAt": now, "source": source, "pictures": self._keep(cid, images), "at": now}
        members.append(m)
        self._save(members)
        return self._public(m)

    def edit(self, cid: str, name: str | None = None, about: str | None = None) -> dict:
        members = self._saved()
        m = self._find(members, cid)
        if name is not None and name.strip():
            m["name"] = " ".join(name.split())[:60]
        if about is not None:
            m["about"] = " ".join(about.split())[:600]
        self._save(members)
        return self._public(m)

    def add_pictures(self, cid: str, pictures: list[bytes]) -> dict:
        members = self._saved()
        m = self._find(members, cid)
        if len(m["pictures"]) + len(pictures) > MOST:
            raise JobError(f"A character has at most {MOST} pictures: remove one first.")
        m["pictures"] += self._keep(cid, [_picture(d) for d in pictures])
        self._save(members)
        return self._public(m)

    def remove_picture(self, cid: str, name: str) -> dict:
        members = self._saved()
        m = self._find(members, cid)
        if name not in m["pictures"]:
            raise JobError("That picture isn't there any more.")
        if len(m["pictures"]) == 1:
            raise JobError("A character needs at least one picture: add another first, or delete the character.")
        m["pictures"].remove(name)
        (self.root / cid / name).unlink(missing_ok=True)
        self._save(members)
        return self._public(m)

    def main_picture(self, cid: str, name: str) -> dict:
        members = self._saved()
        m = self._find(members, cid)
        if name not in m["pictures"]:
            raise JobError("That picture isn't there any more.")
        m["pictures"] = [name] + [f for f in m["pictures"] if f != name]
        self._save(members)
        return self._public(m)

    def remove(self, cid: str) -> dict:
        members = self._saved()
        self._find(members, cid)
        self._save([m for m in members if m["id"] != cid])
        shutil.rmtree(self.root / cid, ignore_errors=True)
        return self.list()

    def file(self, cid: str, name: str) -> Path:
        if not (re.fullmatch(r"[0-9a-f]{8}", cid) and re.fullmatch(r"[0-9a-f]{8}\.png", name)):
            raise JobError("No such picture.")
        f = self.root / cid / name
        if not f.is_file():
            raise JobError("No such picture.")
        return f

    # ---- the casts of earlier videos ---------------------------------------------------------------------------
    def _video_cast(self, pid: str, fid: str) -> list[dict]:
        """An earlier music video's characters: each REF_<key>.png in its characters/, with any more pictures of them,
        and who each is (from what the app copied in; otherwise the director invented them)."""
        folder = self.cfg.projects / pid / "music" / fid / "work" / "characters"
        if not folder.is_dir():
            return []
        try:
            record = json.loads((folder / RECORD).read_text())
        except (OSError, ValueError):
            record = {}
        try:
            play = json.loads((folder.parent / "screenplay.json").read_text()).get("cast") or {}
        except (OSError, ValueError, AttributeError):
            play = {}
        out = []
        for f in sorted(folder.iterdir()):
            hit = MAIN.fullmatch(f.name)
            if not hit or not f.is_file():
                continue
            key = hit.group(1)
            known = record.get(key) or {}
            said = play.get(key) if isinstance(play.get(key), dict) else {}
            more = sorted((g for g in folder.iterdir() if (h := MORE.fullmatch(g.name)) and h.group(1) == key),
                          key=lambda g: int(MORE.fullmatch(g.name).group(2)))
            out.append({"key": key, "name": known.get("name") or said.get("name") or key.replace("_", " "),
                        "about": known.get("about") or said.get("desc") or "",
                        "who": known.get("who") if known.get("who") in WHO else "invented",
                        "files": [f, *more], "path": f"music/{fid}/work/characters/{f.name}"})
        return out

    def videos(self) -> list[dict]:
        """Every earlier music video with characters, newest first: its song, and its cast's main pictures."""
        out = []
        for p in self.app.store.projects():
            root = self.cfg.projects / p["id"] / "music"
            if not root.is_dir():
                continue
            for d in root.iterdir():
                cast = self._video_cast(p["id"], d.name) if re.fullmatch(r"[0-9a-f]{8}", d.name) else []
                if not cast:
                    continue
                at = max(c["files"][0].stat().st_mtime for c in cast)
                out.append({"projectId": p["id"], "filmId": d.name, "title": p.get("title") or "Untitled", "at": at,
                            "cast": [{"key": c["key"], "name": c["name"], "about": c["about"], "who": c["who"],
                                      "pictures": len(c["files"]), "path": c["path"]} for c in cast]})
        return sorted(out, key=lambda v: -v["at"])

    def from_video(self, pid: str, fid: str, key: str, name: str, about: str, who: str, confirmed: bool) -> dict:
        """One character of an earlier video, saved into the Cast with all its pictures."""
        c = next((c for c in self._video_cast(pid, fid) if c["key"] == key), None) if re.fullmatch(r"[A-Za-z0-9_-]+", pid) \
            and re.fullmatch(r"[0-9a-f]{8}", fid) else None
        if c is None:
            raise JobError("That video's character isn't there any more.")
        return self.add(name or c["name"], about if about is not None else c["about"], who, confirmed,
                        [f.read_bytes() for f in c["files"][:MOST]], source=f"video {pid}/{fid}")

    # ---- into a video ------------------------------------------------------------------------------------------
    def resolve(self, ids: list[str] | None, from_video: dict | None) -> list[dict]:
        """The characters a new video is to use: {name, about, who, files} each (none: the director invents them)."""
        if ids and from_video:
            raise JobError("Choose characters from your Cast or the cast of an earlier video, not both.")
        if from_video:
            pid, fid = str(from_video.get("projectId") or ""), str(from_video.get("filmId") or "")
            cast = self._video_cast(pid, fid) if re.fullmatch(r"[A-Za-z0-9_-]+", pid) and re.fullmatch(r"[0-9a-f]{8}", fid) else []
            if not cast:
                raise JobError("That video's characters aren't there any more.")
            return [{k: c[k] for k in ("name", "about", "who", "files")} for c in cast]
        out = []
        members = self._saved()
        for cid in ids or []:
            m = self._find(members, cid)
            files = [self.root / cid / f for f in m["pictures"] if (self.root / cid / f).is_file()]
            if not files:
                raise JobError(f"{m['name']} has no pictures any more.")
            out.append({"name": m["name"], "about": m.get("about") or "", "who": m.get("who") or "invented", "files": files})
        return out


def place(members: list[dict], characters: Path) -> str:
    """The characters' pictures into a video's characters/ folder (REF_<key>.png, more as REF_<key>.2.png …), who
    each is beside them (cast.json), and the "Your cast" section for the director's notes."""
    characters.mkdir(parents=True, exist_ok=True)
    taken: set[str] = set()
    record: dict[str, Any] = {}
    lines = []
    for m in members:
        key = key_of(m["name"], taken)
        names = []
        for i, f in enumerate(m["files"][:MOST]):
            name = f"REF_{key}.png" if i == 0 else f"REF_{key}.{i + 1}.png"
            shutil.copyfile(f, characters / name)
            names.append(f"`characters/{name}`")
        record[key] = {"name": m["name"], "about": m["about"], "who": m["who"]}
        about = f" {m['about'].rstrip('.')}." if m["about"] else ""
        more = f" (more of them: {', '.join(names[1:])})" if len(names) > 1 else ""
        who = WHO.get(m["who"], WHO["invented"])
        real = (" The person confirmed this, so it's with their say-so: keep the likeness true to the pictures, never "
                "caricatured or made fun of, and show them with dignity.") if m["who"] != "invented" else ""
        lines.append(f"- **{m['name']}** (key `{key}`): {names[0]}{more}.{about} {who[0].upper() + who[1:]}.{real}")
    (characters / RECORD).write_text(json.dumps(record, indent=1))
    return ("## Your cast\n\nThe person chose this video's cast. Their pictures are already in `characters/`, filed as the "
            "Video Builder's own references (`refs_source` is `own` in settings.json). Use them as they are: don't make new "
            "pictures to stand in for them.\n\n" + "\n".join(lines) + "\n\n"
            "- In screenplay.json each of them is a cast member, under the key above, whose `ref` is their REF picture.\n"
            "- Make every picture of them (first frames, stills) with their main picture as a reference (`--ref` with "
            "tools/picture.py, or your picture tools' reference input), so they're the same in every shot; the other "
            "pictures show more of them. If your picture source takes no references, leave them out of the stills and "
            "let the Video Builder's references carry them, described the same way each time.\n"
            "- Anyone else on screen (a band behind them, people passing) is an original character you invent.\n")
