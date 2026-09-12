"""One scene retry or one deterministic export; no autonomous re-render loop."""
import base64
import copy
import fcntl
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from .film_review import read, write
from .film_voice import voice_contract, voice_direction
from . import film_audio_drive
from . import film_cast


def run(command):
    subprocess.run(list(map(str,command)),check=True,timeout=1800)


def probe(path):
    return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)],timeout=30))


def published(path):
    try:return read(path)
    except (FileNotFoundError,json.JSONDecodeError):return None


def conditioning_source(audio,kind,data_root):
    if kind=='performance':
        digest=hashlib.file_digest(Path(audio).open('rb'),'sha256').hexdigest()
        vocal=Path(data_root)/'video/audio-cache'/digest/'vocals.wav'
        if vocal.is_file():return vocal,'isolated-vocal'
    return Path(audio),'full-mix'


def prepare_vocal_reference(target,source,shot,policy):
    # Cut before padding: H3 rounds up duration, but must never hear vocals
    # belonging to the following scene in that extra fraction of a second.
    windows = '+'.join(f"between(t,{w['start']:.9f},{w['end']:.9f})" for w in policy['vocalWindows']) or '0'
    # aeval evaluates each audio sample. A volume filter evaluated per audio
    # frame would leak up to a full frame of voice across a rest boundary.
    gate = f"if(gt({windows},0),val(0),0)|if(gt({windows},0),val(1),0)".replace(',', r'\,')
    # Forced word alignment is approximate, especially for sung/held notes.
    # Never use those estimates to remove samples from a locked vocal source.
    gating = '' if policy.get('timingAuthority')=='recorded-audio' else f',aeval={gate}'
    run(['ffmpeg','-y','-v','error','-ss',shot['start'],'-i',source,'-af',
         f"aresample=48000,atrim=duration={policy['visibleDuration']},asetpts=PTS-STARTPTS,aformat=channel_layouts=stereo{gating},apad",
         '-t',shot['generationSeconds'],'-ar',48000,'-ac',2,'-c:a','pcm_s16le',target])


class H3Rejected(RuntimeError):
    pass


def api(path,data=None):
    url=os.environ.get('SOUND_VISION_H3_URL','http://127.0.0.1:7310').rstrip('/')+path
    req=Request(url,data=json.dumps(data).encode() if data is not None else None,
                headers={'Content-Type':'application/json'})
    try:
        with urlopen(req,timeout=90) as response:return json.load(response)
    except HTTPError as error:
        raw=error.read(65536).decode(errors='replace')
        try:message=json.loads(raw).get('error',raw)
        except json.JSONDecodeError:message=raw
        if 400<=error.code<500:raise H3Rejected(f'H3 rejected the request ({error.code}): {str(message)[:1200]}') from error
        raise RuntimeError(f'H3 response interrupted ({error.code}); recover the existing run before retrying.') from error


def frame(source,seconds,target):
    run(['ffmpeg','-y','-v','error','-ss',max(0,seconds),'-i',source,'-vf','scale=960:-2','-frames:v',1,'-q:v',2,target])


