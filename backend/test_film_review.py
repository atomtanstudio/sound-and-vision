import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from .film_review import FilmReviews, Edit, Retry, Export, vocal_windows, read, write
from .film_worker import prompt_for, render_scene, render_timing, prepare_context, probe, conditioning_source


@pytest.fixture
def review(tmp_path):
    data=tmp_path/'data';data.mkdir()
    folder=data/'films'/'example'/'repair';folder.mkdir(parents=True)
    audio=data/'song.flac';audio.write_bytes(b'original audio')
    references=folder/'references';references.mkdir();(references/'person.png').write_bytes(b'reference')
    shots=[]
    for i in range(2):
        work=folder/'clips'/f'original-{i}';work.mkdir(parents=True)
        (work/'background.mp4').write_bytes(f'original scene {i}'.encode())
        shots.append({'index':i,'name':f'Scene {i+1}','type':'performance' if i==0 else 'narrative',
                      'start':i*6,'end':i*6+6,'startFrame':i*144,'endFrame':(i+1)*144,
                      'generationSeconds':6,'runId':f'original-{i}',
                      'references':[str(references/'person.png')],'prompt':'Original uncorrected action'})
    write(folder/'film-plan.json',{'title':'Repair','artist':'Test','takeId':'test-take','duration':12,
                                  'fps':24,'audio':str(audio),'output':[1920,1080],'shots':shots})
    (folder/'Film.mp4').write_bytes(b'completed original film')
    write(folder/'Film.receipt.json',{'title':'Repair'})
    write(folder/'alignment-sections.json',{'cues':[{'words':[
        {'text':'First','start':.8,'end':1.3,'review':None},
        {'text':'line','start':1.4,'end':2,'review':None},
        {'text':'across','start':5.8,'end':6.3,'review':'Check'}]}]})
    service=FilmReviews(SimpleNamespace(root=data),SimpleNamespace(gpu_lock=threading.Lock()))
    started=[];service.start=lambda *args:started.append(args)
    film=service.discover()[0]
    return service,film['id'],folder,started


def test_import_retains_whole_film_and_exact_scene_windows(review):
    service,key,folder,_=review
    film=service.load(key)
    assert len(film['scenes'])==2
    assert film['scenes'][0]['timing']['leadingRest']==.8
    assert film['exports'][0]['source']==str(folder/'Film.mp4')
    assert service.discover()[0]['revision']==1
    public=service.public(film)
    assert 'plan' not in public and 'source' not in public['scenes'][0]['takes'][0]
    assert public['exports'][0]['mediaUrl'].endswith('/exports/original')


def test_video_trash_survives_discovery_and_restart_and_can_restore(review):
    service,key,folder,_=review
    original=service.load(key)
    trashed=service.trash(key,original['revision'])
    assert trashed['deletedAt'] and service.discover()==[]
    assert service.discover(include_deleted=True)[0]['id']==key
    with pytest.raises(HTTPException) as error:service.load(key)
    assert error.value.status_code==404
    assert (folder/'Film.mp4').read_bytes()==b'completed original film'
    assert (folder/'clips/original-0/background.mp4').read_bytes()==b'original scene 0'
    resumed=FilmReviews(service.store,service.manager)
    assert resumed.discover()==[] # Retained source plan must not silently recreate it.
    assert resumed.pending()==[]
    with pytest.raises(HTTPException):resumed.trash(key,1,False)
    restored=resumed.trash(key,trashed['revision'],False)
    assert not restored['deletedAt'] and len(resumed.discover())==1
    assert resumed.load(key)['scenes']==original['scenes']
    assert restored['cutRevision']==original['cutRevision']


def test_video_trash_rejects_active_jobs_and_stale_edits(review):
    service,key,_,_=review
    result=service.submit(key,Retry(revision=1,requestId='active-trash-test',correction='Fix'),0)
    with pytest.raises(HTTPException):service.trash(key,result['revision'])
    service.update_job(key,'active-trash-test','ready','Ready')
    with pytest.raises(HTTPException):service.trash(key,1)
    assert not service.load(key).get('deletedAt')


