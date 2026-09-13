import hashlib
import json
from .test_api import client, payload
from .test_music_video import audio


def test_library_collects_finished_exports_and_excludes_trash_and_missing_files(client):
    c, store, config = client
    tracks = c.post('/api/generations', json=payload()).json()['tracks']
    take_id = tracks[0]['id']
    with store.db() as db:
        for i, state in enumerate(['succeeded', 'succeeded', 'running', 'failed', 'succeeded']):
            job_id = f'video-export-{i}'
            db.execute('INSERT INTO assistance_jobs(id,kind,state,input_json,result_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                       (job_id, 'song-video-render', state, json.dumps({'takeId': take_id, 'planId': 'reviewed-plan'}), json.dumps({'duration': 12}), i+100, i+100))
            if i != 4:
                folder = store.root/'music-videos/reviewed-plan/exports'/job_id
                folder.mkdir(parents=True); (folder/'movie.mp4').write_bytes(b'video')
    film_file = c.app.state.films.root/'film-fixture/manifest.json'
    film_file.parent.mkdir()
    export = film_file.parent/'saved.mp4'; export.write_bytes(b'film')
    film = {'id': 'film-fixture', 'takeId': tracks[1]['id'], 'title': 'Earlier film', 'duration': 12,
            'exports': [{'id': 'export-1', 'state': 'ready', 'source': str(export)}, {'id': 'export-2', 'state': 'queued'}]}
    film_file.write_text(json.dumps(film))
    response = c.get('/api/library/videos')
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result['videos']) == 3
    assert result['missingFiles'] == 1
    assert len({item['id'] for item in result['videos']}) == 3
    assert {item['kind'] for item in result['videos']} == {'film', 'music-video'}
    assert all(item['videoUrl'].startswith('/api/') for item in result['videos'])
    assert str(config.data) not in response.text
    assert c.get('/api/library/videos', headers={'Authorization': ''}).status_code == 401
    with store.db() as db: db.execute('UPDATE takes SET deleted_at=123 WHERE id=?', (take_id,))
    assert len(c.get('/api/library/videos').json()['videos']) == 1
    film['deletedAt'] = 123; film_file.write_text(json.dumps(film))
    assert c.get('/api/library/videos').json()['videos'] == []


def test_vocal_preview_reuses_the_exact_song_stem_and_keeps_original_audio(client):
    c, store, _ = client
    take = c.post('/api/songs/import', content=audio(4), headers={'x-filename': 'song.wav'}).json()['id']
    endpoint = f'/api/takes/{take}/vocal-preview'
    assert c.get(endpoint).json() == {'available': False, 'audioUrl': None}
    assert c.get(endpoint+'/audio').status_code == 404
    source = store.path_for(store.job(take)['output_key'])/'audio.flac'
    original = source.read_bytes()
    stem = store.root/'video/audio-cache'/hashlib.sha256(original).hexdigest()/'vocals.wav'
    stem.parent.mkdir(parents=True); stem.write_bytes(audio(4))
    assert c.get(endpoint).json() == {'available': True, 'audioUrl': endpoint+'/audio'}
    response = c.get(endpoint+'/audio', headers={'Range': 'bytes=0-11'})
    assert response.status_code == 206
    assert response.content == stem.read_bytes()[:12]
    assert response.headers['content-type'] == 'audio/wav'
    assert response.headers['cache-control'] == 'no-store'
    assert c.get(endpoint+'/audio', headers={'Authorization': ''}).status_code == 401
    other = c.post('/api/songs/import', content=audio(5), headers={'x-filename': 'other.wav'}).json()['id']
    assert c.get(f'/api/takes/{other}/vocal-preview').json()['available'] is False
    assert source.read_bytes() == original
    with store.db() as db: assert db.execute('SELECT count(*) FROM assistance_jobs').fetchone()[0] == 0
