#!/usr/bin/env python3
"""VRGameDevGirl's Video Builder on this machine: run one of the H3 film skill's scripts on this project, inside the ComfyUI
container that has her nodes (the Sound / Vision app runs it for you). Copied into a music video's folder as
tools/vrgdg.py; the skill's guide is reference/SKILL.md.

  python3 tools/vrgdg.py song_plan.py . [args]              run it and print what it prints
  python3 tools/vrgdg.py --no-wait render_scenes.py . 1 2 3  start it and print an id at once (a render takes minutes)
  python3 tools/vrgdg.py --wait ID [ID ...]                 wait for runs started with --no-wait, printing their output
  python3 tools/vrgdg.py --list                             what's running or waiting

"." is this project (any path starting with ./ is inside it). Each run's whole output is kept in vrgdg/logs/<id>.log,
so `tail -n 20 vrgdg/logs/<id>.log` shows how a long one is going. Renders (render_scenes.py) run one at a time; other
scripts run at once. The exit code is the script's own.
"""

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE, DONE, LOGS = ROOT / "vrgdg" / "queue", ROOT / "vrgdg" / "done", ROOT / "vrgdg" / "logs"


def send(script: str, args: list[str]) -> str:
    rid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    QUEUE.mkdir(parents=True, exist_ok=True)
    tmp = QUEUE / f".{rid}.tmp"
    tmp.write_text(json.dumps({"script": script, "args": args}))
    os.replace(tmp, QUEUE / f"{rid}.json")
    return rid


def wait(ids: list[str], timeout: float, quiet: bool = False) -> int:
    start, code, left = time.time(), 0, list(ids)
    seen: dict[str, int] = {}
    while left:
        for rid in list(left):
            log = LOGS / f"{rid}.log"
            if not quiet and log.exists():  # stream what it has printed since last time
                text = log.read_text(errors="replace")
                new = text[seen.get(rid, 0):]
                if new:
                    sys.stdout.write(new)
                    sys.stdout.flush()
                    seen[rid] = len(text)
            done = DONE / f"{rid}.json"
            if done.exists():
                answer = json.loads(done.read_text())
                if answer.get("error"):
                    print(f"[{rid}] {answer['error']}", file=sys.stderr)
                code = code or (0 if answer.get("ok") else int(answer.get("code") or 1))
                left.remove(rid)
        if not left:
            break
        if time.time() - start > timeout:
            print(f"still running after {timeout:.0f} s: {' '.join(left)} (see vrgdg/logs/)", file=sys.stderr)
            return 124
        time.sleep(2)
    return code


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-wait", action="store_true")
    ap.add_argument("--wait", nargs="+", metavar="ID")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--timeout", type=float, default=540, help="how long to wait here (the run itself goes on)")
    ap.add_argument("script", nargs="?")
    ap.add_argument("args", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    if a.list:
        for f in sorted(QUEUE.glob("*.json")) if QUEUE.is_dir() else []:
            print("waiting", f.stem, json.loads(f.read_text()).get("script"))
        for f in sorted(LOGS.glob("*.log")) if LOGS.is_dir() else []:
            if not (DONE / f"{f.stem}.json").exists():
                print("running", f.stem)
        return 0
    if a.wait:
        return wait(a.wait, a.timeout)
    if not a.script:
        ap.error("name a script (song_plan.py, build_prompts.py, render_scenes.py, qa_music.py, assemble.py, …)")
    rid = send(a.script, a.args)
    if a.no_wait:
        print(rid)
        return 0
    return wait([rid], a.timeout)


if __name__ == "__main__":
    sys.exit(main())