def test_boundary_words_are_clipped_and_rests_are_not_guessed():
    alignment={'cues':[{'words':[{'text':'held','start':4.8,'end':5.4,'review':None},
                                {'text':'note','start':6.2,'end':7.1,'review':None}]}]}
    timing=vocal_windows(alignment,{'start':5,'end':7})
    assert timing['leadingRest']==0
    assert timing['words'][0]['start']==0 and timing['words'][0]['end']==.4
    assert timing['words'][1]['end']==2
    assert len(timing['spans'])==2
    assert vocal_windows({}, {'start':5,'end':7})['leadingRest']==2


def test_retry_is_idempotent_preserves_original_and_snapshots_context(review):
    service,key,folder,started=review
    body=Retry(revision=1,requestId='scene-retry-001',correction='Keep the mouth closed before the first vocal.',continuity='One person; no props.',issue='lip-sync')
    first=service.submit(key,body,0);second=service.submit(key,body,0)
    assert first==second and len(started)==1
    scene=first['scenes'][0]
    assert scene['selected']=='original' and len(scene['takes'])==2
    assert (folder/'clips/original-0/background.mp4').read_bytes()==b'original scene 0'
    context=read(service.folder(key)/'jobs/scene-retry-001/input.json')
    assert len(context['story'])==2
    assert context['shot']['startFrame']==0 and context['shot']['endFrame']==144
    assert context['timing']['leadingRest']==.8
    assert context['correction']==body.correction and context['sceneContinuity']==body.continuity
    assert context['plan']['audio']==str(folder.parents[2]/'song.flac')
    assert first['cutRevision']==1
    assert not first['scenes'][0]['takes'][-1]['contextChanged']
    with pytest.raises(HTTPException) as error:
        service.submit(key,body.model_copy(update={'correction':'Different request'}),0)
    assert error.value.status_code==409
    with pytest.raises(HTTPException):
        service.submit(key,body.model_copy(update={'requestId':'scene-retry-002','revision':first['revision']}),0)
    changed=service.edit(key,None,Edit(revision=first['revision'],continuity='A changed cast and setting'))
    assert changed['scenes'][0]['takes'][-1]['contextChanged']


def test_accept_requires_ready_take_and_export_preserves_other_scenes(review):
    service,key,folder,_=review
    service.submit(key,Retry(revision=1,requestId='replacement-001',correction='Stay silent.'),0)
    film=service.load(key)
    with pytest.raises(HTTPException):service.accept(key,0,'replacement-001',film['revision'])
    service.update_job(key,'replacement-001','ready','Ready')
    accepted=service.accept(key,0,'replacement-001',film['revision'])
    assert accepted['cutRevision']==2 and accepted['scenes'][0]['review']=='approved'
    assert accepted['scenes'][1]['selected']=='original'
    service.submit(key,Export(revision=accepted['revision'],requestId='film-export-001'))
    snapshot=read(service.folder(key)/'jobs/film-export-001/input.json')
    assert snapshot['story'][0]['selected']=='replacement-001'
    assert snapshot['story'][1]['source']==str(folder/'clips/original-1/background.mp4')
    restored=service.accept(key,0,'original',accepted['revision'])
    assert restored['cutRevision']==3
    assert read(service.folder(key)/'jobs/film-export-001/input.json')==snapshot
    assert service.load(key)['exports'][0]['id']=='original'


def test_concurrent_edits_cannot_overwrite_newer_context(review):
    service,key,_,_=review
    def edit(i):
        try:return service.edit(key,0,Edit(revision=1,correction=f'Correction {i}'))['revision']
        except HTTPException as e:return e.status_code
    with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(edit,range(8)))
    assert results.count(2)==1 and results.count(409)==7
    assert service.load(key)['cutRevision']==1
    with pytest.raises(HTTPException):service.load('../../escape')


