import asyncio
import json
import types
from pathlib import Path

from PIL import Image

from sv.video import music


def test_the_surreal_request_is_the_person_s_brief():
    text = music.OPENINGS["surreal"].format(title="Pyramid Song", by=" by Radiohead")
    for idea in ("Not a conventional video", "no illustrating the lyrics", "transform into one another", "tangential",
                 "silhouettes", "title screen", "no lyrics on screen", "see Pictures in your notes", "H3", "Go all out"):
        assert idea in text, idea
    assert "first 30 seconds" in music.FIRST.format(seconds=30) and "out/opening.mp4" in music.FIRST
    notes = music.Music.RULES.read_text()
    assert "Never type the song's lyrics" in notes and "## Motion" in notes and "out/opening.mp4" in notes
    assert "tools/h3.py" in music.motion_section("local")


class _Res:
    seconds = 87.0

    def files(self, node, kind):
        return [{"filename": "x.mp4"}]


class _Comfy:
    def __init__(self):
        self.graphs, self.uploads = [], []

    async def upload(self, path, subfolder="sv"):
        self.uploads.append(Image.open(path).size)
        return Path(path).name

    async def run(self, graph, on):
        on({"type": "queued", "prompt_id": "p1"})
        self.graphs.append(graph)
        return _Res()

    async def download(self, ref, dest):
        Path(dest).write_bytes(b"mp4")
        return dest


def _helper_round(tmp_path, req):
    work = tmp_path / "work"
    (work / "shots").mkdir(parents=True)
    Image.new("RGB", (2048, 1152), "navy").save(work / "shots" / "a.png")
    (work / "h3" / "queue").mkdir(parents=True)
    (work / "h3" / "queue" / "r1.json").write_text(json.dumps(req))
    m = music.Music.__new__(music.Music)
    m.film_changed = lambda *a, **k: None

    async def nothing():
        pass
    comfy = _Comfy()
    ctx = types.SimpleNamespace(sched=types.SimpleNamespace(free_gpu=nothing), comfy=comfy, prompt_id=None)

    async def go():
        task = asyncio.create_task(m._h3_loop(ctx, "p", work))
        for _ in range(100):
            if (work / "h3" / "done" / "r1.json").exists():
                break
            await asyncio.sleep(0.02)
        task.cancel()
    asyncio.run(go())
    return json.loads((work / "h3" / "done" / "r1.json").read_text()), comfy, work


def test_h3_requests_render_in_the_folder_at_the_clip_size(tmp_path):
    answer, comfy, work = _helper_round(tmp_path, {"image": "shots/a.png", "prompt": "mist drifts", "out": "clips/a.mp4",
                                                   "seconds": 6, "width": 1344, "height": 768})
    assert answer["ok"] and answer["out"] == "clips/a.mp4" and answer["frames"] == 141
    assert (work / "clips" / "a.mp4").exists() and comfy.uploads == [(1344, 768)]
    inputs = comfy.graphs[0]["7"]["inputs"]
    assert (inputs["width"], inputs["height"], inputs["prompt"]) == (1344, 768, "mist drifts")


def test_h3_requests_cannot_reach_outside_the_folder(tmp_path):
    answer, comfy, _ = _helper_round(tmp_path, {"image": "../../etc/passwd", "prompt": "x", "out": "clips/a.mp4"})
    assert not answer["ok"] and "in this folder" in answer["error"] and not comfy.graphs
    answer, comfy, _ = _helper_round(tmp_path / "b", {"image": "shots/a.png", "prompt": "x", "out": "clips/a.mp4", "width": 1000})
    assert not answer["ok"] and "multiples of 32" in answer["error"]


def test_performance_and_hybrid_go_through_the_video_builder():
    for kind in ("performance", "hybrid"):
        text = music.OPENINGS[kind].format(title="Rapture", by=" by Dub Pistols")
        for idea in ("lip-sync", "never the real artist", "title screen", "no lyrics on screen", "tools/vrgdg.py",
                     "reference/SKILL.md", "Go all out"):
            assert idea in text.replace("lip-syncing", "lip-sync"), (kind, idea)
    m = music.Music.__new__(music.Music)
    assert m.rules({"kind": "hybrid"}).name == "VRGDG.md" and m.rules({"kind": "surreal"}).name == "SURREAL.md"
    assert m.timeout({"kind": "performance"}) == music.SINGING_HOURS * 3600 > m.timeout({"kind": "surreal"})
    assert m.timeout({"kind": "hybrid", "songSeconds": 300}) == 10 * 3600  # a 5-minute song: the floor
    assert m.timeout({"kind": "hybrid", "songSeconds": 420}) == 14 * 3600  # 7 minutes: 2 hours a minute
    for kind in ("performance", "hybrid"):  # the person's note on "Ahead": not the lyrics acted out
        assert "a line about rain is not a rainy street" in music.OPENINGS[kind]
    notes = (music.HERE / "VRGDG.md").read_text()
    assert "Never type the song's lyrics" in notes and "tools/vrgdg.py" in notes and "## Pictures" in notes
    assert "never the real artist" in music.pictures_section("openai", singing=True)


