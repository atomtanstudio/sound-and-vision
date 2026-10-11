import io
import types
from pathlib import Path

import numpy as np
from PIL import Image

from sv import brand as brand_mod, library as library_mod, look
from sv.store import Store

FONTS = Path(__file__).resolve().parent / "no-fonts"  # none: the renderer falls back to a system face


def test_a_look_is_kept_in_range_and_defaults_fill_the_gaps():
    l = look.normalize({"title": {"size": 999, "anchor": "nowhere", "case": "shouty", "color": "red", "place": "manual"},
                        "logos": {"app": {"size": -4}, "mine": {"anchor": "tl", "dx": 3}}, "scrim": 7})
    t = l["title"]
    assert t["size"] == 40 and t["anchor"] == "bc" and t["case"] == "upper" and t["color"] == "auto" and t["place"] == "manual"
    assert l["artist"]["place"] == "auto" and l["logos"]["app"]["size"] == 1 and l["logos"]["mine"]["anchor"] == "tl"
    assert l["logos"]["label"] == look.DEFAULT["logos"]["label"] and l["scrim"] == 1
    assert look.normalize(None, {"title": {"font": "Cormorant"}})["title"]["font"] == "Cormorant"


def test_places_are_distances_in_from_the_anchored_edges():
    W, H, s = 1920, 1080, 1080
    assert look.place("bl", 2.5, 2.5, 100, 50, W, H, s) == (27.0, 1080 - 27 - 50)
    assert look.place("br", 2.5, 2.5, 100, 50, W, H, s) == (1920 - 27 - 100, 1080 - 27 - 50)
    assert look.place("tc", 0, 10, 200, 40, W, H, s) == (860.0, 108.0)
    x, y = look.place("mc", 5, -5, 100, 100, W, H, s)  # from the centre: right and up
    assert (x, y) == (960 + 54 - 50, 540 - 54 - 50)
    assert look.place("br", 1.25, 1.25, 189, 59, 1080, 1080, 1080, whole=True) == (1080 - 13 - 189, 1080 - 13 - 59)


def _picture(top_bright: bool) -> Image.Image:
    a = np.zeros((600, 600, 3), np.uint8)
    a[:300 if top_bright else 600] = 40
    if top_bright:
        a[:300] = 235
    else:
        a[300:] = 235
    return Image.fromarray(a)


def test_an_auto_title_goes_where_the_picture_is_calmer():
    for bright_top, place in ((True, "lower"), (False, "upper")):
        layer, info = look.render(_picture(bright_top), "Some Title", "", {}, None, FONTS)
        assert info["place"] == place and layer.size == (600, 600)


def test_a_placed_title_and_a_logo_land_where_the_look_says(tmp_path):
    logo = tmp_path / "l.png"
    Image.new("RGBA", (200, 100), (255, 255, 255, 255)).save(logo)
    l = look.normalize({"title": {"place": "manual", "anchor": "tl", "dx": 5, "dy": 5, "shadow": False},
                        "artist": {"show": False}, "scrim": "none",
                        "logos": {"label": {"show": False}, "app": {"show": False}, "x": {"anchor": "br", "dx": 2, "dy": 2, "size": 10}}})
    pic = Image.new("RGB", (1280, 720), (0, 0, 0))
    lay = look.layout(l, 1280, 720, "Hi", "", FONTS)
    x0, y0 = lay["title"]["box"][:2]
    assert (round(x0), round(y0)) == (36, 36)
    layer, _ = look.render(pic, "Hi", "", {"x": logo}, l, FONTS)
    alpha = np.asarray(layer)[..., 3]
    # the logo: 72 px wide (10% of 720), 14 px in from the bottom-right corner
    assert alpha[720 - 14 - 1, 1280 - 14 - 1] == 255 and alpha[720 - 14 - 1, 1280 - 14 - 72 - 2] < 60  # (its soft shadow)
    assert alpha[:300, :400].max() > 0  # the title, top-left


def test_a_new_logo_is_trimmed_and_given_a_free_corner(tmp_path):
    saved = {}
    store = types.SimpleNamespace(setting=lambda k, d=None: saved.get(k, d), set_setting=lambda k, v: saved.__setitem__(k, v))
    app = types.SimpleNamespace(cfg=types.SimpleNamespace(data=tmp_path), store=store)
    b = brand_mod.Brand(app)
    pic = Image.new("RGBA", (400, 300), (0, 0, 0, 0))
    pic.paste((255, 0, 0, 255), (100, 50, 300, 150))
    buf = io.BytesIO()
    pic.save(buf, "PNG")
    got = b.add_logo("My Label", buf.getvalue())
    mine = next(x for x in got["logos"] if x["name"] == "My Label")
    assert (mine["w"], mine["h"]) == (200, 100)
    assert got["look"]["logos"][mine["id"]]["anchor"] == "tr"  # the first free corner (no other logos here)
    assert b.logos() == {mine["id"]: tmp_path / "branding" / f"{mine['id']}.png"}
    got = b.remove_logo(mine["id"])
    assert not got["logos"] and mine["id"] not in saved["brand"]["look"].get("logos", {})


