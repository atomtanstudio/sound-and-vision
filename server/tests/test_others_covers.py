import numpy as np
import pytest
from PIL import Image

from sv.covers import compose
from sv.look import palette
from sv.music import others, yue2

LYRICS = "[Verse]\nfirst line goes here\nsecond line goes there\n[Chorus]\nsing it all again now"


def req(**kw):
    base = dict(genres=["synthwave"], moods=["nostalgic"], instruments="analog synths", voice="female", lyrics=LYRICS)
    return yue2.SongRequest(**{**base, **kw})


def test_ace_reads_tags_and_real_controls():
    sent = others.prepare("ace15", req(tempo=108, key="A minor", time_signature="3", language="Spanish"), {})
    p = sent["params"]
    assert p["style"] == "synthwave, nostalgic, analog synths, female vocals"
    assert (p["bpm"], p["key"], p["time_signature"], p["language"]) == (108, "A minor", "3", "es")
    assert p["lyrics"].startswith("[Verse]")


def test_music3_reads_a_caption_and_caps_length():
    sent = others.prepare("music3", req(length="long", tempo=90), {})
    assert sent["params"]["style"].startswith("A nostalgic synthwave song with a female singer.")
    assert sent["params"]["seconds"] <= others.MUSIC3_MAX
    assert sent["params"]["guidance"] == 1.7


def test_instrumental_and_influences_filtered_by_model():
    lib = {"a": {"name": "A", "file": "x", "models": ["ace15"]}, "y": {"name": "Y", "file": "z", "models": ["yue2"]}}
    sent = others.prepare("ace15", req(sung=False, influences=[{"id": "a", "strength": 0.5}, {"id": "y", "strength": 0.5}]), lib)
    assert sent["lyrics"] == "[Instrumental]" and "instrumental" in sent["style"]
    assert [i["id"] for i in sent["influences"]] == ["a"]


def test_needs_a_sound():
    with pytest.raises(yue2.SongError):
        others.prepare("ace15", req(genres=[], moods=[], instruments=""), {})


def test_palette_finds_the_pictures_hues():
    img = np.zeros((96, 96, 3), dtype=np.uint8)
    img[:, :48] = (230, 40, 40)
    img[:, 48:] = (40, 60, 230)
    pal = palette(img)
    assert len(pal) == 2 and all(max(c) == 255 for c in pal)


def test_compose_sets_a_square_sleeve(tmp_path):
    art = tmp_path / "art.png"
    Image.fromarray(np.tile(np.linspace(0, 255, 300, dtype=np.uint8)[:, None, None], (1, 400, 3))).save(art)
    out, small = tmp_path / "cover.jpg", tmp_path / "small.jpg"
    look = compose(art, out, "A Long Title That Wraps Onto Two Lines", "Someone", {}, small)
    assert Image.open(out).size == (3000, 3000) and Image.open(small).size == (640, 640)
    assert look["place"] in ("lower", "upper")
