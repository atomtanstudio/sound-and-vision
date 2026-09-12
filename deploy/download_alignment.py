"""Download and lock the isolated CPU alignment models; never touches YuE2/H3."""

import hashlib, json, os
from pathlib import Path
from huggingface_hub import HfApi, snapshot_download

root = Path("/srv/ai/sound-vision")
models = root / "alignment-models"
models.mkdir(exist_ok=True)
os.environ["TORCH_HOME"] = str(models / "torch")
lock_path = root / "alignment.lock.json"
previous = json.loads(lock_path.read_text()) if lock_path.exists() else {}
repo = "Systran/faster-whisper-large-v3"
revision = previous.get("revision") or HfApi().model_info(repo).sha
snapshot = snapshot_download(
    repo,
    revision=revision,
    cache_dir=models / "huggingface",
    allow_patterns=["*.json", "*.bin", "*.txt"],
)
from demucs.pretrained import get_model

model = get_model("htdemucs")
import torchaudio

torchaudio.pipelines.WAV2VEC2_ASR_LARGE_LV60K_960H.get_model()
files = list((models / "torch/hub/checkpoints").glob("*"))
lock = {
    "repo": repo,
    "revision": revision,
    "path": snapshot,
    "demucs": "htdemucs",
    "demucsFiles": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
    "englishCTC": "WAV2VEC2_ASR_LARGE_LV60K_960H",
    "device": "cpu",
    "computeType": "int8",
    "stableTs": "2.19.1",
    "fasterWhisper": "1.2.1",
}
lock_path.write_text(json.dumps(lock, indent=2) + "\n")
print(json.dumps(lock, indent=2))
