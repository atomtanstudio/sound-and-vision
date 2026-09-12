"""Public downloads only; pins the custom code and its parent encoder."""

import argparse, json
from pathlib import Path
from huggingface_hub import snapshot_download

p = argparse.ArgumentParser()
p.add_argument("--models", type=Path, required=True)
args = p.parse_args()
pins = {
    "SheetSage2": "eab522a8168e8b8b8c4856bf8609cd86198f01fe",
    "MERT-v2-FullSong": "d8ba1c745e733b3908ce6ad16ebeb17ac7600a42",
}
rows = {}
for name, revision in pins.items():
    path = snapshot_download(
        "m-a-p/" + name,
        revision=revision,
        token=False,
        cache_dir=args.models / "hf-cache",
        allow_patterns=["*.py", "*.json", "*.md", "*.txt", "LICENSE", "*.safetensors"],
    )
    rows[name] = {"revision": revision, "path": path}
(args.models / "reference.lock.json").write_text(json.dumps(rows, indent=2) + "\n")
print(json.dumps(rows, indent=2))
