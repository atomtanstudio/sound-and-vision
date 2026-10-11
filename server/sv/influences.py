"""The influence library: LoRAs, as the app calls them (Artist, Genre or Style). Each one is a
.safetensors file under loras/soundandvision/<model>/ with a sidecar <name>.json describing it:

    {"name": "Dream pop", "kind": "Style", "recommended": 0.5, "max": 0.8, "about": "...", "hidden": false}

Hidden ones (the instrumental influence) are used by the app itself, never listed.

Adding your own: an uploaded file or a Hugging Face link. Only .safetensors is accepted (a pickled
.ckpt/.pt can run code when loaded); the header is read to check it's a LoRA and which song model
it was trained for (from its tensor names), and the user can correct the model if it can't tell.
"""

from __future__ import annotations

import errno
import hashlib
import json
import re
import shutil
import struct
import time
from pathlib import Path
from urllib.parse import urlparse

MAX_BYTES = 4 * 1024**3
MODELS = ("yue2", "ace15", "music3")


class InfluenceError(ValueError):
    pass


def library(loras: Path) -> dict[str, dict]:
    root = loras / "soundandvision"
    out: dict[str, dict] = {}
    for side in sorted(root.glob("*/*.json")):
        model_file = side.with_suffix(".safetensors")
        if not model_file.exists():
            continue
        try:
            rec = json.loads(side.read_text())
        except ValueError:
            continue
        iid = side.stem
        out[iid] = {"id": iid, "file": str(model_file.relative_to(loras)), "models": [side.parent.name],
                    "kind": "Style", "recommended": 0.5, "max": 1.0, "about": "", **rec}
    return out


def in_words(rec: dict) -> str:
    """An influence's sound in words, for a song model it wasn't trained for: "Glitchcore: a dark, stuttering
    electro-industrial track with chopped pitched vocals" (its name and the first sentence of what it's about)."""
    about = " ".join(str(rec.get("about") or "").split())
    about = re.split(r"(?<=[.!?])\s", about)[0].strip().rstrip(".,; ")
    about = re.sub(r"^(turns|makes) (a|the|your|any) songs? into\s+", "", about, flags=re.I)
    about = re.sub(r"[.,;]?\s*trained on\b.*$", "", about, flags=re.I).strip()
    return f"{rec['name']}: {about[:160]}" if about else str(rec["name"])


def sort_out(choices: list, library: dict[str, dict], model: str) -> tuple[list[dict], list[str]]:
    """The influences picked for a song, for one model: those trained for it (loaded, at their strength), and the rest
    described in words (for its style). One that's gone from the library is left out."""
    trained, words = [], []
    for c in choices:
        rec = library.get(c.id)
        if not rec or c.strength <= 0:
            continue
        if model in rec.get("models", []):
            trained.append({"id": c.id, "name": rec["name"], "file": rec["file"], "strength": c.strength})
        else:
            words.append(in_words(rec))
    return trained, words


def listed(loras: Path, model: str | None = None) -> list[dict]:
    return [r for r in library(loras).values() if not r.get("hidden") and (model is None or model in r["models"])]


def header(path: Path) -> dict:
    with open(path, "rb") as f:
        raw = f.read(8)
        if len(raw) < 8:
            raise InfluenceError("That file is empty or cut short.")
        n = struct.unpack("<Q", raw)[0]
        if n <= 0 or n > 64 * 1024 * 1024:
            raise InfluenceError("That isn't a .safetensors file (its header doesn't read).")
        try:
            return json.loads(f.read(n))
        except ValueError as exc:
            raise InfluenceError("That isn't a .safetensors file (its header doesn't read).") from exc


