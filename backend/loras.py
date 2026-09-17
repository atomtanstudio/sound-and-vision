"""Discover local YuE2 adapters and merge both experts into an owned model instance."""

from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from functools import lru_cache
from pathlib import Path


PAIR = re.compile(
    r"^(text_encoders|diffusion_model)\.model\.layers\.(\d+)\."
    r"(self_attn\.(?:qkv_proj|o_proj)|mlp\.(?:gate_up_proj|down_proj))$"
)
SHAPES = {"qkv_proj": (4096, 2048), "o_proj": (2048, 2048),
          "gate_up_proj": (12288, 2048), "down_proj": (2048, 6144)}


def fingerprint(path):
    stat = Path(path).stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_header(path):
    """Read bounded safetensors metadata without importing Torch into the API."""
    with Path(path).open("rb") as source:
        raw = source.read(8)
        if len(raw) != 8:
            raise ValueError("Incomplete safetensors file.")
        length = struct.unpack("<Q", raw)[0]
        if not 2 <= length <= 16 * 1024 * 1024:
            raise ValueError("Invalid safetensors header.")
        header = json.loads(source.read(length))
    if not isinstance(header, dict):
        raise ValueError("Invalid safetensors header.")
    metadata = header.pop("__metadata__", {})
    if not isinstance(metadata, dict):
        raise ValueError("Invalid adapter metadata.")
    spans = []
    for key, tensor in header.items():
        if not isinstance(tensor, dict) or tensor.get("dtype") not in {"F16", "BF16", "F32"}:
            raise ValueError("Adapter tensors must use F16, BF16 or F32.")
        shape = tensor.get("shape")
        if not isinstance(shape, list) or any(type(n) is not int or n < 1 for n in shape):
            raise ValueError("Invalid tensor shape.")
        offsets = tensor.get("data_offsets")
        if (not isinstance(offsets, list) or len(offsets) != 2 or
                any(type(n) is not int for n in offsets)):
            raise ValueError("Invalid tensor offsets.")
        size = math.prod(shape) * (4 if tensor["dtype"] == "F32" else 2)
        if offsets[0] < 0 or offsets[1] - offsets[0] != size:
            raise ValueError("Invalid tensor byte length.")
        spans.append(offsets)
    end = 0
    for start, stop in sorted(spans):
        if start != end:
            raise ValueError("Overlapping or missing tensor data.")
        end = stop
    if not spans or length + 8 + end != Path(path).stat().st_size:
        raise ValueError("Incomplete safetensors data.")
    return header, metadata


def adapter_pairs(header):
    pairs = sorted(k[:-len(".lora_A.weight")] for k in header if k.endswith(".lora_A.weight"))
    consumed = set()
    experts = set()
    for prefix in pairs:
        match = PAIR.fullmatch(prefix)
        if not match or int(match[2]) >= 28:
            raise ValueError("Unsupported adapter layout. Use a YuE2 AR/NAR LoRA exported by AI Toolkit.")
        a, b = prefix + ".lora_A.weight", prefix + ".lora_B.weight"
        if b not in header:
            raise ValueError("Adapter has an unpaired LoRA tensor.")
        ashape, bshape = header[a]["shape"], header[b]["shape"]
        rows, cols = SHAPES[match[3].split(".")[-1]]
        if (len(ashape) != 2 or len(bshape) != 2 or
                not 1 <= ashape[0] <= 2048 or ashape[1] != cols or
                bshape != [rows, ashape[0]]):
            raise ValueError("Adapter dimensions do not match YuE2-3B.")
        consumed.update((a, b))
        if prefix + ".alpha" in header:
            if math.prod(header[prefix + ".alpha"]["shape"]) != 1:
                raise ValueError("LoRA alpha must be a scalar.")
            consumed.add(prefix + ".alpha")
        experts.add("AR" if match[1] == "text_encoders" else "NAR")
    if not pairs or consumed != set(header):
        raise ValueError("Unsupported or unpaired adapter tensors; no weights were loaded.")
    return pairs, sorted(experts)


