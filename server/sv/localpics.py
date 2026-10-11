"""Pictures made on this machine's GPU by our ComfyUI: every image model the app knows how to run, offered when the
ComfyUI has its files. A picture choice is "local" (Krea 2, as it always was) or "local:<id>".

- Krea 2 Turbo: 8 steps, CFG 1, no reference pictures.
- Qwen Image 2.1 Turbo (the int8 build): the person's own recipe from their workflow (qwenImage21TurboBasic_v10,
  2026-10-09): Euler, CFG 1 and its 8 fixed sigmas, at about 2 megapixels. It takes reference pictures: they go to its
  text encoder (TextEncodeQwenImage21's images, with the VAE), so a person or place can stay the same.

Which models are there is asked of the ComfyUI (its model folders), at most once a minute."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable

KREA_SIZES = {"16:9": (1344, 768), "1:1": (1280, 1280), "9:16": (768, 1344), "4:5": (1024, 1280), "3:2": (1344, 896)}
QWEN_SIGMAS = "1.0, 0.978453, 0.95418, 0.926626, 0.89508, 0.845148, 0.704534, 0.414568, 0.0"


@dataclass(frozen=True)
class Model:
    key: str
    name: str
    files: dict[str, str]  # ComfyUI folder → file
    refs: int  # how many reference pictures it takes (0: none)
    graph: Callable[..., dict]
    sampler: str  # the node whose progress is the picture's
    out: str  # the node the picture comes out of
    sizes: dict[str, tuple[int, int]] = field(default_factory=dict)

    @property
    def engine(self) -> str:
        return "local" if self.key == "krea2" else f"local:{self.key}"

    def size(self, shape: str) -> tuple[int, int]:
        """Its size for a shape ("16:9", "1:1", …): its own table, else about 2 megapixels at multiples of 32."""
        if shape in self.sizes:
            return self.sizes[shape]
        w, h = (int(x) for x in (shape.split(":") if ":" in shape else ("1", "1")))
        side = math.sqrt(2_000_000 / (w * h))
        return int(round(w * side / 32) * 32), int(round(h * side / 32) * 32)


def krea_graph(prompt: str, width: int, height: int, seed: int, prefix: str, refs: list[str] | None = None) -> dict:
    """Krea 2 Turbo: one picture. The sampler is node 8, the picture comes out of node 10."""
    f = MODELS["krea2"].files
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": f["diffusion_models"], "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": f["text_encoders"], "type": "krea2", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": f["vae"]}},
        "4": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3.0}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "6": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["5", 0]}},
        "7": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "8": {"class_type": "KSampler", "inputs": {"model": ["4", 0], "positive": ["5", 0], "negative": ["6", 0],
                                                   "latent_image": ["7", 0], "seed": seed, "steps": 8, "cfg": 1.0,
                                                   "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": prefix}},
    }


def qwen21_graph(prompt: str, width: int, height: int, seed: int, prefix: str, refs: list[str] | None = None) -> dict:
    """Qwen Image 2.1 Turbo: one picture, from up to 16 reference pictures already uploaded to the ComfyUI (their
    names). The sampler is node 10, the picture comes out of node 12."""
    f = MODELS["qwen21"].files
    g: dict[str, Any] = {
        "4": {"class_type": "UNETLoader", "inputs": {"unet_name": f["diffusion_models"], "weight_dtype": "default"}},
        "6": {"class_type": "QwenImage21Cache", "inputs": {"model": ["4", 0], "device": "auto", "dtype": "default"}},
        "7": {"class_type": "CLIPLoader", "inputs": {"clip_name": f["text_encoders"], "type": "qwen_image", "device": "default"}},
        "8": {"class_type": "VAELoader", "inputs": {"vae_name": f["vae"]}},
        "3": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "9": {"class_type": "TextEncodeQwenImage21", "inputs": {"clip": ["7", 0], "prompt": prompt, "negative_prompt": "",
                                                                 "resolution": 1024}},
        "14": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "15": {"class_type": "ManualSigmas", "inputs": {"sigmas": QWEN_SIGMAS}},
        "10": {"class_type": "SamplerCustom", "inputs": {"model": ["6", 0], "positive": ["9", 0], "negative": ["9", 1],
                                                         "sampler": ["14", 0], "sigmas": ["15", 0], "latent_image": ["3", 0],
                                                         "add_noise": True, "noise_seed": seed, "cfg": 1.0}},
        "11": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["8", 0]}},
        "12": {"class_type": "SaveImage", "inputs": {"images": ["11", 0], "filename_prefix": prefix}},
    }
    for i, name in enumerate((refs or [])[:16], start=1):
        g[f"r{i}"] = {"class_type": "LoadImage", "inputs": {"image": name}}
        g["9"]["inputs"][f"images.image_{i}"] = [f"r{i}", 0]
    if refs:
        g["9"]["inputs"]["vae"] = ["8", 0]
    return g


MODELS: dict[str, Model] = {
    "krea2": Model("krea2", "Krea 2", {"diffusion_models": "krea2_turbo_fp8_scaled.safetensors",
                                       "text_encoders": "qwen3vl_4b_fp8_scaled.safetensors", "vae": "wan_2.1_vae.safetensors"},
                   0, krea_graph, "8", "10", KREA_SIZES),
    "qwen21": Model("qwen21", "Qwen Image 2.1", {"diffusion_models": "qwen_image_2.1_turbo_int8_convrot.safetensors",
                                                "text_encoders": "qwen3vl_8b_int8_convrot.safetensors",
                                                "vae": "qwen_image_2.1_vae_bf16.safetensors"},
                    16, qwen21_graph, "10", "12"),
}
ALIAS = {"diffusion_models": ("diffusion_models", "unet"), "text_encoders": ("text_encoders", "clip"), "vae": ("vae",)}


def of(engine: str) -> Model:
    """The model a picture choice names ("local" is Krea 2)."""
    key = engine.split(":", 1)[1] if engine.startswith("local:") else "krea2"
    return MODELS.get(key, MODELS["krea2"])


def engines() -> list[str]:
    return [m.engine for m in MODELS.values()]


class Available:
    """Which of MODELS the ComfyUI has every file of, asked at most once a minute (a ComfyUI that doesn't answer:
    as last known, Krea 2 at first)."""

    def __init__(self) -> None:
        self.keys: set[str] = {"krea2"}
        self.at = 0.0

    async def check(self, comfy: Any) -> set[str]:
        if comfy is None or time.monotonic() - self.at < 60:
            return self.keys
        have: dict[str, set[str]] = {}
        for folder in {f for names in ALIAS.values() for f in names}:
            try:
                have[folder] = set(await comfy.models(folder))
            except Exception:  # noqa: BLE001 (a folder this ComfyUI doesn't list by that name)
                continue
        if not have:  # ComfyUI not answering: keep what was known
            return self.keys
        self.keys = {m.key for m in MODELS.values()
                     if all(any(file in have.get(f, set()) for f in ALIAS[kind]) for kind, file in m.files.items())}
        self.at = time.monotonic()
        return self.keys
