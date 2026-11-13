"""The model files in scripts/models.txt, with their sizes, so a job stops before ComfyUI loads one that a stopped
download left cut short: ComfyUI can fail on such a file, or hang the machine reading it. Only files models.txt lists
and that are found where it says are checked; anything else is left to ComfyUI. With no models.txt, nothing is.
"""
from pathlib import Path

from .config import ROOT

MANIFEST = ROOT / "scripts" / "models.txt"


class ModelFiles:
    def __init__(self, models: Path, loras: Path, manifest: Path = MANIFEST):
        # the name a graph uses (the path under its folder, e.g. "ace_step_1.5/x.safetensors") -> (places, bytes, set)
        self.files: dict[str, tuple[list[Path], int, str]] = {}
        try:
            lines = manifest.read_text().splitlines()
        except OSError:
            return
        for line in lines:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            group, rel, _src, _sha, size = line.split("|")
            folder, name = rel.split("/", 1)
            if folder == "loras":
                places = [loras / name]
            else:
                places = [models / "comfyui" / rel]
                alt = {"text_encoders": "clip", "diffusion_models": "unet"}.get(folder)
                if alt:
                    places.append(models / "comfyui" / alt / name)
            self.files[name] = (places, int(size), group)

    def problems(self, graph: dict) -> list[str]:
        """Plain-language problems with the model files this graph loads (empty = none found)."""
        out: list[str] = []
        for node in graph.values():
            for value in (node.get("inputs") or {}).values():
                if not isinstance(value, str):
                    continue
                hit = self.files.get(value.replace("\\", "/"))
                if not hit:
                    continue
                places, want, group = hit
                place = next((p for p in places if p.is_file()), None)
                if place is None:
                    continue
                have = place.stat().st_size
                if have != want:
                    msg = (f"{place.name} is {have / 1e9:.1f} of {want / 1e9:.1f} GB, so it's cut short (a download that "
                           f"stopped). Run scripts/models.sh {group} to fetch the rest, then try again.")
                    if msg not in out:
                        out.append(msg)
        return out
