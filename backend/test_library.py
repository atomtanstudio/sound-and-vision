from .test_api import client, payload


def test_batch_move_and_persistent_empty_project(client):
    c, store, config = client
    tracks = c.post("/api/generations", json=payload()).json()["tracks"]
    ids = [t["id"] for t in tracks]
    response = c.post("/api/projects", json={"name": "  Ambient album  "})
    assert response.status_code == 200
    project = response.json()
    assert c.post("/api/projects", json={"name": "ambient album"}).json() == project
    assert c.post("/api/projects", json={"name": " "}).status_code == 422
    assert (
        c.post(
            "/api/library/actions",
            json={"ids": ids, "action": "move", "project": "Ambient album"},
        ).status_code
        == 200
    )
    from .api import Store

    assert {t["project"] for t in Store(config.data).rows()} == {"Ambient album"}
    assert project in c.get("/api/projects").json()["projects"]
    before = store.rows()
    assert (
        c.post(
            "/api/library/actions",
            json={
                "ids": [ids[0], "f" * 32],
                "action": "move",
                "project": "Invalid move",
            },
        ).status_code
        == 404
    )
    assert store.rows() == before
    assert not any(
        p["name"] == "Invalid move" for p in c.get("/api/projects").json()["projects"]
    )


def test_trash_restore_atomic_and_retains_files(client):
    c, store, _ = client
    ids = [t["id"] for t in c.post("/api/generations", json=payload()).json()["tracks"]]
    for take in ids:
        c.post(f"/api/takes/{take}/cancel")
    with store.db() as db:
        db.execute(
            "UPDATE generation_jobs SET state='running' WHERE take_id=?", (ids[1],)
        )
    assert (
        c.post("/api/library/actions", json={"ids": ids, "action": "trash"}).status_code
        == 409
    )
    assert all(t["deletedAt"] is None for t in store.rows())
    with store.db() as db:
        db.execute(
            "UPDATE generation_jobs SET state='cancelled' WHERE take_id=?", (ids[1],)
        )
    original = store.root / "runs" / ids[0] / "original.wav"
    original.parent.mkdir()
    original.write_bytes(b"preserve this recording")
    assert (
        c.post("/api/library/actions", json={"ids": ids, "action": "trash"}).status_code
        == 200
    )
    assert c.get("/api/library").json()["tracks"] == []
    assert len(c.get("/api/library?include_deleted=true").json()["tracks"]) == 2
    assert original.read_bytes() == b"preserve this recording"
    assert c.post(f"/api/takes/{ids[0]}/retry").status_code == 409
    assert (
        c.patch(f"/api/takes/{ids[0]}", json={"title": "Hidden edit"}).status_code
        == 409
    )
    # A repeated deletion is safe, and preserves the first deletion timestamp.
    before = store.rows(include_deleted=True)
    assert (
        c.post("/api/library/actions", json={"ids": ids, "action": "trash"}).status_code
        == 200
    )
    assert store.rows(include_deleted=True) == before
    assert (
        c.post(
            "/api/library/actions",
            json={"ids": ids, "action": "move", "project": "Album"},
        ).status_code
        == 409
    )
    assert (
        c.post(
            "/api/library/actions", json={"ids": ids, "action": "restore"}
        ).status_code
        == 200
    )
    assert len(store.rows()) == 2
    assert all(t["deletedAt"] is None for t in store.rows())
    assert original.exists()


def test_batch_auth_and_input_constraints(client):
    c, store, _ = client
    for ids in [[], ["bad"], ["a" * 32] * 2, ["0" * 32] * 201]:
        assert (
            c.post(
                "/api/library/actions", json={"ids": ids, "action": "trash"}
            ).status_code
            == 422
        )
    assert (
        c.post(
            "/api/library/actions", json={"ids": ["a" * 32], "action": "move"}
        ).status_code
        == 422
    )
    assert (
        c.post(
            "/api/library/actions", json={"ids": ["a" * 32], "action": "purge"}
        ).status_code
        == 422
    )
    assert c.get("/api/projects", headers={"Authorization": "bad"}).status_code == 401
    assert (
        c.post(
            "/api/library/actions",
            json={"ids": ["a" * 32], "action": "trash"},
            headers={"Authorization": "bad"},
        ).status_code
        == 401
    )
