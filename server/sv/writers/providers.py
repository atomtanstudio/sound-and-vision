"""The language models the app can ask, each signed in its own way:

- Grok: xAI's official CLI with a private home (0700); the user approves a device code in
  any browser. Requests are one turn, no tools (enforced in layers, see GROK_NO_TOOLS and GrokStream).
  Ported from the old app's accounts.py.
- Claude: Claude Code in the studio container, under the owner's own login, which they made once in a
  terminal (`studio.sh signin`). The app never starts, relays or reads that login. No tools.
- Local: Ollama on the same machine (no account, nothing leaves it).

Each gives complete(system, prompt, schema, model) -> dict.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import httpx


class WriterError(Exception):
    """Something the user should read: not signed in, too slow, the provider's own error."""


def _json(text: str) -> dict:
    text = text.strip()
    start = text.find("{")
    if start < 0:
        raise WriterError("The answer wasn't in the expected form.")
    try:
        return json.loads(text[start:text.rfind("}") + 1])
    except ValueError as exc:
        raise WriterError("The answer wasn't in the expected form.") from exc


def _private(*dirs: Path) -> None:
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        d.chmod(0o700)


SCRUBBED = ("OPENAI_API_KEY", "XAI_API_KEY", "GROK_DEPLOYMENT_KEY", "ANTHROPIC_API_KEY")

# ---- Grok -------------------------------------------------------------------------------------

DEVICE_URL = re.compile(r"https://accounts\.x\.ai/\S+")
DEVICE_CODE = re.compile(r"\b[A-Z0-9]{4}-[A-Z0-9]{4}\b")
NOT_SIGNED_IN = re.compile(r"not (signed in|authenticated)", re.I)
MODEL_LINE = re.compile(r"^\s*[*•-]\s+([a-z][a-z0-9.\-]*)(\s+\(default\))?\s*$")
GROK_ENV = {
    "DISABLE_TELEMETRY": "1", "GROK_TELEMETRY_ENABLED": "0", "GROK_TELEMETRY_TRACE_UPLOAD": "false",
    "GROK_TELEMETRY_MIXPANEL_ENABLED": "false", "GROK_FEEDBACK_ENABLED": "0", "GROK_DISABLE_AUTOUPDATER": "1",
    "GROK_MEMORY": "0", "GROK_SUBAGENTS": "0", "GROK_WEB_FETCH": "0", "GROK_IMAGE_GEN": "0", "GROK_IMAGE_EDIT": "0",
    "GROK_VIDEO_GEN": "0", "GROK_WORKFLOW": "0", "GROK_SESSION_SEARCH": "0",
}
# An empty --tools is ignored, so allow one harmless tool, then take it and the CLI's own tools away.
GROK_NO_TOOLS = [
    "--tools", "todo_write", "--disallowed-tools", "todo_write,run_terminal_cmd,run_terminal_command,search_tool,use_tool",
    "--deny", "Bash", "--deny", "Edit", "--deny", "Write", "--deny", "Read", "--deny", "Grep", "--deny", "WebFetch",
    "--deny", "MCPTool",
]
LOGIN_SECONDS = 900


