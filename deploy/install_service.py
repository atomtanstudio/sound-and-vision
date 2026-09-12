"""Run as the service owner, after installing the isolated runtime and models."""

import argparse, json, os, secrets, subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--root", type=Path, required=True)
parser.add_argument("--models", type=Path, required=True)
parser.add_argument("--comfy-urls", default="")
args = parser.parse_args()
root = args.root.resolve()
models = json.loads((args.models / "models.lock.json").read_text())["models"]
root.mkdir(parents=True, exist_ok=True)
os.chmod(root, 0o700)
token = root / "service.token"
if not token.exists():
    token.write_text(secrets.token_hex(32) + "\n")
os.chmod(token, 0o600)
env = {
    "SOUND_VISION_TOKEN_FILE": str(token),
    "SOUND_VISION_DATA": str(root / "data"),
    "SOUND_VISION_MODEL": models["YuE2-3B"]["path"],
    "SOUND_VISION_VAE": models["YuE2-Vae"]["path"],
    "SOUND_VISION_COMFY_URLS": args.comfy_urls,
    "SOUND_VISION_MIN_FREE_MIB": "23552",
    "HF_HOME": str(args.models.resolve() / "hf-cache"),
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
}
(root / "service.env").write_text(
    "".join(f"{key}={value}\n" for key, value in env.items())
)
os.chmod(root / "service.env", 0o600)
units = Path.home() / ".config/systemd/user"
units.mkdir(parents=True, exist_ok=True)
(units / "sound-vision.service").write_text(
    (root / "deploy/sound-vision.service.in").read_text().replace("@ROOT@", str(root))
)
subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
subprocess.run(
    ["systemctl", "--user", "enable", "--now", "sound-vision.service"], check=True
)
print(
    "Sound/Vision installed as a user service on127.0.0.1:5191. No other services changed."
)
