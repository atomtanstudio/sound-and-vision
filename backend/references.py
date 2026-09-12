"""Private audio upload and serialized, cancellable reference transcription."""

import asyncio, contextlib, json, os, uuid
from pathlib import Path
from urllib.parse import unquote
from fastapi import APIRouter, HTTPException, Request

MAX_UPLOAD = 50 * 1024 * 1024


def routes(service, manager):
    router = APIRouter(prefix="/api")
    root = service.store.root.parent
    python = root / ".venv-reference/bin/python"
    lock = Path(
        os.environ.get(
            "SOUND_VISION_REFERENCE_LOCK", "/srv/ai/models/yue2/reference.lock.json"
        )
    )
    reference_limit = asyncio.Semaphore(1)

    async def transcribe(job_id, folder, source, mode):
        process = None
        acquired = False
        try:
            async with reference_limit:
                while True:
                    if manager.gpu_lock.acquire(blocking=False):
                        acquired = True
                        reason = await asyncio.to_thread(manager.gpu_ready)
                        if not reason:
                            await asyncio.sleep(1)
                            reason = await asyncio.to_thread(manager.gpu_ready)
                        if not reason:
                            break
                        manager.gpu_lock.release()
                        acquired = False
                    service.save(job_id, "waiting-for-resource")
                    await asyncio.sleep(3)
                service.save(job_id, "running")
                env = {
                    **os.environ,
                    "SOUND_VISION_REFERENCE_LOCK": str(lock),
                    "HF_HOME": str(lock.parent / "hf-cache"),
                    "HF_HUB_CACHE": str(lock.parent / "hf-cache"),
                    "HF_HUB_OFFLINE": "1",
                    "TRANSFORMERS_OFFLINE": "1",
                }
                with (folder / "worker.log").open("wb") as output:
                    process = await asyncio.create_subprocess_exec(
                        str(python),
                        str(Path(__file__).parent / "reference_runner.py"),
                        str(source),
                        str(folder),
                        mode,
                        env=env,
                        stdout=output,
                        stderr=output,
                    )
                    async with asyncio.timeout(1200):
                        while process.returncode is None:
                            await asyncio.sleep(2)
                            if await asyncio.to_thread(manager.competing_work):
                                raise RuntimeError(
                                    "Another GPU service started work. Transcription stopped; retry when it is idle."
                                )
                        if process.returncode:
                            failure = folder / "failure.json"
                            raise RuntimeError(
                                json.loads(failure.read_text())["message"]
                                if failure.exists()
                                else "Reference transcription failed. Worker log retained."
                            )
                return json.loads((folder / "result.json").read_text())
        finally:
            if process and process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), 8)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
            if acquired:
                manager.gpu_lock.release()

    @router.post("/references", status_code=202)
    async def upload(request: Request, mode: str = "melody"):
        if mode not in {"melody", "full"}:
            raise HTTPException(422, "Choose melody or full-score transcription.")
        if not python.is_file() or not lock.is_file():
            raise HTTPException(503, "Reference transcription is not installed.")
        name = Path(unquote(request.headers.get("x-filename", "audio.wav"))).name
        suffix = Path(name).suffix.lower()
        if suffix not in {".wav", ".flac", ".mp3", ".m4a", ".ogg"}:
            raise HTTPException(422, "Choose WAV, FLAC, MP3, M4A, or OGG audio.")
        job_id = uuid.uuid4().hex
        folder = service.store.root / "references" / job_id
        folder.mkdir(parents=True, mode=0o700)
        source = folder / ("source" + suffix)
        length = 0
        try:
            with source.open("xb") as stream:
                async for chunk in request.stream():
                    length += len(chunk)
                    if length > MAX_UPLOAD:
                        raise HTTPException(413, "Choose audio smaller than 50 MB.")
                    stream.write(chunk)
            if length == 0:
                raise HTTPException(422, "The uploaded audio is empty.")
        except BaseException:
            source.unlink(missing_ok=True)
            raise
        return service.submit(
            job_id,
            "reference",
            {"filename": name[:200], "mode": mode},
            lambda: transcribe(job_id, folder, source, mode),
            serialized=False,
        )

    return router
