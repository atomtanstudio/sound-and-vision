"""Short-film contracts using synthetic images and in-memory account responses."""
import asyncio
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from PIL import Image

from . import film_director as director, film_creation, film_vocal_timing
from .film_review import Export,Retry,SceneCut,read,write
from .film_worker import generation_prompt,repair_prompt
from .film_audio_drive import retime
from .test_film_creation import creation,body
from .test_api import client,payload

CONCEPT = dict(
    premise='An estranged repairer restores an old radio so he can reconnect with his sister over their childhood song.',
    protagonist='Rowan, an adult radio repairer, and his sister Mira.',
    motivation='Rowan wants to repair the relationship he damaged by refusing to listen; restoring the radio gives him a reason to reach out.',
    relationships='Mira is his sister, established in the opening beside the broken radio. She returns after he chooses to ask for help.',
    beginning='Rowan and Mira face the silent radio in the workshop. A family photograph establishes their shared past.',
    conflict='The radio stays silent because Rowan insists on repairing it alone. Mira steps away after his refusal of help.',
    turningPoint='Rowan sets down his tools and invites Mira to guide him with the handwritten instructions she kept.',
    resolution='They restore the radio together. Rowan listens beside Mira, resolving his refusal to accept her help.',
    visualMotif='A dark radio dial gradually warms with light as communication returns.',
    continuityRules='Rowan always has gray shoulder-length hair and a full beard. Mira is always his sister. One radio remains on the same workshop bench.',
)
CAST = [
    dict(id='rowan',name='Rowan',role='repairer and lead vocalist',appearance='Adult with shoulder-length gray hair, full gray beard, angular face, brown workshop apron and blue shirt.'),
    dict(id='mira',name='Mira',role='Rowan’s sister',appearance='Adult with curly black hair to her shoulders, round face, green cardigan and black trousers.'),
]
LOCATION = dict(id='workshop',name='Radio workshop',appearance='A small wood-lined workshop with one radio on a central wooden bench, a window on the left and warm desk lamp.')


def storyboard(performance=False):
    scenes=[]
    for i,(beat,end) in enumerate(zip(['beginning','conflict','resolution'],[7.,14.,21.025])):
        scenes.append(dict(name=['The broken radio','The refusal','Listening together'][i],endSeconds=end,
            beat='performance' if performance else beat,purpose='Reveal the character’s changing willingness to accept help.',
            cause='This choice follows the previous refusal and changes how the siblings approach the radio.',
            characterReason='The siblings belong here because their shared radio and relationship are established in the opening.',
            action=['Both siblings look at the radio on the bench.','Rowan sets down the repair tool and looks toward Mira.','They stand together beside the illuminated radio.'][i],
            framing='A steady medium-wide shot shows the bench and the exact assigned cast.',locationId='workshop',
            startState='One radio remains on the workbench with its dial dark.',endState='The same radio stays on the bench as the character finishes the stated action.',
            continuity='Same workshop, same siblings, one radio and consistent clothing.',
            castIds=['rowan','mira'] if i!=1 else ['rowan'],vocalistId='rowan' if i==0 else None))
    return dict(continuity=CONCEPT['continuityRules'],cast=CAST,locations=[LOCATION],scenes=scenes)


def account_fixture(board=None,fail_audit=False):
    board=board or storyboard(); calls=[]
    image=io.BytesIO();Image.new('RGB',(96,64),'#6f8078').save(image,format='PNG')
    async def turn(prompt,schema=None,images=False,**kwargs):
        calls.append(dict(prompt=prompt,images=images,**kwargs))
        if images:return [{'type':'imageGeneration','result':base64.b64encode(image.getvalue()).decode()}],'fixture'
        fields=schema.get('properties',{})
        if 'premise' in fields:result=CONCEPT
        elif 'coherent' in fields:
            result=dict(coherent=not fail_audit,motivatedCharacters=True,earnedEnding=True,stableCastAndRelationships=True,
                        issues=['The ending does not follow the opening.'] if fail_audit else [])
        else:result=board
        return [{'type':'agentMessage','text':json.dumps(result)}],'fixture'
    return SimpleNamespace(turn=turn),calls


