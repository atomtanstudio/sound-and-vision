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
