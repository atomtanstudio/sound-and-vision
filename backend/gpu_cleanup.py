"""Release explicitly configured video caches after owned work, without interrupting jobs."""

import json
import logging
import subprocess
import threading
import time
from pathlib import Path

import httpx

log = logging.getLogger("soundvision.gpu_cleanup")


class VideoGpuCleanup:
    def __init__(self, data, urls, h3_url):
        self.folder = Path(data) / "gpu-cleanup"
        self.folder.mkdir(parents=True, exist_ok=True)
        self.urls = tuple(dict.fromkeys(url.rstrip("/") for url in urls))
        self.h3_url = h3_url.rstrip("/")
        self.pending = self.folder / "video-pending.json"
        self.receipt = self.folder / "video-last-release.json"
        self.lock = threading.Lock()
        self.retry_at = 0

    @staticmethod
    def write(path, value):
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, indent=2) + "\n")
        temporary.replace(path)

    def request(self, source):
        if not self.urls:
            return
        try:
            with self.lock:
                data = json.loads(self.pending.read_text()) if self.pending.exists() else {"sources": []}
                if source not in data["sources"]:
                    data["sources"].append(source)
                data["requested_at"] = time.time()
                self.write(self.pending, data)
        except (OSError, ValueError, KeyError, TypeError):
            # A cleanup failure must never discard an otherwise successful video.
            log.exception("Could not schedule video GPU cleanup")

    @staticmethod
    def free_mib():
        try:
            result = subprocess.run(
                ["nvidia-smi", "--id=0", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, check=True, timeout=5,
            )
            return int(result.stdout.strip())
        except (OSError, ValueError, subprocess.SubprocessError):
            return None

    @staticmethod
    def queue_idle(client, url):
        response = client.get(url + "/queue")
        response.raise_for_status()
        queue = response.json()
        if not isinstance(queue, dict) or any(not isinstance(queue.get(k), list) for k in ("queue_running", "queue_pending")):
            raise ValueError("Renderer returned an unverifiable queue.")
        return not queue["queue_running"] and not queue["queue_pending"]

    def run_if_idle(self, gpu_lock):
        if not self.urls or not self.pending.exists() or time.monotonic() < self.retry_at:
            return
        if not gpu_lock.acquire(blocking=False):
            return  # Keep the durable request until the local GPU owner finishes.
        result = {"at": time.time(), "targets": list(self.urls), "status": "deferred", "requested": []}
        try:
            with self.lock:
                if not self.pending.exists():
                    return
                pending = json.loads(self.pending.read_text())
            result["sources"] = pending["sources"]
            with httpx.Client(timeout=5, trust_env=False, follow_redirects=False) as client:
                response = client.get(self.h3_url + "/api/machine")
                response.raise_for_status()
                provider = response.json()
                if (not isinstance(provider, dict) or provider.get("online") is not True or
                        provider.get("busy") is not False or provider.get("activeJobId")):
                    result["reason"] = "Video provider is active or its idle state is unverified."
                    return
                # Check all explicitly opted-in renderers before making any change.
                if any(not self.queue_idle(client, url) for url in self.urls):
                    result["reason"] = "A video renderer has running or queued work."
                    return
                result["free_mib_before"] = self.free_mib()
                for url in self.urls:
                    # Catch a job arriving since the initial observation.
                    if not self.queue_idle(client, url):
                        result["reason"] = "A renderer started work before cleanup."
                        return
                    response = client.post(url + "/free", json={"unload_models": True, "free_memory": True})
                    response.raise_for_status()
                    result["requested"].append(url)
                # ComfyUI acknowledges before its worker performs the unload.
                time.sleep(1)
                result["free_mib_after"] = self.free_mib()
                result["status"] = "release_requested"
                with self.lock:
                    current = json.loads(self.pending.read_text())
                    remaining = [s for s in current["sources"] if s not in pending["sources"]]
                    if remaining:
                        current["sources"] = remaining
                        self.write(self.pending, current)
                    else:
                        self.pending.unlink()
        except (OSError, ValueError, KeyError, TypeError, httpx.HTTPError) as exc:
            result["reason"] = str(exc)
            log.warning("Video GPU cleanup deferred: %s", exc)
        finally:
            self.retry_at = time.monotonic() + (0 if result["status"] == "release_requested" else 15)
            try:
                self.write(self.receipt, result)
            except OSError:
                log.exception("Could not record video GPU cleanup")
            gpu_lock.release()
