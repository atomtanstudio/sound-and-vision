#!/usr/bin/env python3
"""MiniMax H3 on the machine's GPU: bring a still to life. The Sound / Vision app renders each request, one at a time, in
the order sent, while this session runs. (Copied into a music video's folder as tools/h3.py.)

  python3 tools/h3.py STILL "PROMPT" --out clips/s01.mp4 [--seconds 6] [--size 1344x768] [--end STILL] [--seed N]
  python3 tools/h3.py STILL --prompt-file prompts/s01.txt --out clips/s01.mp4
  python3 tools/h3.py ... --no-wait          send it and print its id at once (collect it later with --wait)
  python3 tools/h3.py --wait ID [ID ...]     wait for clips sent with --no-wait
  python3 tools/h3.py --queue                what's still waiting to be rendered

STILL is the clip's first frame. --end pins its last frame too (the clip travels from one picture to the other).
Paths are inside this folder. Each finished clip prints one JSON line: {"ok": true, "out": ..., "seconds": ...,
"renderSeconds": ...} or {"ok": false, "error": ...}; the exit code is 0 only if every clip came back.
"""

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE, DONE = ROOT / "h3" / "queue", ROOT / "h3" / "done"


def rel(p: str) -> str:
    path = (Path.cwd() / p).resolve()
    if ROOT not in path.parents:
        sys.exit(f"{p} is not inside {ROOT}")
    return str(path.relative_to(ROOT))


def send(a: argparse.Namespace) -> str:
    prompt = Path(a.prompt_file).read_text() if a.prompt_file else a.prompt
    if not prompt or not prompt.strip():
        sys.exit("Give a prompt (as the second argument, or --prompt-file).")
    if not (Path.cwd() / a.still).is_file():
        sys.exit(f"There's no still at {a.still}")
    w, _, h = a.size.lower().partition("x")
    req = {"image": rel(a.still), "prompt": prompt, "out": rel(a.out), "seconds": a.seconds, "width": int(w), "height": int(h)}
    if a.end:
        req["end"] = rel(a.end)
    if a.seed is not None:
        req["seed"] = a.seed
    rid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    QUEUE.mkdir(parents=True, exist_ok=True)
    tmp = QUEUE / f".{rid}.tmp"
    tmp.write_text(json.dumps(req))
    os.replace(tmp, QUEUE / f"{rid}.json")  # whole, or not there at all
    return rid


def wait(ids: list[str], timeout: float) -> int:
    start, bad, left = time.time(), 0, list(ids)
    told = start
    while left:
        for rid in list(left):
            f = DONE / f"{rid}.json"
            if f.exists():
                answer = json.loads(f.read_text())
                print(json.dumps({"id": rid, **answer}), flush=True)
                bad += not answer.get("ok")
                left.remove(rid)
        if not left:
            break
        if time.time() - start > timeout:
            print(json.dumps({"ok": False, "error": f"still waiting after {timeout:.0f} s", "waiting": left}), flush=True)
            return 1
        if time.time() - told > 60:
            told = time.time()
            ahead = len(list(QUEUE.glob("*.json"))) if QUEUE.is_dir() else 0
            print(f"… {len(left)} clip(s) rendering or waiting ({ahead} in the queue), {time.time() - start:.0f} s so far",
                  file=sys.stderr, flush=True)
        time.sleep(3)
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("still", nargs="?")
    ap.add_argument("prompt", nargs="?")
    ap.add_argument("--prompt-file")
    ap.add_argument("--out")
    ap.add_argument("--seconds", type=float, default=6.0)
    ap.add_argument("--size", default="1344x768")
    ap.add_argument("--end")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--no-wait", action="store_true")
    ap.add_argument("--wait", nargs="+", metavar="ID")
    ap.add_argument("--queue", action="store_true")
    ap.add_argument("--timeout", type=float, default=3600)
    a = ap.parse_args()
    if a.queue:
        for f in sorted(QUEUE.glob("*.json"), key=lambda f: f.stat().st_mtime) if QUEUE.is_dir() else []:
            print(f.stem, json.loads(f.read_text()).get("out"))
        return 0
    if a.wait:
        return wait(a.wait, a.timeout)
    if not a.still or not a.out:
        ap.error("give a STILL and --out (or --wait / --queue)")
    rid = send(a)
    if a.no_wait:
        print(rid)
        return 0
    return wait([rid], a.timeout)


if __name__ == "__main__":
    sys.exit(main())
