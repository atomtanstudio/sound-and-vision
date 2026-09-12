import asyncio
import copy
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from .test_film_review import review
from .film_review import Retry, read, write
from .film_intelligence import normalize_plan, resolve_input, plan_repair, review_repair
from .openai_account import Account


def plan(**changes):
    return dict(intent='One silent continuous closing shot.',observations=['Source has several views.'],
        method='frame-regenerate',scope='entire-scene',startSeconds=0,endSeconds=6,anchorFrame=0,
        sourceStartSeconds=0,sourceEndSeconds=0,
        cutPolicy='single-shot',speechPolicy='silent',action='The woman stands quietly with relaxed closed lips in one static camera setup.',
        continuity='Same coat and corner.',explanation='Rebuild one view without copying the unwanted cuts.',
        needsClarification=False,question='',**changes)


def snapshot(service,key):
    service.submit(key,Retry(revision=1,requestId='smart-plan-test',method='smart',correction='Stop talking and jumping between shots.'),0)
    work=service.folder(key)/'jobs/smart-plan-test'
    return work,read(work/'input.json')


def test_single_shot_intent_cannot_reuse_the_cut_heavy_source_video(review):
    service,key,_,_=review;_,data=snapshot(service,key)
    proposed=plan();proposed['method']='source-edit'
    normalized=normalize_plan(proposed,data,[0,48,143])
    assert normalized['method']=='frame-regenerate'
    resolved=resolve_input(data,normalized)
    assert resolved['shot']['type']=='narrative' and resolved['timing']['words']==[]
    assert resolved['correction']==proposed['action']
    assert data['method']=='smart' and data['shot']['type']=='performance' # Original snapshot is untouched.


def test_interval_protects_source_join_and_unknown_anchor_or_ambiguous_intent_stops(review):
    service,key,_,_=review;_,data=snapshot(service,key)
    proposed=plan();proposed.update(scope='interval',startSeconds=2,endSeconds=5,anchorFrame=96)
    normalized=normalize_plan(proposed,data,[0,48,96,143])
    assert normalized['anchorFrame']==48 and normalized['repairRange']=={'startFrame':48,'endFrame':120}
    proposed['anchorFrame']=17
    with pytest.raises(ValueError):normalize_plan(proposed,data,[0,48,96,143])
    proposed.update(anchorFrame=0,needsClarification=True,question='Which person should sing?')
    with pytest.raises(ValueError,match='Which person'):normalize_plan(proposed,data,[0])


@pytest.mark.parametrize('cuts,mouth,expected',[([3.0],'not-assessable','needs-review'),([], 'possible-mouthing','needs-review'),([], 'not-assessable','uncertain')])
def test_visual_planner_receives_frames_checkpoints_once_and_review_overrides_missed_cuts(review,monkeypatch,cuts,mouth,expected):
    service,key,_,_=review;work,data=snapshot(service,key)
    source=Path(data['baseTake']['source'])
    subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=24:duration=6','-c:v','libx264','-pix_fmt','yuv420p',str(source)],check=True)
    calls=[]
    async def turn(prompt,schema=None,reference_images=()):
        assert reference_images and all(Path(p).is_file() for p in reference_images)
        calls.append(prompt)
        result=plan() if len(calls)==1 else {'result':'no-obvious-issue','summary':'Seems consistent in the sampled frames.','findings':[],'mouth':mouth}
        return [{'type':'agentMessage','text':json.dumps(result)}],'test-vision'
    service.account=SimpleNamespace(turn=turn)
    resolved=asyncio.run(plan_repair(service,key,'smart-plan-test',work,data))
    assert asyncio.run(plan_repair(service,key,'smart-plan-test',work,data))==resolved and len(calls)==1
    assert read(work/'input.json')['correction']=='Stop talking and jumping between shots.'
    assert service.load(key)['scenes'][0]['takes'][-1]['smartPlan']['intent']==plan()['intent']
    (work/'background.mp4').write_bytes(source.read_bytes());write(work/'checks.json',{'frames':144})
    monkeypatch.setattr('backend.film_intelligence.detected_cuts',lambda _: cuts)
    asyncio.run(review_repair(service,key,'smart-plan-test',work,resolved))
    result=read(work/'checks.json')['aiReview']
    assert result['result']==expected
    if cuts:assert '3.00s' in result['findings'][0]
    assert 'not continuous video' in calls[1].lower() and len(calls)==2


def test_account_visual_attachments_cannot_read_arbitrary_files(tmp_path):
    root=tmp_path/'project';root.mkdir();image=root/'frame.jpg';image.write_bytes(b'image fixture')
    account=Account(root)
    inputs=account.image_inputs([image])
    assert inputs[0]['type']=='image' and inputs[0]['url'].startswith('data:image/jpeg;base64,')
    secret=root/'credentials.json';secret.write_text('secret')
    external=tmp_path/'external.jpg';external.write_bytes(b'outside')
    for paths in ([secret],[external],[image]*5):
        with pytest.raises(ValueError):account.image_inputs(paths)


def test_reuse_rejects_cuts_short_ranges_and_performance_timing(review):
    service,key,_,_=review;_,data=snapshot(service,key)
    data['baseTake']['checks']={'possibleInternalCuts':[3.0]}
    proposed=plan();proposed.update(method='reuse-shot',sourceStartSeconds=3,sourceEndSeconds=6)
    normalized=normalize_plan(proposed,data,[0,48,143])
    assert normalized['method']=='reuse-shot' and normalized['playbackSpeed']==.5
    assert normalized['sourceRange']=={'startFrame':72,'endFrame':144}
    proposed.update(sourceStartSeconds=1,sourceEndSeconds=6)
    with pytest.raises(ValueError,match='contains a measured cut'):normalize_plan(proposed,data,[0])
    proposed.update(sourceStartSeconds=4,sourceEndSeconds=6)
    with pytest.raises(ValueError,match='at least half'):normalize_plan(proposed,data,[0])
    proposed.update(sourceStartSeconds=3,speechPolicy='original-performance')
    with pytest.raises(ValueError,match='silent full-scene'):normalize_plan(proposed,data,[0])


def test_reuse_extracts_the_chosen_shot_and_keeps_exact_duration_without_h3(review):
    from .film_worker import render_reuse, probe
    service,key,_,_=review;work,data=snapshot(service,key)
    source=Path(data['baseTake']['source'])
    subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','color=blue:size=160x90:rate=24:duration=3',
        '-f','lavfi','-i','color=red:size=160x90:rate=24:duration=3',
        '-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]','-map','[v]',
        '-c:v','libx264','-pix_fmt','yuv420p',str(source)],check=True)
    data['baseTake']['checks']={'possibleInternalCuts':[3.0]}
    proposed=plan();proposed.update(method='reuse-shot',sourceStartSeconds=3,sourceEndSeconds=6)
    resolved=resolve_input(data,normalize_plan(proposed,data,[0]))
    render_reuse(work,resolved)
    media=probe(work/'background.mp4');video=next(s for s in media['streams'] if s['codec_type']=='video')
    assert int(video['nb_frames'])==144 and float(video['duration'])==6
    assert not any(s['codec_type']=='audio' for s in media['streams'])
    pixels=subprocess.check_output(['ffmpeg','-v','error','-i',str(work/'background.mp4'),
        '-vf','scale=1:1','-pix_fmt','rgb24','-f','rawvideo','-'])
    assert min(pixels[0::3])>230 and max(pixels[2::3])<20 # Every frame comes from the red shot.
    assert read(work/'checks.json')['method']=='reuse-shot'
