"""No provider calls: synthetic sheets and rejected-in-memory render requests."""
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

from . import film_cast, film_creation, film_vocal_timing
from .film_review import Export, Retry, read, write
from .film_voice import voice_contract, voice_direction
from .film_worker import H3Rejected, generation_prompt, repair_prompt, render_scene
from .test_film_creation import creation, body


CAST = [
    dict(id='guitar', name='Ash', role='guitarist', appearance='Long black hair, full beard, angular face, tall adult, black denim, red guitar.'),
    dict(id='lead', name='Robin', role='lead vocalist', appearance='Short silver hair, clean-shaven round face, adult, blue leather jacket, handheld microphone.'),
    dict(id='bass', name='Sol', role='bassist', appearance='Long red hair, braided red beard, broad face, adult, brown coat, black bass guitar.'),
    dict(id='dragon', name='Ember', role='dragon in the story', appearance='A huge emerald dragon with two swept horns, gold eyes, long tail and torn left wing tip.'),
]


def prepare_cast(service, monkeypatch, hybrid=False):
    film = film_creation.create(service, body(treatment='mixed', workflow='vrgdg-h3-turbo' if hybrid else 'directed'))
    job = film['jobs'][0]['id']; work = service.folder(film['id'])/'jobs'/job
    plan = read(work/'input.json')['plan']
    alignment = {'cues':[{'text':'Hello there', 'words':[{'text':'Hello','start':1,'end':2}, {'text':'there','start':3,'end':4}]}],
                 'duration':plan['duration'], 'version':2, 'sourceSha256':hashlib.sha256(Path(plan['audio']).read_bytes()).hexdigest(),
                 'lyricsSha256':film_vocal_timing.lyrics_key(plan['lyrics'])}
    async def ensure(*args):return alignment
    monkeypatch.setattr(film_vocal_timing, 'ensure', ensure)
    write(work/'beats.json', {'beats':[]})
    write(service.store.root/'video'/('film-align-'+job)/'result.json', alignment)
    png = io.BytesIO(); Image.new('RGB',(96,96),'green').save(png,format='PNG')
    calls = []
    board = {'continuity':'Same band and dragon across the entire film.', 'referencePrompt':'Empty concert hall with moody blue lights.', 'cast':CAST,
             'scenes':[
                 dict(name='Band', action='The band plays their assigned instruments on the stage.', continuity='Same three musicians and their instruments.', castIds=['guitar','lead','bass'], vocalistId='lead'),
                 dict(name='Dragon', action='The dragon folds its wings in the forest.', continuity='One emerald dragon.', castIds=['dragon'], vocalistId=None),
                 dict(name='Lead alone', action='Robin walks quietly through the hallway.', continuity='Same vocalist and blue jacket.', castIds=['lead'], vocalistId=None),
             ]}
    if hybrid:
        for scene,end in zip(board['scenes'],[7,14,21.025]):scene.update(endSeconds=end,performance=scene['vocalistId'] is not None)
    async def turn(prompt, schema=None, images=False, **kwargs):
        calls.append({'prompt':prompt, 'images':images, **kwargs})
        if images:return [{'type':'imageGeneration','result':base64.b64encode(png.getvalue()).decode()}], 'fixture'
        return [{'type':'agentMessage','text':json.dumps(board)}], 'fixture'
    service.account = SimpleNamespace(turn=turn)
    asyncio.run(film_creation.prepare(service, film['id'], job, work, read(work/'input.json')))
    service.update_job(film['id'], job, 'ready', 'Ready')
    return service.load(film['id']), work, calls