class Grok:
    id, name = "grok", "Grok"

    def __init__(self, binary: Path, home: Path):
        self.binary, self.home, self.work = binary, home, home.parent / "grok-work"
        self.login: dict | None = None
        self.login_proc: asyncio.subprocess.Process | None = None
        self.login_error: str | None = None
        self.models: list[dict] = []
        self.checked: tuple[float, bool] | None = None

    def _env(self) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if k not in SCRUBBED and not k.startswith("SV_")}
        return {**env, "HOME": str(self.home), **GROK_ENV}

    async def _run(self, args: list[str], timeout: float) -> tuple[int, str]:
        _private(self.home, self.work)
        proc = await asyncio.create_subprocess_exec(str(self.binary), *args, cwd=self.work, env=self._env(),
                                                    stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.STDOUT)
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout)
        except TimeoutError:
            proc.kill()
            raise WriterError(f"Grok didn't answer within {timeout:g} s.") from None
        return proc.returncode or 0, out.decode(errors="replace")

    async def connected(self) -> bool:
        if not self.binary.is_file():
            return False
        now = time.monotonic()
        if self.checked and now - self.checked[0] < 60:
            return self.checked[1]
        try:
            code, text = await self._run(["models"], 30)
        except WriterError:
            return False
        ok = code == 0 and not NOT_SIGNED_IN.search(text)
        if ok:
            self.models = []
            for line in text.splitlines():
                if (m := MODEL_LINE.match(line)) and not any(x["id"] == m.group(1) for x in self.models):
                    self.models.append({"id": m.group(1), "name": m.group(1), "default": bool(m.group(2))})
        self.checked = (now, ok)
        return ok

    async def status(self) -> dict[str, Any]:
        if not self.binary.is_file():
            return {"id": self.id, "name": self.name, "installed": False, "connected": False, "canSignIn": True}
        if self.login and time.time() > self.login["expiresAt"]:
            await self.cancel_login()
            self.login_error = "The sign-in code expired. Start again."
        ok = False if self.login else await self.connected()
        return {"id": self.id, "name": self.name, "installed": True, "connected": ok, "canSignIn": True,
                "models": self.models if ok else [], "error": self.login_error,
                "login": {k: self.login[k] for k in ("url", "code", "expiresAt")} if self.login else None,
                "note": "Runs at xAI under your Grok account."}

    async def begin_login(self) -> dict[str, Any]:
        if self.login:
            return await self.status()
        _private(self.home, self.work)
        proc = await asyncio.create_subprocess_exec(str(self.binary), "login", "--device-auth", cwd=self.work, env=self._env(),
                                                    stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.STDOUT)
        self.login_proc = proc
        found: dict[str, str] = {}
        ready = asyncio.Event()

        async def read() -> None:
            assert proc.stdout
            async for raw in proc.stdout:
                line = raw.decode(errors="replace")
                if "url" not in found and (m := DEVICE_URL.search(line)):
                    found["url"] = m.group(0)
                elif "code" not in found and "url" in found and (m := DEVICE_CODE.search(line)):
                    found["code"] = m.group(0)
                if "url" in found and "code" in found:
                    ready.set()
            code = await proc.wait()
            ready.set()
            if self.login_proc is proc:
                self.login, self.login_proc, self.checked = None, None, None
                self.login_error = None if code == 0 else "Sign-in didn't complete."

        asyncio.create_task(read())
        try:
            await asyncio.wait_for(ready.wait(), 30)
        except TimeoutError:
            pass
        if "code" not in found or urlparse(found.get("url", "")).hostname != "accounts.x.ai":
            proc.terminate()
            raise WriterError("Grok didn't start a sign-in.")
        self.login = {"url": found["url"], "code": found["code"], "expiresAt": time.time() + LOGIN_SECONDS}
        self.login_error = None
        return await self.status()

    async def cancel_login(self) -> None:
        proc, self.login_proc, self.login = self.login_proc, None, None
        if proc and proc.returncode is None:
            proc.terminate()

    async def logout(self) -> dict[str, Any]:
        await self.cancel_login()
        await self._run(["logout"], 30)
        self.checked, self.models = None, []
        return await self.status()

    async def complete(self, system: str, prompt: str, schema: dict, model: str | None = None, timeout: float = 150) -> dict:
        if not await self.connected():
            raise WriterError("Sign in to Grok first (Settings → Connections).")
        _private(self.home, self.work)
        fd, prompt_file = tempfile.mkstemp(prefix="prompt-", suffix=".txt", dir=self.work)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(prompt)  # in a private file, never on the command line
        session = str(uuid.uuid4())
        args = ["--prompt-file", prompt_file, "--session-id", session, "--output-format", "streaming-json",
                "--max-turns", "1", "--no-subagents", "--no-plan", "--disable-web-search",
                "--system-prompt-override", system, "--cwd", str(self.work), *GROK_NO_TOOLS,
                "--json-schema", json.dumps(schema), *(["-m", model] if model else [])]
        try:
            proc = await asyncio.create_subprocess_exec(str(self.binary), *args, cwd=self.work, env=self._env(),
                                                        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                                                        stderr=asyncio.subprocess.STDOUT)
            tools_checked, text, end, noise = False, [], None, []
            assert proc.stdout

            async def read() -> None:
                nonlocal tools_checked, end
                async for raw in proc.stdout:
                    line = raw.decode(errors="replace").strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except ValueError:
                        noise.append(line[:200])
                        continue
                    kind = str(ev.get("type") or "") if isinstance(ev, dict) else ""
                    if kind == "available_commands":
                        if ev.get("tools"):
                            raise WriterError("Grok was offered tools, which the app doesn't allow, so the request was stopped.")
                        tools_checked = True
                    elif "tool" in kind:
                        raise WriterError("Grok tried to use a tool, which the app doesn't allow, so the request was stopped.")
                    elif kind == "error":
                        raise WriterError(str(ev.get("message") or "Grok reported an error."))
                    elif kind == "text":
                        text.append(str(ev.get("data") or ""))
                    elif kind == "end":
                        end = ev

            try:
                await asyncio.wait_for(read(), timeout)
            except TimeoutError:
                raise WriterError(f"Grok didn't finish within {timeout:g} s.") from None
            finally:
                if proc.returncode is None:
                    proc.kill()
                await proc.wait()
            if end is None:
                raise WriterError(f"Grok stopped without an answer. {' '.join(noise[-3:])}".strip())
            if not tools_checked:
                raise WriterError("Grok didn't show which tools it had, so its answer wasn't used.")
            structured = end.get("structuredOutput", end.get("structured_output"))
            return structured if isinstance(structured, dict) else _json("".join(text))
        finally:
            os.unlink(prompt_file)
            self._forget(session)

    def _forget(self, session: str) -> None:
        folder = self.home / ".grok" / "sessions" / quote(str(self.work), safe="")
        if folder.is_dir():
            (folder / "prompt_history.jsonl").unlink(missing_ok=True)
            stale = time.time() - 600
            for entry in folder.iterdir():
                if entry.is_dir() and (entry.name == session or entry.stat().st_mtime < stale):
                    shutil.rmtree(entry, ignore_errors=True)


