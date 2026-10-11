"""Sound / Vision's server: the API, the live event stream, the media files, and the built interface. It runs on
the GPU machine: `uvicorn sv.app:app --host 0.0.0.0 --port 7660`.

Access: devices on the networks in SV_OPEN_NETWORKS (a home network) come straight in. Anyone else needs the one
key (data/secrets/api-token): a browser pairs once (POST /pair) and keeps it as a cookie; the development proxy and
scripts send it as a bearer header."""

from __future__ import annotations

import html
import json
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import tempfile
from urllib.parse import urlparse

import httpx
import asyncio
import time

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import influences, net
from .analysis import run_analysis
from .comfy.client import Comfy
from .comfy.registry import Registry
from .config import load
from .events import Hub
from .jobs import JobError, Scheduler
from .music import yue2
from .music.takes import run_other_take, run_yue2_take
from . import covers as covers_mod, influence_engine, songs
from . import imports as imports_mod
from . import brand as brand_mod, library as library_mod, look as look_mod, share as share_mod
from .video import finish as finish_mod
from .video import kinetic as kinetic_mod
from .video import living as living_mod
from .video import music as music_mod
from .guard import UNSAFE, Guard
from .mcp import MCPError
from .store import Conflict, Store
from .web import web_file
from .writers import Writers, WriterError
from .paths import under

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("sv.app")
cfg = load()
store = Store(cfg.db)
hub = Hub()
comfy = Comfy(cfg.comfy)
registry = Registry()
sched = Scheduler(cfg, store, hub, comfy, registry)
sched.register("song.yue2", "gpu", run_yue2_take)
sched.register("song.other", "gpu", run_other_take)
sched.register("analysis", "gpu", run_analysis)
writers = Writers(cfg, store)


class _App:  # what songs.start_takes needs from here
    pass


APP = _App()
APP.cfg, APP.store, APP.hub, APP.sched = cfg, store, hub, sched
songs.register(sched, APP, writers)
engine = influence_engine.register(sched, APP, writers)
covers = covers_mod.register(sched, APP, writers)
APP.covers = covers
living = living_mod.register(sched, APP, writers)
APP.living = living
finish_mod.register(sched, APP, living)
imports = imports_mod.register(sched, APP)
kinetic = kinetic_mod.register(sched, APP, writers)
music = music_mod.register(sched, APP, writers)
brand = brand_mod.Brand(APP)
APP.brand = brand
library = library_mod.Library(APP)
APP.library = library
share = share_mod.register(sched, APP)
APP.share = share
TOKEN = cfg.token()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await sched.start()
    yield
    await sched.stop()
    await comfy.close()
    await writers.providers["openai"].close()


