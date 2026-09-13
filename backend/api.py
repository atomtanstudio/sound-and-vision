"""Authenticated single-owner API, SQLite metadata and one owned GPU subprocess."""

from __future__ import annotations
import contextlib, dataclasses, fcntl, hashlib, json, logging, os, secrets, signal, sqlite3, subprocess, sys, threading, time, uuid
from pathlib import Path
from urllib.request import urlopen
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from .contracts import ContinuePlan, GenerationSubmission, TrackPatch
from .assistance import Assistance, routes as assistance_routes
from .references import routes as reference_routes
from .covers import routes as cover_routes, start_cover
from .library import routes as library_routes
from .song_import import routes as song_import_routes
from .video import routes as video_routes
from .film_review import FilmReviews, routes as film_routes

log = logging.getLogger("soundvision")
ROOT = Path(__file__).resolve().parent.parent
TERMINAL = {"succeeded", "failed", "cancelled", "needs-review"}
STAGE_LABELS = {
    "queued": "Queued",
    "waiting-for-resource": "Waiting for GPU",
    "loading": "Loading YuE2",
    "planning": "Planning score",
    "generating": "Generating music",
    "synthesizing": "Synthesizing audio",
    "decoding": "Decoding audio",
    "exporting": "Exporting audio",
    "needs-review": "Score ready for review",
    "complete": "Ready",
    "failed": "Failed",
    "cancelled": "Cancelled",
    "interrupted": "Interrupted",
}


def now():
    return int(time.time() * 1000)


def json_write(path, data):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(tmp, path)


