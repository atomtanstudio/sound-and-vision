"""The look of what's laid over a picture: the title, the artist and the brand's logos, on a song's cover, a living
cover's fixed top or a video's thumbnail. One description (a "look") and one renderer, so the editor in the app, the
cover and the thumbnail agree.

A look places each element by an anchor (a corner, an edge's middle or the centre: "tl" … "br") and its distance in
from that edge (dx, dy), in percent of the picture's shorter side, so "2.5% in from the bottom-left corner" means the
same on a square cover, a 16:9 thumbnail and a 9:16 story. Sizes are percent of the shorter side too.

The title can also be placed automatically (place "auto"): centred, near the top or the bottom, wherever the picture
is calmer and darker (the sleeve the app always made). The artist either follows the title (place "auto") or has a
place of its own. The editor (web/src/look/) draws with the same rules on a canvas.
"""

from __future__ import annotations

import copy
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ANCHORS = {"tl": (0, 0), "tc": (0.5, 0), "tr": (1, 0), "ml": (0, 0.5), "mc": (0.5, 0.5), "mr": (1, 0.5),
           "bl": (0, 1), "bc": (0.5, 1), "br": (1, 1)}
CASES = ("upper", "asis", "lower")
LEAD, BASE = 1.32, 0.86  # a title line's height, and where its baseline sits, in ems
FALLBACK = [Path.home() / ".local/share/fonts/maxmusic/Inter-Medium.ttf", Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]

# The sleeve the app has always made, as a look: the title centred near the top or the bottom (auto), the artist under
# it between two rules, the label's logo bottom-left and the app's bottom-right.
DEFAULT: dict[str, Any] = {
    "title": {"show": True, "place": "auto", "font": "Inter-Medium", "weight": None, "size": 6.2, "tracking": 0.3,
              "case": "upper", "color": "auto", "shadow": True, "width": 82.0, "anchor": "bc", "dx": 0.0, "dy": 10.5},
    "artist": {"show": True, "place": "auto", "font": "Inter-Medium", "weight": None, "size": 2.108, "tracking": 0.5,
               "case": "upper", "color": "auto", "shadow": True, "rules": True, "anchor": "bc", "dx": 0.0, "dy": 6.0},
    "logos": {"label": {"show": True, "anchor": "bl", "dx": 2.5, "dy": 2.5, "size": 6.0},
              "app": {"show": True, "anchor": "br", "dx": 1.25, "dy": 1.25, "size": 17.5}},
    "scrim": "auto",
}


# ---- fonts ----------------------------------------------------------------------------------------------------------

@lru_cache(maxsize=4)
def catalog(folder: str) -> list[dict]:
    """The fonts in data/fonts: id (the file's name), family, style, and the weight range of variable ones."""
    out = []
    for f in sorted(Path(folder).glob("*.[ot]tf")):
        try:
            face = ImageFont.truetype(str(f), 20)
            family, style = face.getname()
        except OSError:
            continue
        weight = None
        try:
            axis = next((x for x in face.get_variation_axes() if _is_weight(x)), None)
            if axis:
                weight = [int(axis["minimum"]), int(axis["maximum"]), int(axis["default"])]
        except (OSError, AttributeError):
            pass
        out.append({"id": f.stem, "family": family or f.stem, "style": style or "Regular", "file": f.name, "weight": weight})
    return out


def _is_weight(axis: dict) -> bool:
    name = axis.get("name")
    name = name.decode(errors="replace") if isinstance(name, bytes) else str(name)
    return name.strip().lower() in ("weight", "wght")


def font_path(folder: Path, fid: str) -> Path | None:
    for ext in (".ttf", ".otf"):
        p = folder / f"{fid}{ext}"
        if p.is_file() and p.resolve().parent == folder.resolve():
            return p
    return None


def load_font(folder: Path, fid: str, px: float, weight: int | None = None) -> ImageFont.FreeTypeFont:
    path = font_path(folder, fid) or next((f for f in FALLBACK if f.exists()), None)
    if path is None:
        return ImageFont.load_default(max(1, round(px)))
    face = ImageFont.truetype(str(path), max(1, round(px)))
    if weight:
        try:
            axes = face.get_variation_axes()
            face.set_variation_by_axes([min(a["maximum"], max(a["minimum"], weight)) if _is_weight(a) else a["default"]
                                        for a in axes])
        except (OSError, AttributeError):
            pass
    return face


