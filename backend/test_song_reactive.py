import asyncio
import base64
import contextlib
import io
import json
import sqlite3

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from .assistance import Assistance
from .song_reactive import ArtworkRequest, RegisteredSurface, create_artwork, routes


class Provider:
    def __init__(self):
        self.calls = []
        self.confidence = .95

    async def status(self):
        return {"connected": True, "images": True}

    async def turn(self, prompt, schema=None, images=False, reference_images=()):
        self.calls.append((prompt, images, tuple(reference_images)))
        if images:
            raw = io.BytesIO()
            Image.new("RGB", (1024, 576), "#20252a").save(raw, "PNG")
            return [{"type": "imageGeneration", "result": base64.b64encode(raw.getvalue()).decode()}], "fixture"
        if schema and "heroDesign" in schema.get("properties", {}):
            data = json.loads(prompt.split("SONG DATA:\n", 1)[1].split("\nOnly the explicit", 1)[0])
            self.title = data["song"]["title"]
            data = {"concept": "A place kept for a friend", "mood": "Quiet and tender",
                    "reasoning": "The supplied lyrics describe making room for a returning friend.",
                    "evidence": ["An empty chair comes from the provided lyric imagery."],
                    "reference": "dream", "heroDesign": "A beautifully crafted pearlescent listening object with a large glass aperture, precise joinery and tactile controls.",
                    "setting": "A quiet room beside a rainy window, with a worn wooden table and restrained photographic depth.",
                    "lighting": "Soft blue evening light through rain, balanced by warm indirect lamplight on the pearl cabinet.",
                    "props": "One empty chair and a pale flower.", "titleLines": [getattr(self, "title_override", self.title)],
                    "titlePlacement": "upper-left", "effect": "ribbon", "motionReason": "Soft measured curves suit the tender mood.",
                    "color": "#aabbcc", "accent": "#ddeeff"}
        else:
            data = {"quality": .9, "visibleTitle": getattr(self, "visible_title_override", self.title),
                    "observations": "The blank glass is unobstructed inside its frame.", "surfaces": [
                {"index": 0, "corners": [{"x": x, "y": y} for x,y in getattr(self, "corners", [[.2,.3],[.7,.3],[.7,.7],[.2,.7]])], "confidence": self.confidence}
            ]}
        return [{"type": "agentMessage", "text": json.dumps(data)}], "fixture"


def test_pipeline_uses_song_data_then_registers_the_actual_generated_image(tmp_path):
    p = Provider()
    song = {"title": "Synthetic song", "genre": "Tender dream pop", "lyrics": "A chair waits by the window."}
    result = asyncio.run(create_artwork(p, song, "16:9", tmp_path))
    assert song["lyrics"] in p.calls[0][0]
    assert p.calls[1][1] is True
    assert len(p.calls[0][2]) == 3
    assert p.calls[1][2][0].endswith("dream.png")
    assert result["renderer"] == "reference-player-v1"
    assert p.calls[2][2] == (str(tmp_path / "artwork.png"),)
    assert result["surfaces"][0]["effect"] == "ribbon"
    assert result["surfaces"][0]["corners"][0] == [.2,.3]
    assert len(result["artworkSha256"]) == 64
    # Re-running this saved version makes zero additional provider calls.
    again = asyncio.run(create_artwork(p, song, "16:9", tmp_path))
    assert again == result
    assert len(p.calls) == 3
    with pytest.raises(ValueError, match="different song"):
        asyncio.run(create_artwork(p, {**song,"title":"Different"}, "16:9", tmp_path))


def test_uncertain_registration_retains_artwork_and_does_not_regenerate_it(tmp_path):
    p = Provider();p.confidence = .4
    song = {"title":"Synthetic", "genre":"Ambient", "lyrics":""}
    with pytest.raises(ValueError, match="confidently"):
        asyncio.run(create_artwork(p, song, "16:9", tmp_path))
    assert (tmp_path / "artwork.png").is_file()
    assert not (tmp_path / "scene.json").exists()
    p.confidence = .95
    asyncio.run(create_artwork(p, song, "16:9", tmp_path))
    assert sum(images for _,images,_ in p.calls) == 1


def test_explicit_revision_keeps_reference_identity_and_reuses_completed_image(tmp_path):
    reference = tmp_path / "reference.png"
    Image.new("RGB", (1024, 576), "#40252a").save(reference)
    work = tmp_path / "revision"
    p = Provider(); song = {"title": "Synthetic", "genre": "Ambient", "lyrics": ""}
    result = asyncio.run(create_artwork(p, song, "16:9", work, reference_images=[str(reference)]))
    assert p.calls[1][2] == (str(reference),)
    assert p.calls[2][2] == (str(work / "artwork.png"),)
    assert asyncio.run(create_artwork(p, song, "16:9", work, reference_images=[str(reference)])) == result
    assert len(p.calls) == 3
    Image.new("RGB", (1024, 576), "#10252a").save(reference)
    with pytest.raises(ValueError, match="different song data"):
        asyncio.run(create_artwork(p, song, "16:9", work, reference_images=[str(reference)]))
    assert len(p.calls) == 3