@dataclasses.dataclass
class Settings:
    data: Path
    model: Path
    vae: Path
    token: str
    model_revision: str = "1a96eca688d6ae5d7f0feb88573fec89920fcd19"
    vae_revision: str = "95535e72a97bc0f09b8ada125d26b4009428c0e8"
    source_revision: str = "92a73cc7652fcc1f937855e4b765e0a0edd7ff2e"
    comfy_urls: tuple[str, ...] = ()
    min_free_mib: int = 23552

    @classmethod
    def from_env(cls):
        token = Path(os.environ["SOUND_VISION_TOKEN_FILE"]).read_text().strip()
        if len(token) < 32:
            raise RuntimeError(
                "Configure a random service token of at least32 characters."
            )
        return cls(
            Path(os.environ["SOUND_VISION_DATA"]).resolve(),
            Path(os.environ["SOUND_VISION_MODEL"]).resolve(),
            Path(os.environ["SOUND_VISION_VAE"]).resolve(),
            token,
            comfy_urls=tuple(
                u.rstrip("/")
                for u in os.environ.get("SOUND_VISION_COMFY_URLS", "").split(",")
                if u
            ),
            min_free_mib=int(os.environ.get("SOUND_VISION_MIN_FREE_MIB", "23552")),
        )


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        (self.root / "runs").mkdir(exist_ok=True)
        self.path = self.root / "library.sqlite3"
        with self.db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY)"
            )
            for path in sorted((ROOT / "db").glob("*.sql")):
                if not db.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=?", (path.name,)
                ).fetchone():
                    db.executescript(
                        "BEGIN IMMEDIATE;\n"
                        + path.read_text()
                        + f"\nINSERT INTO schema_migrations VALUES('{path.name}');\nCOMMIT;"
                    )

    @contextlib.contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=15000")
        try:
            yield db
        finally:
            db.close()

    def path_for(self, key):
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError("Invalid artifact path")
        return path

    def rows(self, include_deleted=False):
        with self.db() as db:
            rows = db.execute(
                """SELECT t.*, p.name AS project_name, r.request_json, j.id AS job_id, j.state AS job_state,
                j.stage,j.attempt,j.cancel_requested,j.progress_json,j.error,j.output_key FROM takes t
                JOIN projects p ON p.id=t.project_id JOIN generation_requests r ON r.id=t.request_id
                JOIN generation_jobs j ON j.take_id=t.id WHERE (? OR t.deleted_at IS NULL)
                ORDER BY t.created_at DESC,t.take_index""",
                (include_deleted,),
            ).fetchall()
        return [self.track(dict(row)) for row in rows]

    def track(self, row):
        with self.db() as db:
            cover = db.execute(
                "SELECT status,storage_key FROM assets WHERE take_id=? AND kind='cover'",
                (row["id"],),
            ).fetchone()
        progress = json.loads(row["progress_json"])
        duration = (row["duration_ms"] or 0) / 1000
        result = None
        if row["job_state"] == "succeeded" and row["output_key"]:
            file = self.path_for(row["output_key"]) / "delivery.json"
            if file.is_file():
                result = json.loads(file.read_text())
        stage = STAGE_LABELS.get(row["stage"], row["stage"])
        elapsed = progress.get("elapsed_seconds", 0)
        subtitle = f"Take {row['take_index']} · {stage}"
        if row["job_state"] == "running":
            subtitle += f" · {int(elapsed)//60}:{int(elapsed)%60:02}"
        if row["cancel_requested"] and row["job_state"] not in TERMINAL:
            subtitle = f"Take {row['take_index']} · Cancelling"
        return {
            "id": row["id"],
            "source": "imported" if row["stage"] == "imported" else "yue2",
            "title": row["title"],
            "subtitle": "Imported song" if row["stage"] == "imported" else subtitle,
            "project": row["project_name"],
            "favorite": bool(row["favorite"]),
            "created": row["created_at"],
            "deletedAt": row["deleted_at"],
            "form": json.loads(row["request_json"]),
            "requestId": row["request_id"],
            "take": row["take_index"],
            "seed": row["seed"],
            "duration": duration,
            "status": row["job_state"],
            "stage": row["stage"],
            "elapsed": elapsed,
            "attempt": row["attempt"],
            "error": row["error"],
            "warnings": (result or {}).get("warnings", []),
            "truncated": (result or {}).get("truncated"),
            "audioUrl": (
                f"/api/takes/{row['id']}/files/audio.mp3"
                if row["job_state"] == "succeeded"
                else None
            ),
            "coverStatus": (
                "ready"
                if cover and cover["status"] == "ready"
                else (
                    "requested"
                    if cover and cover["status"] == "requested"
                    else "unavailable"
                )
            ),
            "cover": (
                f"/api/takes/{row['id']}/cover?version={Path(cover['storage_key']).stem}"
                if cover and cover["status"] == "ready"
                else None
            ),
            "sampleRate": (result or {}).get("sample_rate"),
            "delivery": result,
        }

    def job(self, take_id):
        with self.db() as db:
            row = db.execute(
                """SELECT j.*,t.seed,t.take_index,t.request_id,t.deleted_at,r.request_json FROM generation_jobs j
                JOIN takes t ON t.id=j.take_id JOIN generation_requests r ON r.id=t.request_id WHERE j.take_id=?""",
                (take_id,),
            ).fetchone()
        if not row:
            raise HTTPException(404, "Take not found")
        if row["deleted_at"] is not None:
            raise HTTPException(409, "Restore this track from Trash first.")
        return dict(row)

    def update_job(self, take_id, state, stage, error=None, progress=None):
        take_state = {
            "succeeded": "ready",
            "needs-review": "draft",
            "waiting-for-resource": "queued",
        }.get(state, state)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if state == "waiting-for-resource":
                current = db.execute(
                    "SELECT state,cancel_requested FROM generation_jobs WHERE take_id=?",
                    (take_id,),
                ).fetchone()
                if (
                    not current
                    or current["cancel_requested"]
                    or current["state"] not in {"queued", "waiting-for-resource"}
                ):
                    db.rollback()
                    return
            db.execute(
                "UPDATE generation_jobs SET state=?,stage=?,error=?,progress_json=COALESCE(?,progress_json),updated_at=? WHERE take_id=?",
                (
                    state,
                    stage,
                    error,
                    json.dumps(progress) if progress is not None else None,
                    now(),
                    take_id,
                ),
            )
            db.execute(
                "UPDATE takes SET status=?,updated_at=? WHERE id=?",
                (take_state, now(), take_id),
            )
            request = db.execute(
                "SELECT request_id FROM takes WHERE id=?", (take_id,)
            ).fetchone()[0]
            states = [
                r[0]
                for r in db.execute(
                    "SELECT j.state FROM generation_jobs j JOIN takes t ON t.id=j.take_id WHERE t.request_id=?",
                    (request,),
                )
            ]
            status = (
                "completed"
                if all(s == "succeeded" for s in states)
                else (
                    "cancelled"
                    if all(s == "cancelled" for s in states)
                    else (
                        "failed"
                        if all(
                            s in {"failed", "cancelled", "succeeded"} for s in states
                        )
                        else (
                            "preparing"
                            if all(s in TERMINAL for s in states)
                            else "running" if "running" in states else "queued"
                        )
                    )
                )
            )
            db.execute(
                "UPDATE generation_requests SET status=?,updated_at=? WHERE id=?",
                (status, now(), request),
            )
            db.commit()


