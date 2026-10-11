from sv.imports import parse_lrc, safe_suffix, AUDIO
from sv.music import yue2


def test_lrc_lines_and_sheet():
    lrc = ("[ar:Someone]\n[ti:A Song]\n[00:12.50]first line here\n[00:15.00]second line\n"
           "[00:30.25]after a long rest\n[00:33.00][01:40.00]a repeated line\n[00:36.10]")
    lines, sheet = parse_lrc(lrc)
    assert [x["start"] for x in lines] == [12.5, 15.0, 30.25, 33.0, 100.0]
    assert lines[0]["end"] == 15.0 and lines[-1]["end"] == 106.0  # the last runs at most a few seconds on
    assert sheet.count("[Verse]") == 3 and "first line here\nsecond line" in sheet


def test_enhanced_lrc_word_stamps_are_dropped():
    lines, _ = parse_lrc("[00:01.00]<00:01.00>hello <00:01.50>there")
    assert lines[0]["text"] == "hello there"


def test_uploads_are_known_audio():
    assert safe_suffix("song.MP3", AUDIO) == ".mp3" and safe_suffix("song.exe", AUDIO) is None


def test_a_cover_sings_to_the_covered_song():
    req = yue2.SongRequest(lyrics="[Verse]\none two three four five\n[Chorus]\nsix seven eight nine ten", genres=["jazz"],
                           cover=yue2.CoverChoice(keep="full", reference="reference/ref-1.flac", seconds=200.0))
    sent = yue2.prepare(req, {})
    assert sent["sketch"] == {"reference": "reference/ref-1.flac", "mode": "full"}
    assert sent["sing"]["plan"] == "full" and sent["sing"]["seconds"] == 220.0
    try:
        yue2.prepare(yue2.SongRequest(lyrics=req.lyrics, cover=yue2.CoverChoice(keep="melody")), {})
        raise AssertionError("a cover needs its song")
    except yue2.SongError:
        pass
