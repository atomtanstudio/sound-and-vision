"""Opt-in VRGDG Audio Drive construction with H3LIX's existing fused Turbo.

The upstream node is installed separately in ComfyUI. This adapter supplies
scene windows and one explicit character, and preserves the full mix.
"""
import hashlib
import math
from pathlib import Path

WORKFLOW = 'vrgdg-h3-turbo'
TIERS = {'standard': [960, 544], 'native': [1344, 768]}


def enabled(plan):
    return plan.get('workflow') == WORKFLOW


def scene_windows(duration, seconds):
    if not math.isfinite(duration) or not 1 <= duration <= 900:
        raise ValueError('Music videos support songs between one second and fifteen minutes.')
    if not 5 <= seconds <= 15:
        raise ValueError('Scene length must be between five and fifteen seconds.')
    frames = math.ceil(duration * 24)
    shots = []
    for start in range(0, frames, seconds * 24):
        end = min(frames, start + seconds * 24)
        count = max(5, end - start)
        aligned = count + (5 - count) % 17
        shots.append(dict(index=len(shots), startFrame=start, endFrame=end,
                          start=start / 24, end=min(end / 24, duration),
                          generationSeconds=aligned / 24,
                          cutOnMeasuredBeat=False))
    return shots


def storyboard_windows(duration, ends):
    """Snap storyboard cuts to frames and reject gaps, short or oversize scenes."""
    if not ends or any(not math.isfinite(v) for v in ends) or abs(ends[-1]-duration) > 1/24:
        raise ValueError('The storyboard must end at the end of the song.')
    frames = math.ceil(duration * 24)
    cuts = [0, *[round(v*24) for v in ends[:-1]], frames]
    shots = []
    for i, (a, b) in enumerate(zip(cuts, cuts[1:])):
        minimum = 1 if i == len(ends)-1 else 48
        if not minimum <= b-a <= 360:
            raise ValueError('Each storyboard scene must be 2–15 seconds, with a shorter final tail allowed.')
        count = max(5, b-a); aligned = count + (5-count) % 17
        shots.append(dict(index=i,startFrame=a,endFrame=b,start=a/24,end=min(b/24,duration),
                          generationSeconds=aligned/24,cutOnMeasuredBeat=False))
    return shots


def retime(reviews, film_id, index, body):
    from fastapi import HTTPException
    from .film_review import ACTIVE, read, write
    from .film_vocal_timing import apply
    with reviews.lock:
        film=reviews.load(film_id);reviews.check_revision(film,body.revision)
        plan=read(film['plan'])
        if not enabled(plan) and plan.get('workflow')!='short-film':raise HTTPException(422,'This project does not have editable storyboard cuts.')
        if any(s['takes'] for s in film['scenes']) or any(j['state'] in ACTIVE for j in film['jobs']):
            raise HTTPException(409,'Set cut points before rendering any scenes.')
        if not 0 <= index < len(plan['shots'])-1:
            raise HTTPException(422,'The final scene must end with the song.')
        ends=[s['end'] for s in plan['shots']];ends[index]=body.endSeconds
        try:windows=storyboard_windows(plan['duration'],ends)
        except ValueError as e:raise HTTPException(422,str(e)) from e
        for shot,scene,window in zip(plan['shots'],film['scenes'],windows):
            shot.update(window)
            scene.update({k:window[k] for k in ('start','end','startFrame','endFrame')})
            if plan.get('workflow')=='short-film' and not plan.get('lyrics','').strip():
                from .film_review import vocal_windows
                shot['type']='narrative';scene['timing']=vocal_windows({},shot)
            else:scene['timing']=apply(plan,shot)
            scene['type']=shot['type']
            if shot.get('story'):
                shot['story']['endSeconds']=shot['end']
                scene['story']=shot['story']
        plan.setdefault('timingEdits',[]).append({'index':index,'endSeconds':body.endSeconds})
        write(film['plan'],plan)
        film['revision']+=1;film['cutRevision']+=1;reviews.save(film)
        return reviews.public(film)