# ---- the description ------------------------------------------------------------------------------------------------

def _merge(base: dict, over: dict | None) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _num(v: Any, lo: float, hi: float, default: float) -> float:
    try:
        return min(hi, max(lo, float(v)))
    except (TypeError, ValueError):
        return default


def normalize(*looks: dict | None) -> dict:
    """DEFAULT, then each look over it (the brand's, then a song's own), checked and kept in range."""
    look = DEFAULT
    for over in looks:
        look = _merge(look, over if isinstance(over, dict) else None)
    for key in ("title", "artist"):
        t, d = look[key], DEFAULT[key]
        t["show"] = bool(t.get("show", True))
        t["place"] = "manual" if t.get("place") == "manual" else "auto"
        t["font"] = str(t.get("font") or d["font"])[:80]
        t["weight"] = int(_num(t["weight"], 1, 1000, 400)) if t.get("weight") else None
        t["size"] = _num(t.get("size"), 0.5, 40, d["size"])
        t["tracking"] = _num(t.get("tracking"), -0.2, 2, d["tracking"])
        t["case"] = t.get("case") if t.get("case") in CASES else "upper"
        c = str(t.get("color") or "auto")
        t["color"] = c if c == "auto" or (len(c) == 7 and c.startswith("#")) else "auto"
        t["shadow"] = bool(t.get("shadow", True))
        t["anchor"] = t.get("anchor") if t.get("anchor") in ANCHORS else d["anchor"]
        t["dx"], t["dy"] = _num(t.get("dx"), -100, 200, 0.0), _num(t.get("dy"), -100, 200, 0.0)
        if key == "title":
            t["width"] = _num(t.get("width"), 10, 100, d["width"])
        else:
            t["rules"] = bool(t.get("rules", True))
    logos = {}
    for lid, lg in (look.get("logos") or {}).items():
        if not isinstance(lg, dict):
            continue
        logos[str(lid)[:40]] = {"show": bool(lg.get("show", True)),
                                "anchor": lg.get("anchor") if lg.get("anchor") in ANCHORS else "br",
                                "dx": _num(lg.get("dx"), -100, 200, 2.0), "dy": _num(lg.get("dy"), -100, 200, 2.0),
                                "size": _num(lg.get("size"), 1, 80, 8.0)}
    look["logos"] = logos
    s = look.get("scrim")
    look["scrim"] = s if s in ("auto", "none") else _num(s, 0, 1, 0.4) if s is not None else "auto"
    return look


def place(anchor: str, dx: float, dy: float, w: float, h: float, W: float, H: float, s: float,
          whole: bool = False) -> tuple[float, float]:
    """The top-left corner of a w x h box anchored in a W x H picture, dx/dy (percent of the short side s) in from the
    anchored edges (from the centre line for a middle anchor, where a positive value moves right or down). `whole`:
    the distances in whole pixels (how the logos have always been placed)."""
    ax, ay = ANCHORS[anchor]
    mx, my = dx * s / 100, dy * s / 100
    if whole:
        mx, my = int(mx), int(my)
    px = ax * W + (mx if ax == 0 else -mx if ax == 1 else mx)
    py = ay * H + (my if ay == 0 else -my if ay == 1 else my)
    return px - ax * w, py - ay * h


# ---- text -----------------------------------------------------------------------------------------------------------

def cased(text: str, case: str) -> str:
    text = " ".join(str(text or "").split())
    return text.upper() if case == "upper" else text.lower() if case == "lower" else text


def tracked_width(font, text: str, tracking: float) -> float:
    return sum(font.getlength(c) for c in text) + tracking * max(0, len(text) - 1)


def split(font, text: str, tracking: float, most: float) -> list[str]:
    """One line if it fits in `most`, otherwise two, broken where the halves are closest in width."""
    one = " ".join(text.split())
    if not one or tracked_width(font, one, tracking) <= most:
        return [one] if one else []
    words = one.split(" ")
    if len(words) < 2:
        return [one]
    best, gap = [one], float("inf")
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        g = abs(tracked_width(font, a, tracking) - tracked_width(font, b, tracking))
        if g < gap:
            best, gap = [a, b], g
    return best


