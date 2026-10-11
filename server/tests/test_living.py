from sv.video.living import acceptable, schedule, settings_of, snap, with_picture
from sv.writers import tasks
from sv.video import h3


def test_schedule_takes_turns_at_sections():
    starts = [15.9, 31.3, 62.2, 79.4, 110.1, 117.7, 146.4, 150.2, 167.4, 198.0, 215.1, 220.8, 251.2, 266.4]
    plan = schedule(269.08, 2, starts)
    assert plan[0]["start"] == 0 and plan[-1]["end"] == 269.08
    assert all(a["end"] == b["start"] for a, b in zip(plan, plan[1:]))
    assert all(a["loop"] != b["loop"] for a, b in zip(plan, plan[1:]))  # neighbours always differ
    assert all(x["end"] - x["start"] >= 7.5 for x in plan)                # no flicker of a few seconds
    assert {x["loop"] for x in plan} == {0, 1}


def test_one_loop_is_one_stretch_and_no_sections_still_turns():
    assert schedule(200, 1, [30, 60]) == [{"loop": 0, "start": 0.0, "end": 200}]
    plan = schedule(100, 3, [])
    assert len({x["loop"] for x in plan}) == 3 and plan[-1]["end"] == 100


def test_settings_are_clamped_and_feel_decides_what_passes():
    s = settings_of({"settings": {"count": 9, "seconds": 7, "feel": "wild"}})
    assert (s["count"], s["seconds"], s["feel"], s["keepPeople"], s["transition"]) == (4, 6, "subtle", False, "seamless")
    # the old "hold" setting (saved as True by default) no longer holds anyone
    assert settings_of({"settings": {"hold": True}})["keepPeople"] is False and "hold" not in settings_of({"settings": {"hold": True}})
    assert acceptable({"motion": "calm"}, "still") and not acceptable({"motion": "lively", "changed": 0.2}, "still")
    assert acceptable({"motion": "lively", "changed": 0.2}, "subtle") and not acceptable({"motion": "lively", "changed": 0.3}, "subtle")
    assert acceptable({"motion": "lively", "changed": 0.3}, "gentle") and not acceptable({"motion": "cuts"}, "gentle")


def test_h3_length_and_prompt():
    assert h3.snap_length(6) == 141 and (h3.snap_length(4) - 5) % 17 == 0
    text = h3.prompt("Dust drifts   in the light.", "still")
    assert text.startswith(h3.SHOT) and "Dust drifts in the light." in text and "almost still" in text


def test_changes_land_where_the_loop_is_back_on_the_cover():
    lengths = [11.667, 5.833]  # loops of different lengths: each ends on whole loops of its own
    plan = snap(schedule(269.08, 2, [15.9, 31.3, 62.2, 79.4, 110.1, 117.7, 146.4, 167.4, 198.0, 220.8, 251.2]), 269.08, lengths)
    assert plan[0]["start"] == 0 and plan[-1]["end"] == 269.08
    assert all(a["end"] == b["start"] for a, b in zip(plan, plan[1:]))
    for st in plan[:-1]:
        whole = (st["end"] - st["start"]) / lengths[st["loop"]]
        assert abs(whole - round(whole)) < 1e-6 and round(whole) >= 1


def test_a_new_picture_clears_words_written_for_another():
    lv = {"picture": 1, "plan": {"cover": 1, "people": True},
          "loops": [{"id": "a", "motion": "The woman starts to glitch", "madeWith": "The woman starts to glitch", "cover": 1, "video": "x.mp4"},
                    {"id": "b", "motion": "Dust drifts", "edited": True}]}
    out = with_picture(lv, 2)
    assert out["picture"] == 2 and "plan" not in out
    assert [x["motion"] for x in out["loops"]] == ["", ""] and out["loops"][0]["video"] == "x.mp4"
    # the same picture again changes nothing
    same = with_picture({**lv, "picture": 1}, 1)
    assert same["loops"][0]["motion"] == "The woman starts to glitch" and same["plan"]["cover"] == 1


def test_claude_art_directs_with_free_rein():
    text, schema = tasks.prompt("living", {"song": {"title": "Low Moon Kiln"}, "note": "rain",
                                           "made": ["A woman in a red robe in a flooded cistern", "An empty chair in a sunlit room"]})
    assert "complete creative freedom" in text and "kiln" in text and "flooded cistern" in text and "rain" in text
    assert set(schema["required"]) >= {"idea", "prompt", "finish", "count", "feel", "transition"}
    d = tasks.read("living", {"idea": "Dust in the light", "why": "It fits", "finish": "a faint CRT glow on the beat",
                              "prompt": "A macro photograph of iron filings arranged by a magnet, cold blue light, deep black",
                              "count": 9, "feel": "wild", "seconds": 7, "transition": "spin"})
    assert (d["picture"], d["count"], d["feel"], d["seconds"], d["transition"]) == ("new", 2, "subtle", 6, "seamless")
    assert d["finish"].startswith("a faint CRT")
    try:
        tasks.read("living", {"idea": "x", "why": "", "prompt": "", "finish": "", "count": 2, "feel": "still",
                              "seconds": 6, "transition": "seamless"})
        raise AssertionError("the picture needs a prompt")
    except ValueError:
        pass