def prepared(creation,monkeypatch,concept=CONCEPT,fail_audit=False,lyrics=True,treatment='mixed'):
    if not lyrics:
        original=creation.store.job
        creation.store.job=lambda key:{**original(key),'request_json':json.dumps({'lyrics':'','description':'Instrumental guitar piece'})}
    film=film_creation.create(creation,body(workflow=director.WORKFLOW,treatment=treatment,concept=concept,renderTier='standard'))
    job=film['jobs'][0]['id'];work=creation.folder(film['id'])/'jobs'/job
    plan=read(work/'input.json')['plan']
    async def ensure(*args):
        return dict(version=2,sourceSha256=hashlib.sha256(Path(plan['audio']).read_bytes()).hexdigest(),
            lyricsSha256=film_vocal_timing.lyrics_key(plan['lyrics']),duration=plan['duration'],
            cues=[{'text':'A real lyric','words':[{'text':'A','start':1,'end':2}]}])
    monkeypatch.setattr(film_vocal_timing,'ensure',ensure)
    creation.account,calls=account_fixture(storyboard(treatment=='performance'),fail_audit)
    if not fail_audit:
        asyncio.run(director.prepare(creation,film['id'],job,work,read(work/'input.json')))
        creation.update_job(film['id'],job,'ready','Ready')
    return film['id'],work,calls


@pytest.mark.parametrize('idea',['','A story about repairing a relationship through music.'])
def test_magic_wand_uses_the_actual_lyrics_and_user_idea_without_images(idea):
    account,calls=account_fixture()
    result=asyncio.run(director.develop(account,{'lyrics':'The radio fell silent','style':'Acoustic folk'},idea,'mixed',{'ending':'Hopeful'}))
    assert result['concept']==CONCEPT and len(calls)==1 and calls[0]['images'] is False
    assert 'The radio fell silent' in calls[0]['prompt'] and 'Hopeful' in calls[0]['prompt']
    if idea:assert idea in calls[0]['prompt']
    assert 'an earned resolution' in calls[0]['prompt']


@pytest.mark.parametrize('concept',[CONCEPT,None])
def test_complete_storyboard_uses_sheets_for_images_and_images_for_animation(creation,monkeypatch,concept):
    key,work,calls=prepared(creation,monkeypatch,concept=concept)
    film=creation.load(key);plan=read(film['plan'])
    assert film['concept']==CONCEPT and film['storyboardVersion']==1
    assert len(film['cast'])==2 and len(film['scenes'])==3
    image_calls=[c for c in calls if c['images']]
    writing_calls=[c for c in calls if not c['images'] and 'Develop the entire film' not in c['prompt']]
    assert writing_calls and all(c['timeout_seconds']==director.STORYBOARD_TIMEOUT for c in writing_calls)
    assert len(image_calls)==5 # Two character sheets, then three real frame requests.
    assert all(c.get('reference_images') for c in image_calls[2:])
    assert len(image_calls[2]['reference_images'])==1
    assert len(image_calls[3]['reference_images'])==2 # Same location gains its earlier image reference.
    for shot in plan['shots']:
        assert shot['references'][0]==shot['storyboardFrame']['source']
        assert shot['references'][1:]==[c['source'] for c in shot['characterReferences']]
    request=Export(revision=film['revision'],requestId='animate-storyboard')
    film_creation.generate(creation,key,request,0)
    snapshot=read(creation.folder(key)/'jobs/animate-storyboard/input.json')
    assert snapshot['frameAnchor'] and snapshot['storyboardAnchor']
    text=generation_prompt(snapshot)
    assert '[keyframe completion + audio reference]' in text
    assert '<Picture 2>' in text and '<Picture 3>' in text
    assert 'opening frame' in text and '<Subject 1> (S1)' in text
    for field in ('framing','startState','endState','purpose'):
        assert snapshot['shot']['story'][field] in text
    # Recovery must not repeat any account/image calls or erase a queued take.
    count=len(calls)
    asyncio.run(director.prepare(creation,key,film['jobs'][0]['id'],work,read(work/'input.json')))
    assert len(calls)==count and creation.load(key)['scenes'][0]['takes']
    public=creation.public(creation.load(key))
    assert public['scenes'][0]['storyboardUrl'].startswith('/api/films/')
    assert 'source' not in public['scenes'][0]['storyboardFrame']


