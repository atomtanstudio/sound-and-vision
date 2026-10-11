"""Capabilities as ComfyUI API graphs plus a binding.

Each file in workflows/ is one capability (song.yue2, song.ace15, ...):

    {
      "id": "song.ace15", "title": "...", "model": "ace15",
      "params": {"style": {"to": [["enc", "tags"]], "type": "str"}, "seconds": {...}, ...},
      "influences": {"model": ["unet", 0], "clip": ["clip", 0]},   # optional: where LoRAs chain in
      "outputs": {"audio": "save"},
      "graph": { ...ComfyUI API prompt... }
    }

bind() fills a copy of the graph from plain parameters; check() compares every graph
with the live instance's /object_info and says, in plain words, what is missing.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent / "workflows"
TYPES = {"str": str, "int": int, "float": (int, float), "bool": bool}


class BindError(ValueError):
    pass


@dataclass(frozen=True)
class Influence:
    """A LoRA, as the app calls it. `file` is relative to ComfyUI's loras folder."""

    file: str
    strength: float


@dataclass
class Workflow:
    id: str
    title: str
    model: str | None
    params: dict[str, dict]
    graph: dict[str, dict]
    outputs: dict[str, str]
    influences: dict[str, list] | None = None

    @classmethod
    def load(cls, path: Path) -> "Workflow":
        d = json.loads(path.read_text())
        return cls(d["id"], d.get("title", d["id"]), d.get("model"), d.get("params", {}), d["graph"],
                   d.get("outputs", {}), d.get("influences"))

    def bind(self, values: dict[str, Any], *, influences: list[Influence] = (), prefix: str | None = None) -> dict:
        unknown = set(values) - set(self.params)
        if unknown:
            raise BindError(f"{self.title} doesn't take {', '.join(sorted(unknown))}.")
        g = copy.deepcopy(self.graph)
        for name, spec in self.params.items():
            if name in values and values[name] is not None:
                v = values[name]
            elif "default" in spec:
                v = spec["default"]
            elif spec.get("required", True):
                raise BindError(f"{self.title} needs '{name}'.")
            else:
                continue
            want = TYPES[spec.get("type", "str")]
            if spec.get("type") == "float" and isinstance(v, int) and not isinstance(v, bool):
                v = float(v)
            if not isinstance(v, want) or (spec.get("type") in ("int", "float") and isinstance(v, bool)):
                raise BindError(f"'{name}' should be {spec.get('type', 'str')}, got {type(v).__name__}.")
            if "min" in spec and v < spec["min"] or "max" in spec and v > spec["max"]:
                raise BindError(f"'{name}' must be between {spec.get('min')} and {spec.get('max')}.")
            if "choices" in spec and v not in spec["choices"]:
                raise BindError(f"'{name}' must be one of {', '.join(map(str, spec['choices']))}.")
            for node, field in spec["to"]:
                g[node]["inputs"][field] = v
        if influences:
            if not self.influences:
                raise BindError(f"{self.title} can't take influences.")
            chain(g, influences, self.influences["model"], self.influences.get("clip"))
        if prefix:
            for node in self.outputs.values():
                if "filename_prefix" in g[node]["inputs"]:
                    g[node]["inputs"]["filename_prefix"] = prefix
        return g


def chain(g: dict, influences: list[Influence], model_src: list, clip_src: list | None) -> None:
    """Insert one LoraLoader per influence after the node that makes MODEL (and CLIP), and
    point everything that used those outputs at the end of the chain."""
    model_ref, clip_ref = list(model_src), list(clip_src) if clip_src else None
    users = [(nid, k) for nid, n in g.items() for k, v in n["inputs"].items() if v == list(model_src)]
    clip_users = [(nid, k) for nid, n in g.items() for k, v in n["inputs"].items()
                  if clip_src and v == list(clip_src)]
    for i, inf in enumerate(influences):
        nid = f"sv_influence_{i}"
        if clip_ref:
            g[nid] = {"class_type": "LoraLoader", "inputs": {
                "model": model_ref, "clip": clip_ref, "lora_name": inf.file,
                "strength_model": inf.strength, "strength_clip": inf.strength}}
            model_ref, clip_ref = [nid, 0], [nid, 1]
        else:
            g[nid] = {"class_type": "LoraLoaderModelOnly", "inputs": {
                "model": model_ref, "lora_name": inf.file, "strength_model": inf.strength}}
            model_ref = [nid, 0]
    for nid, k in users:
        g[nid]["inputs"][k] = model_ref
    for nid, k in clip_users:
        g[nid]["inputs"][k] = clip_ref


class Registry:
    def __init__(self, folder: Path = HERE):
        self.workflows = {w.id: w for w in (Workflow.load(p) for p in sorted(folder.glob("*.json")))}

    def __getitem__(self, wid: str) -> Workflow:
        return self.workflows[wid]

    def check(self, object_info: dict) -> dict[str, list[str]]:
        """{workflow id: [problems]} against a live /object_info. Empty list = ready."""
        report: dict[str, list[str]] = {}
        for w in self.workflows.values():
            problems: list[str] = []
            for nid, node in w.graph.items():
                ct = node["class_type"]
                info = object_info.get(ct)
                if info is None:
                    problems.append(f"ComfyUI has no '{ct}' node.")
                    continue
                spec = {**info["input"].get("required", {}), **info["input"].get("optional", {})}
                for field, value in node["inputs"].items():
                    if isinstance(value, list) or field not in spec:
                        continue
                    allowed = spec[field][0] if isinstance(spec[field][0], list) else \
                        (spec[field][1] or {}).get("options") if len(spec[field]) > 1 and isinstance(spec[field][1], dict) else None
                    if allowed and value not in allowed and field.endswith(("_name", "name1", "name2")):
                        problems.append(f"'{value}' isn't installed (needed by {ct}).")
            report[w.id] = problems
        return report
