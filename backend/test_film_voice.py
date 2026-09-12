import asyncio
import copy
import json
import math
import struct
import wave
from types import SimpleNamespace

import pytest
from .film_voice import voice_contract, voice_direction
from .film_worker import generation_prompt, repair_prompt, prepare_vocal_reference
from .film_review import read, write


def example(kind='performance'):
    return {'shot':{'type':kind,'start':30,'end':34.75,'generationSeconds':5,
                    'startFrame':720,'endFrame':834,'prompt':'A person walking.'},
            'plan':{'fps':24,'language':'en'},'sceneContinuity':'Same person and coat.',
            'correction':'Match the original vocal and pauses.',
            'timing':{'words':[{'text':'One','start':1,'end':1.5},{'text':'Two','start':3,'end':4.5}]}}


def test_prompt_voice_contract_is_identical_for_creation_and_source_edit():
    data=example();policy=voice_contract(data)
    assert policy['restWindows']==[{'start':0,'end':1},{'start':1.5,'end':3},{'start':4.5,'end':5}]
    for prompt in (generation_prompt(data),repair_prompt(data)):
        assert voice_direction(data) in prompt
        assert 'From 0.000 to 1.000 seconds' in prompt
        assert 'From 1.500 to 3.000 seconds' in prompt
        assert 'From 4.500 to 5.000 seconds' in prompt
        assert '<d>[English] One.</d>' in prompt and '(S1)' in prompt
    silent=example('narrative')
    for prompt in (generation_prompt(silent),repair_prompt(silent)):
        assert '<Audio' not in prompt and '(S1)' not in prompt and '<d>' not in prompt
        assert 'jaw stays at rest' in prompt
    silent['shot']['type']='performance';silent['timing']['words']=[]
    assert voice_contract(silent)['mode']=='silent'


def test_overlapping_alignment_preserves_the_lyric_word_order():
    data=example();data['timing']['words']=[{'text':'thumb.','start':1.879,'end':2.081},
                                         {'text':'Then','start':1.863,'end':2.267}]
    policy=voice_contract(data)
    assert policy['vocalWindows']==[{'start':1.863,'end':2.267,'words':['thumb.','Then']}]
    assert '<d>[English] thumb. Then.</d>' in voice_direction(data)


@pytest.mark.parametrize('start,end',[(-.1,1),(2,1),(1,5),(float('nan'),2),(1,float('inf'))])
def test_invalid_vocal_timing_stops_before_submission(start,end):
    data=example();data['timing']['words']=[{'text':'Word','start':start,'end':end}]
    with pytest.raises(ValueError,match='Invalid measured'):generation_prompt(data)


@pytest.mark.parametrize('locked',[False,True])
def test_audio_reference_preserves_scene_and_silences_rounded_tail(tmp_path,locked):
    # A voice-like tone continues past the cut. The next scene must not leak
    # into the 0.25-second padding required by the generator.
    data=example();data['shot'].update(start=.5,end=5.25)
    if locked:data['plan']['renderProfile']='singularity-first-pass'
    source=tmp_path/'source.wav';target=tmp_path/'reference.wav';rate=48000
    samples=[int(12000*math.sin(2*math.pi*330*i/rate)) for i in range(rate*6)]
    with wave.open(str(source),'wb') as audio:
        audio.setparams((2,2,rate,0,'NONE','not compressed'))
        audio.writeframes(b''.join(struct.pack('<hh',v,v) for v in samples))
    prepare_vocal_reference(target,source,data['shot'],voice_contract(data))
    with wave.open(str(target),'rb') as audio:
        assert audio.getnframes()==5*rate
        raw=audio.readframes(5*rate)
    if locked:
        # Even low-confidence or missing word alignments must not remove a
        # single recorded sample from the visible scene or leak the next one.
        expected=b''.join(struct.pack('<hh',v,v) for v in samples[int(.5*rate):int(5.25*rate)])
        assert raw[:len(expected)]==expected
        assert set(raw[len(expected):])=={0}
        return
    # The conditioning waveform now has sample-level silence in every rest,
    # as well as the rounded tail. The source recording is never modified.
    for a,b in [(0,1),(1.501,3),(4.501,5)]:
        assert set(raw[int(a*rate)*4:int(b*rate)*4])=={0}
    assert raw[rate*4:int(1.5*rate)*4]==b''.join(struct.pack('<hh',v,v) for v in samples[int(1.5*rate):2*rate])
    assert any(raw[3*rate*4:int(4.5*rate)*4])
    assert set(raw[int(4.75*rate)*4:])=={0}


