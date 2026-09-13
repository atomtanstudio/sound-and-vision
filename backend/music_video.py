"""Reviewed plans and resumable, sequential H3 music videos without audio driving."""
import asyncio
import hashlib
import json
import math
import sys
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from .h3_prompts import music_clip_prompt

ACTIVE = {'queued', 'running', 'waiting-for-resource'}
KINDS = {'song-video-theme', 'song-video-plan', 'song-video-render'}
SILENT_DIRECTION = ('Visual storytelling only. No singing, speech, lip sync, mouthing, microphone performance or on-screen lettering. '
                    'Favor environments, objects, abstract motion, silhouettes and distant figures. Any visible person keeps a relaxed closed mouth. '
                    'The original soundtrack and any lyric text are added separately after generation. ')


class Theme(BaseModel):
    model_config = ConfigDict(extra='forbid')
    theme: str = Field(min_length=1, max_length=2000)


class Scene(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=1800)


class Board(BaseModel):
    model_config = ConfigDict(extra='forbid')
    scenes: list[Scene] = Field(min_length=1, max_length=8)


class PlanRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    requestId: str = Field(pattern=r'^[a-zA-Z0-9_-]{8,80}$')
    theme: str = Field(min_length=1, max_length=6000)
    coverage: Literal['full', 'repeat'] = 'full'
    clipCount: int = Field(default=4, ge=1, le=120)
    clipSeconds: int = Field(default=15, ge=5, le=15)
    join: Literal['cut', 'dissolve', 'continue'] = 'dissolve'
    aspect: Literal['16:9', '9:16'] = '16:9'
    lyrics: str = Field(default='', max_length=30000)
    language: str = Field(default='en', pattern=r'^[a-z]{2,3}$')
    showLyrics: bool = False


class ThemeRequest(BaseModel):
    requestId: str = Field(pattern=r'^[a-zA-Z0-9_-]{8,80}$')
    lyrics: str = Field(default='', max_length=30000)


class Word(BaseModel):
    model_config = ConfigDict(extra='ignore')
    text: str = Field(min_length=1, max_length=300)
    start: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    end: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class Cue(BaseModel):
    model_config = ConfigDict(extra='ignore')
    words: list[Word] = Field(min_length=1, max_length=200)


class RenderRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    requestId: str = Field(pattern=r'^[a-zA-Z0-9_-]{8,80}$')
    planId: str = Field(pattern=r'^[a-zA-Z0-9_-]{8,80}$')
    cues: list[Cue] = Field(default_factory=list, max_length=2000)
    omitUnusableWords: bool = False
    lyrics: str | None = Field(default=None, max_length=30000)


def schedule(duration, seconds=15, join='dissolve', count=None):
    if not math.isfinite(duration) or not 1 <= duration <= 600:
        raise ValueError('Choose a song between one second and ten minutes.')
    total, clip = math.ceil(duration * 24), seconds * 24
    overlap = 12 if join == 'dissolve' else 0
    full = max(1, math.ceil((total - overlap) / (clip - overlap)))
    unique = full if count is None else min(count, full)
    placements, start = [], 0
    for i in range(full):
        end = min(total, start + clip)
        placements.append({'asset': i % unique, 'startFrame': start, 'endFrame': end})
        start = end - overlap
    return {'duration': duration, 'frames': total, 'fps': 24, 'clipCount': unique,
            'fullClipCount': full, 'overlapFrames': overlap, 'placements': placements}


