import asyncio
from pathlib import Path

import pytest

from sv.influence_engine import Folder, Share, file_title, guess_song, library, lrc_words, match_song, norm
from sv.jobs import JobError
from sv.writers import tasks


def test_norm_matches_library_and_catalogue_titles():
    assert norm("Space Song") == norm("space song")
    assert norm("Kim & Jessie") == norm("Kim and Jessie")
    assert norm("Midnight City - 2011 Remaster") == norm("Midnight City")
    assert norm("Wait (feat. Someone)") == norm("Wait")
    assert norm("The Cure") == norm("Cure")
    assert norm("Beyoncé") == norm("Beyonce")


def test_file_title():
    assert file_title("03 - Skin Of The Night.m4a", "M83") == "Skin Of The Night"
    assert file_title("M83 - Wait.flac", "M83") == "Wait"
    assert file_title("1-03 Title.mp3", "X") == "Title"


def test_smbclient_listing():
    text = """  .                                   D        0  Fri May  1 08:06:58 2026
  ..                                 DA        0  Thu Oct  8 21:36:50 2026
  Saturdays = Youth                   D        0  Fri May  1 10:04:30 2026

\\Music\\Library\\M83\\Saturdays = Youth
  .                                   D        0  Fri May  1 10:04:30 2026
  01 - You Appearing.m4a              N  7451293  Fri May  1 10:04:27 2026
  Cover.jpg                           N   619176  Fri May  1 10:04:24 2026
"""
    rows = list(Share._entries(text))
    assert (None, "Saturdays = Youth", True) in rows
    assert ("\\Music\\Library\\M83\\Saturdays = Youth", "01 - You Appearing.m4a", False) in rows


def test_research_answer_is_tidied():
    out = tasks.read("research", {
        "name": "Synthwave", "kind": "Genre", "trigger": "Synth Wave!", "about": "x", "how_many": "y", "style": "z",
        "voice": "male", "artists": [{"name": "Kavinsky", "why": "w", "songs": ["Nightcall", ""]}, {"name": "", "songs": ["a"]}],
        "preview_lyrics": [{"kind": "verse", "lines": ["one", "two"]}, {"kind": "chorus", "lines": []}]})
    assert out["trigger"] == "synth_wave"
    assert out["artists"] == [{"name": "Kavinsky", "why": "w", "songs": ["Nightcall"]}]
    assert out["previewLyrics"] == [{"kind": "verse", "lines": ["one", "two"]}]
    assert tasks.system("research") != tasks.SYSTEM


def test_lrc_words():
    lrc = "[ar:Someone]\n[ti:Something]\n[length: 03:20]\n[00:12.30]one two three four\n[00:15.10]five six seven eight\n\n[00:18.00]<00:18.00>nine ten eleven twelve\n"
    assert lrc_words(lrc) == "one two three four\nfive six seven eight\nnine ten eleven twelve"
    assert lrc_words("[00:01.00]too short") == ""


def test_your_music_is_a_folder_or_a_share():
    assert library("") is None
    share = library("smb://nas.local/storage/Music/Library")
    assert isinstance(share, Share) and (share.share, share.root) == ("//nas.local/storage", "Music/Library")
    assert isinstance(library("/mnt/music"), Folder)


def test_a_music_folder_finds_an_artist_s_songs_and_nothing_outside_it(tmp_path):
    album = tmp_path / "music" / "M83" / "Hurry Up"
    album.mkdir(parents=True)
    (album / "01 - Midnight City.flac").write_bytes(b"x" * 20)
    (album / "cover.jpg").write_bytes(b"x")
    (tmp_path / "secret.flac").write_bytes(b"x")
    lib = Folder(tmp_path / "music")
    songs = asyncio.run(lib.songs_of("m83"))
    assert songs == [{"title": "Midnight City", "path": "M83/Hurry Up/01 - Midnight City.flac"}]
    asyncio.run(lib.fetch(songs[0]["path"], tmp_path / "copy.flac"))
    assert (tmp_path / "copy.flac").read_bytes() == b"x" * 20
    with pytest.raises(JobError):
        asyncio.run(lib.fetch("../secret.flac", tmp_path / "nope.flac"))


