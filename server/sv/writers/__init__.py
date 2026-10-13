"""Who does what: each kind of work goes to the provider and model the user chose for it, falling
down the list when that one isn't connected. Defaults (the user, 2026-10-09): Claude Haiku 5.5 writes lyrics and reads the Home prompt; Claude Opus directs videos. A Claude or ChatGPT step can
carry its reasoning level ("effort": none means the model's own default; Claude's are low … max, ChatGPT's are the ones
each model lists). "film" is the long Claude Code session that makes a video in code (a living cover's finish, a
Motion Graphics film, a music video); only Claude does it.

Pictures have roles too (IMAGE_ROLES): album covers, and the pictures for music videos. Each is one choice of
image_ids(): ChatGPT's own image tool (under their ChatGPT plan), Krea 2 on the local GPU, or one of the person's own
MCP servers ("mcp:<id>", which Claude uses to make the picture). An install can also turn on the owner's Mitte
(SV_MITTE=1: GPT Image 2.5, driven by Claude through the Mitte connector on their Claude account). A step that names an
MCP server can also carry the model to use there and its settings ({"model", "options"}), from the server's catalog
(sv/catalog.py); without them the server uses its own default."""

from __future__ import annotations

from typing import Any

from .. import localpics
from ..catalog import Catalogs, clean_choice, summary
from ..config import Config
from ..mcp import Servers
from ..store import Store
from . import tasks
from .openai import ChatGPT
from .providers import Claude, Grok, Local, WriterError

TASK_ROLE = {"song": "lyrics", "section": "lyrics", "titles": "lyrics", "sound": "lyrics", "match": "interpret",
             "interpret": "interpret", "cover": "chores", "research": "research", "captions": "research", "motion": "direct",
             "living": "direct"}
HAIKU, SONNET, OPUS = "claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"
DEFAULT_WHO = {
    "interpret": [{"provider": "claude", "model": HAIKU}, {"provider": "claude", "model": SONNET}, {"provider": "local", "model": None}],
    "lyrics": [{"provider": "claude", "model": HAIKU}, {"provider": "claude", "model": SONNET}, {"provider": "local", "model": None}],
    "research": [{"provider": "claude", "model": SONNET}, {"provider": "claude", "model": HAIKU}, {"provider": "local", "model": None}],
    "direct": [{"provider": "claude", "model": OPUS}, {"provider": "local", "model": None}],  # (a local-only install works too)
    "chores": [{"provider": "claude", "model": HAIKU}, {"provider": "local", "model": None}],
    "film": [{"provider": "claude", "model": OPUS, "effort": "xhigh"}],  # the user: "extra high" for videos
}
EFFORTS = ("low", "medium", "high", "xhigh", "max")
FILM_MODELS = {OPUS: "Opus 5.5", "claude-fable-5-1": "Fable 5.1", SONNET: "Sonnet 5.5"}
IMAGE_ROLES = {"covers": "Album covers", "scenes": "Pictures for music videos"}
IMAGE_DEFAULTS = {"covers": [{"provider": "local"}], "scenes": [{"provider": "local"}]}
MOTION_ROLES = {"motion": "Animating scenes (Surreal music videos)"}
MITTE_COST = 0.071  # USD a picture (GPT Image 2.5, high, 2K: Mitte's price list, 2026-10)
# Grok Imagine's models, as xAI lists them (docs.x.ai/docs/models, 2026-10-11). The Grok CLI takes the picture model
# from GROK_IMAGE_GEN_MODEL_OVERRIDE; its video tool always uses grok-imagine-video-1.5 (CLI 1.0.41).
GROK_IMAGE_DEFAULT = "grok-imagine-image-2.0"  # the user, 2026-10-11
PROVIDER_MODELS = {"grok": {
    "image": [{"id": "grok-imagine-image-2.0", "name": "Grok Imagine Image 2.0", "options": [],
               "note": "xAI's newest picture model: crisp short text, and up to three reference pictures."},
              {"id": "grok-imagine-image-quality", "name": "Grok Imagine Image Quality", "options": [],
               "note": "Its highest-fidelity model: more detail and finer control."},
              {"id": "grok-imagine-image", "name": "Grok Imagine Image", "options": [],
               "note": "The standard model: the quickest."}],
    "video": [{"id": "grok-imagine-video-1.5", "name": "Grok Imagine Video 1.5", "options": [],
               "note": "xAI's newest video model, from a still picture."}]}}
ROLE_LABELS = {"interpret": "Reading the Home prompt", "lyrics": "Lyrics, titles and rewrites",
               "research": "Researching a sound for the Influence Engine", "direct": "Directing videos", "chores": "Small chores (cover prompts, labels)",
               "film": "Making videos in code (Motion Graphics, living cover finishes)"}


