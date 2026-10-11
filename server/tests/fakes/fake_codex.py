"""A stand-in for `codex app-server` in tests: the same JSON-RPC over stdio, for the calls sv/writers/openai.py makes.

Sign-in completes a moment after it starts (as if the code were approved). A text turn answers {"ok": true} as the
final message; a thread with image_generation on makes a small PNG (and a copy under generated_images/, as Codex does).
A prompt with TOOL starts a command instead, and waits to be interrupted. Every request goes to $FAKE_CODEX_LOG.
"""

import base64
import json
import os
import struct
import sys
import threading
import zlib
from pathlib import Path

home = Path(os.environ["CODEX_HOME"])
auth = home / "auth.json"
log = Path(os.environ["FAKE_CODEX_LOG"])
lock = threading.Lock()
threads: dict[str, dict] = {}
stopped = threading.Event()


def png() -> bytes:
    rows = b"".join(b"\x00" + b"".join(bytes((x * 30, y * 30, 160)) for x in range(8)) for y in range(8))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


def send(msg: dict) -> None:
    with lock:
        sys.stdout.write(json.dumps(msg) + "\n")
        sys.stdout.flush()


def item(tid: str, kind: str, event: str, **fields) -> None:
    send({"method": f"item/{event}", "params": {"threadId": tid, "item": {"type": kind, "id": f"{kind}-1", **fields}}})


def done(tid: str, status: str = "completed") -> None:
    send({"method": "turn/completed", "params": {"threadId": tid, "turn": {"id": "turn-1", "status": status}}})


for line in sys.stdin:
    msg = json.loads(line)
    with log.open("a") as f:
        f.write(json.dumps(msg) + "\n")
    method, params, rid = msg.get("method"), msg.get("params") or {}, msg.get("id")
    if method in (None, "initialized"):
        continue
    if method == "initialize":
        send({"id": rid, "result": {"userAgent": "fake-codex"}})
    elif method == "account/read":
        send({"id": rid, "result": {"account": {"type": "chatgpt", "email": "you@example.com", "planType": "plus"} if auth.exists() else None}})
    elif method == "account/login/start":
        send({"id": rid, "result": {"loginId": "login-1", "verificationUrl": "https://auth.openai.com/codex/device", "userCode": "ABCD-1234"}})

        def approve():
            auth.write_text("{}")
            send({"method": "account/login/completed", "params": {"loginId": "login-1", "success": True}})
        threading.Timer(0.2, approve).start()
    elif method in ("account/login/cancel", "thread/unsubscribe"):
        send({"id": rid, "result": {}})
    elif method == "account/logout":
        auth.unlink(missing_ok=True)
        send({"id": rid, "result": {}})
    elif method == "model/list":
        send({"id": rid, "result": {"data": [
            {"id": "gpt-5.5", "displayName": "GPT-5.5", "isDefault": True, "defaultReasoningEffort": "medium",
             "supportedReasoningEfforts": [{"reasoningEffort": e, "description": e} for e in ("low", "medium", "high")]}]}})
    elif method == "thread/start":
        tid = f"thread-{len(threads) + 1}"
        threads[tid] = params
        send({"id": rid, "result": {"thread": {"id": tid}}})
    elif method == "turn/interrupt":
        stopped.set()
        send({"id": rid, "result": {}})
    elif method == "turn/start":
        tid, text = params["threadId"], params["input"][0]["text"]
        send({"id": rid, "result": {"turn": {"id": "turn-1"}}})
        paints = threads[tid]["config"]["features"].get("image_generation")

        def run(tid=tid, text=text, paints=paints):
            item(tid, "userMessage", "started")
            item(tid, "userMessage", "completed")
            if "TOOL" in text:
                item(tid, "commandExecution", "started", command="ls")
                stopped.wait(10)
                done(tid, "interrupted")
                return
            if paints:
                picture = png()
                (home / "generated_images" / tid).mkdir(parents=True, exist_ok=True)
                (home / "generated_images" / tid / "exec-1.png").write_bytes(picture)
                item(tid, "imageGeneration", "started", status="generating")
                item(tid, "imageGeneration", "completed", status="completed", result=base64.b64encode(picture).decode())
                item(tid, "agentMessage", "completed", text="done", phase="final_answer")
            else:
                item(tid, "agentMessage", "completed", text='{"ok": true}', phase="final_answer")
            done(tid)
        threading.Thread(target=run, daemon=True).start()
