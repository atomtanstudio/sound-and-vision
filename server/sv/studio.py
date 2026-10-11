"""Long Claude sessions in the studio container: Claude Code writing and rendering code in one folder (a motion graphics
film, a living cover's finish), on the GPU machine, under the owner's own Claude subscription. Ported from the old app
(soundandvision.old/server/sv/studio.py), where the free-rein films were made this way.

The session gets what a Claude Code chat on the desktop gets (memory: free-rein-films): every tool, the shell, the web,
and installs (npm here; pip bootstrapped into the folder, see video/folder.py), so a film made in the app can be made
the way the person's best chat-made films were. Nothing else is loaded into it: no --add-dir (Claude Code loads the
skills of any folder it's given, and /opt/kit still holds the old app's rulebooks), no auto memory.

Claude Code is Anthropic's CLI, unmodified, in the `sv-claude-studio` image; the owner signs in to it once in a terminal
(studio.sh signin). The app never sees, relays or stores that login, never sets an API key and never passes --bare.

A session is one `claude -p` run in a container whose only working folder is the work folder (plus the image's kit,
read-only, for its node_modules and fonts). Its stream-json output is kept line by line in <work>/../session.jsonl and
summarized for the interface: what Claude says, and what each step is in everyday words.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Callable

# Free rein, like a desktop chat: the whole shell (inside the container: the film's folder is the only one it can
# write), the web, subagents and the person's own skills. Headless runs can't ask, so everything is allowed up front.
FREE_TOOLS = ["Bash", "Read", "Write", "Edit", "MultiEdit", "NotebookEdit", "Glob", "Grep", "TodoWrite", "WebFetch",
              "WebSearch", "Agent", "Task", "Skill", "ToolSearch", "Monitor", "TaskCreate", "TaskGet", "TaskList",
              "TaskUpdate", "TaskStop"]
# What the shell starts with: Python packages Claude installs land in the folder (.local/), so they're still there
# when a note continues the session in a new container.
SHELL_ENV = {"PYTHONUSERBASE": "/work/.local", "PIP_USER": "1", "PIP_BREAK_SYSTEM_PACKAGES": "1",
             "PATH": "/work/.local/bin:/work/node_modules/.bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"}


class StudioError(Exception):
    """Something the person should read: the studio isn't there, the plan's limit, a run that failed."""


def _short(text: str, n: int = 280) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _tool_line(name: str, inp: dict) -> str:
    path = re.sub(r"^/work/?", "", str(inp.get("file_path") or inp.get("path") or ""))
    if name in ("Write", "Edit", "MultiEdit"):
        return f"{'Wrote' if name == 'Write' else 'Edited'} {path}"
    if name == "Read":
        return f"Read {path}"
    if name == "Bash":
        return "Ran " + _short(inp.get("command", ""), 160)
    if name in ("Glob", "Grep"):
        return f"Searched for {_short(inp.get('pattern', ''), 80)}"
    if name == "TodoWrite":
        todos = inp.get("todos") or []
        doing = next((t.get("content") for t in todos if t.get("status") == "in_progress"), None)
        return f"Plan: {sum(t.get('status') == 'completed' for t in todos)}/{len(todos)} done" + (f", now {_short(doing, 100)}" if doing else "")
    if name == "WebSearch":
        return f"Searched the web for {_short(inp.get('query', ''), 100)}"
    if name == "WebFetch":
        return f"Read {_short(inp.get('url', ''), 120)}"
    return name


# What a step is, for someone who doesn't read code: by the command it runs or the file it writes.
_PLAIN = [
    (r"^Ran .*\b(pip3?|npm) (install|i)\b|get-pip", "Installing tools"),
    (r"^Searched the web|^Read https?:", "Looking something up on the web"),
    (r"^Ran .*(tools/render\.mjs|render)", "Rendering the video"),
    (r"^Ran .*(tools/shot\.mjs|still|poster|contact)", "Drawing stills to check the look"),
    (r"^Ran (ffmpeg|ffprobe)", "Working on the video file"), (r"node --check", "Checking the code"),
    (r"^Read .*\.(png|jpg|jpeg)$", "Looking at a frame"), (r"^(Wrote|Edited) .*\.(glsl|frag|vert|js|mjs|html|py)$", "Writing the code"),
    (r"^(Wrote|Edited)", "Writing files"), (r"^(Read|Searched)|^Ran (ls|wc|mkdir|cat|head)", "Looking through the song and its files"),
]


def plain(line: dict) -> str:
    text = str(line.get("text") or "")
    if line.get("kind") != "tool":
        return text
    if text.startswith("Plan:"):
        return text.replace("Plan:", "Working through the plan:", 1)
    return next((say for pattern, say in _PLAIN if re.search(pattern, text)), "Working")


def summarize(event: dict) -> list[dict]:
    """Interface lines for one stream-json event: {kind: say|tool|result|limit|error, text}."""
    t = event.get("type")
    if t == "assistant":
        lines = []
        for block in (event.get("message") or {}).get("content") or []:
            if block.get("type") == "text" and block.get("text", "").strip():
                lines.append({"kind": "say", "text": _short(block["text"], 600)})
            elif block.get("type") == "tool_use":
                lines.append({"kind": "tool", "text": _tool_line(block.get("name", ""), block.get("input") or {})})
        return lines
    if t == "result":
        text = str(event.get("result") or "")
        if event.get("is_error") and re.search(r"usage limit|rate limit|limit reached", text, re.I):
            return [{"kind": "limit", "text": _short(text, 300)}]
        if event.get("subtype") == "error_max_turns":
            return [{"kind": "error", "text": f"The director used all {event.get('num_turns')} steps this session allows."}]
        return [{"kind": "error" if event.get("is_error") else "result", "text": _short(text, 1200)}]
    return []


def machine_trouble(text: str) -> str | None:
    """A plain reason when the studio container couldn't start because of the machine, not the film: an update to
    the NVIDIA driver's libraries that runs ahead of the loaded driver until the machine restarts."""
    if re.search(r"Driver/library version mismatch|libnvidia|libEGL_nvidia|libcuda\.so", text):
        return "The graphics driver was updated, and the machine needs a restart before the studio can start."
    return None


