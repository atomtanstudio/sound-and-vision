"""Explicit live inference verification. Creates one retained workflow-check take."""

import argparse, json, time, urllib.request
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--root", type=Path, required=True)
p.add_argument("--generate", action="store_true", required=True)
args = p.parse_args()
root = args.root
token = (root / "service.token").read_text().strip()
receipt = {"started_at": time.time(), "steps": []}


def call(path, body=None):
    r = urllib.request.Request(
        "http://127.0.0.1:5191/api" + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(r, timeout=20) as response:
        return json.load(response)


def save():
    (root / "lifecycle-verification.json").write_text(
        json.dumps(receipt, indent=2) + "\n"
    )


def record(text):
    receipt["steps"].append(text)
    save()
    print(text, flush=True)


def take():
    return next(t for t in call("/library")["tracks"] if t["id"] == receipt["take_id"])


def wait(states, timeout=180):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        result = take()
        if result["status"] in states:
            return result
        if result["status"] == "failed":
            raise RuntimeError(result["error"])
        time.sleep(0.5)
    raise TimeoutError("Timed out: " + json.dumps(take()))


source = json.loads((root / "baseline-request.json").read_text())
source["requestId"] = "lifecycle-yue2-20260910-01"
source["form"]["title"] = "Score review — workflow check"
source["form"]["planFirst"] = True
source["form"]["seed"] = "725"
response = call("/generations", source)
receipt["take_id"] = response["tracks"][0]["id"]
save()
initial = take()
if initial["status"] not in {"cancelled", "failed"}:
    call("/takes/" + receipt["take_id"] + "/cancel", {})
    wait({"cancelled"})
base_attempt = take()["attempt"]
call("/takes/" + receipt["take_id"] + "/retry", {})
wait({"running"})
call("/takes/" + receipt["take_id"] + "/cancel", {})
wait({"cancelled"})
record("Active owned generation cancelled; earlier attempts retained.")
call("/takes/" + receipt["take_id"] + "/retry", {})
review = wait({"needs-review"})
assert review["attempt"] == base_attempt + 2
record("Retry created a new attempt and paused for score review.")
plan = call("/takes/" + receipt["take_id"] + "/plan")
assert plan["abc"].strip()
receipt["score_characters"] = len(plan["abc"])
call("/takes/" + receipt["take_id"] + "/continue", {})
result = wait({"succeeded"})
assert result["attempt"] == base_attempt + 3
record("Unchanged exact plan approved; another attempt produced validated audio.")
receipt["delivery"] = result["delivery"]
receipt["status"] = "passed"
save()
print(
    json.dumps(
        {
            "take_id": receipt["take_id"],
            "duration": result["duration"],
            "truncated": result["truncated"],
        }
    ),
    flush=True,
)