def test_correction_prompt_carries_timing_story_and_no_obsolete_action(review):
    service,key,_,_=review
    service.submit(key,Retry(revision=1,requestId='prompt-test-001',correction='Both mugs stay on the table.',continuity='Exactly two mugs.'),0)
    data=read(service.folder(key)/'jobs/prompt-test-001/input.json')
    data['repairVersion']=1 # Existing queued requests must keep their saved prompt contract.
    prompt=prompt_for(data,3)
    assert 'initial 0.800 seconds' in prompt
    assert 'Both mugs stay on the table.' in prompt and 'Exactly two mugs.' in prompt
    assert '<Picture 2>' in prompt and '<Picture 3>' in prompt
    assert '<Picture 2>: weak_reference -' in prompt
    assert '<Picture 3>: weak_reference -' in prompt
    assert 'Scene 2' not in prompt # Full context stays in the snapshot, not the render instructions.
    assert 'Original uncorrected action' not in prompt
    data['compiledContext']={'brief':{'cast':'One repairman','singleAction':'He stays seated.'}}
    compiled=prompt_for(data,1)
    assert '\ncast:' not in compiled # Must not become an unsupported H3 top-level field.
    assert 'The scene constraints are: cast: One repairman' in compiled


def test_uncertain_provider_submission_is_never_replayed(review,monkeypatch):
    service,key,_,_=review
    service.submit(key,Retry(revision=1,requestId='uncertain-test-001',correction='Stay silent.'),0)
    work=service.folder(key)/'jobs/uncertain-test-001';data=read(work/'input.json')
    write(work/'provider-intent.json',{'submissionStarted':True,'runId':data['runId']})
    monkeypatch.setenv('SOUND_VISION_H3_LIBRARY',str(work/'empty-library'))
    def forbidden(*args,**kwargs):raise AssertionError('Provider submission must not repeat')
    monkeypatch.setattr('backend.film_worker.api',forbidden)
    with pytest.raises(RuntimeError,match='no duplicate'):
        render_scene(work,data)


def test_context_preview_preserves_neighbor_frames_and_absolute_audio_window(review):
    import array,math,subprocess
    service,key,folder,_=review
    film=service.load(key);plan=read(film['plan'])
    def run(args):subprocess.run(['ffmpeg','-y','-v','error',*map(str,args)],check=True)
    audio=folder/'test-master.wav'
    run(['-f','lavfi','-i','aevalsrc=sin(2*PI*(220*t+30*t*t)):s=48000:d=12','-c:a','pcm_s16le',audio])
    plan['audio']=str(audio)
    for scene,color in zip(film['scenes'],['red','blue']):
        run(['-f','lavfi','-i',f'color={color}:s=160x90:r=24:d=6','-c:v','libx264','-pix_fmt','yuv420p',scene['takes'][0]['source']])
    scene=film['scenes'][1]
    target=prepare_context(film,scene,scene['takes'][0],plan,service.folder(key)/'test-context')
    video=probe(target)['streams'][0]
    assert int(video['nb_frames'])==192 # Two seconds of the previous scene plus all six target seconds.
    assert [video['width'],video['height']]==[1920,1080]
    def pcm(path,start=0):
        raw=subprocess.check_output(['ffmpeg','-v','error','-ss',str(start),'-i',str(path),'-vn','-ar','8000','-ac','1','-f','f32le','-'])
        samples=array.array('f');samples.frombytes(raw);return samples
    expected,actual=pcm(audio,4),pcm(target)
    size=min(len(expected),len(actual));a,b=expected[:size],actual[:size]
    correlation=sum(x*y for x,y in zip(a,b))/math.sqrt(sum(x*x for x in a)*sum(y*y for y in b))
    assert correlation>.99
    # Changing the accepted neighbor must not reuse a stale context-preview file.
    changed=copy.deepcopy(film);replacement=folder/'replacement.mp4'
    replacement.write_bytes(Path(changed['scenes'][0]['takes'][0]['source']).read_bytes())
    changed['scenes'][0]['takes'][0]['source']=str(replacement)
    assert prepare_context(changed,scene,scene['takes'][0],plan,service.folder(key)/'test-context')!=target


