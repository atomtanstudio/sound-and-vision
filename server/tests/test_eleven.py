import asyncio
import types

import pytest

from sv.jobs import JobError
from sv.music import eleven
from sv.music.yue2 import SongError, SongRequest

SCHEMA = {"required": ["prompt"], "properties": {
    "prompt": {"type": "string"}, "composition_plan": {"type": ["object", "null"]},
    "force_instrumental": {"type": "boolean", "default": True},
    "music_length_min": {"type": "number", "default": 1, "minimum": 0.1, "maximum": 10},
    "output_format": {"type": "string", "enum": ["mp3_44100_64", "mp3_44100_128", "mp3_44100_192"], "default": "mp3_44100_128",
                      "description": "Output audio format and quality"},
    "respect_sections_durations": {"type": "boolean", "default": True, "description": "Keep each section to its length"}}}
LYRICS = "[Verse]\nSalt on my wrist and a sparkler's tail\nSomebody's speaker hums a half-step high\n\n[Chorus]\nLift your hands\nLet the coastline sing\n\n[Outro]\n"


def _song(**kw):
    return SongRequest(genres=["synth-pop"], moods=["warm"], instruments="analog synths", voice="female", lyrics=LYRICS,
                       tempo=124, **kw)


def test_the_nodes_own_settings_are_offered_and_the_ones_the_song_fills_are_not():
    got = {f["key"]: f for f in eleven.fields(SCHEMA)}
    assert set(got) == {"output_format", "respect_sections_durations"}
    assert got["output_format"]["type"] == "choice" and got["output_format"]["default"] == "mp3_44100_128"
    assert got["output_format"]["label"] == "Audio quality" and got["output_format"]["labels"]["mp3_44100_128"] == "MP3 · 128 kbps"
    assert got["respect_sections_durations"]["type"] == "switch"
    assert got["respect_sections_durations"]["label"] == "Keep each section to its length"


def test_a_sung_song_becomes_a_plan_of_sections_scaled_to_its_length():
    p = eleven.plan(eleven.tidy_lyrics(LYRICS), ["synth-pop"], 60)
    names = [s["section_name"] for s in p["sections"]]
    assert names[:2] == ["Verse", "Chorus"] and p["sections"][0]["lines"][0].startswith("Salt on my wrist")
    assert all(3000 <= s["duration_ms"] <= 120000 for s in p["sections"])
    assert abs(sum(s["duration_ms"] for s in p["sections"]) - 60000) < 1500  # (rounded to 0.1 s each)
    long = eleven.plan("[Verse]\n" + "\n".join(f"line {i} " + "word " * 60 for i in range(40)), [], 600)
    assert len(long["sections"][0]["lines"]) == 30 and all(len(l) <= 200 for l in long["sections"][0]["lines"])
    assert long["sections"][0]["duration_ms"] == 120000  # (no section longer than ElevenLabs allows)
    with pytest.raises(SongError):
        eleven.plan("", [], 60)


def test_what_a_take_sends():
    known = eleven.fields(SCHEMA)
    sent = eleven.prepare(_song(length="short"), "abc", {"output_format": "mp3_44100_192", "respect_sections_durations": False,
                                                          "made_up": 1, "force_instrumental": True}, known)
    inp = sent["input"]
    assert sent["model"] == "eleven" and sent["server"] == "abc" and inp["force_instrumental"] is False
    assert inp["output_format"] == "mp3_44100_192" and inp["respect_sections_durations"] is False and "made_up" not in inp
    assert "synth-pop" in inp["composition_plan"]["positive_global_styles"] and "124 BPM" in sent["style"]
    assert inp["prompt"] == ""  # (a prompt or a plan, never both; Mitte still wants the field)
    assert sum(s["duration_ms"] for s in inp["composition_plan"]["sections"]) == pytest.approx(150000, abs=1500)
    inst = eleven.prepare(SongRequest(genres=["ambient"], sung=False, length="short"), "abc", {"output_format": "wav"}, known)
    assert inst["input"]["force_instrumental"] is True and inst["input"]["music_length_min"] == 2.5
    assert "composition_plan" not in inst["input"] and "output_format" not in inst["input"]  # (not one of its values)
    with pytest.raises(SongError):
        eleven.prepare(SongRequest(genres=["pop"], lyrics="la"), "abc", {}, known)
    assert eleven.server_of("mcp:a9885ed1ad:music") == "a9885ed1ad" and eleven.server_of("music3") is None


