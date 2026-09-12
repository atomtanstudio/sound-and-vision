import asyncio, base64, io, json
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient
from .api import Settings, create_app
from .alignment_runner import reconcile


def test_motion_reference_requires_paired_valid_audio_and_image_fields():
    import pytest
    from pydantic import ValidationError
    from .video import VideoRequest

    base = {
        "requestId": "reference-test-001",
        "kind": "motion",
        "prompt": "A quiet room",
    }
    for extra in [
        {"audioStart": 0},
        {"referenceImageJobId": "image-test-001"},
        {"audioStart": -1, "referenceImageJobId": "image-test-001"},
        {"audioStart": float("inf"), "referenceImageJobId": "image-test-001"},
        {"audioStart": 0, "referenceImageJobId": "../../escape"},
        {"kind": "images", "audioStart": 0, "referenceImageJobId": "image-test-001"},
    ]:
        with pytest.raises(ValidationError):
            VideoRequest(**{**base, **extra})
    valid = VideoRequest(
        **base, seconds=15.5, audioStart=0, referenceImageJobId="image-test-001"
    )
    assert valid.audioStart == 0 and valid.seconds == 15.5
    # Old integer-duration requests retain their canonical serialization, so
    # retries of saved requests remain idempotent after this schema extension.
    old = VideoRequest(**base).model_dump(exclude_none=True)
    assert type(old["seconds"]) is int
    assert "audioStart" not in old and "referenceImageJobId" not in old


def test_alignment_never_invents_missing_word_times():
    lyrics = "[Verse]\nStay with me\n[Chorus]\nStay with me"
    evidence = [
        {"word": w, "start": i + 10, "end": i + 10.5, "probability": 0.9}
        for i, w in enumerate(["Stay", "with", "me", "Stay", "with"])
    ]
    out = reconcile(lyrics, evidence, evidence, 60)
    assert out["wordCount"] == 6
    assert out["cues"][0]["id"] != out["cues"][1]["id"]
    assert out["cues"][1]["words"][2]["start"] is None
    assert out["reviewCount"] == 1
    assert out["lyrics"] == lyrics


def test_disagreement_low_confidence_and_invalid_timing_flagged():
    a = [
        {"word": "Hello", "start": 5, "end": 5.5, "probability": 0.9},
        {"word": "there", "start": 6, "end": 6.5, "probability": 0.2},
        {"word": "friend", "start": 80, "end": 81, "probability": 0.9},
    ]
    b = [{**a[0], "start": 10}, a[1], a[2]]
    result = reconcile("Hello there friend", a, b, 60)
    assert result["reviewCount"] == 3
    assert result["cues"][0]["words"][2]["start"] is None


def test_video_api_jobs_are_idempotent_and_assets_survive_retry(tmp_path):
    config = Settings(tmp_path / "data", tmp_path / "model", tmp_path / "vae", "x" * 40)
    app = create_app(config, start_worker=False)

    async def status():
        return {"images": True, "connected": True}

    calls = []
    raw = io.BytesIO()
    Image.new("RGB", (320, 180), "navy").save(raw, format="PNG")

    async def turn(prompt, **kwargs):
        calls.append(prompt)
        return [
            {
                "type": "imageGeneration",
                "result": base64.b64encode(raw.getvalue()).decode(),
            }
        ], "test"

    app.state.assistance.account.status = status
    app.state.assistance.account.turn = turn
    with TestClient(app, headers={"Authorization": "Bearer " + config.token}) as c:
        created = c.post(
            "/api/generations",
            json={
                "requestId": "video-take-test",
                "form": {
                    "description": "Dream pop",
                    "lyrics": "Stay with me",
                    "count": 1,
                },
            },
        ).json()["tracks"][0]
        take = created["id"]
        with app.state.store.db() as db:
            db.execute(
                "UPDATE generation_jobs SET state='succeeded',output_key='test' WHERE take_id=?",
                (take,),
            )
        body = {
            "requestId": "video-image-test",
            "kind": "images",
            "aspect": "9:16",
            "prompt": "Quiet clouds",
            "slot": 0,
        }
        a = c.post(f"/api/takes/{take}/video", json=body)
        assert a.status_code == 202
        assert (
            c.post(f"/api/takes/{take}/video", json=body).json()["id"] == a.json()["id"]
        )
        import time

        for _ in range(30):
            state = c.get(f"/api/takes/{take}/video").json()["jobs"]
            if state[0]["state"] == "succeeded":
                break
            time.sleep(0.05)
        assert state[0]["state"] == "succeeded", state
        assert len(calls) == 1
        result = state[0]["result"]
        assert result["sourceDimensions"] == [320, 180]
        assert result["dimensions"] == [1080, 1920]
        media = c.get(result["assetUrl"])
        assert media.status_code == 200
        assert Image.open(io.BytesIO(media.content)).size == (1080, 1920)
        assert (
            c.post("/api/video/jobs/video-image-test/retry", json={}).json()["id"]
            == "video-image-test"
        )
        assert (
            c.post(
                f"/api/takes/{take}/video", json={**body, "prompt": "Changed"}
            ).status_code
            == 409
        )
        assert (
            c.post(
                f"/api/takes/{take}/video", json={**body, "requestId": "../../escape"}
            ).status_code
            == 422
        )
        assert (
            c.get(
                result["assetUrl"], headers={"Authorization": "Bearer wrong"}
            ).status_code
            == 401
        )
        assert (
            c.post(
                f"/api/takes/{take}/video",
                json={
                    **body,
                    "requestId": "no-alignment-model",
                    "kind": "alignment",
                    "lyrics": "Stay",
                },
            ).status_code
            == 503
        )