def _draw_line(d: ImageDraw.ImageDraw, font, text: str, x: float, baseline: float, tracking: float, fill) -> None:
    top = baseline - font.getbbox("H")[3]
    for c in text:
        d.text((x, top), c, font=font, fill=fill)
        x += font.getlength(c) + tracking


def _hsv(h: float, s: float, v: float) -> tuple[int, int, int]:
    i = int(h * 6) % 6
    f = h * 6 - int(h * 6)
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    r, g, b = [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)][i]
    return round(r * 255), round(g * 255), round(b * 255)


def palette(small: np.ndarray) -> list[tuple[int, int, int]]:
    """Two light, vivid colors from the picture's own hues (by how colorful and bright each part is); a picture with
    no color to speak of gives a warm white."""
    x = small.reshape(-1, 3).astype(np.float32) / 255
    mx, mn = x.max(1), x.min(1)
    d = np.maximum(mx - mn, 1e-6)
    r, g, b = x[:, 0], x[:, 1], x[:, 2]
    h = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) / 6
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    w = sat ** 1.2 * mx ** 1.5
    bins = 18
    hist = np.bincount((h * bins).astype(int) % bins, weights=w, minlength=bins)
    # black and white, or nearly: colored letters would be the only color in it, so a warm white
    if hist.sum() < 1 or float((sat * mx).mean()) < 0.06:
        return [(242, 238, 230)]
    picks: list[int] = []
    for k in np.argsort(-hist):
        if all(min(abs(k - p), bins - abs(k - p)) >= 3 for p in picks):
            picks.append(int(k))
        if len(picks) == 2:
            break
    return sorted((_hsv((k + 0.5) / bins, 0.45, 1.0) for k in picks), key=lambda c: c[0] - c[2])


def zone(lum: np.ndarray, top: float, height: float) -> tuple[float, float]:
    """How bright (85th percentile) and how busy (spread) the picture is behind the words (top/height: 0..1)."""
    n = lum.shape[0]
    y0, y1 = max(0, int((top - 0.02) * n)), min(n, int((top + height + 0.03) * n) + 1)
    v = lum[y0:y1, int(0.12 * n):int(0.88 * n)].ravel()
    return (float(np.percentile(v, 85)), float(v.std())) if v.size else (0.5, 0.2)


def info(picture: Image.Image) -> dict:
    """What the editor needs to draw exactly as render() will: the picture's two title colours and its small
    grayscale (96 × 96, 0..255), from the same picture at the same size the server sets it on."""
    thumb = np.asarray(picture.convert("RGB").resize((96, 96), Image.Resampling.BILINEAR))
    lum = (thumb @ np.array([0.299, 0.587, 0.114])) / 255
    return {"palette": palette(thumb), "n": 96, "lum": np.round(lum * 255).astype(int).ravel().tolist()}


def hexrgb(c: str) -> tuple[int, int, int]:
    return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)


# ---- laying it out --------------------------------------------------------------------------------------------------

