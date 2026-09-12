import copy
import subprocess
from pathlib import Path

import pytest
from fastapi import HTTPException
from .test_film_review import review
from .film_review import Retry, read, write
from .film_worker import splice_range, probe, render_range, prepare_preview


def test_range_validated_and_preserved_in_immutable_snapshot(review):
    service,key,_,_=review
    invalid=[{}, {'repairStartFrame':12,'repairEndFrame':20},
             {'repairStartFrame':0,'repairEndFrame':145}]
    for fields in invalid:
        with pytest.raises(HTTPException):service.submit(key,Retry(revision=1,requestId='range-invalid-01',method='frame-regenerate',correction='Walk forward',**fields),0)
    result=service.submit(key,Retry(revision=1,requestId='range-valid-0001',method='frame-regenerate',correction='Walk forward',repairStartFrame=48,repairEndFrame=144),0)
    data=read(service.folder(key)/'jobs/range-valid-0001/input.json')
    assert data['repairRange']=={'startFrame':48,'endFrame':144}
    assert result['scenes'][0]['selected']=='original'
    assert result['scenes'][0]['takes'][-1]['repairRange']==data['repairRange']


def video(path,source,seconds):
    subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i',source,'-t',str(seconds),'-c:v','libx264','-pix_fmt','yuv420p',str(path)],check=True)


def hashes(path):
    result=subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-map','0:v:0','-f','framemd5','-'],text=True)
    return [line.rsplit(',',1)[1].strip() for line in result.splitlines() if not line.startswith('#')]


def test_range_splice_retains_every_outside_frame_and_browser_preview_decodes(tmp_path):
    source=tmp_path/'source.mp4';patch=tmp_path/'replacement.mp4';target=tmp_path/'output.mp4'
    video(source,'testsrc2=size=160x90:rate=24',6)
    video(patch,'color=blue:size=160x90:rate=24',2)
    splice_range(source,patch,target,48,96,144,24)
    original,changed,new=hashes(source),hashes(target),hashes(patch)
    assert len(changed)==144
    assert changed[:48]==original[:48] and changed[96:]==original[96:]
    assert changed[48:96]==new
    audio=tmp_path/'audio.wav'
    subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','sine=frequency=440:duration=6',str(audio)],check=True)
    preview=prepare_preview(target,audio,{'start':0,'end':6},tmp_path/'preview')
    stream=next(s for s in probe(preview)['streams'] if s['codec_type']=='video')
    assert stream['profile']!='High 4:4:4 Predictive' and int(stream['nb_frames'])==144


def test_range_passes_only_start_frame_and_rebased_audio_to_generator(review,monkeypatch):
    service,key,_,_=review
    service.submit(key,Retry(revision=1,requestId='range-source-001',method='frame-regenerate',correction='Walk forward',repairStartFrame=48,repairEndFrame=144),0)
    work=service.folder(key)/'jobs/range-source-001';data=read(work/'input.json');captured=[]
    monkeypatch.setattr('backend.film_worker.run',lambda args:Path(args[-1]).write_bytes(b'frame'))
    def generate(folder,snapshot):
        captured.append(copy.deepcopy(snapshot));(folder/'background.mp4').write_bytes(b'patch')
        write(folder/'checks.json',{'possibleInternalCuts':[]})
    monkeypatch.setattr('backend.film_worker.render_scene',generate)
    monkeypatch.setattr('backend.film_worker.splice_range',lambda source,patch,target,*args:target.write_bytes(b'assembled'))
    render_range(work,data)
    patch=captured[0]
    assert patch['method']=='generate' and patch['frameAnchor']
    assert 'baseTake' not in patch and 'repairVersion' not in patch
    assert patch['shot']['start']==2 and patch['shot']['end']==6
    assert patch['shot']['generationSeconds']==4
    assert patch['shot']['references']==[str(work/'replacement/opening.png')]
    assert patch['timing']['words']==[{'text':'across','start':3.8,'end':4,'review':'Check'}]
    assert read(work/'checks.json')['preservedFrames']=={'before':48,'after':0}
