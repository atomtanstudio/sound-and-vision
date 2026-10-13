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


def test_every_kind_of_music_video_is_told_about_joins():
    assert "## Joins" in music.JOINS and "out/joins.json" in music.JOINS and "tools/joins.py smooth" in music.JOINS
    assert "up to 15 seconds is one clip" in music.JOINS and "tools/joins.py check" in music.JOINS
    assert "pieces that each start on the last frame" not in music.H3_MOTION  # the recipe that made the seams
    builder = music.with_joins((Path(music.__file__).parent / "VRGDG.md").read_text())
    assert builder.index("## Joins") < builder.index("## Hand back") and builder.count("## Joins") == 1
    assert music.with_joins(music.with_joins(builder)) == builder  # kept up to date in place, never twice


def test_a_note_brings_an_earlier_video_s_notes_and_tools_up_to_date(tmp_path):
    work = tmp_path / "work"; work.mkdir()
    (work / "CLAUDE.md").write_text("# This folder\n\n## Pictures\n\npics\n\n## Motion: MiniMax H3 (`tools/h3.py`)\n\n"
                                    "A longer shot can be pieces that each start on the last frame of the one before.\n"
                                    "\n## Hand back\n\n- out/final.mp4\n")
    m = music.Music.__new__(music.Music)
    m.cfg = types.SimpleNamespace(mitte=False)
    m.writers = types.SimpleNamespace(mcp=types.SimpleNamespace(get=lambda sid: None), catalogs=None)
    asyncio.run(m.refresh(None, {"id": "p"}, {"kind": "surreal", "motion": "local"}, work))
    notes = (work / "CLAUDE.md").read_text()
    assert "## Joins" in notes and "pieces that each start" not in notes
    assert notes.index("## Pictures") < notes.index("## Motion") < notes.index("## Joins") < notes.index("## Hand back")
    # notes from before Joins had its own section (the way "Tears" got them): one Joins section after a refresh
    (work / "CLAUDE.md").write_text(notes.replace("\n## Joins", "\n### Joins").replace("## Hand back", "## Hand back", 1))
    asyncio.run(m.refresh(None, {"id": "p"}, {"kind": "surreal", "motion": "local"}, work))
    again = (work / "CLAUDE.md").read_text()
    assert again.count("## Joins") == 1 and "### Joins" not in again and again.count("## Hand back") == 1
    assert notes.count("## Hand back") == 1 and "pics" in notes
    for tool in ("h3.py", "picture.py", "joins.py"):
        assert (work / "tools" / tool).exists(), tool
    assert "def smooth" in (work / "tools" / "joins.py").read_text()


def test_the_joins_tool_says_how_to_use_it():
    import ast
    src = (Path(music.__file__).parent / "jointool.py").read_text()
    doc = ast.get_docstring(ast.parse(src))
    for idea in ("tools/joins.py check", "tools/joins.py smooth", "CLIP:FIRST:COUNT", ":rev", "exactly COUNT frames",
                 "the camera turns"):
        assert idea in doc, idea


def test_a_whole_move_can_be_one_fifteen_second_take(tmp_path):
    answer, comfy, _ = _helper_round(tmp_path, {"image": "shots/a.png", "prompt": "one long move", "out": "clips/a.mp4",
                                                "seconds": 15, "width": 1344, "height": 768})
    assert answer["ok"] and answer["frames"] == 362
    answer, _, _ = _helper_round(tmp_path / "b", {"image": "shots/a.png", "prompt": "x", "out": "clips/a.mp4", "seconds": 16})
    assert not answer["ok"] and "1 to 15" in answer["error"]



def _checker(tmp_path, report, listed=True):
    work = tmp_path / "work"; (work / "out").mkdir(parents=True)
    video = work / "out" / "final.mp4"; video.write_bytes(b"x")
    if listed:
        (work / "out" / "joins.json").write_text(json.dumps({"joins": [12.5, 36.9]}))
    m = music.Music.__new__(music.Music)
    m.cfg = types.SimpleNamespace()
    said = {}
    m.film_changed = lambda pid, **kw: said.update(kw)
    async def studio(cfg, *args, timeout=0):
        assert args[0] == "exec" and "tools/joins.py check out/final.mp4 --joins out/joins.json --json" in args[-1]
        (work / "out" / "tmp" / "joins-check.json").write_text(json.dumps(report))
    music.folder.studio, old = studio, music.folder.studio
    try:
        note = asyncio.run(m.verify(types.SimpleNamespace(update=lambda **kw: None), {"id": "p"}, {}, work, video))
    finally:
        music.folder.studio = old
    return note, said


def test_the_app_checks_the_joins_handed_back_and_says_what_to_fix(tmp_path):
    ok = {"joins": [{"at": 12.5, "ok": True}, {"at": 36.9, "ok": True}], "failed": 0}
    note, said = _checker(tmp_path, ok)
    assert note is None and said["joinsCheck"]["checked"] == 2 and said["joinsCheck"]["failed"] == []
    bad = {"joins": [{"at": 12.5, "ok": True}, {"at": 36.9, "ok": False, "why": "frames are skipped: the picture jumps"}]}
    note, said = _checker(tmp_path / "b", bad)
    assert "1 of the 2 listed don't pass" in note and "0:36.9" in note and "frames are skipped" in note
    assert said["joinsCheck"]["failed"] == [{"at": 36.9, "why": "frames are skipped: the picture jumps"}]
    note, _ = _checker(tmp_path / "c", ok, listed=False)
    assert note == music.NO_JOINS_LIST and "out/joins.json" in note


def test_the_director_is_sent_back_at_most_twice(tmp_path):
    from sv.video.kinetic import Kinetic
    film = {"id": "f1", "fixRounds": 0}
    sent = []
    k = Kinetic.__new__(Kinetic)
    k.JOB = "music.film"
    k.app = types.SimpleNamespace(store=types.SimpleNamespace(project=lambda pid: {"id": pid}),
                                  sched=types.SimpleNamespace(submit=lambda kind, job, pid: sent.append(job) or {"id": f"j{len(sent)}"}))
    k.get = lambda p: {"film": film}
    k.film_changed = lambda pid, **kw: film.update(kw)
    async def verify(ctx, p, f, work, video):
        return "fix the join at 0:36.9"
    k.verify = verify
    results = [asyncio.run(k._send_back(None, {"id": "p"}, film, tmp_path, tmp_path / "v.mp4")) for _ in range(3)]
    assert results == [True, True, False] and len(sent) == 2 and film["fixRounds"] == 2
    assert sent[0]["stage"] == "note" and sent[0]["app"] and sent[0]["text"] == "fix the join at 0:36.9"