def test_locked_vocal_prompt_follows_audio_instead_of_uncertain_word_gaps():
    data=example();data['plan']['renderProfile']='singularity-first-pass'
    data['timing']['words'][1].update(confidence=0,review='Low alignment confidence')
    policy=voice_contract(data);direction=voice_direction(data)
    assert policy['timingAuthority']=='recorded-audio' and policy['gateVersion']==3
    assert 'continuous recording is the timing authority' in direction
    assert 'held notes' in direction and '(S1)' in direction
    assert 'From 1.500 to 3.000' not in direction and '<d>' not in direction


def test_review_preserves_submitted_audio_policy_and_does_not_certify_estimated_rests(tmp_path,monkeypatch):
    from .film_intelligence import review_voice
    data=example();data['plan']['renderProfile']='singularity-first-pass';calls=[]
    async def turn(prompt,schema,reference_images):
        calls.append(prompt)
        return [{'type':'agentMessage','text':json.dumps({'result':'uncertain','summary':'Playback required.',
                'findings':[],'mouth':'not-assessable'})}], 'fixture-model'
    service=SimpleNamespace(account=SimpleNamespace(turn=turn),update_job=lambda *args:None)
    monkeypatch.setattr('backend.film_intelligence.inspection_sheet',lambda *args: ({'sampling':'frames'},tmp_path/'sheet.jpg'))
    submitted={**voice_contract(data),'submittedMarker':'retained'}
    write(tmp_path/'checks.json',{'voicePolicy':submitted})
    asyncio.run(review_voice(service,'film','job',tmp_path,data))
    result=read(tmp_path/'checks.json')
    assert result['voicePolicy']==submitted
    assert 'not verified silence boundaries' in calls[0]
    assert result['aiReview']['result']=='uncertain'


@pytest.mark.parametrize('mouth,expected',[('possible-mouthing','needs-review'),('not-assessable','uncertain'),('no-obvious-issue','no-obvious-issue')])
def test_initial_voice_review_is_cached_and_flags_uncertain_faces(tmp_path,monkeypatch,mouth,expected):
    from .film_intelligence import review_voice
    data=example('narrative');calls=[]
    async def turn(prompt,schema,reference_images):
        calls.append(prompt)
        return [{'type':'agentMessage','text':json.dumps({'result':'no-obvious-issue','summary':'Sampled evidence only.',
                'findings':[],'mouth':mouth})}], 'fixture-model'
    service=SimpleNamespace(account=SimpleNamespace(turn=turn),update_job=lambda *args:None)
    monkeypatch.setattr('backend.film_intelligence.inspection_sheet',lambda *args: ({'sampling':'frames'},tmp_path/'sheet.jpg'))
    write(tmp_path/'checks.json',{})
    asyncio.run(review_voice(service,'film','job',tmp_path,data))
    asyncio.run(review_voice(service,'film','job',tmp_path,data))
    result=read(tmp_path/'checks.json')
    assert result['aiReview']['result']==expected and len(calls)==1
    assert 'not continuous video or audio' in calls[0] and result['voicePolicy']['mode']=='silent'


def test_frame_aligned_scene_duration_survives_song_timestamp_subtraction():
    data=example()
    data['shot'].update(start=3676/24,end=3936/24,generationSeconds=260/24)
    assert data['shot']['end']-data['shot']['start'] > data['shot']['generationSeconds']
    data['timing']['words']=[{'text':'couch.','start':10.299,'end':10.823}]
    policy=voice_contract(data)
    assert policy['visibleDuration']==260/24
    assert policy['vocalWindows'][0]['words']==['couch.']
    assert policy['restWindows'][-1]['end']==260/24


@pytest.mark.parametrize('duration,generated',[(5,5-1e-5),(0,5),(-1,5),(5,float('nan')),
                                               (float('nan'),5),(5,float('inf')),(float('inf'),5)])
def test_invalid_scene_durations_still_stop_before_submission(duration,generated):
    data=example();data['shot'].update(start=0,end=duration,generationSeconds=generated)
    with pytest.raises(ValueError,match='Invalid scene duration'):voice_contract(data)