# (no /docs or /openapi.json: they'd sit outside the access check, and nothing uses them)
app = FastAPI(title="Sound / Vision", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


GUARD = Guard(cfg.hosts)


def bearer(headers) -> bool:
    """The key as a bearer header: the development proxy and scripts (a page on another site can't send one)."""
    auth = headers.get("authorization", "")
    return auth.startswith("Bearer ") and secrets.compare_digest(auth[7:], TOKEN)


def allowed(headers, cookies, host: str | None) -> bool:
    """A device on an open network (SV_OPEN_NETWORKS, a home network), or one carrying the key: the paired cookie,
    or (from the development proxy and scripts) a bearer header."""
    if cfg.open_to(host) or bearer(headers):
        return True
    key = cookies.get("sv", "")
    return bool(key) and secrets.compare_digest(key, TOKEN)


@app.middleware("http")
async def access(request: Request, call_next):
    if not GUARD.known_host(request.headers.get("host")):  # (sv/guard.py: a page's own domain pointed at us)
        return JSONResponse({"error": "Open Sound / Vision by this machine's address or name (or add the name to "
                                      "SV_HOSTS)."}, status_code=421)
    if request.method in UNSAFE and not bearer(request.headers) and not GUARD.same_origin(request.headers):
        return JSONResponse({"error": "That request came from another site."}, status_code=403)
    if request.url.path.startswith(("/api", "/files")) and \
            not allowed(request.headers, request.cookies, request.client and request.client.host):
        return JSONResponse({"error": "This browser isn't paired with Sound / Vision yet.",
                             "keyFile": str(cfg.data / "secrets" / "api-token")}, status_code=401)
    return await call_next(request)


class PairIn(BaseModel):
    key: str


@app.post("/pair")
async def pair(body: PairIn):
    """Pair a browser: the key comes in the request body (never in an address, where it would sit in
    the history) and is kept as an http-only cookie for a year."""
    if not secrets.compare_digest(body.key.strip(), TOKEN):
        raise HTTPException(403, "That key isn't this Sound / Vision's.")
    r = JSONResponse({"ok": True})
    r.set_cookie("sv", TOKEN, max_age=365 * 86400, httponly=True, samesite="lax")
    return r


def _err(status: int, message: str) -> HTTPException:
    return HTTPException(status, message)


# ---- health ------------------------------------------------------------------------------------

_comfy_seen: dict[str, Any] = {"at": 0.0, "state": None}


@app.get("/api/health")
async def health() -> dict:
    """Never hangs: ComfyUI gets 3 s to answer. While it works on a song its web server can be slow,
    so a slow answer during a job is "busy", not "down"; the last good reading is kept for context."""
    out: dict[str, Any] = {"ok": True, "machine": cfg.machine}
    jobs = store.jobs(("queued", "running"))
    running = any(j["status"] == "running" and j["lane"] == "gpu" for j in jobs)
    try:
        stats = await asyncio.wait_for(comfy.system_stats(), 3)
        dev = stats["devices"][0]
        state = {"ok": True, "busy": running, "version": stats["system"]["comfyui_version"],
                 "vramFreeMiB": int(dev["vram_free"]) // 2**20, "vramTotalMiB": int(dev["vram_total"]) // 2**20}
        _comfy_seen.update(at=time.time(), state=state)
        out["comfy"] = state
    except Exception as exc:  # noqa: BLE001
        last = _comfy_seen["state"] or {}
        if running and time.time() - _comfy_seen["at"] < 600:
            out["comfy"] = {**last, "ok": True, "busy": True, "slow": True}
        else:
            out["comfy"] = {"ok": False, "error": str(exc)[:200] or "no answer in 3 s"}
    out["queue"] = len(jobs)
    # what's being made right now, for the status light (any lane: Claude's films count as much as the GPU's songs)
    titles: dict[str, str] = {}
    for j in jobs:
        if j.get("projectId") and j["projectId"] not in titles:
            titles[j["projectId"]] = (store.project(j["projectId"]) or {}).get("title") or ""
    out["working"] = [{"id": j["id"], "kind": j["kind"], "status": j["status"], "message": (j.get("message") or "")[:160],
                       "projectId": j.get("projectId"), "title": titles.get(j.get("projectId") or "", "")}
                      for j in sorted(jobs, key=lambda j: j["status"] != "running")][:12]
    return out


@app.get("/api/models/check")
async def models_check() -> dict:
    return registry.check(await comfy.object_info(refresh=True))


# ---- live events -------------------------------------------------------------------------------

@app.websocket("/api/live")
async def live(ws: WebSocket) -> None:
    """Every change, as {"kind": ..., "data": ...}, to one window (let in as the API is)."""
    if not GUARD.known_host(ws.headers.get("host")) or (not bearer(ws.headers) and not GUARD.same_origin(ws.headers)) \
            or not allowed(ws.headers, ws.cookies, ws.client and ws.client.host):
        await ws.close(code=4401)  # (a page on another site would otherwise read every change as it happens)
        return
    await ws.accept()
    q = hub.subscribe()
    try:
        await ws.send_json({"kind": "hello", "data": {"at": time.time()}})
        while True:
            try:
                kind, data = await asyncio.wait_for(q.get(), timeout=20)
                await ws.send_json({"kind": kind, "data": data})
            except TimeoutError:
                await ws.send_json({"kind": "ping", "data": None})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        hub.unsubscribe(q)


@app.get("/api/events")
async def events() -> StreamingResponse:
    return StreamingResponse(hub.stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---- projects ----------------------------------------------------------------------------------

class ProjectIn(BaseModel):
    title: str = ""
    doc: dict = {}
    rev: int | None = None


@app.get("/api/projects")
async def list_projects() -> list[dict]:
    out = []
    for p in store.projects():
        takes = store.takes(p["id"])
        out.append({**p, "takeCount": len(takes),
                    "master": next((t for t in takes if t["id"] == p.get("masterTake")), None)})
    return out


@app.post("/api/projects")
async def create_project(body: ProjectIn) -> dict:
    p = store.create_project(body.title or "Untitled song", body.doc)
    hub.publish("project", p)
    return p


@app.get("/api/projects/{pid}")
async def get_project(pid: str) -> dict:
    p = store.project(pid)
    if not p:
        raise _err(404, "That song isn't here any more.")
    return p


# Kept by the server and changed only through their own routes: a save from the song page carries them over as they
# are, whatever it sends for them.
SERVER_OWNED = ("artist", "cover", "covers", "prompt", "writtenBy", "living", "reference", "source", "lyricsHeard", "kinetic", "music", "layout",
                "thumbs", "clips")
_resleeve: dict[str, asyncio.Task] = {}


async def _resleeve_later(pid: str) -> None:
    """The title changed: set the sleeve again once typing has paused."""
    await asyncio.sleep(2.5)
    try:
        hub.publish("project", await asyncio.to_thread(covers.reset, pid))
    except Exception:
        log.exception("re-setting the cover of %s failed", pid)
    finally:
        _resleeve.pop(pid, None)


@app.put("/api/projects/{pid}")
async def save_project(pid: str, body: ProjectIn) -> dict:
    old = store.project(pid) or {}
    # the server's own fields are the server's: whatever a save sends for them is ignored (some hold file paths)
    doc = {**{k: v for k, v in body.doc.items() if k not in SERVER_OWNED}, **{k: old[k] for k in SERVER_OWNED if k in old}}
    try:
        p = store.save_project(pid, body.title, doc, body.rev)
    except KeyError:
        raise _err(404, "That song isn't here any more.") from None
    except Conflict:
        return JSONResponse({"error": "conflict", "project": store.project(pid)}, status_code=409)
    hub.publish("project", p)
    if (p.get("cover") or {}).get("title") not in (None, p["title"]):
        if (t := _resleeve.get(pid)) and not t.done():
            t.cancel()
        _resleeve[pid] = asyncio.create_task(_resleeve_later(pid))
    return p


@app.delete("/api/projects/{pid}")
async def trash_project(pid: str) -> dict:
    store.trash_project(pid)
    hub.publish("project", {"id": pid, "trashed": True})
    return {"ok": True}


# ---- takes -------------------------------------------------------------------------------------

@app.get("/api/projects/{pid}/takes")
async def list_takes(pid: str) -> list[dict]:
    return store.takes(pid)


class MakeIn(yue2.SongRequest):
    model: str = "yue2"


@app.post("/api/projects/{pid}/takes")
async def make_takes(pid: str, body: MakeIn) -> dict:
    if not store.project(pid):
        raise _err(404, "That song isn't here any more.")
    req = yue2.SongRequest(**body.model_dump(exclude={"model"}))
    if req.cover:  # the song to cover is this song's reference: its file and length come from here, not the browser
        ref = (store.project(pid) or {}).get("reference") or {}
        if body.model != "yue2":
            raise _err(422, "Covers are made with YuE2.")
        if not ref.get("file"):
            raise _err(409, "Choose the song to cover first.")
        req.cover.reference, req.cover.seconds = ref["file"], ref.get("seconds")
    try:
        if body.model in ("ace15", "music3"):
            made = songs.start_other_takes(APP, pid, body.model, req)
        elif body.model == "yue2":
            made = songs.start_takes(APP, pid, req)
        else:
            raise _err(422, "That song model isn't here.")
        songs.name_if_untitled(APP, pid)
        return made
    except yue2.SongError as exc:
        raise _err(422, str(exc)) from None


class QuickIn(BaseModel):
    prompt: str
    takes: int = 2


@app.post("/api/quick")
async def quick(body: QuickIn) -> dict:
    """The Home prompt: a new song from whatever was typed. The song exists at once (so the page can open it);
    a job reads the prompt, fills the song in and starts the takes."""
    if not body.prompt.strip():
        raise _err(422, "Type something first: an idea, a mood, a sound, or some lyrics.")
    p = store.create_project("New song", {"prompt": body.prompt, "sung": True})
    hub.publish("project", p)
    job = sched.submit("quick", {"message": "Reading your idea", "prompt": body.prompt, "takes": max(1, min(4, body.takes))}, p["id"])
    return {"project": p, "job": job}


@app.post("/api/takes/{tid}/use")
async def use_take(tid: str) -> dict:
    """Make this the song's take: everything else (the video, the timing) follows it. Listening starts."""
    t = store.take(tid)
    if not t or t["status"] != "ready":
        raise _err(409, "That take isn't ready yet.")
    p = store.patch_project(t["projectId"], masterTake=tid)
    hub.publish("project", p)
    a = t.get("analysis") or {}
    if a.get("status") not in ("ready", "running", "queued"):
        store.update_take(tid, analysis={"status": "queued"})
        sched.submit("analysis", {"message": "Waiting its turn"}, t["projectId"], tid)
        hub.publish("take", store.take(tid))
    return {"project": p, "take": store.take(tid)}


@app.post("/api/takes/{tid}/listen")
async def listen_again(tid: str) -> dict:
    t = store.take(tid)
    if not t or t["status"] != "ready":
        raise _err(409, "That take isn't ready yet.")
    store.update_take(tid, analysis={"status": "queued"})
    job = sched.submit("analysis", {"message": "Waiting its turn"}, t["projectId"], tid)
    hub.publish("take", store.take(tid))
    return job


@app.patch("/api/takes/{tid}")
async def rename_take(tid: str, body: dict) -> dict:
    fields = {k: body[k] for k in ("label", "liked") if k in body}
    t = store.update_take(tid, **fields)
    hub.publish("take", t)
    return t


@app.delete("/api/takes/{tid}")
async def trash_take(tid: str) -> dict:
    t = store.take(tid)
    if t and t.get("jobId"):
        await sched.cancel(t["jobId"])
    store.trash_take(tid)
    hub.publish("take", {"id": tid, "projectId": t["projectId"] if t else None, "trashed": True})
    return {"ok": True}


# ---- jobs --------------------------------------------------------------------------------------

@app.get("/api/jobs")
async def list_jobs(project: str | None = None) -> list[dict]:
    return store.jobs(("queued", "running"), project)


@app.get("/api/jobs/{jid}")
async def get_job(jid: str) -> dict:
    """One job, finished or not (the list above has only the live ones): how a page learns why one failed."""
    j = store.job(jid)
    if not j:
        raise _err(404, "No such job.")
    return j


@app.post("/api/jobs/{jid}/cancel")
async def cancel_job(jid: str) -> dict:
    j = await sched.cancel(jid)
    if not j:
        raise _err(404, "No such job.")
    return j


# ---- writing -----------------------------------------------------------------------------------

class WriteIn(BaseModel):
    task: str
    song: dict = {}
    text: str | None = None
    target: dict | None = None
    avoid: str | None = None
    provider: str | None = None
    model: str | None = None


@app.post("/api/write")
async def write(body: WriteIn) -> dict:
    try:
        return await writers.write(body.task, body.model_dump(), body.provider, body.model)
    except WriterError as exc:
        raise _err(422, str(exc)) from None


# ---- connections -------------------------------------------------------------------------------

@app.get("/api/connections")
async def connections() -> dict:
    return await writers.connections()


@app.post("/api/connections/{provider}/signin")
async def signin(provider: str) -> dict:
    p = writers.providers.get(provider)
    if not p or not hasattr(p, "begin_login"):
        raise _err(422, "Sign in to that one where it runs (see its note).")
    try:
        return await p.begin_login()
    except WriterError as exc:
        raise _err(422, str(exc)) from None


@app.post("/api/connections/{provider}/signin/cancel")
async def signin_cancel(provider: str) -> dict:
    p = writers.providers.get(provider)
    if p and hasattr(p, "cancel_login"):
        await p.cancel_login()
    return await p.status() if p else {}


@app.get("/api/who")
async def who_does_what() -> dict:
    """Who does each job right now (the first connected model of each role), so the interface can name it."""
    return await writers.doers()


@app.post("/api/connections/{provider}/signout")
async def signout(provider: str) -> dict:
    """Sign out of an account the app signed in to (ChatGPT, Grok): its login is removed from the app's own home."""
    p = writers.providers.get(provider)
    if p is None or not hasattr(p, "logout"):
        raise _err(422, "Sign out of that one where it runs.")
    try:
        return await p.logout()
    except WriterError as exc:
        raise _err(409, str(exc)) from None


class McpIn(BaseModel):
    name: str
    url: str
    header: str = ""
    key: str = ""
    paid: bool = True


class McpPatch(BaseModel):
    paid: bool | None = None
    director: bool | None = None  # Claude may use it while it directs a video


@app.get("/api/mcp")
async def mcp_list() -> list[dict]:
    """Your MCP servers (never their keys)."""
    return writers.mcp.listed()


@app.post("/api/mcp")
async def mcp_add(body: McpIn) -> dict:
    """Add a server: it's connected to and its tools listed first, so one that doesn't answer isn't kept."""
    try:
        return await writers.mcp.add(body.name, body.url, body.header, body.key, body.paid)
    except MCPError as exc:
        raise _err(422, str(exc)) from None


@app.post("/api/mcp/{sid}/check")
async def mcp_check(sid: str) -> dict:
    try:
        return await writers.mcp.check(sid)
    except MCPError as exc:
        raise _err(404, str(exc)) from None


@app.patch("/api/mcp/{sid}")
async def mcp_patch(sid: str, body: McpPatch) -> dict:
    try:
        return writers.mcp.update(sid, paid=body.paid, director=body.director)
    except MCPError as exc:
        raise _err(404, str(exc)) from None


class SignInIn(BaseModel):
    origin: str = ""  # where the browser has the app (http://machine:7660): it comes back there


@app.post("/api/mcp/{sid}/signin")
async def mcp_signin(sid: str, body: SignInIn, request: Request) -> dict:
    """Start signing in to a server: the address to open in the browser, which comes back to the app afterwards."""
    o = urlparse(body.origin) if body.origin else urlparse(str(request.base_url))
    if o.scheme not in ("http", "https") or not o.netloc:
        raise _err(422, "The app's address isn't one a browser could come back to.")
    try:
        return {"url": await writers.mcp.begin_signin(sid, f"{o.scheme}://{o.netloc}/api/mcp/oauth/callback")}
    except MCPError as exc:
        raise _err(422, str(exc)) from None


SIGNED_IN_PAGE = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Sound / Vision</title><body style="margin:0;display:grid;place-items:center;min-height:100vh;background:#0b0c0f;
color:#f1f1f3;font:16px system-ui,sans-serif"><main style="max-width:30em;padding:24px;text-align:center"><p>{msg}</p>
<p style="color:#868995">You can close this tab.</p></main><script>try{{window.opener&&window.opener.postMessage("sv-mcp","*")}}catch(e){{}}</script>"""


@app.get("/api/mcp/oauth/callback", response_class=HTMLResponse)
async def mcp_callback(state: str = "", code: str = "", error: str = "", error_description: str = "") -> HTMLResponse:
    """Where the browser comes back after signing in to a server."""
    if error:
        msg = f"The sign-in didn't go through: {error_description or error}."
    else:
        try:
            rec = await writers.mcp.finish_signin(state, code)
            msg = f"Signed in to {rec['name']}: {len(rec.get('tools') or [])} tools." if rec.get("ok") else \
                f"Signed in to {rec['name']}, but it didn't answer: {rec.get('error')}"
        except MCPError as exc:
            msg = str(exc)
    hub.publish("mcp", {})
    return HTMLResponse(SIGNED_IN_PAGE.format(msg=html.escape(msg)))


class AddressIn(BaseModel):
    address: str


@app.post("/api/mcp/signin/finish")
async def mcp_signin_pasted(body: AddressIn) -> dict:
    """The address the browser ended on after signing in, pasted (when it couldn't come back to the app by itself)."""
    try:
        return await writers.mcp.finish_from_address(body.address)
    except MCPError as exc:
        raise _err(422, str(exc)) from None


@app.post("/api/mcp/{sid}/signout")
async def mcp_signout(sid: str) -> dict:
    try:
        return writers.mcp.sign_out(sid)
    except MCPError as exc:
        raise _err(404, str(exc)) from None


@app.delete("/api/mcp/{sid}")
async def mcp_remove(sid: str) -> dict:
    """Pictures it made stay; anything set to use it goes back to the GPU."""
    writers.mcp.remove(sid)
    return {"ok": True}


@app.put("/api/connections/who/{role}")
async def set_who(role: str, chain: list[dict]) -> dict:
    writers.set_who(role, chain)
    return writers.who()


# ---- influences --------------------------------------------------------------------------------

@app.get("/api/influences")
async def list_influences(model: str | None = None) -> list[dict]:
    return influences.listed(cfg.loras, model)


def _incoming(suffix: str = ".safetensors") -> Path:
    d = cfg.data / "incoming"
    d.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkstemp(dir=d, suffix=suffix)[1])


@app.post("/api/influences/inspect")
async def inspect_influence(file: UploadFile = File(...)) -> dict:
    """Read an uploaded file's header (the browser sends only the first part) to say what it is."""
    tmp = _incoming()
    try:
        head = await file.read(64 << 20)  # a header is a few KB to a few MB; nothing bigger is read
        tmp.write_bytes(head)
        return influences.inspect(tmp)
    except influences.InfluenceError as exc:
        raise _err(422, str(exc)) from None
    finally:
        tmp.unlink(missing_ok=True)


@app.post("/api/influences/upload")
async def upload_influence(file: UploadFile = File(...), name: str = Form(...), kind: str = Form("Style"),
                           about: str = Form(""), model: str = Form("yue2")) -> dict:
    if not (file.filename or "").lower().endswith(".safetensors"):
        raise _err(422, "Only .safetensors files can be added (other formats can run code when loaded).")
    tmp = _incoming()
    size = 0
    try:
        with open(tmp, "wb") as out:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > influences.MAX_BYTES:
                    raise _err(413, "That file is too big for an influence (over 4 GB).")
                out.write(chunk)
        rec = influences.add(cfg.loras, tmp, name=name, kind=kind, about=about, model=model, source=f"upload: {file.filename}")
    except influences.InfluenceError as exc:
        raise _err(422, str(exc)) from None
    finally:
        tmp.unlink(missing_ok=True)
    hub.publish("influences", {"added": rec["id"]})
    return rec


class FromUrlIn(BaseModel):
    url: str
    name: str = ""
    kind: str = "Style"
    about: str = ""
    model: str | None = None


@app.post("/api/influences/from-url")
async def influence_from_url(body: FromUrlIn) -> dict:
    """Download a LoRA from Hugging Face (server side), check it, and add it."""
    try:
        url = influences.hf_url(body.url)
    except influences.InfluenceError as exc:
        raise _err(422, str(exc)) from None
    tmp = _incoming()
    try:
        try:  # (each redirect is checked: Hugging Face's own CDN is public; nothing on the home network is)
            status = await net.download(url, tmp, most=influences.MAX_BYTES, timeout=httpx.Timeout(60, read=300))
        except net.UnsafeURL as exc:
            raise _err(413 if "too big" in str(exc) else 422, "That file is too big for an influence (over 4 GB)."
                       if "too big" in str(exc) else f"Couldn't download that file: {exc}") from None
        if status in (401, 403):
            raise _err(422, "Hugging Face wants a sign-in for that file (it's gated or private).")
        if status != 200:
            raise _err(422, f"Hugging Face answered {status} for that link.")
        info = influences.inspect(tmp)
        model = body.model or info["model"]
        if not model:
            raise _err(422, "Couldn't tell which song model that LoRA is for. Choose one and add it again.")
        name = body.name.strip() or info.get("name") or Path(url).stem.replace("_", " ")
        rec = influences.add(cfg.loras, tmp, name=name, kind=body.kind, about=body.about, model=model, source=url)
    except influences.InfluenceError as exc:
        raise _err(422, str(exc)) from None
    except httpx.HTTPError:
        raise _err(422, "Couldn't download that file from Hugging Face.") from None
    finally:
        tmp.unlink(missing_ok=True)
    hub.publish("influences", {"added": rec["id"]})
    return rec


# ---- covers ------------------------------------------------------------------------------------

class CoverIn(BaseModel):
    engine: str | None = None
    note: str = ""
    prompt: str = ""
    moving: bool = False
    forLiving: bool = False


class CoverUseIn(BaseModel):
    n: int
    forLiving: bool = False


class CoverTextIn(BaseModel):
    artist: str | None = None


class CoverSettingsIn(BaseModel):
    engine: str | None = None
    artist: str | None = None
    auto: str | None = None


@app.post("/api/projects/{pid}/cover")
async def make_cover(pid: str, body: CoverIn) -> dict:
    """A new picture for the song's sleeve (made as Settings → Pictures says, or as asked), then the sleeve is set."""
    if store.project(pid) is None:
        raise _err(404, "No such song.")
    return covers.start(pid, body.engine, body.note, body.prompt, body.moving, body.forLiving)


@app.post("/api/projects/{pid}/cover/upload")
async def upload_cover(pid: str, file: UploadFile = File(...), forLiving: bool = Form(False)) -> dict:
    """Your own picture as the cover (PNG, JPEG or WebP, up to 40 MB)."""
    if store.project(pid) is None:
        raise _err(404, "No such song.")
    d = cfg.data / "incoming"
    d.mkdir(parents=True, exist_ok=True)
    dest = d / f"cover-{secrets.token_hex(6)}"
    size = 0
    with open(dest, "wb") as out:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > 40 * 1024 * 1024:
                out.close()
                dest.unlink(missing_ok=True)
                raise _err(413, "That picture is over 40 MB.")
            out.write(chunk)
    with open(dest, "rb") as f:
        head = f.read(12)
    if not (head.startswith(b"\x89PNG") or head.startswith(b"\xff\xd8\xff") or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")):
        dest.unlink(missing_ok=True)
        raise _err(422, "Choose a PNG, JPEG or WebP picture.")
    return covers.upload(pid, dest, forLiving)


async def _receive(file: UploadFile, limit_mb: int, prefix: str, allowed: tuple[str, ...], what: str) -> Path:
    """An upload, kept in incoming/ until it's moved where it belongs."""
    suffix = imports_mod.safe_suffix(file.filename or "", allowed)
    if not suffix:
        raise _err(422, f"Choose {what}.")
    d = cfg.data / "incoming"
    d.mkdir(parents=True, exist_ok=True)
    dest = d / f"{prefix}-{secrets.token_hex(6)}{suffix}"
    size = 0
    with open(dest, "wb") as out:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > limit_mb * 1024 * 1024:
                out.close()
                dest.unlink(missing_ok=True)
                raise _err(413, f"That file is over {limit_mb} MB.")
            out.write(chunk)
    return dest


AUDIO_CHOICE = "an audio file: MP3, WAV, FLAC, M4A, AAC, OGG or Opus"


@app.post("/api/songs/upload")
async def upload_song(file: UploadFile = File(...), title: str = Form(""), artist: str = Form(""), lyrics: str = Form(""),
                      lrc: str = Form(""), lrcFile: UploadFile | None = File(None), cover: UploadFile | None = File(None),
                      language: str = Form("")) -> dict:
    """Your own finished song (made in Suno, or anywhere): into the library, ready for its videos."""
    src = await _receive(file, 250, "song", imports_mod.AUDIO, AUDIO_CHOICE)
    if lrcFile is not None and lrcFile.filename:
        lrc = (await lrcFile.read(2_000_000)).decode("utf-8", errors="replace")
    art = await _receive(cover, 40, "art", imports_mod.IMAGES, "a PNG, JPEG or WebP picture") if cover is not None and cover.filename else None
    try:
        return imports.song(src, file.filename or "song", title, artist, lyrics[:20000], lrc[:200000], art, language[:40])
    except JobError as exc:
        raise _err(422, exc.message) from None


@app.post("/api/projects/{pid}/reference")
async def upload_reference(pid: str, file: UploadFile = File(...)) -> dict:
    """A song to cover, uploaded: kept on this song as its reference."""
    if store.project(pid) is None:
        raise _err(404, "No such song.")
    src = await _receive(file, 250, "ref", imports_mod.AUDIO, AUDIO_CHOICE)
    try:
        return await asyncio.to_thread(imports.reference, pid, src, file.filename or "song")
    except JobError as exc:
        raise _err(422, exc.message) from None


class ReferenceIn(BaseModel):
    projectId: str


@app.post("/api/projects/{pid}/reference/song")
async def reference_song(pid: str, body: ReferenceIn) -> dict:
    """One of your songs as the song to cover."""
    try:
        return await asyncio.to_thread(imports.reference_from, pid, body.projectId)
    except JobError as exc:
        raise _err(409, exc.message) from None


@app.post("/api/projects/{pid}/reference/words")
async def reference_words(pid: str) -> dict:
    """The covered song's own words onto this song's lyric sheet."""
    try:
        return imports.words_of_reference(pid)
    except JobError as exc:
        raise _err(409, exc.message) from None


@app.delete("/api/projects/{pid}/reference")
async def forget_reference(pid: str) -> dict:
    try:
        return imports.forget_reference(pid)
    except JobError as exc:
        raise _err(404, exc.message) from None


@app.post("/api/projects/{pid}/cover/use")
async def use_cover(pid: str, body: CoverUseIn) -> dict:
    """An earlier picture of the song becomes its cover again."""
    try:
        p = await asyncio.to_thread(covers.use, pid, body.n, body.forLiving)
    except JobError as exc:
        raise _err(409, exc.message) from None
    hub.publish("project", p)
    return p


@app.get("/api/projects/{pid}/covers/{n}/thumb.jpg")
async def cover_thumb(pid: str, n: int):
    try:
        f = await asyncio.to_thread(covers.thumb, pid, n)
    except JobError as exc:
        raise _err(404, exc.message) from None
    return FileResponse(f, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


class ArtistIn(BaseModel):
    artist: str | None = None  # None: back to your artist name from Brand (or the file's)


@app.put("/api/projects/{pid}/artist")
async def set_artist(pid: str, body: ArtistIn) -> dict:
    """The song's own artist (blank: none), and its cover's words set again with it."""
    if not store.project(pid):
        raise _err(404, "That song isn't here any more.")
    doc = {k: v for k, v in store.project(pid).items() if k not in ("id", "title", "rev", "createdAt", "updatedAt", "artist")}
    p = store.patch_project(pid, artist=body.artist.strip()[:80]) if body.artist is not None else \
        store.save_project(pid, store.project(pid)["title"], doc, None)
    if p.get("cover"):
        try:
            p = await asyncio.to_thread(covers.reset, pid)
        except JobError:
            pass  # (the picture behind it is gone: the words show on the next cover)
    hub.publish("project", p)
    return p


@app.post("/api/projects/{pid}/cover/text")
async def cover_text(pid: str, body: CoverTextIn) -> dict:
    """Set the sleeve again with the song's current title and this artist (no new picture)."""
    try:
        if body.artist is not None:  # what's typed here is the song's own artist from now on
            await asyncio.to_thread(lambda: store.patch_project(pid, artist=body.artist.strip()[:80]))
        p = await asyncio.to_thread(covers.reset, pid, body.artist)
    except JobError as exc:
        raise _err(409, exc.message) from None
    hub.publish("project", p)
    return p


@app.get("/api/covers/settings")
async def cover_settings() -> dict:
    return covers.settings()


@app.put("/api/covers/settings")
async def set_cover_settings(body: CoverSettingsIn) -> dict:
    return covers.set_settings(body.engine, body.artist, body.auto)


# ---- Living Album Cover --------------------------------------------------------------------------

class LivingIn(BaseModel):
    settings: dict | None = None
    motions: dict[str, str] | None = None
    mode: str | None = None
    keep: bool = False


class AutoIn(BaseModel):
    note: str = ""
    again: bool = False
    resume: str | None = None  # carry on after a stop: a picture source for an unpainted picture, or "same"


class PlanIn(BaseModel):
    note: str = ""


class RenderIn(BaseModel):
    shape: str | None = None


def _living(fn):
    try:
        return fn()
    except JobError as exc:
        raise _err(409, exc.message) from None


@app.put("/api/projects/{pid}/living")
async def living_update(pid: str, body: LivingIn) -> dict:
    return _living(lambda: living.update(pid, body.settings, body.motions, body.mode, body.keep))


@app.get("/api/projects/{pid}/living/layer.png")
async def living_layer(pid: str):
    try:
        f = await asyncio.to_thread(living.layer, pid)
    except JobError as exc:
        raise _err(404, exc.message) from None
    return FileResponse(f, media_type="image/png", headers={"Cache-Control": "private, max-age=60"})


@app.get("/api/projects/{pid}/living/picture.jpg")
async def living_picture(pid: str):
    try:
        f = await asyncio.to_thread(living.picture, pid)
    except JobError as exc:
        raise _err(404, exc.message) from None
    return FileResponse(f, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=60"})


@app.post("/api/projects/{pid}/living/plan")
async def living_plan(pid: str, body: PlanIn) -> dict:
    """Claude writes one subtle motion per loop (from the cover's own description)."""
    try:
        return await living.plan(pid, body.note)
    except JobError as exc:
        raise _err(409, exc.message) from None


@app.post("/api/projects/{pid}/living/picture")
async def living_picture_use(pid: str) -> dict:
    """'Use this cover': the song's cover is the living cover's picture."""
    return _living(lambda: living.confirm(pid))


@app.post("/api/projects/{pid}/living/loops/{lid}/make")
async def living_make(pid: str, lid: str) -> dict:
    return _living(lambda: living.make(pid, lid))


@app.post("/api/projects/{pid}/living/auto")
async def living_auto(pid: str, body: AutoIn) -> dict:
    """"Let Claude make it": the picture, the motion and the video, decided and made end to end."""
    return _living(lambda: living.auto(pid, body.note, body.again, body.resume))


@app.post("/api/projects/{pid}/living/render")
async def living_render(pid: str, body: RenderIn) -> dict:
    return _living(lambda: living.render(pid, body.shape))


# ---- Motion Graphics (the "kinetic" film) -------------------------------------------------------

class KineticIn(BaseModel):
    request: str = ""
    feel: str = ""
    shape: str = "wide"
    ideaFirst: bool = False
    model: str | None = None
    effort: str | None = None
    lyrics: bool = True


class NoteIn(BaseModel):
    text: str = ""
    go: bool = False


@app.post("/api/projects/{pid}/kinetic")
async def kinetic_start(pid: str, body: KineticIn) -> dict:
    """A motion graphics film (with the lyrics or without), written and rendered in code by Claude with free rein."""
    if body.effort and body.effort not in ("low", "medium", "high", "xhigh", "max"):
        raise _err(422, "Choose a reasoning level: low, medium, high, xhigh or max.")
    try:
        return kinetic.start(pid, body.request, body.feel, body.shape, body.ideaFirst, body.model, body.effort, body.lyrics)
    except JobError as exc:
        raise _err(409, exc.message) from None


@app.post("/api/projects/{pid}/kinetic/note")
async def kinetic_note(pid: str, body: NoteIn) -> dict:
    """A note to Claude about the film: continues the same conversation."""
    try:
        return kinetic.note(pid, body.text, body.go)
    except JobError as exc:
        raise _err(409, exc.message) from None


@app.post("/api/projects/{pid}/kinetic/stop")
async def kinetic_stop(pid: str) -> dict:
    try:
        return await kinetic.stop(pid)
    except JobError as exc:
        raise _err(409, exc.message) from None


@app.get("/api/projects/{pid}/kinetic/peek")
async def kinetic_peek(pid: str) -> list[dict]:
    """The newest pictures Claude has drawn while it works."""
    return await asyncio.to_thread(kinetic.peek, pid)


# ---- Music Video (Surreal first; performance and hybrid next) -------------------------------------

class MusicIn(BaseModel):
    request: str = ""
    feel: str = ""
    kind: str = "surreal"
    opening: bool = True
    part: dict | None = None  # {start, end, label}: a part of the song, made on its own first
    model: str | None = None
    effort: str | None = None


@app.post("/api/projects/{pid}/music")
async def music_start(pid: str, body: MusicIn) -> dict:
    """A music video: Claude plans it, makes its pictures as Settings says and brings them to life with H3."""
    if body.effort and body.effort not in ("low", "medium", "high", "xhigh", "max"):
        raise _err(422, "Choose a reasoning level: low, medium, high, xhigh or max.")
    try:
        return music.start(pid, body.request, body.feel, body.kind, body.opening, body.model, body.effort, body.part)
    except JobError as exc:
        raise _err(409, exc.message) from None


@app.get("/api/projects/{pid}/music/request")
async def music_request(pid: str, kind: str = "surreal") -> dict:
    """The request Claude gets for this kind of music video unless you write your own."""
    p = store.project(pid)
    if not p or kind not in music_mod.KINDS:
        raise _err(404, "No such song or kind.")
    return {"request": music.opening(p, {"kind": kind}), "kinds": list(music_mod.KINDS)}


@app.post("/api/projects/{pid}/music/note")
async def music_note(pid: str, body: NoteIn) -> dict:
    """A note to Claude about the video (or, with go, "make the rest"): continues the same conversation."""
    try:
        return music.note(pid, body.text, body.go)
    except JobError as exc:
        raise _err(409, exc.message) from None


@app.post("/api/projects/{pid}/music/stop")
async def music_stop(pid: str) -> dict:
    try:
        return await music.stop(pid)
    except JobError as exc:
        raise _err(409, exc.message) from None


@app.get("/api/projects/{pid}/music/peek")
async def music_peek(pid: str) -> list[dict]:
    """The newest pictures Claude has made while it works."""
    return await asyncio.to_thread(music.peek, pid)


# ---- branding: logos, fonts and the look of the title, the artist and the logos -------------------

class NameIn(BaseModel):
    name: str = ""


class LookIn(BaseModel):
    look: dict = {}


class LayoutIn(BaseModel):
    layout: dict | None = None


@app.get("/api/fonts")
async def list_fonts() -> list[dict]:
    return look_mod.catalog(str(brand.fonts))


@app.get("/api/fonts/{fid}")
async def font_file(fid: str):
    f = look_mod.font_path(brand.fonts, fid)
    if not f:
        raise _err(404, "No such font.")
    return FileResponse(f, media_type="font/otf" if f.suffix == ".otf" else "font/ttf",
                        headers={"Cache-Control": "private, max-age=86400"})


@app.get("/api/brand")
async def get_brand() -> dict:
    return await asyncio.to_thread(brand.get)


@app.post("/api/brand/logos")
async def add_logo(file: UploadFile = File(...), name: str = Form("Logo"), replace: str = Form("")) -> dict:
    """A logo of yours (PNG, JPEG or WebP, transparency kept), or a new picture for one you have (`replace`)."""
    data = await file.read(20_000_001)
    if len(data) > 20_000_000:
        raise _err(413, "That picture is over 20 MB.")
    try:
        return await asyncio.to_thread(brand.add_logo, name, data, replace or None)
    except JobError as exc:
        raise _err(422, exc.message) from None


@app.patch("/api/brand/logos/{lid}")
async def rename_logo(lid: str, body: NameIn) -> dict:
    return brand.rename_logo(lid, body.name)


@app.delete("/api/brand/logos/{lid}")
async def remove_logo(lid: str) -> dict:
    try:
        return brand.remove_logo(lid)
    except JobError as exc:
        raise _err(404, exc.message) from None


@app.get("/api/brand/logos/{lid}.png")
async def logo_file(lid: str):
    try:
        return FileResponse(brand.logo_file(lid), headers={"Cache-Control": "private, max-age=3600"})
    except JobError as exc:
        raise _err(404, exc.message) from None


@app.put("/api/brand/look")
async def set_brand_look(body: LookIn) -> dict:
    """Your house look: where the title, the artist and each logo sit, and how the words are set."""
    return brand.set_look(body.look)


@app.post("/api/brand/apply")
async def apply_brand() -> dict:
    """Every song's cover set again with today's look (the pictures are kept; only the sleeve changes)."""
    n = 0
    for p in store.projects():
        if p.get("cover"):
            try:
                hub.publish("project", await asyncio.to_thread(covers.reset, p["id"]))
                n += 1
            except JobError:
                pass
    return {"updated": n}


@app.put("/api/projects/{pid}/layout")
async def set_layout(pid: str, body: LayoutIn) -> dict:
    """This song's own look, over the house look (none: the house look as it is); its cover is set again with it."""
    if not store.project(pid):
        raise _err(404, "That song isn't here any more.")
    p = store.patch_project(pid, layout=look_mod.normalize(body.layout) if body.layout else None)
    if p.get("cover"):
        try:
            p = await asyncio.to_thread(covers.reset, pid)
        except JobError as exc:
            raise _err(409, exc.message) from None
    hub.publish("project", p)
    return p


@app.get("/api/projects/{pid}/cover/picture")
async def cover_picture(pid: str):
    """The cover's picture without its title and logos, 1080 px (what the look is laid over in the editor)."""
    p = store.project(pid)
    cover = (p or {}).get("cover")
    art = under(cfg.projects / pid, cover.get("art")) if cover else None
    if not art or not art.exists():
        raise _err(404, "This song has no cover picture.")
    out = cfg.projects / pid / "covers" / f"picture-{cover['n']}-1080.jpg"
    if not out.exists():
        await asyncio.to_thread(lambda: covers_mod.square(art, 1080).save(out, "JPEG", quality=88))
    return FileResponse(out, headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/projects/{pid}/cover/picture/info")
async def cover_picture_info(pid: str) -> dict:
    """The cover picture's title colours and small grayscale, as the server reads them at the cover's size (so the
    editor's automatic colours and placement are the cover's)."""
    p = store.project(pid)
    cover = (p or {}).get("cover")
    art = under(cfg.projects / pid, cover.get("art")) if cover else None
    if not art or not art.exists():
        raise _err(404, "This song has no cover picture.")
    out = cfg.projects / pid / "covers" / f"picture-{cover['n']}-info.json"
    if out.exists():
        return json.loads(out.read_text())
    data = await asyncio.to_thread(lambda: look_mod.info(covers_mod.square(art, covers_mod.SIZE)))
    out.write_text(json.dumps(data))
    return data


# ---- the Library: songs and videos, in folders ----------------------------------------------------

class KeysIn(BaseModel):
    keys: list[str]


class MoveIn(BaseModel):
    keys: list[str]
    folder: str | None = None


class OrderIn(BaseModel):
    ids: list[str]


class ThumbIn(BaseModel):
    at: float = 0.0
    layout: dict | None = None
    show: dict | None = None  # the words on it: {"title": …, "artist": …} (the song's own unless given)


def _lib(fn, *args):
    try:
        return fn(*args)
    except JobError as exc:
        raise _err(409, exc.message) from None


@app.get("/api/library")
async def get_library() -> dict:
    return await asyncio.to_thread(library.get)


@app.post("/api/library/folders")
async def add_folder(body: NameIn) -> dict:
    return _lib(library.add_folder, body.name)


@app.patch("/api/library/folders/{fid}")
async def rename_folder(fid: str, body: NameIn) -> dict:
    return _lib(library.rename_folder, fid, body.name)


@app.delete("/api/library/folders/{fid}")
async def remove_folder(fid: str) -> dict:
    return _lib(library.remove_folder, fid)


@app.put("/api/library/folders")
async def order_folders(body: OrderIn) -> dict:
    return _lib(library.order_folders, body.ids)


@app.get("/api/library/trash")
async def library_trash() -> list[dict]:
    return await asyncio.to_thread(library.trashed)


@app.post("/api/library/trash")
async def trash_items(body: KeysIn) -> dict:
    """Songs and videos into the trash: out of sight, nothing erased (restore brings them back)."""
    r = await asyncio.to_thread(library.trash, body.keys)
    hub.publish("library", r)
    return r


@app.post("/api/library/restore")
async def restore_items(body: KeysIn) -> dict:
    r = await asyncio.to_thread(library.restore, body.keys)
    hub.publish("library", r)
    return r


@app.post("/api/library/move")
async def move_items(body: MoveIn) -> dict:
    """Items into a folder (none: out of every folder)."""
    return _lib(library.move, body.keys, body.folder)


@app.get("/api/library/thumb/{pid}/{kind}/{vid}")
async def video_thumb(pid: str, kind: str, vid: str):
    try:
        f = await asyncio.to_thread(library.thumb, pid, kind, vid)
    except JobError as exc:
        raise _err(404, exc.message) from None
    return FileResponse(f, headers={"Cache-Control": "private, max-age=600"})


@app.get("/api/library/frame/{pid}/{kind}/{vid}")
async def video_frame(pid: str, kind: str, vid: str, at: float = 0.0, w: int = 1280):
    """One frame of a video, as a JPEG (for choosing a thumbnail)."""
    try:
        data = await asyncio.to_thread(library.frame, pid, kind, vid, at, w)
    except JobError as exc:
        raise _err(404, exc.message) from None
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=600"})


@app.get("/api/library/frame/{pid}/{kind}/{vid}/info")
async def video_frame_info(pid: str, kind: str, vid: str, at: float = 0.0) -> dict:
    """The frame's title colours and small grayscale at the thumbnail's size (as for a cover's picture)."""
    try:
        _, pic = await asyncio.to_thread(library.thumb_picture, pid, kind, vid, at)
    except JobError as exc:
        raise _err(404, exc.message) from None
    return await asyncio.to_thread(look_mod.info, pic)


@app.post("/api/library/thumb/{pid}/{kind}/{vid}")
async def make_thumb(pid: str, kind: str, vid: str, body: ThumbIn) -> dict:
    """Your own thumbnail for a video: a frame of it with the title, the artist and your logos laid over it."""
    p = await asyncio.to_thread(_lib, library.make_thumb, pid, kind, vid, body.at, body.layout, body.show)
    hub.publish("project", p)
    return p


@app.delete("/api/library/thumb/{pid}/{kind}/{vid}")
async def forget_thumb(pid: str, kind: str, vid: str) -> dict:
    p = _lib(library.forget_thumb, pid, kind, vid)
    hub.publish("project", p)
    return p


# ---- Share: clips for TikTok, Reels, Shorts and posts ----------------------------------------------

class ClipIn(BaseModel):
    preset: str = "tiktok"
    start: float = 0.0
    end: float = 30.0
    source: dict = {}
    frame: str = "blur"
    focus: float = 0.5
    words: bool = False
    logos: bool = True
    captions: bool = False
    level: bool = True


@app.get("/api/share/presets")
async def share_presets() -> dict:
    return {"presets": {k: {**v, "size": list(v["size"])} for k, v in share_mod.PRESETS.items()}, "loudness": share_mod.LOUD}


@app.get("/api/share/moments/{pid}")
async def share_moments(pid: str, seconds: float = 30.0, upto: float | None = None, since: float | None = None) -> dict:
    """The song's best stretches of that length (on its bars, ending by `upto`), and its loudness and sections for the
    timeline."""
    try:
        return await asyncio.to_thread(share.moments, pid, seconds, upto, since)
    except JobError as exc:
        raise _err(409, exc.message) from None


@app.post("/api/share/clips/{pid}")
async def make_clip(pid: str, body: ClipIn) -> dict:
    try:
        return share.start(pid, body.model_dump())
    except JobError as exc:
        raise _err(409, exc.message) from None


@app.post("/api/share/preview/{pid}")
async def clip_preview(pid: str, body: ClipIn, at: float | None = None):
    """One frame of the clip exactly as it will be made (the moment's middle, unless `at`)."""
    try:
        data = await share.preview(pid, body.model_dump(), at)
    except JobError as exc:
        raise _err(409, exc.message) from None
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/api/share/clips")
async def list_clips() -> list[dict]:
    return await asyncio.to_thread(share.all_clips)


@app.delete("/api/share/clips/{pid}/{cid}")
async def remove_clip(pid: str, cid: str) -> dict:
    try:
        p = share.remove(pid, cid)
    except JobError as exc:
        raise _err(404, exc.message) from None
    hub.publish("project", p)
    return p


# ---- the Influence Engine ----------------------------------------------------------------------

class RunIn(BaseModel):
    text: str
    projectId: str | None = None
    takeId: str | None = None


class StartIn(BaseModel):
    drop: list[str] | None = None  # the songs to leave out; without it, the run's own choices stand


class KeepIn(BaseModel):
    step: int
    name: str | None = None


def _run_or_404(rid: str) -> dict:
    run = store.run(rid)
    if run is None:
        raise _err(404, "No such influence run.")
    return run


@app.get("/api/influence-runs")
async def list_runs() -> list[dict]:
    return store.runs()


@app.get("/api/influence-runs/{rid}")
async def get_run(rid: str) -> dict:
    return _run_or_404(rid)


@app.post("/api/influence-runs")
async def new_run(body: RunIn) -> dict:
    """'Needs more influence': research the sound they asked for. With a take, what it sounds like now is passed along."""
    if len(body.text.strip()) < 3:
        raise _err(422, "Say what it needs more of: a genre, a style or an artist.")
    heard = ""
    if body.projectId and (p := store.project(body.projectId)):
        heard = ", ".join(x for x in [", ".join(p.get("genres") or []), ", ".join(p.get("moods") or []),
                                       p.get("instruments") or "", p.get("extra") or ""] if x)
    run = engine.create(body.text, heard, body.projectId, body.takeId)
    return run


@app.post("/api/influence-runs/{rid}/start")
async def start_run(rid: str, body: StartIn) -> dict:
    _run_or_404(rid)
    try:
        return engine.start(rid, body.drop)
    except JobError as exc:
        raise _err(409, exc.message) from None


@app.post("/api/influence-runs/{rid}/audio")
async def run_audio(rid: str, files: list[UploadFile] = File(...), song: str | None = Form(None)) -> dict:
    """Audio you add to a run: one file for one song, or many matched to its list by their tags or names."""
    _run_or_404(rid)
    got: list[tuple[str, Path]] = []
    try:
        for f in files[:200]:
            tmp, size = _incoming(".audio"), 0
            got.append((Path(f.filename or "song").name, tmp))
            with open(tmp, "wb") as out:
                while chunk := await f.read(1 << 20):
                    size += len(chunk)
                    if size > 400 << 20:
                        raise _err(413, f"{f.filename} is too big for a song (over 400 MB).")
                    out.write(chunk)
        return await engine.add_audio(rid, got, song)
    except JobError as exc:
        raise _err(409, exc.message) from None
    finally:
        for _, tmp in got:
            tmp.unlink(missing_ok=True)


@app.post("/api/influence-runs/{rid}/keep")
async def keep_run(rid: str, body: KeepIn) -> dict:
    _run_or_404(rid)
    try:
        return engine.keep(rid, body.step, body.name)
    except JobError as exc:
        raise _err(409, exc.message) from None


class TryIn(BaseModel):
    step: int
    projectId: str
    strength: float = 0.7


@app.post("/api/influence-runs/{rid}/try")
async def try_run(rid: str, body: TryIn) -> dict:
    """Hear a checkpoint on one of your songs: one YuE2 take with it as an influence."""
    _run_or_404(rid)
    try:
        return engine.try_step(rid, body.step, body.projectId, max(0.1, min(1.0, body.strength)))
    except JobError as exc:
        raise _err(409, exc.message) from None


@app.post("/api/influence-runs/{rid}/stop")
async def stop_run(rid: str) -> dict:
    run = _run_or_404(rid)
    if run.get("jobId"):
        await sched.cancel(run["jobId"])
    return store.run(rid)


@app.delete("/api/influence-runs/{rid}")
async def delete_run(rid: str) -> dict:
    run = _run_or_404(rid)
    if run.get("jobId") and (j := store.job(run["jobId"])) and j["status"] in ("queued", "running"):
        raise _err(409, "Stop it first.")
    engine.tidy(run, everything=True)
    store.trash_run(rid)
    hub.publish("influenceRun", {"id": rid, "deleted": True})
    return {"ok": True}


# ---- media -------------------------------------------------------------------------------------

@app.get("/files/influence/{rid}/{path:path}")
async def influence_files(rid: str, path: str):
    root = (cfg.data / "influence" / rid).resolve()
    f = (root / path).resolve()
    if not f.is_relative_to(root) or not f.is_file():
        raise _err(404, "No such file.")
    return FileResponse(f, headers={"Cache-Control": "private, max-age=3600"})


@app.get("/files/{pid}/{path:path}")
async def files(pid: str, path: str):
    f = music_mod.project_file(cfg.projects, cfg.vrgdg_films, pid, path)
    if f is None:
        raise _err(404, "No such file.")
    return FileResponse(f, headers={"Cache-Control": "private, max-age=31536000, immutable"})


if cfg.web and (Path(cfg.web) / "index.html").is_file():
    app.mount("/assets", StaticFiles(directory=Path(cfg.web) / "assets"), name="assets")

    @app.get("/{path:path}")
    async def spa(path: str):
        return FileResponse(web_file(Path(cfg.web), path))
