import json
import pytest
from fastapi.testclient import TestClient
from .api import Settings, Store, create_app


@pytest.fixture
def client(tmp_path):
    config = Settings(
        tmp_path / "data",
        tmp_path / "model",
        tmp_path / "vae",
        "test-token-" + "x" * 40,
    )
    app = create_app(config, start_worker=False)
    with TestClient(app, headers={"Authorization": "Bearer " + config.token}) as client:
        yield client, app.state.store, config


def payload(count=2, request_id="test-request-0001"):
    return {
        "requestId": request_id,
        "form": {
            "description": "Warm English piano pop",
            "title": "Test song",
            "lyrics": "[Verse]\nWe follow the morning light",
            "count": count,
            "seed": "9223372036854775807",
        },
    }


def test_auth_and_validation(client):
    c, store, config = client
    assert c.get("/api/health", headers={"Authorization": "bad"}).status_code == 401
    no_lyrics = payload()
    no_lyrics["form"]["lyrics"] = ""
    assert c.post("/api/generations", json=no_lyrics).status_code == 422
    bad = payload()
    bad["form"]["seed"] = "9223372036854775808"
    assert c.post("/api/generations", json=bad).status_code == 422
    bad = payload()
    bad["form"]["semantic"] = {"min_tokens": 100, "max_tokens": 2}
    assert c.post("/api/generations", json=bad).status_code == 422
    assert store.rows() == []


def test_idempotency_and_persistence(client):
    c, store, config = client
    response = c.post("/api/generations", json=payload())
    assert response.status_code == 202, response.text
    tracks = response.json()["tracks"]
    assert len(tracks) == 2
    assert {t["seed"] for t in tracks} == {"9223372036854775807", "0"}
    assert c.post("/api/generations", json=payload()).json()["reused"] is True
    assert len(Store(config.data).rows()) == 2
    changed = payload()
    changed["form"]["title"] = "Different"
    assert c.post("/api/generations", json=changed).status_code == 409
    with store.db() as db:
        assert (
            db.execute("SELECT COUNT(*) FROM assets WHERE kind='cover'").fetchone()[0]
            == 2
        )


def test_cancel_retry_and_publication(client):
    c, store, _ = client
    track = c.post("/api/generations", json=payload(1)).json()["tracks"][0]
    take = track["id"]
    assert c.post(f"/api/takes/{take}/cancel").status_code == 200
    # A racing resource probe must not resurrect a cancelled job.
    store.update_job(take, "waiting-for-resource", "waiting-for-resource", "GPU busy")
    assert store.job(take)["state"] == "cancelled"
    assert c.post(f"/api/takes/{take}/retry").status_code == 200
    assert store.job(take)["state"] == "queued"
    assert c.get(f"/api/takes/{take}/files/audio.wav").status_code in {404, 409}
    assert c.get(f"/api/takes/{take}/files/spec.json").status_code == 404
    assert (
        c.patch(
            f"/api/takes/{take}",
            json={"title": "Renamed", "favorite": True, "project": "Album"},
        ).json()["title"]
        == "Renamed"
    )
    assert c.patch(f"/api/takes/{take}", json={"project": "  "}).status_code == 422


def test_plan_review_preserves_source(client):
    c, store, _ = client
    track = c.post("/api/generations", json=payload(1)).json()["tracks"][0]
    take = track["id"]
    folder = store.root / "runs" / take / "attempt-001"
    (folder / "plan").mkdir(parents=True)
    (folder / "plan" / "score.abc").write_text("X:1\nK:C\nCDEF")
    key = f"runs/{take}/attempt-001"
    with store.db() as db:
        db.execute(
            "UPDATE generation_jobs SET output_key=?,state='needs-review' WHERE take_id=?",
            (key, take),
        )
    assert c.get(f"/api/takes/{take}/plan").json()["abc"].startswith("X:1")
    assert (
        c.post(
            f"/api/takes/{take}/continue", json={"abc": "X:1\nK:C\nDEFG"}
        ).status_code
        == 200
    )
    assert store.job(take)["resume_plan_key"] == key + "/plan"
    assert (folder / "plan" / "score.abc").read_text().endswith("CDEF")
    assert c.post(f"/api/takes/{take}/continue", json={}).status_code == 409


def test_restart_marks_interrupted_without_discarding_files(client):
    c, store, config = client
    track = c.post("/api/generations", json=payload(1)).json()["tracks"][0]
    take = track["id"]
    retained = store.root / "runs" / take / "partial.txt"
    retained.parent.mkdir()
    retained.write_text("keep")
    with store.db() as db:
        db.execute(
            "UPDATE generation_jobs SET state='running' WHERE take_id=?", (take,)
        )
    manager = c.app.state.manager
    manager.start()
    manager.close()
    assert store.job(take)["state"] == "failed"
    assert store.job(take)["stage"] == "interrupted"
    assert retained.read_text() == "keep"
