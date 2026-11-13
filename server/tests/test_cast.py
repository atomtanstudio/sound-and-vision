"""Cast: the person's own characters, saved once (with their say-so on who's in the pictures) and used in any
lip-synced music video, or the cast of an earlier video used again (sv/cast.py, and its place in sv/video/music.py)."""
import asyncio
import io
import json
import types

import pytest
from PIL import Image

from sv import cast as cast_mod
from sv.jobs import JobError
from sv.video import music


class _Store:
    def __init__(self, projects=()):
        self.settings, self._projects = {}, list(projects)

    def setting(self, key, default=None):
        return self.settings.get(key, default)

    def set_setting(self, key, value):
        self.settings[key] = json.loads(json.dumps(value))

    def projects(self):
        return self._projects


def _app(tmp_path, projects=()):
    cfg = types.SimpleNamespace(data=tmp_path / "data", projects=tmp_path / "data" / "projects")
    return types.SimpleNamespace(cfg=cfg, store=_Store(projects))


def png(size=(600, 800), color="tan", mode="RGB") -> bytes:
    b = io.BytesIO()
    Image.new(mode, size, color).save(b, "PNG")
    return b.getvalue()


@pytest.fixture
def cast(tmp_path):
    return cast_mod.Cast(_app(tmp_path))


def test_nothing_is_kept_without_saying_who_is_in_the_pictures(cast):
    with pytest.raises(JobError, match="Tick the box"):
        cast.add("Mara", "", "invented", False, [png()])
    with pytest.raises(JobError, match="Say who this is"):
        cast.add("Mara", "", "", True, [png()])
    assert cast.list()["members"] == [] and not cast.root.exists()


def test_a_character_is_kept_with_who_it_is_and_when_that_was_confirmed(cast):
    m = cast.add("  Mara  Vale ", "Singer, silver jacket", "me", True, [png(), png(color="navy")])
    assert m["name"] == "Mara Vale" and m["who"] == "me" and m["confirmedAt"] > 0
    assert len(m["pictures"]) == 2 and m["pictures"][0]["url"].startswith(f"/api/cast/{m['id']}/")
    assert "themselves" in m["whoSays"]
    assert cast.list()["members"][0]["id"] == m["id"]


def test_pictures_are_checked_before_any_is_kept(cast):
    with pytest.raises(JobError, match="isn't a picture"):
        cast.add("X", "", "invented", True, [png(), b"not a picture"])
    with pytest.raises(JobError, match="too small"):
        cast.add("X", "", "invented", True, [png((100, 100))])
    with pytest.raises(JobError, match="between 1 and 4"):
        cast.add("X", "", "invented", True, [png()] * 5)
    assert cast.list()["members"] == []


def test_a_transparent_picture_sits_on_plain_grey_and_a_huge_one_is_made_smaller(cast):
    m = cast.add("X", "", "invented", True, [png((4000, 3000), (0, 0, 0, 0), "RGBA")])
    with Image.open(cast.file(m["id"], m["pictures"][0]["name"])) as im:
        assert im.mode == "RGB" and max(im.size) == 2048 and im.getpixel((10, 10)) == cast_mod.BACKDROP


def test_pictures_can_be_added_reordered_and_removed_but_never_all(cast):
    m = cast.add("X", "", "invented", True, [png()])
    first = m["pictures"][0]["name"]
    m = cast.add_pictures(m["id"], [png(color="red"), png(color="blue")])
    with pytest.raises(JobError, match="at most 4"):
        cast.add_pictures(m["id"], [png(), png()])
    second = m["pictures"][1]["name"]
    m = cast.main_picture(m["id"], second)
    assert m["pictures"][0]["name"] == second
    m = cast.remove_picture(m["id"], first)
    assert first not in [p["name"] for p in m["pictures"]] and not (cast.root / m["id"] / first).exists()
    m = cast.remove_picture(m["id"], m["pictures"][1]["name"])
    with pytest.raises(JobError, match="at least one picture"):
        cast.remove_picture(m["id"], m["pictures"][0]["name"])
    assert cast.edit(m["id"], name="Y", about="tall")["about"] == "tall"
    cast.remove(m["id"])
    assert cast.list()["members"] == [] and not (cast.root / m["id"]).exists()


