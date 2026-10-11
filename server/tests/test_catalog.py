import asyncio
import types

import pytest

from sv import catalog, covers
from sv.catalog import Catalogs, choice_words, clean, clean_choice, lookups, summary
from sv.video import music
from sv.writers import Writers


class _Store:
    def __init__(self):
        self.saved = {}

    def setting(self, key):
        return self.saved.get(key)

    def set_setting(self, key, value):
        self.saved[key] = value


SERVER = {"id": "abc123", "name": "Pics Place", "url": "https://pics.example.com/mcp", "ok": True, "paid": True,
          "tools": [{"name": "search_nodes", "readOnly": True}, {"name": "get_node", "readOnly": True},
                    {"name": "list_resolutions"}, {"name": "run_node"}, {"name": "generate_video"},
                    {"name": "upload_files", "readOnly": True}, {"name": "select_folder"}]}

RAW = {"image": [{"id": "gpt-image-25", "name": "GPT Image 2.5", "note": "Real text.", "options": [
                     {"key": "resolution", "label": "Resolution", "values": ["1K", "2K", "4K"], "default": "2K"},
                     {"key": "quality", "label": "Quality", "values": ["low", "high"], "default": "medium"},
                     {"key": "aspect_ratio", "label": "Shape", "values": ["1:1", "16:9"], "default": "1:1"},
                     {"key": "background", "label": "Background", "values": ["auto"], "default": "auto"}]},
                 {"id": "gpt-image-25", "name": "again", "note": "", "options": []},
                 {"id": "", "name": "no id", "note": "", "options": []}],
       "video": [{"id": "minimax-h3", "name": "MiniMax H3", "note": "", "options": [
                     {"key": "duration", "label": "Clip length (seconds)", "values": [str(n) for n in range(5, 16)], "default": "5"},
                     {"key": "prompt", "label": "Prompt", "values": ["a", "b"], "default": ""}]}]}


def _writers(store=None, servers=(SERVER,)):
    w = Writers.__new__(Writers)
    w.store = store or _Store()
    w.providers = {"claude": object(), "local": object()}
    w.machine, w.mitte = "the server", False
    w.mcp = types.SimpleNamespace(listed=lambda: [dict(s) for s in servers], get=lambda sid: next((dict(s) for s in servers if s["id"] == sid), None))
    w.catalogs = None
    w.on_mcp = None
    return w


def test_a_catalog_keeps_only_settings_a_person_can_choose():
    got = clean(RAW)
    assert [m["id"] for m in got["image"]] == ["gpt-image-25"]  # the repeat and the one without an id are dropped
    opts = {o["key"]: o for o in got["image"][0]["options"]}
    assert set(opts) == {"resolution", "quality"}  # the shape is the app's, and one value is no choice
    assert opts["resolution"]["default"] == "2K" and opts["quality"]["default"] == ""  # a default it doesn't list goes
    assert [o["key"] for o in got["video"][0]["options"]] == ["duration"] and len(got["video"][0]["options"][0]["values"]) == 11
    assert clean({"image": "nonsense"}) == {"image": [], "video": []} and clean(None) == {"image": [], "video": []}


def test_reading_a_catalog_may_only_look_things_up():
    # read-only by the server's word or by its name, but never a tool that makes, uploads or picks something
    assert lookups(SERVER["tools"]) == ["search_nodes", "get_node", "list_resolutions"]


def test_a_role_keeps_the_model_and_settings_chosen_on_an_mcp_server():
    w = _writers()
    w.set_who("motion", [{"provider": "mcp:abc123", "model": "minimax-h3",
                          "options": {"duration": "5", "aspect_ratio": "16:9", "bad key!": "x", "resolution": ""}}])
    assert w.store.saved["who"]["motion"] == [{"provider": "mcp:abc123", "model": "minimax-h3", "options": {"duration": "5"}}]
    w.set_who("covers", [{"provider": "local", "model": "sneaky", "options": {"quality": "max"}}])
    assert w.store.saved["who"]["covers"] == [{"provider": "local"}]  # only an MCP server carries a model here
    assert clean_choice("", {"quality": "high"}) == {} and clean_choice("m", "x") == {"model": "m"}