def test_added_audio_is_matched_to_the_list():
    songs = [{"id": "a", "artist": "M83", "title": "Midnight City"}, {"id": "b", "artist": "Kavinsky", "title": "Nightcall"}]
    assert match_song(songs, *guess_song("03 - Nightcall.mp3", {})) == songs[1]
    assert match_song(songs, *guess_song("M83 - Midnight City (2011 Remaster).flac", {})) == songs[0]
    assert match_song(songs, *guess_song("track1.m4a", {"artist": "M83", "title": "Midnight City"})) == songs[0]
    assert match_song(songs, *guess_song("Someone Else - Nightcall.mp3", {})) is None


def test_share_names_that_smbclient_would_run_are_never_put_in_a_command():
    from sv.influence_engine import UNSAFE_SMB
    for bad in ('Artist"; !touch x; "', "a;b", 'a"b', "a\nb"):
        assert UNSAFE_SMB.search(bad)
    assert not UNSAFE_SMB.search("Panic! at the Disco")
    assert not UNSAFE_SMB.search("M83/Hurry Up, We're Dreaming (2011)/01 - Intro.flac".replace("/", ""))
    share = Share("//nas/storage", "Music")
    with pytest.raises(JobError):
        asyncio.run(share.fetch('Music/Bad";!cmd/x.flac', Path("/tmp/x")))


# ---- a song finder (an add-on's) ---------------------------------------------------------------------------

import copy
import types


class _Store:
    def __init__(self, run):
        self.runs = {run["id"]: copy.deepcopy(run)}

    def run(self, rid):
        return copy.deepcopy(self.runs.get(rid))

    def update_run(self, rid, status=None, **fields):
        r = self.runs[rid]
        if status:
            r["status"] = status
        r.update(copy.deepcopy(fields))
        return copy.deepcopy(r)


class _Ctx:
    def __init__(self, store, rid):
        self.job, self.store, self.said, self.queued = {"runId": rid}, store, [], []
        self.sched = types.SimpleNamespace(submit=lambda kind, payload: self.queued.append(kind) or {"id": "j2"})

    def update(self, stage=None, message=None, progress=None):
        self.said.append(message)


class _Finder:
    name = "Tape Deck"

    def __init__(self, has, fails=(), others=()):
        self.has, self.fails, self.asked, self.others = has, set(fails), None, list(others)

    async def instead(self, artist, have, count):
        return [{"title": t, "seconds": 210} for t in self.others if t not in have][:count]

    async def look(self, songs):
        self.asked = songs
        return {s["id"]: {"title": s["title"].upper(), "seconds": 200} for s in songs if s["title"] in self.has}

    async def get(self, songs, music, tell):
        for s in songs:
            tell(s["id"], state="downloading")
            if s["title"] in self.fails:
                tell(s["id"], state="failed", note="It wasn't there")
                continue
            f = music.root / s["artist"] / f"{s['title']}.flac"
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(b"x" * 20)
            tell(s["id"], path=f"{s['artist']}/{s['title']}.flac")
        tell(message="All done", progress=1)


def _engine(tmp_path, run):
    from sv.influence_engine import Engine
    (tmp_path / "music").mkdir(exist_ok=True)
    cfg = types.SimpleNamespace(music=str(tmp_path / "music"), trainer_root=tmp_path / "trainer", data=tmp_path / "data",
                                ffmpeg="ffmpeg", lrclib="")
    store = _Store(run)
    app = types.SimpleNamespace(cfg=cfg, store=store, hub=types.SimpleNamespace(publish=lambda *a: None))
    return Engine(app, None), store


