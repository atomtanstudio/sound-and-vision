import asyncio
import base64
import io
import json
import threading
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from PIL import Image

from .film_creation import CreateFilm, create, generate, prepare, scene_windows
from .film_review import FilmReviews, Export, read, write
from .film_worker import generation_prompt


@pytest.fixture
def creation(tmp_path, monkeypatch):
    root=tmp_path/'data';root.mkdir()
    output=root/'runs/take-one';output.mkdir(parents=True);(output/'audio.flac').write_bytes(b'audio')
    store=SimpleNamespace(root=root, path_for=lambda key:root/key,
        job=lambda key:dict(state='succeeded',output_key='runs/take-one',request_json=json.dumps({'lyrics':'A real lyric','description':'Dream pop'})))
    service=FilmReviews(store,SimpleNamespace(gpu_lock=threading.Lock()))
    service.start=lambda *args:None
    monkeypatch.setattr('backend.film_worker.probe',lambda _: {'format':{'duration':'21.025'}})
    return service


def body(**overrides):
    return CreateFilm(requestId='new-project-0001', takeId='take-one', title='New song', **overrides)


def test_create_is_durable_and_idempotent_and_tracks_the_exact_song(creation):
    result=create(creation,body())
    assert result['takeId']=='take-one' and result['scenes']==[]
    assert result['jobs'][0]['kind']=='prepare'
    assert create(creation,body())==result
    assert len(creation.discover())==1
    assert read(creation.load(result['id'])['plan'])['audio'].endswith('runs/take-one/audio.flac')
    with pytest.raises(HTTPException):create(creation,body(direction='changed'))
    with pytest.raises(HTTPException):creation.trash(result['id'],1)


def test_unfinished_song_and_missing_source_are_rejected(creation):
    creation.store.job=lambda _:dict(state='queued',output_key=None)
    with pytest.raises(HTTPException) as error:create(creation,body())
    assert error.value.status_code==409
    assert creation.discover()==[]


@pytest.mark.parametrize('duration,seconds',[(1.01,5),(11.01,10),(180.13,15),(899.9,5)])
def test_windows_cover_audio_once_within_renderer_limits(duration,seconds):
    import math
    shots=scene_windows(duration,seconds,[i*.48 for i in range(2000)])
    assert shots[0]['startFrame']==0 and shots[-1]['endFrame']==math.ceil(duration*24)
    assert all(a['endFrame']==b['startFrame'] for a,b in zip(shots,shots[1:]))
    assert all(0<s['end']-s['start']<=15 and 5<=s['generationSeconds']<=15 for s in shots)


def prepared(creation,monkeypatch):
    result=create(creation,body())
    job=result['jobs'][0]['id'];work=creation.folder(result['id'])/'jobs'/job
    # Retained pre-character-sheet preparation exercises legacy recovery.
    legacy=read(work/'input.json');legacy['plan'].pop('castRequired',None);legacy['plan'].pop('renderProfile',None)
    write(work/'input.json',legacy)
    write(work/'beats.json',{'beats':[i*.5 for i in range(44)]})
    png=io.BytesIO();Image.new('RGB',(80,50)).save(png,format='PNG')
    calls=[]
    async def turn(prompt,schema=None,images=False):
        calls.append(images)
        if images:return [{'type':'imageGeneration','result':base64.b64encode(png.getvalue()).decode()}], 'test'
        scenes=[dict(name=f'Scene {i}',action='Walk slowly on a deserted beach.',continuity='One person, same coat.') for i in range(3)]
        return [{'type':'agentMessage','text':json.dumps(dict(continuity='Same person and coat.',referencePrompt='One adult in a blue coat.',scenes=scenes))}], 'test'
    creation.account=SimpleNamespace(turn=turn)
    asyncio.run(prepare(creation,result['id'],job,work,read(work/'input.json')))
    creation.update_job(result['id'],job,'ready','Storyboard ready')
    return result['id'],work,calls


def test_prepare_then_generate_uses_storyboard_without_source_video(creation,monkeypatch):
    key,work,calls=prepared(creation,monkeypatch)
    film=creation.load(key)
    assert len(film['scenes'])==3 and calls==[False,True]
    assert all(s['type']=='narrative' for s in film['scenes'])
    request=Export(revision=film['revision'],requestId='first-scene-0001')
    first=generate(creation,key,request,0)
    assert generate(creation,key,request,0)==first
    snapshot=read(creation.folder(key)/'jobs'/request.requestId/'input.json')
    assert 'baseTake' not in snapshot and snapshot['method']=='generate'
    assert '<Audio 1>' not in generation_prompt(snapshot)
    with pytest.raises(HTTPException):creation.submit(key,Export(revision=first['revision'],requestId='premature-export'))
    creation.update_job(key,request.requestId,'ready','Ready')
    complete=creation.load(key)
    assert complete['scenes'][0]['selected']==request.requestId
    with pytest.raises(HTTPException):generate(creation,key,Export(revision=complete['revision'],requestId='duplicate-initial'),0)
    # Recovery of preparation reuses artifacts and cannot erase completed scenes.
    asyncio.run(prepare(creation,key,film['jobs'][0]['id'],work,read(work/'input.json')))
    assert creation.load(key)['scenes'][0]['selected']==request.requestId and calls==[False,True]