def test_the_job_is_told_the_model_and_settings_and_the_person_sees_them(tmp_path):
    cats = Catalogs(tmp_path / "cats")
    cats._put("abc123", {"at": 1, **clean(RAW)})
    step = {"provider": "mcp:abc123", "model": "gpt-image-25", "options": {"resolution": "2K", "quality": "high"}}
    words = choice_words(cats, "abc123", "image", step)
    assert words == "GPT Image 2.5 (`gpt-image-25`), with Resolution `resolution` = 2K, Quality `quality` = high"
    assert summary(cats, "abc123", "image", step) == "GPT Image 2.5, 2K, high"
    assert choice_words(cats, "abc123", "image", {"provider": "mcp:abc123"}) == ""  # its own default: nothing said
    assert summary(cats, "abc123", "video", {"model": "not-listed"}) == "not-listed"  # a model the catalog lost still shows
    assert summary(cats, "abc123", "video", {"model": "minimax-h3", "options": {"duration": "5"}}) == "MiniMax H3, 5 s"

    w = _writers()
    w.catalogs = cats
    w.set_who("covers", [step])
    assert w.using("covers") == "GPT Image 2.5, 2K, high" and w.using("scenes") == ""

    notes = music.pictures_section("mcp:abc123", False, SERVER, words) + music.motion_section("mcp:abc123", SERVER, "MiniMax H3 (`minimax-h3`)")
    assert "Make every picture with GPT Image 2.5 (`gpt-image-25`), with Resolution" in notes
    assert "Make every clip with MiniMax H3 (`minimax-h3`)" in notes and "use no other model" in notes
    assert "Make every" not in music.motion_section("mcp:abc123", SERVER)  # the server's own default: nothing added


def test_a_cover_from_an_mcp_server_is_made_with_the_chosen_model():
    asked = {}

    class Claude:
        async def complete(self, system, prompt, schema, model=None, **kw):
            asked["prompt"] = prompt
            return {"status": "done", "url": "https://pics.example.com/p.png", "error": ""}

    w = types.SimpleNamespace(providers={"claude": Claude()}, who=lambda: {"chores": [{"provider": "local"}]},
                              mcp=types.SimpleNamespace(allowed=lambda ids: ["mcp__pics_place"], claude_config=_config))
    url = asyncio.run(covers.make_picture_with(w, SERVER, "a lighthouse", "1:1", "GPT Image 2.5 (`gpt-image-25`)"))
    assert url.startswith("https://") and "- Make it with GPT Image 2.5 (`gpt-image-25`)." in asked["prompt"]
    asyncio.run(covers.make_picture_with(w, SERVER, "a lighthouse", "1:1"))
    assert "Make it with" not in asked["prompt"]


async def _config(ids):
    return {"mcpServers": {"pics_place": {"type": "http", "url": SERVER["url"]}}}


def test_a_catalog_is_read_with_only_look_up_tools_and_kept(tmp_path):
    seen = {}

    class Claude:
        async def complete(self, system, prompt, schema, model=None, timeout=0, tools=None, turns=0, mcp=None, **kw):
            seen.update(prompt=prompt, tools=tools, model=model, mcp=mcp)
            return RAW

    w = _writers()
    w.providers = {"claude": Claude()}
    w.mcp = types.SimpleNamespace(get=lambda sid: dict(SERVER) if sid == "abc123" else None, claude_config=_config)
    w.who = lambda: {"chores": [{"provider": "claude", "model": "claude-opus-5-5"}]}
    got = asyncio.run(catalog.read(w, "abc123"))
    assert seen["tools"] == ["mcp__pics_place__search_nodes", "mcp__pics_place__get_node", "mcp__pics_place__list_resolutions"]
    assert seen["model"] == "claude-opus-5-5" and "`search_nodes`" in seen["prompt"] and "only look things up" in seen["prompt"]
    assert got["image"][0]["id"] == "gpt-image-25"

    cats = Catalogs(tmp_path / "cats")
    told = []
    w.on_mcp = lambda: told.append(1)

    async def both():
        cats.start(w, "abc123")
        assert cats.public("abc123")["state"] == "reading"
        await asyncio.gather(*cats._tasks)
    asyncio.run(both())
    assert cats.public("abc123")["state"] == "ready" and told == [1]
    assert cats.model("abc123", "video", "minimax-h3")["name"] == "MiniMax H3"
    cats.drop("abc123")
    assert cats.public("abc123") == {"state": "none"}


