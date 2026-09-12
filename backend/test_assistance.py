import asyncio, json
from pathlib import Path
import pytest
from fastapi import HTTPException
from .api import Settings, Store, create_app
from .assistance import Assistance, WritingInput
from fastapi.testclient import TestClient


@pytest.mark.parametrize("count", [1, 2])
def test_one_cover_scheduled_per_take(tmp_path, monkeypatch, count):
    config = Settings(tmp_path / "data", tmp_path / "model", tmp_path / "vae", "x" * 40)
    app = create_app(config, start_worker=False)
    app.state.assistance.account.connected = True
    app.state.assistance.account.image_generation = True
    scheduled = []

    def cover(service, take_id, request_id):
        scheduled.append((take_id, request_id))

    monkeypatch.setattr("backend.api.start_cover", cover)
    with TestClient(app, headers={"Authorization": "Bearer " + config.token}) as c:
        body = {
            "requestId": "cover-fanout-001",
            "form": {
                "description": "original folk",
                "lyrics": "Original lyrics",
                "count": count,
            },
        }
        response = c.post("/api/generations", json=body)
        assert response.status_code == 202
        assert {row[0] for row in scheduled} == {
            t["id"] for t in response.json()["tracks"]
        }
        assert len(scheduled) == count
        assert c.post("/api/generations", json=body).json()["reused"]
        assert len(scheduled) == count


def test_review_proposal_limits_changes(tmp_path):
    async def run():
        service = Assistance(Store(tmp_path))

        async def turn(*args):
            return [
                {
                    "type": "agentMessage",
                    "text": json.dumps(
                        {
                            "title": "unrequested",
                            "lyrics": "unrequested",
                            "style": "Warm cello and piano",
                            "abc": "unrequested",
                            "summary": "Refined arrangement",
                            "ideas": [],
                        }
                    ),
                }
            ], "test-model"

        service.account.turn = turn
        body = WritingInput(
            requestId="test-writing-001",
            task="Refine the style",
            title="Original",
            lyrics="Keep me",
            abc="Keep score",
        )
        result = await service.write(body)
        assert result["proposal"]["style"] == "Warm cello and piano"
        assert result["proposal"]["title"] == "Original"
        assert result["proposal"]["lyrics"] == "Keep me"
        assert result["proposal"]["abc"] == "Keep score"
        assert result["input"]["lyrics"] == "Keep me"

    asyncio.run(run())


def test_direct_description_preserves_other_fields_and_rejects_empty_output(tmp_path):
    async def run():
        service=Assistance(Store(tmp_path))
        style='Industrial metal with a female vocalist, syncopated low guitars and mechanical drums.'
        async def turn(prompt,*args):
            assert 'industrial metal with a female vocalist' in prompt
            return [{'type':'agentMessage','text':json.dumps({
                'title':'wrong','lyrics':'wrong','style':style,'abc':'wrong','summary':'Done',
                'ideas':[{'title':'wrong','style':'wrong','description':'wrong'}]})}], 'test-model'
        service.account.turn=turn
        body=WritingInput(requestId='describe-song-001',task='Describe song',
            prompt='industrial metal with a female vocalist',title='Keep title',lyrics='Keep lyrics',abc='Keep score')
        result=await service.write(body)
        assert result['proposal']['style']==style
        assert result['proposal']['title']=='Keep title'
        assert result['proposal']['lyrics']=='Keep lyrics'
        assert result['proposal']['abc']=='Keep score'
        assert result['proposal']['ideas']==[]
        style='   '
        with pytest.raises(ValueError,match='empty description'):await service.write(body)
    asyncio.run(run())


def test_score_edit_rejects_changed_melody(tmp_path):
    async def run():
        service = Assistance(Store(tmp_path))
        original = (Path(__file__).parent / "vendor/example-melody.abc").read_text()
        # Change tempo while claiming melody/timing preservation.
        import re

        changed = re.sub(r"Q:1/4=\d+", "Q:1/4=17", original)
        assert changed != original

        async def turn(*args):
            return [
                {
                    "type": "agentMessage",
                    "text": json.dumps(
                        {
                            "title": "",
                            "lyrics": "",
                            "style": "",
                            "abc": changed,
                            "summary": "Changed tempo",
                            "ideas": [],
                        }
                    ),
                }
            ], "test-model"

        service.account.turn = turn
        with pytest.raises(ValueError, match="protected melody or timing"):
            await service.write(
                WritingInput(
                    requestId="test-score-001",
                    task="Edit score",
                    abc=original,
                    preserveMelody=True,
                )
            )

    asyncio.run(run())


def test_job_idempotency_cancel_and_restart(tmp_path):
    async def run():
        service = Assistance(Store(tmp_path))
        began = asyncio.Event()

        async def wait():
            began.set()
            await asyncio.Event().wait()

        first = service.submit(
            "persistent-request", "writing", {"original": "keep"}, wait
        )
        same = service.submit(
            "persistent-request", "writing", {"original": "keep"}, wait
        )
        assert first["id"] == same["id"]
        with pytest.raises(HTTPException) as e:
            service.submit(
                "persistent-request", "writing", {"original": "changed"}, wait
            )
        assert e.value.status_code == 409
        await began.wait()
        await service.close()
        assert service.get(first["id"])["state"] == "cancelled"
        with service.store.db() as db:
            assert json.loads(
                db.execute("SELECT input_json FROM assistance_jobs").fetchone()[0]
            ) == {"original": "keep"}
            db.execute("UPDATE assistance_jobs SET state='running'")
        service.recover()
        assert service.get(first["id"])["state"] == "failed"

    asyncio.run(run())


def test_reference_upload_boundaries_and_provenance(tmp_path, monkeypatch):
    root = tmp_path
    (root / ".venv-reference/bin").mkdir(parents=True)
    (root / ".venv-reference/bin/python").touch()
    lock = root / "reference.lock.json"
    lock.write_text("{}")
    monkeypatch.setenv("SOUND_VISION_REFERENCE_LOCK", str(lock))
    config = Settings(root / "data", root / "model", root / "vae", "x" * 40)
    app = create_app(config, start_worker=False)
    with TestClient(app, headers={"Authorization": "Bearer " + config.token}) as c:
        assert c.post("/api/references?mode=invalid", content=b"a").status_code == 422
        assert (
            c.post(
                "/api/references", content=b"", headers={"X-Filename": "track.wav"}
            ).status_code
            == 422
        )
        assert (
            c.post(
                "/api/references", content=b"a", headers={"X-Filename": "playlist.m3u"}
            ).status_code
            == 422
        )
        assert (
            c.post(
                "/api/references",
                content=b"a",
                headers={"Content-Length": str(51 * 1024 * 1024)},
            ).status_code
            == 413
        )
        assert c.get("/api/takes/missing/cover").status_code == 404
        assert (
            c.get("/api/openai/account", headers={"Authorization": "bad"}).status_code
            == 401
        )
        submission = {
            "requestId": "reference-missing",
            "form": {
                "description": "pop",
                "lyrics": "Original line",
                "referenceId": "0" * 32,
            },
        }
        assert c.post("/api/generations", json=submission).status_code == 404