def prepare_preview(source,audio,scene,work,poster=False):
    work.mkdir(parents=True,exist_ok=True)
    target=work/((poster+'.jpg' if isinstance(poster,str) else 'poster.jpg') if poster else 'preview.mp4')
    with (work/'prepare.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if target.exists():return target
        if poster:
            partial=target.with_name(target.stem+'.partial.jpg')
            when=0 if poster=='start' else max(0,scene['end']-scene['start']-2/scene.get('fps',24)) if poster=='end' else min(1,(scene['end']-scene['start'])/2)
            frame(source,when,partial)
        else:
            partial=work/'preview.partial.mp4'
            lossless = next(s for s in probe(source)['streams'] if s['codec_type']=='video').get('profile')=='High 4:4:4 Predictive'
            video_args=['-c:v','libx264','-threads',4,'-preset','fast','-crf',18,'-pix_fmt','yuv420p'] if lossless else ['-c:v','copy']
            run(['ffmpeg','-y','-v','error','-i',source,'-ss',scene['start'],'-i',audio,
                 '-map','0:v:0','-map','1:a:0','-t',scene['end']-scene['start'],
                 *video_args,'-c:a','aac','-b:a','320k','-movflags','+faststart',partial])
        partial.replace(target)
    return target


def prepare_context(film,scene,take,plan,work):
    """A candidate and both adjacent cuts, with one uninterrupted song excerpt."""
    index=scene['index'];fps=plan['fps'];parts=[]
    if index>0 and any(t['id']==film['scenes'][index-1]['selected'] and t['state']=='ready' for t in film['scenes'][index-1]['takes']):
        previous=film['scenes'][index-1]
        selected=next(t for t in previous['takes'] if t['id']==previous['selected'])
        count=min(2*fps,previous['endFrame']-previous['startFrame'])
        parts.append((selected['source'],(previous['endFrame']-previous['startFrame']-count)/fps,count))
    lead=parts[0][2]/fps if parts else 0
    parts.append((take['source'],0,scene['endFrame']-scene['startFrame']))
    if index+1<len(film['scenes']) and any(t['id']==film['scenes'][index+1]['selected'] and t['state']=='ready' for t in film['scenes'][index+1]['takes']):
        following=film['scenes'][index+1]
        selected=next(t for t in following['takes'] if t['id']==following['selected'])
        parts.append((selected['source'],0,min(2*fps,following['endFrame']-following['startFrame'])))
    signature=hashlib.sha256(json.dumps(parts).encode()).hexdigest()[:20]
    work=work/signature;work.mkdir(parents=True,exist_ok=True)
    target=work/'context.mp4'
    with (work/'context.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if target.exists():return target
        for i,(source,start,count) in enumerate(parts):
            run(['ffmpeg','-y','-v','error','-ss',start,'-i',source,'-an',
                 '-vf',f'fps={fps},scale=1920:1080:force_original_aspect_ratio=increase:flags=lanczos,crop=1920:1080,setsar=1',
                 '-frames:v',count,'-c:v','libx264','-threads',4,'-preset','fast','-crf',18,'-pix_fmt','yuv420p',work/f'part-{i}.mp4'])
        sequence=work/'parts.ffconcat'
        sequence.write_text('ffconcat version 1.0\n'+''.join(f"file 'part-{i}.mp4'\n" for i in range(len(parts))))
        duration=sum(p[2] for p in parts)/fps
        partial=work/'context.partial.mp4'
        run(['ffmpeg','-y','-v','error','-f','concat','-safe',0,'-i',sequence,'-ss',scene['start']-lead,
             '-i',plan['audio'],'-map','0:v:0','-map','1:a:0','-t',duration,'-c:v','copy',
             '-c:a','aac','-b:a','320k','-movflags','+faststart',partial])
        if int(probe(partial)['streams'][0]['nb_frames'])!=sum(p[2] for p in parts):
            raise RuntimeError('Context preview frame count mismatch')
        partial.replace(target)
    return target


def prompt_for(data,reference_count):
    if film_cast.prompt_sections(data) is not None:
        return cast_prompt(data)
    if film_audio_drive.enabled(data.get('plan', {})):
        return film_audio_drive.prompt(data)
    if data.get('method') == 'generate':
        return generation_prompt(data)
    if data.get('repairVersion', 1) >= 2:
        return repair_prompt(data)
    shot=data['shot'];timing=data['timing'];seconds=shot['generationSeconds']
    words=timing['words'];spans=timing['spans']
    schedule='; '.join(f"{w['start']:.3f}–{w['end']:.3f}s: {w['text']}" for w in words)
    ranges='; '.join(f"{s['start']:.3f}–{s['end']:.3f}s" for s in spans) or 'none'
    audio_role=('the isolated recorded lead vocal, with the original pauses and timing' if data.get('conditioningAudio')=='isolated-vocal' else 'the exact original song excerpt')
    brief=data.get('compiledContext',{}).get('brief',{'singleAction':data['correction'],'objectContinuity':data['sceneContinuity']})
    scoped='The scene constraints are: '+' '.join(f"{key}: {str(value).replace(chr(10),' ')}" for key,value in brief.items())
    performance=(f"<Subject 1> (S1) sings only the recorded lead vocal in <Audio 1>. Vocal windows within this clip: {ranges}. "
                 f"Keep his lips relaxed and closed during the initial {timing['leadingRest']:.3f} seconds and during rests between those windows. "
                 "Do not begin singing on the first frame unless the vocal is already audible. Follow the actual syllables, pauses and breaths, without anticipating words. "
                 "A near-frontal, steady chest-up portrait keeps both lips visible throughout; no talking gestures, smiling with an open mouth, props over the lips or exaggerated head movement. "
                 f"The source timing, in seconds relative to this clip, is: {schedule}. "
                 f"The recorded words are <d>[English] {' '.join(w['text'] for w in words)}</d>."
                 if shot['type']=='performance' else
                 "The people are silent and never mouth the singing or speak. The song is heard only by the audience. Use a single simple physical action, with no handoffs unless explicitly required by the correction.")
    extra=data.get('identityReferences',[])
    identities='\n'.join(f"<Subject {i+2}> is the supporting character defined in <Picture {i+2}>: {r['role']}. This is an identity reference, not a requirement to copy its location or other objects." for i,r in enumerate(extra))
    neighbors='\n'.join(f'<Picture {i}> provides neighboring-shot context only; it does not replace the identities or location in Picture 1.' for i in range(2+len(extra),reference_count+1))
    retention='\n'.join([*[f'<Subject {i+2}> (appears in [Shot 1]): fully_preserved - preserve the exact supporting character identity and wardrobe.' for i in range(len(extra))],
                         *[f'<Picture {i}>: weak_reference - continuity at the neighboring cut only; keep the target scene and cast unchanged.' for i in range(2+len(extra),reference_count+1)]])
    return f'''subject_definitions:
<Subject 1> is the lead person in <Picture 1>, preserving their exact face, age, hair, clothing, body proportions and the environment. Supporting people and props visible in Picture 1 retain their identities and number.
{identities}
{neighbors}
<Audio 1> is {audio_role} for this scene, aligned at clip time zero.

summary:
[reference generation + audio reference] One continuous photographic take in the exact location of Picture 1. Preserve its people and visual style.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - exact identity, wardrobe and plausible anatomy.
{retention}
<Audio 1>: reference - follow its original performance timing. The original audio will be muxed unchanged after generation.

detailed_description:
Match the original scene reference's visual medium, lighting, color palette and camera perspective, with an almost stationary camera. [Shot 1] Keep the camera in this one location with the same exact people throughout the entire clip. The scoped scene brief is:
{scoped}
{performance}
Maintain the exact object count, positions and ownership specified in this scene brief. Each hand holds at most the object assigned to it. Existing objects stay where placed throughout this one action. Start and end in the same location with the same cast and lighting. Do not introduce an extra entrance, exit, transaction, location or character. Preserve this single scene for the full {seconds}-second generation. One uninterrupted camera take: no internal cuts, montage, location changes, dissolves, time jumps, frozen frames, speed ramps, typography or logos. Keep all movement small, physically credible and clearly observable. The camera stays on the same side of the people throughout; faces, clothing and objects retain their shapes and natural scale. Preserve the light direction and background arrangement of the source image. Avoid suddenly changing the angle, camera distance or lens. The last frame should look like a natural continuation of the first frame rather than a different setup.

overall_soundscape:
No new dialogue, vocal, ambience or sound effects.

non_diegetic_music:
The original full song will be added after generation. Preserve the supplied vocal timing; do not generate a replacement soundtrack.
'''


def repair_prompt(data):
    """Edit the actual chosen video using the official full-reference contract."""
    if film_cast.prompt_sections(data) is not None:
        return cast_prompt(data)
    shot = data['shot']
    singing = voice_contract(data)['mode'] == 'recorded-vocals'
    brief = data.get('compiledContext', {}).get('brief', {})
    constraints = ' '.join(f'{k}: {str(v).replace(chr(10), " ")}' for k, v in brief.items())
    correction = data['correction'].replace('\n', ' ')
    continuity = data['sceneContinuity'].replace('\n', ' ')
    cuts=sorted(set(t for t in data.get('baseTake',{}).get('checks',{}).get('possibleInternalCuts',[]) if .1<t<shot['generationSeconds']-.1))
    cut_descriptions='\n'.join(f"[Shot {i+2}] At {int(t//60):02}:{t%60:06.3f}, the camera cuts to the corresponding view in <Video 1> at this same time. Keep the visible people, setting and composition of that source view. Apply the requested correction there without moving this shot to the opening or exchanging it with an earlier shot." for i,t in enumerate(cuts))
    appearances=', '.join(f'[Shot {i+1}]' for i in range(len(cuts)+1))
    identities = '\n'.join(f"<Subject {i+2}> is the supporting person in <Picture {i+2}>: {r['role']}. Preserve this identity only where that person belongs in the source scene." for i, r in enumerate(data.get('identityReferences', [])))
    retention = '\n'.join(f'<Subject {i+2}> (appears in [Shot 1]): fully_preserved - exact identity and clothing.' for i in range(len(data.get('identityReferences', []))))
    audio_definition = '<Audio 1> is the recorded lead vocal for <Subject 1> (S1), aligned at scene time zero with the original pauses.' if singing else ''
    audio_retention = '<Audio 1>: reference - use the recorded syllable timing and rests for the visible performance.' if singing else ''
    performance = 'The source mouth motion is not a timing reference. '+voice_direction(data)
    return f'''subject_definitions:
<Subject 1> is the lead person defined in <Picture 1>, as seen in the source scene. Keep the same identity, face, hair, age, clothes and body proportions.
{identities}
<Video 1> is the source video for the target video edit. It defines the existing framing, environment, lighting, camera path, cast arrangement and action timing.
{audio_definition}

summary:
[video editing{' + audio reference' if singing else ''}] The target video is an edited version of <Video 1>. Apply only the requested correction and preserve the rest of the source scene.

retention_analysis:
<Subject 1> (appears in {appearances}): fully_preserved - preserve identity, wardrobe and anatomy from the reference.
{retention}
<Video 1> (source video editing): partially_preserved - correct only the specified defect; preserve the source framing, cast, location, lighting, camera path and all unaffected actions.
{audio_retention}

detailed_description:
Match the source video's visual medium, color, light and photographic detail. [Shot 1] Begin in the same composition as <Video 1>, with <Subject 1> and the existing cast in their original positions. This is a correction to this existing shot, not a new staging or interpretation. The requested change is: {correction}
The scene constraints are: {constraints} {continuity}
{performance}
The correction takes priority over defective motion or objects visible in the source. Otherwise retain the original shot sequence and pace. Preserve who owns each object and how many objects exist. Keep all unaffected hands, props, clothing, background and movement as in the source. Do not introduce additional people, entrances, handoffs or objects. Keep the camera angle, distance, trajectory and lens of each source shot. End in the source video's final composition except for the specifically corrected defect, so the existing adjacent shots still fit. Preserve existing shot order and cut times across the full {shot['generationSeconds']} seconds; add no cuts, scene changes, titles or logos. Source-frame evidence takes priority over older storyboard location notes.
{cut_descriptions}

overall_soundscape:
No new speech, ambience or sound effects.

non_diegetic_music:
The original master song is added unchanged after the visual edit. Do not generate a replacement soundtrack.
'''


def prepare_source_reference(work, data):
    # H3 retains reference-video spatial tokens during sampling. A native-size
    # video roughly doubles that sequence and exceeded this Legion GPU's VRAM.
    # Keep all 24-fps motion in a small proxy; identity stills remain high-res.
    target = work/'source-reference.mp4'
    count = max(5, round(data['shot']['generationSeconds']*24))
    count += (5-count%17)%17
    source_count = data['shot']['endFrame']-data['shot']['startFrame']
    run(['ffmpeg','-y','-v','error','-i',data['baseTake']['source'],'-an',
         '-vf',f'fps=24,trim=end_frame={source_count},setpts=PTS-STARTPTS,scale=512:288:flags=lanczos,setsar=1,tpad=stop_mode=clone:stop_duration=2',
         '-frames:v',count,'-c:v','libx264','-threads',4,'-preset','fast','-crf',16,'-pix_fmt','yuv420p',target])
    return target


def render_timing(work, data):
    """Move existing frames against the untouched master audio; no synthesis."""
    shot = data['shot'];fps = data['plan']['fps'];shift = data['shiftFrames']
    count = shot['endFrame'] - shot['startFrame'];source = Path(data['baseTake']['source'])
    if not shift or abs(shift) >= count:raise ValueError('Invalid timing adjustment')
    write(work/'phase.json', {'phase':'Adjusting existing frames; keeping the original song timing'})
    filters = f'fps={fps},trim=end_frame={count},setpts=PTS-STARTPTS,'
    filters += (f'tpad=start_mode=clone:start={shift}' if shift > 0 else
                f'trim=start_frame={-shift},setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop={-shift}')
    target = work/'background.mp4'
    run(['ffmpeg','-y','-v','error','-i',source,'-an','-vf',filters,'-frames:v',count,
         '-c:v','libx264','-threads',4,'-preset','fast','-crf',18,'-pix_fmt','yuv420p','-movflags','+faststart',target])
    actual = next(s for s in probe(target)['streams'] if s['codec_type']=='video')
    if int(actual['nb_frames']) != count:raise RuntimeError('Timing repair frame count mismatch')
    run(['ffmpeg','-v','error','-xerror','-i',target,'-f','null','-'])
    write(work/'checks.json', {'decode':'complete','frames':count,'fps':fps,
          'dimensions':[actual['width'],actual['height']], 'audioStart':shot['start'],'audioEnd':shot['end'],
          'method':'timing','baseTakeId':data['baseTake']['id'],'shiftFrames':shift,
          'baseSha256':hashlib.sha256(source.read_bytes()).hexdigest(),
          'sourceSha256':hashlib.sha256(target.read_bytes()).hexdigest(),
          'manualReview':['Check the vocal alignment throughout, not just the first word.',
                          f'{abs(shift)} frames are held at the {"start" if shift > 0 else "end"}; inspect that boundary.']})


def splice_range(source, replacement, target, start, end, count, fps):
    """Lossless saved candidate: only the explicit range comes from the model."""
    if start==0 and end==count:
        actual=next(s for s in probe(replacement)['streams'] if s['codec_type']=='video')
        if int(actual['nb_frames'])!=count:raise RuntimeError('Full-scene replacement frame count mismatch')
        shutil.copyfile(replacement,target)
        return
    filters=[];labels=[]
    for stream,a,b,label in [(0,0,start,'before'),(1,0,end-start,'patch'),(0,end,count,'after')]:
        if b<=a:continue
        filters.append(f'[{stream}:v]trim=start_frame={a}:end_frame={b},setpts=PTS-STARTPTS[{label}]')
        labels.append(f'[{label}]')
    filters.append(''.join(labels)+f'concat=n={len(labels)}:v=1:a=0[out]')
    run(['ffmpeg','-y','-v','error','-i',source,'-i',replacement,'-filter_complex',';'.join(filters),
         '-map','[out]','-an','-r',fps,'-frames:v',count,'-c:v','libx264','-threads',4,
         '-preset','fast','-crf',0,'-pix_fmt','yuv420p','-movflags','+faststart',target])
    actual=next(s for s in probe(target)['streams'] if s['codec_type']=='video')
    if int(actual['nb_frames'])!=count:raise RuntimeError('Range repair frame count mismatch')


def render_range(work,data):
    shot=data['shot'];fps=data['plan']['fps'];region=data['repairRange']
    start,end=region['startFrame'],region['endFrame'];count=shot['endFrame']-shot['startFrame']
    if not 0<=start<end<=count or end-start<2*fps:raise ValueError('Invalid repair range')
    source=Path(data['baseTake']['source']);patch=work/'replacement';patch.mkdir(exist_ok=True)
    anchor=data.get('repairAnchorFrame',start)
    if not 0<=anchor<count or ((start or end!=count) and anchor!=start):raise ValueError('Invalid replacement anchor')
    still=patch/'opening.png'
    if not still.exists():
        run(['ffmpeg','-y','-v','error','-i',source,'-vf',f'select=eq(n\\,{anchor})','-frames:v',1,still])
    partial=copy.deepcopy(data)
    for key in ('repairVersion','baseTake','repairRange','compiledContext'):partial.pop(key,None)
    partial.update(method='generate',frameAnchor=True,story=[],identityReferences=[])
    partial['storyboardAnchor']=False
    partial['shot'].update(start=shot['start']+start/fps,end=shot['start']+end/fps,
        startFrame=shot['startFrame']+start,endFrame=shot['startFrame']+end,
        generationSeconds=math.ceil((end-start)/fps*2)/2,references=[str(still)],
        prompt=('The editor isolated seconds '+str(start/fps)+' through '+str(end/fps)+
                ' of the original scene. Any times in the correction refer to that original scene; '
                'apply the requested corrected movement from the opening of this replacement. '
                'Preserve the actual visible setting and camera view in the opening picture. '+data['correction'].replace('\n',' ')))
    partial['sceneContinuity']='Keep the same visible people, wardrobe, props, lighting and setting as the opening picture. One simple physical action, with no new scene or internal cut.'
    if 'characterReferences' in shot:
        partial['shot']['references'] = [str(still), *[r['source'] for r in shot['characterReferences']]]
        partial['shot']['referenceHashes'] = [hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in partial['shot']['references']]
    if data.get('smartPlan'):
        # The visual planner has already translated the complaint into the target
        # action. Do not echo old cut times or the defective motion into H3.
        partial['shot']['prompt']=data['correction']
        partial['sceneContinuity']=data['sceneContinuity']
    partial['timing']=vocal_windows_for_range(data['timing'],start/fps,end/fps)
    write(patch/'input.json',partial)
    write(work/'phase.json',{'phase':f'Replacing {start/fps:.2f}–{end/fps:.2f} seconds from a still frame; keeping the rest of the scene'})
    if not (patch/'checks.json').exists():render_scene(patch,partial)
    write(work/'phase.json',{'phase':'Keeping the source frames outside the repair range'})
    target=work/'background.mp4'
    splice_range(source,patch/'background.mp4',target,start,end,count,fps)
    checks=read(patch/'checks.json')
    checks.update(method='frame-regenerate',baseTakeId=data['baseTake']['id'],frames=count,
        audioStart=shot['start'],audioEnd=shot['end'],repairRange=region,
        preservedFrames={'before':start,'after':count-end},preservation='lossless decoded source frames outside the repair range',
        possibleInternalCuts=[round(t+start/fps,5) for t in checks.get('possibleInternalCuts',[])],
        sourceSha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        manualReview=['Corrected motion within the replacement','Entry and exit boundaries of the replacement','Lip sync where singing is present'])
    checks['anchorFrame']=anchor
    checks['leadingRest']=data['timing']['leadingRest']
    write(work/'checks.json',checks)


def render_reuse(work,data):
    """Conform one existing shot to the scene; never re-synthesize its action."""
    from .film_intelligence import detected_cuts, validate_reuse
    plan=data['smartPlan'];shot=data['shot'];fps=data['plan']['fps']
    count=shot['endFrame']-shot['startFrame'];source=Path(data['baseTake']['source'])
    region=plan['sourceRange'];start,end=region['startFrame'],region['endFrame']
    if plan['speechPolicy']!='silent' or plan['scope']!='entire-scene':
        raise ValueError('Cannot slow a vocal performance or partial repair.')
    validate_reuse(start,end,count,fps,detected_cuts(source))
    write(work/'phase.json',{'phase':f'Keeping one continuous shot at {(end-start)/count:.0%} speed; original song timing retained'})
    # Motion interpolation smooths the slowed source. Padding only supplies edge
    # samples for interpolation; the final trim fixes the exact original length.
    filters=(f'trim=start_frame={start}:end_frame={end},setpts=(PTS-STARTPTS)*{count}/{end-start},'
             f'tpad=stop_mode=clone:stop_duration=0.2,minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,'
             f'trim=end_frame={count},setpts=N/({fps}*TB)')
    target=work/'background.mp4'
    run(['ffmpeg','-y','-v','error','-i',source,'-an','-vf',filters,'-frames:v',count,
         '-c:v','libx264','-threads',4,'-preset','fast','-crf',18,'-pix_fmt','yuv420p','-movflags','+faststart',target])
    actual=next(s for s in probe(target)['streams'] if s['codec_type']=='video')
    if int(actual['nb_frames'])!=count:raise RuntimeError('Continuous shot frame count mismatch')
    run(['ffmpeg','-v','error','-xerror','-i',target,'-f','null','-'])
    write(work/'checks.json',{'decode':'complete','frames':count,'fps':fps,
        'dimensions':[actual['width'],actual['height']],'audioStart':shot['start'],'audioEnd':shot['end'],
        'method':'reuse-shot','baseTakeId':data['baseTake']['id'],'sourceRange':region,
        'playbackSpeed':(end-start)/count,'conditioningAudio':'none',
        'baseSha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'sourceSha256':hashlib.sha256(target.read_bytes()).hexdigest(),
        'manualReview':['Review the slowed motion and interpolation around the face, hands and moving edges.',
                        'Check the mouth throughout. Existing action is retained, so speech-like movement cannot be removed by slowing it.']})


def vocal_windows_for_range(timing,start,end):
    from .film_review import vocal_windows
    return vocal_windows({'cues':[{'words':timing['words']}]},{'start':start,'end':end})


def generation_prompt(data):
    if film_cast.prompt_sections(data) is not None:
        return cast_prompt(data)
    shot=data['shot']
    singing=voice_contract(data)['mode']=='recorded-vocals'
    audio_definition='<Audio 1> is the exact recorded vocal excerpt for <Subject 1> (S1), aligned at clip time zero.' if singing else ''
    audio_retention='<Audio 1>: reference - original vocal timing, pauses and breaths.' if singing else ''
    performance=voice_direction(data)
    anchored=data.get('frameAnchor',False)
    picture_definition='<Picture 1> is the opening frame of [Shot 1], defining the visible setting, composition, people and pose.' if anchored else ''
    picture_role='fully_preserved - opening composition and visible scene.' if anchored else 'weak_reference - identity and visual style, with the specified scene composition.'
    return f'''subject_definitions:
<Subject 1> is the lead character in <Picture 1>. Retain their exact identity, age, hair, face and wardrobe.
{picture_definition}
{audio_definition}

summary:
[{ 'keyframe completion' if anchored else 'reference generation'}{ ' + audio reference' if singing else ''}] One continuous {'recorded vocal performance' if singing else 'quiet observational scene'} guided by <Picture 1>.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - consistent identity, proportions and wardrobe from Picture 1.
{('<Picture 1> ([Shot 1] first frame): '+picture_role) if anchored else ''}
{audio_retention}

detailed_description:
Photographic live-action cinematography with natural lighting, restrained camera motion and the reference image's visual style.
[Shot 1] <Subject 1>, the person identified in <Picture 1>, performs the following physical action: {shot['prompt']}
{ 'The shot begins from <Picture 1>. Its actual visible location and camera composition take priority over older storyboard notes. The requested action starts immediately and proceeds forward through this isolated replacement.' if anchored else ''}
Scene continuity: {data['sceneContinuity']}
{performance}
The same physical action develops as one continuous moment for the full {shot['generationSeconds']} seconds. The camera holds the stated viewing side, height and distance; any requested tracking is gradual and follows the subject's physical movement. The person keeps the same face, age, hair silhouette and complete wardrobe as the reference. Coat edges, shirt layers and sleeves remain attached to the same body as posture changes. The eyes stay engaged with the environment and the immediate action, rather than addressing an audience beyond the lens. Fingers and hands maintain their natural resting shape unless the scene specifically assigns them an action.

The opening establishes the subject's position relative to the existing ground, walls, doorways and other fixed features. Through the middle, weight shifts and clothing movement follow the same deliberate pace. A walking subject places each foot on the visible surface and continues along the indicated route; a stationary subject maintains the stated pose with only natural balance adjustments. The ending continues that same state instead of introducing another event. The face follows the vocal-and-rest state described above independently of the body's movement.

Preserve the established light direction and exposure. Shadows stay connected to their subjects, and reflections remain on the corresponding surfaces. Existing objects keep their count, position and ownership. Background architecture holds its shape as the camera or person moves. Maintain this one camera setup and the original scene's cast and setting through the final frame, allowing the motion and ambient visual details to carry the shot.

overall_soundscape:
N/A

non_diegetic_music:
N/A
'''


def cast_prompt(data):
    definitions, retention, identity_rules = film_cast.prompt_sections(data)
    policy = voice_contract(data)
    singing = policy['mode'] == 'recorded-vocals'
    editing = data.get('repairVersion', 1) >= 2
    anchor = data.get('frameAnchor', False)
    story = data['shot'].get('story', {}) if data.get('storyboardAnchor') and not editing else {}
    story_path = ('Storyboard direction: '+str(story['framing'])+'\n'
                  'Begin with: '+str(story['startState'])+'\n'
                  'By the final frame: '+str(story['endState'])+'\n'
                  'The action serves this story purpose: '+str(story['purpose'])) if story else ''
    task = 'video editing' if editing else 'keyframe completion' if anchor else 'reference generation'
    action = data.get('correction') or data['shot']['prompt']
    source = ('<Video 1> supplies the source framing, camera path, cast arrangement and physical action to edit. '
              'Character sheets override any changing identities in that source video.' if editing else
              '<Picture 1> is the opening frame, supplying the actual setting, composition and pose.' if anchor else '')
    audio = (f"<Audio 1> is the isolated recorded vocal for <Subject {policy['subjectNumber']}> (S1), aligned at clip time zero. " +
             ('The original performance, including held notes, breaths and pauses, is preserved continuously.'
              if policy.get('timingAuthority')=='recorded-audio' else 'Samples outside measured vocal windows are silent.') if singing else '')
    return f'''subject_definitions:
{definitions}
{source}
{audio}

summary:
[{task}{' + audio reference' if singing else ''}] One coherent music-video scene with the explicitly assigned cast.

retention_analysis:
{retention}
{'<Video 1> (source video editing): partially_preserved - retain existing staging, shot order and cut times except for the requested correction.' if editing else ''}
{'<Picture 1> ([Shot 1] first frame): fully_preserved - opening composition, location and pose.' if anchor else ''}
{'<Audio 1>: reference - recorded syllable timing and silent rests only.' if singing else ''}

detailed_description:
Use the visual medium, era, lighting and cinematography specified by the storyboard. Preserve natural anatomy and coherent physical movement.
[Shot 1] {action}
{story_path}
Scene continuity: {data['sceneContinuity']}
{identity_rules}
{voice_direction(data)}
{'The continuous recorded vocal takes priority over estimated word timings, scene notes and source mouth motion.' if policy.get('timingAuthority')=='recorded-audio' else 'The measured vocal and rest policy takes priority over any scene notes or source mouth motion.'} Instrumental performance means hands and body playing the assigned instrument.
Keep each face recognizable as its own character at every camera distance, angle and motion speed. Preserve hair length, beard shape, body silhouette and garment structure from first frame to last.
The scene is one continuous physical moment. Keep all prop counts and ownership consistent, with hands attached naturally to the correct body and instrument.
Clothing moves with the body while retaining its color and shape. Light direction and shadows remain consistent with the environment. Background architecture stays coherent as the camera moves.
{'Preserve source camera movement and shot order while applying the specific correction.' if editing else 'Use one camera setup and one simple action, with no internal cuts, split screens, montage, scene change or new arrivals.'}
No sheet grid, duplicated character views, captions or overlays. The ending continues the same cast, physical action and setting across the scene boundary.

overall_soundscape:
N/A

non_diegetic_music:
N/A
'''


def render_scene(work,data):
    if data.get('method') == 'timing':return render_timing(work, data)
    if data.get('method') == 'frame-regenerate':return render_range(work, data)
    if data.get('method') == 'reuse-shot':return render_reuse(work, data)
    if (work/'context-brief.json').exists():data={**data,'compiledContext':read(work/'context-brief.json')}
    shot=data['shot'];source=Path(data['plan']['audio']);fps=data['plan']['fps']
    hybrid=film_audio_drive.enabled(data['plan'])
    refined=data['plan'].get('renderProfile') == film_cast.PROFILE
    film_cast.check_references(data)
    policy=voice_contract(data)
    locked_vocal=refined and policy.get('timingAuthority')=='recorded-audio'
    source,conditioning=((source,'full-mix-locked') if hybrid and not refined else
        conditioning_source(source,shot['type'],os.environ.get('SOUND_VISION_DATA',str(Path(__file__).resolve().parent.parent/'data'))))
    audio_enabled = (hybrid and not refined) or policy['mode']=='recorded-vocals'
    if refined and audio_enabled and conditioning != 'isolated-vocal':
        raise ValueError('The isolated vocal stem is unavailable. Prepare vocal timing before rendering a singing scene.')
    if locked_vocal:conditioning='isolated-vocal-locked'
    data={**data,'conditioningAudio':conditioning}
    if hybrid:
        from .film_vocal_timing import validate_render, VERSION
        validate_render(data)
        if not refined and (len(shot['references']) != 1 or data.get('identityReferences') or data.get('repairVersion')):
            raise ValueError('Audio Drive requires exactly one shared character reference and a fresh scene render.')
        actual_hash=hashlib.sha256(Path(shot['references'][0]).read_bytes()).hexdigest()
        if not refined and actual_hash != shot.get('referenceSha256'):
            raise ValueError('The shared character reference changed. No scene was submitted.')
        policy={**policy,'conditioningMode':'source-audio-locked' if locked_vocal or not refined else 'none','timingVersion':VERSION}
    if data.get('storyboardAnchor') and data['plan'].get('lyrics','').strip():
        from .film_vocal_timing import validate_render
        validate_render(data)
    if not audio_enabled:conditioning='none'
    library=Path(os.environ.get('SOUND_VISION_H3_LIBRARY','/srv/ai/h3lix-library'))/data['runId']
    intent=work/'provider-intent.json'
    if not intent.exists():
        write(work/'phase.json',{'phase':'Waiting for the existing H3 renderer'})
        deadline=time.monotonic()+7200
        while True:
            machine=api('/api/machine')
            if machine.get('online') and not machine.get('busy') and not machine.get('activeJobId'):break
            if time.monotonic()>deadline:raise TimeoutError('Renderer remained busy; no scene was submitted.')
            time.sleep(4)
        references=([Path(p) for p in shot['references']] if 'characterReferences' in shot else
                    [Path(shot['references'][0]),*[Path(r['source']) for r in data.get('identityReferences',[])]])
        previous=next((s for s in data['story'] if s['index']==shot['index']-1),None)
        following=next((s for s in data['story'] if s['index']==shot['index']+1),None)
        for neighbor,label in [(previous,'previous-end'),(following,'next-start')]:
            if neighbor and neighbor.get('source'):
                original=data['plan']['shots'][neighbor['index']]
                when=max(0,(original['endFrame']-original['startFrame']-2)/fps) if label=='previous-end' else 0
                # Retain neighboring frames for boundary review, not as render
                # references: unrelated locations otherwise induce internal cuts.
                target=work/(label+'.jpg');frame(neighbor['source'],when,target)
        audio=work/'song-window.wav'
        if audio_enabled:
            if hybrid and not refined:film_audio_drive.prepare_audio(audio,source,shot)
            else:prepare_vocal_reference(audio,source,shot,policy)
        assets=[{'id':'picture-'+str(i+1),'kind':'image','fileName':p.name,'role':'Character identity and appearance',
                 'dataUrl':'data:image/'+('png' if p.suffix=='.png' else 'jpeg')+';base64,'+base64.b64encode(p.read_bytes()).decode()}
                for i,p in enumerate(references)]
        if audio_enabled:assets.append({'id':'song-window','kind':'audio','fileName':'song-window.wav','finalSoundtrack':False,
                       'dataUrl':'data:audio/wav;base64,'+base64.b64encode(audio.read_bytes()).decode()})
        if data.get('repairVersion', 1) >= 2:
            base = prepare_source_reference(work, data)
            assets.append({'id':'source-video','kind':'video','fileName':'source-scene.mp4','includeSoundtrack':False,
                           'role':'Source video to edit','dataUrl':'data:video/mp4;base64,'+base64.b64encode(base.read_bytes()).decode()})
        prompt=prompt_for(data,len(references));(work/'prompt.txt').write_text(prompt)
        request={'mode':'Reference to Video','title':data['plan']['title']+' — '+shot['name'],
                 'prompt':prompt,'ratio':'16:9','duration':shot['generationSeconds'],'tier':'native',
                 'turbo':'On','steps':4,'nativeAudio':'Off','seed':data['seed'],'runId':data['runId'],'assets':assets}
        if hybrid and not refined:
            request.update(audioDrive='vrgdg-source',generationModel='current',profile='advanced',
                           tier=data['plan'].get('renderTier','native'))
        if refined:
            request.update(generationModel=film_cast.PROFILE, profile='advanced', steps=8,
                           tier=data['plan'].get('renderTier','native') if hybrid or data['plan'].get('workflow')=='short-film' else 'native')
        if locked_vocal:request['audioDrive']='vrgdg-vocal'
        validator=Path(os.environ.get('SOUND_VISION_H3_VALIDATOR','/srv/ai/h3lix-current/server/prompting.mjs'))
        if validator.is_file():
            code="import fs from 'node:fs';import {pathToFileURL} from 'node:url';const {validateH3Prompt}=await import(pathToFileURL(process.argv[1]).href);const x=JSON.parse(fs.readFileSync(0,'utf8'));const r=validateH3Prompt(x.prompt,'Reference to Video',{duration:x.duration,assets:x.assets});console.log(JSON.stringify({ok:r.ok,errors:r.errors,warnings:r.warnings}));"
            validation=subprocess.run(['node','--input-type=module','-e',code,str(validator)],
                input=json.dumps({'prompt':prompt,'duration':shot['generationSeconds'],'assets':[{'kind':a['kind'],'finalSoundtrack':a.get('finalSoundtrack',False)} for a in assets]}),
                capture_output=True,text=True,timeout=30,check=True)
            checked=json.loads(validation.stdout);write(work/'prompt-validation.json',checked)
            if not checked['ok']:raise RuntimeError('Prompt check failed before H3 submission: '+'; '.join(checked['errors']))
        write(intent,{'runId':data['runId'],'submissionStarted':True,
                      'renderProfile':data['plan'].get('renderProfile','legacy-turbo'),
                      'generationModel':request.get('generationModel','current'), 'steps':request['steps'],
                      'audioDrive':request.get('audioDrive'),
                      'castIds':shot.get('castIds',[]),'vocalistId':shot.get('vocalistId'),
                      'voicePolicy':policy,
                      'baseTakeId':data.get('baseTake',{}).get('id'),
                      'baseSha256':hashlib.sha256(Path(data['baseTake']['source']).read_bytes()).hexdigest() if data.get('baseTake') else None,
                      'referenceVideo':{'dimensions':[512,288],'fps':24,'sha256':hashlib.sha256(base.read_bytes()).hexdigest()} if data.get('baseTake') else None,
                      'assetKinds':[a['kind'] for a in assets],
                      'requestSha256':hashlib.sha256(json.dumps(request,sort_keys=True).encode()).hexdigest(),
                      'referenceHashes':[hashlib.sha256(p.read_bytes()).hexdigest() for p in references]})
        # This POST is deliberately never replayed after an uncertain response.
        try:response=api('/api/jobs',request)
        except H3Rejected as error:
            write(work/'provider-rejection.json',{'error':str(error),'runId':data['runId']})
            raise
        write(work/'provider.json',response)
        if response.get('runId')!=data['runId']:raise RuntimeError('Unexpected provider run ID; retained for recovery.')
    deadline=time.monotonic()+3600
    if (work/'provider-rejection.json').exists():
        raise H3Rejected(read(work/'provider-rejection.json')['error'])
    while True:
        item=published(library/'manifest.json')
        if item:break
        state=published(library/'status.json') or {}
        event=state.get('lastEvent',{})
        if state.get('state')=='error' or event.get('event')=='job-error':
            raise RuntimeError(event.get('message','H3 scene failed. Original and attempt retained.'))
        if not state and not (work/'provider.json').exists():
            raise RuntimeError('Submission response was interrupted. Recover this same run after H3 finishes; no duplicate was submitted.')
        write(work/'phase.json',{'phase':event.get('message','Recovering the existing H3 scene')})
        if time.monotonic()>deadline:raise TimeoutError('H3 run retained. Recover the existing run before creating another take.')
        time.sleep(4)
    original=Path(item['videoPath']);shutil.copyfile(original,work/'provider.mp4')
    if hybrid and not refined and item.get('settings',{}).get('audioDrive') != 'vrgdg-source':
        raise RuntimeError('The provider did not confirm Audio Drive. The result was not selected.')
    if refined and (item.get('settings',{}).get('generationModel') != film_cast.PROFILE or
                    item.get('settings',{}).get('steps') != 8):
        raise RuntimeError('The provider did not confirm the Singularity first pass. The result was retained for inspection.')
    if locked_vocal and item.get('settings',{}).get('audioDrive')!='vrgdg-vocal':
        raise RuntimeError('The provider did not confirm locked vocal audio. This saved result is retained; a new take must use the updated audio-lock path.')
    info=probe(original);stream=next(s for s in info['streams'] if s['codec_type']=='video')
    frames=shot['endFrame']-shot['startFrame']
    if float(stream.get('duration',info['format']['duration']))+.001<frames/fps:raise RuntimeError('Generated scene is too short; it was not selected.')
    write(work/'phase.json',{'phase':'Checking and preparing the candidate'})
    target=work/'background.mp4'
    dimensions=data['plan']['output'] if hybrid else [1920,1080]
    if hybrid and [stream['width'],stream['height']] != dimensions:
        raise RuntimeError('Renderer dimensions do not match the Audio Drive project.')
    filters=f'fps={fps},setsar=1' if hybrid else f'fps={fps},scale=1920:1080:force_original_aspect_ratio=increase:flags=lanczos,crop=1920:1080,setsar=1'
    run(['ffmpeg','-y','-v','error','-i',original,'-an','-vf',filters,
         '-frames:v',frames,'-c:v','libx264','-threads',6,'-preset','fast','-crf',18,'-pix_fmt','yuv420p','-movflags','+faststart',target])
    actual=next(s for s in probe(target)['streams'] if s['codec_type']=='video')
    if int(actual['nb_frames'])!=frames:raise RuntimeError('Frame count mismatch; candidate was not selected.')
    run(['ffmpeg','-v','error','-xerror','-i',target,'-f','null','-'])
    cut_log=subprocess.run(['ffmpeg','-hide_banner','-i',str(target),'-vf',"select='gt(scene,0.24)',showinfo",'-an','-f','null','-'],capture_output=True,text=True,check=True).stderr
    cuts=[float(t) for t in re.findall(r'pts_time:([0-9.]+)',cut_log)]
    write(work/'checks.json',{'decode':'complete','frames':frames,'fps':fps,'dimensions':dimensions,
                            'workflow':data['plan'].get('workflow','directed'),
                            'renderProfile':data['plan'].get('renderProfile','legacy-turbo'),
                            'castIds':shot.get('castIds',[]),'characterSheetVersion':data['plan'].get('characterSheetVersion'),
                            'vocalTimingVersion':data['timing'].get('version'),
                            'referenceSha256':shot.get('referenceSha256'),
                            'audioStart':shot['start'],'audioEnd':shot['end'], 'leadingRest':data['timing']['leadingRest'],
                            'possibleInternalCuts':cuts,'continuityCompiler':data.get('compiledContext',{}).get('provider','saved-scene-notes'),
                            'conditioningAudio':conditioning,'voicePolicy':policy,
                            'method':data.get('method','legacy-regeneration'), 'baseTakeId':data.get('baseTake',{}).get('id'),
                            'manualReview':['Lip sync throughout the scene','People match the references','Objects keep their count and ownership','Both neighboring cuts'],
                            'sourceSha256':hashlib.sha256(target.read_bytes()).hexdigest(),'providerRunId':data['runId']})


def export_film(work,data):
    if film_audio_drive.enabled(data['plan']):return film_audio_drive.export_film(work,data)
    root=Path(__file__).resolve().parent.parent
    plan=data['plan'];clips=work/'clips'
    for shot,selected in zip(plan['shots'],data['story']):
        shot['runId']='scene-'+str(shot['index'])
        folder=clips/shot['runId'];folder.mkdir(parents=True,exist_ok=True)
        target=folder/'background.mp4'
        if not target.exists():
            try:os.link(selected['source'],target)
            except OSError:shutil.copyfile(selected['source'],target)
        write(folder/'receipt.json',{'selected':selected['selected']})
    write(work/'film-plan.json',plan)
    write(work/'phase.json',{'phase':'Assembling the selected scenes with the original soundtrack'})
    run([root/'.venv-alignment/bin/python',root/'scripts/video/compose-music-film.py','--plan',work/'film-plan.json',
         '--audio',plan['audio'],'--font',root/'assets/fonts/SV-Manrope.ttf','--output',work/'film.mp4','--clips',clips])
    write(work/'phase.json',{'phase':'Checking the full export and soundtrack timing'})
    run([root/'.venv-alignment/bin/python',root/'scripts/video/verify-film.py','--film',work/'film.mp4',
         '--audio',plan['audio'],'--plan',work/'film-plan.json'])
    write(work/'checks.json',read(work/'film.verification.json'))


def main():
    work=Path(sys.argv[1]);data=read(work/'input.json')
    if data.get('method')=='smart':
        data=read(work/'planned-input.json')
    with (work/'worker.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            if (work/'checks.json').exists():return
            if data['kind']=='scene':render_scene(work,data)
            else:export_film(work,data)
        except Exception as error:
            write(work/'failure.json',{'error':str(error)[:1500]});raise


if __name__=='__main__':main()