def test_only_its_own_pictures_are_served(cast):
    m = cast.add("X", "", "invented", True, [png()])
    with pytest.raises(JobError):
        cast.file(m["id"], "../../sv.db")
    with pytest.raises(JobError):
        cast.file("../x", m["pictures"][0]["name"])


def _earlier_video(tmp_path, pid="p1", fid="aaaa1111", record=None):
    chars = tmp_path / "data" / "projects" / pid / "music" / fid / "work" / "characters"
    chars.mkdir(parents=True)
    (chars / "REF_singer.png").write_bytes(png())
    (chars / "REF_singer.2.png").write_bytes(png(color="red"))
    (chars / "REF_drummer.png").write_bytes(png(color="blue"))
    (chars / "singer_mitte1.png").write_bytes(png())  # a candidate the director didn't choose: not part of the cast
    (chars.parent / "screenplay.json").write_text(json.dumps({"cast": {"singer": {"name": "the singer", "desc": "silver jacket"}}}))
    if record:
        (chars / "cast.json").write_text(json.dumps(record))
    return chars


def test_an_earlier_video_s_cast_can_be_used_again_or_saved(tmp_path):
    _earlier_video(tmp_path, record={"drummer": {"name": "Rich", "about": "", "who": "me"}})
    c = cast_mod.Cast(_app(tmp_path, [{"id": "p1", "title": "Glory"}]))
    (v,) = c.videos()
    assert v["title"] == "Glory" and v["filmId"] == "aaaa1111"
    by = {x["key"]: x for x in v["cast"]}
    assert set(by) == {"singer", "drummer"}
    assert by["singer"]["name"] == "the singer" and by["singer"]["about"] == "silver jacket"
    assert by["singer"]["pictures"] == 2 and by["singer"]["who"] == "invented"
    assert by["drummer"]["name"] == "Rich" and by["drummer"]["who"] == "me"   # what the earlier video was told
    with pytest.raises(JobError, match="Tick the box"):
        c.from_video("p1", "aaaa1111", "singer", "", None, "invented", False)
    m = c.from_video("p1", "aaaa1111", "singer", "Mara", None, "invented", True)
    assert m["name"] == "Mara" and len(m["pictures"]) == 2 and m["about"] == "silver jacket"
    with pytest.raises(JobError):
        c.from_video("../p1", "aaaa1111", "singer", "", None, "invented", True)


def test_a_video_uses_cast_members_or_an_earlier_video_s_cast_never_both(tmp_path):
    _earlier_video(tmp_path)
    c = cast_mod.Cast(_app(tmp_path, [{"id": "p1", "title": "Glory"}]))
    m = c.add("Mara", "silver jacket", "permission", True, [png(), png()])
    (got,) = c.resolve([m["id"]], None)
    assert got["name"] == "Mara" and got["who"] == "permission" and len(got["files"]) == 2
    assert len(c.resolve(None, {"projectId": "p1", "filmId": "aaaa1111"})) == 2
    with pytest.raises(JobError, match="not both"):
        c.resolve([m["id"]], {"projectId": "p1", "filmId": "aaaa1111"})
    with pytest.raises(JobError, match="isn't in your Cast"):
        c.resolve(["deadbeef"], None)
    assert c.resolve(None, None) == []


def test_the_cast_goes_into_the_video_as_its_references_with_who_each_is(tmp_path, cast):
    a = cast.add("Mara Vale", "silver jacket", "invented", True, [png(), png()])
    b = cast.add("Rich", "", "me", True, [png()])
    chars = tmp_path / "work" / "characters"
    notes = cast_mod.place(cast.resolve([a["id"], b["id"]], None), chars)
    assert (chars / "REF_mara_vale.png").is_file() and (chars / "REF_mara_vale.2.png").is_file() and (chars / "REF_rich.png").is_file()
    record = json.loads((chars / "cast.json").read_text())
    assert record["rich"]["who"] == "me" and record["mara_vale"]["name"] == "Mara Vale"
    assert notes.startswith("## Your cast") and "`characters/REF_mara_vale.png`" in notes and "key `rich`" in notes
    assert "An invented character" in notes and "the person themselves" in notes and "with dignity" in notes
    assert notes.count("with dignity") == 1   # only the real person gets the likeness note


