import asyncio
import base64
import hashlib
import io
import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from fastapi import HTTPException

from .film_audio_drive import WORKFLOW, scene_windows, storyboard_windows, retime, export_film
from .film_creation import create, prepare, generate
from .film_review import Export, Retry, SceneCut, read, write
from .film_worker import H3Rejected, render_scene
from .test_film_creation import creation, body
from . import film_vocal_timing


@pytest.fixture(autouse=True)
def measured_timing(monkeypatch):
    async def ensure(reviews, plan, work, phase):
        return {'version':2,'sourceSha256':hashlib.sha256(Path(plan['audio']).read_bytes()).hexdigest(),
                'lyricsSha256':film_vocal_timing.lyrics_key(plan['lyrics']),'duration':plan['duration'],
                'cues':[{'text':'A real lyric','words':[{'text':'A','start':10.5,'end':11.,'review':None}]}]}
    monkeypatch.setattr(film_vocal_timing,'ensure',ensure)


def test_fixed_and_storyboard_timing_cover_the_song_exactly():
    shots=scene_windows(265.438667,15)
    assert len(shots)==18 and shots[-1]['end']==265.438667
    assert shots[-1]['endFrame']==math.ceil(265.438667*24)
    assert all(round(s['generationSeconds']*24)%17==5 for s in shots)
    varied=storyboard_windows(30.23,[8,20,30.23])
    assert [s['endFrame']-s['startFrame'] for s in varied]==[192,288,246]
    for ends in [[8,30.23],[8,8,30.23],[8,20,29],[float('nan')]]:
        with pytest.raises(ValueError):storyboard_windows(30.23,ends)


def prepare_hybrid(creation, flexible=True):
    f=create(creation,body(workflow=WORKFLOW,renderTier='standard',treatment='mixed',sceneTiming='storyboard' if flexible else 'fixed'))
    job=f['jobs'][0]['id'];work=creation.folder(f['id'])/'jobs'/job
    # Existing source-locked projects keep their saved provider contract.
    legacy=read(work/'input.json');legacy['plan'].pop('castRequired',None);legacy['plan'].pop('renderProfile',None)
    write(work/'input.json',legacy)
    buffer=io.BytesIO();Image.new('RGB',(32,32)).save(buffer,format='PNG')
    calls=[]
    async def turn(prompt,schema=None,images=False):
        calls.append(prompt)
        if images:return [{'type':'imageGeneration','result':base64.b64encode(buffer.getvalue()).decode()}],'test'
        scenes=[dict(name=f'Scene {i}',performance=True,action='An adult man in a black jacket stands in a steel corridor.',continuity='Same face and jacket.',
                     **({'endSeconds':end} if flexible and 'endSeconds' in json.dumps(schema) else {})) for i,end in enumerate([7,14,21.025])]
        board={'scenes':scenes}
        if 'referencePrompt' in schema.get('properties',{}):board.update(continuity='Same man.',referencePrompt='Contemporary male lead.')
        return [{'type':'agentMessage','text':json.dumps(board)}],'test'
    creation.account=SimpleNamespace(turn=turn)
    asyncio.run(prepare(creation,f['id'],job,work,read(work/'input.json')))
    creation.update_job(f['id'],job,'ready','Storyboard ready')
    assert not (work/'beats.json').exists() # No beat snapping; vocal analysis is supplied separately.
    return creation.load(f['id']),calls


def test_flexible_storyboard_and_cut_editor_are_safe_before_rendering(creation):
    f,calls=prepare_hybrid(creation)
    assert [s['end'] for s in f['scenes']]==[7,14,21.025]
    assert 'Choose scene lengths' in calls[0] and 'recording timeline' in calls[0] and '10.5' in calls[0]
    changed=retime(creation,f['id'],0,SceneCut(revision=f['revision'],endSeconds=8.1))
    assert changed['scenes'][0]['end']==changed['scenes'][1]['start']==194/24
    snapshot=read(creation.load(f['id'])['plan'])
    assert snapshot['shots'][1]['startFrame']==194 and snapshot['output']==[960,544]
    assert len({s['referenceSha256'] for s in snapshot['shots']})==1
    revision=changed['revision']
    with pytest.raises(HTTPException):retime(creation,f['id'],0,SceneCut(revision=revision,endSeconds=13.9))
    assert creation.load(f['id'])['revision']==revision
    generate(creation,f['id'],Export(revision=revision,requestId='hybrid-first-scene'),0)
    with pytest.raises(HTTPException):retime(creation,f['id'],0,SceneCut(revision=revision+1,endSeconds=8))


