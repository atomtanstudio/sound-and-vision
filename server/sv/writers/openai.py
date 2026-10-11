"""Sign in with ChatGPT: OpenAI's own Codex CLI, in app-server mode (JSON-RPC over stdio), with a private home (0700)
and device-code sign-in, the same way Grok signs in. The app holds no OAuth client of its own: the user approves a URL
and a short code in any browser, and the credentials stay in Codex's home. Ported from the old app's accounts.py.

It writes (one turn, no tools, JSON out, with the model's own reasoning levels) and paints (ChatGPT's built-in image
tool, the only tool switched on, for that one turn), both under the user's ChatGPT plan.

Codex's own sandbox can't start where unprivileged user namespaces are off, so "no tools" is enforced in layers: every
tool is switched off when the thread starts, a turn that starts any other item is stopped at once, and the policy
(read-only, never approve) refuses any file change. Requests from the runtime to run something are always refused.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .providers import LOGIN_SECONDS, WriterError, _json, _private

SCRUBBED = ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_ACCESS_TOKEN", "OPENAI_BASE_URL", "XAI_API_KEY",
            "GROK_DEPLOYMENT_KEY", "ANTHROPIC_API_KEY")
# Every tool feature Codex turns on by default, off (see the module notes).
THREAD_CONFIG = {
    "web_search": "disabled", "agents": {"enabled": False}, "tools": {"view_image": False},
    "features": {f: False for f in (
        "shell_tool", "unified_exec", "code_mode_host", "apps", "plugins", "remote_plugin", "multi_agent",
        "browser_use", "browser_use_external", "computer_use", "in_app_browser", "image_generation", "view_image",
        "sleep_tool", "goals", "hooks", "skill_search", "tool_suggest", "skill_mcp_dependency_install",
        "shell_snapshot", "workspace_dependencies", "tool_call_mcp_elicitation")},
}
TEXT_ITEMS = {"userMessage", "agentMessage", "reasoning"}
IMAGE_CONFIG = {**THREAD_CONFIG, "features": {**THREAD_CONFIG["features"], "image_generation": True}}
IMAGE_ITEMS = TEXT_ITEMS | {"imageGeneration"}
PICTURE_RULES = (
    "You make one picture with the built-in image generation tool, exactly as the request describes, in the shape it "
    "states. Call the tool exactly once, with a prompt faithful to the request; you may improve its wording for the image "
    "model but never drop a stated detail. Any attached images are references for the same person, place or object: "
    "keep their identity, face, build, clothing and layout, and change only what the request asks. Never add text, "
    "letters, labels, numbers, logos or watermarks unless the request asks for them. Do not call any other tool, run "
    "commands or read files. After the image is made, reply with the single word: done. If the image tool fails or "
    "declines, reply with one sentence saying why."
)
SHAPES = {"1:1": "square", "16:9": "16:9 landscape", "9:16": "9:16 portrait", "4:5": "4:5 portrait", "3:2": "3:2 landscape"}
MAX_REFERENCES = 5
SAFETY = re.compile(r"safety|content polic|moderation|disallowed|not allowed|violat", re.I)
PNG = b"\x89PNG\r\n\x1a\n"
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def _image_input(path: Path) -> dict:
    """An image as turn input, inline: the image tool reads a path through Codex's sandbox, which may not start."""
    kind = IMAGE_TYPES.get(path.suffix.lower(), "image/png")
    return {"type": "image", "url": f"data:{kind};base64,{base64.b64encode(path.read_bytes()).decode()}", "detail": "original"}