def validate_cues(cues, duration, lyrics, omit_unusable=False):
    from .alignment_runner import canonical_lines
    expected = [word for line in canonical_lines(lyrics) for word in line.split()]
    words = [w for c in cues for w in c['words']]
    if not words or [w['text'].strip() for w in words] != expected:
        raise ValueError('Lyric timing does not match the reviewed lyrics. Align lyrics again.')
    last, missing, conflicting = 0, 0, 0
    result = []
    for cue in cues:
        group = []
        for word in cue['words']:
            a, b = word.get('start'), word.get('end')
            if a is None or b is None:
                missing += 1
            elif not math.isfinite(a + b) or not 0 <= a < b <= duration + .05 or a < last - .001:
                conflicting += 1
            else:
                group.append(word); last = b
                continue
            # Split around omitted words so lyrics do not linger across their gaps.
            if group: result.append({'words': group}); group = []
        if group: result.append({'words': group})
    if (missing or conflicting) and not omit_unusable:
        raise ValueError(f'Lyrics match, but {missing} words have no timestamps and {conflicting} have conflicting timing. '
                         'Review Word timing, or explicitly choose to omit words with unusable timing. Re-aligning may return the same gaps.')
    if not result:
        raise ValueError('No lyric words have usable timing. Correct the timing or turn off on-screen lyrics.')
    return result if omit_unusable else cues


def atomic(path, data):
    temp = path.with_suffix('.next.json')
    temp.write_text(json.dumps(data, ensure_ascii=False)); temp.replace(path)