def test_the_pictures_notes_follow_the_person_s_choice():
    tool = music.pictures_section("local", singing=False)
    assert "tools/picture.py" in tool and "Krea 2" in tool and "Mitte" not in tool and "shots/" in tool
    assert "--ref" in music.pictures_section("openai", singing=False)
    mcp = music.pictures_section("mcp:abc", singing=True, server={"name": "My Pics", "paid": True})
    assert "mcp__my_pics__" in mcp and "cost the person money" in mcp and "never the real artist" in mcp
    assert "run_node" in music.pictures_section("mitte", singing=False)  # (only where the owner turned it on)
    m = music.Music.__new__(music.Music)
    m.cfg = types.SimpleNamespace(mitte=False)
    assert m.pictures({"pictures": "mitte"}) == "local" and m.connectors({"pictures": "mitte"}) == []
    m.cfg = types.SimpleNamespace(mitte=True)
    assert m.pictures({}) == "mitte" and m.connectors({}) == ["mcp__claude_ai_Mitte"]
    assert "render_scenes.py" in music.VRGDG_GPU and "assemble.py" in music.VRGDG_SCRIPTS and "remote.sh" not in music.VRGDG_SCRIPTS


def test_a_builder_film_s_pictures_are_served_but_nothing_else_through_its_link(tmp_path):
    projects, films = tmp_path / "projects", tmp_path / "films"
    builder = films / "sv-p1-f1"
    (builder / "logs" / "qa").mkdir(parents=True)
    (builder / "logs" / "qa" / "review_001.jpg").write_bytes(b"jpg")
    (films / "rapture").mkdir()
    (films / "rapture" / "secret.png").write_bytes(b"png")
    (films / "sv-p2-f9").mkdir()
    (films / "sv-p2-f9" / "other.png").write_bytes(b"png")
    work = projects / "p1" / "music" / "f1" / "work"
    work.parent.mkdir(parents=True)
    work.symlink_to(builder, target_is_directory=True)
    (projects / "p1" / "cover.png").write_bytes(b"png")
    (projects / "p1" / "music" / "f1" / "bad").symlink_to(films / "rapture", target_is_directory=True)
    (projects / "p1" / "music" / "f1" / "other").symlink_to(films / "sv-p2-f9", target_is_directory=True)

    def get(pid, path):
        return music.project_file(projects, films, pid, path)
    assert get("p1", "music/f1/work/logs/qa/review_001.jpg") == (builder / "logs" / "qa" / "review_001.jpg").resolve()
    assert get("p1", "cover.png") is not None
    assert get("p1", "music/f1/bad/secret.png") is None          # a link to someone else's Builder film
    assert get("p1", "music/f1/other/other.png") is None         # another song's film
    (projects / "p2").mkdir()
    (projects / "p2" / "cover.png").write_bytes(b"png")
    assert get("p1", "../p2/cover.png") is None                  # climbing out into another song
    assert get("p1", "music/f1/work/../../../../films/rapture/secret.png") is None
    assert get("..", "p1/cover.png") is None
    assert get("p1", "music/f1/work") is None                    # folders aren't files


def test_a_part_of_the_song_is_asked_for_by_its_times_without_a_title_screen():
    m = music.Music.__new__(music.Music)
    m._ready = lambda pid: ({"id": pid}, {"duration": 219.28})
    m._new = lambda pid, request, feel, shape, model, effort, **extra: extra
    m.writers = types.SimpleNamespace(picture_by=lambda role: "local", step=lambda role: {"provider": "local"})
    got = m.start("p1", kind="performance", opening=False, part={"start": 179.202, "end": 209.85, "label": "the final chorus"})
    assert got["opening"] and got["part"] == {"start": 179.202, "end": 209.85, "label": "the final chorus"}
    assert got["pictures"] == "local" and m.connectors(got) == []  # pictures from the app: no picture connector
    text = m.prompt_parts(got)[0]
    assert "from 2:59.2 to 3:29.8 (the final chorus), 30.6 seconds" in text and "skip the title screen" in text
    assert "out/opening.mp4" in text and "song/song.m4a from 2:59.2" in text
    for bad in ({"start": 200, "end": 230}, {"start": 10, "end": 12}, {"start": 50, "end": 40}):
        try:
            m.start("p1", kind="performance", part=bad)
            raise AssertionError(bad)
        except music.JobError:
            pass
    assert m.prompt_parts({"opening": True})[0].startswith("Plan the whole video")  # the first 30 seconds, as before


def test_the_motion_notes_follow_the_person_s_choice():
    assert "tools/h3.py" in music.motion_section("local") and "Mitte" not in music.motion_section("local")
    hosted = music.motion_section("mitte")
    assert '"slug"' not in hosted and "h3-max" in hosted and "frame_mode" in hosted and "costs the person money" in hosted
    mcp = music.motion_section("mcp:x", {"name": "Clips", "paid": True})
    assert "mcp__clips__" in mcp and "turns a still into video" in mcp and "may cost the person money" in mcp
    m = music.Music.__new__(music.Music)
    m.cfg = types.SimpleNamespace(mitte=True)
    film = {"pictures": "local", "motion": "mitte"}
    assert m.motion(film) == "mitte" and m.connectors(film) == ["mcp__claude_ai_Mitte"]
    m.cfg = types.SimpleNamespace(mitte=False)
    assert m.motion(film) == "local" and m.connectors(film) == []


def test_answers_to_the_session_are_never_written_through_a_link(tmp_path):
    work = tmp_path / "work"
    (work / "h3").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    music.reply(work, work / "h3" / "done", "a.json", {"ok": True})
    assert json.loads((work / "h3" / "done" / "a.json").read_text()) == {"ok": True}
    (work / "pictures").mkdir()
    (work / "pictures" / "done").symlink_to(outside)  # Claude replaced the folder with a link
    music.reply(work, work / "pictures" / "done", "b.json", {"ok": True})
    assert not (outside / "b.json").exists()