# ---- Claude -----------------------------------------------------------------------------------

# The Claude models offered by default (any other model id can be typed in Settings and is passed through).
CLAUDE_LABELS = {"claude-haiku-5-5": "Haiku 5.5", "claude-sonnet-5-5": "Sonnet 5.5", "claude-opus-5-5": "Opus 5.5",
                 "claude-fable-5-1": "Fable 5.1"}
CLAUDE_MODELS = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5", "fable": "claude-fable-5-1",
                 **{k: k for k in CLAUDE_LABELS}}


# Claude Code's sign-in refresh colliding with another run's (a `.oauth_refresh.lock`): transient, seen 2026-10-08/09
OAUTH_HICCUP = re.compile(r"refresh(ing)? (the )?OAuth token|oauth_refresh", re.I)


CLAUDE_EFFORTS = ("low", "medium", "high", "xhigh", "max")  # Claude Code's --effort


class Claude:
    id, name = "claude", "Claude"

    def __init__(self, studio_sh: Path, scratch: Path):
        self.studio_sh, self.scratch = studio_sh, scratch
        self.checked: tuple[float, dict] | None = None
        # Claude Code signs in with your own Claude plan, once, in a terminal: the app never relays that login
        self.SIGNIN = f"Sign in once, in a terminal on the machine Sound / Vision runs on: {studio_sh} signin"

    async def _account(self) -> dict:
        now = time.monotonic()
        if self.checked and now - self.checked[0] < 120:
            return self.checked[1]
        info: dict = {"installed": self.studio_sh.exists()}
        if info["installed"]:
            proc = await asyncio.create_subprocess_exec(str(self.studio_sh), "status", stdout=asyncio.subprocess.PIPE,
                                                        stderr=asyncio.subprocess.DEVNULL)
            try:
                out, _ = await asyncio.wait_for(proc.communicate(), 60)
                data = _json(out.decode(errors="replace"))
                info.update(connected=bool(data.get("loggedIn")))
            except (TimeoutError, WriterError):
                info.update(connected=False)
        self.checked = (now, info)
        return info

    async def status(self) -> dict[str, Any]:
        a = await self._account()
        return {"id": self.id, "name": self.name, "installed": a.get("installed", False), "connected": a.get("connected", False),
                "models": [{"id": k, "name": v, "default": k == "claude-haiku-5-5", "efforts": list(CLAUDE_EFFORTS)}
                           for k, v in CLAUDE_LABELS.items()],
                "customModels": True,
                "error": None if a.get("connected") or not a.get("installed") else self.SIGNIN,
                "note": "Runs under your own Claude plan, signed in on this machine."}

    async def complete(self, system: str, prompt: str, schema: dict, model: str | None = None, timeout: float = 180,
                       tools: list[str] | None = None, turns: int = 2, images: list[Path] | None = None,
                       effort: str | None = None, mcp: dict | None = None, _again: bool = False) -> dict:
        """One answer as JSON. `tools` names the only connector tools it may call (for example an MCP server's, to make
        a picture), each allowed by name; `mcp` adds MCP servers for this run (Claude Code's --mcp-config). `images`
        are shown to it: copied into its work folder, with Read allowed (the only built-in tool it ever gets) so it
        can look at them."""
        if not (await self._account()).get("connected"):
            raise WriterError(self.SIGNIN)
        self.scratch.mkdir(parents=True, exist_ok=True)
        name = f"sv-write-{uuid.uuid4().hex[:10]}"
        shown: list[Path] = []
        for img in images or []:
            copy = self.scratch / f"look-{uuid.uuid4().hex[:8]}{img.suffix.lower()}"
            shutil.copyfile(img, copy)
            shown.append(copy)
        if shown:
            prompt = ("Look at " + ", ".join(f"/work/{c.name}" for c in shown) + " first (use Read).\n\n" + prompt)
            turns = max(turns, 2 + len(shown))
        args = [str(self.studio_sh), "run", str(self.scratch), "-p", "--system-prompt", system,
                "--tools", "Read" if shown else "",
                "--model", CLAUDE_MODELS.get(model or "haiku", model or CLAUDE_MODELS["haiku"]), "--output-format", "json",
                "--no-session-persistence", "--max-turns", str(turns), "--json-schema", json.dumps(schema)]
        if effort:
            args += ["--effort", effort]
        secret = None
        if mcp:  # (keys and tokens in a private file, never on a command line; it goes when the answer's in)
            from ..studio import private_file
            self.scratch.mkdir(parents=True, exist_ok=True)
            secret = private_file(self.scratch, mcp)
            args += ["--mcp-config", f"/work/{secret.name}"]
        allowed = [*(tools or []), *(["Read"] if shown else [])]
        if allowed:
            args += ["--allowedTools", " ".join(allowed)]
        if tools:
            # Connector tools (Mitte): wait for the connectors before the first turn. Headless Claude otherwise starts
            # while they're still connecting and has none of their tools (measured 2026-10-09: 9 of 22 runs saw no
            # Mitte tools; 30 of 30 did with this, about half a second slower).
            args += ["--settings", json.dumps({"env": {"MCP_CONNECTION_NONBLOCKING": "0"}})]
        env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "CLAUDE_"))} | \
              {"SV_STUDIO_GPU": "0", "SV_STUDIO_NAME": name}
        proc = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.PIPE, env=env)
        try:
            out, err = await asyncio.wait_for(proc.communicate(prompt.encode()), timeout)
        except TimeoutError:
            finally_remove([*shown, *([secret] if secret else [])])
            await asyncio.create_subprocess_exec("docker", "stop", "-t", "2", name)
            raise WriterError("Claude took too long to answer. Try again.") from None
        finally_remove([*shown, *([secret] if secret else [])])
        data = _json(out.decode(errors="replace")) if out.strip() else {}
        if data.get("is_error") or not data:
            msg = str(data.get("result") or err.decode(errors="replace")[-300:] or "Claude didn't answer.")
            if OAUTH_HICCUP.search(msg) and not _again:
                # another studio run was refreshing the sign-in at that moment (it clears itself within a minute);
                # nothing was done yet, so one more try is safe
                await asyncio.sleep(20)
                return await self.complete(system, prompt, schema, model, timeout, tools, turns, images, effort, mcp, _again=True)
            if re.search(r"content filtering|output blocked", msg, re.I):
                raise WriterError("Claude's safety filter stopped that answer. Try again, or rephrase the idea.")
            raise WriterError(msg)
        structured = data.get("structured_output")
        return structured if isinstance(structured, dict) else _json(str(data.get("result") or ""))


