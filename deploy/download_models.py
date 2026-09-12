"""Download only pinned YuE2 generation/decoder files; no auxiliary models."""

import json, os
from pathlib import Path
from huggingface_hub import snapshot_download

ROOT = Path(os.environ.get("SOUND_VISION_MODELS", "/srv/ai/models/yue2"))
MODELS = {
    "YuE2-3B": ("m-a-p/YuE2-3B", "1a96eca688d6ae5d7f0feb88573fec89920fcd19"),
    "YuE2-Vae": ("m-a-p/YuE2-Vae", "95535e72a97bc0f09b8ada125d26b4009428c0e8"),
}
ROOT.mkdir(parents=True, exist_ok=True)
for name, (repo, revision) in MODELS.items():
    target = ROOT / name / revision
    print(f"Downloading {repo}@{revision}", flush=True)
    snapshot_download(
        repo_id=repo,
        revision=revision,
        local_dir=target,
        token=False,
        max_workers=4,
        allow_patterns=[
            "*.json",
            "*.safetensors",
            "*.tiktoken",
            "modeling*.py",
            "README.md",
            "LICENSE",
            "THIRD_PARTY_NOTICES.md",
            "licenses/*",
        ],
    )
    print(f"Complete: {name}", flush=True)
(ROOT / "models.lock.json").write_text(
    json.dumps(
        {
            "source_revision": "92a73cc7652fcc1f937855e4b765e0a0edd7ff2e",
            "models": {
                name: {
                    "repo": repo,
                    "revision": revision,
                    "path": str(ROOT / name / revision),
                }
                for name, (repo, revision) in MODELS.items()
            },
        },
        indent=2,
    )
    + "\n"
)