def test_the_song_finder_looks_for_what_isnt_in_your_music_and_spares_fill_in(tmp_path):
    artists = [{"name": f"Artist {i}", "why": "", "songs": ["A", "B", "C", "D"]} for i in range(12)]  # 3 used, 1 spare each
    plan = {"name": "Tape", "kind": "Style", "trigger": "tape", "about": "", "howMany": "", "style": "", "voice": "",
            "previewLyrics": "", "artists": artists}
    eng, store = _engine(tmp_path, {"id": "run1", "status": "researching", "ask": {"text": "tape"}, "songs": []})
    (tmp_path / "music" / "Artist 0").mkdir()
    (tmp_path / "music" / "Artist 0" / "01 - A.flac").write_bytes(b"x" * 20)

    async def write(task, data):
        return {"result": plan, "by": {"kind": "test"}}
    eng.writers = types.SimpleNamespace(write=write)
    eng.finder = _Finder(has={"C", "D"})
    asyncio.run(eng.research(_Ctx(store, "run1")))
    run = store.run("run1")
    a0 = {s["title"]: s for s in run["songs"] if s["artist"] == "Artist 0"}
    assert a0["A"]["source"] == "library" and a0["A"]["id"] not in {s["id"] for s in eng.finder.asked}
    assert a0["C"]["source"] == "finder" and a0["C"]["found"]["seconds"] == 200 and a0["C"]["seconds"] == 200
    assert a0["B"]["source"] == "needed" and not a0["B"]["use"] and a0["D"]["use"]  # the spare took its place
    assert run["finder"] == "Tape Deck" and run["finderNote"] is None and run["status"] == "planned"


def test_the_song_finder_gets_its_songs_into_your_music_before_they_are_gathered(tmp_path, monkeypatch):
    from sv.influence_engine import Engine
    songs = [{"id": f"track-{i:03d}", "artist": "Band", "title": f"Song {i}", "source": "finder", "use": True,
              "state": "waiting"} for i in range(9)]
    run = {"id": "run2", "status": "planned", "folder": "training/x", "finder": "Tape Deck", "songs": songs}
    eng, store = _engine(tmp_path, run)
    eng.finder = _Finder(has=set(), fails={"Song 4"})

    async def to_flac(self, src, dest):
        dest.write_bytes(src.read_bytes())

    async def no_words(self, *a):
        return "", None
    monkeypatch.setattr(Engine, "_to_flac", to_flac)
    monkeypatch.setattr(Engine, "_published_lyrics", no_words)
    ctx = _Ctx(store, "run2")
    asyncio.run(eng.gather(ctx))
    got = {s["title"]: s for s in store.run("run2")["songs"]}
    assert got["Song 0"]["source"] == "library" and got["Song 0"]["path"] == "Band/Song 0.flac" and got["Song 0"]["state"] == "ready"
    assert got["Song 4"]["state"] == "failed" and got["Song 4"]["note"] == "It wasn't there"
    assert ctx.queued == ["influence.listen"] and "Getting 9 songs with Tape Deck" in ctx.said


def test_a_run_whose_song_finder_has_gone_says_so(tmp_path):
    songs = [{"id": "track-001", "artist": "Band", "title": "Song", "source": "finder", "use": True, "state": "waiting"}]
    eng, store = _engine(tmp_path, {"id": "run3", "status": "planned", "folder": "training/y", "finder": "Tape Deck", "songs": songs})
    with pytest.raises(JobError, match="at least 8"):
        asyncio.run(eng.gather(_Ctx(store, "run3")))
    assert store.run("run3")["songs"][0]["note"] == "Tape Deck isn't here any more: add its audio"


def test_add_ons_are_loaded_from_a_folder_and_one_that_breaks_is_skipped(tmp_path):
    from sv import addons
    (tmp_path / "good.py").write_text("def register(app):\n    app.seen.append('good')\n")
    (tmp_path / "bad.py").write_text("raise RuntimeError('no')\n")
    (tmp_path / "_helper.py").write_text("raise RuntimeError('not an add-on')\n")
    app = types.SimpleNamespace(seen=[])
    assert addons.load(str(tmp_path), app) == ["good"] and app.seen == ["good"]
    assert addons.load("", app) == [] and addons.load(str(tmp_path / "none"), app) == []