@lru_cache(maxsize=128)
def inspect_adapter(path, stamp):
    header, metadata = read_header(path)
    pairs, experts = adapter_pairs(header)
    engine = metadata.get("sound_vision_inference_engine")
    if engine not in (None, "native"):
        raise ValueError("Unsupported adapter inference engine.")
    digest = sha256(path)
    if fingerprint(path) != stamp:
        raise ValueError("Adapter changed during scanning. Finish copying it and refresh.")
    return {"sha256": digest, "experts": experts, "pairs": len(pairs), "metadata": metadata}


def metadata_trigger(meta):
    try:
        frequency = json.loads(meta.get("ss_tag_frequency", "{}"))
        tags = {tag for group in frequency.values() for tag in group}
        return next(iter(tags)) if len(tags) == 1 else ""
    except (ValueError, TypeError, AttributeError):
        return ""


class LoraLibrary:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def scan(self):
        groups, issues = {}, []
        for path in sorted(self.root.rglob("*.safetensors")):
            relative = path.relative_to(self.root)
            try:
                if not path.resolve().is_relative_to(self.root):
                    raise ValueError("Links outside the LoRA folder are not loaded.")
                info = inspect_adapter(str(path), fingerprint(path))
                meta = info["metadata"]
                sidecar = path.parent / "lora.json"
                options = {}
                if sidecar.exists():
                    if not sidecar.resolve().is_relative_to(self.root) or sidecar.stat().st_size > 65536:
                        raise ValueError("Invalid lora.json sidecar.")
                    options = json.loads(sidecar.read_text())
                    if not isinstance(options, dict):
                        raise ValueError("lora.json must contain an object.")
                group_key = str(relative.parent) if path.parent != self.root else str(relative)
                kind = options.get("kind", "artist" if relative.parts[0] == "artists" else "style")
                if kind not in {"style", "artist"}:
                    raise ValueError("LoRA kind must be style or artist.")
                name = options.get("name", path.parent.name if path.parent != self.root else path.stem)
                trigger = options.get("trigger", metadata_trigger(meta))
                if (not isinstance(name, str) or not name.strip() or len(name) > 120 or
                        not isinstance(trigger, str) or len(trigger) > 200):
                    raise ValueError("Invalid LoRA name or trigger.")
                generation = options.get("generation", {})
                if (not isinstance(generation, dict) or set(generation) - {"cot", "cfg_scale", "ode_steps", "max_tokens"} or
                        generation.get("cot", "off") not in {"full", "melody", "off"}):
                    raise ValueError("Invalid generation defaults in lora.json.")
                for key, lo, hi in [("cfg_scale", 0, 20), ("ode_steps", 1, 1000), ("max_tokens", 200, 24576)]:
                    if key in generation:
                        value = generation[key]
                        if type(value) not in {int, float} or not math.isfinite(value) or not lo <= value <= hi:
                            raise ValueError("Invalid generation defaults in lora.json.")
                        if key != "cfg_scale" and type(value) is not int:
                            raise ValueError("Token and synthesis defaults must be integers.")
                training = json.loads(meta.get("training_info", "{}"))
                step = training.get("step") if isinstance(training, dict) else None
                if type(step) is not int or step < 0:
                    found = re.search(r"(?:step|checkpoint)[-_ ]?(\d+)$", path.stem, re.I)
                    step = int(found[1]) if found else None
                group = groups.setdefault(group_key, {
                    "id": hashlib.sha256(group_key.encode()).hexdigest()[:32],
                    "name": name.strip(), "kind": kind, "trigger": trigger.strip(),
                    "preferredStep": options.get("preferred_step"),
                    "generation": generation, "checkpoints": [],
                })
                checkpoint = {
                    "id": hashlib.sha256(str(relative).encode()).hexdigest()[:32],
                    "sha256": info["sha256"], "filename": str(relative), "step": step,
                    "label": f"Step {step:,}" if step is not None else path.stem,
                    "experts": info["experts"],
                }
                # The exporter marks native-base adapters in hash-checked metadata.
                # Legacy Toolkit exports keep the server's configured route.
                if meta.get("sound_vision_inference_engine") == "native":
                    checkpoint["inference_engine"] = "native"
                group["checkpoints"].append(checkpoint)
            except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
                issues.append({"filename": str(relative), "message": str(exc)})
        for group in groups.values():
            group["checkpoints"].sort(key=lambda c: (c["step"] is None, c["step"] or 0, c["filename"]))
        return {"folder": str(self.root), "groups": sorted(groups.values(), key=lambda g: (g["kind"], g["name"].casefold())), "issues": issues}

    def resolve(self, selection):
        for group in self.scan()["groups"]:
            for checkpoint in group["checkpoints"]:
                if checkpoint["id"] == selection["id"]:
                    if checkpoint["sha256"] != selection["sha256"]:
                        raise ValueError("This LoRA file changed. Refresh and select the checkpoint again.")
                    return {**checkpoint, "name": group["name"], "kind": group["kind"],
                            "trigger": group["trigger"], "strength": selection["strength"]}
        raise ValueError("Selected LoRA is unavailable or incompatible. Restore it or select another checkpoint.")

    def path_for(self, selection):
        current = self.resolve(selection)
        return str(self.root / current["filename"])