class Manager:
    def __init__(self, settings, store):
        self.settings = settings
        self.store = store
        self.stop = threading.Event()
        self.thread = None
        self.process = None
        self.server_lock = None
        self.gpu_lock = threading.Lock()

    def start(self):
        self.server_lock = open(self.store.root / "service.lock", "a")
        try:
            fcntl.flock(self.server_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another Sound/Vision service owns this data directory.")
        with self.store.db() as db:
            interrupted = [
                r[0]
                for r in db.execute(
                    "SELECT take_id FROM generation_jobs WHERE state='running'"
                )
            ]
        for take in interrupted:
            self.store.update_job(
                take,
                "failed",
                "interrupted",
                "Service restarted during generation. Partial artifacts retained; retry starts a new attempt.",
            )
        self.thread = threading.Thread(
            target=self.loop, name="soundvision-queue", daemon=True
        )
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        if self.thread:
            self.thread.join(timeout=10)
        if self.server_lock:
            self.server_lock.close()

    def competing_work(self):
        for url in self.settings.comfy_urls:
            try:
                with urlopen(url + "/queue", timeout=3) as response:
                    queue = json.load(response)
                if queue.get("queue_running") or queue.get("queue_pending"):
                    return f"Waiting for existing ComfyUI work at {url}."
            except Exception:
                return f"Cannot verify the external GPU queue at {url}."
        return None

    def gpu_ready(self):
        if (
            not (self.settings.model / "model.safetensors").is_file()
            or not (self.settings.vae / "model.safetensors").is_file()
        ):
            return "Pinned model files are not installed."
        external = self.competing_work()
        if external:
            return external
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=memory.free,utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
            free, util = [
                int(v.strip()) for v in result.stdout.splitlines()[0].split(",")
            ]
            if free < self.settings.min_free_mib:
                return f"Waiting for GPU memory: {free} MiB free; {self.settings.min_free_mib} MiB required."
            if util > 15:
                return "Waiting for other GPU activity to finish."
        except Exception:
            return "GPU status unavailable."
        return None

    def loop(self):
        while not self.stop.wait(2):
            try:
                with self.store.db() as db:
                    row = db.execute(
                        "SELECT take_id FROM generation_jobs WHERE state IN ('queued','waiting-for-resource') AND take_id IN (SELECT id FROM takes WHERE deleted_at IS NULL) ORDER BY created_at LIMIT 1"
                    ).fetchone()
                if not row:
                    continue
                take = row[0]
                reason = self.gpu_ready()
                if reason:
                    self.store.update_job(
                        take, "waiting-for-resource", "waiting-for-resource", reason
                    )
                    continue
                # A second observation catches jobs starting during the initial probe.
                if self.stop.wait(1):
                    break
                reason = self.gpu_ready()
                if reason:
                    self.store.update_job(
                        take, "waiting-for-resource", "waiting-for-resource", reason
                    )
                    continue
                if not self.gpu_lock.acquire(blocking=False):
                    self.store.update_job(
                        take,
                        "waiting-for-resource",
                        "waiting-for-resource",
                        "Waiting for the current local GPU task.",
                    )
                    continue
                try:
                    reason = self.gpu_ready()
                    if not reason:
                        self.run_take(take)
                    else:
                        self.store.update_job(
                            take, "waiting-for-resource", "waiting-for-resource", reason
                        )
                finally:
                    self.gpu_lock.release()
            except Exception as exc:
                log.exception("Queue operation failed; artifacts retained")
                if self.process and self.process.poll() is None:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait()
                    self.process = None
                try:
                    if self.store.job(take)["state"] == "running":
                        self.store.update_job(take, "failed", "failed", str(exc)[:2000])
                except Exception:
                    log.exception("Could not update interrupted job")

    def run_take(self, take):
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute(
                "UPDATE generation_jobs SET state='running',stage='loading',attempt=attempt+1,error=NULL,updated_at=? WHERE take_id=? AND state IN ('queued','waiting-for-resource') AND cancel_requested=0",
                (now(), take),
            ).rowcount
            if not changed:
                db.rollback()
                return
            db.execute(
                "UPDATE takes SET status='running',updated_at=? WHERE id=?",
                (now(), take),
            )
            db.commit()
        job = self.store.job(take)
        form = json.loads(job["request_json"])
        key = f"runs/{take}/attempt-{job['attempt']:03}"
        out = self.store.path_for(key)
        out.mkdir(parents=True, exist_ok=False)
        with self.store.db() as db:
            db.execute(
                "UPDATE generation_jobs SET output_key=? WHERE take_id=?", (key, take)
            )
        song = {
            "id": take,
            "style": form["style"].strip() or form["description"].strip(),
            "lyrics": form["lyrics"],
            "cot": form["cot"],
            "seed": int(job["seed"]),
        }
        if form["cot"] != "off" and form["abc"].strip():
            song["abc"] = form["abc"]
        if form["cfg_scale"]:
            song["cfg_scale"] = float(form["cfg_scale"])
        spec = {
            "song": song,
            "generation": {
                "abc": form["score"],
                "semantic": form["semantic"],
                "ode_steps": form["ode_steps"],
            },
            "model": str(self.settings.model),
            "vae": str(self.settings.vae),
            "source_revision": self.settings.source_revision,
            "model_revision": self.settings.model_revision,
            "vae_revision": self.settings.vae_revision,
            "output": str(out),
            "plan_first": form["planFirst"]
            and form["cot"] != "off"
            and not job["resume_plan_key"],
            "resume_plan": (
                str(self.store.path_for(job["resume_plan_key"]))
                if job["resume_plan_key"]
                else None
            ),
            "edited_abc": job["edited_abc"],
        }
        json_write(out / "spec.json", spec)
        conflict = None
        cancel_started = None
        monitor = 0
        with open(out / "worker.log", "w") as output:
            self.process = subprocess.Popen(
                [sys.executable, "-m", "backend.runner", str(out / "spec.json")],
                cwd=ROOT,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            while self.process.poll() is None:
                if self.stop.wait(1):
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                    break
                current = self.store.job(take)
                # Never interrupt another service. Yield by cancelling only our process if its queue becomes active.
                if time.monotonic() - monitor > 5:
                    external = self.competing_work()
                    monitor = time.monotonic()
                    if external:
                        conflict = external
                if current["cancel_requested"] or conflict:
                    (out / "cancel").touch()
                    if cancel_started is None:
                        cancel_started = time.monotonic()
                    if time.monotonic() - cancel_started > 8:
                        self.process.terminate()
                    if time.monotonic() - cancel_started > 15:
                        self.process.kill()
                progress = out / "progress.json"
                if progress.exists():
                    try:
                        data = json.loads(progress.read_text())
                        self.store.update_job(
                            take, "running", data["stage"], progress=data
                        )
                    except (ValueError, OSError):
                        pass
            code = self.process.wait()
            self.process = None
        if self.stop.is_set():
            self.store.update_job(
                take,
                "failed",
                "interrupted",
                "Service stopped; artifacts retained. Retry starts a new attempt.",
            )
            return
        if conflict:
            self.store.update_job(
                take,
                "failed",
                "interrupted",
                "Yielded to another GPU service. "
                + conflict
                + " Retry when the shared GPU is idle.",
            )
            return
        if self.store.job(take)["cancel_requested"]:
            self.store.update_job(
                take,
                "cancelled",
                "cancelled",
                "Cancelled by user; partial artifacts retained.",
            )
            return
        if code == 0 and (out / "plan-ready.json").exists():
            self.store.update_job(take, "needs-review", "needs-review")
            return
        if code != 0 or not (out / "delivery.json").is_file():
            failure = (
                json.loads((out / "failure.json").read_text())
                if (out / "failure.json").exists()
                else {
                    "message": f"Worker exited with code{code}. See retained worker log."
                }
            )
            self.store.update_job(
                take, "failed", "failed", str(failure["message"])[:2000]
            )
            return
        delivery = json.loads((out / "delivery.json").read_text())
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "UPDATE takes SET duration_ms=? WHERE id=?",
                (round(delivery["duration"] * 1000), take),
            )
            for fmt in ["flac", "wav", "mp3"]:
                db.execute(
                    "INSERT INTO assets(id,take_id,kind,format,storage_key,status,provider,model,created_at) VALUES(?,?,'audio',?,?,'ready','local','YuE2-3B',?) ON CONFLICT(take_id,kind,format) DO UPDATE SET storage_key=excluded.storage_key,status='ready'",
                    (uuid.uuid4().hex, take, fmt, f"{key}/audio.{fmt}", now()),
                )
            db.commit()
        self.store.update_job(
            take,
            "succeeded",
            "complete",
            progress={"elapsed_seconds": delivery["timing"]["e2e_seconds"]},
        )


def create_app(settings=None, start_worker=True):
    settings = settings or Settings.from_env()
    store = Store(settings.data)
    manager = Manager(settings, store)
    assistance = Assistance(store)
    assistance.account.manager = manager
    films = FilmReviews(store, manager, assistance.account, assistance=assistance)

    @contextlib.asynccontextmanager
    async def lifespan(app):
        if start_worker:
            manager.start()
            assistance.recover()
            if os.environ.get("SOUND_VISION_ENABLE_MUSIC_VIDEO") == "1":
                films.recover()
        yield
        await films.close()
        await assistance.close()
        if start_worker:
            manager.close()

    app = FastAPI(
        title="Sound/Vision music service",
        version="0.2.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.store = store
    app.state.manager = manager
    app.state.assistance = assistance
    app.state.films = films
    app.include_router(assistance_routes(assistance))
    app.include_router(reference_routes(assistance, manager))
    app.include_router(cover_routes(assistance))
    app.include_router(library_routes(store))
    app.include_router(song_import_routes(store))
    app.include_router(video_routes(assistance, manager))
    app.include_router(film_routes(films))

    @app.middleware("http")
    async def protect(request: Request, call_next):
        from fastapi.responses import JSONResponse

        # Token stays in the trusted development proxy/service configuration, never in browser bundles.
        supplied = request.headers.get("authorization", "")
        if not secrets.compare_digest(supplied, "Bearer " + settings.token):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        path = request.url.path
        if (os.environ.get("SOUND_VISION_ENABLE_MUSIC_VIDEO") != "1" and request.method == "POST" and
            (path == "/api/films" or path.startswith("/api/films/")) and
            path != "/api/films/credits/preview" and not path.endswith('/cancel')):
            return JSONResponse({"detail": "Music video is coming soon. Existing projects are preserved."}, status_code=409)
        length = request.headers.get("content-length")
        max_length = (
            50 * 1024 * 1024 if request.url.path == "/api/references" else 1024 * 1024
        )
        if length and (not length.isdigit() or int(length) > max_length):
            return JSONResponse({"detail": "Request too large"}, status_code=413)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/api/health")
    def health():
        ready = (settings.model / "model.safetensors").is_file() and (
            settings.vae / "model.safetensors"
        ).is_file()
        return {
            "service": "sound-vision",
            "features": {"musicVideo": os.environ.get("SOUND_VISION_ENABLE_MUSIC_VIDEO") == "1"},
            "connected": True,
            "generation": ready,
            "model": "YuE2-3B",
            "model_revision": settings.model_revision,
            "decoder": "YuE2-Vae",
            "decoder_revision": settings.vae_revision,
            "source_revision": settings.source_revision,
            "sample_rate": 48000,
            "channels": 2,
            "backend": "torch",
            "quantization": "none",
            "formats": ["wav", "flac", "mp3"],
            "requires_lyrics": True,
            "writing": assistance.account.connected,
            "covers": assistance.account.connected
            and assistance.account.image_generation,
            "weight_license": "CC-BY-NC-4.0",
            "queue": "persistent-single-worker",
            "database": "sqlite",
            "gpu_policy": "Observe external queues; never unload or interrupt other services.",
        }

    @app.get("/api/library")
    def library(include_deleted: bool = False):
        return {"tracks": store.rows(include_deleted=include_deleted)}

    @app.post("/api/generations", status_code=202)
    async def submit(payload: GenerationSubmission):
        form = payload.form.model_dump()
        if form.get("sourceTakeId"):
            store.job(form["sourceTakeId"])
        if form.get("referenceId"):
            reference = assistance.get(form["referenceId"])
            if reference["kind"] != "reference" or reference["state"] != "succeeded":
                raise HTTPException(422, "Use a completed reference transcription.")
        canonical = json.dumps(form, sort_keys=True)
        stamp = now()
        request_id = payload.requestId
        with store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT request_json FROM generation_requests WHERE id=?", (request_id,)
            ).fetchone()
            if existing:
                db.rollback()
                if existing["request_json"] != canonical:
                    raise HTTPException(
                        409, "This request ID already belongs to different inputs."
                    )
                return {
                    "requestId": request_id,
                    "tracks": [t for t in store.rows() if t["requestId"] == request_id],
                    "reused": True,
                }
            project_id = hashlib.sha256(form["project"].encode()).hexdigest()[:32]
            db.execute(
                "INSERT OR IGNORE INTO projects VALUES(?,?,?,?)",
                (project_id, form["project"], stamp, stamp),
            )
            db.execute(
                "INSERT INTO generation_requests VALUES(?,?,?,?,?,?,?,?)",
                (
                    request_id,
                    project_id,
                    form["title"] or form["description"][:44] or "Untitled",
                    canonical,
                    form["count"],
                    "queued",
                    stamp,
                    stamp,
                ),
            )
            for index in range(1, form["count"] + 1):
                take = uuid.uuid4().hex
                seed = (
                    (int(form["seed"]) + index - 1) % (2**63)
                    if form["seed"]
                    else secrets.randbelow(2**63)
                )
                db.execute(
                    "INSERT INTO takes(id,request_id,project_id,take_index,title,style_summary,status,seed,created_at,updated_at) VALUES(?,?,?,?,?,?,'queued',?,?,?)",
                    (
                        take,
                        request_id,
                        project_id,
                        index,
                        form["title"].strip() or form["description"][:44] or "Untitled",
                        form["style"] or form["description"],
                        str(seed),
                        stamp + index,
                        stamp,
                    ),
                )
                db.execute(
                    "INSERT INTO generation_jobs(id,take_id,state,created_at,updated_at) VALUES(?,?,'queued',?,?)",
                    (uuid.uuid4().hex, take, stamp + index, stamp),
                )
                db.execute(
                    "INSERT INTO assets(id,take_id,kind,format,status,provider,model,prompt,created_at) VALUES(?,?,'cover','png','requested',?,?,?,?)",
                    (
                        uuid.uuid4().hex,
                        take,
                        'comfyui' if assistance.account.config.provider=='local' else 'openai',
                        assistance.account.image_model,
                        f"{form['title']}. {form['description'] or form['style']}. Distinct cover for take{index}.",
                        stamp,
                    ),
                )
            db.commit()
        if (assistance.account.connected and assistance.account.image_generation) or assistance.account.config.provider == 'local':
            for track in store.rows():
                if track["requestId"] == request_id:
                    try:
                        start_cover(assistance, track["id"], "cover-" + track["id"])
                    except Exception:
                        log.exception(
                            "Cover setup failed; music generation remains queued"
                        )
        return {
            "requestId": request_id,
            "tracks": [t for t in store.rows() if t["requestId"] == request_id],
            "reused": False,
        }

    @app.patch("/api/takes/{take_id}")
    def patch(take_id: str, change: TrackPatch):
        store.job(take_id)
        with store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if (
                db.execute(
                    "SELECT deleted_at FROM takes WHERE id=?", (take_id,)
                ).fetchone()[0]
                is not None
            ):
                raise HTTPException(409, "Restore this track from Trash first.")
            if change.title is not None:
                db.execute(
                    "UPDATE takes SET title=? WHERE id=?", (change.title, take_id)
                )
            if change.favorite is not None:
                db.execute(
                    "UPDATE takes SET favorite=? WHERE id=?",
                    (int(change.favorite), take_id),
                )
            if change.project is not None:
                project_id = hashlib.sha256(change.project.encode()).hexdigest()[:32]
                db.execute(
                    "INSERT OR IGNORE INTO projects VALUES(?,?,?,?)",
                    (project_id, change.project, now(), now()),
                )
                db.execute(
                    "UPDATE takes SET project_id=? WHERE id=?", (project_id, take_id)
                )
            db.execute("UPDATE takes SET updated_at=? WHERE id=?", (now(), take_id))
            db.commit()
        return next(t for t in store.rows() if t["id"] == take_id)

    @app.post("/api/takes/{take_id}/cancel")
    def cancel(take_id: str):
        with store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT state FROM generation_jobs WHERE take_id=?", (take_id,)
            ).fetchone()
            if not row:
                db.rollback()
                raise HTTPException(404, "Take not found")
            if row[0] in {"succeeded", "failed", "cancelled"}:
                db.rollback()
                raise HTTPException(409, "This take is no longer running.")
            db.execute(
                "UPDATE generation_jobs SET cancel_requested=1 WHERE take_id=?",
                (take_id,),
            )
            db.commit()
        if row[0] != "running":
            store.update_job(
                take_id, "cancelled", "cancelled", "Cancelled before generation."
            )
        return {"status": "cancel-requested"}

    @app.post("/api/takes/{take_id}/retry")
    def retry(take_id: str):
        store.job(take_id)
        with store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute(
                "UPDATE generation_jobs SET state='queued',stage='queued',cancel_requested=0,error=NULL,progress_json='{}',updated_at=? WHERE take_id=? AND state IN ('failed','cancelled') AND take_id IN (SELECT id FROM takes WHERE deleted_at IS NULL)",
                (now(), take_id),
            ).rowcount
            if not changed:
                raise HTTPException(
                    409, "Only failed or cancelled takes can be retried."
                )
            db.execute("UPDATE takes SET status='queued' WHERE id=?", (take_id,))
            db.commit()
        return {"status": "queued"}

    @app.get("/api/takes/{take_id}/plan")
    def plan(take_id: str):
        job = store.job(take_id)
        if not job["output_key"]:
            raise HTTPException(409, "No plan has been saved.")
        file = store.path_for(job["output_key"]) / "plan" / "score.abc"
        if not file.is_file():
            raise HTTPException(409, "This take has no symbolic score.")
        return {"abc": file.read_text(), "reviewable": job["state"] == "needs-review"}

    @app.post("/api/takes/{take_id}/continue")
    def continue_plan(take_id: str, body: ContinuePlan):
        job = store.job(take_id)
        if job["state"] != "needs-review":
            raise HTTPException(409, "This take is not waiting for score review.")
        if body.abc is not None and not body.abc.strip():
            raise HTTPException(422, "Edited score cannot be blank.")
        with store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute(
                "UPDATE generation_jobs SET state='queued',stage='queued',resume_plan_key=?,edited_abc=?,progress_json='{}',updated_at=? WHERE take_id=? AND state='needs-review' AND take_id IN (SELECT id FROM takes WHERE deleted_at IS NULL)",
                (job["output_key"] + "/plan", body.abc, now(), take_id),
            ).rowcount
            if not changed:
                raise HTTPException(409, "The plan was already continued.")
            db.commit()
        return {"status": "queued"}

    @app.get("/api/takes/{take_id}/files/{filename}")
    def file(take_id: str, filename: str):
        job = store.job(take_id)
        allowed = {
            "audio.wav",
            "audio.flac",
            "audio.mp3",
            "score.abc",
            "plan.json",
            "request.json",
            "config.json",
            "result.json",
            "delivery.json",
            "latent.npy",
            "semantic.npy",
            "worker.log",
        }
        if filename not in allowed or not job["output_key"]:
            raise HTTPException(404, "Artifact not found")
        if filename.startswith("audio.") and job["state"] != "succeeded":
            raise HTTPException(409, "Audio has not passed validation.")
        path = store.path_for(job["output_key"]) / filename
        if not path.is_file():
            raise HTTPException(404, "Artifact not found")
        return FileResponse(
            path,
            filename=filename,
            media_type={
                "mp3": "audio/mpeg",
                "wav": "audio/wav",
                "flac": "audio/flac",
                "json": "application/json",
            }.get(path.suffix[1:], "application/octet-stream"),
        )

    return app
