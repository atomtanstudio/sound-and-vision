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
