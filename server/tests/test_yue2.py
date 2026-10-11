import pytest

from sv.music import yue2
from sv.music.yue2 import SongError, SongRequest

LIB = {"sv_dreampop_v1": {"id": "sv_dreampop_v1", "name": "Dream pop", "file": "soundandvision/yue2/sv_dreampop_v1.safetensors",
                          "models": ["yue2"]},
       "ace_only": {"id": "ace_only", "name": "Ace thing", "file": "x.safetensors", "models": ["ace15"]}}
LYRICS = "[Verse 1]\nPaper boats on the river\nCarry every word we kept\n\n\n[Chorus]\nHold on to the afterglow\nLet the night run slow"


def test_style_reads_in_yue2_order():
    r = SongRequest(voice="female", genres=["dream pop"], instruments="shimmering guitars", moods=["wistful"], tempo=96, key="A minor")
    assert yue2.compose_style(r) == "English, female vocal, dream pop, shimmering guitars, wistful, 96 BPM, A minor"


def test_style_needs_a_sound():
    with pytest.raises(SongError, match="sound"):
        yue2.compose_style(SongRequest(lyrics=LYRICS))


def test_style_override_wins():
    assert yue2.compose_style(SongRequest(style_override="  exactly   this ")) == "exactly this"


def test_instrumental_style_and_form():
    r = SongRequest(sung=False, genres=["lo-fi"], length="short")
    p = yue2.prepare(r, LIB)
    assert p["style"].endswith("lo-fi, instrumental, no vocals") and not p["style"].startswith("English")
    assert p["lyrics"] == "[Intro]\n\n[Verse]\n\n[Chorus]\n\n[Outro]"
    assert p["influences"][-1]["id"] == "instrumental"


def test_lyrics_are_tidied_for_yue2():
    assert yue2.tidy_lyrics(LYRICS) == ("[Verse]\nPaper boats on the river\nCarry every word we kept\n\n"
                                        "[Chorus]\nHold on to the afterglow\nLet the night run slow")


def test_sung_needs_words():
    with pytest.raises(SongError, match="needs lyrics"):
        yue2.prepare(SongRequest(genres=["pop"], lyrics="[Verse]\n"), LIB)


def test_influences_are_checked_and_need_a_sketch():
    with pytest.raises(SongError, match="doesn't work with YuE2"):
        yue2.prepare(SongRequest(genres=["pop"], lyrics=LYRICS, influences=[{"id": "ace_only", "strength": .5}]), LIB)
    with pytest.raises(SongError, match="sketch"):
        yue2.prepare(SongRequest(genres=["pop"], lyrics=LYRICS, plan="free",
                                 influences=[{"id": "sv_dreampop_v1", "strength": .5}]), LIB)
    p = yue2.prepare(SongRequest(genres=["pop"], lyrics=LYRICS, influences=[{"id": "sv_dreampop_v1", "strength": .5}]), LIB)
    assert p["influences"] == [{"id": "sv_dreampop_v1", "name": "Dream pop",
                                "file": "soundandvision/yue2/sv_dreampop_v1.safetensors", "strength": .5}]


def test_free_skips_the_sketch_and_engine_settings_pass_through():
    p = yue2.prepare(SongRequest(genres=["pop"], lyrics=LYRICS, plan="free", length="short",
                                 engine={"top_k": 50, "steps": 48}), LIB)
    assert p["sketch"] is None
    assert p["sing"]["seconds"] == 150.0 and p["sing"]["top_k"] == 50 and p["sing"]["steps"] == 48
    assert "guidance" not in p["sing"]


def test_seeds_follow_the_chosen_one():
    assert yue2.seeds(SongRequest(seed=10, takes=3)) == [10, 11, 12]
    assert len(set(yue2.seeds(SongRequest(takes=4)))) == 4


def test_guard_trims_a_sketch_that_runs_past_the_lyrics():
    abc = "X:1\nK:C\n%intro\n|C|\n%verse\n|A|\n%chorus\n|B|\n%verse\n|A|\n%chorus\n|B|\n%outro\n|G|"
    fitted, report = yue2.guard(abc, "[Verse]\na\n\n[Chorus]\nb")
    assert report["kept"] == ["intro", "verse", "chorus", "outro"]
    assert fitted.count("%verse") == 1 and "%outro" in fitted


def test_guard_leaves_a_fitting_sketch_alone():
    assert yue2.guard("X:1\n%verse\n|A|\n%chorus\n|B|", "[Verse]\na\n\n[Chorus]\nb") == (None, {})
