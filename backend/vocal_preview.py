"""Expose existing Demucs stems for editing, never change the song soundtrack."""
import hashlib
from functools import lru_cache
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse


@lru_cache(maxsize=128)
def fingerprint(path: str, size: int, modified: int):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''): digest.update(chunk)
    return digest.hexdigest()


def routes(store):
    router = APIRouter()

    def stem(take_id):
        job = store.job(take_id)
        if job['state'] != 'succeeded': return None
        source = store.path_for(job['output_key'])/'audio.flac'
        if not source.is_file(): return None
        stat = source.stat()
        file = store.root/'video/audio-cache'/fingerprint(str(source), stat.st_size, stat.st_mtime_ns)/'vocals.wav'
        return file if file.is_file() else None

    @router.get('/api/takes/{take_id}/vocal-preview')
    def status(take_id: str):
        available = stem(take_id) is not None
        return {'available': available, 'audioUrl': f'/api/takes/{take_id}/vocal-preview/audio' if available else None}

    @router.get('/api/takes/{take_id}/vocal-preview/audio')
    def audio(take_id: str):
        file = stem(take_id)
        if file is None: raise HTTPException(404, 'No cached vocal stem. Align or transcribe this song first.')
        return FileResponse(file, media_type='audio/wav')

    return router