def inspect(path: Path) -> dict:
    """What the file is: a LoRA? for which model? its rank, size and trigger words if it says."""
    h = header(path)
    meta = h.pop("__metadata__", {}) or {}
    keys = list(h)
    lora = [k for k in keys if re.search(r"lora_(A|B|up|down)\b|\.lora\.|lokr|hada_", k)]
    if not lora:
        raise InfluenceError("That file isn't a LoRA (it has no LoRA weights), so it can't be an influence.")
    joined = "\n".join(keys[:4000])
    model = None
    if re.search(r"(text_encoders|diffusion_model)\.model\.layers\.\d+\.(mlp\.gate_up_proj|self_attn\.qkv_proj)", joined) \
            or "yue2" in json.dumps(meta).lower():
        model = "yue2"
    elif re.search(r"ace|lyric_encoder|acestep", joined + json.dumps(meta), re.I):
        model = "ace15"
    elif re.search(r"minimax_music|music3", joined + json.dumps(meta), re.I):
        model = "music3"
    ranks = sorted({min(v["shape"]) for k, v in h.items() if re.search(r"lora_(A|down)", k) and "shape" in v})
    trigger = None
    for k in ("ss_tag_frequency", "trigger", "trigger_word", "modelspec.trigger_phrase"):
        if meta.get(k):
            try:
                tf = json.loads(meta[k]) if k == "ss_tag_frequency" else meta[k]
                trigger = next(iter(next(iter(tf.values())).keys())) if isinstance(tf, dict) else str(tf)
            except (ValueError, StopIteration, AttributeError):
                pass
            break
    return {"model": model, "loraTensors": len(lora), "rank": ranks[-1] if ranks else None, "trigger": trigger,
            "name": meta.get("name") or meta.get("ss_output_name"), "bytes": path.stat().st_size}


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:48]
    return s or "influence"


def add(loras: Path, src: Path, *, name: str, kind: str, about: str, model: str, source: str,
        recommended: float = 0.5) -> dict:
    """File a checked LoRA into the library and describe it. `src` is moved, not copied."""
    if model not in MODELS:
        raise InfluenceError("Choose which song model it's for.")
    if kind not in ("Artist", "Genre", "Style"):
        raise InfluenceError("Choose Artist, Genre or Style.")
    info = inspect(src)
    folder = loras / "soundandvision" / model
    folder.mkdir(parents=True, exist_ok=True)
    base = slug(name)
    iid, i = base, 2
    while (folder / f"{iid}.safetensors").exists():
        iid, i = f"{base}_{i}", i + 1
    sha = hashlib.sha256()
    with open(src, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            sha.update(chunk)
    dest = folder / f"{iid}.safetensors"
    move_into(src, dest)
    dest.chmod(0o644)
    rec = {"name": name.strip()[:60], "kind": kind, "about": about.strip()[:400], "recommended": recommended, "max": 1.0,
           "source": source, "sha256": sha.hexdigest(), "rank": info["rank"], "trigger": info["trigger"],
           "added": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "own": True}
    (folder / f"{iid}.json").write_text(json.dumps(rec, indent=2))
    return {"id": iid, "file": str(dest.relative_to(loras)), "models": [model], **rec}


def move_into(src: Path, dest: Path) -> None:
    """Move a file into the library. The app's data and the models can be on different disks, where a plain
    rename can't cross: then it's copied beside the destination and switched in whole, so nothing half-written is
    ever seen under the real name."""
    try:
        src.replace(dest)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        part = dest.with_name(f".{dest.name}.part")
        try:
            shutil.copyfile(src, part)
            part.replace(dest)
        finally:
            part.unlink(missing_ok=True)
        src.unlink(missing_ok=True)


def hf_url(url: str) -> str:
    """A Hugging Face file link, as the direct download address. Only huggingface.co / hf.co, only .safetensors."""
    u = urlparse(url.strip())
    if u.scheme != "https" or u.hostname not in ("huggingface.co", "hf.co"):
        raise InfluenceError("Paste a link to a file on huggingface.co.")
    path = u.path.replace("/blob/", "/resolve/", 1)
    if "/resolve/" not in path or not path.endswith(".safetensors"):
        raise InfluenceError("Link to the .safetensors file itself (open the file on Hugging Face and copy its address).")
    return f"https://huggingface.co{path}"
