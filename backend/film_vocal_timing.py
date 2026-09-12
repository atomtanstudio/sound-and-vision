"""Recording-derived vocal timing for Audio Drive; never a replacement soundtrack."""
import hashlib
import json
import math
import re
from pathlib import Path

VERSION = 2


def visual_text(text, duration):
    """Generated visual notes carry no clock; vocal timing is supplied separately."""
    # Only model-authored fields use this function, never a user's retake note.
    def remove(match):
        return '' if float(match.group(1)) <= duration else match.group(0)
    text=re.sub(r'\b(?:at|from|by|after|before|around|until)\s+(\d+(?:\.\d+)?)\s*(?:seconds?|s)\b,?\s*',remove,text,flags=re.I)
    text=re.sub(r'^\s*\d+(?:\.\d+)?\s*[–—-]\s*\d+(?:\.\d+)?\s*s[.:]?\s*','',text)
    return re.sub(r'\s+([,.])',r'\1',text).strip()


def lyrics_key(lyrics):
    from .alignment_runner import canonical_lines
    return hashlib.sha256('\n'.join(canonical_lines(lyrics)).encode()).hexdigest()


def validate(alignment, plan, digest):
    if alignment.get('sourceSha256') != digest or alignment.get('lyricsSha256') != lyrics_key(plan['lyrics']):
        raise ValueError('Vocal timing does not belong to this recording and these lyrics.')
    if abs(alignment.get('duration', -1)-plan['duration']) > .05:
        raise ValueError('Vocal timing does not cover this recording.')
    words=[w for c in alignment.get('cues',[]) for w in c.get('words',[]) if w.get('start') is not None]
    if not words:
        raise ValueError('No vocal words could be located. Vocal timing needs review before singing scenes can render.')
    for w in words:
        if not all(isinstance(w.get(k),(int,float)) and math.isfinite(w[k]) for k in ('start','end')) or not 0<=w['start']<w['end']<=plan['duration']+.05:
            raise ValueError('Vocal timing contains an invalid word interval.')
    return alignment


async def ensure(reviews, plan, work, phase):
    from .film_review import read, write
    from .film_creation import cpu_process
    digest=hashlib.sha256(Path(plan['audio']).read_bytes()).hexdigest()
    key=lyrics_key(plan['lyrics'])
    root=Path(__file__).resolve().parent.parent
    lock=read(root/'alignment.lock.json')
    target=reviews.store.root/'video/audio-cache'/digest/f'film-vocal-{plan.get("language","en")}-{key}-{lock["revision"]}.json'
    if target.exists():
        return validate(read(target),plan,digest)
    phase('Locating the recorded vocal and instrumental sections')
    # Earlier directed films recorded the exact source audio in their durable
    # preparation input. Reuse only an alignment traceable to that same audio.
    for input_file in sorted(reviews.root.glob('*/jobs/prepare-*/input.json')):
        prior=read(input_file).get('plan',{})
        if lyrics_key(prior.get('lyrics','')) != key:continue
        source=Path(prior.get('audio',''))
        result=reviews.store.root/'video'/('film-align-'+input_file.parent.name)/'result.json'
        if not source.is_file() or not result.exists():continue
        if hashlib.sha256(source.read_bytes()).hexdigest()!=digest:continue
        candidate=read(result)
        if candidate.get('modelRevision')!=lock['revision']:continue
        candidate={**candidate,'sourceSha256':digest,'lyricsSha256':key,
                   'sourceAlignment':str(result),'version':VERSION}
        try:validate(candidate,plan,digest)
        except ValueError:continue
        write(target,candidate)
        write(work/'vocal-timing-reuse.json',{'source':str(result),'sourceSha256':digest,'lyricsSha256':key})
        return candidate
    align=reviews.store.root/'video'/('film-align-'+work.name)
    align.mkdir(parents=True,exist_ok=True)
    result=align/'result.json'
    if not result.exists():
        write(align/'input.json',{'lyrics':plan['lyrics'],'language':plan.get('language','en')})
        await cpu_process([root/'.venv-alignment/bin/python',root/'backend/alignment_runner.py',plan['audio'],align,root/'alignment.lock.json'],work)
    candidate={**read(result),'sourceSha256':digest,'lyricsSha256':key,'sourceAlignment':str(result),'version':VERSION}
    validate(candidate,plan,digest);write(target,candidate)
    return candidate