def test_performance_uses_existing_vocal_stem_without_replacing_the_song(tmp_path):
    import hashlib
    master=tmp_path/'song.flac';master.write_bytes(b'full original song')
    assert conditioning_source(master,'performance',tmp_path)==(master,'full-mix')
    vocal=tmp_path/'video/audio-cache'/hashlib.sha256(master.read_bytes()).hexdigest()/'vocals.wav'
    vocal.parent.mkdir(parents=True);vocal.write_bytes(b'isolated voice')
    assert conditioning_source(master,'performance',tmp_path)==(vocal,'isolated-vocal')
    assert conditioning_source(master,'narrative',tmp_path)==(master,'full-mix')
    assert master.read_bytes()==b'full original song'


def test_repairs_use_previewed_take_and_validate_methods(review):
    service,key,_,_=review
    film=service.load(key)
    original=film['scenes'][0]['takes'][0]
    film['scenes'][0]['takes'].append({**original,'id':'another-take','label':'Another take'})
    service.save(film)
    body=Retry(revision=1,requestId='source-edit-test',baseTakeId='another-take',correction='Keep lips closed during rests.')
    result=service.submit(key,body,0)
    snapshot=read(service.folder(key)/'jobs/source-edit-test/input.json')
    assert snapshot['baseTake']['id']=='another-take'
    assert result['scenes'][0]['selected']=='original'
    assert result['scenes'][0]['takes'][-1]['baseTakeId']=='another-take'
    prompt=prompt_for(snapshot,1)
    assert '[video editing + audio reference]' in prompt and '<Video 1> (source video editing)' in prompt
    assert 'The source mouth motion is not a timing reference' in prompt
    for fields in ({'baseTakeId':'missing'}, {'method':'timing','shiftFrames':0}, {'shiftFrames':5}):
        with pytest.raises(HTTPException):
            service.submit(key,Retry(revision=result['revision'],requestId='invalid-method-01',correction='Fix',**fields),1)
    service.submit(key,Retry(revision=result['revision'],requestId='silent-edit-test',correction='Stay silent.'),1)
    silent=read(service.folder(key)/'jobs/silent-edit-test/input.json')
    assert '<Audio' not in prompt_for(silent,1)
    assert '[video editing]' in prompt_for(silent,1)


def test_queue_order_cancel_and_restart_are_consistent_across_films(review):
    import asyncio
    service,key,_,_=review
    other=copy.deepcopy(service.load(key));other['id']='a-second-film';service.save(other)
    first=service.submit(key,Retry(revision=1,requestId='fifo-first-scene',correction='Fix'),0)
    second=service.submit('a-second-film',Retry(revision=1,requestId='fifo-second-scene',correction='Fix'),0)
    third=service.submit(key,Retry(revision=first['revision'],requestId='fifo-third-scene',correction='Fix'),1)
    assert third['jobs'][-1]['queuePosition']==3
    service.update_job(key,'fifo-first-scene','running','Rendering')
    assert service.public(service.load('a-second-film'))['jobs'][0]['queuePosition']==1
    service.dispatch=lambda:None
    cancelled=service.cancel('a-second-film','fifo-second-scene')
    assert cancelled['jobs'][0]['state']=='cancelled'
    assert service.public(service.load(key))['jobs'][-1]['queuePosition']==1
    with pytest.raises(HTTPException):service.cancel(key,'fifo-first-scene')
    async def restart():
        resumed=FilmReviews(service.store,service.manager)
        order=[]
        async def worker(film_id,job_id):
            order.append(job_id)
            resumed.update_job(film_id,job_id,'ready','Ready')
            resumed.tasks.pop((film_id,job_id))
            resumed.dispatch()
        resumed.run=worker
        resumed.recover()
        while resumed.tasks:await asyncio.gather(*list(resumed.tasks.values()))
        await resumed.close()
        return order
    assert asyncio.run(restart())==['fifo-first-scene','fifo-third-scene']


