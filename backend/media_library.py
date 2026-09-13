"""Read-only catalog of completed full-length video exports."""
import json
import re
from pathlib import Path
from fastapi import APIRouter


def routes(store, films):
    router = APIRouter()

    @router.get('/api/library/videos')
    def videos():
        items, missing = [], 0
        with store.db() as db:
            rows = db.execute("""SELECT j.id, j.created_at,
                json_extract(j.input_json,'$.takeId') AS take_id,
                json_extract(j.input_json,'$.planId') AS plan_id,
                json_extract(j.result_json,'$.duration') AS duration, t.title
                FROM assistance_jobs j JOIN takes t ON t.id=json_extract(j.input_json,'$.takeId')
                WHERE j.kind='song-video-render' AND j.state='succeeded' AND t.deleted_at IS NULL
                ORDER BY j.created_at DESC,j.id""").fetchall()
            deleted = {r[0] for r in db.execute('SELECT id FROM takes WHERE deleted_at IS NOT NULL')}
        for row in rows:
            if not all(re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', str(row[k] or '')) for k in ('id', 'plan_id')):
                continue
            if not (store.root/'music-videos'/row['plan_id']/'exports'/row['id']/'movie.mp4').is_file():
                missing += 1; continue
            url = f"/api/music-video/jobs/{row['id']}/media"
            items.append({'id': 'music-video:' + row['id'], 'kind': 'music-video', 'takeId': row['take_id'],
                          'title': row['title'], 'duration': row['duration'], 'created': row['created_at'],
                          'videoUrl': url, 'downloadUrl': url + '?download=1'})
        with films.lock:
            for file in films.root.glob('*/manifest.json'):
                try:
                    film = json.loads(file.read_text())
                    if not isinstance(film, dict):
                        missing += 1; continue
                    if film.get('deletedAt') or film.get('takeId') in deleted: continue
                    film_id = film['id']
                    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', film_id): continue
                    for export in film.get('exports', []):
                        if not isinstance(export, dict):
                            missing += 1; continue
                        if export.get('state') != 'ready': continue
                        export_id = export['id']
                        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', export_id): continue
                        if not Path(export.get('source', '')).is_file():
                            missing += 1; continue
                        url = f'/api/films/{film_id}/exports/{export_id}'
                        items.append({'id': f'film:{film_id}:{export_id}', 'kind': 'film', 'filmId': film_id,
                                      'takeId': film.get('takeId'), 'title': film.get('title', 'Music video'),
                                      'duration': film.get('duration'),
                                      'created': export.get('created') or film.get('created') or int(file.stat().st_mtime * 1000),
                                      'videoUrl': url, 'downloadUrl': url})
                except (OSError, ValueError, KeyError, TypeError):
                    missing += 1
        return {'videos': sorted(items, key=lambda item: item['created'] or 0, reverse=True), 'missingFiles': missing}

    return router
