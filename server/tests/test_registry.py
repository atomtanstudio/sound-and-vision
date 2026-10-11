import os
from pathlib import Path

import pytest

from sv.comfy.client import Comfy
from sv.comfy.registry import BindError, Influence, Registry

REG = Registry()
LIVE = os.environ.get("SV_COMFY")  # e.g. http://127.0.0.1:8210; live tests skip without it


def test_all_four_song_workflows_load():
    assert {"song.yue2", "song.ace15", "song.ace15.replace", "song.music3"} <= set(REG.workflows)


def test_bind_fills_every_target():
    g = REG["song.yue2"].bind({"style": "dream pop", "lyrics": "[Verse]\nla", "seed": 7, "seconds": 60})
    assert g["abc"]["inputs"]["style"] == g["music"]["inputs"]["style"] == "dream pop"
    assert g["abc"]["inputs"]["seed"] == g["music"]["inputs"]["seed"] == g["sample"]["inputs"]["seed"] == 7
    assert g["music"]["inputs"]["max_duration"] == 60.0 and isinstance(g["music"]["inputs"]["max_duration"], float)


def test_bind_leaves_the_template_alone():
    REG["song.ace15"].bind({"style": "x", "seed": 1})
    assert REG["song.ace15"].graph["enc"]["inputs"]["tags"] == ""


@pytest.mark.parametrize("values, msg", [
    ({"lyrics": "x"}, "needs 'style'"),
    ({"style": "x", "lyrics": "y", "seed": "7"}, "should be int"),
    ({"style": "x", "lyrics": "y", "seconds": 2000}, "between"),
    ({"style": "x", "lyrics": "y", "plan": "off"}, "one of"),
    ({"style": "x", "tempo": 120}, "doesn't take tempo"),
])
def test_bind_says_what_is_wrong(values, msg):
    with pytest.raises(BindError, match=msg):
        REG["song.yue2"].bind(values)


def test_influences_chain_after_the_loader_and_rewire_everything():
    g = REG["song.yue2"].bind({"style": "x", "lyrics": "y"}, influences=[
        Influence("soundandvision/yue2/sv_dreampop_v1.safetensors", 0.6),
        Influence("soundandvision/yue2/ar_lora_inst_v3abc_comfyui.safetensors", 1.0)])
    a, b = g["sv_influence_0"], g["sv_influence_1"]
    assert a["inputs"]["model"] == ["ckpt", 0] and a["inputs"]["clip"] == ["ckpt", 1]
    assert b["inputs"]["model"] == ["sv_influence_0", 0]
    assert g["sample"]["inputs"]["model"] == ["sv_influence_1", 0]
    assert g["abc"]["inputs"]["clip"] == g["music"]["inputs"]["clip"] == ["sv_influence_1", 1]
    assert g["decode"]["inputs"]["vae"] == ["ckpt", 2]  # the VAE is not a LoRA target


def test_prefix_names_the_output():
    g = REG["song.ace15"].bind({"style": "x"}, prefix="sv/p1/take-3")
    assert g["save"]["inputs"]["filename_prefix"] == "sv/p1/take-3"


@pytest.mark.skipif(not LIVE, reason="set SV_COMFY to run against sv-comfy")
async def test_live_instance_has_everything_every_workflow_needs():
    c = Comfy(LIVE)
    try:
        report = REG.check(await c.object_info())
    finally:
        await c.close()
    assert report == {w: [] for w in REG.workflows}, report


@pytest.mark.skipif(not LIVE, reason="set SV_COMFY to run against sv-comfy")
async def test_live_ace15_makes_a_short_song(tmp_path: Path):
    c = Comfy(LIVE)
    events = []
    try:
        g = REG["song.ace15"].bind({"style": "lo-fi piano, warm, 80 BPM", "seconds": 10.0, "seed": 11, "bpm": 80},
                                   prefix="sv/test/ace15")
        res = await c.run(g, events.append)
        files = res.files("save")
        assert files, res.outputs
        out = await c.download(files[0], tmp_path / "a.flac")
        assert out.stat().st_size > 50_000
    finally:
        await c.close()
    kinds = {e["type"] for e in events}
    assert {"queued", "done"} <= kinds
    assert "progress" in kinds or "cached" in kinds
