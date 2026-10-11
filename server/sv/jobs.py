"""The one queue. Every GPU job (songs, stems and timing, later H3 scenes and renders) runs here,
one at a time; network jobs (writers, MCP tools) have their own lane. Jobs are rows in SQLite, so
they survive restarts: a job that was running when the server stopped is queued again (twice at
most). Each change is published to every open window."""

from __future__ import annotations

import asyncio
import logging
import time
import traceback
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from .comfy.client import Comfy, ComfyError
from .comfy.registry import Registry
from .config import Config
from .events import Hub
from .store import Store

log = logging.getLogger("sv.jobs")
LANES = ("gpu", "net", "cpu", "studio")  # cpu: renders (ffmpeg), so they never wait behind the GPU or the writers;
# studio: Claude's long code sessions (a living cover's finish), so they never hold up a render
MAX_ATTEMPTS = 3


class JobError(Exception):
    """A job failed for a reason the user should read; `detail` keeps the technical text."""

    def __init__(self, message: str, detail: Any = None):
        super().__init__(message)
        self.message, self.detail = message, detail


class Cancelled(Exception):
    pass


@dataclass
class Context:
    cfg: Config
    store: Store
    hub: Hub
    comfy: Comfy
    registry: Registry
    job: dict
    sched: "Scheduler"
    prompt_id: str | None = None
    proc: asyncio.subprocess.Process | None = None
    cancelled: bool = False
    _last: float = field(default=0.0)

    def update(self, stage: str | None = None, message: str | None = None, progress: float | None = None,
               force: bool = False, **extra: Any) -> None:
        """Report where the job is. Progress (0..1) is throttled to a few updates a second."""
        if self.cancelled:
            raise Cancelled()
        now = time.monotonic()
        if not force and stage is None and message is None and now - self._last < 0.25:
            return
        self._last = now
        fields: dict[str, Any] = dict(extra)
        if stage is not None:
            fields["stage"] = stage
        if message is not None:
            fields["message"] = message
        if progress is not None:
            fields["progress"] = round(max(0.0, min(1.0, progress)), 3)
        self.job = self.store.update_job(self.job["id"], **fields)
        self.hub.publish("job", self.job)

    def take_changed(self, take: dict) -> None:
        self.hub.publish("take", take)


Runner = Callable[[Context], Awaitable[dict | None]]


class Scheduler:
    def __init__(self, cfg: Config, store: Store, hub: Hub, comfy: Comfy, registry: Registry):
        self.cfg, self.store, self.hub, self.comfy, self.registry = cfg, store, hub, comfy, registry
        self.runners: dict[str, tuple[str, Runner]] = {}
        self.wake = {lane: asyncio.Event() for lane in LANES}
        self.running: dict[str, Context] = {}
        self.tasks: list[asyncio.Task] = []

    def register(self, kind: str, lane: str, runner: Runner) -> None:
        self.runners[kind] = (lane, runner)

    async def start(self) -> None:
        for j in self.store.jobs(("running",)):
            if j["attempts"] >= MAX_ATTEMPTS:
                self._finish(j["id"], "failed", message="Stopped when the server restarted, too many times.")
            else:
                self.store.update_job(j["id"], "queued", message="Waiting to start again after a restart.")
        for lane in LANES:
            self.tasks.append(asyncio.create_task(self._worker(lane), name=f"lane-{lane}"))

    async def stop(self) -> None:
        """A clean shutdown (a deploy): running jobs go back in the queue without using up an attempt."""
        for jid in list(self.running):
            self.store.requeue(jid, "Waiting to start again after a restart.")
        for t in self.tasks:
            t.cancel()

    def submit(self, kind: str, doc: dict, project_id: str | None = None, take_id: str | None = None) -> dict:
        lane, _ = self.runners[kind]
        job = self.store.create_job(kind, lane, {"message": "Waiting its turn", **doc}, project_id, take_id)
        self.hub.publish("job", job)
        self.wake[lane].set()
        return job

    async def cancel(self, jid: str) -> dict | None:
        job = self.store.job(jid)
        if not job or job["status"] not in ("queued", "running"):
            return job
        ctx = self.running.get(jid)
        if ctx is None:
            return self._finish(jid, "cancelled", message="Stopped.")
        ctx.cancelled = True
        if ctx.prompt_id:
            try:
                await self.comfy.cancel(ctx.prompt_id)
            except httpx.HTTPError:
                pass
        if ctx.proc and ctx.proc.returncode is None:
            ctx.proc.terminate()
        return self.store.job(jid)

    def _finish(self, jid: str, status: str, **fields: Any) -> dict:
        job = self.store.update_job(jid, status, **fields)
        self.hub.publish("job", job)
        return job

    async def free_gpu(self) -> None:
        """Before a GPU job: our ComfyUI keeps what it needs; other instances drop idle models (allowed by the user)."""
        if not self.cfg.free_others:
            return
        async with httpx.AsyncClient(timeout=4) as http:
            for base in self.cfg.other_comfys:
                try:
                    await http.post(f"{base}/free", json={"unload_models": True, "free_memory": True})
                except httpx.HTTPError:
                    pass

    async def _worker(self, lane: str) -> None:
        while True:
            job = self.store.next_job(lane)
            if job is None:
                self.wake[lane].clear()
                await self.wake[lane].wait()
                continue
            kind_lane, runner = self.runners.get(job["kind"], (lane, None))
            if runner is None:
                self._finish(job["id"], "failed", message=f"Nothing runs '{job['kind']}' jobs.")
                continue
            ctx = Context(self.cfg, self.store, self.hub, self.comfy, self.registry, job, self)
            self.running[job["id"]] = ctx
            ctx.job = self.store.update_job(job["id"], "running", message="Starting", progress=None)
            self.hub.publish("job", ctx.job)
            try:
                if lane == "gpu":
                    await self.free_gpu()
                result = await runner(ctx)
                self._finish(job["id"], "done", message="Done", progress=1.0, result=result or {})
            except Cancelled:
                self._finish(job["id"], "cancelled", message="Stopped.")
            except (JobError, ComfyError) as exc:
                if ctx.cancelled:
                    self._finish(job["id"], "cancelled", message="Stopped.")
                else:
                    self._finish(job["id"], "failed", message=exc.message, detail=str(exc.detail)[:4000] if exc.detail else None)
            except Exception as exc:  # anything unexpected: a plain message, the trace kept for us
                log.exception("job %s failed", job["id"])
                self._finish(job["id"], "failed", message="Something went wrong on the server.",
                             detail="".join(traceback.format_exception(exc))[-4000:])
            finally:
                self.running.pop(job["id"], None)
                hook = getattr(runner, "after", None)
                if hook:
                    try:
                        await hook(ctx, self.store.job(job["id"]))
                    except Exception:
                        log.exception("after-hook for %s failed", job["id"])
