import asyncio
import json
import types

import pytest

from sv import localpics
from sv.video import music
from sv.writers import Writers, WriterError
from sv.writers.grok_media import Stream


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
    w.machine, w.mitte = "Studio", False
    w.mcp = types.SimpleNamespace(listed=lambda: [])
    w.local = localpics.Available()
    return w


def test_local_models_are_named_by_their_choice_and_sized_for_each():
    assert localpics.of("local").key == "krea2" and localpics.of("local:qwen21").key == "qwen21"
    assert localpics.of("local:gone").key == "krea2"  # a model that's gone falls back to Krea 2
    assert localpics.engines() == ["local", "local:qwen21"]
    assert localpics.MODELS["krea2"].size("16:9") == (1344, 768)  # Krea keeps its own sizes
    w, h = localpics.MODELS["qwen21"].size("16:9")
    assert w % 32 == 0 and h % 32 == 0 and 1.9e6 < w * h < 2.1e6 and abs(w / h - 16 / 9) < 0.02


def test_qwen_takes_reference_pictures_through_its_text_encoder():
    g = localpics.qwen21_graph("a moth on a window", 1888, 1056, 7, "sv/x", refs=["a.png", "b.png"])
    enc = g["9"]["inputs"]
    assert enc["images.image_1"] == ["r1", 0] and enc["images.image_2"] == ["r2", 0] and enc["vae"] == ["8", 0]
    assert g["r1"] == {"class_type": "LoadImage", "inputs": {"image": "a.png"}}
    plain = localpics.qwen21_graph("a moth", 1408, 1408, 7, "sv/x")
    assert "vae" not in plain["9"]["inputs"] and not any(k.startswith("r") for k in plain)
    assert plain["10"]["inputs"]["cfg"] == 1.0 and plain["15"]["inputs"]["sigmas"].endswith("0.0")  # the person's recipe


def test_the_models_offered_are_the_ones_the_comfyui_has():
    class Comfy:
        def __init__(self, files):
            self.files = files

        async def models(self, folder):
            if folder not in self.files:
                raise RuntimeError("404")  # (a folder name this ComfyUI doesn't list, like "unet")
            return self.files[folder]
    q, k = localpics.MODELS["qwen21"].files, localpics.MODELS["krea2"].files
    both = Comfy({"diffusion_models": [q["diffusion_models"], k["diffusion_models"]],
                  "text_encoders": [q["text_encoders"], k["text_encoders"]], "vae": [q["vae"], k["vae"]]})
    assert asyncio.run(localpics.Available().check(both)) == {"krea2", "qwen21"}
    krea = Comfy({"diffusion_models": [k["diffusion_models"]], "clip": [k["text_encoders"]], "vae": [k["vae"]]})
    assert asyncio.run(localpics.Available().check(krea)) == {"krea2"}  # (its text encoder found under clip/)
    assert asyncio.run(localpics.Available().check(Comfy({}))) == {"krea2"}  # not answering: as last known


def test_choices_list_each_local_model_and_grok_with_whether_they_work():
    w = _writers()
    w.local.keys = {"krea2"}
    st = {"openai": {"connected": False}, "grok": {"connected": True}, "claude": {"connected": True}}
    pics = {c["id"]: c for c in w.image_choices(st)}
    assert pics["local"]["name"] == "Krea 2 on Studio" and pics["local"]["connected"]
    assert pics["local:qwen21"]["name"] == "Qwen Image 2.1 on Studio" and pics["local:qwen21"]["connected"] is False
    assert "reference pictures" in pics["local:qwen21"]["note"]
    assert pics["grok"]["connected"] and pics["openai"]["connected"] is False and pics["openai"]["name"] == "GPT Image 2 (ChatGPT)"
    assert {"grok", "local", "local:qwen21"} <= set(w.image_ids())
    clips = {c["id"]: c for c in w.motion_choices(st)}
    assert clips["grok"]["connected"] and "grok" in w.motion_ids()


def test_the_notes_say_who_makes_the_pictures_and_clips():
    assert music.picture_maker("mcp:abc") is None and music.picture_maker("mitte") is None
    assert "Krea 2 takes no reference pictures" in music.picture_maker("local")[1]
    assert music.picture_maker("local:qwen21")[0] == "Qwen Image 2.1 on this machine's GPU"
    assert "`--ref` keeps" in music.picture_maker("local:qwen21")[1]
    assert "Grok plan" in music.pictures_section("grok", False)
    grok = music.motion_section("grok")
    assert "Grok Imagine" in grok and "1 to 15 whole seconds" in grok and "tools/h3.py" in grok