def test_performance_prompt_uses_only_measured_local_word_times():
    data={'shot':{'type':'performance','prompt':'A singing portrait','generationSeconds':10},
          'sceneContinuity':'One lead','timing':{'leadingRest':2.25,'words':[{'text':'Hello','start':2.25,'end':3.1}]}}
    prompt=generation_prompt(data)
    assert '<Audio 1>' in prompt and '2.250' in prompt and '3.100' in prompt


def test_explicit_video_rerender_preserves_takes_and_uses_current_storyboard(creation,monkeypatch):
    import copy
    key,_,_=prepared(creation,monkeypatch)
    film=creation.load(key)
    with pytest.raises(HTTPException,match='Animate this scene first'):
        generate(creation,key,Export(revision=film['revision'],requestId='too-early-rerender'),0,rerender=True)
    generate(creation,key,Export(revision=film['revision'],requestId='original-video'),0)
    creation.update_job(key,'original-video','ready','Ready')
    before=creation.load(key);original=copy.deepcopy(before['scenes'][0]['takes'][0])
    request=Export(revision=before['revision'],requestId='fresh-video-rerender')
    fresh=generate(creation,key,request,0,rerender=True)
    assert generate(creation,key,request,0,rerender=True)==fresh
    assert len(fresh['scenes'][0]['takes'])==2 and fresh['scenes'][0]['selected']=='original-video'
    assert fresh['jobs'][-1]['operation']=='video-rerender'
    saved=read(creation.folder(key)/'jobs'/request.requestId/'input.json')
    assert saved['method']=='generate' and 'baseTake' not in saved and 'repairVersion' not in saved
    assert saved['shot']['references']==read(before['plan'])['shots'][0]['references']
    assert saved['shot']['start']==before['scenes'][0]['start'] and saved['shot']['end']==before['scenes'][0]['end']
    for body,rerender in [(request,False),(Export(revision=before['revision'],requestId='stale-rerender'),True),
                         (Export(revision=fresh['revision'],requestId='duplicate-rerender'),True)]:
        with pytest.raises(HTTPException):generate(creation,key,body,0,rerender=rerender)
    creation.update_job(key,request.requestId,'ready','Ready')
    ready=creation.load(key)
    assert ready['scenes'][0]['selected']=='original-video' and ready['cutRevision']==before['cutRevision']
    assert ready['scenes'][0]['takes'][0]==original
    accepted=creation.accept(key,0,request.requestId,ready['revision'])
    assert accepted['scenes'][0]['selected']==request.requestId and len(accepted['scenes'][0]['takes'])==2
    assert accepted['cutRevision']==before['cutRevision']+1


@pytest.mark.parametrize('kind,kinds',[('narrative',['image']),('performance',['image','audio'])])
def test_initial_scene_provider_contract_and_no_duplicate_post(creation,monkeypatch,kind,kinds):
    from pathlib import Path
    from .film_worker import render_scene, H3Rejected
    key,_,_=prepared(creation,monkeypatch)
    film=creation.load(key)
    generate(creation,key,Export(revision=film['revision'],requestId='provider-contract'),0)
    work=creation.folder(key)/'jobs/provider-contract';data=read(work/'input.json')
    data['shot']['type']=kind
    data['timing']['words']=[{'text':'Hello','start':1,'end':2}] if kind=='performance' else []
    sent=[]
    def fake_api(path,body=None):
        if path=='/api/machine':return {'online':True,'busy':False}
        sent.append(body);raise H3Rejected('Stop before actual submission')
    monkeypatch.setattr('backend.film_worker.api',fake_api)
    monkeypatch.setattr('backend.film_worker.run',lambda args:Path(args[-1]).write_bytes(b'audio excerpt'))
    monkeypatch.setenv('SOUND_VISION_H3_VALIDATOR',str(work/'not-installed'))
    with pytest.raises(H3Rejected):render_scene(work,data)
    assert [a['kind'] for a in sent[0]['assets']]==kinds
    assert sent[0]['turbo']=='On' and sent[0]['steps']==4
    with pytest.raises(H3Rejected):render_scene(work,data)
    assert len(sent)==1