def test_a_video_s_cast_is_found_again_with_who_each_is(tmp_path):
    """The cast copied into one video is the "earlier video" of the next, with its names and who each is."""
    c = cast_mod.Cast(_app(tmp_path, [{"id": "p2", "title": "Glory"}]))
    m = c.add("Rich", "", "me", True, [png()])
    cast_mod.place(c.resolve([m["id"]], None), tmp_path / "data" / "projects" / "p2" / "music" / "bbbb2222" / "work" / "characters")
    (v,) = c.videos()
    assert v["cast"][0]["name"] == "Rich" and v["cast"][0]["who"] == "me"


# ---- in a music video ------------------------------------------------------------------------------------------

def _music(tmp_path, resolve=None):
    m = music.Music.__new__(music.Music)
    m.app = types.SimpleNamespace(cast=types.SimpleNamespace(
        resolve=resolve or (lambda ids, frm: [{"name": "Mara", "about": "", "who": "invented", "files": []}])))
    m.writers = types.SimpleNamespace(picture_by=lambda role: "local", step=lambda role: {"provider": "local"},
                                      motion_by=lambda: "local")
    m._new = lambda pid, request, feel, shape, model, effort, **extra: extra
    return m


def test_a_cast_is_for_the_lip_synced_kinds(tmp_path):
    m = _music(tmp_path)
    with pytest.raises(JobError, match="Performance and Hybrid"):
        m.start("p", kind="surreal", cast=["abcd1234"])
    extra = m.start("p", kind="performance", cast=["abcd1234"])
    assert extra["cast"] == ["abcd1234"] and extra["castNames"] == ["Mara"] and extra["castReal"] is False


def test_the_director_is_told_to_use_the_cast_and_the_rule_is_for_everyone_else(tmp_path):
    m = _music(tmp_path)
    film = {"kind": "hybrid", "opening": True, "cast": ["abcd1234"], "castReal": True}
    parts = m.prompt_parts(film)
    assert any("chose this video's cast" in x and "real people" in x for x in parts)
    assert not any("chose this video's cast" in x for x in m.prompt_parts({"kind": "hybrid", "opening": True}))
    part = m.prompt_parts({**film, "part": {"start": 10.0, "end": 40.0, "label": "chorus"}})
    assert any("chose this video's cast" in x for x in part)
    assert "never a real person" in music.pictures_section("local", True)
    assert "own cast (see Your cast)" in music.pictures_section("local", True, cast=True)


def test_setup_files_the_cast_before_the_pictures_notes_and_says_the_references_are_the_person_s(tmp_path, cast):
    a = cast.add("Mara", "", "invented", True, [png()])
    work = tmp_path / "work"
    work.mkdir()
    (work / "CLAUDE.md").write_text("# Notes\n\nIntro.\n\n## Pictures\n\nMake them.\n")
    (work / "settings.json").write_text(json.dumps({"refs_source": "mitte", "fps": 24}))
    m = _music(tmp_path, resolve=cast.resolve)
    m.film_changed = lambda *a, **k: None
    ctx = types.SimpleNamespace(update=lambda **k: None)
    asyncio.run(m._place_cast(ctx, {"id": "p"}, {"cast": [a["id"]]}, work))
    notes = (work / "CLAUDE.md").read_text()
    assert notes.index("## Your cast") < notes.index("## Pictures") and "Make them." in notes
    assert json.loads((work / "settings.json").read_text()) == {"refs_source": "own", "fps": 24}
    assert (work / "characters" / "REF_mara.png").is_file()
