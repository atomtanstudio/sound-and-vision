"""Grok Imagine through the Grok CLI the app is signed in with (Settings → Grok): one picture (image_gen, or image_edit
from reference pictures; Grok Imagine Image 2.0 unless another model is chosen) or one clip that starts from a still (reference_to_video, the still as its first frame and,
if given, another as its last). It runs on the person's Grok plan; Grok Imagine needs SuperGrok.

Each request offers the CLI exactly one tool and lets it be called once: anything else stops it. Its files go into a
private work folder, and the request's own session folder (where the CLI saves what it made) is removed afterwards,
with the CLI's prompt history. Ported from the earlier app, where it ran for pictures (sv/accounts.py, 2026-09)."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from .providers import GROK_ENV, WriterError, _private

if TYPE_CHECKING:
    from .providers import Grok

PICTURE_SYSTEM = (
    "You make one picture with Grok Imagine. Call {tool} exactly once. Use the user's description as the prompt, word "
    "for word: do not add, drop or reword anything. Use the aspect ratio the user gives.{refs} Do not call any other "
    "tool, run commands or read files. After the picture is saved, reply with only the word: done. If the tool fails "
    "or declines, reply with one sentence saying why."
)
CLIP_SYSTEM = (
    "You make one short video clip with Grok Imagine. Call reference_to_video exactly once. Use the user's description "
    "as the prompt, word for word: do not add, drop or reword anything. Pass the first picture path the user gives as "
    "first_frame{last}. Pass no other images, voices or keyframes. Use the aspect_ratio, duration (seconds) and "
    "resolution_name the user gives. Do not call any other tool, run commands or read files. After the video is saved, "
    "reply with only the word: done. If the tool fails or declines, reply with one sentence saying why."
)
PICTURES = (".jpg", ".jpeg", ".png", ".webp")
VIDEOS = (".mp4", ".webm", ".mov")
CLIP_SECONDS = (1, 15)  # what Grok Imagine makes, in whole seconds


class Stream:
    """The events of one request: only `tool` may be offered and called; the finished call says where it saved."""

    def __init__(self, tool: str) -> None:
        self.tool = tool
        self.tools_checked = False
        self.calls: set[str] = set()
        self.saved: str | None = None
        self.said: list[str] = []
        self.noise: list[str] = []

    def feed(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        try:
            event = json.loads(line)
        except ValueError:
            self.noise = [*self.noise[-4:], line[:200]]
            return
        if not isinstance(event, dict):
            return
        kind = str(event.get("type") or event.get("sessionUpdate") or "")
        if kind == "available_commands":
            tools = event.get("tools")
            if not isinstance(tools, list) or set(tools) != {self.tool}:
                raise WriterError(f"The Grok CLI didn't offer exactly its {self.tool} tool ({tools!r}), so the request "
                                  "was stopped. Its options may have changed with an update.")
            self.tools_checked = True
        elif "tool" in kind:
            call = str(event.get("toolCallId") or event.get("id") or "")
            if "update" in kind or "result" in kind:
                if call not in self.calls:  # progress and results only for a call that was allowed when it started
                    raise WriterError("Grok reported a tool call the app didn't allow, so the request was stopped.")
            else:
                meta = event.get("_meta") if isinstance(event.get("_meta"), dict) else {}
                tm = meta.get("x.ai/tool") if isinstance(meta.get("x.ai/tool"), dict) else {}
                name = next((v for v in (tm.get("name"), event.get("title"), event.get("name")) if isinstance(v, str) and v), "")
                if name != self.tool or not call:
                    raise WriterError(f"Grok tried to use {name or 'an unnamed tool'}, which the app doesn't allow, so the "
                                      "request was stopped.")
                self.calls.add(call)
                if len(self.calls) > 2:
                    raise WriterError(f"Grok kept calling {self.tool}, so the request was stopped.")
            for text in _texts(event):
                try:
                    out = json.loads(text)
                except ValueError:
                    continue
                if isinstance(out, dict) and isinstance(out.get("path"), str):
                    self.saved = out["path"]
        elif kind == "error":
            raise WriterError(str(event.get("message") or "Grok reported an error."))
        elif kind == "text":
            self.said.append(str(event.get("data") or ""))

    def made(self, folder: Path, suffixes: tuple[str, ...]) -> Path:
        """What it made: the saved file, which must be inside the request's own session folder."""
        said = "".join(self.said).strip()
        if not self.tools_checked:
            raise WriterError("The Grok CLI didn't show which tools it offered, so what it made wasn't used.")
        candidates = [Path(self.saved)] if self.saved else []
        candidates += sorted(p for p in folder.rglob("*") if p.is_file()) if folder.is_dir() else []
        for path in candidates:
            try:
                path = path.resolve()
            except OSError:
                continue
            if folder.resolve() in path.parents and path.is_file() and path.suffix.lower() in suffixes:
                return path
        if "supergrok" in said.lower():
            raise WriterError("Grok Imagine needs a SuperGrok subscription on the signed-in account.")
        raise WriterError(said[:300] if said and said.lower() != "done" else
                          f"Grok didn't make it. {' '.join(self.noise)[-200:]}".strip())


