import asyncio
import io
import json
import math
import re
import subprocess
import time
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from .api import Settings, create_app
from .music_video import schedule, validate_cues, SILENT_DIRECTION
from .music_video_render import compose, probe, subtitles


def audio(seconds=12):
    out = io.BytesIO()
    with wave.open(out, 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(8000); f.writeframes(b'\0\0' * round(8000 * seconds))
    return out.getvalue()


@pytest.mark.parametrize('join', ['cut','dissolve','continue'])
def test_schedule_covers_entire_song_and_accounts_for_overlap(join):
    for duration in [1,5,5.04,6.3,30,259.2,600]:
        for count in [None,1,4]:
            plan = schedule(duration,5,join,count)
            shots = plan['placements']; overlap = plan['overlapFrames']
            assert shots[0]['startFrame']==0 and shots[-1]['endFrame']==math.ceil(duration*24)
            assert max(s['asset'] for s in shots)<plan['clipCount']
            assert all(b['startFrame']==a['endFrame']-overlap for a,b in zip(shots,shots[1:]))
            assert sum(s['endFrame']-s['startFrame'] for s in shots)-overlap*(len(shots)-1)==plan['frames']
            assert plan['clipCount'] == (plan['fullClipCount'] if count is None else min(count,plan['fullClipCount']))


def test_untrusted_and_missing_word_timing_rejected_before_render():
    cues=[{'words':[{'text':'Hello','start':1,'end':2}]}]
    assert validate_cues(cues,10,'[Verse]\nHello')==cues
    for value in [[],[{'words':[{'text':'Different','start':1,'end':2}]}],[{'words':[{'text':'Hello','start':None,'end':2}]}],[{'words':[{'text':'Hello','start':1,'end':100}]}]]:
        with pytest.raises(ValueError): validate_cues(value,10,'Hello')


@pytest.mark.parametrize('join,count,lyric', [('cut',None,False),('dissolve',None,True),('continue',1,False)])
def test_real_export_preserves_duration_with_cuts_blends_and_repeats(tmp_path, join, count, lyric):
    if lyric:
        from .music_video_render import requirements
        try: requirements(True)
        except ValueError: pytest.skip('This machine lacks FFmpeg libass; covered on the Linux backend')
    song=tmp_path/'song.wav';song.write_bytes(audio(6.3))
    plan={**schedule(6.3,5,join,count),'aspect':'16:9'}
    source=tmp_path/'source.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=96x54:rate=24','-t','5','-c:v','libx264','-pix_fmt','yuv420p',str(source)],check=True)
    data={'plan':plan,'clips':[{'path':str(source)} for _ in range(plan['clipCount'])],'audio':str(song),'dimensions':[96,54],
          'cues':[{'words':[{'text':'Hello {world}\\n','start':1,'end':2}]}] if lyric else []}
    compose(tmp_path,data)
    info=probe(tmp_path/'movie.mp4');v=next(s for s in info['streams'] if s['codec_type']=='video');a=next(s for s in info['streams'] if s['codec_type']=='audio')
    assert int(v['nb_frames'])==math.ceil(6.3*24)
    assert abs(float(v['duration'])-6.3)<1/24
    assert abs(float(a['duration'])-6.3)<.05
    if lyric: assert '｛world｝' in (tmp_path/'lyrics.ass').read_text()


