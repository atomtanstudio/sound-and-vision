#!/usr/bin/env python3
"""Pictures for this video, made by the Sound / Vision app with whatever the person chose for them in Settings (ChatGPT's
image tool, Grok Imagine, or an image model on the machine's GPU), one at a time, in the order sent, while this session
runs. (Copied into a music video's folder as tools/picture.py.)

  python3 tools/picture.py "PROMPT" --out shots/s01.png [--shape 16:9] [--ref PICTURE ...]
  python3 tools/picture.py --prompt-file prompts/s01.txt --out shots/s01.png
  python3 tools/picture.py ... --no-wait          send it and print its id at once (collect it later with --wait)
  python3 tools/picture.py --wait ID [ID ...]     wait for pictures sent with --no-wait

--shape is 16:9 (the default), 1:1, 9:16, 4:5 or 3:2. --ref gives up to five pictures of the same person, place or
thing to keep (a source that can't use them says so). Paths are inside this folder. Each finished picture prints
one JSON line: {"ok": true, "out": ..., "by": ...} or {"ok": false, "error": ...}; the exit code is 0 only if every
picture came back.
"""

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE, DONE = ROOT / "pictures" / "queue", ROOT / "pictures" / "done"
SHAPES = ("16:9", "1:1", "9:16", "4:5", "3:2")


def rel(p: str) -> str:
    path = (Path.cwd() / p).resolve()
    if ROOT not in path.parents:
        sys.exit(f"{p} is not inside {ROOT}")
    return str(path.relative_to(ROOT))


def send(a: argparse.Namespace) -> str:
    prompt = Path(a.prompt_file).read_text() if a.prompt_file else a.prompt
    if not prompt or not prompt.strip():
        sys.exit("Give a prompt (as the first argument, or --prompt-file).")
    if a.shape not in SHAPES:
        sys.exit(f"--shape is one of {', '.join(SHAPES)}")
    if not a.out.lower().endswith((".png", ".jpg", ".jpeg")):
        sys.exit("--out is a .png or .jpg file")
    for r in a.ref or []:
        if not (Path.cwd() / r).is_file():
            sys.exit(f"There's no picture at {r}")
    req = {"prompt": prompt, "out": rel(a.out), "shape": a.shape, "refs": [rel(r) for r in (a.ref or [])][:5]}
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
            print(f"… {len(left)} picture(s) being made or waiting ({ahead} in the queue), {time.time() - start:.0f} s so far",
                  file=sys.stderr, flush=True)
        time.sleep(2)
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("prompt", nargs="?")
    ap.add_argument("--prompt-file")
    ap.add_argument("--out")
    ap.add_argument("--shape", default="16:9")
    ap.add_argument("--ref", action="append", metavar="PICTURE")
    ap.add_argument("--no-wait", action="store_true")
    ap.add_argument("--wait", nargs="+", metavar="ID")
    ap.add_argument("--timeout", type=float, default=1800)
    a = ap.parse_args()
    if a.wait:
        return wait(a.wait, a.timeout)
    if not a.out:
        ap.error("give a PROMPT and --out (or --wait)")
    rid = send(a)
    if a.no_wait:
        print(rid)
        return 0
    return wait([rid], a.timeout)


if __name__ == "__main__":
    sys.exit(main())