def triggered_style(style, trigger):
    if not trigger or re.search(r"(?<!\w)" + re.escape(trigger) + r"(?!\w)", style, re.I):
        return style
    return f"{trigger}, {style}"


def target_weights(prefix):
    match = PAIR.fullmatch(prefix)
    if not match:
        raise ValueError("Unsupported YuE2 adapter layer.")
    expert, layer, projection = match.groups()
    family, name = projection.split(".")
    base = f"model.layers.{layer}.{'nar_' if expert == 'diffusion_model' else ''}{family}."
    if name == "qkv_proj":
        return [(base + "q_proj.weight", 2048), (base + "k_proj.weight", 1024), (base + "v_proj.weight", 1024)]
    if name == "gate_up_proj":
        return [(base + "gate_proj.weight", 6144), (base + "up_proj.weight", 6144)]
    return [(base + name + ".weight", SHAPES[name][0])]


def merge_adapter(model, path, expected_sha, strength):
    """Merge only in process memory, before CUDA graph capture; never save base weights."""
    import torch
    from safetensors import safe_open

    if not math.isfinite(strength) or not 0.1 <= strength <= 2:
        raise ValueError("LoRA strength must be between 0.1 and 2.")
    stamp = fingerprint(path)
    if sha256(path) != expected_sha:
        raise ValueError("LoRA file changed after submission; refusing a different checkpoint.")
    header, _ = read_header(path)
    pairs, experts = adapter_pairs(header)
    operations = []
    with safe_open(path, framework="pt", device="cpu") as source:
        # Validate every tensor and every target before changing any model weights.
        for prefix in pairs:
            a, b = source.get_tensor(prefix + ".lora_A.weight"), source.get_tensor(prefix + ".lora_B.weight")
            alpha = float(source.get_tensor(prefix + ".alpha").item()) if prefix + ".alpha" in header else a.shape[0]
            if not math.isfinite(alpha) or alpha <= 0 or not torch.isfinite(a).all() or not torch.isfinite(b).all():
                raise ValueError("LoRA contains non-finite weights or invalid alpha.")
            offset = 0
            for target, rows in target_weights(prefix):
                weight = model.get_parameter(target)
                if list(weight.shape) != [rows, a.shape[1]]:
                    raise ValueError(f"LoRA does not match the installed model: {target}")
                operations.append((weight, a, b[offset:offset + rows], strength * alpha / a.shape[0]))
                offset += rows
        if fingerprint(path) != stamp:
            raise ValueError("LoRA file changed while loading.")
        with torch.no_grad():
            for weight, a, b, scale in operations:
                delta = b.to(device=weight.device, dtype=torch.float32) @ a.to(device=weight.device, dtype=torch.float32)
                weight.copy_((weight.float() + delta * scale).to(weight.dtype))
    return {"sha256": expected_sha, "strength": strength, "experts": experts,
            "adapter_modules": len(pairs), "model_weights_updated": len(operations),
            "format": "yue2-ai-toolkit-peft", "merge": "in-memory-float32-into-bfloat16"}