class Writers:
    def __init__(self, cfg: Config, store: Store):
        accounts = cfg.data / "accounts"
        self.store = store
        self.providers = {
            "grok": Grok(cfg.grok_bin, accounts / "grok-home"),
            "claude": Claude(cfg.studio_sh, cfg.data / "scratch" / "claude-write"),
            "local": Local(cfg.ollama, machine=cfg.machine),
            "openai": ChatGPT(cfg.codex_bin, accounts / "codex-home", cfg.codex_path),
        }
        self.machine, self.mitte = cfg.machine, cfg.mitte
        self.mcp = Servers(cfg.data / "secrets" / "mcp.json")
        self.catalogs = Catalogs(cfg.data / "mcp-catalogs")
        self.on_mcp = None  # called when a catalog has been read (the app tells the interface)
        self.comfy = None  # our ComfyUI (set by the app): which local image models it has
        self.local = localpics.Available()

    def who(self) -> dict[str, list[dict]]:
        saved = {k: v for k, v in (self.store.setting("who") or {}).items() if (k in DEFAULT_WHO or k in IMAGE_ROLES or k in MOTION_ROLES)
                 and v}
        images = self.image_defaults()
        old = (self.store.setting("covers") or {}).get("engine")  # the covers' own switch, before covers had a role
        if old:
            images["covers"] = [{"provider": old}]
        who = {**DEFAULT_WHO, **images, **saved}
        ids = self.image_ids()
        for role in IMAGE_ROLES:  # a choice that's gone (a removed server, Mitte turned off) falls back to the GPU
            if not who.get(role) or who[role][0].get("provider") not in ids:
                who[role] = images[role]
        if not who.get("motion") or who["motion"][0].get("provider") not in self.motion_ids():
            who["motion"] = [{"provider": "local"}]  # H3 on the GPU, unless something else was chosen
        return who

    def motion_ids(self) -> list[str]:
        return ["local", "grok", *(["mitte"] if self.mitte else []), *(f"mcp:{s['id']}" for s in self.mcp.listed())]

    def motion_by(self) -> str:
        """Who animates the scenes of a Surreal music video (one of motion_ids())."""
        return self.who()["motion"][0]["provider"]

    def motion_choices(self, statuses: dict[str, dict] | None = None) -> list[dict]:
        """What can turn stills into clips, as image_choices() lists pictures."""
        st = statuses or {}
        out = [{"id": "local", "name": f"MiniMax H3 on {self.machine}", "cost": 0, "paid": False, **({"connected": True} if st else {}),
                "note": "On your GPU: free, about 90 seconds a clip."},
               {"id": "grok", "name": "Grok Imagine", "cost": 0, "paid": False,
                **({"connected": bool(st["grok"].get("connected"))} if "grok" in st else {}),
                "note": "On your Grok plan (it needs SuperGrok): about 40 seconds a clip, up to 15 seconds long, at 720p."}]
        if self.mitte and self.who().get("motion", [{}])[0].get("provider") == "mitte":  # (only while it's still chosen:
            # the owner's Mitte is an MCP server now, so it isn't offered twice)
            out.append({"id": "mitte", "name": "H3 Max (Mitte)", "cost": 0.2, "paid": True,
                        **({"connected": bool(st["claude"].get("connected"))} if "claude" in st else {}),
                        "note": "Hosted H3 through Mitte: much faster; about 20¢ a 5-second clip at 768p (13¢ at 480p)."})
        for s in self.mcp.listed():
            out.append({"id": f"mcp:{s['id']}", "name": s["name"], "cost": None, "paid": bool(s.get("paid")),
                        **({"connected": bool(s.get("ok"))} if st else {}),
                        "note": "Your MCP server: the model that directs your videos uses its tool that turns a still into video." +
                                (" It may charge your account, so you're asked first." if s.get("paid") else "")})
        return out

    def image_defaults(self) -> dict[str, list[dict]]:
        """The GPU's Krea 2, until the person chooses (the owner's Mitte is one of their MCP servers now)."""
        return {role: list(steps) for role, steps in IMAGE_DEFAULTS.items()}

    def image_ids(self) -> list[str]:
        return ["openai", "grok", *localpics.engines(), *(["mitte"] if self.mitte else []),
                *(f"mcp:{s['id']}" for s in self.mcp.listed())]

    def set_who(self, role: str, chain: list[dict]) -> None:
        cur = self.store.setting("who") or {}
        if role in IMAGE_ROLES or role in MOTION_ROLES:
            ids = self.image_ids() if role in IMAGE_ROLES else self.motion_ids()
            grok = [m["id"] for m in PROVIDER_MODELS["grok"]["image"]] if role in IMAGE_ROLES else []
            cur[role] = [{"provider": c["provider"],
                          **(clean_choice(c.get("model"), c.get("options")) if c["provider"].startswith("mcp:") else
                             {"model": c["model"]} if c["provider"] == "grok" and c.get("model") in grok else {})}
                         for c in chain if c.get("provider") in ids][:1]
        elif role in DEFAULT_WHO:
            cur[role] = [{"provider": c["provider"], "model": c.get("model"),
                          **({"effort": str(c["effort"])[:20]} if c.get("effort") and (
                              c["provider"] == "openai" or (c["provider"] == "claude" and c["effort"] in EFFORTS)) else {})}
                         for c in chain if c.get("provider") in self.providers and (role != "film" or c["provider"] == "claude")]
        else:
            return
        self.store.set_setting("who", cur)

    def step(self, role: str) -> dict:
        """The first choice for a role: {provider, model?, options?, effort?}."""
        return (self.who().get(role) or [{}])[0]

    def using(self, role: str) -> str:
        """For a picture or clip role on an MCP server or Grok, the model (and settings) chosen there, short ("" for an
        MCP server's own default)."""
        step = self.step(role)
        provider = str(step.get("provider") or "")
        kind = "video" if role in MOTION_ROLES else "image"
        if provider == "grok":
            mid = step.get("model") or (GROK_IMAGE_DEFAULT if kind == "image" else "grok-imagine-video-1.5")
            return next((m["name"] for m in PROVIDER_MODELS["grok"][kind] if m["id"] == mid), mid)
        if not provider.startswith("mcp:"):
            return ""
        return summary(self.catalogs, provider.removeprefix("mcp:"), kind, step)

    def made_with(self, role: str) -> str:
        """Exactly what Settings has chosen for a picture or clip role, in words: "ImagineArt · GPT Image 2.5, 2K",
        "Grok Imagine Image 2.0", "Krea 2 on Legion"."""
        step = self.step(role)
        provider = str(step.get("provider") or "local")
        choices = self.motion_choices() if role in MOTION_ROLES else self.image_choices()
        name = next((c["name"] for c in choices if c["id"] == provider), provider)
        use = self.using(role)
        if provider == "grok":
            return use or name
        return f"{name} · {use}" if use else name

    def grok_model(self, role: str) -> str:
        """The Grok Imagine picture model for a role (its default when none was chosen)."""
        step = self.step(role)
        return step.get("model") if step.get("provider") == "grok" and step.get("model") else GROK_IMAGE_DEFAULT

    async def read_models_once(self, sid: str) -> None:
        """A server that answers gets its catalog read by itself, once (when it's added, signed in to or checked), if
        Claude, which reads it, is connected. After that it's read again only when the person asks."""
        rec = self.mcp.get(sid)
        if not rec or not rec.get("ok") or self.catalogs.public(sid)["state"] != "none":
            return
        try:
            if not (await self.providers["claude"].status()).get("connected"):
                return
        except Exception:  # noqa: BLE001 (no Claude, no reading: the person can still ask for it)
            return
        self.catalogs.start(self, sid)

    def mcp_listed(self) -> list[dict]:
        """The MCP servers for the interface, each with its catalog (sv/catalog.py)."""
        return [s | {"catalog": self.catalogs.public(s["id"])} for s in self.mcp.listed()]

    def image_choices(self, statuses: dict[str, dict] | None = None) -> list[dict]:
        """What can make pictures: {id, name, note, cost (USD a picture, None if unknown), paid, connected}. Without
        statuses, `connected` is left out (the connections themselves aren't asked)."""
        st = statuses or {}

        def on(pid: str) -> dict:
            return {"connected": bool(st[pid].get("connected"))} if pid in st else {}
        out = [
            {"id": "openai", "name": "GPT Image 2 (ChatGPT)", "cost": 0, "paid": False, **on("openai"),
             "note": "ChatGPT's own image tool, on your ChatGPT plan." + ("" if st.get("openai", {}).get("connected", True) else " Sign in above.")},
            {"id": "grok", "name": "Grok Imagine", "cost": 0, "paid": False, **on("grok"),
             "note": "Grok Imagine, on your Grok plan (it needs SuperGrok)."},
            # every image model on this machine's GPU whose files our ComfyUI has (sv/localpics.py)
            *({"id": m.engine, "name": f"{m.name} on {self.machine}", "cost": 0, "paid": False,
               **({"connected": m.key in self.local.keys} if st else {}),
               "note": "On your GPU: free, and waits its turn behind songs." +
                       (" It keeps people and places the same from reference pictures." if m.refs else "")}
              for m in localpics.MODELS.values()),
        ]
        if self.mitte and any(self.who().get(r, [{}])[0].get("provider") == "mitte" for r in IMAGE_ROLES):  # (as above)
            out.append({"id": "mitte", "name": "GPT Image 2.5 (Mitte)", "cost": MITTE_COST, "paid": False, **on("claude"),
                        "note": "Through Mitte on your Claude account; about 7¢ a picture."})
        for s in self.mcp.listed():
            out.append({"id": f"mcp:{s['id']}", "name": s["name"], "cost": None, "paid": bool(s.get("paid")),
                        **({"connected": bool(s.get("ok"))} if st else {}),
                        "note": "Your MCP server: the model that directs your videos uses its tools to make each picture." +
                                (" It may charge your account, so you're asked first." if s.get("paid") else "")})
        return out

    async def statuses(self) -> dict[str, dict]:
        """Each provider's sign-in, as it stands (what the picture and clip choices are marked connected by)."""
        await self.local.check(self.comfy)  # (which local image models are there, at most once a minute)
        return {k: await p.status() for k, p in self.providers.items()}

    async def connections(self) -> dict[str, Any]:
        statuses = await self.statuses()
        return {"providers": list(statuses.values()), "who": self.who(), "roles": ROLE_LABELS, "efforts": list(EFFORTS),
                "filmModels": FILM_MODELS, "imageRoles": IMAGE_ROLES, "imageProviders": self.image_choices(statuses),
                "motionRoles": MOTION_ROLES, "motionProviders": self.motion_choices(statuses), "mcp": self.mcp_listed(),
                "providerModels": PROVIDER_MODELS}

    async def doers(self) -> dict[str, Any]:
        """Who does each job right now, for the interface's wording: the first connected step of each role's chain
        ({provider, name, model} with a short `name` such as "Claude" or "ChatGPT"), or None when nothing in the chain is
        connected, so the interface names a model only once one is connected. `filmModels`: the models that can
        direct videos in code (Claude Code's), with their names."""
        statuses = {k: await p.status() for k, p in self.providers.items()}
        short = {"claude": "Claude", "openai": "ChatGPT", "grok": "Grok", "local": "your local model"}

        def label(provider: str, model: str | None) -> str:
            models = statuses.get(provider, {}).get("models") or []
            hit = next((m for m in models if m["id"] == model), None) or next((m for m in models if m.get("default")), None)
            return (hit or {}).get("name") or model or short.get(provider, provider)
        out: dict[str, Any] = {}
        for role, chain in self.who().items():
            if role not in DEFAULT_WHO:
                continue
            step = next((c for c in chain if statuses.get(c["provider"], {}).get("connected")), None)
            out[role] = None if step is None else {
                "provider": step["provider"], "name": short.get(step["provider"], step["provider"]),
                "model": label(step["provider"], step.get("model"))}
        claude = statuses["claude"]
        return {"roles": out, "plan": "Claude" if claude.get("connected") else None,
                "filmModels": [{"id": k, "name": f"Claude {v}"} for k, v in FILM_MODELS.items()] if claude.get("connected") else []}

    def picture_by(self, role: str) -> str:
        """Who makes this role's pictures (one of image_ids())."""
        return (self.who().get(role) or self.image_defaults()[role])[0]["provider"]

    def film(self) -> dict:
        """The model and reasoning level for videos made in code (Settings → Who does what)."""
        step = (self.who().get("film") or DEFAULT_WHO["film"])[0]
        return {"model": step.get("model") or OPUS, "effort": step.get("effort")}

    async def write(self, task: str, body: dict, provider: str | None = None, model: str | None = None,
                    images: list | None = None) -> dict:
        """`images`: pictures the writer looks at (Claude and ChatGPT; the others go by the words)."""
        if task not in tasks.SCHEMAS:
            raise WriterError("The writer doesn't know that task.")
        prompt, schema = tasks.prompt(task, body)
        chain = [{"provider": provider, "model": model}] if provider else self.who()[TASK_ROLE[task]]
        tried: list[str] = []
        for step in chain:
            p = self.providers.get(step["provider"])
            if p is None:
                continue
            st = await p.status()
            if not st.get("connected"):
                tried.append(f"{p.name} isn't connected")
                continue
            try:
                extra = {"images": images, "effort": step.get("effort")} if p.id in ("claude", "openai") else {}
                data = await p.complete(tasks.system(task), prompt, schema, step.get("model"), **{k: v for k, v in extra.items() if v})
                return {"result": tasks.read(task, data), "by": {"provider": p.id, "name": p.name, "model": step.get("model")}}
            except (WriterError, ValueError) as exc:
                tried.append(f"{p.name}: {exc}")
        raise WriterError("No writer could do it. " + "; ".join(tried))


__all__ = ["Writers", "WriterError"]
