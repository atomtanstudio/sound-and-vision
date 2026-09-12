"""Explicit live smoke run: one writing request, one cover and one reference transcription."""

import argparse, json, urllib.request
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--root", type=Path, required=True)
p.add_argument("--submit", action="store_true")
args = p.parse_args()
root = args.root
token = (root / "service.token").read_text().strip()
record = root / "assistance-verification.json"


def call(path, data=None, headers=None):
    req = urllib.request.Request(
        "http://127.0.0.1:5191/api" + path,
        data=data,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            **(headers or {}),
        },
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        return json.load(response)


account = call("/openai/account")
print(
    json.dumps(
        {
            "connected": account["connected"],
            "images": account["images"],
            "models": len(account["models"]),
        }
    )
)
if args.submit:
    if record.exists():
        raise SystemExit(
            "Existing run retained. Poll it instead of creating duplicate work."
        )
    payload = {
        "requestId": "assistance-smoke-20260910-01",
        "task": "Draft lyrics",
        "title": "Lanterns at Dawn",
        "style": "English indie folk, fingerpicked acoustic guitar, warm female vocal, 90 BPM",
        "prompt": "Write an original 60-word song about neighbours lighting lanterns before sunrise. One verse and one chorus. No artist imitation.",
    }
    writing = call("/assistance", json.dumps(payload).encode())
    take = "eabe44e7a8da4e8ca9cd8b92a94caa78"
    cover = call("/takes/" + take + "/cover", b"{}")
    audio = root / "data/runs" / take / "attempt-001/audio.mp3"
    reference = call(
        "/references?mode=melody",
        audio.read_bytes(),
        {
            "Content-Type": "application/octet-stream",
            "X-Filename": "City-Lights-reference.mp3",
        },
    )
    record.write_text(
        json.dumps(
            {
                "writing": writing["id"],
                "cover": cover["id"],
                "reference": reference["id"],
            },
            indent=2,
        )
        + "\n"
    )
jobs = json.loads(record.read_text())
result = {}
for kind, job_id in jobs.items():
    job = call("/assistance/" + job_id)
    result[kind] = job
    print(
        json.dumps(
            {
                "kind": kind,
                "id": job_id,
                "state": job["state"],
                "error": job.get("error"),
                "resultKeys": list((job.get("result") or {}).keys()),
            }
        )
    )
(root / "assistance-verification-result.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n"
)