def test_full_mix_and_pinned_renderer_even_in_silent_scene_and_retry_is_not_duplicated(creation,monkeypatch):
    f,_=prepare_hybrid(creation)
    generate(creation,f['id'],Export(revision=f['revision'],requestId='hybrid-first-scene'),0)
    work=creation.folder(f['id'])/'jobs/hybrid-first-scene';data=read(work/'input.json')
    data['shot']['type']='narrative';sent=[];audio_commands=[]
    def fake_api(path,payload=None):
        if path=='/api/machine':return {'online':True,'busy':False}
        sent.append(payload);raise H3Rejected('Engineering test: no submission')
    def fake_run(args):audio_commands.append(args);Path(args[-1]).write_bytes(b'full original mix')
    monkeypatch.setattr('backend.film_worker.api',fake_api)
    monkeypatch.setattr('backend.film_worker.run',fake_run)
    monkeypatch.setattr('backend.film_worker.conditioning_source',lambda *args:pytest.fail('Must not replace the full mix'))
    monkeypatch.setenv('SOUND_VISION_H3_VALIDATOR',str(work/'none'))
    with pytest.raises(H3Rejected):render_scene(work,data)
    r=sent[0]
    assert r['audioDrive']=='vrgdg-source' and r['generationModel']=='current' and r['steps']==4
    assert r['tier']=='standard' and [a['kind'] for a in r['assets']]==['image','audio']
    assert 'quiet observer' in r['prompt'] and '<Audio 1>' in r['prompt']
    assert audio_commands[0][audio_commands[0].index('-i')+1]==Path(data['plan']['audio'])
    assert audio_commands[0][audio_commands[0].index('-ar')+1]==44100
    assert not any('apad' in str(a) for a in audio_commands[0])
    with pytest.raises(H3Rejected):render_scene(work,data)
    assert len(sent)==1
    data['shot']['referenceSha256']='wrong'
    with pytest.raises(ValueError,match='reference changed'):render_scene(work,data)


def test_hybrid_regeneration_retains_original_take_and_never_adds_source_video(creation):
    f,_=prepare_hybrid(creation)
    generate(creation,f['id'],Export(revision=f['revision'],requestId='hybrid-first-scene'),0)
    creation.update_job(f['id'],'hybrid-first-scene','ready','Ready')
    f=creation.load(f['id'])
    with pytest.raises(HTTPException):creation.submit(f['id'],Retry(revision=f['revision'],requestId='bad-repair-method',method='smart',correction='Fix it'),0)
    r=Retry(revision=f['revision'],requestId='hybrid-retake-one',method='regenerate',correction='Use a rear view during the instrumental.',continuity='Same jacket.')
    creation.submit(f['id'],r,0)
    creation.submit(f['id'],r,0)
    data=read(creation.folder(f['id'])/'jobs/hybrid-retake-one/input.json')
    assert data['method']=='generate' and data['identityReferences']==[] and 'baseTake' not in data and 'repairVersion' not in data
    f=creation.load(f['id']);assert len(f['scenes'][0]['takes'])==2 and f['scenes'][0]['selected']=='hybrid-first-scene'


def test_hybrid_export_joins_video_without_scaling_or_titles(tmp_path):
    import subprocess
    work=tmp_path/'export';work.mkdir();audio=tmp_path/'song.wav'
    subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','sine=frequency=440:duration=3.23',str(audio)],check=True)
    shots=storyboard_windows(3.23,[2,3.23]);story=[]
    for s in shots:
        file=tmp_path/f"source-{s['index']}.mp4"
        subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','color=blue:size=960x544:rate=24',
            '-frames:v',str(s['endFrame']-s['startFrame']),'-c:v','libx264','-threads','2','-pix_fmt','yuv420p',str(file)],check=True)
        story.append(dict(index=s['index'],selected='take-'+str(s['index']),source=str(file)))
    export_film(work,dict(plan=dict(workflow=WORKFLOW,shots=shots,output=[960,544],fps=24,duration=3.23,audio=str(audio)),story=story))
    checked=read(work/'checks.json')
    assert checked['videoAssembly']=='stream-copy' and checked['creditsApplied'] is False
    assert checked['frames']==78 and checked['dimensions']==[960,544]
    def pixels(file):
        output=subprocess.check_output(['ffmpeg','-v','error','-i',str(file),'-map','0:v','-f','framemd5','-'],text=True)
        return [l.rsplit(',',1)[-1].strip() for l in output.splitlines() if not l.startswith('#')]
    assert pixels(work/'film.mp4')==sum([pixels(s['source']) for s in story],[])


def test_refresh_preserves_cuts_reference_and_old_takes_while_correcting_the_board(creation):
    f,_=prepare_hybrid(creation)
    generate(creation,f['id'],Export(revision=f['revision'],requestId='hybrid-first-scene'),0)
    creation.update_job(f['id'],'hybrid-first-scene','ready','Ready')
    f=creation.load(f['id']);old_plan=read(f['plan'])
    f.pop('vocalTiming',None);old_plan.pop('vocalTiming',None)
    for s in f['scenes']:s['type']='performance';s['timing']={'words':[],'spans':[],'leadingRest':0}
    write(f['plan'],old_plan);creation.save(f)
    req=Export(revision=f['revision'],requestId='correct-vocal-map')
    film_vocal_timing.submit_refresh(creation,f['id'],req)
    film_vocal_timing.submit_refresh(creation,f['id'],req)
    work=creation.folder(f['id'])/'jobs'/req.requestId
    asyncio.run(film_vocal_timing.refresh(creation,f['id'],req.requestId,work,read(work/'input.json')))
    fixed=creation.load(f['id']);new_plan=read(fixed['plan'])
    assert [s['type'] for s in fixed['scenes']]==['narrative','performance','narrative']
    assert fixed['scenes'][0]['selected']=='hybrid-first-scene'
    assert fixed['scenes'][0]['takes'][0]['timingOutdated'] is True
    assert fixed['vocalTiming']['firstVocal']==10.5
    assert [(s['startFrame'],s['endFrame'],s['references']) for s in old_plan['shots']]==[(s['startFrame'],s['endFrame'],s['references']) for s in new_plan['shots']]
    assert (work/'previous-manifest.json').exists() and (work/'previous-plan.json').exists()