@pytest.mark.parametrize('hybrid',[False,True])
def test_every_cast_member_has_a_durable_sheet_before_scene_submission(creation,monkeypatch,hybrid):
    film,work,calls=prepare_cast(creation,monkeypatch,hybrid)
    plan=read(film['plan'])
    assert plan['renderProfile']==film_cast.PROFILE and film['characterSheetVersion']==1
    assert len(film['cast'])==4 and sum(c['images'] for c in calls)==5
    assert [len(s['references']) for s in plan['shots']]==[3,1,1]
    assert plan['shots'][0]['references'][1]==plan['shots'][2]['references'][0]
    assert plan['shots'][0]['vocalistId']=='lead'
    assert 'EVERY recognizable' in calls[0]['prompt']
    assert all('left-facing profile' in c['prompt'] and 'right-facing profile' in c['prompt'] for c in calls[2:])
    request=Export(revision=film['revision'],requestId='new-band-render')
    film_creation.generate(creation,film['id'],request,0)
    film_creation.generate(creation,film['id'],request,0)
    snapshot=read(creation.folder(film['id'])/'jobs/new-band-render/input.json')
    film_cast.check_references(snapshot)
    for prompt in (generation_prompt(snapshot),repair_prompt({**snapshot,'repairVersion':2})):
        assert '<Subject 1> is Ash' in prompt and '<Subject 2> is Robin' in prompt and '<Subject 3> is Sol' in prompt
        assert '<Subject 2> (S1)' in prompt and '<Subject 1> keeps lips gently closed' in prompt
        assert '<Subject 3> keeps lips gently closed' in prompt
        assert 'Ember' not in prompt
    before=copy.deepcopy(creation.load(film['id'])['scenes'])
    asyncio.run(film_creation.prepare(creation,film['id'],film['jobs'][0]['id'],work,read(work/'input.json')))
    assert creation.load(film['id'])['scenes']==before and len(calls)==6
    public=creation.public(creation.load(film['id']))
    assert all('source' not in c and c['sheetUrl'].endswith('/sheet') for c in public['cast'])


def test_missing_or_changed_sheet_stops_before_provider_work(creation,monkeypatch):
    film,_,_=prepare_cast(creation,monkeypatch)
    Path(film['cast'][2]['source']).write_bytes(b'changed identity')
    with pytest.raises(HTTPException) as error:
        film_creation.generate(creation,film['id'],Export(revision=film['revision'],requestId='blocked-hash'),0)
    assert error.value.status_code==409 and 'changed' in error.value.detail
    assert not creation.load(film['id'])['scenes'][0]['takes']


@pytest.mark.parametrize('hybrid',[False,True])
@pytest.mark.parametrize('singing',[False,True])
def test_refined_provider_sends_cast_and_continuous_locked_vocals(creation,monkeypatch,hybrid,singing):
    film,_,_=prepare_cast(creation,monkeypatch,hybrid)
    index=0 if singing else 1
    film_creation.generate(creation,film['id'],Export(revision=film['revision'],requestId='provider-fixture'),index)
    work=creation.folder(film['id'])/'jobs/provider-fixture';data=read(work/'input.json')
    sent=[];audio_calls=[]
    def api(path,payload=None):
        if path=='/api/machine':return {'online':True,'busy':False}
        sent.append(payload);raise H3Rejected('Fixture stops before submission')
    def vocal(target,source,shot,policy):
        audio_calls.append(policy);target.write_bytes(b'fixture-gated-vocals')
    monkeypatch.setattr('backend.film_worker.api',api)
    monkeypatch.setattr('backend.film_worker.prepare_vocal_reference',vocal)
    monkeypatch.setattr('backend.film_worker.conditioning_source',lambda *args:(Path(data['plan']['audio']),'isolated-vocal'))
    monkeypatch.setenv('SOUND_VISION_H3_VALIDATOR',str(work/'not-installed'))
    with pytest.raises(H3Rejected):render_scene(work,data)
    assert sent[0]['generationModel']==film_cast.PROFILE and sent[0]['steps']==8
    assert sent[0].get('audioDrive')==('vrgdg-vocal' if singing else None)
    assert [a['kind'] for a in sent[0]['assets']]==(['image']*3+['audio'] if singing else ['image'])
    assert len(audio_calls)==int(singing)
    if singing:
        assert audio_calls[0]['subjectNumber']==2
        assert audio_calls[0]['restWindows'][0]=={'start':0,'end':1}
        assert audio_calls[0]['timingAuthority']=='recorded-audio'
        assert audio_calls[0]['gateVersion']==3
        assert 'continuous recording is the timing authority' in sent[0]['prompt']
        assert 'From 0.000 to 1.000 seconds' not in sent[0]['prompt']
    else:
        assert '<Audio 1>' not in sent[0]['prompt'] and '(S1)' not in sent[0]['prompt']
    with pytest.raises(H3Rejected):render_scene(work,data)
    assert len(sent)==1


