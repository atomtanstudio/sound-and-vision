"""What an MCP server's models are: the ones that make pictures and the ones that turn a still into a clip, each with
the settings a person might choose for it (resolution, quality, clip length: what changes the result and the price).

A catalog is read when the person asks (Settings), by Claude: it reads the server's own descriptions of its tools, and
may call only the tools that look things up (a catalog search, a model's details), never one that makes, uploads or
changes anything, so reading it costs nothing on the server. It's kept in data/mcp-catalogs/<server id>.json.

Settings then offers a model and its settings beside the server, for album covers, music video pictures and clips;
the job is told to use exactly those (see choice_words)."""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .mcp import slug

if TYPE_CHECKING:
    from .writers import Writers

KINDS = ("image", "video")
MOST_MODELS, MOST_OPTIONS, MOST_VALUES = 40, 8, 40
KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,39}$")
# what the app decides itself, never offered as a setting
APP_DECIDES = re.compile(r"aspect|(^|_)ratio($|_)|prompt|image|picture|urls?$|mask|(^|_)org(_|$)|folder|seed|count|"
                         r"^n$|num_(images|outputs)|file|negative", re.I)
# a tool that only looks things up: the server says so (readOnlyHint), or its name does and it isn't marked destructive
LOOKUP = re.compile(r"^(search|list|get|fetch|describe|lookup|find)_", re.I)
# the tools whose own words a catalog is read from, in full (Claude Code shortens long descriptions, and a server's
# model list is often in one): those that make pictures or video, or name models, not a single-purpose maker
MAKES = re.compile(r"image|picture|photo|video|clip|animat|model|node|catalog", re.I)
SINGLE = re.compile(r"fashion|avatar|logo|thumbnail|carousel|(^|_)ads?(_|$)|caption|music|audio|cooking|drone|jewel|"
                    r"interior|instagram|showcase|background|enhance|upscal|edit|effect|status|upload|delete|update|"
                    r"product|project|folder|asset|balance|widget", re.I)
WORDS_BUDGET = 48_000  # characters of tool descriptions and schemas, at most

CHANGES = re.compile(r"generat|run|create|upload|delete|remove|update|edit|apply|enhance|animate|restyle|extract|"
                     r"composite|select|submit|buy|pay|cancel|train", re.I)

OPTION = {"type": "object", "additionalProperties": False, "required": ["key", "label", "values", "default"],
          "properties": {"key": {"type": "string"}, "label": {"type": "string"},
                         "values": {"type": "array", "items": {"type": "string"}}, "default": {"type": "string"}}}
MODEL = {"type": "object", "additionalProperties": False, "required": ["id", "name", "note", "options"],
         "properties": {"id": {"type": "string"}, "name": {"type": "string"}, "note": {"type": "string"},
                        "options": {"type": "array", "items": OPTION}}}
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["image", "video"],
          "properties": {"image": {"type": "array", "items": MODEL}, "video": {"type": "array", "items": MODEL}}}

ASK = """List the models the MCP server "{name}" can run for two jobs:
- image: a picture from a text prompt (some also take reference pictures);
- video: a short clip that starts from a still picture (image-to-video).

Its tools are yours to read (`mcp__{slug}__…`). Their descriptions and input schemas often list the models and each
model's allowed values. If the server has catalog tools (search, list, get), use them to find its models and read each
one's inputs. {lookups} You can't make, upload or change anything, and nothing should be: only look things up.
{words}
For each model:
- id: exactly what the server's tools take to choose it (its model name or slug, as written);
- name: its human name;
- note: one short line: what it's good at, and its price only if the server states one (never guess a price);
- options: only the settings that change the quality, size, length or price of what it makes, as the server lists them
  for that model: resolution, quality, duration (clip length, in seconds) and the like. Each has key (the input's name,
  exactly as the tool takes it), label (a few plain words), values (every allowed value as a string, smallest or
  cheapest first; for a range of whole seconds, list each one) and default (the server's default, or "" if it doesn't
  say). Leave out the aspect ratio, the prompt, pictures and other media, seeds, and account or folder ids: the app
  sets those.

Leave a model out of a job it can't do: an image model under video, or a video model that can't start from a still.
List at most {most} models a job, the server's own default first. If the server can't do a job, its list is empty."""


