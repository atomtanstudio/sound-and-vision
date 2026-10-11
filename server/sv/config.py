"""Where everything is. Every value can be set with an SV_* environment variable, usually from the install's sv.env
(see sv.env.example at the top of the repo). The defaults suit one GPU machine running everything, with the data and
the models in folders next to the code."""

from __future__ import annotations

import ipaddress
import os
import socket
import secrets
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # the repo


def _p(name: str, default: Path | str) -> Path:
    return Path(os.environ.get(name) or default).expanduser()


def _list(name: str, default: str = "") -> tuple[str, ...]:
    return tuple(u.strip() for u in (os.environ.get(name, default)).split(",") if u.strip())


@dataclass(frozen=True)
class Config:
    data: Path
    web: Path | None
    machine: str  # what the interface calls the GPU machine ("Legion", "the server")
    # devices on these networks use the app without pairing (a home network); everyone else needs the key
    open_networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]
    hosts: tuple[str, ...]  # names the app answers to besides IP addresses, localhost and the machine's own name
    comfy: str
    other_comfys: tuple[str, ...]
    free_others: bool
    loras: Path
    analysis_image: str
    analysis_worker: Path
    analysis_models: Path
    whisper: Path  # faster-whisper large-v3 (a Hugging Face model folder: snapshots/ link into blobs/)
    ffmpeg: str
    grok_bin: Path
    codex_bin: Path  # OpenAI's Codex CLI, for "Sign in with ChatGPT"
    codex_path: tuple[Path, ...]  # folders it needs on PATH (its Node), if they aren't already
    studio_sh: Path
    ollama: str
    # the Influence Engine: FL YuE2's trainer (its own ComfyUI), MOSS-Music, and where your own music is
    trainer: str
    trainer_container: str
    trainer_root: Path
    listen_python: Path
    influence_tools: Path
    mitte: bool  # the owner's own picture service through their Claude account (SV_MITTE=1); off for everyone else
    music: str  # a folder of your music (Artist/…/Song.flac), or smb://host/share/path; empty: you add songs by hand
    # VRGameDevGirl's Video Builder (her ComfyUI pack and its H3 film skill) in its own ComfyUI container, for music
    # videos with people singing: the films folder as the host sees it and as the container does
    vrgdg_box: str
    vrgdg_python: str
    vrgdg_skill: str
    vrgdg_films: Path
    vrgdg_films_in: str
    vrgdg_url: str

    @property
    def projects(self) -> Path:
        return self.data / "projects"

    @property
    def db(self) -> Path:
        return self.data / "sv.db"

    def token(self) -> str:
        """The app's key: paired browsers carry it as a cookie, the dev proxy as a bearer header."""
        f = self.data / "secrets" / "api-token"
        if not f.exists():
            f.parent.mkdir(parents=True, exist_ok=True)
            f.parent.chmod(0o700)
            f.write_text(secrets.token_urlsafe(32))
            f.chmod(0o600)
        return f.read_text().strip()

    def open_to(self, host: str | None) -> bool:
        """Whether a device at this address may use the app without the key."""
        try:
            addr = ipaddress.ip_address(host or "")
        except ValueError:
            return False
        return any(addr in net for net in self.open_networks)


def networks(text: str) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    out = []
    for part in text.split(","):
        if part.strip():
            try:
                out.append(ipaddress.ip_network(part.strip(), strict=False))
            except ValueError:
                raise SystemExit(f"SV_OPEN_NETWORKS: {part.strip()!r} isn't a network (try 192.168.1.0/24)") from None
    return tuple(out)


def own_name() -> str:
    """What the interface calls this machine when SV_MACHINE doesn't say: its own name (its hostname, without a
    domain), or "the server" when it has none worth showing."""
    name = socket.gethostname().split(".")[0].strip()
    return name if name and name.lower() not in ("localhost", "localhost-localdomain", "ubuntu", "debian") else "the server"


def load() -> Config:
    data = _p("SV_DATA", ROOT / "data")
    models = _p("SV_MODELS", ROOT / "models")
    web = _p("SV_WEB", ROOT / "web" / "dist")
    comfy = os.environ.get("SV_COMFY", "http://127.0.0.1:8210")
    return Config(
        data=data,
        web=web if (web / "index.html").is_file() else None,
        machine=os.environ.get("SV_MACHINE") or own_name(),
        open_networks=networks(os.environ.get("SV_OPEN_NETWORKS", "")),
        hosts=_list("SV_HOSTS"),
        comfy=comfy,
        other_comfys=_list("SV_OTHER_COMFYS"),
        # other ComfyUIs on the machine may be asked to unload idle models before a big job
        free_others=os.environ.get("SV_FREE_OTHERS", "1") == "1",
        loras=_p("SV_LORAS", models / "comfyui" / "loras"),
        analysis_image=os.environ.get("SV_ANALYSIS_IMAGE", "sv-analysis:latest"),
        analysis_worker=_p("SV_ANALYSIS_WORKER", ROOT / "infra" / "legion" / "analysis" / "worker"),
        analysis_models=_p("SV_ANALYSIS_MODELS", models / "audio-separation" / "sv"),
        whisper=_p("SV_WHISPER", models / "huggingface" / "models--Systran--faster-whisper-large-v3"),
        ffmpeg=os.environ.get("SV_FFMPEG", "ffmpeg"),
        grok_bin=_p("SV_GROK_BIN", "grok"),
        codex_bin=_p("SV_CODEX_BIN", "codex"),
        codex_path=tuple(Path(d).expanduser() for d in _list("SV_CODEX_PATH")),
        studio_sh=_p("SV_STUDIO_SH", ROOT / "infra" / "studio" / "studio.sh"),
        ollama=os.environ.get("SV_OLLAMA", "http://127.0.0.1:11434"),
        trainer=os.environ.get("SV_TRAINER", "http://127.0.0.1:8196"),
        trainer_container=os.environ.get("SV_TRAINER_CONTAINER", "ai-comfy-fl-yue2"),
        trainer_root=_p("SV_TRAINER_ROOT", data / "trainer"),
        listen_python=_p("SV_LISTEN_PYTHON", data / "listen" / "venv" / "bin" / "python"),
        influence_tools=_p("SV_INFLUENCE_TOOLS", ROOT / "infra" / "legion" / "influence"),
        mitte=os.environ.get("SV_MITTE") == "1",
        music=os.environ.get("SV_MUSIC", ""),
        vrgdg_box=os.environ.get("SV_VRGDG_BOX", "ai-comfy-vrgdg"),
        vrgdg_python=os.environ.get("SV_VRGDG_PYTHON", "/opt/venv/bin/python"),
        vrgdg_skill=os.environ.get("SV_VRGDG_SKILL", "/vrgdg/profile/claude/vrgdg-h3-film"),
        vrgdg_films=_p("SV_VRGDG_FILMS", data / "video-builder" / "output" / "films"),
        vrgdg_films_in=os.environ.get("SV_VRGDG_FILMS_IN", "/vrgdg/profile/output/films"),
        vrgdg_url=os.environ.get("SV_VRGDG_URL", "http://127.0.0.1:8199"),
    )