def test_plan_review_render_resume_and_song_ownership(tmp_path, monkeypatch):
    from . import music_video
    original_routes = music_video.routes
    calls=[]; fail_once=[True]
    def wrapped(service, ops):
        def folder(job_id):
            p=tmp_path/'data/video'/job_id;p.mkdir(parents=True,exist_ok=True);return p
        def start(job_id,payload,resume=None):
            async def job():
                calls.append(payload)
                if payload['kind'] == 'alignment':
                    return {'cues': [{'words': [{'text': text, 'start': i+1, 'end': i+1.5} for i, text in enumerate(payload['lyrics'].split())]}]}
                if payload['slot']==1 and fail_once[0]: fail_once[0]=False;raise ValueError('Test clip failure')
                (folder(job_id)/'background.mp4').write_bytes(b'fixture')
                return {'muted':True}
            return service.submit(job_id,'video-motion',payload,job,serialized=False)
        async def process(command,work,*args,**kwargs): (work/'movie.mp4').write_bytes(b'fixture')
        return original_routes(service,{'start':start,'folder':folder,'run_process':process})
    monkeypatch.setattr(music_video,'routes',wrapped)
    config=Settings(tmp_path/'data',tmp_path/'model',tmp_path/'vae','x'*40)
    app=create_app(config,start_worker=False)
    async def proposal(prompt,schema,*args,**kwargs):
        if 'theme' in schema['properties']: result={'theme':'A city waking under copper light.'}
        else:
            count=int(re.search(r'exactly (\d+) scenes',prompt)[1])
            assert SILENT_DIRECTION in prompt
            result={'scenes':[{'name':f'Scene {i}','prompt':'Slow camera movement through a quiet city.'} for i in range(count)]}
        return [{'type':'agentMessage','text':json.dumps(result)}],'test'
    app.state.assistance.account.turn=proposal
    with TestClient(app,headers={'Authorization':'Bearer '+config.token}) as c:
        t=c.post('/api/songs/import',content=audio(),headers={'x-filename':'song.wav'}).json()['id']
        other=c.post('/api/songs/import',content=audio(),headers={'x-filename':'other.wav'}).json()['id']
        def wait(job_id):
            for _ in range(160):
                result=next(j for j in c.get(f'/api/takes/{t}/music-video').json()['jobs'] if j['id']==job_id)
                if result['state'] not in {'queued','running','waiting-for-resource'}: return result
                time.sleep(.05)
            raise AssertionError('Job did not finish')
        body={'requestId':'plan-test-001','theme':'Copper city','coverage':'full','clipCount':4,'clipSeconds':5,'join':'continue','showLyrics':False}
        assert c.post(f'/api/takes/{t}/music-video/plan',json=body).status_code==202
        plan=wait(body['requestId']);assert plan['state']=='succeeded',plan
        assert plan['result']['clipCount']==3 and len(plan['result']['scenes'])==3
        assert calls==[] # Planning never renders.
        assert c.post(f'/api/takes/{t}/music-video/plan',json={**body,'theme':'changed'}).status_code==409
        render={'requestId':'render-test-001','planId':body['requestId']}
        assert c.post(f'/api/takes/{other}/music-video/render',json=render).status_code==404
        assert c.post(f'/api/takes/{t}/music-video/render',json=render).status_code==202
        result=wait(render['requestId']);assert result['state']=='failed'
        assert [p['slot'] for p in calls]==[0,1]
        retry=c.post(f'/api/takes/{t}/music-video/render',json={**render,'requestId':'render-test-002'});assert retry.status_code==202
        result=wait('render-test-002');assert result['state']=='succeeded',result
        assert [p['slot'] for p in calls]==[0,1,1,2] # Finished first clip reused.
        assert calls[1]['continuationJobId']==calls[2]['continuationJobId']
        from .h3_prompts import FIRST_FRAME_INSTRUCTION
        assert calls[0]['prompt'].startswith('integrated_multimodal_description: [Shot 1] ')
        assert calls[1]['prompt'].startswith(FIRST_FRAME_INSTRUCTION + '\n\n')
        assert calls[2]['prompt'].startswith(FIRST_FRAME_INSTRUCTION + '\n\n')
        assert calls[3]['prompt'].startswith('integrated_multimodal_description: [Shot 1] ')
        assert all(not p.get('audioStart') and SILENT_DIRECTION in p['prompt'] for p in calls)
        assert c.get(result['result']['videoUrl']).status_code==200
        assert c.get(result['result']['videoUrl']).headers.get('content-disposition') is None
        assert 'attachment' in c.get(result['result']['downloadUrl']).headers['content-disposition']
        assert c.get(result['result']['videoUrl'],headers={'Authorization':''}).status_code==401
        # Lyric omission is explicit, reaches the composer, and never alters the saved plan.
        from . import music_video_render
        monkeypatch.setattr(music_video_render, 'requirements', lambda lyrics=False: None)
        lyric_plan={**body,'requestId':'lyric-plan-001','showLyrics':True,'lyrics':'First Missing Last'}
        assert c.post(f'/api/takes/{t}/music-video/plan',json=lyric_plan).status_code==202
        assert wait('lyric-plan-001')['state']=='succeeded'
        cue_data=[{'words':[{'text':'First','start':1,'end':2},{'text':'Missing','start':None,'end':None},{'text':'Last','start':3,'end':4}]}]
        request={'requestId':'lyric-render-001','planId':'lyric-plan-001','cues':cue_data}
        before=len(calls)
        assert c.post(f'/api/takes/{t}/music-video/render',json=request).status_code==202
        assert 'Lyrics match, but 1 words' in wait('lyric-render-001')['error']
        assert len(calls)==before
        assert c.post(f'/api/takes/{t}/music-video/render',json={**request,'requestId':'lyric-render-002','omitUnusableWords':True}).status_code==202
        result=wait('lyric-render-002');assert result['state']=='succeeded',result
        assert result['result']['omittedLyricWords']==1
        sent=json.loads((tmp_path/'data/music-videos/lyric-plan-001/exports/lyric-render-002/input.json').read_text())
        assert [w['text'] for cue in sent['cues'] for w in cue['words']]==['First','Last']
        assert sent['plan']['lyrics']=='First Missing Last'
        # Corrected text validates against the reviewed sheet without regenerating clips.
        before = len(calls)
        corrected = [{'words': [{'text': 'First', 'start': 1, 'end': 2}, {'text': 'Last', 'start': 3, 'end': 4},
                                {'text': 'Last', 'start': 5, 'end': 6}]}]
        update = {**request, 'requestId': 'lyric-edit-render-001', 'lyrics': 'First Last Last', 'cues': corrected}
        assert c.post(f'/api/takes/{t}/music-video/render', json=update).status_code == 202
        result = wait(update['requestId']); assert result['state'] == 'succeeded', result
        assert len(calls) == before
        exported = json.loads((tmp_path/'data/music-videos/lyric-plan-001/exports/lyric-edit-render-001/input.json').read_text())
        assert exported['cues'] == corrected
        assert exported['plan']['lyrics'] == 'First Last Last'
        assert json.loads((tmp_path/'data/music-videos/lyric-plan-001/plan.json').read_text())['lyrics'] == 'First Missing Last'
        assert c.post(f'/api/takes/{t}/music-video/render', json={**update, 'requestId': 'lyric-edit-render-002', 'lyrics': 'Wrong text'}).status_code == 202
        assert 'does not match' in wait('lyric-edit-render-002')['error']
        assert len(calls) == before
        # Re-aligning edited text on the same storyboard cannot reuse stale words.
        for suffix, text in [('003', 'First Last'), ('004', 'First Last Again'), ('005', 'First Last Again')]:
            request_id = 'lyric-edit-render-' + suffix
            assert c.post(f'/api/takes/{t}/music-video/render', json={**update, 'requestId': request_id, 'lyrics': text, 'cues': []}).status_code == 202
            result = wait(request_id); assert result['state'] == 'succeeded', result
        assert len(calls) == before + 2
        assert all(p['kind'] == 'alignment' for p in calls[before:])



