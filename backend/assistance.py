"""Reviewable writing proposals and account APIs. No paid API-key fallback."""

from __future__ import annotations
import asyncio, base64, contextlib, hashlib, io, importlib.util, json, sys, time, uuid
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from .providers import Providers, current_job
from .provider_config import ProviderConfig, public as public_config, model_paths, with_saved_key


class WritingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requestId: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{7,99}$")
    task: Literal[
        "Song ideas",
        "Describe song",
        "Draft lyrics",
        "Rewrite a section",
        "Refine the style",
        "Translate lyrics",
        "Edit score",
    ]
    prompt: str = Field(default="", max_length=20000)
    title: str = Field(default="", max_length=200)
    lyrics: str = Field(default="", max_length=100000)
    style: str = Field(default="", max_length=20000)
    abc: str = Field(default="", max_length=100000)
    preserveMelody: bool = True
    model: str | None = Field(default=None, max_length=100)


class ProviderTest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requestId: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{7,99}$")
    kind: Literal['writing', 'image']
    config: ProviderConfig


class Idea(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(max_length=200)
    style: str = Field(max_length=20000)
    description: str = Field(max_length=2000)


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(max_length=200)
    lyrics: str = Field(max_length=100000)
    style: str = Field(max_length=20000)
    abc: str = Field(max_length=100000)
    summary: str = Field(max_length=2000)
    ideas: list[Idea] = Field(max_length=3)


def score_tools():
    path = Path(__file__).parent / "vendor/abc_tools.py"
    spec = importlib.util.spec_from_file_location("sv_abc_tools", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Assistance:
    def __init__(self, store):
        self.store = store
        self.account = Providers(store.root.parent)
        self.tasks = {}
        self.limit = asyncio.Semaphore(1)
        self.image_limit = asyncio.Semaphore(1)

    def recover(self):
        with self.store.db() as db:
            db.execute(
                "UPDATE assistance_jobs SET state='failed',error='Service restarted. Start a new request; original input is retained.' WHERE state IN ('queued','running','waiting-for-resource')"
            )

    def get(self, job_id):
        with self.store.db() as db:
            row = db.execute(
                "SELECT * FROM assistance_jobs WHERE id=?", (job_id,)
            ).fetchone()
        if not row:
            raise HTTPException(404, "Request not found")
        return {
            "id": row["id"],
            "kind": row["kind"],
            "state": row["state"],
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "error": row["error"],
        }

    def save(self, job_id, state, result=None, error=None):
        with self.store.db() as db:
            db.execute(
                "UPDATE assistance_jobs SET state=?,result_json=?,error=?,updated_at=? WHERE id=?",
                (
                    state,
                    json.dumps(result) if result is not None else None,
                    error,
                    int(time.time() * 1000),
                    job_id,
                ),
            )

    def submit(self, job_id, kind, payload, operation, serialized=True):
        canonical = json.dumps(payload, sort_keys=True)
        with self.store.db() as db:
            previous = db.execute(
                "SELECT kind,input_json FROM assistance_jobs WHERE id=?", (job_id,)
            ).fetchone()
            if previous:
                if previous["kind"] != kind or previous["input_json"] != canonical:
                    raise HTTPException(
                        409, "Request ID already belongs to different inputs."
                    )
                return self.get(job_id)
            stamp = int(time.time() * 1000)
            db.execute(
                "INSERT INTO assistance_jobs(id,kind,state,input_json,created_at,updated_at) VALUES(?,?,?, ?,?,?)",
                (job_id, kind, "queued", canonical, stamp, stamp),
            )

        async def run():
            context_token = current_job.set(job_id)
            try:
                async with (
                    (self.image_limit if kind in {"cover", "video-image", "provider-image"} else self.limit)
                    if serialized
                    else contextlib.nullcontext()
                ):
                    self.save(job_id, "running")
                    result = await operation()
                    self.save(job_id, "succeeded", result=result)
            except asyncio.CancelledError:
                self.save(
                    job_id, "cancelled", error="Cancelled; original input is retained."
                )
            except Exception as e:
                self.save(job_id, "failed", error=str(e)[:1500])
            finally:
                current_job.reset(context_token)
                self.tasks.pop(job_id, None)

        self.tasks[job_id] = asyncio.create_task(run())
        return self.get(job_id)

    async def write(self, body: WritingInput, account=None):
        provider = account or self.account
        local = getattr(getattr(provider, 'config', None), 'provider', None) == 'local'
        editable = {
            "Song ideas": set(), "Describe song": {"style"},
            "Draft lyrics": {"title", "style", "lyrics"},
            "Rewrite a section": {"lyrics"}, "Translate lyrics": {"lyrics"},
            "Refine the style": {"style"}, "Edit score": {"abc"},
        }[body.task]
        payload = body.model_dump(exclude={"requestId", "model"})
        if body.task == "Edit score" and not body.abc.strip():
            raise ValueError("Add or load a score before requesting a score edit.")
        if (
            body.task in {"Rewrite a section", "Translate lyrics"}
            and not body.lyrics.strip()
        ):
            raise ValueError("Add lyrics before requesting this edit.")
        prompt = (
            "Create a reviewable music proposal. Return title, lyrics, style, abc, summary, ideas. "
            "Write original lyrics with [Verse], [Chorus] section labels suitable for YuE2. "
            "For Song ideas return exactly three ideas, each with title, style and description; keep other fields unchanged. "
            "For Describe song return exactly one ready-to-use song description in style, changing no other field. "
            "Use the supplied prompt as the brief: if empty invent a fresh, coherent musical direction; "
            "if partial expand it while preserving every explicit constraint, including genre and vocalist gender. "
            "Write a concise paragraph of roughly 45-100 words specifying genre, tempo or groove, instruments, "
            "vocal register, texture and delivery, mood, production and useful arrangement contrast. "
            "No title, lyrics, headings, alternatives, explanation or marketing language in this description. "
            "When an artist is named, translate the broad musical influence into concrete genre, instrumentation, "
            "rhythm, production and vocal qualities. Omit artist and song names from the resulting style prompt; "
            "do not promise an exact voice, quote existing lyrics or copy a particular composition. "
            "Do not assert what artists YuE2 was trained on or assume an artist-name token is a reliable control. "
            "For Draft lyrics return a complete short song, title and style. For rewrite/translate change only lyrics. "
            "For Refine the style change only style. For Edit score change only ABC according to the brief. "
            "Preserve source fields outside the requested task exactly. Ideas is empty outside Song ideas. "
            "No generation calls or file operations. Do not invent listening observations or extracted lyrics. "
            "If preserveMelody is true, retain exact sounding notes, durations, voices, bar boundaries, meter, and tempo; harmony-only changes may change chord symbols. "
            "USER SONG DATA:\n" + json.dumps(payload, ensure_ascii=False)
        )
        schema = Proposal.model_json_schema()
        if local:
            # Small models receive only the selected task and fields to edit.
            guidance = {
                'Song ideas': 'Create exactly three distinct original song ideas, each with title, style and description.',
                'Describe song': 'Write one ready-to-use song description in style. Use 45-100 words covering genre, groove or tempo, instruments, vocal gender/register/delivery, mood and arrangement contrast. No headings or alternatives.',
                'Draft lyrics': 'Write the complete original song requested in the brief, with a title, style description and lyrics. Include EVERY requested verse and chorus, with [Verse] and [Chorus] labels. Do not stop after the first verse.',
                'Rewrite a section': 'Rewrite only the requested lyric section. Return the complete lyrics, preserving all other sections exactly.',
                'Translate lyrics': 'Translate the supplied lyrics as requested. Preserve the section labels and return the complete translated lyrics.',
                'Refine the style': 'Refine only the style description according to the brief. Preserve explicit musical and vocal constraints.',
                'Edit score': 'Edit only the supplied ABC score according to the brief. Return the complete ABC score.',
            }[body.task]
            prompt = ('Create a reviewable music proposal for one task: '+body.task+'. '+guidance+
                ' Include a short summary of the change. Follow the brief exactly; if it is empty, invent a coherent original direction. '
                'Convert named artist influences into concrete musical traits; omit artist/song names from style. '
                'Do not copy existing lyrics, claim exact voices or invent listening observations. '
                'Return only the fields requested by the response schema. No tool calls. '
                'If preserveMelody is true, retain exact sounding notes, durations, voices, bar boundaries, meter and tempo. '
                '\nUSER SONG DATA:\n'+json.dumps(payload,ensure_ascii=False))
            fields = editable | {'summary'} | ({'ideas'} if body.task == 'Song ideas' else set())
            schema = {**schema, 'properties': {k:v for k,v in schema['properties'].items() if k in fields}, 'required':sorted(fields)}
            if body.task != 'Song ideas':schema.pop('$defs',None)
        if body.task == "Edit score":
            abc = score_tools()
            abc.parse_abc(body.abc)
            prompt = (
                "YuE2 native ABC contract: preserve the Vocal and Ins monophonic voices, section comments, "
                "and the existing header and rhythmic unit. Harmony is quoted chord symbols in Vocal, not polyphonic note brackets. "
                "Chord root is A-G with optional b/#; permitted qualities are exactly "
                + repr(abc.QUALITIES)
                + "; an optional slash bass must be a note name. No 9, 11, 13, add9, 6/9 or altered extensions. "
                "Use maj7, m7, 7, m7b5 etc for jazz color. Duration multipliers: "
                + repr(sorted(abc.DURATIONS))
                + ". Split unsupported lengths into tied notes or separate rests. Both voice groups span identical measures. "
                "No w: lyric annotations, tuplets, decorators, or invented fields.\n"
                + prompt
            )
        items, model = await provider.turn(prompt, schema, body.model)
        texts = [i["text"] for i in items if i.get("type") == "agentMessage"]
        if not texts:
            raise ValueError("The writing provider returned no proposal.")
        if local:
            returned = json.loads(texts[-1])
            if not isinstance(returned,dict) or set(schema['required']) - returned.keys():
                raise ValueError('The local model omitted required proposal fields. Original draft retained.')
            proposal = Proposal.model_validate({**{key:getattr(body,key) for key in ('title','lyrics','style','abc')},
                'ideas':[],**returned}).model_dump()
        else:
            proposal = Proposal.model_validate_json(texts[-1]).model_dump()
        if body.task != 'Song ideas':proposal['ideas'] = []
        if body.task == 'Describe song':
            proposal['style'] = proposal['style'].strip()
            if not proposal['style']:
                raise ValueError('The writing provider returned an empty description. Your draft is unchanged.')
            proposal['ideas'] = []
        for key in ("title", "lyrics", "style", "abc"):
            if key not in editable:
                proposal[key] = getattr(body, key)
        checks = None
        if body.task == "Edit score":
            abc = score_tools()
            edited = abc.parse_abc(proposal["abc"])
            if body.preserveMelody:
                checks = abc.compare(abc.parse_abc(body.abc), edited)
                if not checks["match"]:
                    raise ValueError(
                        "The score edit changed protected melody or timing. Original score retained. "
                        + json.dumps(checks)
                    )
        return {
            "proposal": proposal,
            "model": model,
            "checks": checks,
            "input": payload,
        }

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.account.close()


def routes(service):
    router = APIRouter(prefix="/api")

    async def guard(fn):
        try:
            return await fn()
        except Exception as e:
            raise HTTPException(503, str(e)[:1000]) from e

    @router.get("/providers")
    def provider_settings():
        return {"config":public_config(service.account.config),"modelPathsYaml":model_paths(service.account.config)}

    @router.post("/providers/probe")
    async def probe_providers(body: ProviderConfig):
        return await guard(lambda: service.account.inventory(body))

    @router.post("/providers/tests", status_code=202)
    async def provider_test(body: ProviderTest):
        from PIL import Image
        if body.config.provider != 'local':raise HTTPException(422,'These tests use local models only.')
        probe=Providers(service.store.root.parent)
        probe.config=with_saved_key(body.config,service.account.config)
        probe.manager=service.account.manager
        payload={'kind':body.kind,'configHash':hashlib.sha256(probe.config.model_dump_json().encode()).hexdigest()}
        async def operation():
            if body.kind=='writing':
                return await service.write(WritingInput(requestId=body.requestId,task='Describe song',
                    prompt='Original nocturnal synth-pop with a warm male baritone, analog bass and a hopeful chorus.',title='Local writing test'),account=probe)
            items,model=await probe.turn('Make one finished square album cover: an original paper collage of a sunrise reflected in a vinyl record, deep blue and warm gold, tactile cut paper, balanced composition. No text, lettering or logos.',images=True)
            raw=base64.b64decode(next(i['result'] for i in items if i.get('type')=='imageGeneration'),validate=True)
            path=service.store.root/'provider-tests'/(body.requestId+'.png');path.parent.mkdir(parents=True,exist_ok=True)
            with Image.open(io.BytesIO(raw)) as image:
                if image.width*image.height>20_000_000:raise ValueError('Test image dimensions are too large.')
                image.convert('RGB').save(path)
            return {'previewUrl':'/api/providers/tests/'+body.requestId+'/image','model':model,'provider':'comfyui'}
        return service.submit(body.requestId,'provider-'+body.kind,payload,operation)

    @router.get("/providers/tests/{job_id}/image")
    def provider_test_image(job_id: str):
        from fastapi.responses import FileResponse
        job=service.get(job_id)
        if job['kind']!='provider-image' or job['state']!='succeeded':raise HTTPException(404,'Test image is not ready.')
        return FileResponse(service.store.path_for('provider-tests/'+job_id+'.png'),media_type='image/png')

    @router.put("/providers")
    async def configure_providers(body: ProviderConfig):
        if any(not task.done() for task in service.tasks.values()):
            raise HTTPException(409,"Finish or cancel active writing and image requests before changing providers.")
        result=await guard(lambda: configure(body))
        return {"config":result,"modelPathsYaml":model_paths(service.account.config)}

    async def configure(body):
        return service.account.configure(body)

    @router.get("/openai/account")
    async def status():
        return await guard(service.account.status)

    @router.post("/openai/login")
    async def login():
        return await guard(service.account.begin_login)

    @router.post("/openai/login/cancel")
    async def cancel_login():
        await guard(service.account.cancel_login)
        return await guard(service.account.status)

    @router.post("/openai/logout")
    async def logout():
        if any(not task.done() for task in service.tasks.values()):
            raise HTTPException(
                409, "Finish or cancel active assistance requests before disconnecting."
            )
        return await guard(service.account.logout)

    @router.post("/assistance", status_code=202)
    async def writing(body: WritingInput):
        status = await guard(service.account.status)
        if not status["connected"]:
            raise HTTPException(409, "Choose and connect a writing provider in AI setup first.")
        return service.submit(
            body.requestId, "writing", body.model_dump(), lambda: service.write(body)
        )

    @router.get("/assistance/{job_id}")
    def get(job_id: str):
        return service.get(job_id)

    @router.post("/assistance/{job_id}/cancel")
    async def cancel(job_id: str):
        service.get(job_id)
        task = service.tasks.get(job_id)
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            if service.get(job_id)["state"] in {
                "queued",
                "running",
                "waiting-for-resource",
            }:
                service.save(job_id, "cancelled", error="Cancelled before execution.")
        return service.get(job_id)

    return router