def test_pure_instrumental_performance_does_not_invent_vocals_or_a_plot(creation,monkeypatch):
    key,_,_=prepared(creation,monkeypatch,lyrics=False,treatment='performance')
    film=creation.load(key);plan=read(film['plan'])
    assert all(s['type']=='narrative' and s['vocalistId'] is None for s in film['scenes'])
    assert all(s['story']['beat']=='performance' for s in plan['shots'])
    assert film['vocalTiming']['source']=='not-analyzed'


def test_bad_causality_stops_before_character_or_storyboard_image_generation(creation,monkeypatch):
    key,work,calls=prepared(creation,monkeypatch,fail_audit=True)
    job=creation.load(key)['jobs'][0]['id']
    with pytest.raises(ValueError,match='Story review'):
        asyncio.run(director.prepare(creation,key,job,work,read(work/'input.json')))
    assert not any(c['images'] for c in calls)
    assert (work/'storyboard-revision.json').exists() # Exactly one script-only correction.
    assert len([c for c in calls if 'Review this complete concept' in c['prompt']])==2


def test_missing_resolution_unknown_locations_and_random_cast_are_rejected():
    plan={'duration':21.025,'treatment':'mixed'}
    for change in ['ending','location','cast','act-order']:
        board=copy.deepcopy(storyboard())
        if change=='ending':board['scenes'][-1]['beat']='conflict'
        elif change=='location':board['scenes'][1]['locationId']='unexplained-room'
        elif change=='cast':board['scenes'][1]['castIds']=['unexplained-companion']
        else:board['scenes'].insert(2,{**board['scenes'][0],'endSeconds':18})
        with pytest.raises(ValueError):director.validate_board(board,plan)


def test_story_format_cannot_add_on_camera_singing():
    board=copy.deepcopy(storyboard());plan={'duration':21.025,'treatment':'story'}
    with pytest.raises(ValueError,match='off camera'):director.validate_board(board,plan)
    for shot in board['scenes']:shot['vocalistId']=None
    assert len(director.validate_board(board,plan))==3


def test_scene_image_edit_is_reviewed_and_preserves_other_frames_and_cuts(creation,monkeypatch):
    key,_,calls=prepared(creation,monkeypatch)
    film=creation.load(key);previous=read(film['plan'])
    body=director.FrameEdit(revision=film['revision'],requestId='revise-story-frame',
        action='Rowan carefully sets the repair tool beside the old radio.',
        framing='Close medium shot, keeping the radio and Rowan’s hands clearly visible.',continuity='One radio stays on the same workshop bench.')
    director.submit_frame(creation,key,1,body);director.submit_frame(creation,key,1,body)
    work=creation.folder(key)/'jobs'/body.requestId
    with pytest.raises(HTTPException):film_creation.generate(creation,key,Export(revision=creation.load(key)['revision'],requestId='wait-for-image'),0)
    asyncio.run(director.revise_frame(creation,key,body.requestId,work,read(work/'input.json')))
    updated=read(creation.load(key)['plan'])
    assert updated['shots'][0]==previous['shots'][0] and updated['shots'][2]==previous['shots'][2]
    assert updated['shots'][1]['story']['action']==body.action
    assert [(s['startFrame'],s['endFrame']) for s in updated['shots']]==[(s['startFrame'],s['endFrame']) for s in previous['shots']]
    assert Path(previous['shots'][1]['storyboardFrame']['source']) in calls[-1]['reference_images']
    count=len(calls)
    asyncio.run(director.revise_frame(creation,key,body.requestId,work,read(work/'input.json')))
    assert len(calls)==count