def test_complete_lyric_sheet_reports_gaps_and_requires_explicit_omission():
    import copy
    cues=[{'words':[{'text':'First','start':1,'end':2}]},
          {'words':[{'text':'Missing','start':None,'end':None},{'text':'line','start':None,'end':None}]},
          {'words':[{'text':'Clash','start':1.5,'end':2.5},{'text':'Last','start':3,'end':4}]}]
    original=copy.deepcopy(cues)
    lyrics='[Verse]\nFirst\nMissing line\nClash Last'
    with pytest.raises(ValueError,match=r'Lyrics match, but 2 words have no timestamps and 1 have conflicting timing'):
        validate_cues(cues,10,lyrics)
    clean=validate_cues(cues,10,lyrics,omit_unusable=True)
    assert [w['text'] for c in clean for w in c['words']]==['First','Last']
    assert cues==original
    with pytest.raises(ValueError,match='does not match'):
        validate_cues(cues,10,'Changed lyrics',omit_unusable=True)
    with pytest.raises(ValueError,match='No lyric words have usable timing'):
        validate_cues([cues[1]],10,'Missing line',omit_unusable=True)


def test_renderer_and_aligner_agree_on_inline_brackets():
    cues=[{'words':[{'text':'Echo','start':1,'end':2},{'text':'[again]','start':2,'end':3}]}]
    assert validate_cues(cues,10,'[Verse]\nEcho [again]')==cues