def test_a_catalog_that_fails_says_why_and_keeps_what_it_had(tmp_path):
    class Claude:
        async def complete(self, *a, **kw):
            return {"image": [], "video": []}

    w = _writers()
    w.providers = {"claude": Claude()}
    w.mcp = types.SimpleNamespace(get=lambda sid: dict(SERVER), claude_config=_config)
    w.who = lambda: {}
    with pytest.raises(ValueError, match="No models came back"):
        asyncio.run(catalog.read(w, "abc123"))
    w.mcp = types.SimpleNamespace(get=lambda sid: dict(SERVER, ok=False), claude_config=_config)
    with pytest.raises(ValueError, match="isn't answering"):
        asyncio.run(catalog.read(w, "abc123"))

    cats = Catalogs(tmp_path / "cats")
    cats._put("abc123", {"at": 1, **clean(RAW)})

    async def again():
        cats.start(w, "abc123")
        await asyncio.gather(*cats._tasks)
    asyncio.run(again())
    got = cats.public("abc123")
    assert got["state"] == "error" and "isn't answering" in got["error"] and got["image"][0]["id"] == "gpt-image-25"


def test_the_tools_that_make_pictures_and_video_are_read_in_full():
    names = ["generate_image", "generate_video", "generate_drone_video", "animate_fashion_image", "list_fashion_models",
             "generate_video_captions", "request_image_upload", "edit_photo", "run_node", "get_node", "search_nodes",
             "get_balance", "generate_logo"]
    tools = [{"name": n, "description": f"{n} " + "x" * 30, "inputSchema": {"type": "object"}} for n in names]
    assert [t["name"] for t in catalog.makers(tools)] == ["generate_image", "generate_video", "run_node"]
    text = catalog.words([{"name": "generate_video", "description": "models: " + "m, " * 2000 + "minimax-h3 (last)",
                           "inputSchema": {"properties": {"duration": {"type": "string"}}}}])
    assert "minimax-h3 (last)" in text and '"duration"' in text  # a long description isn't cut short
    assert catalog.words([{"name": "get_balance"}]) == ""
    huge = [{"name": f"generate_image_{i}", "description": "y" * 40_000} for i in range(3)]
    assert len(catalog.words(huge)) < catalog.WORDS_BUDGET + 500


def test_a_server_that_answers_gets_its_models_read_once_by_itself(tmp_path):
    started = []

    class Claude:
        def __init__(self, on):
            self.on = on

        async def status(self):
            return {"connected": self.on}

    w = _writers()
    w.catalogs = Catalogs(tmp_path / "cats")
    w.catalogs.start = lambda writers, sid: started.append(sid)
    w.providers = {"claude": Claude(True)}
    asyncio.run(w.read_models_once("abc123"))
    assert started == ["abc123"]
    w.catalogs._put("abc123", {"at": 1, "image": [], "video": []})
    asyncio.run(w.read_models_once("abc123"))  # read already: only when the person asks again
    assert started == ["abc123"]
    w.catalogs.drop("abc123")
    w.providers = {"claude": Claude(False)}
    asyncio.run(w.read_models_once("abc123"))  # no Claude to read it: left for the person to ask, later
    w.mcp = types.SimpleNamespace(get=lambda sid: dict(SERVER, ok=False))
    w.providers = {"claude": Claude(True)}
    asyncio.run(w.read_models_once("abc123"))  # one that isn't answering isn't read
    asyncio.run(w.read_models_once("gone"))
    assert started == ["abc123"]
