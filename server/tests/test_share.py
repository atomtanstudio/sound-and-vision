import json
import types

import numpy as np

from sv import share


def _app(tmp_path, db, lines=None):
    tid = "t1"
    d = tmp_path / "p1" / "takes" / tid
    (d / "analysis").mkdir(parents=True)
    (d / "loudness.json").write_text(json.dumps({"rate": share.RATE, "db": db}))
    (d / "analysis" / "analysis.json").write_text(json.dumps({
        "bars": [float(b) for b in range(0, 120, 2)],
        "sections": [{"label": "Verse 1", "start": 0, "end": 40}, {"label": "Chorus", "start": 40, "end": 70},
                     {"label": "", "start": 70, "end": 120}],
        "lines": lines or []}))
    store = types.SimpleNamespace(project=lambda pid: {"id": "p1", "masterTake": tid},
                                  take=lambda t: {"id": tid, "status": "ready", "duration": 120.0, "files": {"flac": "x"}})
    return share.Share(types.SimpleNamespace(cfg=types.SimpleNamespace(projects=tmp_path, ffmpeg="ffmpeg"), store=store))


def test_the_best_moment_is_the_loud_stretch_on_a_bar(tmp_path):
    db = [-40.0] * (120 * share.RATE)
    for i in range(40 * share.RATE, 70 * share.RATE):
        db[i] = -8.0  # the chorus is the loud part
    m = _app(tmp_path, db).moments("p1", 30)
    best = m["moments"][0]
    assert best["start"] == 40.0 and best["end"] == 70.0 and "chorus" in best["why"]
    assert len(m["moments"]) == 3 and all(abs(a["start"] - b["start"]) >= 22.5 for a in m["moments"] for b in m["moments"] if a is not b)
    assert len(m["level"]) <= 600 and m["sections"][1]["label"] == "Chorus"


def test_moments_stay_inside_a_shorter_video(tmp_path):
    db = list(np.linspace(-40, -5, 120 * share.RATE))  # louder and louder: the end wins unless it can't be reached
    m = _app(tmp_path, db).moments("p1", 20, upto=32)
    assert all(x["end"] <= 32 for x in m["moments"])


def test_frames_and_shapes():
    assert "force_original_aspect_ratio=increase,crop=1080:1920:x='(iw-1080)*0.250'" in share._reframe(1080, 1920, "fill", 0.25)
    assert "pad=1080:1350" in share._reframe(1080, 1350, "bars", 0.5)
    assert "gblur" in share._reframe(1080, 1920, "blur", 0.5)
    assert [share.shape_of(*share.PRESETS[k]["size"]) for k in ("tiktok", "portrait", "square", "wide")] == ["story", "portrait", "square", "wide"]


def test_a_clip_of_a_part_of_the_song_is_timed_in_the_song(tmp_path):
    db = list(np.linspace(-40, -5, 120 * share.RATE))
    s = _app(tmp_path, db)
    m = s.moments("p1", 20, upto=90, since=60)  # a video of 1:00–1:30 of the song
    assert m["moments"] and all(60 <= x["start"] and x["end"] <= 90 for x in m["moments"])
    rec = {"id": "v1", "file": "music/f/part.mp4", "seconds": 30.0, "part": {"start": 60.0, "end": 90.0}}
    s.app.library = types.SimpleNamespace(video=lambda pid, kind, vid: ({}, rec, None, None))
    doc = s._doc("p1", {"preset": "tiktok", "start": 64, "end": 100, "source": {"type": "video", "kind": "music", "vid": "v1"}})
    assert (doc["start"], doc["end"], doc["offset"]) == (64.0, 90.0, 60.0)  # the picture is read from 4 s into the video
    for bad in (10, 89.5):
        try:
            s._doc("p1", {"start": bad, "source": {"type": "video", "kind": "music", "vid": "v1"}})
            raise AssertionError(bad)
        except share.JobError as exc:
            assert "1:00 to 1:30" in exc.message
