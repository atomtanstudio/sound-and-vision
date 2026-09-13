"""Bounded, CPU-only audio import for the persistent library and video tools."""
import asyncio
import json
import math
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Request
from .library import project_row

MAX_BYTES = 100 * 1024 * 1024
MAX_SECONDS = 600
FORMATS = 'wav,flac,mp3,mov,ogg'


def normalize(source, folder):
    common = ['-v', 'error', '-protocol_whitelist', 'file,pipe', '-format_whitelist', FORMATS]
    try:
        result = subprocess.run(['ffprobe', *common, '-show_entries', 'format=duration:stream=codec_type', '-of', 'json', str(source)], capture_output=True, text=True, timeout=20, check=True)
        info = json.loads(result.stdout)
        duration = float(info.get('format', {}).get('duration', 0))
        if not math.isfinite(duration) or not 1 <= duration <= MAX_SECONDS or not any(s.get('codec_type') == 'audio' for s in info.get('streams', [])):
            raise ValueError()
        subprocess.run(['ffmpeg', *common, '-nostdin', '-i', str(source), '-map', '0:a:0', '-vn', '-t', str(MAX_SECONDS + 1), '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le', str(folder/'audio.wav')], capture_output=True, timeout=120, check=True)
        import wave
        with wave.open(str(folder/'audio.wav')) as audio:
            duration = audio.getnframes()/audio.getframerate()
        if not 1 <= duration <= MAX_SECONDS:
            raise ValueError()
        for ext, codec in [('flac', 'flac'), ('mp3', 'libmp3lame')]:
            subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(folder/'audio.wav'), '-c:a', codec, str(folder/f'audio.{ext}')], capture_output=True, timeout=120, check=True)
        return duration
    except (ValueError, KeyError, subprocess.SubprocessError) as error:
        raise HTTPException(422, 'Choose valid audio between 1 second and 10 minutes long.') from error


def routes(store):
    router = APIRouter()
    limit = asyncio.Lock()

    @router.post('/api/songs/import', status_code=201)
    async def import_song(request: Request):
        if limit.locked():
            raise HTTPException(409, 'Another song is being imported. Try again when it finishes.')
        async with limit:
            name = Path(unquote(request.headers.get('x-filename', 'song.wav'))).name
            if Path(name).suffix.lower() not in {'.wav','.flac','.mp3','.m4a','.ogg'}:
                raise HTTPException(422, 'Choose WAV, FLAC, MP3, M4A, or OGG audio.')
            take = uuid.uuid4().hex
            key = 'imports/' + take
            folder = store.path_for(key)
            folder.mkdir(parents=True, mode=0o700)
            source = folder / ('original' + Path(name).suffix.lower())
            committed = False
            try:
                size = 0
                with source.open('xb') as out:
                    async for chunk in request.stream():
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise HTTPException(413, 'Choose a song smaller than 100 MB.')
                        out.write(chunk)
                if not size:
                    raise HTTPException(422, 'The uploaded file is empty.')
                # Await the worker even on disconnect so cleanup cannot race decoding.
                task = asyncio.create_task(asyncio.to_thread(normalize, source, folder))
                try:
                    duration = await asyncio.shield(task)
                except asyncio.CancelledError:
                    await task
                    raise
                stamp = int(time.time()*1000)
                title = Path(name).stem[:200] or 'Imported song'
                from .contracts import SongForm
                form = SongForm.model_construct().model_dump()
                form.update(title=title, description='Imported audio', lyrics='', project='Imported songs')
                delivery = {'source':'imported','duration':duration,'sample_rate':48000,'channels':2,'warnings':[]}
                (folder/'delivery.json').write_text(json.dumps(delivery))
                with store.db() as db:
                    db.execute('BEGIN IMMEDIATE')
                    project = project_row(db, 'Imported songs', stamp)
                    db.execute('INSERT INTO generation_requests VALUES(?,?,?,?,?,?,?,?)', ('import-'+take, project['id'],title,json.dumps(form),1,'completed',stamp,stamp))
                    db.execute("INSERT INTO takes(id,request_id,project_id,take_index,title,style_summary,status,seed,duration_ms,created_at,updated_at) VALUES(?,?,?,1,?,'Imported audio','ready',NULL,?,?,?)", (take,'import-'+take,project['id'],title,round(duration*1000),stamp,stamp))
                    db.execute("INSERT INTO generation_jobs(id,take_id,state,stage,output_key,created_at,updated_at) VALUES(?,?,'succeeded','imported',?,?,?)", (uuid.uuid4().hex,take,key,stamp,stamp))
                    for ext in ('wav','flac','mp3'):
                        db.execute("INSERT INTO assets(id,take_id,kind,format,storage_key,status,provider,created_at) VALUES(?,?,'audio',?,?,'ready','import',?)", (uuid.uuid4().hex,take,ext,key+'/audio.'+ext,stamp))
                    db.commit()
                committed = True
                return next(t for t in store.rows() if t['id']==take)
            finally:
                if not committed:
                    shutil.rmtree(folder, ignore_errors=True)
    return router
