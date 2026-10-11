"""One FL YuE2 checkpoint as an app influence: FL saves split projections (q, k, v; gate, up) as
lora_down/lora_up pairs, for the singer (AR) and, when trained, the sound (NAR, plus full-weight
changes to its latent projections). ComfyUI's YuE2 fuses those projections (qkv_proj, gate_up_proj),
so each group becomes one LoRA:

- shared down-projection (FL's native layout): A = down, B = the ups stacked (rank r);
- separate down-projections (FL's standard layout): A = the downs stacked, B = the ups block-diagonal
  (rank n*r). Either way B @ A is exactly the stacked per-projection updates.

FL applies B @ A at scale 1, so alpha is set to the rank. Every source tensor is consumed or it fails, and the fused
product is checked against FL's own before it's saved (in bf16, the precision ComfyUI applies it in).

    python convert.py --ar step-000500.safetensors [--nar step-000500-nar.safetensors] --out x.safetensors \
        [--meta '{"trigger": "sv_x", ...}']

Runs on the CPU with the listen venv (torch + safetensors). Prints one JSON line.
"""

import argparse
import json
import os
from pathlib import Path

import torch
from safetensors import safe_open
from safetensors.torch import save_file

LAYERS = 28
GROUPS = [("self_attn", "qkv_proj", ("q_proj", "k_proj", "v_proj")),
          ("self_attn", "o_proj", ("o_proj",)),
          ("mlp", "gate_up_proj", ("gate_proj", "up_proj")),
          ("mlp", "down_proj", ("down_proj",))]
DIFFS = ("llm2vae", "vae2llm")


def fuse(downs: list[torch.Tensor], ups: list[torch.Tensor]) -> tuple[torch.Tensor, torch.Tensor]:
    if all(torch.equal(downs[0], d) for d in downs[1:]):
        return downs[0], torch.cat(ups, 0)
    return torch.cat(downs, 0), torch.block_diag(*ups)


def branch(path: Path, expert: str, nar: bool, out: dict) -> int:
    consumed: set[str] = set()
    with safe_open(str(path), framework="pt", device="cpu") as src:
        keys = set(src.keys())
        for layer in range(LAYERS):
            for family, fused, split in GROUPS:
                names = [f"model.layers.{layer}.{'nar_' if nar else ''}{family}.{p}" for p in split]
                if not all(n + ".lora_down.weight" in keys for n in names):
                    continue
                downs = [src.get_tensor(n + ".lora_down.weight").float() for n in names]
                ups = [src.get_tensor(n + ".lora_up.weight").float() for n in names]
                a, b = fuse(downs, ups)
                assert b.shape[1] == a.shape[0] and all(torch.isfinite(t).all() for t in (a, b))
                key = f"{expert}.model.layers.{layer}.{family}.{fused}"
                out[key + ".lora_A.weight"] = a.contiguous()
                out[key + ".lora_B.weight"] = b.contiguous()
                out[key + ".alpha"] = torch.tensor(float(a.shape[0]))
                consumed.update(n + s for n in names for s in (".lora_down.weight", ".lora_up.weight"))
        if nar:
            for module in DIFFS:
                for suffix in (".diff", ".diff_b"):
                    if module + suffix in keys:
                        out[f"{expert}.{module}{suffix}"] = src.get_tensor(module + suffix).float().contiguous()
                        consumed.add(module + suffix)
        left = keys - consumed
        assert not left, f"{path.name}: {len(left)} tensors not mapped, e.g. {sorted(left)[:3]}"
    return len(consumed)


def check(out: dict, sources: list[tuple[Path, str, bool]]) -> None:
    """Rebuild every source projection's B @ A from the fused tensors and compare."""
    for path, expert, nar in sources:
        with safe_open(str(path), framework="pt", device="cpu") as src:
            for layer in (0, LAYERS // 2, LAYERS - 1):
                for family, fused, split in GROUPS:
                    key = f"{expert}.model.layers.{layer}.{family}.{fused}"
                    if key + ".lora_A.weight" not in out:
                        continue
                    whole = out[key + ".lora_B.weight"] @ out[key + ".lora_A.weight"]
                    row = 0
                    for p in split:
                        n = f"model.layers.{layer}.{'nar_' if nar else ''}{family}.{p}"
                        want = src.get_tensor(n + ".lora_up.weight").float() @ src.get_tensor(n + ".lora_down.weight").float()
                        got = whole[row:row + want.shape[0]]
                        assert torch.allclose(got, want, atol=1e-6, rtol=1e-4), f"{key}/{p} differs"
                        row += want.shape[0]
                    assert row == whole.shape[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ar", required=True, type=Path)
    ap.add_argument("--nar", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--meta", default="{}")
    a = ap.parse_args()
    torch.set_num_threads(4)
    out: dict[str, torch.Tensor] = {}
    sources = [(a.ar, "text_encoders", False)] + ([(a.nar, "diffusion_model", True)] if a.nar else [])
    counts = {expert: branch(path, expert, nar, out) for path, expert, nar in sources}
    check(out, sources)
    extra = json.loads(a.meta)
    meta = {"format": "sound-vision-yue2-v2", "source_ar": a.ar.name, "source_nar": a.nar.name if a.nar else "",
            **{k: v if isinstance(v, str) else json.dumps(v) for k, v in extra.items()}}
    if extra.get("trigger"):
        meta["ss_tag_frequency"] = json.dumps({"training": {extra["trigger"]: 1}})
    a.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = a.out.with_suffix(".tmp")
    # checked above at full precision; stored as bf16 (the precision ComfyUI applies them in), half the size
    save_file({k: v if k.endswith(".alpha") else v.to(torch.bfloat16) for k, v in out.items()}, str(tmp), metadata=meta)
    os.replace(tmp, a.out)
    a.out.chmod(0o644)
    print(json.dumps({"out": str(a.out), "tensors": len(out), "sourceTensors": counts, "bytes": a.out.stat().st_size,
                      "ranks": sorted({int(t.shape[0]) for k, t in out.items() if k.endswith("lora_A.weight")})}))


if __name__ == "__main__":
    main()
