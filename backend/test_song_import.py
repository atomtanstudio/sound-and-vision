import io
import wave
from .test_api import client
from .api import Store


def wav_bytes():
    out=io.BytesIO()
    with wave.open(out,'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000);w.writeframes(b'\0\0'*16000)
    return out.getvalue()


def test_import_persists_and_supports_video_and_downloads(client):
    c,store,config=client
    response=c.post('/api/songs/import',content=wav_bytes(),headers={'x-filename':'My%20Song.wav'})
    assert response.status_code==201,response.text
    t=response.json()
    assert t['source']=='imported' and t['title']=='My Song'
    assert t['duration']==2 and t['subtitle']=='Imported song'
    assert t['status']=='succeeded' and t['form']['lyrics']==''
    assert Store(config.data).rows()[0]['id']==t['id']
    for ext in ('mp3','wav','flac'):
        assert c.get(f"/api/takes/{t['id']}/files/audio.{ext}").status_code==200
    assert c.get(f"/api/takes/{t['id']}/video").status_code==200
    assert c.post('/api/library/actions',json={'ids':[t['id']],'action':'trash'}).status_code==200
    assert c.post('/api/library/actions',json={'ids':[t['id']],'action':'restore'}).status_code==200
    with store.db() as db:
        assert db.execute("select count(*) from generation_jobs where state='queued'").fetchone()[0]==0


def test_invalid_import_cleans_up_without_library_entry(client,monkeypatch):
    from . import song_import
    c,store,_=client
    assert c.post('/api/songs/import',content=b'',headers={'x-filename':'x.wav'}).status_code==422
    assert c.post('/api/songs/import',content=b'not audio',headers={'x-filename':'x.mp3'}).status_code==422
    assert c.post('/api/songs/import',content=b'bad',headers={'x-filename':'x.m3u'}).status_code==422
    monkeypatch.setattr(song_import,'MAX_BYTES',10)
    assert c.post('/api/songs/import',content=b'x'*11,headers={'x-filename':'x.wav'}).status_code==413
    assert store.rows()==[]
    assert not list((store.root/'imports').glob('*'))


def test_import_requires_auth(client):
    c,store,_=client
    assert c.post('/api/songs/import',content=wav_bytes(),headers={'Authorization':'','x-filename':'x.wav'}).status_code==401
    assert store.rows()==[]


def test_transcription_is_reviewable_not_an_alignment():
    from .alignment_runner import transcript_draft
    heard=[{'word':' Hello','start':1,'end':1.4,'probability':.9},{'word':' world','start':1.4,'end':1.8,'probability':.5},{'word':' Again','start':4,'end':4.5,'probability':.9}]
    result=transcript_draft(heard,10)
    assert result['lyrics']=='Hello world\nAgain'
    assert result['requiresReview'] and result['reviewCount']==1
    assert 'cues' not in result
    assert transcript_draft([],10)['lyrics']==''


def test_transcription_accepts_empty_lyrics_but_requires_runtime(client):
    c,store,_=client
    t=c.post('/api/songs/import',content=wav_bytes(),headers={'x-filename':'song.wav'}).json()
    response=c.post(f"/api/takes/{t['id']}/video",json={'requestId':'transcribe-import-01','kind':'transcription','lyrics':''})
    assert response.status_code==503,response.text
    assert 'not installed' in response.text
    assert store.rows()[0]['form']['lyrics']==''


def test_transcription_job_routes_to_local_runner_and_persists(client, monkeypatch):
    import json,time
    from pathlib import Path
    from . import video
    c,store,config=client
    t=c.post('/api/songs/import',content=wav_bytes(),headers={'x-filename':'song.wav'}).json()
    root=store.root.parent
    python=root/'.venv-alignment/bin/python';python.parent.mkdir(parents=True);python.touch()
    (root/'alignment.lock.json').write_text('{}')
    calls=[]
    async def spawn(*command,**kwargs):
        calls.append(command)
        work=Path(command[3])
        payload=json.loads((work/'input.json').read_text())
        assert payload['kind']=='transcription' and payload['lyrics']==''
        assert Path(command[1]).name=='alignment_runner.py'
        (work/'result.json').write_text(json.dumps({'lyrics':'Recognized lyric','requiresReview':True,'duration':2}))
        class Process:
            returncode=0
        return Process()
    monkeypatch.setattr(video.asyncio,'create_subprocess_exec',spawn)
    body={'requestId':'transcription-local-job','kind':'transcription','lyrics':''}
    a=c.post(f"/api/takes/{t['id']}/video",json=body)
    assert a.status_code==202,a.text
    for _ in range(30):
        jobs=c.get(f"/api/takes/{t['id']}/video").json()['jobs']
        if jobs and jobs[0]['state']=='succeeded':break
        time.sleep(.05)
    assert jobs[0]['kind']=='lyric-transcription'
    assert jobs[0]['result']['lyrics']=='Recognized lyric'
    assert len(calls)==1
    assert c.post(f"/api/takes/{t['id']}/video",json=body).json()['id']==a.json()['id']
    assert store.rows()[0]['form']['lyrics']==''