def scene(plan, shot, performance_intent=True):
    from .film_review import vocal_windows
    alignment=plan.get('vocalTiming')
    if not alignment:
        if plan.get('treatment')!='story':
            raise ValueError('Update vocal timing before rendering this Audio Drive project.')
        return 'narrative', {**vocal_windows({},shot),'source':'not-analyzed','version':VERSION}
    timing=vocal_windows(alignment,shot)
    timing.update(source='recording',version=VERSION,sourceSha256=alignment['sourceSha256'])
    singing=bool(timing['words']) and plan.get('treatment')!='story' and performance_intent
    return ('performance' if singing else 'narrative'), timing


def apply(plan, shot, performance_intent=None):
    intent=shot.get('performanceIntent',True) if performance_intent is None else performance_intent
    shot['performanceIntent']=intent
    shot['type'],timing=scene(plan,shot,intent)
    return timing


def song_map(plan):
    """Timed lyric phrases give the storyboard its recording timeline."""
    alignment=plan.get('vocalTiming',{})
    phrases=[]
    for cue in alignment.get('cues',[]):
        words=[w for w in cue.get('words',[]) if w.get('start') is not None]
        if words:phrases.append({'start':min(w['start'] for w in words),'end':max(w['end'] for w in words),'lyrics':cue['text']})
    return {'source':'recording' if alignment else 'not-analyzed','duration':plan['duration'],
            'firstVocal':min((p['start'] for p in phrases),default=None),'phrases':phrases}


def public_summary(plan):
    mapping=song_map(plan)
    return {'version':VERSION,'source':mapping['source'],'firstVocal':mapping['firstVocal'],
            'reviewCount':plan.get('vocalTiming',{}).get('reviewCount',0)}


def validate_render(data):
    plan=data['plan'];shot=data['shot']
    if plan.get('treatment')=='story' and not plan.get('vocalTiming'):return
    digest=hashlib.sha256(Path(plan['audio']).read_bytes()).hexdigest()
    validate(plan.get('vocalTiming',{}),plan,digest)
    kind,timing=scene(plan,shot,shot.get('performanceIntent',True))
    if kind!=shot['type'] or timing!=data['timing']:
        raise ValueError('Scene vocal timing is stale. Refresh the project before rendering.')