def test_a_run_is_followed_to_its_audio(monkeypatch):
    calls = []
    answers = {"run_node": {"result": {"data": {"id": "task-1", "status": "pending"}}},
               "get_task": [{"result": {"data": {"status": "pending"}}}, {"result": {"data": {"node_run_id": "run-9"}}}],
               "get_node_run": [{"result": {"data": {"status": "in_progress"}}},
                                {"links": [{"data": {"src": "https://cdn.example/a.mp3", "content_type": "audio/mpeg"}}],
                                 "result": {"data": {"status": "done", "output": {"result": {"assets": [
                                     {"url": "https://fal.example/a.mp3", "content_type": "audio/mpeg"}]}}}}}]}

    async def fake_call(mcp, sid, tool, args, timeout=60):
        calls.append((tool, args))
        a = answers[tool]
        return a.pop(0) if isinstance(a, list) else a
    monkeypatch.setattr(eleven, "_call", fake_call)
    monkeypatch.setattr(eleven, "FOLLOW_EVERY", 0)
    url, kind = asyncio.run(eleven.make(None, "abc", {"prompt": "x"}))
    assert url == "https://fal.example/a.mp3" and kind == "audio/mpeg"
    assert calls[0] == ("run_node", {"slug": "music", "input": {"prompt": "x"}}) and calls[1] == ("get_task", {"task_id": "task-1"})
    assert ("get_node_run", {"id": "run-9"}) in calls

    answers["run_node"] = {"result": {"data": {"id": "task-2"}}}
    answers["get_task"] = [{"result": {"data": {"status": "error", "error": "Not enough credits"}}}]
    with pytest.raises(JobError, match="Not enough credits"):
        asyncio.run(eleven.make(None, "abc", {"prompt": "x"}))


def test_only_a_server_that_runs_elevenlabs_music_offers_it(monkeypatch):
    async def fake_call(mcp, sid, tool, args, timeout=60):
        if sid == "mitte":
            return {"result": {"data": {"name": "Music", "desc": "Generate music with ElevenLabs Music model.", "is_paid_only": True,
                                        "input_schema": SCHEMA}}}
        return {"result": {"data": {"name": "Music", "desc": "Some other music model"}}}
    monkeypatch.setattr(eleven, "_call", fake_call)
    eleven._offers.clear()
    tools = [{"name": n} for n in ("search_nodes", "get_node", "run_node", "get_task", "get_node_run")]
    mcp = types.SimpleNamespace(listed=lambda: [
        {"id": "mitte", "name": "Mitte", "ok": True, "paid": False, "tools": tools},
        {"id": "other", "name": "Other", "ok": True, "paid": True, "tools": tools},
        {"id": "ia", "name": "ImagineArt", "ok": True, "tools": [{"name": "generate_music"}]},
        {"id": "off", "name": "Off", "ok": False, "tools": tools}])
    got = asyncio.run(eleven.offered(mcp))
    assert [m["id"] for m in got] == ["mcp:mitte:music"]
    assert got[0]["name"] == "ElevenLabs Music" and got[0]["via"] == "Mitte" and got[0]["paidOnly"]
    assert {f["key"] for f in got[0]["fields"]} == {"output_format", "respect_sections_durations"}


def test_influences_a_model_cant_load_are_described_in_its_style():
    from sv.influences import in_words, sort_out
    from sv.music import others
    lib = {"glitch": {"id": "glitch", "name": "Glitchcore", "file": "soundandvision/yue2/glitchcore.safetensors", "models": ["yue2"],
                      "about": "Turns a song into a dark, stuttering electro-industrial track with chopped pitched vocals, distorted bass."},
           "dream": {"id": "dream", "name": "Dream pop", "file": "soundandvision/yue2/sv_dreampop_v1.safetensors", "models": ["yue2"],
                     "about": "Hazy, shimmering, reverb-washed guitars and soft vocals. Trained on your dream pop set. 0."}}
    assert in_words(lib["glitch"]) == ("Glitchcore: a dark, stuttering electro-industrial track with chopped pitched vocals, "
                                       "distorted bass")
    assert in_words(lib["dream"]) == "Dream pop: Hazy, shimmering, reverb-washed guitars and soft vocals"
    picks = [{"id": "glitch", "strength": 0.7}, {"id": "dream", "strength": 0.5}, {"id": "gone", "strength": 1}]
    r = _song(influences=picks)
    assert sort_out(r.influences, lib, "yue2")[1] == [] and len(sort_out(r.influences, lib, "yue2")[0]) == 2
    sent = eleven.prepare(r, "abc", {}, [], lib)
    assert in_words(lib["glitch"]) in sent["input"]["composition_plan"]["positive_global_styles"]
    ace = others.prepare("ace15", r, lib)
    assert ace["influences"] == [] and "Glitchcore: a dark" in ace["style"]
    m3 = others.prepare("music3", r, lib)
    assert "In the spirit of Glitchcore: a dark" in m3["style"] and "Dream pop: Hazy" in m3["style"]
