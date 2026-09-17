"""Run as the service owner, after installing the isolated runtime and models."""

import argparse, json, os, secrets, subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--root", type=Path, required=True)
parser.add_argument("--models", type=Path, required=True)
parser.add_argument("--comfy-urls", default="")
parser.add_argument("--video-comfy-urls", default="", help="Idle video renderers the app may unload after its video jobs.")
parser.add_argument("--lora-toolkit-root", type=Path, help="Optional existing AI Toolkit checkout for matched YuE2 LoRA inference.")
parser.add_argument("--lora-toolkit-python", type=Path, help="Python from that checkout's existing environment.")
parser.add_argument("--lora-toolkit-model", type=Path, help="Existing YuE2 ConvRot8 all-in-one checkpoint.")
args = parser.parse_args()
matched = [args.lora_toolkit_root, args.lora_toolkit_python, args.lora_toolkit_model]
if any(matched) and not all(matched):
    parser.error("Supply all three --lora-toolkit-* options together.")
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
    "SOUND_VISION_VIDEO_COMFY_URLS": args.video_comfy_urls,
    "SOUND_VISION_MIN_FREE_MIB": "23552",
    "HF_HOME": str(args.models.resolve() / "hf-cache"),
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
}
if all(matched):
    env.update({
        "SOUND_VISION_LORA_ENGINE": "ai-toolkit",
        "SOUND_VISION_LORA_TOOLKIT_ROOT": str(args.lora_toolkit_root.resolve()),
        "SOUND_VISION_LORA_TOOLKIT_PYTHON": str(args.lora_toolkit_python.absolute()),
        "SOUND_VISION_LORA_TOOLKIT_MODEL": str(args.lora_toolkit_model.resolve()),
    })
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