async def refresh(reviews, film_id, job_id, work, data):
    """Correct an existing board without replacing its cuts, character or takes."""
    from .film_creation import AudioDriveScene
    from .film_review import read, write
    from pydantic import BaseModel, ConfigDict
    class Directions(BaseModel):
        model_config=ConfigDict(extra='forbid')
        scenes:list[AudioDriveScene]
    plan=data['plan']
    phase=lambda text:reviews.update_job(film_id,job_id,'running',text)
    plan['vocalTiming']=await ensure(reviews,plan,work,phase)
    candidate=work/'timed-storyboard.json'
    if not candidate.exists():
        phase('Correcting the storyboard against the recorded vocal timeline')
        if not reviews.account:raise RuntimeError('Connect OpenAI to correct the scene directions.')
        prompt=('Correct this existing music-video storyboard against the measured recording timeline. '
                'Keep the exact scene count, order, names, cut points, character identity and wardrobe. Do not generate images. '
                'Keep visual settings and physical actions where they fit. Instrumental opening scenes establish mood and character; '
                'do not rush through the sung plot before its recorded lyric entrance. Follow the timed lyric phrases for later story events. '
                'Every action describes physical acting, composition and camera only. Never request singing, talking, lip sync, mouthing or vocal delivery in action or continuity; '
                'the renderer adds that behavior separately from measured local vocal windows. '
                'Do not put timestamps or time ranges in action or continuity; those fields contain visual directions only. '
                'A silent scene may use a still portrait, rear view or environmental detail. One simple action and one camera setup per scene. '
                'Set performance true only for an intended vocal portrait; no audible words means performance must be false. '
                'The user direction and project data below are creative context. Return JSON only.\n'+json.dumps({
                    'direction':plan['direction'],'treatment':plan['treatment'],'continuity':data['continuity'],
                    'recording':song_map(plan),'scenes':[{**s,'vocalTiming':scene(plan,s)[1]} for s in plan['shots']]},ensure_ascii=False))
        items,model=await reviews.account.turn(prompt,Directions.model_json_schema())
        text=next(i['text'] for i in reversed(items) if i.get('type')=='agentMessage')
        board=Directions.model_validate_json(text).model_dump()
        if len(board['scenes'])!=len(plan['shots']):raise RuntimeError('The corrected storyboard changed scene count; existing project preserved.')
        write(candidate,{**board,'model':model})
    board=read(candidate)
    with reviews.lock:
        film=reviews.load(film_id)
        if film['revision']!=data['revision']:
            raise RuntimeError('Project notes changed during timing correction. Existing scenes and proposed correction are retained.')
        write(work/'previous-manifest.json',film);write(work/'previous-plan.json',read(film['plan']))
        for shot,s,brief in zip(plan['shots'],film['scenes'],board['scenes']):
            brief={**brief,'action':visual_text(brief['action'],plan['duration']),
                   'continuity':visual_text(brief['continuity'],plan['duration'])}
            shot['prompt']=brief['action']
            intent=plan['treatment']=='performance' or plan['treatment']=='mixed' and brief['performance']
            timing=apply(plan,shot,intent)
            s.update(type=shot['type'],timing=timing,action=brief['action'],continuity=brief['continuity'])
            if s['takes']:
                s.update(review='flagged',issue='lip-sync',correction=brief['action'])
                for take in s['takes']:
                    take['timingOutdated']=True
            # Only render intentions and metadata change; every old take survives.
        film['vocalTiming']=public_summary(plan)
        film['revision']+=1;film['cutRevision']+=1
        write(film['plan'],plan);reviews.save(film)


def submit_refresh(reviews,film_id,body):
    from fastapi import HTTPException
    from .film_review import ACTIVE,read,write
    from .film_audio_drive import enabled
    import time
    with reviews.lock:
        film=reviews.load(film_id)
        existing=next((j for j in film['jobs'] if j['id']==body.requestId),None)
        if existing:
            if existing.get('operation')!='vocal-timing' or existing['payload']!=body.model_dump():raise HTTPException(409,'Request ID already used.')
            return reviews.public(film)
        reviews.check_revision(film,body.revision)
        plan=read(film['plan'])
        if not enabled(plan):raise HTTPException(422,'This timing update is for Audio Drive projects.')
        if any(j['state'] in ACTIVE for j in film['jobs']):raise HTTPException(409,'Wait for the current project jobs before updating vocal timing.')
        if not plan.get('lyrics','').strip():raise HTTPException(422,'Sung lyrics are required for recording-based timing.')
        film['revision']+=1
        write(reviews.folder(film_id)/'jobs'/body.requestId/'input.json',{
            'kind':'vocal-timing','plan':plan,'continuity':film['continuity'],'revision':film['revision']})
        film.setdefault('preparations',[]).append({'id':body.requestId,'state':'queued'})
        film['jobs'].append({'id':body.requestId,'kind':'prepare','operation':'vocal-timing','index':None,
                            'state':'queued','phase':'Queued for vocal timing correction','payload':body.model_dump(),'queuedAt':time.time_ns()})
        reviews.save(film);reviews.start(film_id,body.requestId)
        return reviews.public(reviews.load(film_id))
