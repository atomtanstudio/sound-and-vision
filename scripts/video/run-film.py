"""Resume a Sound/Vision shot plan without duplicating completed generation jobs."""

import argparse
import fcntl
import json
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("/srv/ai/sound-vision"))
    parser.add_argument("--url", default="http://127.0.0.1:5191")
    args = parser.parse_args()
    folder = args.plan.parent
    lock = (folder / "batch.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    plan = json.loads(args.plan.read_text())
    token = (args.root / "service.token").read_text().strip()

    def api(path, data=None):
        body = json.dumps(data).encode() if data is not None else None
        request = urllib.request.Request(
            args.url + path,
            data=body,
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
            },
        )
        for attempt in range(10):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    return json.load(response)
            except urllib.error.HTTPError as error:
                if error.code < 500 or attempt == 9:
                    raise
            except (urllib.error.URLError, socket.timeout, ConnectionError):
                if attempt == 9:
                    raise
            # POSTs here use the same app-level requestId on each attempt.
            time.sleep(3)

    completed = []
    mappings_path = folder / "job-map.json"
    mappings = json.loads(mappings_path.read_text()) if mappings_path.exists() else {}
    for shot in plan["shots"]:
        request = shot["request"]
        # The API itself compares canonical payloads for existing request IDs.
        job = api(f"/api/takes/{plan['takeId']}/video", request)
        job_id = job["id"]
        mappings[request["requestId"]] = job_id
        mappings_path.write_text(json.dumps(mappings, indent=2) + "\n")
        while True:
            job = api(f"/api/assistance/{job_id}")
            status = {
                "state": job["state"],
                "currentShot": shot["index"] + 1,
                "totalShots": len(plan["shots"]),
                "name": shot["name"],
                "completed": completed,
                "jobId": job_id,
                "phase": (job.get("result") or {}).get("phase"),
                "updated": time.time(),
            }
            temp = folder / "batch-status.tmp"
            temp.write_text(json.dumps(status, indent=2) + "\n")
            temp.replace(folder / "batch-status.json")
            if job["state"] == "succeeded":
                completed.append(request["requestId"])
                print(
                    f"Completed {shot['index']+1}/{len(plan['shots'])}: {shot['name']}",
                    flush=True,
                )
                break
            if job["state"] in {"failed", "cancelled"}:
                raise RuntimeError(
                    f"Shot {shot['index']+1} needs recovery: {job.get('error')}"
                )
            time.sleep(15)
    (folder / "batch-status.json").write_text(
        json.dumps(
            {
                "state": "succeeded",
                "completed": completed,
                "totalShots": len(plan["shots"]),
                "updated": time.time(),
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