def test_folders_hold_items_and_letting_one_go_keeps_them(tmp_path):
    saved = {}
    store = types.SimpleNamespace(setting=lambda k, d=None: saved.get(k, d), set_setting=lambda k, v: saved.__setitem__(k, v),
                                  projects=lambda: [], takes=lambda pid: [], trashed_projects=lambda: [])
    lib = library_mod.Library(types.SimpleNamespace(covers=types.SimpleNamespace(house_artist=lambda: ""), cfg=types.SimpleNamespace(projects=tmp_path), store=store))
    f = lib.add_folder("  Pyramid   Song ")["folders"][0]
    assert f["name"] == "Pyramid Song"
    lib.move(["s:p1", "v:p1:music:a"], f["id"])
    assert lib.get()["placed"] == {"s:p1": f["id"], "v:p1:music:a": f["id"]}
    lib.move(["s:p1"], None)
    assert lib.get()["placed"] == {"v:p1:music:a": f["id"]}
    lib.remove_folder(f["id"])
    assert lib.get() == {"folders": [], "placed": {}, "items": [], "trash": 0}


def test_videos_are_listed_with_their_shapes():
    p = {"id": "p1", "title": "T", "cover": {"artist": "A", "small": "covers/c-sm.jpg"},
         "living": {"renders": [{"id": "r1", "file": "living/x.mp4", "shape": "story", "seconds": 60}]},
         "music": {"videos": [{"id": "m1", "file": "music/f/film.mp4", "shape": "wide", "seconds": 30, "opening": True}]}}
    store = types.SimpleNamespace(projects=lambda: [p], takes=lambda pid: [], setting=lambda k, d=None: d)
    items = library_mod.Library(types.SimpleNamespace(covers=types.SimpleNamespace(house_artist=lambda: ""), cfg=types.SimpleNamespace(projects=Path("/x")), store=store)).items()
    by = {i["key"]: i for i in items}
    assert by["s:p1"]["aspect"] == 1.0 and by["s:p1"]["artist"] == "A"
    assert abs(by["v:p1:living:r1"]["aspect"] - 9 / 16) < 1e-9 and by["v:p1:music:m1"]["opening"]
    assert by["v:p1:music:m1"]["thumb"].startswith("/api/library/thumb/p1/music/m1")


def test_a_thumbnail_frame_is_lit_not_a_fade_from_black():
    rng = np.random.default_rng(1)
    black = np.zeros((90, 160, 3), np.float32) + 0.02
    lit = np.clip(rng.random((90, 160, 3)).astype(np.float32) * 0.8 + 0.1, 0, 1)
    assert library_mod.frame_score(lit) > library_mod.frame_score(black)


def test_deleting_puts_songs_and_videos_in_the_trash_and_restore_brings_them_back(tmp_path):
    store = Store(tmp_path / "sv.db")
    lib = library_mod.Library(types.SimpleNamespace(covers=types.SimpleNamespace(house_artist=lambda: ""), cfg=types.SimpleNamespace(projects=tmp_path), store=store))
    a = store.create_project("Ahead", {"music": {"film": None, "videos": [
        {"id": "m2", "file": "music/f/v2.mp4", "shape": "wide", "at": 2}, {"id": "m1", "file": "music/f/v1.mp4", "shape": "wide", "at": 1}]},
        "clips": [{"id": "c1", "file": "clips/c1.mp4", "shape": "story", "presetName": "TikTok", "at": 3}]})
    b = store.create_project("Salt Circle Rite", {})
    keys = {i["key"] for i in lib.items()}
    assert {"v:%s:music:m1" % a["id"], "v:%s:clip:c1" % a["id"], "s:%s" % b["id"]} <= keys

    got = lib.trash([f"v:{a['id']}:music:m1", f"v:{a['id']}:clip:c1", f"s:{b['id']}"])
    assert got == {"trashed": 3, "busy": []}
    keys = {i["key"] for i in lib.items()}
    assert f"v:{a['id']}:music:m2" in keys and f"v:{a['id']}:music:m1" not in keys and f"s:{b['id']}" not in keys
    assert [v["id"] for v in store.project(a["id"])["music"]["videos"]] == ["m2"]  # the song's page no longer has it
    assert store.project(a["id"])["music"]["film"] is None  # the rest of the section untouched
    trash = {i["key"] for i in lib.trashed()}
    assert trash == {f"v:{a['id']}:music:m1", f"v:{a['id']}:clip:c1", f"s:{b['id']}"}

    assert lib.restore(list(trash)) == {"restored": 3}
    assert [v["id"] for v in store.project(a["id"])["music"]["videos"]] == ["m2", "m1"]  # back in order
    assert "trashedAt" not in store.project(a["id"])["clips"][0] and store.project(b["id"]) is not None
    assert lib.trashed() == []


def test_a_song_being_worked_on_stays_out_of_the_trash(tmp_path):
    store = Store(tmp_path / "sv.db")
    lib = library_mod.Library(types.SimpleNamespace(covers=types.SimpleNamespace(house_artist=lambda: ""), cfg=types.SimpleNamespace(projects=tmp_path), store=store))
    p = store.create_project("Busy", {})
    store.jobs = lambda statuses=("queued", "running"), project_id=None: [{"id": "j1"}] if project_id == p["id"] else []
    assert lib.trash([f"s:{p['id']}"]) == {"trashed": 0, "busy": [f"s:{p['id']}"]}
    assert store.project(p["id"]) is not None


def test_a_song_s_artist_is_its_own_then_its_file_s_then_yours():
    from sv.covers import artist_of
    assert artist_of({}, "Rich") == "Rich"  # made here, nothing set: your artist name from Brand
    assert artist_of({"source": {"artist": "Wire"}}, "Rich") == "Wire"  # brought in: the file's
    assert artist_of({"cover": {"artist": "Old"}}, "Rich") == "Old"  # set on its cover before songs had their own
    assert artist_of({"artist": "Coastline", "source": {"artist": "Wire"}}, "Rich") == "Coastline"
    assert artist_of({"artist": ""}, "Rich") == ""  # its own, blank: no artist on it
