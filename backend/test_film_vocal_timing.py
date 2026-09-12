import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from . import film_vocal_timing as timing
from .film_audio_drive import prompt,storyboard_windows
from .film_voice import voice_contract
from .film_review import write


def test_generated_visual_notes_do_not_leak_the_song_clock_into_clip_time():
    assert timing.visual_text('Locked portrait: at 69.774s he raises his right thumb.',265)=='Locked portrait: he raises his right thumb.'
    assert timing.visual_text('He holds the cloth by 130.75s, then lowers it.',265)=='He holds the cloth then lowers it.'
    assert timing.visual_text('20–30s. Same worker and wardrobe.',265)=='Same worker and wardrobe.'
    assert '1990s' in timing.visual_text('Set around 1990s with worn furnishings.',265)


def recording(tmp_path):
    audio=tmp_path/'song.flac';audio.write_bytes(b'original song')
    plan={'audio':str(audio),'duration':75.,'lyrics':'He worked the press','treatment':'performance'}
    plan['vocalTiming']={'version':2,'sourceSha256':hashlib.sha256(audio.read_bytes()).hexdigest(),
        'lyricsSha256':timing.lyrics_key(plan['lyrics']),'duration':75.,'cues':[
            {'text':'He worked the press','words':[{'text':'He','start':60.814,'end':60.895,'review':None},
              {'text':'worked','start':61.016,'end':61.297,'review':None},
              {'text':'the','start':64.,'end':64.2,'review':None},
              {'text':'press','start':64.3,'end':64.8,'review':None}]}]}
    return plan


def test_performance_treatment_never_marks_the_instrumental_first_minute_as_singing(tmp_path):
    plan=recording(tmp_path)
    shots=storyboard_windows(75,[9,20,30,38,50,60,69,75])
    for i,shot in enumerate(shots):
        local=timing.apply(plan,shot,True)
        shot['prompt']='Locked portrait: the lead watches the steel press.'
        data={'plan':plan,'shot':shot,'timing':local,'sceneContinuity':'Same lead, same jacket.'}
        timing.validate_render(data)
        text=prompt(data)
        if i<6:
            assert shot['type']=='narrative' and not local['words'] and local['source']=='recording'
            assert 'quiet observer for this entire shot' in text
            assert '<d>' not in text and 'follows the audible syllables' not in text
        elif i==6:
            assert shot['type']=='performance' and local['leadingRest']==.814
            assert '0.000 to 0.814 seconds' in text
            assert '0.814 to 0.895 seconds' in text and '1.016 to 1.297 seconds' in text
            assert '0.895 to 1.016 seconds' in text and '1.297 to 4.000 seconds' in text
            assert '4.800 to' in text # Ending rest includes discarded H3 padding.


def test_missing_mismatched_and_stale_timing_cannot_submit_a_singing_render(tmp_path):
    plan=recording(tmp_path);shot=storyboard_windows(75,[15,30,45,60,75])[-1]
    local=timing.apply(plan,shot,True)
    data={'plan':plan,'shot':shot,'timing':local}
    timing.validate_render(data)
    with pytest.raises(ValueError):timing.validate_render({**data,'timing':{**local,'words':[]}})
    with pytest.raises(ValueError):timing.validate_render({**data,'shot':{**shot,'type':'narrative'}})
    with pytest.raises(ValueError):timing.scene({**plan,'vocalTiming':None},shot)
    changed={**plan,'vocalTiming':{**plan['vocalTiming'],'sourceSha256':'different recording'}}
    with pytest.raises(ValueError):timing.validate_render({**data,'plan':changed})


def test_cut_movement_recomputes_vocal_status_and_local_entrance(tmp_path):
    plan=recording(tmp_path)
    before={'start':50.,'end':60.,'generationSeconds':10.125,'performanceIntent':True}
    assert timing.apply(plan,before)['words']==[] and before['type']=='narrative'
    after={**before,'end':62.,'generationSeconds':12.25}
    assert timing.apply(plan,after)['leadingRest']==10.814 and after['type']=='performance'
    story={**plan,'treatment':'mixed'}
    local=timing.apply(story,after,False)
    assert local['words'] and after['type']=='narrative'
    assert voice_contract({'shot':after,'timing':local})['mode']=='silent'


def test_alignment_reuse_requires_the_same_audio_and_lyrics(tmp_path,monkeypatch):
    plan=recording(tmp_path);root=tmp_path/'data';work=tmp_path/'work';work.mkdir()
    reviews=SimpleNamespace(root=root/'film-reviews',store=SimpleNamespace(root=root))
    prior=reviews.root/'old/jobs/prepare-old/input.json'
    write(prior,{'plan':plan})
    candidate={**plan['vocalTiming'],'modelRevision':'test-model'}
    result=root/'video/film-align-prepare-old/result.json';write(result,candidate)
    # This test supplies only model-lock lookup, never a renderer or speech model.
    import backend.film_review as review
    real_read=review.read
    monkeypatch.setattr(review,'read',lambda p:{'revision':'test-model'} if Path(p).name=='alignment.lock.json' else real_read(p))
    resolved=asyncio.run(timing.ensure(reviews,plan,work,lambda _:None))
    assert resolved['sourceSha256']==candidate['sourceSha256']
    assert resolved['sourceAlignment']==str(result)
    assert (work/'vocal-timing-reuse.json').exists()
    assert timing.song_map({**plan,'vocalTiming':resolved})['firstVocal']==60.814