class ChatGPT:
    id, name = "openai", "ChatGPT"
    takes_images = True

    def __init__(self, binary: Path, home: Path, path_dirs: tuple[Path, ...] = ()):
        self.binary, self.home, self.work = binary, home, home.parent / "codex-work"
        self.path_dirs = path_dirs
        self.proc: asyncio.subprocess.Process | None = None
        self.start_lock = asyncio.Lock()
        self.pending: dict[int, asyncio.Future] = {}
        self.threads: dict[str, asyncio.Queue] = {}
        self.sequence = 0
        self.login: dict | None = None
        self.login_error: str | None = None
        self.models: list[dict] = []

    @property
    def installed(self) -> bool:
        return bool(shutil.which(str(self.binary), path=self._env()["PATH"])) if not self.binary.is_absolute() \
            else self.binary.is_file()

    def _env(self) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if k not in SCRUBBED and not k.startswith("SV_")}
        env["CODEX_HOME"] = str(self.home)
        if self.path_dirs:
            env["PATH"] = os.pathsep.join([*(str(p) for p in self.path_dirs), env.get("PATH", "")])
        return env

    # ---- the runtime ------------------------------------------------------------------------
    async def _start(self) -> None:
        async with self.start_lock:
            if self.proc and self.proc.returncode is None:
                return
            if not self.installed:
                raise WriterError("ChatGPT needs OpenAI's Codex CLI on this machine (npm i -g @openai/codex, or SV_CODEX_BIN).")
            _private(self.home, self.work)
            log = open(self.home.parent / "codex-runtime.log", "ab")
            os.chmod(log.name, 0o600)
            self.proc = await asyncio.create_subprocess_exec(
                str(self.binary), "app-server", "-c", 'cli_auth_credentials_store="file"', "-c", "analytics.enabled=false",
                cwd=self.work, env=self._env(), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=log,
                limit=64 << 20)  # a picture comes back as one line of base64
            log.close()
            asyncio.get_running_loop().create_task(self._read(self.proc))
            await self._ask("initialize", {"clientInfo": {"name": "sound_vision", "title": "Sound / Vision", "version": "1.0.0"},
                                           "capabilities": {"experimentalApi": True}})
            await self._send({"method": "initialized", "params": {}})

    async def _send(self, payload: dict) -> None:
        assert self.proc and self.proc.stdin
        self.proc.stdin.write((json.dumps(payload) + "\n").encode())
        await self.proc.stdin.drain()

    async def _ask(self, method: str, params: dict | None = None, timeout: float = 30) -> dict:
        self.sequence += 1
        key = self.sequence
        done: asyncio.Future = asyncio.get_running_loop().create_future()
        self.pending[key] = done
        try:
            await self._send({"id": key, "method": method, "params": params or {}})
            return await asyncio.wait_for(done, timeout)
        except TimeoutError:
            raise WriterError(f"ChatGPT didn't answer {method} within {timeout:g} s.") from None
        finally:
            self.pending.pop(key, None)

    async def _read(self, proc: asyncio.subprocess.Process) -> None:
        assert proc.stdout
        async for line in proc.stdout:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if "id" in msg and "method" not in msg:
                done = self.pending.get(msg["id"])
                if done and not done.done():
                    if "error" in msg:
                        done.set_exception(WriterError((msg["error"] or {}).get("message") or "ChatGPT's request failed."))
                    else:
                        done.set_result(msg.get("result") or {})
            elif "id" in msg:  # the runtime asking to run a tool, a command or read a file: never
                try:
                    await self._send({"id": msg["id"], "error": {"code": -32601, "message": "Tools are not available in Sound / Vision."}})
                except (OSError, ConnectionError):
                    pass
            else:
                params = msg.get("params") or {}
                if msg.get("method") == "account/login/completed":
                    self.login = None
                    self.login_error = None if params.get("success") else (params.get("error") or "Sign-in didn't complete.")
                    self.models = []
                if (q := self.threads.get(params.get("threadId"))) is not None:
                    q.put_nowait(msg)
        for done in self.pending.values():
            if not done.done():
                done.set_exception(WriterError("ChatGPT's runtime stopped."))
        for q in self.threads.values():
            q.put_nowait({"method": "connection/closed"})

    # ---- the account ------------------------------------------------------------------------
    async def status(self) -> dict[str, Any]:
        if not self.installed:
            return {"id": self.id, "name": self.name, "installed": False, "connected": False, "canSignIn": True}
        try:
            await self._start()
            account = (await self._ask("account/read", {"refreshToken": False})).get("account")
        except WriterError as exc:
            return {"id": self.id, "name": self.name, "installed": True, "connected": False, "canSignIn": True, "error": str(exc)}
        connected = bool(account and account.get("type") == "chatgpt")
        if self.login and time.time() > self.login["expiresAt"]:
            await self.cancel_login()
            self.login_error = "The sign-in code expired. Start again."
        if connected and not self.models:
            data = await self._ask("model/list", {"includeHidden": False})
            self.models = [{"id": m["id"], "name": m.get("displayName") or m["id"], "default": bool(m.get("isDefault")),
                            "efforts": [o["reasoningEffort"] for o in m.get("supportedReasoningEfforts") or []],
                            "defaultEffort": m.get("defaultReasoningEffort")} for m in data.get("data", [])]
        return {"id": self.id, "name": self.name, "installed": True, "connected": connected, "canSignIn": True,
                "account": (account or {}).get("email") if connected else None,
                "plan": (account or {}).get("planType") if connected else None,
                "models": self.models if connected else [], "error": self.login_error,
                "login": {k: self.login[k] for k in ("url", "code", "expiresAt")} if self.login else None,
                "note": "Runs at OpenAI under your ChatGPT plan. Writes, and makes pictures with ChatGPT's image tool."}

    async def begin_login(self) -> dict[str, Any]:
        st = await self.status()
        if st["connected"] or self.login:
            return st
        result = await self._ask("account/login/start", {"type": "chatgptDeviceCode"}, timeout=60)
        url = urlparse(result.get("verificationUrl") or "")
        if url.scheme != "https" or url.hostname != "auth.openai.com":
            raise WriterError("OpenAI sent an unexpected sign-in address, so it isn't shown.")
        self.login = {"id": result["loginId"], "url": result["verificationUrl"], "code": result["userCode"],
                      "expiresAt": time.time() + LOGIN_SECONDS}
        self.login_error = None
        return await self.status()

    async def cancel_login(self) -> None:
        if self.login:
            try:
                await self._ask("account/login/cancel", {"loginId": self.login["id"]})
            except WriterError:
                pass
            finally:
                self.login = None

    async def logout(self) -> dict[str, Any]:
        await self._start()
        await self.cancel_login()
        await self._ask("account/logout")
        self.models = []
        return await self.status()

    def _model(self, model: str | None) -> str | None:
        return model or next((m["id"] for m in self.models if m["default"]), None)

    # ---- one turn -----------------------------------------------------------------------------
    async def _turn(self, *, instructions: str, config: dict, allowed: set[str], inputs: list[dict], model: str | None,
                    effort: str | None, schema: dict | None, timeout: float) -> tuple[list[str], dict | None]:
        st = await self.status()
        if not st["connected"]:
            raise WriterError("Sign in with ChatGPT in Settings first.")
        thread = await self._ask("thread/start", {
            "cwd": str(self.work), "model": self._model(model), "modelProvider": "openai", "approvalPolicy": "never",
            "sandbox": "read-only", "ephemeral": True, "config": config, "developerInstructions": instructions})
        tid = thread["thread"]["id"]
        events: asyncio.Queue = asyncio.Queue()
        self.threads[tid] = events
        turn_id, finished = None, False
        said: list[str] = []
        image: dict | None = None
        try:
            params: dict[str, Any] = {"threadId": tid, "input": inputs, "approvalPolicy": "never",
                                      "sandboxPolicy": {"type": "readOnly", "networkAccess": False}}
            if schema:
                params["outputSchema"] = schema
            if effort:
                params["effort"] = effort
            turn_id = (await self._ask("turn/start", params))["turn"]["id"]
            deadline = time.monotonic() + timeout
            while True:
                left = deadline - time.monotonic()
                if left <= 0:
                    raise WriterError(f"ChatGPT didn't finish within {timeout:g} s.")
                try:
                    event = await asyncio.wait_for(events.get(), left)
                except TimeoutError:
                    continue
                method, p = event.get("method"), event.get("params") or {}
                item = p.get("item") or {}
                if method == "connection/closed":
                    raise WriterError("ChatGPT's runtime stopped.")
                if method == "item/started" and item.get("type") not in allowed:
                    raise WriterError("ChatGPT tried to use a tool, which Sound / Vision doesn't allow, so it was stopped.")
                if method == "item/completed" and item.get("type") == "imageGeneration":
                    image = item
                if method == "item/completed" and item.get("type") == "agentMessage":
                    said.append(item.get("text") or "")
                if method == "error":
                    said.append((p.get("error") or {}).get("message") or "")
                if method == "turn/completed":
                    turn = p.get("turn") or {}
                    if turn.get("status") != "completed":
                        said.append((turn.get("error") or {}).get("message") or "")
                        raise WriterError(_failure(image, said) or "ChatGPT didn't complete the request.")
                    finished = True
                    return said, image
        finally:
            if turn_id and not finished:
                try:
                    await self._ask("turn/interrupt", {"threadId": tid, "turnId": turn_id}, timeout=5)
                except WriterError:
                    pass
            self.threads.pop(tid, None)
            try:
                await self._ask("thread/unsubscribe", {"threadId": tid}, timeout=5)
            except WriterError:
                pass
            self._forget_images(tid)

    async def complete(self, system: str, prompt: str, schema: dict, model: str | None = None, *,
                       effort: str | None = None, images: list[Path] | None = None, timeout: float = 240) -> dict:
        said, _ = await self._turn(
            instructions=system + " Do not call any tools, run commands or read files. Return only the requested JSON object.",
            config=THREAD_CONFIG, allowed=TEXT_ITEMS, model=model, effort=effort, schema=schema, timeout=timeout,
            inputs=[{"type": "text", "text": prompt, "text_elements": []}, *(_image_input(p) for p in (images or [])[:MAX_REFERENCES])])
        answer = [t for t in said if t.strip()]
        if not answer:
            raise WriterError("ChatGPT returned no answer.")
        return _json(answer[-1])

    async def picture(self, prompt: str, *, shape: str = "1:1", references: list[Path] | None = None,
                      model: str | None = None, timeout: float = 360) -> bytes:
        """One PNG from ChatGPT's image tool. `references`: up to five pictures of the same person, place or thing."""
        refs = list(references or [])[:MAX_REFERENCES]
        for r in refs:
            if not r.is_file():
                raise WriterError(f"The reference picture {r.name} is missing.")
        ask = f"Make this picture, {SHAPES.get(shape, shape)}:\n{prompt}"
        said, image = await self._turn(instructions=PICTURE_RULES, config=IMAGE_CONFIG, allowed=IMAGE_ITEMS, model=model,
                                       effort=None, schema=None, timeout=timeout,
                                       inputs=[{"type": "text", "text": ask, "text_elements": []}, *(_image_input(r) for r in refs)])
        return _png(image, said)

    async def close(self) -> None:
        if self.proc and self.proc.returncode is None:
            self.proc.terminate()
            try:
                await asyncio.wait_for(self.proc.wait(), 5)
            except TimeoutError:
                self.proc.kill()

    def _forget_images(self, thread_id: str) -> None:
        """Codex keeps a copy of each picture under generated_images/<thread>; the app keeps its own."""
        folder = self.home / "generated_images"
        if folder.is_dir():
            stale = time.time() - 600
            for entry in folder.iterdir():
                if entry.is_dir() and (entry.name == thread_id or entry.stat().st_mtime < stale):
                    shutil.rmtree(entry, ignore_errors=True)


def _failure(item: dict | None, said: list[str]) -> str | None:
    """Why a picture or an answer wasn't made, in plain words: the plan's limit, the safety filter, or what it said."""
    failure = (item or {}).get("failure") or {}
    if failure.get("type") == "usageLimitExceeded":
        resets = failure.get("resetsAt")
        minutes = round((resets - time.time()) / 60) if isinstance(resets, (int, float)) else None
        return "Your ChatGPT plan's limit for pictures is used up" + (f"; it resets in about {minutes} minutes." if minutes and minutes > 0 else ".")
    words = " ".join(w.strip() for w in said if w and w.strip())
    if SAFETY.search(words):
        return "OpenAI's safety filter declined it. Try again, or change the prompt."
    if words and words.lower().strip(" .") != "done":
        return f"ChatGPT said: {words[:240]}"
    return None


def _png(item: dict | None, said: list[str]) -> bytes:
    if not item or not item.get("result"):
        raise WriterError(_failure(item, said) or "ChatGPT didn't make a picture.")
    try:
        data = base64.b64decode(item["result"], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise WriterError("ChatGPT's picture couldn't be read.") from exc
    if not data.startswith(PNG):
        raise WriterError("ChatGPT's picture wasn't a PNG.")
    return data
