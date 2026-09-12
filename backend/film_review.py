"""Versioned scene review. Originals, timing and submitted context are immutable.

The API has one process, as required by the GPU manager. Atomic manifests and an
in-process lock serialize edits; provider intent on disk prevents duplicate H3
submissions after restarts. Scene generation is never an automatic retry loop.
"""
import asyncio
import copy
import hashlib
import json
import re
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from .film_credits import credits_for

ACTIVE = {"queued", "running", "waiting-for-resource"}


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    temp.replace(path)


class Edit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    correction: str = Field(default="", max_length=4000)
    continuity: str = Field(default="", max_length=6000)
    issue: Literal["none", "lip-sync", "identity", "objects", "motion", "other"] = "none"


class Retry(Edit):
    requestId: str = Field(pattern=r"^[a-zA-Z0-9_-]{8,80}$")
    baseTakeId: str | None = Field(default=None, max_length=80)
    method: Literal['smart', 'source-edit', 'timing', 'frame-regenerate', 'regenerate'] = 'source-edit'
    shiftFrames: int = Field(default=0, ge=-24, le=24)
    repairStartFrame: int | None = Field(default=None, ge=0)
    repairEndFrame: int | None = Field(default=None, ge=1)


class Revision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)


class Export(Revision):
    requestId: str = Field(pattern=r"^[a-zA-Z0-9_-]{8,80}$")


class SceneCut(Revision):
    endSeconds: float = Field(gt=0, le=900, allow_inf_nan=False)


class Credits(BaseModel):
    model_config=ConfigDict(extra='forbid')
    enabled: bool = True
    artist: str = Field(default='',max_length=160)
    songTitle: str = Field(default='',max_length=160)
    recordLabel: str = Field(default='',max_length=160)


class CreditEdit(Revision):
    credits: Credits


class SceneBrief(BaseModel):
    model_config = ConfigDict(extra='forbid')
    cast: str = Field(max_length=700)
    location: str = Field(max_length=400)
    startState: str = Field(max_length=700)
    singleAction: str = Field(max_length=900)
    endState: str = Field(max_length=700)
    objectContinuity: str = Field(max_length=900)


def vocal_windows(alignment, shot):
    """Keep real acoustic word positions, including words crossing a scene cut."""
    words = []
    for cue in alignment.get('cues', []):
        for word in cue['words']:
            start, end = word.get('start'), word.get('end')
            if start is not None and end is not None and end > shot['start'] and start < shot['end']:
                words.append({**word, 'start': round(max(0, start-shot['start']), 3),
                              'end': round(min(shot['end']-shot['start'], end-shot['start']), 3)})
    spans = []
    for word in words:
        if spans and word['start']-spans[-1]['end'] < .35:
            spans[-1]['end'] = max(spans[-1]['end'], word['end'])
        else:
            spans.append({'start':word['start'], 'end':word['end']})
    return {'words':words, 'spans':spans, 'uncertainWords':sum(bool(w.get('review')) for w in words),
            'leadingRest':round(words[0]['start'],3) if words else round(shot['end']-shot['start'],3)}


def context_hash(film,index):
    context={'continuity':film['continuity'],'scenes':[
        {'index':s['index'],'continuity':s['continuity'],
         'selected':s['selected'] if s['index']!=index else None,
         'correction':s['correction'] if s['index']==index else None}
        for s in film['scenes']]}
    return hashlib.sha256(json.dumps(context,sort_keys=True).encode()).hexdigest()