def test_shared_repair_tools_keep_storyboard_and_character_picture_roles(creation,monkeypatch):
    key,_,_=prepared(creation,monkeypatch)
    film=creation.load(key)
    film_creation.generate(creation,key,Export(revision=film['revision'],requestId='original-scene'),0)
    creation.update_job(key,'original-scene','ready','Ready');film=creation.load(key)
    request=Retry(revision=film['revision'],requestId='source-edit-new-film',method='source-edit',correction='Keep the same gray hair and beard.',continuity='Same siblings and the same radio.')
    creation.submit(key,request,0)
    data=read(creation.folder(key)/'jobs/source-edit-new-film/input.json')
    prompt=repair_prompt(data)
    assert '[video editing + audio reference]' in prompt
    assert '<Picture 1> is the original storyboard' in prompt and '<Picture 2>' in prompt


def test_unified_film_cut_editor_preserves_storyboard_images(creation,monkeypatch):
    key,_,_=prepared(creation,monkeypatch)
    film=creation.load(key);plan=read(film['plan'])
    updated=retime(creation,key,0,SceneCut(revision=film['revision'],endSeconds=8))
    assert updated['scenes'][0]['end']==updated['scenes'][1]['start']==8
    assert updated['scenes'][0]['story']['endSeconds']==8
    assert [s['storyboardFrame'] for s in read(creation.load(key)['plan'])['shots']]==[s['storyboardFrame'] for s in plan['shots']]


def test_concept_endpoint_uses_existing_durable_writing_queue(client,monkeypatch):
    monkeypatch.setenv('SOUND_VISION_ENABLE_MUSIC_VIDEO','1')
    c,store,_=client
    take=c.post('/api/generations',json=payload(1)).json()['tracks'][0]
    with store.db() as db:db.execute("UPDATE generation_jobs SET state='succeeded' WHERE take_id=?",(take['id'],))
    account,calls=account_fixture()
    c.app.state.films.account=account
    request=dict(requestId='concept-api-once',takeId=take['id'],direction='',treatment='mixed',creative={'cast':'Two siblings'})
    first=c.post('/api/films/concepts',json=request)
    assert first.status_code==202
    second=c.post('/api/films/concepts',json=request)
    assert second.status_code==202 and second.json()['id']==first.json()['id']
    import time
    for _ in range(30):
        job=c.get('/api/assistance/concept-api-once').json()
        if job['state']=='succeeded':break
        time.sleep(.01)
    assert job['result']['concept']==CONCEPT and len(calls)==1 and not calls[0]['images']
    assert c.post('/api/films/concepts',json={**request,'direction':'A different idea'}).status_code==409


def test_slow_storyboard_keeps_one_request_running_and_reports_elapsed_progress(monkeypatch):
    async def run():
        released=asyncio.Event();calls=[];progress=[];waits=[]
        async def turn(prompt,schema,**options):
            calls.append(options)
            await released.wait()
            return [{'type':'agentMessage','text':json.dumps(CONCEPT)}],'fixture'
        real_wait=asyncio.wait
        async def wait(tasks,timeout=None):
            waits.append(timeout)
            if len(waits)==1:
                await asyncio.sleep(0)
                return set(),tasks
            released.set()
            return await real_wait(tasks)
        monkeypatch.setattr(asyncio,'wait',wait)
        result,_=await director.structured(SimpleNamespace(turn=turn),'Synthetic story',director.FilmConcept,
            timeout_seconds=600,phase=progress.append,label='Writing the complete storyboard')
        assert result==CONCEPT and calls==[{'timeout_seconds':600}]
        assert waits==[15,15] and len(progress)==1
        assert progress[0].startswith('Writing the complete storyboard · ') and progress[0].endswith(' elapsed')
    asyncio.run(run())