def test_unrecognized_phrase_is_constrained_by_audio_anchors_not_word_count():
    from .alignment_runner import fill_phrase_gaps

    windows = [
        {"start": 10, "end": 12, "text": "one two"},
        {"start": 20, "end": 22, "text": "five six"},
    ]
    tokens = ["one", "two", "three", "four", "five", "six"]
    result, offsets = fill_phrase_gaps(windows, [0, 4], tokens, 30)
    assert result[1] == {"start": 12, "end": 20, "text": "three four"}
    assert offsets == [0, 2, 4]
    # This only bounds acoustic inference. It assigns no word times at all.
    assert not any("words" in p for p in result)


def test_low_ctc_score_requires_strong_independent_corroboration():
    aligned = [{"word": "Hello", "start": 5, "end": 5.5, "probability": 0.2}]
    heard = [{"word": "Hello", "start": 5.1, "end": 5.6, "probability": 0.95}]
    assert reconcile("Hello", aligned, heard, 60)["reviewCount"] == 0
    heard[0]["start"] = 6
    assert reconcile("Hello", aligned, heard, 60)["reviewCount"] == 1


def test_ambiguous_h3_submission_cannot_duplicate_and_queued_image_cancels(tmp_path):
    config = Settings(tmp_path / "data", tmp_path / "model", tmp_path / "vae", "x" * 40)
    app = create_app(config, start_worker=False)

    async def status():
        return {"images": True, "connected": True}

    async def slow_turn(*args, **kwargs):
        await asyncio.sleep(60)

    app.state.assistance.account.status = status
    app.state.assistance.account.turn = slow_turn
    with TestClient(app, headers={"Authorization": "Bearer " + config.token}) as c:
        take = c.post(
            "/api/generations",
            json={
                "requestId": "recovery-take-001",
                "form": {
                    "description": "Ambient",
                    "lyrics": "Home tonight",
                    "count": 1,
                },
            },
        ).json()["tracks"][0]["id"]
        body = {
            "takeId": take,
            "kind": "motion",
            "slot": 0,
            "aspect": "16:9",
            "seconds": 8,
            "prompt": "Quiet sky",
            "lyrics": "",
            "language": "en",
        }
        with app.state.store.db() as db:
            db.execute(
                "UPDATE generation_jobs SET state='succeeded',output_key='test' WHERE take_id=?",
                (take,),
            )
            db.execute(
                "INSERT INTO assistance_jobs(id,kind,state,input_json,created_at,updated_at) VALUES('lost-submission','video-motion','failed',?,1,1)",
                (json.dumps(body, sort_keys=True),),
            )
        path = app.state.store.root / "video/lost-submission"
        path.mkdir(parents=True)
        (path / "h3.json").write_text(json.dumps({"submissionStarted": True}))
        assert (
            c.post("/api/video/jobs/lost-submission/retry", json={}).status_code == 409
        )
        assert (
            c.post(
                f"/api/takes/{take}/video",
                json={
                    **{k: v for k, v in body.items() if k != "takeId"},
                    "requestId": "duplicate-motion",
                },
            ).status_code
            == 409
        )
        image = c.post(
            f"/api/takes/{take}/video",
            json={
                "kind": "images",
                "prompt": "Quiet sky",
                "requestId": "queued-image-cancel",
            },
        ).json()
        assert (
            c.post(f"/api/video/jobs/{image['id']}/cancel", json={}).json()["state"]
            == "cancelled"
        )
        assert c.get(f"/api/video/jobs/{image['id']}/media").status_code == 404