def lookups(tools: list[dict]) -> list[str]:
    """The tools of a server that only look things up, by name."""
    return [t["name"] for t in tools if t.get("name") and not CHANGES.search(t["name"]) and
            (t.get("readOnly") or LOOKUP.match(t["name"]))]


def makers(tools: list[dict]) -> list[dict]:
    """The tools a catalog is read from, most likely first: those that make pictures or video, or list models."""
    def score(t: dict) -> int:
        n = t.get("name") or ""
        return (3 * bool(MAKES.search(n)) + 2 * bool(re.match(r"(generate|create|make|run|text_to|image_to)", n, re.I))
                - 6 * bool(SINGLE.search(n)))
    return sorted((t for t in tools if score(t) >= 4), key=score, reverse=True)[:6]


def words(tools: list[dict]) -> str:
    """Those tools' own descriptions and inputs, in full (within a budget), for the prompt."""
    out, left = [], WORDS_BUDGET
    for t in makers(tools):
        text = (f"### {t.get('name')}\n{(t.get('description') or '').strip()}\n\nInputs: "
                f"{json.dumps(t.get('inputSchema') or {}, separators=(',', ':'))}")[:left]
        out.append(text)
        left -= len(text)
        if left <= 0:
            break
    if not out:
        return ""
    return ("\nWhat the server says about its tools that make pictures or video, in full (your own view of them may be "
            "shortened, so go by this):\n<<<\n" + "\n\n".join(out) + "\n>>>\n")


def clean(raw: Any) -> dict:
    """A catalog as Claude gave it, made safe to keep and show: sizes capped, settings the app decides dropped, each
    setting with at least two values to choose from."""
    out: dict[str, list] = {}
    for kind in KINDS:
        models, seen = [], set()
        for m in (raw or {}).get(kind) or []:
            if not isinstance(m, dict):
                continue
            mid = str(m.get("id") or "").strip()[:120]
            if not mid or mid in seen:
                continue
            seen.add(mid)
            options, keys = [], set()
            for o in m.get("options") or []:
                if not isinstance(o, dict):
                    continue
                key = str(o.get("key") or "").strip()
                if not KEY.match(key) or APP_DECIDES.search(key) or key in keys:
                    continue
                values = list(dict.fromkeys(str(v).strip()[:40] for v in o.get("values") or [] if str(v).strip()))[:MOST_VALUES]
                if len(values) < 2:
                    continue
                keys.add(key)
                default = str(o.get("default") or "").strip()
                options.append({"key": key, "label": " ".join(str(o.get("label") or key).split())[:40],
                                "values": values, "default": default if default in values else ""})
            models.append({"id": mid, "name": " ".join(str(m.get("name") or mid).split())[:80],
                           "note": " ".join(str(m.get("note") or "").split())[:200], "options": options[:MOST_OPTIONS]})
            if len(models) == MOST_MODELS:
                break
        out[kind] = models
    return out


def clean_choice(model: Any, options: Any) -> dict:
    """A role's model and settings for an MCP server, as the interface sent them: {model?, options?}."""
    out: dict[str, Any] = {}
    if isinstance(model, str) and model.strip():
        out["model"] = model.strip()[:120]
        if isinstance(options, dict):
            kept = {str(k): str(v).strip()[:40] for k, v in list(options.items())[:MOST_OPTIONS]
                    if KEY.match(str(k)) and not APP_DECIDES.search(str(k)) and str(v).strip()}
            if kept:
                out["options"] = kept
    return out