def test_a_run_planned_before_there_was_a_song_finder_gets_its_missing_songs_when_it_carries_on(tmp_path, monkeypatch):
    from sv.influence_engine import Engine
    songs = [{"id": f"track-{i:03d}", "artist": "Band", "title": f"Song {i}", "source": "needed", "use": True,
              "state": "needed", "note": "Add its audio"} for i in range(9)]
    eng, store = _engine(tmp_path, {"id": "run4", "status": "stopped", "folder": "training/z", "songs": songs})
    eng.finder = _Finder(has={f"Song {i}" for i in range(8)})

    async def to_flac(self, src, dest):
        dest.write_bytes(src.read_bytes())

    async def no_words(self, *a):
        return "", None
    monkeypatch.setattr(Engine, "_to_flac", to_flac)
    monkeypatch.setattr(Engine, "_published_lyrics", no_words)
    asyncio.run(eng.gather(_Ctx(store, "run4")))
    run = store.run("run4")
    got = {s["title"]: s for s in run["songs"]}
    assert run["finder"] == "Tape Deck" and got["Song 0"]["state"] == "ready" and got["Song 0"]["source"] == "library"
    assert got["Song 8"]["source"] == "needed" and got["Song 8"]["note"] == "Add its audio"


def test_songs_that_cant_be_had_give_way_to_others_by_the_same_artist():
    from sv.influence_engine import replace
    songs = [{"id": "track-001", "artist": "Band", "title": "Hit", "source": "finder", "use": True},
             {"id": "track-002", "artist": "Band", "title": "Rarity", "source": "needed", "use": True},
             {"id": "track-003", "artist": "Band", "title": "Deep Cut", "source": "needed", "use": False},  # left out: stays so
             {"id": "track-004", "artist": "Duo", "title": "Lost", "source": "needed", "use": True}]
    asyncio.run(replace(_Finder(has=set(), others=["Hit", "Second Hit", "Third Hit"]), songs))
    assert [s["title"] for s in songs if s["use"]] == ["Hit", "Second Hit", "Hit"]
    new = {s["id"]: s for s in songs[4:]}
    assert new["track-005"] == {"id": "track-005", "artist": "Band", "title": "Second Hit", "source": "finder",
                                "found": {"title": "Second Hit", "seconds": 210}, "seconds": 210, "use": True,
                                "state": "waiting", "instead": "Rarity"}
    assert not songs[1]["use"] and not songs[2]["use"]
    assert new["track-006"]["artist"] == "Duo" and new["track-006"]["instead"] == "Lost"
    plain = [dict(s) for s in songs[:4]]
    asyncio.run(replace(types.SimpleNamespace(name="No ideas"), plain))  # a finder that can't suggest any
    assert len(plain) == 4


def test_carrying_on_replaces_what_still_cant_be_found(tmp_path, monkeypatch):
    from sv.influence_engine import Engine
    songs = [{"id": f"track-{i:03d}", "artist": "Band", "title": f"Song {i}", "source": "needed", "use": True,
              "state": "needed"} for i in range(9)]
    eng, store = _engine(tmp_path, {"id": "run5", "status": "stopped", "folder": "training/r", "songs": songs})
    eng.finder = _Finder(has={f"Song {i}" for i in range(7)}, others=["Song 0", "Encore", "Finale"])

    async def to_flac(self, src, dest):
        dest.write_bytes(src.read_bytes())

    async def no_words(self, *a):
        return "", None
    monkeypatch.setattr(Engine, "_to_flac", to_flac)
    monkeypatch.setattr(Engine, "_published_lyrics", no_words)
    asyncio.run(eng.gather(_Ctx(store, "run5")))
    got = {s["title"]: s for s in store.run("run5")["songs"]}
    assert not got["Song 7"]["use"] and not got["Song 8"]["use"]
    assert got["Encore"]["instead"] == "Song 7" and got["Finale"]["instead"] == "Song 8"
    assert got["Encore"]["state"] == "ready" and got["Encore"]["source"] == "library"



# ---- getting the words and the captions right ----------------------------------------------------------------