def _ev(**kw):
    return json.dumps(kw)


def test_grok_may_use_only_the_one_tool_and_what_it_made_must_be_its_own(tmp_path):
    s = Stream("image_gen")
    with pytest.raises(WriterError, match="didn't offer exactly"):
        s.feed(_ev(type="available_commands", tools=["image_gen", "run_terminal_cmd"]))
    s = Stream("image_gen")
    s.feed(_ev(type="available_commands", tools=["image_gen"]))
    with pytest.raises(WriterError, match="tried to use run_terminal_cmd"):
        s.feed(_ev(type="tool_call", toolCallId="c1", title="run_terminal_cmd"))
    with pytest.raises(WriterError, match="didn't allow"):
        s.feed(_ev(type="tool_call_update", toolCallId="c9"))  # a result for a call that never started

    folder = tmp_path / "session"
    (folder / "images").mkdir(parents=True)
    (folder / "images" / "pic.jpg").write_bytes(b"x")
    elsewhere = tmp_path / "elsewhere.jpg"
    elsewhere.write_bytes(b"y")
    s = Stream("image_gen")
    s.feed(_ev(type="available_commands", tools=["image_gen"]))
    s.feed(_ev(type="tool_call", toolCallId="c1", title="image_gen"))
    s.feed(_ev(type="tool_call_update", toolCallId="c1", content=[{"text": json.dumps({"path": str(elsewhere)})}]))
    assert s.made(folder, (".jpg",)) == (folder / "images" / "pic.jpg").resolve()  # not the file outside its folder
    s = Stream("image_gen")
    s.feed(_ev(type="available_commands", tools=["image_gen"]))
    s.feed(_ev(type="text", data="You need SuperGrok for that."))
    with pytest.raises(WriterError, match="SuperGrok"):
        s.made(tmp_path / "empty", (".jpg",))


def test_the_owners_mitte_isnt_offered_twice_and_each_choice_says_exactly_what_it_is(tmp_path):
    from sv.catalog import Catalogs, clean
    w = _writers()
    w.mitte = True
    w.mcp = types.SimpleNamespace(listed=lambda: [{"id": "ia", "name": "ImagineArt", "ok": True, "paid": False}])
    w.catalogs = Catalogs(tmp_path / "cats")
    w.catalogs._put("ia", {"at": 1, **clean({"image": [{"id": "gpt-image-2.5-sunburst", "name": "GPT Image 2.5 Sunburst",
        "note": "", "options": [{"key": "quality", "label": "Quality", "values": ["high", "max"], "default": "high"}]}], "video": []})})
    assert "mitte" not in [c["id"] for c in w.image_choices()] + [c["id"] for c in w.motion_choices()]
    w.set_who("covers", [{"provider": "mitte"}])  # still chosen (from before): listed, so it shows
    assert "mitte" in [c["id"] for c in w.image_choices()]

    w.set_who("covers", [{"provider": "mcp:ia", "model": "gpt-image-2.5-sunburst", "options": {"quality": "max"}}])
    assert w.made_with("covers") == "ImagineArt · GPT Image 2.5 Sunburst, max"
    w.set_who("scenes", [{"provider": "grok", "model": "grok-imagine-image-quality"}])
    assert w.made_with("scenes") == "Grok Imagine Image Quality" and w.grok_model("scenes") == "grok-imagine-image-quality"
    w.set_who("scenes", [{"provider": "grok", "model": "made-up"}])  # only Grok's own models are kept
    assert w.step("scenes") == {"provider": "grok"} and w.made_with("scenes") == "Grok Imagine Image 2.0"  # its default
    w.set_who("motion", [{"provider": "grok"}])
    assert w.made_with("motion") == "Grok Imagine Video 1.5" and w.step("motion") == {"provider": "grok"}  # (Grok stays)
    w.set_who("covers", [{"provider": "local:qwen21"}])
    assert w.made_with("covers") == "Qwen Image 2.1 on Studio"


def test_new_songs_get_covers_as_settings_says_but_never_from_a_paid_source():
    from sv.covers import Covers
    c = Covers.__new__(Covers)
    c.settings = lambda statuses=None: {"auto": "on", "autoPaid": False, "engine": "local:qwen21"}
    assert c.auto_engine() == "local:qwen21"
    c.settings = lambda statuses=None: {"auto": "on", "autoPaid": True, "engine": "mcp:ia"}
    assert c.auto_engine() is None
    c.settings = lambda statuses=None: {"auto": "off", "autoPaid": False, "engine": "local"}
    assert c.auto_engine() is None