class Catalogs:
    """The catalogs read so far, and the ones being read now."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.reading: dict[str, float] = {}  # server id → when its reading started
        self._tasks: set[asyncio.Task] = set()

    def _file(self, sid: str) -> Path:
        return self.folder / f"{re.sub(r'[^a-z0-9]', '', sid)[:20]}.json"

    def get(self, sid: str) -> dict | None:
        try:
            return json.loads(self._file(sid).read_text())
        except (OSError, ValueError):
            return None

    def _put(self, sid: str, data: dict) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = self._file(sid).with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1))
        tmp.replace(self._file(sid))

    def drop(self, sid: str) -> None:
        self._file(sid).unlink(missing_ok=True)

    def public(self, sid: str) -> dict:
        """For the interface: {state: none|reading|ready|error, at, error, image, video}."""
        if sid in self.reading:
            return {"state": "reading", "since": self.reading[sid]}
        got = self.get(sid)
        if not got:
            return {"state": "none"}
        return {"state": "error" if got.get("error") else "ready", **got}

    def model(self, sid: str, kind: str, mid: str | None) -> dict | None:
        return next((m for m in (self.get(sid) or {}).get(kind) or [] if m["id"] == mid), None) if mid else None

    def start(self, writers: "Writers", sid: str) -> None:
        """Read a server's catalog in the background (once at a time)."""
        if sid in self.reading:
            return
        self.reading[sid] = time.time()
        task = asyncio.create_task(self._read(writers, sid))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _read(self, writers: "Writers", sid: str) -> None:
        try:
            self._put(sid, {"at": time.time(), **await read(writers, sid)})
        except Exception as exc:  # noqa: BLE001 (kept for the interface to show; the old catalog, if any, stays)
            old = self.get(sid) or {}
            self._put(sid, {**{k: old.get(k, []) for k in KINDS}, "at": time.time(), "error": str(exc)[:300] or "It didn't answer."})
        finally:
            self.reading.pop(sid, None)
            if writers.on_mcp:
                writers.on_mcp()


async def read(writers: "Writers", sid: str) -> dict:
    """A server's catalog, read by Claude with only its look-up tools (Claude Code refuses every other tool)."""
    from .writers.providers import WriterError
    server = writers.mcp.get(sid)
    if server is None:
        raise ValueError("That MCP server isn't in Settings any more.")
    if not server.get("ok"):
        raise ValueError(f"{server['name']} isn't answering: check it again, or sign in, first.")
    name = slug(server["name"])
    tools = [f"mcp__{name}__{t}" for t in lookups(server.get("tools") or [])]
    try:
        said = words(await writers.mcp.tools_of(sid))
    except Exception:  # noqa: BLE001 (Claude still sees the tools through its own connection)
        said = ""
    step = (writers.who().get("chores") or [{}])[0]  # the small-chores model when it's a Claude one, else Sonnet
    model = step.get("model") if step.get("provider") == "claude" and step.get("model") else "sonnet"
    try:
        raw = await writers.providers["claude"].complete(
            "You read an MCP server's tools to list its models for an app, and answer only with the JSON asked for.",
            ASK.format(name=server["name"], slug=name, most=MOST_MODELS,
                       lookups=("Its look-up tools: " + ", ".join(f"`{t.split('__')[-1]}`" for t in tools) + ".") if tools else
                       "It has no look-up tools, so read what its tools say about themselves.", words=said),
            SCHEMA, model, timeout=900, tools=tools or None, turns=80, mcp=await writers.mcp.claude_config([sid]))
    except WriterError as exc:
        raise ValueError(f"Claude couldn't read {server['name']}'s models: {exc}") from None
    got = clean(raw)
    if not got["image"] and not got["video"]:
        raise ValueError(f"No models came back from {server['name']}.")
    return got


def choice_words(catalogs: Catalogs, sid: str, kind: str, step: dict | None) -> str:
    """The model and settings the person chose for a job, in words for whoever drives the server ("" for its own
    default): "GPT Image 2.5 (`gpt-image-25`), with resolution 2K and quality high"."""
    mid = (step or {}).get("model")
    if not mid:
        return ""
    m = catalogs.model(sid, kind, mid)
    label = {o["key"]: o["label"] for o in (m or {}).get("options") or []}
    opts = [f"{label.get(k, k)} `{k}` = {v}" for k, v in ((step or {}).get("options") or {}).items()]
    return (f"{m['name']} (`{mid}`)" if m and m["name"] != mid else f"`{mid}`") + (", with " + ", ".join(opts) if opts else "")


def summary(catalogs: Catalogs, sid: str, kind: str, step: dict | None) -> str:
    """The same, short, for the person ("GPT Image 2.5, 2K, high")."""
    mid = (step or {}).get("model")
    if not mid:
        return ""
    m = catalogs.model(sid, kind, mid)
    label = {o["key"]: o["label"] for o in (m or {}).get("options") or []}

    def shown(k: str, v: str) -> str:  # a clip length in whole seconds reads "5 s"
        return f"{v} s" if v.isdigit() and re.search(r"second|duration|length", f"{k} {label.get(k, '')}", re.I) else v
    return ", ".join([m["name"] if m else mid, *(shown(k, v) for k, v in ((step or {}).get("options") or {}).items())])
