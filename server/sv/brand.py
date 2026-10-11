"""The person's branding: their logos (any number, kept as PNGs in data/branding/) and their house look, how the title,
the artist and the logos sit on a cover or a thumbnail (look.py). A song can have a look of its own (the project's
"layout"), laid over the house look, so every cover needn't look the same.

The app started with two logos, the label's (bottom-left) and the app's (bottom-right); they're the first two here and
can be renamed, replaced, moved or removed like any other.
"""

from __future__ import annotations

import io
import re
import time
import uuid
from pathlib import Path
from typing import Any

from PIL import Image

from . import look as look_mod
from .jobs import JobError

FIRST = [{"id": "label", "name": "Label"}, {"id": "app", "name": "Sound / Vision"}]
MAX_SIDE = 2048


class Brand:
    def __init__(self, app):
        self.app = app
        self.cfg = app.cfg
        self.root = self.cfg.data / "branding"
        self.fonts = self.cfg.data / "fonts"

    def _saved(self) -> dict:
        s = self.app.store.setting("brand")
        if not isinstance(s, dict):
            s = {"logos": [x for x in FIRST if (self.root / f"{x['id']}.png").exists()], "look": {}}
        return s

    def get(self) -> dict:
        s = self._saved()
        logos = []
        for x in s.get("logos") or []:
            f = self.root / f"{x['id']}.png"
            if f.exists():
                with Image.open(f) as im:
                    w, h = im.size
                logos.append({**x, "file": f"/api/brand/logos/{x['id']}.png?v={int(f.stat().st_mtime)}", "w": w, "h": h})
        return {"logos": logos, "look": look_mod.normalize(s.get("look")), "fonts": look_mod.catalog(str(self.fonts))}

    def logos(self) -> dict[str, Path]:
        return {x["id"]: self.root / f"{x['id']}.png" for x in self._saved().get("logos") or []
                if (self.root / f"{x['id']}.png").exists()}

    def house(self) -> dict:
        """The brand's own look, as saved (normalize() lays it over the default)."""
        return self._saved().get("look") or {}

    def look(self, p: dict | None = None) -> dict:
        """The house look, with the song's own over it."""
        return look_mod.normalize(self._saved().get("look"), (p or {}).get("layout"))

    def logo_file(self, lid: str) -> Path:
        if not re.fullmatch(r"[a-z0-9-]{1,40}", lid) or lid not in self.logos():
            raise JobError("That logo isn't here any more.")
        return self.root / f"{lid}.png"

    # ---- changes ----------------------------------------------------------------------------------------------------
    def add_logo(self, name: str, data: bytes, replace: str | None = None) -> dict:
        """A logo from a picture file (PNG, JPEG or WebP; transparency kept), up to 2048 px a side. `replace`: the id
        of a logo whose picture this becomes (keeping its place)."""
        try:
            im = Image.open(io.BytesIO(data))
            im.load()
        except (OSError, Image.DecompressionBombError):
            raise JobError("That file isn't a picture the app can read (PNG, JPEG or WebP).") from None
        im = im.convert("RGBA")
        bbox = im.getchannel("A").getbbox()  # the empty margin around it goes, so it sits where it's put
        if bbox:
            im = im.crop(bbox)
        if max(im.size) > MAX_SIDE:
            im.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
        s = self._saved()
        if replace:
            if replace not in self.logos():
                raise JobError("That logo isn't here any more.")
            lid = replace
        else:
            lid = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:24] or "logo"
            if any(x["id"] == lid for x in s.get("logos") or []):
                lid = f"{lid}-{uuid.uuid4().hex[:4]}"
            s.setdefault("logos", []).append({"id": lid, "name": name.strip()[:60] or "Logo", "at": time.time()})
            used = {lg["anchor"] for lg in look_mod.normalize(s.get("look"))["logos"].values() if lg["show"]}
            corner = next((c for c in ("tr", "tl", "br", "bl") if c not in used), "tr")
            s.setdefault("look", {}).setdefault("logos", {})[lid] = {"show": True, "anchor": corner, "dx": 2.5, "dy": 2.5,
                                                                     "size": 10.0}
        self.root.mkdir(parents=True, exist_ok=True)
        im.save(self.root / f"{lid}.png")
        self.app.store.set_setting("brand", s)
        return self.get()

    def rename_logo(self, lid: str, name: str) -> dict:
        s = self._saved()
        for x in s.get("logos") or []:
            if x["id"] == lid:
                x["name"] = name.strip()[:60] or x["name"]
        self.app.store.set_setting("brand", s)
        return self.get()

    def remove_logo(self, lid: str) -> dict:
        self.logo_file(lid)
        s = self._saved()
        s["logos"] = [x for x in s.get("logos") or [] if x["id"] != lid]
        ((s.get("look") or {}).get("logos") or {}).pop(lid, None)
        (self.root / f"{lid}.png").unlink(missing_ok=True)
        self.app.store.set_setting("brand", s)
        return self.get()

    def set_look(self, look: dict[str, Any]) -> dict:
        s = self._saved()
        s["look"] = look_mod.normalize(look)
        self.app.store.set_setting("brand", s)
        return self.get()
