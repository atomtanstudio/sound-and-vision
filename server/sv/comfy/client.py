"""ComfyUI, used only through its API (sv-comfy, :8210 by default).

A job is: open the WebSocket with our client id, POST /prompt, follow the events for
that prompt (progress per node, cached nodes, errors), then read /history for its
outputs. If the socket drops, it falls back to polling /history, so a job is never
lost to a network blip.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import websockets

Event = dict[str, Any]
OnEvent = Callable[[Event], Awaitable[None] | None]


class ComfyError(RuntimeError):
    """ComfyUI refused or failed a prompt. `message` is plain language; `detail` keeps the technical text."""

    def __init__(self, message: str, detail: Any = None, node_type: str | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail
        self.node_type = node_type


@dataclass
class Result:
    prompt_id: str
    outputs: dict[str, Any]
    cached_nodes: list[str] = field(default_factory=list)
    seconds: float = 0.0

    def files(self, node: str, kind: str = "audio") -> list[dict]:
        """File records ({filename, subfolder, type}) a SaveAudio / SaveImage / VHS node wrote."""
        out = self.outputs.get(node) or {}
        return list(out.get(kind) or out.get("gifs") or out.get("images") or [])


class Comfy:
    def __init__(self, base: str, *, timeout: float = 30.0):
        self.base = base.rstrip("/")
        self.ws_base = "ws" + self.base[4:] if self.base.startswith("http") else self.base
        self.http = httpx.AsyncClient(base_url=self.base, timeout=timeout)
        self._object_info: dict | None = None

    async def close(self) -> None:
        await self.http.aclose()

    # ---- facts about the instance ------------------------------------------------

    async def system_stats(self) -> dict:
        r = await self.http.get("/system_stats")
        r.raise_for_status()
        return r.json()

    async def vram_free_mib(self) -> int:
        dev = (await self.system_stats())["devices"][0]
        return int(dev["vram_free"]) // 2**20

    async def object_info(self, refresh: bool = False) -> dict:
        if self._object_info is None or refresh:
            r = await self.http.get("/object_info", timeout=120)
            r.raise_for_status()
            self._object_info = r.json()
        return self._object_info

    async def models(self, folder: str) -> list[str]:
        """The model files ComfyUI has in one of its folders ("diffusion_models", "text_encoders", "vae", …)."""
        r = await self.http.get(f"/models/{folder}", timeout=20)
        r.raise_for_status()
        got = r.json()
        return [str(x) for x in got] if isinstance(got, list) else []

    async def queue_size(self) -> int:
        r = await self.http.get("/queue")
        r.raise_for_status()
        q = r.json()
        return len(q.get("queue_running", [])) + len(q.get("queue_pending", []))

    # ---- memory ------------------------------------------------------------------

    async def free(self, unload_models: bool = True) -> None:
        """Ask ComfyUI to drop loaded models. It acts on this a moment later, between jobs."""
        r = await self.http.post("/free", json={"unload_models": unload_models, "free_memory": True})
        r.raise_for_status()

    # ---- files -------------------------------------------------------------------

    async def upload(self, path: Path, subfolder: str = "sv", overwrite: bool = True) -> str:
        """Put a file in ComfyUI's input folder; returns the name LoadAudio / LoadImage take."""
        with open(path, "rb") as fh:
            r = await self.http.post(
                "/upload/image",
                data={"subfolder": subfolder, "type": "input", "overwrite": str(overwrite).lower()},
                files={"image": (path.name, fh, "application/octet-stream")},
                timeout=600,
            )
        r.raise_for_status()
        res = r.json()
        return f"{res['subfolder']}/{res['name']}" if res.get("subfolder") else res["name"]

    async def download(self, ref: dict, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        params = {"filename": ref["filename"], "subfolder": ref.get("subfolder", ""), "type": ref.get("type", "output")}
        async with self.http.stream("GET", "/view", params=params, timeout=600) as r:
            r.raise_for_status()
            with open(dest, "wb") as fh:
                async for chunk in r.aiter_bytes(1 << 20):
                    fh.write(chunk)
        return dest

    # ---- running a prompt --------------------------------------------------------

    async def submit(self, graph: dict, client_id: str) -> str:
        r = await self.http.post("/prompt", json={"prompt": graph, "client_id": client_id})
        if r.status_code == 400:
            body = r.json()
            err = body.get("error", {})
            nodes = body.get("node_errors", {})
            first = next(iter(nodes.values()), {}) if nodes else {}
            why = (first.get("errors") or [{}])[0].get("details") or err.get("message") or "the graph was rejected"
            raise ComfyError(f"ComfyUI couldn't start this: {why}", detail=body,
                             node_type=first.get("class_type"))
        r.raise_for_status()
        return r.json()["prompt_id"]

    async def cancel(self, prompt_id: str) -> None:
        """Stop a prompt: drop it from the queue if it's waiting, interrupt it if it's running."""
        await self.http.post("/queue", json={"delete": [prompt_id]})
        await self.http.post("/interrupt", json={"prompt_id": prompt_id})

    async def run(self, graph: dict, on_event: OnEvent | None = None, *, poll_s: float = 2.0) -> Result:
        """Run a graph to the end. on_event gets {type: queued|cached|node|progress|done, ...}."""
        client_id = uuid.uuid4().hex
        loop = asyncio.get_running_loop()
        started = loop.time()

        async def emit(ev: Event) -> None:
            if on_event:
                res = on_event(ev)
                if asyncio.iscoroutine(res):
                    await res

        cached: list[str] = []
        try:
            ws = await websockets.connect(f"{self.ws_base}/ws?clientId={client_id}", max_size=None, open_timeout=10)
        except (OSError, websockets.WebSocketException):
            ws = None

        prompt_id = await self.submit(graph, client_id)
        await emit({"type": "queued", "prompt_id": prompt_id})

        if ws is not None:
            try:
                async with ws:
                    async for raw in ws:
                        if isinstance(raw, bytes):  # latent previews; not used yet
                            continue
                        msg = json.loads(raw)
                        data = msg.get("data") or {}
                        if data.get("prompt_id") not in (None, prompt_id):
                            continue
                        kind = msg.get("type")
                        if kind == "execution_cached":
                            cached = list(data.get("nodes") or [])
                            await emit({"type": "cached", "nodes": cached})
                        elif kind == "executing" and data.get("node"):
                            await emit({"type": "node", "node": data["node"]})
                        elif kind == "progress":
                            await emit({"type": "progress", "node": data.get("node"),
                                        "value": data.get("value"), "max": data.get("max")})
                        elif kind == "execution_error":
                            raise ComfyError(
                                f"{data.get('node_type') or 'A step'} failed: {data.get('exception_message', '').strip()}",
                                detail=data, node_type=data.get("node_type"))
                        elif kind == "execution_interrupted":
                            raise ComfyError("Stopped.", detail=data)
                        elif kind == "execution_success" or (kind == "executing" and data.get("node") is None
                                                             and data.get("prompt_id") == prompt_id):
                            break
            except (websockets.ConnectionClosed, OSError):
                pass  # fall through to polling

        while True:  # the history is the record either way
            r = await self.http.get(f"/history/{prompt_id}")
            r.raise_for_status()
            h = r.json().get(prompt_id)
            if h:
                status = h.get("status") or {}
                if status.get("status_str") == "error":
                    msgs = [m for m in status.get("messages", []) if m and m[0] == "execution_error"]
                    d = msgs[0][1] if msgs else {}
                    raise ComfyError(f"{d.get('node_type') or 'A step'} failed: {d.get('exception_message', '').strip()}",
                                     detail=status, node_type=d.get("node_type"))
                if status.get("completed") or status.get("status_str") == "success":
                    res = Result(prompt_id, h.get("outputs") or {}, cached, round(loop.time() - started, 1))
                    await emit({"type": "done", "seconds": res.seconds})
                    return res
            await asyncio.sleep(poll_s)
