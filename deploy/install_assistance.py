"""Install isolated, pinned account and reference runtimes on the service host."""

import argparse, hashlib, json, os, subprocess, tarfile, urllib.request
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--root", type=Path, required=True)
p.add_argument("--models", type=Path, required=True)
p.add_argument("--skip-openai", action="store_true", help="Install only reference transcription for a local-provider setup")
args = p.parse_args()
root = args.root.resolve()
if not args.skip_openai:
    lock = json.loads((Path(__file__).parent / "openai-runtime.lock.json").read_text())
    (root / "bin").mkdir(exist_ok=True)
    archive = root / "codex-runtime.tar.gz"
    urllib.request.urlretrieve(lock["url"], archive)
    if "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest() != lock["digest"]:
        raise RuntimeError("Codex runtime checksum mismatch; installation stopped.")
    runtime = root / "runtimes" / ("codex-" + lock["version"].removeprefix("rust-v"))
    runtime.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as tar:
        tar.extractall(runtime, filter="data")
    link = root / "bin/codex.next"
    link.unlink(missing_ok=True)
    link.symlink_to(runtime / "bin/codex")
    os.replace(link, root / "bin/codex")
    archive.unlink()
    subprocess.run([root / "bin/codex", "--version"], check=True)
    node_lock = json.loads((Path(__file__).parent / "node-runtime.lock.json").read_text())
    node_archive = root / "node-runtime.tar.xz"
    urllib.request.urlretrieve(node_lock["url"], node_archive)
    if hashlib.sha256(node_archive.read_bytes()).hexdigest() != node_lock["sha256"]:
        raise RuntimeError("Node runtime checksum mismatch; installation stopped.")
    with tarfile.open(node_archive) as tar:
        member = next(
            m for m in tar.getmembers() if m.isfile() and m.name.endswith("/bin/node")
        )
        (root / "bin/node").write_bytes(tar.extractfile(member).read())
    (root / "bin/node").chmod(0o700)
    node_archive.unlink()

uv = Path.home() / ".local/bin/uv"
env = {
    **os.environ,
    "UV_PYTHON_INSTALL_DIR": str(root / "python"),
    "UV_CACHE_DIR": str(root / "uv-cache"),
}
subprocess.run(
    [uv, "venv", "--python", "3.11.16", str(root / ".venv-reference")],
    env=env,
    check=True,
)
python = root / ".venv-reference/bin/python"
subprocess.run(
    [
        uv,
        "pip",
        "install",
        "--python",
        python,
        "torch==2.8.0",
        "torchaudio==2.8.0",
        "--index-url",
        "https://download.pytorch.org/whl/cu128",
    ],
    env=env,
    check=True,
)
subprocess.run(
    [
        uv,
        "pip",
        "install",
        "--python",
        python,
        "transformers==4.45.2",
        "huggingface-hub==0.36.0",
        "safetensors==0.5.3",
        "numpy==1.24.3",
        "scipy==1.13.1",
        "mir_eval==0.8.2",
        "pretty_midi==0.2.10",
        "mido==1.3.3",
        "setuptools==78.1.1",
        "soundfile==0.13.1",
    ],
    env=env,
    check=True,
)
subprocess.run(
    [
        root / ".venv/bin/python",
        Path(__file__).parent / "download_reference.py",
        "--models",
        args.models,
    ],
    env={**env, "HF_HUB_OFFLINE": "0"},
    check=True,
)
print("Reference transcriber installed." if args.skip_openai else "Isolated account runtime and reference transcriber installed.")