def private_file(folder: Path, data: dict) -> Path:
    """A JSON file only this user can read (0600, created that way), for handing a container something secret."""
    f = folder / f".sv-{uuid.uuid4().hex[:12]}.json"
    fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as out:
        json.dump(data, out)
    return f


async def run(studio_sh: Path, work: Path, prompt: str, *, model: str = "claude-opus-5-5", effort: str | None = "high",
              max_turns: int = 400, timeout: float = 3600, on_line: Callable[[dict], None] | None = None,
              is_cancelled: Callable[[], bool] = lambda: False, resume: str | None = None,
              connectors: list[str] | None = None, mcp: dict | None = None) -> dict[str, Any]:
    """One free-rein session in `work` (or, with `resume`, the next turn of an earlier one: a note from the person).
    `connectors`: MCP tools it may use, by server (["mcp__claude_ai_<Name>"] for a connector on the Claude account,
    ["mcp__<name>"] for a server in `mcp`, Claude Code's --mcp-config); the session then waits for them to connect
    before its first turn (see providers.Claude). Returns {state: done|failed|limit|cancelled|timeout, result, lines,
    seconds, session}."""
    if not studio_sh.exists():
        raise StudioError("The studio for videos made in code isn't set up on this machine (infra/studio).")
    name = f"sv-finish-{uuid.uuid4().hex[:10]}"
    args = ["-p", "--model", model, "--output-format", "stream-json", "--verbose", "--permission-mode", "acceptEdits",
            "--allowedTools", *FREE_TOOLS, *(connectors or []), "--max-turns", str(max_turns),
            # Claude Code's own memory is shared by every studio session (they all work in /work): off, so each film
            # starts with fresh eyes instead of what earlier films learned and liked
            "--settings", json.dumps({"autoMemoryEnabled": False,
                                      "env": SHELL_ENV | ({"MCP_CONNECTION_NONBLOCKING": "0"} if connectors else {})})]
    if effort:
        args += ["--effort", effort]
    # MCP servers carry keys and sign-in tokens: in a private file in the session's folder, read by Claude Code as it
    # starts and deleted as soon as it has (never on a command line, where any process list would show them)
    secret = private_file(work, mcp) if mcp and mcp.get("mcpServers") else None
    if secret:
        args += ["--mcp-config", f"/work/{secret.name}"]
    if resume:
        args += ["--resume", resume]
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "CLAUDE_"))} | {"SV_STUDIO_NAME": name}
    proc = await asyncio.create_subprocess_exec(str(studio_sh), "run", str(work), *args, stdin=asyncio.subprocess.PIPE,
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env,
                                                limit=16 * 1024 * 1024)
    assert proc.stdin and proc.stdout
    proc.stdin.write(prompt.encode())  # on stdin: as an argument, text starting with "-" would read as an option
    await proc.stdin.drain()
    proc.stdin.close()
    started = time.monotonic()
    lines: list[dict] = []
    result: dict | None = None
    session = resume
    state = "running"

    async def stop() -> None:
        stopper = await asyncio.create_subprocess_exec("docker", "stop", "-t", "10", name, stdout=asyncio.subprocess.DEVNULL,
                                                       stderr=asyncio.subprocess.DEVNULL)
        await stopper.wait()

    log = (work.parent / "session.jsonl").open("a")
    try:
        while True:
            if is_cancelled():
                state = "cancelled"
                await stop()
                break
            if time.monotonic() - started > timeout:
                state = "timeout"
                await stop()
                break
            try:
                raw = await asyncio.wait_for(proc.stdout.readline(), 5)
            except TimeoutError:
                continue
            if not raw:
                break
            log.write(raw.decode(errors="replace"))
            log.flush()
            try:
                event = json.loads(raw)
            except ValueError:
                continue
            if event.get("session_id"):
                session = event["session_id"]
            if secret and event.get("type") == "system":  # Claude Code has read its MCP servers
                secret.unlink(missing_ok=True)
            for line in summarize(event):
                line["at"] = round(time.monotonic() - started)
                lines.append(line)
                if on_line:
                    try:
                        on_line(line)
                    except Exception:  # noqa: BLE001  the job was stopped as it reported (or the page update failed)
                        if is_cancelled():
                            break
            if is_cancelled():  # stopped: the container goes too, never left running on its own
                state = "cancelled"
                await stop()
                break
            if event.get("type") == "result":
                result = event
    finally:
        log.close()
        if secret:
            secret.unlink(missing_ok=True)
    code = await proc.wait()
    err = (await proc.stderr.read()).decode(errors="replace").strip() if proc.stderr else ""
    if state == "running":
        last = lines[-1]["kind"] if lines else None
        state = "limit" if last == "limit" else "done" if code == 0 and result and not result.get("is_error") else "failed"
        if state == "failed" and err and last not in ("error", "limit"):
            lines.append({"kind": "error", "text": machine_trouble(err) or _short(err, 600)})
    return {"state": state, "result": result, "lines": lines[-60:], "seconds": round(time.monotonic() - started),
            "session": session}