def prompt(data):
    from .film_voice import voice_direction
    shot = data['shot']
    action = data.get('correction') or shot['prompt']
    performance = voice_direction(data)
    timing_rule = ('This entire scene has no on-camera vocal event. The music is heard off screen. The person remains silent.'
                   if shot['type']=='narrative' else
                   'Visible singing is allowed only inside the measured vocal windows below; every other moment is a facial rest.')
    return f'''subject_definitions:
<Subject 1> (S1) is the one adult lead in <Picture 1>. Preserve the same face, age, hair and complete wardrobe.
<Audio 1> is the exact original song excerpt, starting at clip time zero, including all instrumental passages and pauses.

summary:
[reference generation + audio reference] One continuous cinematic music-video scene guided by <Picture 1> and <Audio 1>.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - the same identity, age, facial proportions, hair and wardrobe as Picture 1.
<Audio 1>: reference - original music, voice, timing, breaths and pauses. The full mix remains unchanged.

detailed_description:
Photographic cinematic imagery in the setting, lighting and visual style specified by the scene direction, with controlled camera movement and coherent physical detail.
{timing_rule}
[Shot 1] {action}
Scene continuity: {data['sceneContinuity']}
{performance}
Use the supplied scene direction for setting and style. One camera setup and one simple physical action for the full scene.
The same lead remains recognizable regardless of lighting or vocal pitch. Natural anatomy and restrained coherent motion.
No replacement voice, extra words, extra person, montage, captions or overlays.
The measured vocal/rest instructions take priority over any older scene notes mentioning a performance.

overall_soundscape:
Use <Audio 1> unchanged. No additional sound effects or dialogue.

non_diegetic_music:
The original music in <Audio 1>, unchanged.
'''


def prepare_audio(target, source, shot):
    from .film_worker import run
    # Match Builder: cut the full mix to the exact visible window, 44.1 kHz
    # stereo PCM. Extra H3 grid frames are discarded after generation.
    run(['ffmpeg', '-y', '-v', 'error', '-ss', f"{shot['start']:.9f}", '-i', source,
         '-t', f"{shot['end']-shot['start']:.9f}", '-vn', '-ac', 2, '-ar', 44100,
         '-c:a', 'pcm_s16le', target])


def export_film(work, data):
    from .film_review import write
    from .film_worker import probe, run
    plan = data['plan']; fps = plan['fps']; dimensions = plan['output']
    shots = plan['shots']; selected = data['story']
    if len(shots) != len(selected):
        raise ValueError('Every scene needs a selected take.')
    import shutil
    paths = []; receipts = []; cursor = 0
    for shot, take in zip(shots, selected):
        if shot['index'] != take['index'] or shot['startFrame'] != cursor:
            raise ValueError('Selected scenes must cover the timeline once, in order.')
        cursor = shot['endFrame']
        source = Path(take['source']); info = probe(source)
        streams = info['streams']; v = streams[0]
        count = shot['endFrame'] - shot['startFrame']
        if (len(streams) != 1 or v['codec_type'] != 'video' or v['codec_name'] != 'h264'
                or [v['width'], v['height']] != dimensions or int(v['nb_frames']) != count
                or v['avg_frame_rate'] != '24/1' or v['pix_fmt'] != 'yuv420p'):
            raise ValueError('Scene format does not match this Audio Drive project; export stopped.')
        target = work / f"scene-{shot['index']:04d}.mp4"
        shutil.copyfile(source, target)
        paths.append(f"file '{target.name}'\nduration {count/fps:.12f}\n")
        receipts.append({'index':shot['index'], 'selected':take['selected'],
                         'sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
    if cursor != math.ceil(plan['duration'] * fps):
        raise ValueError('Scenes do not cover the complete song.')
    concat = work/'scenes.ffconcat'
    concat.write_text('ffconcat version 1.0\n'+''.join(paths))
    write(work/'phase.json', {'phase':'Joining scenes with the original song; preserving rendered video'})
    target = work/'film.mp4'
    run(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', 0, '-i', concat,
         '-i', plan['audio'], '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy',
         '-c:a', 'aac', '-b:a', '192k', '-ar', 48000, '-ac', 2,
         '-t', str(cursor/fps), '-movflags', '+faststart', target])
    info = probe(target); v = next(s for s in info['streams'] if s['codec_type']=='video')
    a = next(s for s in info['streams'] if s['codec_type']=='audio')
    if int(v['nb_frames']) != cursor or abs(float(a['duration'])-plan['duration']) > .08:
        raise RuntimeError('Export timing verification failed.')
    run(['ffmpeg','-v','error','-xerror','-i',target,'-f','null','-'])
    write(work/'checks.json', {'workflow':WORKFLOW,'decode':'complete','frames':cursor,
          'fps':fps,'dimensions':dimensions,'audioDuration':float(a['duration']),
          'videoAssembly':'stream-copy','creditsApplied':False,'selectedScenes':receipts,
          'soundtrackSha256':hashlib.sha256(Path(plan['audio']).read_bytes()).hexdigest(),
          'sourceSha256':hashlib.sha256(target.read_bytes()).hexdigest(),
          'manualReview':['Review every vocal pause and the lead identity throughout.']})