def test_preparation_records_the_failed_stage_even_when_exception_text_is_empty(creation,monkeypatch):
    film=film_creation.create(creation,body(workflow=director.WORKFLOW,concept=CONCEPT))
    job=film['jobs'][0]['id'];work=creation.folder(film['id'])/'jobs'/job
    async def fail(reviews,key,job_id,work,data):
        reviews.update_job(key,job_id,'running','Writing the complete storyboard')
        raise TimeoutError()
    monkeypatch.setattr(director,'prepare',fail)
    asyncio.run(creation.run(film['id'],job))
    failed=creation.public(creation.load(film['id']))['jobs'][0]
    assert failed['state']=='failed'
    assert failed['error']=='Writing the complete storyboard: The operation timed out.'
    detail=read(work/'run-error.json')
    assert detail['phase']=='Writing the complete storyboard' and detail['errorType']=='TimeoutError'
    assert not creation.tasks and not creation.load(film['id'])['scenes']


def test_older_empty_failure_is_visible_without_rewriting_or_restarting_it(creation):
    film=film_creation.create(creation,body(workflow=director.WORKFLOW,concept=CONCEPT))
    creation.update_job(film['id'],film['jobs'][0]['id'],'failed','Needs attention','')
    before=creation.load(film['id'])
    result=creation.public(before)
    assert 'without recording an error detail' in result['jobs'][0]['error']
    assert result['jobs'][0]['state']=='failed'
    assert creation.load(film['id'])==before and not creation.tasks
    detail=creation.folder(film['id'])/'jobs'/film['jobs'][0]['id']/'run-error.json'
    write(detail,{'error':'Writing the complete storyboard exceeded the earlier 180-second limit.'})
    assert '180-second' in creation.public(before)['jobs'][0]['error']
    assert creation.load(film['id'])==before and not creation.tasks


@pytest.mark.parametrize('changed',[False,True])
def test_frame_rerender_uses_saved_prompt_and_refs_without_rewriting_story_or_video(creation,monkeypatch,changed):
    key,_,calls=prepared(creation,monkeypatch)
    film=creation.load(key);plan=read(film['plan']);scene=film['scenes'][1]
    scene['takes']=[{'id':'existing-video','state':'ready','source':'kept-video.mp4'}]
    scene['selected']='existing-video';creation.save(film)
    prompt,refs=director.saved_frame_request(plan['shots'][1])
    description=director.frame_prompt(creation,key,1)
    assert description=={'prompt':prompt,'referenceCount':len(refs),'revision':film['revision']}
    edited=prompt+'\nShow exactly two anatomically correct arms, one left and one right.' if changed else None
    body=director.FrameRerender(requestId='rerender-one-frame',revision=film['revision'],prompt=edited)
    old_frame=Path(scene['storyboardFrame']['source']);old_bytes=old_frame.read_bytes();before_calls=len(calls)
    result=director.submit_rerender(creation,key,1,body)
    assert director.submit_rerender(creation,key,1,body)==result
    work=creation.folder(key)/'jobs'/body.requestId;data=read(work/'input.json')
    asyncio.run(director.rerender_frame(creation,key,body.requestId,work,data))
    assert len(calls)==before_calls+1 and calls[-1]['images']
    assert calls[-1]['prompt']==(edited if changed else prompt)
    assert calls[-1]['reference_images']==[Path(p) for p in refs]
    assert old_frame not in calls[-1]['reference_images']
    after=creation.load(key);updated=read(after['plan'])
    assert after['scenes'][0]==film['scenes'][0] and after['scenes'][2]==film['scenes'][2]
    assert after['scenes'][1]['takes']==scene['takes'] and after['scenes'][1]['selected']=='existing-video'
    assert updated['shots'][1]['story']==plan['shots'][1]['story']
    assert old_frame.read_bytes()==old_bytes and after['cutRevision']==film['cutRevision']
    count=len(calls)
    asyncio.run(director.rerender_frame(creation,key,body.requestId,work,data))
    assert len(calls)==count
    with pytest.raises(HTTPException):director.submit_rerender(creation,key,0,body)
    with pytest.raises(HTTPException):director.submit_rerender(creation,key,1,body.model_copy(update={'requestId':'stale-rerender-id'}))