def test_published_lyrics_are_matched_to_the_recording():
    from sv.influence_engine import pick_lyrics
    hits = [{"artistName": "Godflesh", "trackName": "Like Rats", "duration": 360, "plainLyrics": "a", "syncedLyrics": ""},
            {"artistName": "Godflesh", "trackName": "Like Rats", "duration": 359, "plainLyrics": "b", "syncedLyrics": "[00:01.00] b"},
            {"artistName": "Godflesh", "trackName": "Like Rats (Live)", "duration": 359, "plainLyrics": "c"},
            {"artistName": "Someone", "trackName": "Like Rats", "duration": 359, "plainLyrics": "d"},
            {"artistName": "Godflesh", "trackName": "Like Rats", "duration": 200, "plainLyrics": "e"}]
    assert pick_lyrics(hits, "Godflesh", "Like Rats", 359.4)["plainLyrics"] == "b"
    assert pick_lyrics(hits, "Godflesh", "Like Rats", 240) is None  # nothing near its length
    assert pick_lyrics([], "Godflesh", "Like Rats", None) is None


def test_a_caption_never_names_the_artist_or_the_song():
    from sv.influence_engine import unnamed
    c = "Industrial metal with a drum machine. Godflesh's Streetcleaner is relentless. Harsh shouted male vocals."
    assert unnamed(c, "Godflesh", "Streetcleaner") == "Industrial metal with a drum machine. Harsh shouted male vocals."
    assert "Burn" not in unnamed("Burn is loud.", "Nine Inch Nails", "Burn") and unnamed("Burning synths.", "NIN", "Burn") == "Burning synths."


def test_the_writer_s_captions_are_tidied():
    from sv.writers import tasks as t
    text, schema = t.prompt("captions", {"sound": {"name": "Industrial metal", "style": "drum machines"},
                                         "songs": [{"id": "track-001", "artist": "Godflesh", "title": "Pure", "words": True,
                                                    "caption": "An instrumental thrash track."}]})
    assert "Godflesh – Pure" in text and "published lyrics were found" in text and schema["required"] == ["songs"]
    got = t.read("captions", {"songs": [{"id": "track-001", "caption": "Industrial metal, harsh shouted male vocals, drum machine.",
                                         "vocals": "sung"}, {"id": "track-002", "caption": "too short", "vocals": "sung"},
                                        {"id": "track-003", "caption": "A slow, droning instrumental built on feedback.", "vocals": "maybe"}]})
    assert [x["id"] for x in got["songs"]] == ["track-001", "track-003"] and got["songs"][1]["vocals"] == "unsure"


def _listened(tmp_path, songs, voice="male"):
    run = {"id": "run6", "status": "listening", "folder": "training/c", "name": "Industrial metal", "style": "drums",
           "voice": voice, "songs": songs}
    eng, store = _engine(tmp_path, run)
    folder = eng.folder(run)
    folder.mkdir(parents=True)
    for s in songs:
        (folder / f"{s['id']}.flac").write_bytes(b"x")
        (folder / f"{s['id']}.caption.txt").write_text("A punk rock track with no vocals.\n")
        (folder / f"{s['id']}.lyrics.txt").write_text(("word " * 30) if s.pop("words", False) else "")
    return eng, store, folder


