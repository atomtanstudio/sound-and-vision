import types

from sv import studio
from sv.video import kinetic
from sv.writers import EFFORTS, Writers


class _Store:
    def __init__(self):
        self.saved = {}

    def setting(self, key):
        return self.saved.get(key)

    def set_setting(self, key, value):
        self.saved[key] = value


def _writers():
    w = Writers.__new__(Writers)
    w.store = _Store()
    w.providers = {"claude": object(), "local": object()}
    w.machine, w.mitte = "the server", False
    w.mcp = types.SimpleNamespace(listed=lambda: [])
    return w


def test_videos_in_code_default_to_opus_at_extra_high():
    w = _writers()
    assert w.film() == {"model": "claude-opus-5-5", "effort": "xhigh"} and "xhigh" in EFFORTS


def test_reasoning_is_kept_for_claude_only_and_films_are_claude_only():
    w = _writers()
    w.set_who("lyrics", [{"provider": "claude", "model": "claude-haiku-5-5", "effort": "high"},
                         {"provider": "local", "model": None, "effort": "max"}])
    assert w.who()["lyrics"] == [{"provider": "claude", "model": "claude-haiku-5-5", "effort": "high"},
                                 {"provider": "local", "model": None}]
    w.set_who("film", [{"provider": "local", "model": None}, {"provider": "claude", "model": "claude-fable-5-1", "effort": "max"}])
    assert w.film() == {"model": "claude-fable-5-1", "effort": "max"}
    w.set_who("film", [{"provider": "claude", "model": "claude-opus-5-5", "effort": "sideways"}])
    assert w.film() == {"model": "claude-opus-5-5", "effort": None}


def test_the_request_is_the_person_s_own_chat_prompt():
    sung = kinetic.OPENING[True].format(title="Go", by=" by The Chemical Brothers")
    bare = kinetic.OPENING[False].format(title="Go", by=" by The Chemical Brothers")
    for text in (sung, bare):
        assert "dynamic motion graphics music video" in text and "incredible motion designer" in text and "Go all out" in text
        assert "kinetic typography" not in text.lower()
    assert "with lyrics" in sung and "showreel" in sung and "timing.json" in sung and "lyrics" not in bare
    assert "lyrics" in kinetic.HARD and kinetic.SHAPES["wide"] == (1920, 1080)


def test_a_film_session_gets_what_a_desktop_chat_gets_and_no_old_rules():
    from pathlib import Path
    import inspect
    from sv.video import finish, folder
    assert {"Bash", "WebSearch", "WebFetch", "Agent", "Skill"} <= set(studio.FREE_TOOLS)
    assert not any("(" in t for t in studio.FREE_TOOLS)  # the whole shell, not a list of commands
    src = inspect.getsource(studio.run)
    assert "--add-dir" not in src and "disallowedTools" not in src  # an added dir's .claude/skills would load
    assert studio.SHELL_ENV["PYTHONUSERBASE"] == "/work/.local"
    notes = "\n".join(Path(f).read_text() for f in (kinetic.RULES, finish.RULES, folder.MACHINE))
    for old in ("playbook", "KIT.md", "METHOD.md", "toolbox", "skill", "src/engine", "no npm or pip", "what the person loves"):
        assert old.lower() not in notes.lower(), old
    assert "Never type the song's lyrics" in kinetic.RULES.read_text()


def test_studio_lines_read_plainly():
    ev = {"type": "assistant", "message": {"content": [
        {"type": "text", "text": "Rendering a draft now."},
        {"type": "tool_use", "name": "Bash", "input": {"command": "node tools/render.mjs --out out/draft.mp4"}},
        {"type": "tool_use", "name": "Read", "input": {"file_path": "/work/out/review/still_12.png"}}]}}
    lines = studio.summarize(ev)
    assert [studio.plain(x) for x in lines] == ["Rendering a draft now.", "Rendering the video", "Looking at a frame"]
    assert studio.summarize({"type": "result", "is_error": True, "result": "Claude usage limit reached"})[0]["kind"] == "limit"
    web = studio.summarize({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Bash", "input": {"command": "pip install moderngl"}},
        {"type": "tool_use", "name": "WebSearch", "input": {"query": "Pyramid Song time signature"}}]}})
    assert [studio.plain(x) for x in web] == ["Installing tools", "Looking something up on the web"]


def test_pictures_come_from_the_gpu_unless_chosen_and_mitte_only_where_it_is_turned_on():
    w = _writers()
    assert w.who()["covers"] == [{"provider": "local"}] and w.who()["scenes"] == [{"provider": "local"}]
    assert "mitte" not in w.image_ids() and all(c["id"] != "mitte" for c in w.image_choices())
    w.set_who("covers", [{"provider": "mitte"}])  # not offered here: ignored
    assert w.picture_by("covers") == "local"
    w.mitte = True
    assert w.picture_by("scenes") == "local"  # even where it's on: the owner's Mitte is an MCP server of theirs now
    w.set_who("covers", [{"provider": "mitte"}])
    assert w.picture_by("covers") == "mitte"  # (still there for an install that chose it)
    w.mcp = types.SimpleNamespace(listed=lambda: [{"id": "abc", "name": "Pics", "ok": True, "paid": True}])
    w.set_who("scenes", [{"provider": "mcp:abc"}])
    assert w.picture_by("scenes") == "mcp:abc"
    assert next(c for c in w.image_choices() if c["id"] == "mcp:abc")["paid"] is True
    w.mcp = types.SimpleNamespace(listed=lambda: [])  # the server was removed: back to the default
    assert w.picture_by("scenes") == "local"
    w.mitte = False
    assert w.picture_by("covers") == "local"


def test_the_interface_names_a_model_only_once_it_is_connected():
    import asyncio

    class P:
        def __init__(self, on, models=()):
            self.on, self.models = on, list(models)

        async def status(self):
            return {"connected": self.on, "models": self.models}
    w = _writers()
    w.providers = {"claude": P(False), "local": P(True, [{"id": "qwen3.5:4b", "name": "qwen3.5:4b", "default": True}]),
                   "openai": P(False), "grok": P(False)}
    got = asyncio.run(w.doers())
    assert got["roles"]["lyrics"] == {"provider": "local", "name": "your local model", "model": "qwen3.5:4b"}  # the fallback
    assert got["roles"]["direct"]["provider"] == "local"  # a local-only install still plans its videos
    assert got["roles"]["film"] is None  # but nothing connected can direct a video in code
    assert got["plan"] is None and got["filmModels"] == []
    w.providers["claude"] = P(True, [{"id": "claude-opus-5-5", "name": "Opus 5.5", "default": False}])
    got = asyncio.run(w.doers())
    assert got["roles"]["film"]["name"] == "Claude" and got["plan"] == "Claude" and got["filmModels"]