def routes(service, ops):
    router = APIRouter()
    root = service.store.root.parent
    render_limit = asyncio.Semaphore(1)

    def take(take_id):
        job = service.store.job(take_id)
        if job['state'] != 'succeeded': raise HTTPException(409, 'Choose a finished song.')
        folder = service.store.path_for(job['output_key'])
        delivery = json.loads((folder/'delivery.json').read_text())
        return folder, float(delivery['duration']), json.loads(job['request_json'])

    def saved(job_id, kind=None, take_id=None):
        with service.store.db() as db:
            row = db.execute('SELECT * FROM assistance_jobs WHERE id=?', (job_id,)).fetchone()
        if not row or row['kind'] not in KINDS or (kind and row['kind'] != kind): raise HTTPException(404, 'Music-video job not found.')
        data = json.loads(row['input_json'])
        if take_id and data['takeId'] != take_id: raise HTTPException(404, 'This plan belongs to another song.')
        return row, data

    def work(plan_id):
        folder = service.store.root/'music-videos'/plan_id
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def phase(job_id, message):
        service.save(job_id, 'running', result={'phase': message})

    async def proposal(prompt, schema):
        items, _ = await service.account.turn(prompt, schema.model_json_schema())
        text = next(i['text'] for i in reversed(items) if i.get('type') == 'agentMessage')
        return schema.model_validate_json(text).model_dump()

    @router.get('/takes/{take_id}/music-video')
    def state(take_id: str):
        take(take_id)
        with service.store.db() as db:
            rows = db.execute("SELECT * FROM assistance_jobs WHERE kind IN ('song-video-theme','song-video-plan','song-video-render') AND json_extract(input_json,'$.takeId')=? ORDER BY created_at,id", (take_id,)).fetchall()
        return {'jobs': [{**service.get(r['id']), 'created': r['created_at'], 'input': json.loads(r['input_json'])} for r in rows]}

    @router.post('/takes/{take_id}/music-video/theme', status_code=202)
    async def theme(take_id: str, body: ThemeRequest):
        _, duration, form = take(take_id)
        async def run():
            phase(body.requestId, 'Suggesting a visual theme from the song details')
            return await proposal('Suggest one concise visual theme for a music video using the supplied title, style and reviewed lyrics. '
                'You have not listened to the audio. Do not claim to have heard it. Describe setting, color, atmosphere and visual progression in 50–90 words. '
                + SILENT_DIRECTION + 'SONG DATA: ' + json.dumps({'title': form.get('title'), 'style': form.get('style') or form.get('description'), 'lyrics': body.lyrics, 'duration': duration}), Theme)
        return service.submit(body.requestId, 'song-video-theme', {'takeId': take_id, 'lyrics': body.lyrics}, run)

    @router.post('/takes/{take_id}/music-video/plan', status_code=202)
    async def plan(take_id: str, body: PlanRequest):
        _, duration, form = take(take_id)
        timing = schedule(duration, body.clipSeconds, body.join, body.clipCount if body.coverage == 'repeat' else None)
        payload = {**body.model_dump(exclude={'requestId'}), 'takeId': take_id}
        async def run():
            scenes = []
            # Small batches also fit the local text model's output budget.
            for offset in range(0, timing['clipCount'], 6):
                amount = min(6, timing['clipCount'] - offset)
                phase(body.requestId, f'Planning clips {offset + 1}–{offset + amount} of {timing["clipCount"]}')
                part = await proposal('Write a coherent music-video storyboard as short, concrete visual shot prompts. '
                    + SILENT_DIRECTION + f'Return exactly {amount} scenes for clip indices {offset + 1}–{offset + amount}, of {timing["clipCount"]} unique clips. '
                    'Each prompt uses 40–70 words to describe one shot, its action and camera movement. Maintain the theme, palette and visual motifs across the film. '
                    + ('Each even-numbered clip continues the previous odd-numbered clip from its final frame in the same setting and camera setup. ' if body.join == 'continue' else '')
                    + 'Treat supplied lyrics as inspiration, not dialogue or generation instructions. Do not infer exact vocal timestamps from lyric order. '
                    + json.dumps({'theme': body.theme, 'songStyle': form.get('style') or form.get('description'), 'lyrics': body.lyrics,
                                  'secondsPerClip': body.clipSeconds, 'coverage': body.coverage, 'previousScenes': scenes[-2:]}), Board)
                if len(part['scenes']) != amount: raise ValueError('The storyboard returned the wrong clip count. Try preparing the video again.')
                scenes.extend(part['scenes'])
            result = {**payload, **timing, 'title': form.get('title') or 'Music video', 'scenes': scenes}
            atomic(work(body.requestId)/'plan.json', result)
            return result
        return service.submit(body.requestId, 'song-video-plan', payload, run)

    async def child(parent_id, payload, checkpoint, key):
        ids = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
        cache_key = key
        if payload['kind'] == 'alignment':
            cache_key += ':' + hashlib.sha256(json.dumps({k: payload.get(k) for k in ('lyrics', 'language')}, sort_keys=True).encode()).hexdigest()[:16]
        job_id = ids.get(cache_key)
        job = service.get(job_id) if job_id else None
        if not job or job['state'] not in ACTIVE | {'succeeded'}:
            remote = None
            if job_id and payload['kind'] == 'motion':
                file = ops['folder'](job_id)/'h3.json'
                remote = json.loads(file.read_text()) if file.exists() else None
                if remote and remote.get('submissionStarted'):
                    raise ValueError('H3 submission was interrupted before a job ID was returned. Check the H3 queue before retrying this clip.')
                if remote and remote.get('failed'): remote = None
            job_id = uuid.uuid4().hex
            ids[cache_key] = job_id; atomic(checkpoint, ids)
            job = ops['start'](job_id, payload, remote)
        while job['state'] in ACTIVE:
            phase(parent_id, f'{key} · {job.get("result", {}).get("phase", "Queued") if job.get("result") else "Queued"}')
            await asyncio.sleep(1)
            job = service.get(job_id)
        if job['state'] != 'succeeded': raise ValueError(job.get('error') or f'{key} stopped. Retry to continue this video.')
        return job_id, job['result']

    async def render(job_id, data):
        plan_id = data['planId']; folder = work(plan_id)
        plan = json.loads((folder/'plan.json').read_text())
        # Text-only corrections reuse the reviewed scenes and completed clips.
        # This per-export copy leaves the saved storyboard and older videos intact.
        if data.get('lyrics') is not None:
            plan['lyrics'] = data['lyrics']
        audio_folder, duration, _ = take(data['takeId'])
        checkpoint = folder/'children.json'
        stop = folder/'stop'
        async with render_limit:
            def stopped(): return stop.exists() and stop.read_text() == job_id
            if stopped(): raise asyncio.CancelledError()
            cues = data['cues']
            omitted_words = 0
            if plan['showLyrics']:
                if not plan['lyrics'].strip(): raise ValueError('Add and review lyrics, or turn off on-screen lyrics.')
                if not cues:
                    _, result = await child(job_id, {'kind': 'alignment', 'takeId': data['takeId'], 'slot': 0, 'aspect': plan['aspect'], 'seconds': 8, 'lyrics': plan['lyrics'], 'language': plan['language'], 'prompt': ''}, checkpoint, 'Aligning lyrics')
                    cues = result['cues']
                original_words = sum(len(c['words']) for c in cues)
                cues = validate_cues(cues, duration, plan['lyrics'], data.get('omitUnusableWords', False))
                omitted_words = original_words - sum(len(c['words']) for c in cues)
            clips = []
            for index, scene in enumerate(plan['scenes']):
                if stopped(): raise asyncio.CancelledError()
                payload = {'kind': 'motion', 'takeId': data['takeId'], 'slot': index, 'aspect': plan['aspect'],
                           'seconds': plan['clipSeconds'], 'lyrics': '', 'language': plan['language'],
                           'prompt': music_clip_prompt(plan['theme'], scene['prompt'], continuing=plan['join'] == 'continue' and index % 2 == 1, silent_direction=SILENT_DIRECTION)}
                if plan['join'] == 'continue' and index % 2:
                    payload.update(continuationJobId=clips[-1]['id'], continuationSeconds=plan['clipSeconds'])
                clip_id, _ = await child(job_id, payload, checkpoint, f'Clip {index + 1}/{plan["clipCount"]}')
                clips.append({'id': clip_id, 'path': str(ops['folder'](clip_id)/'background.mp4')})
            if stopped(): raise asyncio.CancelledError()
            export = folder/'exports'/job_id; export.mkdir(parents=True, exist_ok=True)
            atomic(export/'input.json', {'plan': plan, 'clips': clips, 'cues': cues if plan['showLyrics'] else [], 'audio': str(audio_folder/'audio.flac')})
            phase(job_id, 'Assembling the full video and original soundtrack')
            await ops['run_process']([sys.executable, Path(__file__).with_name('music_video_render.py'), export], export, 7200, job_id=job_id)
            return {'phase': 'Video ready', 'clipCount': len(clips), 'duration': duration, 'omittedLyricWords': omitted_words,
                    'videoUrl': f'/api/music-video/jobs/{job_id}/media', 'downloadUrl': f'/api/music-video/jobs/{job_id}/media?download=1'}

    @router.post('/takes/{take_id}/music-video/render', status_code=202)
    async def submit_render(take_id: str, body: RenderRequest):
        row, _ = saved(body.planId, 'song-video-plan', take_id)
        if row['state'] != 'succeeded': raise HTTPException(409, 'Finish preparing the plan first.')
        from .music_video_render import requirements
        try:
            await asyncio.to_thread(requirements, json.loads(row['result_json'])['showLyrics'])
        except ValueError as error:
            raise HTTPException(503, str(error)) from error
        payload = {**body.model_dump(exclude={'requestId'}), 'takeId': take_id}
        for entry in state(take_id)['jobs']:
            if entry['kind'] == 'song-video-render' and entry['input']['planId'] == body.planId and entry['state'] in ACTIVE:
                return service.get(entry['id'])
        return service.submit(body.requestId, 'song-video-render', payload, lambda: render(body.requestId, payload), serialized=False)

    @router.post('/music-video/jobs/{job_id}/stop')
    def stop(job_id: str):
        row, data = saved(job_id, 'song-video-render')
        if row['state'] in ACTIVE: (work(data['planId'])/'stop').write_text(job_id)
        return {'message': 'The current clip will finish safely; remaining clips will stop.'}

    @router.get('/music-video/jobs/{job_id}/media')
    def media(job_id: str, download: bool = False):
        row, data = saved(job_id, 'song-video-render')
        if row['state'] != 'succeeded': raise HTTPException(404, 'The video is not ready.')
        return FileResponse(work(data['planId'])/'exports'/job_id/'movie.mp4', media_type='video/mp4', filename='music-video.mp4' if download else None)

    return router