def test_captions_are_checked_and_a_sung_song_without_its_words_is_left_out(tmp_path):
    songs = [{"id": "track-001", "artist": "Godflesh", "title": "Pure", "use": True, "words": True},
             {"id": "track-002", "artist": "Godflesh", "title": "Like Rats", "use": True},
             {"id": "track-003", "artist": "Ambient Act", "title": "Drift", "use": True},
             {"id": "track-004", "artist": "Obscure", "title": "B-side", "use": True}]
    eng, store, folder = _listened(tmp_path, songs)
    sent = []

    async def write(task, body):
        sent.append(body)
        return {"by": {"name": "Claude"}, "result": {"songs": [
            {"id": "track-001", "caption": "Industrial metal. Pure is great. Harsh shouted male vocals.", "vocals": "sung"},
            {"id": "track-002", "caption": "Industrial metal, harsh shouted male vocals.", "vocals": "sung"},
            {"id": "track-003", "caption": "Dark ambient drones, instrumental.", "vocals": "instrumental"},
            {"id": "track-004", "caption": "Industrial rock.", "vocals": "unsure"}]}}
    eng.writers = types.SimpleNamespace(write=write)
    asyncio.run(eng._check_captions(_Ctx(store, "run6"), "run6"))
    got = {s["id"]: s for s in store.run("run6")["songs"]}
    assert sent[0]["songs"][0]["words"] is True and sent[0]["songs"][1]["words"] is False
    assert (folder / "track-001.caption.txt").read_text() == "Industrial metal. Harsh shouted male vocals.\n"
    assert got["track-001"]["use"] and got["track-001"]["captionChecked"] and got["track-001"]["captionBy"] == "Claude"
    assert not got["track-002"]["use"] and not (folder / "track-002.flac").exists() and "left out" in got["track-002"]["note"]
    assert got["track-003"]["use"] and got["track-003"]["vocals"] == "instrumental"  # a real instrumental stays
    assert not got["track-004"]["use"]  # unsure, in a sung sound: left out


def test_without_a_writer_the_captions_stay_and_songs_without_words_go_when_the_sound_is_sung(tmp_path):
    from sv.writers import WriterError
    async def write(task, body):
        raise WriterError("No writer could do it.")
    songs = [{"id": "track-001", "artist": "A", "title": "One", "use": True, "words": True},
             {"id": "track-002", "artist": "A", "title": "Two", "use": True}]
    eng, store, folder = _listened(tmp_path, [dict(x) for x in songs])
    eng.writers = types.SimpleNamespace(write=write)
    asyncio.run(eng._check_captions(_Ctx(store, "run6"), "run6"))
    got = {s["id"]: s for s in store.run("run6")["songs"]}
    assert got["track-001"]["use"] and not got["track-002"]["use"]
    assert (folder / "track-001.caption.txt").read_text() == "A punk rock track with no vocals.\n"
    (tmp_path / "inst").mkdir()
    eng, store, folder = _listened(tmp_path / "inst", [dict(x) for x in songs], voice=None)
    eng.writers = types.SimpleNamespace(write=write)
    asyncio.run(eng._check_captions(_Ctx(store, "run6"), "run6"))
    assert all(s["use"] for s in store.run("run6")["songs"])  # an instrumental sound keeps them


def test_train_again_starts_a_new_run_with_the_same_songs(tmp_path):
    songs = [{"id": "track-001", "artist": "A", "title": "One", "source": "library", "path": "A/One.flac", "use": True,
              "state": "ready", "lyricsFrom": "published", "captionChecked": True},
             {"id": "track-002", "artist": "B", "title": "Two", "source": "yours", "use": True, "state": "ready", "file": "two.mp3"},
             {"id": "track-003", "artist": "C", "title": "Three", "source": "finder", "found": {"ref": 1}, "use": False, "state": "failed"}]
    old = {"id": "rold01", "status": "choosing", "trigger": "sv_industrial_metal", "name": "Industrial metal", "style": "x",
           "voice": "male", "songs": songs, "train": {"status": "complete"}, "folder": "training/sv-industrial_metal-old01"}
    eng, store = _engine(tmp_path, old)
    store.create_run = lambda status, doc: (store.runs.__setitem__("rnew002", {"id": "rnew002", "status": status, **doc})
                                            or store.run("rnew002"))
    new = eng.again("rold01")
    assert new["status"] == "planned" and new["again"] == "rold01" and new["name"] == "Industrial metal" and "train" not in new
    assert new["folder"] == "training/sv-industrial_metal-new002" and new["runName"] == "sv_industrial_metal_new002"
    got = {s["id"]: s for s in new["songs"]}
    assert got["track-001"] == {"id": "track-001", "artist": "A", "title": "One", "path": "A/One.flac", "source": "library",
                                "use": True, "state": "waiting"}
    assert got["track-002"]["source"] == "needed" and got["track-003"]["found"] == {"ref": 1} and not got["track-003"]["use"]