def layout(look: dict, W: int, H: int, title: str, artist: str, fonts: Path, lum: np.ndarray | None = None) -> dict:
    """Where everything goes, in pixels: {"title": {lines, px, tracking, box, baselines}, "artist": {...}, "place"}.
    `lum` (a small grayscale of the picture, 0..1) lets an auto title choose the calmer of the top and the bottom."""
    s = min(W, H)
    T, A = look["title"], look["artist"]
    out: dict[str, Any] = {"place": "manual"}

    t = None
    if T["show"] and title.strip():
        px = s * T["size"] / 100
        font = load_font(fonts, T["font"], px, T["weight"])
        tr = T["tracking"] * px
        most = W * T["width"] / 100
        lines = split(font, cased(title, T["case"]), tr, most)
        widest = max([tracked_width(font, x, tr) for x in lines] or [1])
        if widest > most:  # one word too long for the width: the size comes down to fit
            px *= most / widest
            font = load_font(fonts, T["font"], px, T["weight"])
            tr = T["tracking"] * px
            widest = max([tracked_width(font, x, tr) for x in lines] or [1])
        t = {"lines": lines, "px": px, "tracking": tr, "font": font, "w": widest, "h": len(lines) * px * LEAD,
             "widths": [tracked_width(font, x, tr) for x in lines]}
    a = None
    if A["show"] and artist.strip():
        bpx = s * A["size"] / 100
        bfont = load_font(fonts, A["font"], bpx, A["weight"])
        btr = A["tracking"] * bpx
        text = cased(artist, A["case"])
        a = {"lines": [text], "px": bpx, "tracking": btr, "font": bfont, "w": tracked_width(bfont, text, btr),
             "h": bpx * 1.2, "widths": [tracked_width(bfont, text, btr)]}

    follow = a is not None and t is not None and A["place"] == "auto"
    gap = t["px"] * 0.62 if follow else 0
    if t:
        anchor, dx, dy = T["anchor"], T["dx"], T["dy"]
        group_h = t["h"] + (gap + a["h"] if follow else 0)
        group_w = max(t["w"], a["w"] if follow else 0)
        if T["place"] == "auto":
            anchor, dx, dy = "bc", 0.0, DEFAULT["title"]["dy"]
            out["place"] = "lower"
            if lum is not None:
                hh = group_h / H
                lo, up = zone(lum, 1 - 0.105 - hh, hh), zone(lum, 0.105, hh)
                if up[0] + 1.2 * up[1] + 0.06 < lo[0] + 1.2 * lo[1]:
                    anchor, out["place"] = "tc", "upper"
        x0, y0 = place(anchor, dx, dy, group_w, group_h, W, H, s)
        align = ANCHORS[anchor][0]
        t["box"] = [x0, y0, group_w, t["h"]]
        t["align"] = align
        t["xs"] = [x0 + (group_w - w) * align for w in t["widths"]]
        t["baselines"] = [y0 + i * t["px"] * LEAD + t["px"] * BASE for i in range(len(t["lines"]))]
        out["title"] = t
        if follow:
            ay = y0 + t["h"] + gap
            a["box"] = [x0, ay, group_w, a["h"]]
            a["align"] = align
            a["xs"] = [x0 + (group_w - a["w"]) * align]
            a["baselines"] = [ay + a["px"] * 0.95]
    if a and "box" not in a:
        x0, y0 = place(A["anchor"], A["dx"], A["dy"], a["w"], a["h"], W, H, s)
        a["box"] = [x0, y0, a["w"], a["h"]]
        a["align"] = ANCHORS[A["anchor"]][0]
        a["xs"] = [x0]
        a["baselines"] = [y0 + a["px"] * 0.95]
    if a:
        out["artist"] = a
    return out


