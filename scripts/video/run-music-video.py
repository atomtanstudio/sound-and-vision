"""Resume authorized H3LIX scene jobs; keep every request and source clip.

Uses H3LIX's existing four-step fused Turbo profile. No service changes, model
installs, queue interruption, or provider-side final audio mux are performed.
"""
import argparse, base64, fcntl, hashlib, json, shutil, sqlite3, subprocess, time
from pathlib import Path
from urllib.request import Request, urlopen


def write(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    temp.replace(path)


def api(path, data=None):
    request = Request('http://127.0.0.1:7310' + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={'Content-Type': 'application/json'})
    with urlopen(request, timeout=90) as response:
        return json.load(response)


def published_json(path):
    # H3LIX writes its status/manifest in place. A reader can briefly see an
    # empty or partial JSON file while an event is being persisted.
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--root', type=Path, default=Path('/srv/ai/sound-vision'))
    parser.add_argument('--only', type=int)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    folder = args.plan.parent
    lock = (folder / 'h3-batch.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    completed = []
    for shot in plan['shots']:
        if args.only is not None and shot['index'] != args.only:
            continue
        run_id = shot['runId']
        work = folder / 'clips' / run_id
        work.mkdir(parents=True, exist_ok=True)
        checkpoint = work / 'provider.json'
        source_dir = Path('/srv/ai/h3lix-library') / run_id
        manifest = source_dir / 'manifest.json'
        request_path = work / 'request.json'
        signature = hashlib.sha256(json.dumps(shot, sort_keys=True).encode()).hexdigest()
        if request_path.exists() and json.loads(request_path.read_text())['shotSha256'] != signature:
            raise RuntimeError('Changed shot requires a new runId: ' + run_id)
        write(request_path, {'shotSha256': signature, 'shot': shot})
        if not checkpoint.exists() and not manifest.exists():
            # Both generation owners must be idle before asking H3LIX to start.
            while True:
                with sqlite3.connect(args.root / 'data/library.sqlite3') as db:
                    music_active = db.execute("SELECT count(*) FROM generation_jobs WHERE state IN ('running','queued','waiting-for-resource')").fetchone()[0]
                machine = api('/api/machine')
                if not music_active and not machine.get('busy') and not machine.get('activeJobId'):
                    break
                time.sleep(10)
            audio = work / 'song-window.wav'
            subprocess.run(['ffmpeg','-y','-v','error','-ss',str(shot['start']),
                '-i',plan['audio'],'-af','apad','-t',str(shot['generationSeconds']),
                '-ar','48000','-ac','2','-c:a','pcm_s16le',str(audio)],check=True)
            assets = []
            for i, image in enumerate(shot['references']):
                assets.append({'id':f'picture-{i+1}','kind':'image','fileName':f'picture-{i+1}.png',
                    'role':'Character and scene reference','retention':'Preserve',
                    'dataUrl':'data:image/png;base64,' + base64.b64encode(Path(image).read_bytes()).decode()})
            assets.append({'id':'song-window','kind':'audio','fileName':'song-window.wav',
                'role':'Exact sung performance and timing','finalSoundtrack':False,
                'dataUrl':'data:audio/wav;base64,' + base64.b64encode(audio.read_bytes()).decode()})
            request = {'mode':'Reference to Video','title':plan['title']+' — '+shot['name'],
                'prompt':shot['prompt'],'ratio':'16:9','duration':shot['generationSeconds'],
                'tier':'native','turbo':'On','steps':4,'nativeAudio':'Off',
                'seed':shot.get('seed',923410+shot['index']),'runId':run_id,'assets':assets}
            write(checkpoint, {'submissionStarted':True, 'runId':run_id})
            # Do not automatically replay an ambiguous non-idempotent POST.
            remote = api('/api/jobs', request)
            if remote['runId'] != run_id:
                raise RuntimeError('Provider allocated unexpected runId; inspect '+str(remote))
            write(checkpoint, remote)
        deadline = time.monotonic() + 2400
        item = published_json(manifest)
        while not item:
            status_path = source_dir / 'status.json'
            state = published_json(status_path) or {}
            event = state.get('lastEvent', {})
            write(folder / 'batch-status.json', {'state':state.get('state','submitting'),
                'shot':shot['index'],'name':shot['name'],'completed':completed,
                'phase':event.get('message'),'updated':time.time()})
            if state.get('state') == 'error' or event.get('event') == 'job-error':
                raise RuntimeError(event.get('message', 'H3 job failed: '+run_id))
            if time.monotonic() > deadline:
                raise TimeoutError('Inspect retained run; do not resubmit automatically: '+run_id)
            time.sleep(10)
            item = published_json(manifest)
        source = Path(item['videoPath'])
        target = work / 'background.mp4'
        if not target.exists():
            shutil.copyfile(source, target)
        write(work / 'receipt.json', {'runId':run_id,'source':str(source),'item':item,
            'sha256':hashlib.file_digest(target.open('rb'),'sha256').hexdigest()})
        completed.append(run_id)
        print('Completed', shot['index'], shot['name'], flush=True)
    write(folder / 'batch-status.json', {'state':'succeeded','completed':completed,'updated':time.time()})


if __name__ == '__main__':
    main()