class FilmReviews:
    def __init__(self, store, manager, account=None, assistance=None):
        self.store, self.manager = store, manager
        self.account = account
        self.assistance = assistance
        self.root = store.root / 'film-reviews'
        self.root.mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.tasks = {}
        self.closing = False
        self.render_limit = asyncio.Semaphore(1)
        self.export_limit = asyncio.Semaphore(1)

    def folder(self, film_id):
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', film_id):
            raise HTTPException(404, 'Film not found')
        return self.root / film_id

    def load(self, film_id, include_deleted=False):
        file = self.folder(film_id) / 'manifest.json'
        if not file.exists():
            raise HTTPException(404, 'Film not found')
        film = read(file)
        if film.get('deletedAt') and not include_deleted:
            raise HTTPException(404, 'Video project is in Trash')
        return film

    def save(self, film):
        write(self.folder(film['id']) / 'manifest.json', film)

    def discover(self, include_deleted=False):
        with self.lock:
            for path in sorted((self.store.root / 'films').glob('**/film-plan.json')):
                plan = read(path)
                shots = plan.get('shots', [])
                if not shots or not any(s.get('type') == 'performance' for s in shots):
                    continue
                if plan.get('fps') != 24 or plan.get('output') != [1920,1080] or any(s.get('index')!=i for i,s in enumerate(shots)):
                    continue
                if not all((path.parent/'clips'/s['runId']/'background.mp4').is_file() for s in shots):
                    continue
                film_id = path.parent.name + '-' + hashlib.sha256(str(path.relative_to(self.store.root)).encode()).hexdigest()[:10]
                if (self.folder(film_id)/'manifest.json').exists():
                    continue
                if any(s['endFrame'] != shots[i+1]['startFrame'] for i,s in enumerate(shots[:-1])):
                    continue
                if shots[0]['startFrame'] != 0:
                    continue
                alignment_path = path.parent/'alignment-sections.json'
                alignment = read(alignment_path) if alignment_path.exists() else {}
                notes_path = path.parent/'review-notes.json'
                notes = read(notes_path) if notes_path.exists() else {}
                scenes = []
                for shot in shots:
                    n = notes.get('scenes', {}).get(str(shot['index']), {})
                    identity_refs=[]
                    for ref in n.get('identityReferences',[])[:3]:
                        reference=(path.parent/'references'/ref['file']).resolve()
                        if reference.is_relative_to((path.parent/'references').resolve()) and reference.is_file():
                            identity_refs.append({'source':str(reference),'role':ref['role']})
                    scenes.append({'index':shot['index'], 'name':shot['name'], 'type':shot.get('type','narrative'),
                        'start':shot['startFrame']/plan['fps'], 'end':shot['endFrame']/plan['fps'],
                        'startFrame':shot['startFrame'], 'endFrame':shot['endFrame'],
                        'timing':vocal_windows(alignment, shot), 'correction':n.get('correction',''),
                        'continuity':n.get('continuity',''), 'issue':n.get('issue','none'),
                        'review':'flagged' if n.get('issue') else 'unreviewed', 'selected':'original',
                        'identityReferences':identity_refs,
                        'takes':[{'id':'original','state':'ready','label':'Original','source':str(path.parent/'clips'/shot['runId']/'background.mp4')} ]})
                receipts = [f for f in path.parent.glob('*.receipt.json') if f.with_suffix('').with_suffix('.mp4').is_file()]
                original = next((f.with_suffix('').with_suffix('.mp4') for f in receipts if read(f).get('title') == plan['title']), None)
                self.save({'id':film_id,'revision':1,'cutRevision':1,'title':plan['title'],'artist':plan['artist'],
                    'takeId':plan['takeId'],'duration':plan['duration'],'fps':plan['fps'],'plan':str(path),
                    'continuity':notes.get('continuity','Keep the same cast, wardrobe, locations and object ownership throughout the film.'),
                    'scenes':scenes,'jobs':[], 'exports':([{'id':'original','state':'ready','revision':1,'source':str(original)}] if original else [])})
            films = [read(p) for p in sorted(self.root.glob('*/manifest.json'))]
            return [self.public(f) for f in films if include_deleted or not f.get('deletedAt')]

    def trash(self, film_id, revision, deleted=True):
        with self.lock:
            film = self.load(film_id, include_deleted=True)
            if bool(film.get('deletedAt')) == deleted:return self.public(film)
            self.check_revision(film, revision)
            if any(j['state'] in ACTIVE for j in film['jobs']):
                raise HTTPException(409, 'Finish or cancel this project’s pending jobs before deleting it.')
            film['deletedAt'] = int(time.time()*1000) if deleted else None
            film['revision'] += 1
            self.save(film)
            return self.public(film)

    def check_revision(self, film, revision):
        if film['revision'] != revision:
            raise HTTPException(409, 'The film changed. Refresh it before applying this edit.')

    def scene(self, film, index):
        return next((s for s in film['scenes'] if s['index']==index), None) or self.missing()

    def missing(self):
        raise HTTPException(404, 'Scene or take not found')

    def public(self, film):
        result = copy.deepcopy(film)
        for job in result.get('jobs',[]):
            if job['state']=='failed' and not (job.get('error') or '').strip():
                job['error']='This earlier run stopped without recording an error detail. Saved preparation work is retained.'
                detail=self.folder(film['id'])/'jobs'/job['id']/'run-error.json'
                if detail.exists():
                    recorded=read(detail).get('error')
                    if isinstance(recorded,str) and recorded.strip():job['error']=recorded.strip()[:1500]
        result['credits']=credits_for(film)
        result.pop('plan',None)
        base = '/api/films/'+film['id']
        result['cast'] = [{k:v for k,v in c.items() if k != 'source'} |
                          {'sheetUrl':f"{base}/characters/{c['id']}/sheet"} for c in film.get('cast',[])]
        for scene in result['scenes']:
            if scene.get('storyboardFrame'):
                scene['storyboardFrame']={k:v for k,v in scene['storyboardFrame'].items() if k!='source'}
                scene['storyboardUrl']=f"{base}/scenes/{scene['index']}/storyboard?frame={scene['storyboardFrame']['sha256']}"
            for take in scene['takes']:
                take.pop('source',None)
                take['mediaUrl'] = f"{base}/scenes/{scene['index']}/takes/{take['id']}/media"
                take['posterUrl'] = f"{base}/scenes/{scene['index']}/takes/{take['id']}/poster"
                take['contextUrl'] = f"{base}/scenes/{scene['index']}/takes/{take['id']}/context?cut={film['cutRevision']}"
                take['contextChanged'] = bool(take.get('contextHash') and take['contextHash']!=context_hash(film,scene['index']))
            scene['referenceUrl'] = f"{base}/scenes/{scene['index']}/reference"
            scene['identityReferences']=[{'role':r['role'],'url':f"{base}/scenes/{scene['index']}/identity/{i}"}
                                         for i,r in enumerate(scene.get('identityReferences',[]))]
        for item in result['exports']:
            item.pop('source',None)
            item['mediaUrl'] = f"{base}/exports/{item['id']}"
        queue = self.pending(scene=True)
        positions = {}
        waiting = 0
        for _, film_id, job in queue:
            if job['state'] == 'queued':
                waiting += 1
                positions[(film_id, job['id'])] = waiting
            else:
                positions[(film_id, job['id'])] = 0
        for job in result['jobs']:
            job.pop('payload',None)
            job['queuePosition'] = positions.get((film['id'], job['id']))
        return result

    def pending(self, scene=True):
        """Durable global FIFO; resumed in-flight work goes before waiting work."""
        jobs = []
        for file in sorted(self.root.glob('*/manifest.json')):
            film = read(file)
            if film.get('deletedAt'):continue
            for order, job in enumerate(film['jobs']):
                if job['state'] in ACTIVE and (job['index'] is not None) == scene:
                    key = (job['state'] == 'queued', job.get('queuedAt', 0), film['id'], order)
                    jobs.append((key, film['id'], job))
        return sorted(jobs, key=lambda item: item[0])

    def edit(self, film_id, index, body):
        with self.lock:
            film = self.load(film_id)
            self.check_revision(film,body.revision)
            if index is None:
                film['continuity'] = body.continuity
            else:
                scene = self.scene(film,index)
                scene.update(body.model_dump(exclude={'revision'}))
                scene['review'] = 'flagged' if body.issue != 'none' else 'unreviewed'
            film['revision'] += 1
            self.save(film)
            return self.public(film)

    def submit(self, film_id, body, index=None):
        with self.lock:
            film = self.load(film_id)
            payload = body.model_dump()
            old = next((j for j in film['jobs'] if j['id']==body.requestId),None)
            if old:
                if old['payload'] != payload or old.get('index') != index:
                    raise HTTPException(409,'Request ID already belongs to different inputs.')
                return self.public(film)
            self.check_revision(film, body.revision)
            if any(j['state'] in ACTIVE and j.get('index')==index for j in film['jobs']):
                raise HTTPException(409,'This scene already has a render in progress.' if index is not None else 'An export is already running.')
            plan = read(film['plan'])
            from .film_audio_drive import enabled
            hybrid = enabled(plan)
            if index is not None and any(j['state'] in ACTIVE and j.get('kind')=='prepare' for j in film['jobs']):
                raise HTTPException(409,'Wait for character sheets and vocal timing preparation to finish.')
            if index is not None and ((hybrid and body.method != 'regenerate') or (not hybrid and body.method == 'regenerate')):
                raise HTTPException(422, 'Audio Drive projects use Regenerate scene with the original character reference.')
            plan['credits']=credits_for(film)
            job_id = body.requestId
            work = self.folder(film_id)/'jobs'/job_id
            snapshot = {'kind':'scene' if index is not None else 'export','plan':plan,'revision':film['revision'],
                        'cutRevision':film['cutRevision'],
                        'continuity':film['continuity'],'sourceRoot':str(Path(film['plan']).parent),
                        'story':[{'index':s['index'],'name':s['name'],'type':s['type'],'continuity':s['continuity'],
                                  'selected':s['selected'],'source':next((t['source'] for t in s['takes'] if t['id']==s['selected']),None)}
                                 for s in film['scenes']]}
            if index is not None:
                scene = self.scene(film,index)
                base = next((t for t in scene['takes'] if t['id'] == (body.baseTakeId or scene['selected']) and t['state'] == 'ready'), None)
                if not base:
                    raise HTTPException(422, 'Choose a completed source take for this repair.')
                region = None
                if body.method == 'frame-regenerate':
                    start, end = body.repairStartFrame, body.repairEndFrame
                    if start is None or end is None or not 0 <= start < end <= scene['endFrame']-scene['startFrame'] or end-start < 2*film['fps']:
                        raise HTTPException(422, 'Choose a repair range of at least two seconds inside this scene.')
                    region = {'startFrame':start, 'endFrame':end}
                elif body.repairStartFrame is not None or body.repairEndFrame is not None:
                    raise HTTPException(422, 'A repair range requires Replace motion from a frame.')
                if body.method == 'timing' and (not body.shiftFrames or abs(body.shiftFrames) >= scene['endFrame']-scene['startFrame']):
                    raise HTTPException(422, 'Choose a nonzero timing adjustment shorter than this scene.')
                if body.method != 'timing' and body.shiftFrames:
                    raise HTTPException(422, 'Timing shifts require the timing repair method.')
                if body.method != 'timing' and not body.correction.strip():
                    raise HTTPException(422,'Describe what needs to change in this scene.')
                scene.update(body.model_dump(include={'correction','continuity','issue'}))
                scene['review'] = 'flagged'
                film['revision'] += 1
                snapshot['revision'] = film['revision']
                snapshot.update({'shot':plan['shots'][index], 'timing':scene['timing'],
                                 'repairVersion':2, 'method':body.method, 'shiftFrames':body.shiftFrames,
                                 'repairRange':region,
                                 'baseTake':copy.deepcopy(base),
                                 'identityReferences':scene.get('identityReferences',[]),
                                 'correction':body.correction,'sceneContinuity':body.continuity,
                                 'runId':'sv-scene-'+uuid.uuid4().hex, 'seed':int(uuid.uuid4().hex[:7],16)})
                if hybrid:
                    from .film_vocal_timing import scene as timed_scene
                    timed_scene(plan,plan['shots'][index],plan['shots'][index].get('performanceIntent',True))
                    snapshot.pop('repairVersion', None)
                    snapshot.pop('baseTake', None)
                    snapshot.update(method='generate', identityReferences=scene.get('identityReferences',[]), story=[])
                    write(work/'context-brief.json', {'provider':'saved-scene-notes',
                          'brief':{'singleAction':body.correction,'objectContinuity':body.continuity}})
                if body.method not in {'timing','reuse-shot'}:
                    from .film_cast import check_references
                    try:check_references(snapshot)
                    except ValueError as error:raise HTTPException(409,str(error)) from error
                scene['takes'].append({'id':job_id,'label':f"Take {len(scene['takes'])+1}",
                                       'state':'queued','revision':film['revision'],
                                       'baseTakeId':base['id'], 'method':body.method, 'shiftFrames':body.shiftFrames,
                                       'repairRange':region,
                                       'contextHash':context_hash(film,index),
                                       'source':str(work/'background.mp4'), 'correction':body.correction})
            else:
                if not film['scenes'] or any(not any(t['id']==s['selected'] and t['state']=='ready' for t in s['takes']) for s in film['scenes']):
                    raise HTTPException(409,'Render every scene before exporting the film.')
                film['exports'].append({'id':job_id,'state':'queued','revision':film['cutRevision'],
                                        'source':str(work/'film.mp4')})
            write(work/'input.json',snapshot)
            film['jobs'].append({'id':job_id,'index':index,'state':'queued','payload':payload,'phase':'Queued', 'queuedAt':time.time_ns()})
            self.save(film)
            self.start(film_id,job_id)
            return self.public(self.load(film_id))

    def edit_credits(self,film_id,body):
        with self.lock:
            film=self.load(film_id);self.check_revision(film,body.revision)
            credits=body.credits.model_dump()
            if film.get('workflow') == 'vrgdg-h3-turbo' and credits['enabled']:
                raise HTTPException(422,'Audio Drive test exports do not apply titles or credits.')
            if credits!=credits_for(film):
                film.update(credits=credits,revision=film['revision']+1,cutRevision=film['cutRevision']+1)
                self.save(film)
            return self.public(film)

    def accept(self, film_id,index,take_id,revision):
        with self.lock:
            film=self.load(film_id);self.check_revision(film,revision)
            scene=self.scene(film,index)
            take=next((t for t in scene['takes'] if t['id']==take_id),None)
            if not take or take['state']!='ready':
                raise HTTPException(409,'Only a completed take can be used.')
            if scene['selected'] != take_id:film['cutRevision'] += 1
            scene['selected']=take_id;scene['review']='approved'
            film['revision']+=1;self.save(film)
            return self.public(film)

    def update_job(self, film_id,job_id,state,phase,error=None):
        with self.lock:
            film=self.load(film_id);job=next(j for j in film['jobs'] if j['id']==job_id)
            job.update(state=state,phase=phase,error=error)
            item=(next(t for t in self.scene(film,job['index'])['takes'] if t['id']==job_id)
                  if job['index'] is not None else next(e for e in film.get('preparations',[]) if e['id']==job_id)
                  if job.get('kind')=='prepare' else next(e for e in film['exports'] if e['id']==job_id))
            item['state']=state;item['error']=error
            result=self.folder(film_id)/'jobs'/job_id/'checks.json'
            if state=='ready' and result.exists():item['checks']=read(result)
            if state=='ready' and job.get('kind')=='generate':
                scene=self.scene(film,job['index'])
                if not scene['selected']:
                    scene['selected']=job_id
                    if item.get('checks',{}).get('aiReview',{}).get('result')=='needs-review':scene['review']='flagged'
                    film['cutRevision']+=1
                    film['revision']+=1
            self.save(film)

    def start(self,film_id,job_id):
        self.dispatch()

    def dispatch(self):
        if self.closing:return
        with self.lock:
            for scene in (True, False):
                queue = self.pending(scene)
                if any((film_id, job['id']) in self.tasks for _, film_id, job in queue):continue
                if queue:
                    _, film_id, job = queue[0]
                    phase = 'Preparing storyboard' if job.get('kind')=='prepare' else 'Preparing scene' if scene else 'Preparing export'
                    self.update_job(film_id, job['id'], 'running', phase)
                    self.tasks[(film_id, job['id'])] = asyncio.create_task(self.run(film_id, job['id']))

    def cancel(self, film_id, job_id):
        with self.lock:
            film = self.load(film_id)
            job = next((j for j in film['jobs'] if j['id'] == job_id), None)
            if not job:self.missing()
            if job['state'] == 'cancelled':return self.public(film)
            if job['state'] != 'queued' or (film_id, job_id) in self.tasks:
                raise HTTPException(409, 'This job has already started. Its take will be retained for review.')
            self.update_job(film_id, job_id, 'cancelled', 'Removed from queue')
            self.dispatch()
            return self.public(self.load(film_id))

    async def run(self,film_id,job_id):
        work=self.folder(film_id)/'jobs'/job_id
        acquired=False;process=None
        try:
            data=read(work/'input.json');scene=data['kind']=='scene'
            smart=scene and data.get('method')=='smart'
            async with self.render_limit if scene else self.export_limit:
                if data['kind']=='prepare':
                    from .film_creation import prepare
                    await prepare(self,film_id,job_id,work,data)
                    self.update_job(film_id,job_id,'ready','Storyboard ready')
                    return
                if data['kind']=='direct-film':
                    from .film_director import prepare
                    await prepare(self,film_id,job_id,work,data)
                    self.update_job(film_id,job_id,'ready','Character sheets and illustrated storyboard ready')
                    return
                if data['kind']=='storyboard-frame':
                    from .film_director import revise_frame
                    await revise_frame(self,film_id,job_id,work,data)
                    self.update_job(film_id,job_id,'ready','Storyboard frame updated')
                    return
                if data['kind']=='storyboard-rerender':
                    from .film_director import rerender_frame
                    await rerender_frame(self,film_id,job_id,work,data)
                    self.update_job(film_id,job_id,'ready','Storyboard frame re-rendered')
                    return
                if data['kind']=='vocal-timing':
                    from .film_vocal_timing import refresh
                    await refresh(self,film_id,job_id,work,data)
                    self.update_job(film_id,job_id,'ready','Vocal timing and storyboard updated')
                    return
                if data['kind']=='character-sheets':
                    from .film_cast import upgrade
                    await upgrade(self,film_id,job_id,work,data)
                    self.update_job(film_id,job_id,'ready','Character sheets ready · Singularity first pass')
                    return
                if smart:
                    from .film_intelligence import plan_repair
                    data=await plan_repair(self,film_id,job_id,work,data)
                if scene and data.get('method') not in {'timing','reuse-shot'}:
                    brief=work/'context-brief.json'
                    if not brief.exists() and data.get('method') != 'frame-regenerate':
                        self.update_job(film_id,job_id,'running','Reconciling this scene with the film continuity')
                        try:
                            if not self.account:raise RuntimeError('OpenAI account unavailable')
                            prompt=('Compile the supplied music-video context into one tightly scoped scene brief. '
                                'Return the six requested JSON fields, no tools. The full story is context only, never a montage or instructions to perform other scenes. '
                                'Include ONLY the people, location and objects actually required in the selected scene. '
                                'The user correction and scene continuity override obsolete actions and contradictions in the original shot prompt. '
                                'Keep one simple physical action per existing source shot. Preserve existing source cuts and their order; never demand one uninterrupted take when sourceCuts contains a cut. Never add an entrance, handoff, new character, object or location. '
                                'Preserve the selected scene cast exactly, including each distinct band member and their instrument. '
                                'Vocalist identity and all mouth movement are supplied by measured timing separately; describe physical action only. '
                                'State object ownership and counts positively and explicitly, resolving them against prior/later events. '
                                'No additional camera cuts, no future plot events, no repeated lyric text. Do not invent visual or audio review results. '
                                'The actual source video determines the composition and location at each point; older storyboard notes cannot move or replace its shots. '
                                'SUPPLIED CREATIVE DATA:\n'+json.dumps({**{k:v for k,v in data.items() if k in {'shot','story','continuity','sceneContinuity','correction'}},
                                    'sourceCuts':data.get('baseTake',{}).get('checks',{}).get('possibleInternalCuts',[])},ensure_ascii=False))
                            items,model=await self.account.turn(prompt,SceneBrief.model_json_schema())
                            text=next(i['text'] for i in reversed(items) if i.get('type')=='agentMessage')
                            write(brief,{'brief':SceneBrief.model_validate_json(text).model_dump(),'provider':'openai','model':model})
                        except Exception as error:
                            # Local H3 remains usable without an account; never dump the
                            # whole storyboard into its generation prompt as a fallback.
                            write(brief,{'brief':{'singleAction':data['correction'],'objectContinuity':data['sceneContinuity']},
                                         'provider':'saved-scene-notes','warning':str(error)[:400]})
                    while not self.manager.gpu_lock.acquire(blocking=False):
                        self.update_job(film_id,job_id,'waiting-for-resource','Waiting for the current music or video job')
                        await asyncio.sleep(3)
                    acquired=True
                self.update_job(film_id,job_id,'running','Preparing scene' if scene else 'Assembling selected takes')
                with (work/'worker.log').open('ab') as output:
                    process=await asyncio.create_subprocess_exec(sys.executable,'-m','backend.film_worker',str(work),
                        stdout=output,stderr=output)
                    while process.returncode is None:
                        await asyncio.sleep(2)
                        status=work/'phase.json'
                        if status.exists():
                            self.update_job(film_id,job_id,'running',read(status)['phase'])
                    if process.returncode:
                        failure=work/'failure.json'
                        raise RuntimeError(read(failure)['error'] if failure.exists() else 'Media worker failed; original take retained.')
                if scene:
                    # Visual review does not need the GPU lock.
                    if acquired:self.manager.gpu_lock.release();acquired=False
                    from .film_intelligence import review_repair, review_voice
                    from .film_audio_drive import enabled
                    if not enabled(data['plan']):
                        if smart:await review_repair(self,film_id,job_id,work,data)
                        else:await review_voice(self,film_id,job_id,work,data)
                self.update_job(film_id,job_id,'ready','Ready for review' if scene else 'Export ready')
        except asyncio.CancelledError:
            # Only the local worker is terminated; H3's run remains recoverable.
            raise
        except Exception as error:
            with self.lock:
                failed = next(j for j in self.load(film_id)['jobs'] if j['id']==job_id)
                stage = failed['phase']
            detail = str(error).strip() or ('The operation timed out.' if isinstance(error,TimeoutError)
                                          else f'{type(error).__name__}: no further detail was supplied.')
            message = f'{stage}: {detail}'[:1500]
            write(work/'run-error.json',{'phase':stage,'error':message,'errorType':type(error).__name__,
                                       'causeType':type(error.__cause__).__name__ if error.__cause__ else None,
                                       'failedAt':time.time()})
            self.update_job(film_id,job_id,'failed','Needs attention',message)
        finally:
            if process and process.returncode is None:
                process.terminate()
                try:await asyncio.wait_for(process.wait(),8)
                except asyncio.TimeoutError:
                    process.kill();await process.wait()
            if acquired:self.manager.gpu_lock.release()
            self.tasks.pop((film_id,job_id),None)
            self.dispatch()

    def recover(self):
        self.dispatch()

    async def close(self):
        self.closing = True
        tasks=list(self.tasks.values())
        for task in tasks:task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)

    def media(self,film_id,index,take_id,poster=False):
        with self.lock:
            film=self.load(film_id);scene=self.scene(film,index)
            take=next((t for t in scene['takes'] if t['id']==take_id),None)
            if not take or take['state']!='ready':self.missing()
            source=Path(take['source']);plan=read(film['plan'])
        # Only trusted manifest paths are used, never a path supplied by the API.
        from .film_worker import prepare_preview
        work=self.folder(film_id)/'previews'/str(index)/take_id
        path=prepare_preview(source,Path(plan['audio']),{**scene,'fps':plan['fps']},work,poster)
        return FileResponse(path,media_type='image/jpeg' if poster else 'video/mp4')