def _texts(event: Any) -> list[str]:
    """Every text value inside an event's content (tool results arrive as text holding JSON)."""
    out: list[str] = []
    if isinstance(event, dict):
        for k, v in event.items():
            if k == "text" and isinstance(v, str):
                out.append(v)
            else:
                out += _texts(v)
    elif isinstance(event, list):
        for v in event:
            out += _texts(v)
    return out


async def _run(grok: "Grok", tool: str, ask: str, system: str, flags: dict[str, str], suffixes: tuple[str, ...],
               files: list[Path], timeout: float) -> tuple[bytes, str]:
    """One request: `files` are copied into the work folder first (the CLI reads them there). Returns what it made
    (its bytes and suffix)."""
    if not await grok.connected():
        raise WriterError("Sign in with Grok first (Settings).")
    work = grok.home.parent / "grok-media"
    _private(grok.home, work)
    rid = uuid.uuid4().hex[:10]
    copies = []
    for i, f in enumerate(files):
        dest = work / f"{rid}-{i}{f.suffix.lower()}"
        shutil.copyfile(f, dest)
        copies.append(dest)
    for i, c in enumerate(copies):
        ask = ask.replace(f"{{file{i}}}", str(c))
    prompt_file = work / f"{rid}-ask.txt"
    prompt_file.write_text(ask)
    session = str(uuid.uuid4())
    env = {**grok._env(), **GROK_ENV, **flags}
    args = ["--prompt-file", str(prompt_file), "--session-id", session, "--output-format", "streaming-json",
            "--max-turns", "3", "--no-subagents", "--no-plan", "--disable-web-search", "--system-prompt-override", system,
            "--cwd", str(work), "--tools", tool,
            "--disallowed-tools", "todo_write,run_terminal_cmd,run_terminal_command,search_tool,use_tool",
            # the media tools save a file, which the permission rules count as editing and writing, so those two rules
            # stay off (only the one tool is offered, and the stream check stops any other)
            "--deny", "Bash", "--deny", "Grep", "--deny", "WebFetch", "--deny", "MCPTool", "--always-approve"]
    folder = grok.home / ".grok" / "sessions" / quote(str(work), safe="") / session
    # its own process group, so stopping it also stops anything it started
    proc = await asyncio.create_subprocess_exec(str(grok.binary), *args, cwd=work, env=env, stdin=asyncio.subprocess.DEVNULL,
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                                                start_new_session=True)
    stream = Stream(tool)

    def kill() -> None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass

    async def read() -> None:
        assert proc.stdout
        async for raw in proc.stdout:
            stream.feed(raw.decode(errors="replace"))
        await proc.wait()
    try:
        try:
            await asyncio.wait_for(read(), timeout)
        except TimeoutError:
            raise WriterError(f"Grok didn't finish within {timeout:g} s.") from None
        path = stream.made(folder, suffixes)
        return path.read_bytes(), path.suffix.lower()
    finally:
        if proc.returncode is None:
            kill()
            await proc.wait()
        for c in [*copies, prompt_file]:
            c.unlink(missing_ok=True)
        shutil.rmtree(folder, ignore_errors=True)
        (folder.parent / "prompt_history.jsonl").unlink(missing_ok=True)


async def picture(grok: "Grok", prompt: str, shape: str = "1:1", references: list[Path] | None = None,
                  model: str = "grok-imagine-image-2.0", timeout: float = 420) -> tuple[bytes, str]:
    """One picture from Grok Imagine with `model` (the CLI's GROK_IMAGE_*_MODEL_OVERRIDE): (its bytes, its suffix)."""
    refs = [Path(r) for r in references or []][:3]
    tool = "image_edit" if refs else "image_gen"
    ask = f"Aspect ratio: {shape}\nDescription: {prompt.strip()}"
    if refs:
        ask += "\nReference pictures (pass all of them as the image input): " + ", ".join(f"{{file{i}}}" for i in range(len(refs)))
    system = PICTURE_SYSTEM.format(tool=tool, refs=" Pass every reference picture's path as the image input, so the people "
                                   "and places stay the same." if refs else "")
    flags = {"GROK_IMAGE_GEN": "1" if tool == "image_gen" else "0", "GROK_IMAGE_EDIT": "1" if tool == "image_edit" else "0",
             "GROK_IMAGE_GEN_MODEL_OVERRIDE": model, "GROK_IMAGE_EDIT_MODEL_OVERRIDE": model}
    return await _run(grok, tool, ask, system, flags, PICTURES, refs, timeout)


async def clip(grok: "Grok", still: Path, prompt: str, seconds: int, end: Path | None = None, shape: str = "16:9",
               resolution: str = "720p", timeout: float = 900) -> tuple[bytes, str]:
    """One clip from Grok Imagine that starts on `still` (and ends on `end`, if given): (its bytes, its suffix)."""
    seconds = max(CLIP_SECONDS[0], min(CLIP_SECONDS[1], int(round(seconds))))
    ask = (f"Aspect ratio: {shape}\nDuration: {seconds}\nResolution: {resolution}\nPicture for first_frame: {{file0}}\n" +
           ("Picture for last_frame: {file1}\n" if end else "") + f"Description: {prompt.strip()}")
    system = CLIP_SYSTEM.format(last=", and the second as last_frame" if end else "")
    return await _run(grok, "reference_to_video", ask, system, {"GROK_VIDEO_GEN": "1"}, VIDEOS,
                      [still, *([end] if end else [])], timeout)