@pytest.mark.parametrize('index,kinds', [(0,['image','audio','video']), (1,['image','video'])])
def test_source_edit_submits_the_base_video_and_only_performance_audio(review,monkeypatch,index,kinds):
    from .film_worker import H3Rejected
    service,key,_,_=review
    service.submit(key,Retry(revision=1,requestId='asset-contract-001',correction='Stay in this scene.'),index)
    work=service.folder(key)/'jobs/asset-contract-001';data=read(work/'input.json')
    sent=[]
    def fake_api(path,body=None):
        if path=='/api/machine':return {'online':True,'busy':False}
        sent.append(body);raise H3Rejected('Test stops before provider submission')
    monkeypatch.setattr('backend.film_worker.api',fake_api)
    commands=[]
    def fake_run(args):
        commands.append(args)
        Path(args[-1]).write_bytes(b'test encoded media')
    monkeypatch.setattr('backend.film_worker.run',fake_run)
    monkeypatch.setattr('backend.film_worker.frame',lambda source,when,target:target.write_bytes(b'test frame'))
    monkeypatch.setenv('SOUND_VISION_H3_VALIDATOR',str(work/'not-installed'))
    with pytest.raises(H3Rejected):render_scene(work,data)
    assert [a['kind'] for a in sent[0]['assets']]==kinds
    video=next(a for a in sent[0]['assets'] if a['kind']=='video')
    import base64
    assert base64.b64decode(video['dataUrl'].split(',')[1])==(work/'source-reference.mp4').read_bytes()
    assert any(data['baseTake']['source'] in args for args in commands)
    assert video['includeSoundtrack'] is False
    assert sent[0]['turbo']=='On' and sent[0]['steps']==4


@pytest.mark.parametrize('shift', [-6,6])
def test_timing_repair_moves_only_existing_frames_and_keeps_duration(tmp_path,shift):
    import subprocess
    source=tmp_path/'source.mp4'
    # Provider source includes an unused tail; repairs must respect the edit's
    # 48-frame boundary instead of pulling those unselected frames into the cut.
    subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','testsrc2=s=160x90:r=24:d=2.5',
                    '-c:v','libx264','-crf','18','-pix_fmt','yuv420p',str(source)],check=True)
    data={'shiftFrames':shift,'baseTake':{'id':'original','source':str(source)},
          'shot':{'startFrame':24,'endFrame':72,'start':1,'end':3},'plan':{'fps':24}}
    before=source.read_bytes()
    render_timing(tmp_path,data)
    result=read(tmp_path/'checks.json')
    assert result['frames']==48 and result['audioStart']==1 and result['audioEnd']==3
    assert result['shiftFrames']==shift and source.read_bytes()==before
    def frames(path):
        return subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-vf','scale=40:22','-pix_fmt','gray','-f','rawvideo','-'])
    src,out=frames(source),frames(tmp_path/'background.mp4');size=40*22
    for i in range(48):
        expected=max(0,min(47,i-shift))
        a=src[expected*size:(expected+1)*size];b=out[i*size:(i+1)*size]
        assert sum(abs(x-y) for x,y in zip(a,b))/size<2.5
    assert not (tmp_path/'provider-intent.json').exists()
    from .film_worker import prepare_source_reference
    data['shot']['generationSeconds']=2
    ref=prepare_source_reference(tmp_path,data)
    stream=probe(ref)['streams'][0]
    assert [stream['width'],stream['height']]==[512,288]
    assert int(stream['nb_frames'])==56 # 5 mod 17; retains all 48 original frames.
    assert stream['r_frame_rate']=='24/1'
    ref_frames=frames(ref)
    for i in [0,23,47,55]:
        a=src[min(47,i)*size:(min(47,i)+1)*size];b=ref_frames[i*size:(i+1)*size]
        assert sum(abs(x-y) for x,y in zip(a,b))/size<3