def render(picture: Image.Image, title: str, artist: str, logos: dict[str, Path], look: dict | None, fonts: Path,
           ) -> tuple[Image.Image, dict]:
    """Everything set over the picture, as one transparent layer its size: a soft scrim, the title, the artist and
    the logos. `look` is a normalized look (normalize()); None is the default sleeve."""
    look = look if look is not None else normalize()
    W, H = picture.size
    s = min(W, H)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    clear = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    def paint(color, mask: Image.Image) -> None:
        nonlocal layer
        fill = Image.new("RGBA", (W, H), (*color, 255)) if isinstance(color, tuple) else color
        layer = Image.alpha_composite(layer, Image.composite(fill, clear, mask))

    thumb = np.asarray(picture.convert("RGB").resize((96, 96), Image.Resampling.BILINEAR))
    lum = (thumb @ np.array([0.299, 0.587, 0.114])) / 255
    pal = palette(thumb)
    lay = layout(look, W, H, title, artist, fonts, lum)
    t, a = lay.get("title"), lay.get("artist")
    T, A = look["title"], look["artist"]

    # the scrim: darker where the picture is bright under the words, eased to nothing
    scrim = 0.0
    if t or a:
        box = (t or a)["box"]
        if a and t:
            top, bottom = min(t["box"][1], a["box"][1]), max(t["box"][1] + t["box"][3], a["box"][1] + a["box"][3])
        else:
            top, bottom = box[1], box[1] + box[3]
        bright, _ = zone(lum, max(0.0, top / H), max(0.01, (bottom - top) / H))
        scrim = (min(0.75, max(0.15, (bright - 0.1) * 2)) if look["scrim"] == "auto" else
                 0.0 if look["scrim"] == "none" else float(look["scrim"]))
        if scrim > 0:
            ramp = np.zeros(H, dtype=np.float32)
            if (top + bottom) / 2 >= H / 2:
                y0 = int(max(0, top - 0.14 * s))
                u = np.linspace(0, 1, H - y0)
                ramp[y0:] = u * u * (3 - 2 * u) * scrim
            else:
                y1 = int(0.30 * s if lay["place"] == "upper" else min(H, max(0.30 * s, bottom + 0.14 * s)))
                u = np.linspace(0, 1, y1)
                ramp[:y1] = (1 - u * u * (3 - 2 * u)) * scrim
            paint((0, 0, 0), Image.fromarray((np.repeat(ramp[:, None], W, 1) * 255).astype(np.uint8), "L"))

    def words(el: dict, value: int) -> Image.Image:
        mask = Image.new("L", (W, H), 0)
        d = ImageDraw.Draw(mask)
        for line, x, base in zip(el["lines"], el["xs"], el["baselines"]):
            _draw_line(d, el["font"], line, x, base, el["tracking"], value)
        return mask

    tmask = words(t, 255) if t else None
    amask = None
    if a:
        amask = words(a, 235)
        if A["rules"] and abs(a["align"] - 0.5) < 0.01:  # the two short rules either side of a centred artist
            d = ImageDraw.Draw(amask)
            bx = a["xs"][0]
            gap, rl, cy, lw = a["px"] * 1.1, 0.07 * s, a["baselines"][0] - a["px"] * 0.36, max(1, round(s / 1080))
            for dy in (-2.2, 2.2):
                yy = cy + dy * s / 1080
                d.line([(bx - gap - rl, yy), (bx - gap, yy)], fill=160, width=lw)
                d.line([(bx + a["w"] + gap, yy), (bx + a["w"] + gap + rl, yy)], fill=160, width=lw)
    for el, mask, spec in ((t, tmask, T), (a, amask, A)):
        if el and mask is not None and spec["shadow"]:
            shadow = Image.new("L", (W, H), 0)
            shadow.paste(Image.eval(mask, lambda v: int(v * 0.6)), (0, round(s * 0.0025)))
            paint((0, 0, 0), shadow.filter(ImageFilter.GaussianBlur(s * 0.006)))
    if t and tmask is not None:
        if T["color"] == "auto":
            grad = np.zeros((H, W, 3), dtype=np.uint8)
            c0, c1 = np.array(pal[0], np.float32), np.array(pal[-1], np.float32)
            left = t["box"][0] + (t["box"][2] - t["w"]) * t["align"]  # across the title's own width
            u = np.clip((np.arange(W) - left) / max(1.0, t["w"]), 0, 1)[:, None]
            grad[:] = (c0 * (1 - u) + c1 * u).astype(np.uint8)[None, :, :]
            paint(Image.fromarray(grad, "RGB").convert("RGBA"), tmask)
        else:
            paint(hexrgb(T["color"]), tmask)
    if a and amask is not None:
        paint(tuple(int(c + (255 - c) * 0.6) for c in pal[-1]) if A["color"] == "auto" else hexrgb(A["color"]), amask)

    # the logos, each with a soft shadow so it reads on busy art
    for lid, lg in look["logos"].items():
        f = logos.get(lid)
        if not lg["show"] or not f or not f.exists():
            continue
        logo = Image.open(f).convert("RGBA")
        w = max(2, int(s * lg["size"] / 100))
        h = max(2, int(w * logo.height / logo.width))
        logo = logo.resize((w, h), Image.Resampling.LANCZOS)
        x, y = (int(v) for v in place(lg["anchor"], lg["dx"], lg["dy"], w, h, W, H, s, whole=True))
        blur, off = max(2, s // 200), max(1, s // 300)
        sh = Image.new("L", (W, H), 0)
        sh.paste(Image.eval(logo.getchannel("A"), lambda v: int(v * 0.55)), (x + off, y + off))
        paint((0, 0, 0), sh.filter(ImageFilter.GaussianBlur(blur)))
        if 0 <= x and 0 <= y and x + w <= W and y + h <= H:
            layer.alpha_composite(logo, (x, y))
        else:  # partly off the picture: what's inside is kept
            part = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            part.paste(logo, (x, y), logo)
            layer = Image.alpha_composite(layer, part)
    return layer, {"place": lay["place"], "palette": pal, "scrim": round(scrim, 2)}