def finally_remove(files: list[Path]) -> None:
    for f in files:
        f.unlink(missing_ok=True)


# ---- Local (Ollama) ---------------------------------------------------------------------------

class Local:
    id = "local"

    def __init__(self, url: str, model: str = "qwen3.5:4b", machine: str = "the server"):
        self.url, self.model, self.machine = url, model, machine
        self.name = f"On {machine} (local)"

    async def status(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=5) as http:
                tags = (await http.get(f"{self.url}/api/tags")).json().get("models", [])
            models = [{"id": m["name"], "name": m["name"], "default": m["name"] == self.model} for m in tags]
            return {"id": self.id, "name": self.name, "installed": True, "connected": bool(models), "models": models,
                    "note": f"Runs on {self.machine}; nothing leaves the machine. Small models write weaker lyrics."}
        except httpx.HTTPError:
            return {"id": self.id, "name": self.name, "installed": False, "connected": False}

    async def complete(self, system: str, prompt: str, schema: dict, model: str | None = None, timeout: float = 150) -> dict:
        body = {"model": model or self.model, "stream": False, "format": schema, "keep_alive": "60s",
                "options": {"temperature": 0.9}, "think": False,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
        try:
            async with httpx.AsyncClient(timeout=timeout) as http:
                r = await http.post(f"{self.url}/api/chat", json=body)
                r.raise_for_status()
        except httpx.HTTPError as exc:
            raise WriterError("The local model didn't answer.") from exc
        return _json(r.json().get("message", {}).get("content", ""))