def test_missing_vocal_stem_cannot_fall_back_to_full_band_mix(creation,monkeypatch):
    film,_,_=prepare_cast(creation,monkeypatch)
    film_creation.generate(creation,film['id'],Export(revision=film['revision'],requestId='missing-stem'),0)
    work=creation.folder(film['id'])/'jobs/missing-stem';data=read(work/'input.json')
    monkeypatch.setattr('backend.film_worker.api',lambda *args:pytest.fail('No provider call is allowed'))
    with pytest.raises(ValueError,match='isolated vocal stem'):render_scene(work,data)


def test_cast_validation_rejects_role_aliases_and_unassigned_singers():
    for members,scenes in [
        ([CAST[0],CAST[0]],[{'castIds':['guitar'],'vocalistId':None}]),
        ([CAST[0]],[{'castIds':['stranger'],'vocalistId':None}]),
        ([CAST[0]],[{'castIds':['guitar'],'vocalistId':'lead'}]),
        ([CAST[0]],[{'castIds':['guitar','guitar'],'vocalistId':None}]),
    ]:
        with pytest.raises(ValueError):film_cast.validate_cast(members,scenes)


def test_short_vocal_gaps_remain_closed_mouth_rests():
    data={'shot':{'type':'performance','start':0,'end':5,'generationSeconds':5},
          'timing':{'words':[{'text':'First','start':1,'end':2},{'text':'Second','start':2.2,'end':3}]}}
    assert {'start':2,'end':2.2} in voice_contract(data)['restWindows']


def test_upgrade_keeps_cuts_takes_and_recovers_completed_sheets(creation,monkeypatch):
    from .test_film_creation import prepared
    key,_,_=prepared(creation,monkeypatch)
    film=creation.load(key)
    film_creation.generate(creation,key,Export(revision=film['revision'],requestId='original-fixture'),0)
    creation.update_job(key,'original-fixture','ready','Ready')
    film=creation.load(key);before=copy.deepcopy(film['scenes']);calls=[]
    buffer=io.BytesIO();Image.new('RGB',(64,64)).save(buffer,format='PNG')
    async def turn(prompt,schema=None,images=False,**kwargs):
        calls.append(images)
        if images:return [{'type':'imageGeneration','result':base64.b64encode(buffer.getvalue()).decode()}],'fixture'
        return [{'type':'agentMessage','text':json.dumps({'cast':[CAST[1]],'scenes':[{'castIds':['lead'],'vocalistId':None} for _ in before]})}],'fixture'
    creation.account=SimpleNamespace(turn=turn)
    req=Export(revision=film['revision'],requestId='upgrade-characters')
    film_cast.submit(creation,key,req);film_cast.submit(creation,key,req)
    work=creation.folder(key)/'jobs'/req.requestId
    asyncio.run(film_cast.upgrade(creation,key,req.requestId,work,read(work/'input.json')))
    asyncio.run(film_cast.upgrade(creation,key,req.requestId,work,read(work/'input.json')))
    updated=creation.load(key)
    assert calls==[False,True] and updated['renderProfile']==film_cast.PROFILE
    assert [(s['startFrame'],s['endFrame'],s['selected'],s['takes']) for s in before]==[(s['startFrame'],s['endFrame'],s['selected'],s['takes']) for s in updated['scenes']]
    assert (work/'previous-plan.json').is_file()