def test_uncertain_image_submission_cannot_be_automatically_charged_twice(tmp_path):
    class FailedImage(Provider):
        async def turn(self, *args, **kwargs):
            if kwargs.get("images"):
                self.calls.append(("uncertain", True, ()))
                raise TimeoutError("No final response")
            return await super().turn(*args, **kwargs)
    p=FailedImage();song={"title":"Synthetic","genre":"Ambient","lyrics":""}
    with pytest.raises(TimeoutError):asyncio.run(create_artwork(p,song,"16:9",tmp_path))
    with pytest.raises(ValueError,match="already requested"):
        asyncio.run(create_artwork(p,song,"16:9",tmp_path))
    assert sum(images for _,images,_ in p.calls)==1


def test_scene_geometry_and_request_boundaries():
    with pytest.raises(ValueError):ArtworkRequest(requestId="../../escape")
    with pytest.raises(ValueError):ArtworkRequest(requestId="valid-request",artworkUrl="https://example.com")
    for corners in [[[0,0],[1,1],[1,0],[0,1]], [[0,0],[0,0],[1,1],[0,1]]]:
        with pytest.raises(ValueError):RegisteredSurface(index=0,confidence=1,corners=[{"x":x,"y":y} for x,y in corners])


class Store:
    def __init__(self, root):
        self.root=root;root.mkdir()
        with self.db() as db:
            db.execute("CREATE TABLE assistance_jobs(id TEXT PRIMARY KEY,kind TEXT,state TEXT,input_json TEXT,result_json TEXT,error TEXT,created_at INTEGER,updated_at INTEGER)")
        self.tracks=[{"id":n*32,"title":"Synthetic song "+n,"status":"succeeded","form":{"style":"Dream pop","lyrics":"A chair waits by the window."}} for n in ["a","b"]]
    @contextlib.contextmanager
    def db(self):
        connection=sqlite3.connect(self.root/"test.sqlite");connection.row_factory=sqlite3.Row
        try:
            with connection:yield connection
        finally:connection.close()
    def rows(self):return self.tracks
    def job(self, take_id):
        value=next((t for t in self.tracks if t["id"]==take_id),None)
        if not value:raise HTTPException(404,"Take not found")
        return value


def test_song_owned_api_is_idempotent_and_rejects_cross_song_assets(tmp_path):
    service=Assistance(Store(tmp_path/"data"));provider=Provider();service.account=provider
    app=FastAPI();app.include_router(routes(service));path="/api/takes/"+"a"*32+"/reactive-artwork"
    with TestClient(app) as client:
        body={"requestId":"artwork-test-001","aspect":"16:9","genre":"Dream pop","lyrics":"A chair waits by the window.","notes":""}
        assert client.post(path,json=body).status_code==202
        for _ in range(100):
            job=client.get(path+"/artwork-test-001").json()
            if job["state"] not in {"queued","running"}:break
        assert job["state"]=="succeeded",job
        assert client.get(job["result"]["artworkUrl"]).status_code==200
        assert client.post(path,json=body).json()["id"]==job["id"]
        assert len(provider.calls)==3
        assert client.post(path,json={**body,"notes":"Different"}).status_code==409
        other="/api/takes/"+"b"*32+"/reactive-artwork/artwork-test-001"
        assert client.get(other).status_code==404
        assert client.get(other+"/image").status_code==404
        assert len(client.get(path).json()["jobs"])==1


def test_title_changed_by_planner_never_submits_an_image(tmp_path):
    p = Provider(); p.title_override = "A different title"
    with pytest.raises(ValueError, match="changed the song title"):
        asyncio.run(create_artwork(p, {"title": "Original title", "genre": "Ambient"}, "16:9", tmp_path))
    assert len(p.calls) == 1 and not (tmp_path / "image-request.json").exists()


def test_wrong_visible_title_and_shallow_display_require_review_without_regeneration(tmp_path):
    song = {"title": "Original title", "genre": "Ambient"}
    for name, change, message in [
        ("title", {"visible_title_override": "Wrong title"}, "title is incorrect"),
        ("glass", {"corners": [[.2,.3],[.7,.3],[.7,.32],[.2,.32]]}, "display proportions"),
    ]:
        p = Provider()
        for key, value in change.items(): setattr(p, key, value)
        work = tmp_path / name
        for _ in range(2):
            with pytest.raises(ValueError, match=message):
                asyncio.run(create_artwork(p, song, "16:9", work))
        assert sum(images for _,images,_ in p.calls) == 1
        assert (work / "artwork.png").exists() and not (work / "scene.json").exists()