def test_mitte_not_connected_is_recognised_so_it_can_try_again():
    from sv.covers import NOT_CONNECTED
    from sv.writers.providers import OAUTH_HICCUP
    seen = ["The Mitte tools are not available in this session. The claude.ai Mitte server is still connecting and no "
            "run_node, get_task, or get_node_run tool has been announced.",
            "The Mitte tools (run_node, get_task, get_node_run) are not available in this session. Only the "
            "StructuredOutput tool is loaded."]
    assert all(NOT_CONNECTED.search(x) for x in seen)
    assert not NOT_CONNECTED.search("Content policy violation: the prompt was rejected")
    assert OAUTH_HICCUP.search("Failed to refresh OAuth token") and not OAUTH_HICCUP.search("Rate limited")


def test_a_loop_closes_forward_without_playing_back(tmp_path):
    """A bar sliding steadily right: closed into a loop, every step (the wrap included) keeps moving right."""
    import shutil
    import numpy as np
    import pytest
    from sv.video import loops
    if not shutil.which("ffmpeg"):
        pytest.skip("needs ffmpeg")
    w = h = 64
    n, overlap = 60, 12

    def frame(x):
        f = np.zeros((h, w, 3), np.uint8)
        xs = (np.arange(w) - x) % w
        f[:, :, :] = (np.clip(255 - np.abs(xs - 8) * 40, 0, 255)).astype(np.uint8)[None, :, None]
        return f
    src, dest = tmp_path / "src.mp4", tmp_path / "loop.mp4"
    loops.write_frames([frame(i * 0.5) for i in range(n)], str(src), 24, w, h, crf=0)
    assert loops.close(str(src), str(dest), overlap) == n - overlap
    f = loops.read_frames(str(dest), gray=True).astype(np.float32)
    centre = [float((np.arange(w) * fr.mean(axis=0)).sum() / fr.mean(axis=0).sum()) for fr in f]
    # the blend region moves the bar too, never backwards by more than a hair
    assert (np.diff(centre[overlap:]) > 0).all() and np.abs(f[-1] - f[0]).mean() < 4 * np.median(np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))) + 1


def test_pieces_join_on_a_shared_moment(tmp_path):
    """Two pieces of a bar sliding right, the second starting `blend` frames before the first ends (with a jump, as a
    video model's first frames have): joined, no step is much bigger than an ordinary one."""
    import shutil
    import numpy as np
    import pytest
    from sv.video import loops
    if not shutil.which("ffmpeg"):
        pytest.skip("needs ffmpeg")
    w = h = 64

    def frame(x, lift=0):
        f = np.zeros((h, w, 3), np.uint8)
        xs = (np.arange(w) - x) % w
        f[:, :, :] = (np.clip(255 - np.abs(xs - 8) * 40 + lift, 0, 255)).astype(np.uint8)[None, :, None]
        return f
    blend = 8
    a, b, dest = tmp_path / "a.mp4", tmp_path / "b.mp4", tmp_path / "ab.mp4"
    loops.write_frames([frame(i * 0.5) for i in range(40)], str(a), 24, w, h, crf=0)
    start = 39 - blend  # frame_at(a, back=blend)
    loops.write_frames([frame((start + i) * 0.5, lift=30 if i else 0) for i in range(40)], str(b), 24, w, h, crf=0)
    n = loops.join(str(dest), [str(a), str(b)], blend)
    assert n == 40 - blend + 40 - 1
    f = loops.read_frames(str(dest), gray=True).astype(np.float32)
    steps = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))
    assert steps.max() < 3 * np.median(steps) + 2


def test_claude_s_readme_summary_keeps_the_list_it_leads_into():
    from sv.video.finish import _about
    readme = ("# Title\n\nThe drum is played off frame. The finish only answers the low end:\n\n"
              "- **The kick strikes the drumhead.** Every kick sends a ring.\n- **The walls light up.** On downbeats.\n\n## Render\n")
    assert _about(readme) == ("The drum is played off frame. The finish only answers the low end: The kick strikes the "
                              "drumhead; The walls light up.")