def routes(reviews):
    router=APIRouter(prefix='/api/films')
    from .film_creation import CreateFilm, create, generate
    from .film_director import ConceptRequest,FrameEdit,FrameRerender,submit_concept,submit_frame,frame_prompt,submit_rerender
    @router.post('/concepts',status_code=202)
    async def concept(body:ConceptRequest):return submit_concept(reviews,body)
    @router.post('/{film_id}/scenes/{index}/storyboard',status_code=202)
    async def update_storyboard(film_id:str,index:int,body:FrameEdit):return submit_frame(reviews,film_id,index,body)
    @router.get('/{film_id}/scenes/{index}/storyboard/prompt')
    def storyboard_prompt(film_id:str,index:int):return frame_prompt(reviews,film_id,index)
    @router.post('/{film_id}/scenes/{index}/storyboard/rerender',status_code=202)
    async def rerender_storyboard(film_id:str,index:int,body:FrameRerender):return submit_rerender(reviews,film_id,index,body)
    @router.get('/{film_id}/scenes/{index}/storyboard')
    def storyboard(film_id:str,index:int):
        scene=reviews.scene(reviews.load(film_id),index)
        if not scene.get('storyboardFrame'):reviews.missing()
        return FileResponse(scene['storyboardFrame']['source'],media_type='image/png')
    @router.post('/credits/preview')
    def credit_preview(body:Credits):
        from .film_credits import preview
        return preview(body.model_dump())
    @router.patch('/{film_id}/credits')
    def credit_edit(film_id:str,body:CreditEdit):return reviews.edit_credits(film_id,body)
    @router.post('',status_code=202)
    async def create_film(body:CreateFilm):return create(reviews,body)
    @router.post('/{film_id}/scenes/{index}/generate',status_code=202)
    async def generate_scene(film_id:str,index:int,body:Export):return generate(reviews,film_id,body,index)
    @router.post('/{film_id}/scenes/{index}/rerender',status_code=202)
    async def rerender_scene(film_id:str,index:int,body:Export):return generate(reviews,film_id,body,index,rerender=True)
    @router.post('/{film_id}/vocal-timing',status_code=202)
    async def update_vocal_timing(film_id:str,body:Export):
        from .film_vocal_timing import submit_refresh
        return submit_refresh(reviews,film_id,body)
    @router.post('/{film_id}/character-sheets',status_code=202)
    async def character_sheets(film_id:str,body:Export):
        from .film_cast import submit
        return submit(reviews,film_id,body)
    @router.get('/{film_id}/characters/{character_id}/sheet')
    def character_sheet(film_id:str,character_id:str):
        film=reviews.load(film_id)
        character=next((c for c in film.get('cast',[]) if c['id']==character_id),None)
        if not character:reviews.missing()
        return FileResponse(character['source'],media_type='image/png')
    @router.patch('/{film_id}/scenes/{index}/cut')
    def scene_cut(film_id:str,index:int,body:SceneCut):
        from .film_audio_drive import retime
        return retime(reviews,film_id,index,body)
    @router.get('')
    def films(include_deleted:bool=False):return {'films':reviews.discover(include_deleted)}
    @router.delete('/{film_id}')
    def trash(film_id:str,body:Revision):return reviews.trash(film_id,body.revision)
    @router.post('/{film_id}/restore')
    def restore(film_id:str,body:Revision):return reviews.trash(film_id,body.revision,False)
    @router.get('/{film_id}')
    def film(film_id:str):
        with reviews.lock:return reviews.public(reviews.load(film_id))
    @router.patch('/{film_id}/context')
    def context(film_id:str,body:Edit):return reviews.edit(film_id,None,body)
    @router.patch('/{film_id}/scenes/{index}')
    def edit(film_id:str,index:int,body:Edit):return reviews.edit(film_id,index,body)
    @router.post('/{film_id}/scenes/{index}/retry',status_code=202)
    async def retry(film_id:str,index:int,body:Retry):return reviews.submit(film_id,body,index)
    @router.post('/{film_id}/scenes/{index}/takes/{take_id}/accept')
    def accept(film_id:str,index:int,take_id:str,body:Revision):return reviews.accept(film_id,index,take_id,body.revision)
    @router.post('/{film_id}/exports',status_code=202)
    async def export(film_id:str,body:Export):return reviews.submit(film_id,body)
    @router.post('/{film_id}/jobs/{job_id}/recover',status_code=202)
    async def recover(film_id:str,job_id:str):
        with reviews.lock:
            film=reviews.load(film_id)
            job=next((j for j in film['jobs'] if j['id']==job_id),None)
            if not job:reviews.missing()
            if job['state']=='failed':
                if any(j['id'] != job_id and j.get('index') == job.get('index') and j['state'] in ACTIVE for j in film['jobs']):
                    raise HTTPException(409, 'This scene already has a render in progress.')
                job['queuedAt'] = time.time_ns()
                reviews.save(film)
                reviews.update_job(film_id,job_id,'queued','Recovering the same run')
                reviews.start(film_id,job_id)
            return reviews.public(reviews.load(film_id))
    @router.post('/{film_id}/jobs/{job_id}/cancel')
    async def cancel(film_id:str,job_id:str):return reviews.cancel(film_id,job_id)
    @router.get('/{film_id}/scenes/{index}/takes/{take_id}/media')
    def media(film_id:str,index:int,take_id:str):return reviews.media(film_id,index,take_id)
    @router.get('/{film_id}/scenes/{index}/takes/{take_id}/poster')
    def poster(film_id:str,index:int,take_id:str,edge:Literal['start','end']|None=None):return reviews.media(film_id,index,take_id,edge or True)
    @router.get('/{film_id}/scenes/{index}/takes/{take_id}/context')
    def context_preview(film_id:str,index:int,take_id:str):
        from .film_worker import prepare_context
        with reviews.lock:
            film=reviews.load(film_id);scene=reviews.scene(film,index)
            take=next((t for t in scene['takes'] if t['id']==take_id and t['state']=='ready'),None)
            if not take:reviews.missing()
            plan=read(film['plan'])
        target=prepare_context(film,scene,take,plan,reviews.folder(film_id)/'context'/str(index)/take_id)
        return FileResponse(target,media_type='video/mp4')
    @router.get('/{film_id}/scenes/{index}/reference')
    def reference(film_id:str,index:int):
        plan=read(reviews.load(film_id)['plan'])
        shot=next((s for s in plan['shots'] if s['index']==index),None)
        if not shot or not shot.get('references'):reviews.missing()
        return FileResponse(shot['references'][0],media_type='image/png')
    @router.get('/{film_id}/scenes/{index}/identity/{ref_index}')
    def identity(film_id:str,index:int,ref_index:int):
        scene=reviews.scene(reviews.load(film_id),index)
        refs=scene.get('identityReferences',[])
        if ref_index<0 or ref_index>=len(refs):reviews.missing()
        return FileResponse(refs[ref_index]['source'])
    @router.get('/{film_id}/exports/{export_id}')
    def exported(film_id:str,export_id:str):
        film=reviews.load(film_id)
        item=next((e for e in film['exports'] if e['id']==export_id and e['state']=='ready'),None)
        if not item:reviews.missing()
        return FileResponse(item['source'],media_type='video/mp4',filename=film['title']+'.mp4',content_disposition_type='inline')
    return router
