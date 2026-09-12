"""Compose full-length visualizer or scene films without changing song timing."""
import argparse, hashlib, importlib.util, json, math, shutil, subprocess, time, sys
from pathlib import Path
from fractions import Fraction
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from backend.film_credits import credits_for, credit_lines, credit_windows, render_credits


def run(args, **kwargs):
    subprocess.run(list(map(str,args)),check=True,**kwargs)


def probe(path):
    return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]))


def phase(path,message):
    temporary=path.with_suffix('.next.json')
    temporary.write_text(json.dumps({'phase':message})+'\n');temporary.replace(path)


def compatible_scene(info,frames,fps):
    """Only our exact, video-only delivery format can skip normalization."""
    streams=info['streams']
    if len(streams)!=1 or streams[0]['codec_type']!='video':return False
    v=streams[0]
    try:
        return (v['codec_name']=='h264' and [v['width'],v['height']]==[1920,1080]
            and v.get('profile')=='High' and v.get('has_b_frames')==2
            and v['pix_fmt']=='yuv420p' and v.get('sample_aspect_ratio')=='1:1'
            and v.get('field_order')=='progressive' and int(v['nb_frames'])==frames
            and Fraction(v['r_frame_rate'])==fps and Fraction(v['avg_frame_rate'])==fps
            and Fraction(v['time_base'])==Fraction(1,12288)
            and abs(float(v.get('start_time',0)))<1e-6)
    except (KeyError,ValueError,ZeroDivisionError):return False


def prepare_scene(source,target,info,frames,fps):
    if compatible_scene(info,frames,fps):
        # An independent byte-for-byte copy protects source assets if a future
        # recovery overwrites its work file. No video encoder is involved.
        shutil.copyfile(source,target)
        return 'copied-source'
    run(['ffmpeg','-y','-v','error','-threads','4','-i',source,'-an','-vf',
         f'fps={fps},scale=1920:1080:force_original_aspect_ratio=increase:flags=lanczos,crop=1920:1080,setsar=1',
         '-frames:v',frames,'-c:v','libx264','-threads','6','-preset','fast','-crf','12','-profile:v','high',
         '-pix_fmt','yuv420p','-video_track_timescale','12288',target])
    return 'compatibility-render'


def encode_with_progress(command,frames,path,label='Encoding titles and soundtrack',**kwargs):
    command=list(map(str,command))
    command[1:1]=['-progress','pipe:1','-stats_period','1','-nostats']
    with subprocess.Popen(command,stdout=subprocess.PIPE,text=True,**kwargs) as process:
        for line in process.stdout:
            key,_,value=line.strip().partition('=')
            if key=='frame' and value.strip().isdigit():
                count=min(frames,int(value));percent=min(99,round(count/frames*100))
                phase(path,f'{label} · {percent}% ({count:,}/{frames:,} frames)')
        if process.wait():raise subprocess.CalledProcessError(process.returncode,command)


def needs_titles(shot,duration,fps,windows=None):
    start,end=shot['startFrame']/fps,shot['endFrame']/fps
    return any(start<b and end>a for a,b in (credit_windows(duration) if windows is None else windows))


def render_title_scene(source,target,shot,fps,work,status,windows):
    frames=shot['endFrame']-shot['startFrame'];start=shot['startFrame']/fps
    enabled='+'.join(f'gte(t,{a})*lt(t,{b})' for a,b in windows)
    filters=f"[0:v]setpts=PTS-STARTPTS+{start}/TB[scene];[scene][1:v]overlay=0:0:enable='{enabled}':shortest=1,setpts=PTS-STARTPTS[out]"
    encode_with_progress(['ffmpeg','-y','-v','error','-i',source,'-loop','1','-i',work/'credits.png','-an','-filter_complex',filters,'-map','[out]',
        '-frames:v',frames,'-c:v','libx264','-threads','8','-preset','fast','-crf','18',
        '-pix_fmt','yuv420p','-video_track_timescale','12288',target],frames,status,
        label=f"Rendering titles on scene {shot['index']+1}",cwd=work)
    if int(probe(target)['streams'][0]['nb_frames'])!=frames:raise ValueError('Title scene frame mismatch')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--audio',type=Path,required=True)
    parser.add_argument('--font',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--alignment',type=Path)
    parser.add_argument('--background',type=Path)
    parser.add_argument('--clips',type=Path)
    args=parser.parse_args()
    args.output=args.output.resolve()
    plan=json.loads(args.plan.read_text())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    work=args.output.parent/'composition'
    status=args.output.parent/'phase.json'
    work.mkdir(exist_ok=True)
    fonts=work/'fonts';fonts.mkdir(exist_ok=True)
    shutil.copyfile(args.font,fonts/args.font.name)
    ass=work/'titles.ass'
    if args.alignment:
        spec=importlib.util.spec_from_file_location('kinetic',Path(__file__).with_name('render-kinetic-film.py'))
        kinetic=importlib.util.module_from_spec(spec);spec.loader.exec_module(kinetic)
        alignment=json.loads(args.alignment.read_text())
        kinetic.write_ass(plan,alignment,args.font,ass)
        # Stronger edge/shadow for varied procedural backgrounds; preserve timings.
        text=ass.read_text().replace('&H6579EE&','&HA9D8EF&')
        text=text.replace('\\bord1.2','\\bord2.6\\shad1.5')
        ass.write_text(text)
    credits=credits_for(plan)
    windows=credit_windows(plan['duration']) if credit_lines(credits) else []
    credit_image,credit_info=render_credits(credits)
    credit_image.save(work/'credits.png')
    frame_count=math.ceil(plan['duration']*plan['fps'])
    source_args=[]
    stream_copy=not args.alignment and not args.background
    title_scenes=[]
    if args.background:
        v=next(s for s in probe(args.background)['streams'] if s['codec_type']=='video')
        if int(v['nb_frames'])!=frame_count:raise ValueError('Background must cover the exact full-song frame count')
        source_args=['-i',args.background.resolve()]
    else:
        normalized=[]
        for shot in plan['shots']:
            source=args.clips/shot['runId']/'background.mp4'
            deadline=time.monotonic()+3600
            while not (source.parent/'receipt.json').exists():
                state_path=args.plan.parent/'batch-status.json'
                state=json.loads(state_path.read_text()) if state_path.exists() else {}
                if state.get('state') in {'error','failed','cancelled'}:raise RuntimeError('Scene generation needs attention: '+str(state))
                if time.monotonic()>deadline:raise TimeoutError(str(source))
                time.sleep(10)
            frames=shot['endFrame']-shot['startFrame']
            info=probe(source);v=next(s for s in info['streams'] if s['codec_type']=='video')
            if float(v.get('duration',info['format']['duration']))+1e-4<frames/plan['fps']:
                raise ValueError('Source clip too short: '+str(source))
            target=work/f"shot-{shot['index']:02}.mp4"
            receipt=target.with_suffix('.json')
            expected={'sourceSha256':hashlib.file_digest(source.open('rb'),'sha256').hexdigest(),'frames':frames,'fps':plan['fps'],
                      'preparationVersion':3,'method':'copied-source' if compatible_scene(info,frames,plan['fps']) else 'compatibility-render'}
            phase(status,f"Preparing scene {shot['index']+1}/{len(plan['shots'])} · "+('preserving source video' if expected['method']=='copied-source' else 'matching the film format'))
            if not (target.exists() and receipt.exists() and json.loads(receipt.read_text())==expected):
                prepare_scene(source,target,info,frames,plan['fps'])
                if int(probe(target)['streams'][0]['nb_frames'])!=frames:raise ValueError('Normalized frame mismatch')
                receipt.write_text(json.dumps(expected,indent=2)+'\n')
            if stream_copy and needs_titles(shot,plan['duration'],plan['fps'],windows):
                titled=work/f"titled-{shot['index']:02}.mp4"
                render_title_scene(target,titled,shot,plan['fps'],work,status,windows)
                title_scenes.append(shot['index']);target=titled
            normalized.append(target)
            print('Prepared scene',shot['index'],shot['name'],flush=True)
        concat=work/'clips.ffconcat'
        concat.write_text('ffconcat version 1.0\n'+''.join(f"file '{p.name}'\nduration {(shot['endFrame']-shot['startFrame'])/plan['fps']:.12f}\n" for p,shot in zip(normalized,plan['shots'])))
        source_args=['-f','concat','-safe','0','-i',concat.resolve()]
    partial=args.output.with_suffix('.partial.mp4').resolve()
    filters=('eq=brightness=-0.035,' if args.alignment else '')+'ass=titles.ass:fontsdir=fonts'
    extra_inputs=[];video_map='0:v:0'
    filter_args=['-vf',filters] if args.alignment else []
    if not stream_copy and not args.alignment and windows:
        extra_inputs=['-loop','1','-i',work/'credits.png'];video_map='[out]'
        enabled='+'.join(f'gte(t,{a})*lt(t,{b})' for a,b in windows)
        filter_args=['-filter_complex',f"[0:v][2:v]overlay=0:0:enable='{enabled}':shortest=1[out]"]
    video_args=['-c:v','copy'] if stream_copy else [*filter_args,'-c:v','libx264','-threads','8','-preset','fast','-crf','18','-pix_fmt','yuv420p']
    label='Joining scenes without re-encoding video' if stream_copy else 'Encoding titles and soundtrack'
    phase(status,label+' · 0%')
    encode_with_progress(['ffmpeg','-y','-v','warning','-threads','4',*source_args,'-i',args.audio.resolve(),*extra_inputs,'-map',video_map,'-map','1:a:0',
        *video_args,'-frames:v',frame_count,'-c:a','aac','-b:a','320k','-ar','48000','-metadata','title='+plan['title'],
        '-metadata','artist='+plan['artist'],'-movflags','+faststart',partial],frame_count,status,label=label,cwd=work)
    v=next(s for s in probe(partial)['streams'] if s['codec_type']=='video')
    if int(v['nb_frames'])!=frame_count:raise ValueError('Final frame count mismatch')
    partial.replace(args.output)
    receipt={'title':plan['title'],'artist':plan['artist'],'frames':frame_count,'fps':plan['fps'],'duration':plan['duration'],'dimensions':[1920,1080],'lyrics':bool(args.alignment),'audioSha256':hashlib.file_digest(args.audio.open('rb'),'sha256').hexdigest(),'outputSha256':hashlib.file_digest(args.output.open('rb'),'sha256').hexdigest()}
    receipt.update(videoAssembly='stream-copy' if stream_copy else 'full-frame-render',titleScenes=title_scenes,
                   scenePreparationVersion=3,credits=credits,creditWindows=windows,creditFont=credit_info,
                   compatibilityScenes=[] if args.background else [shot['index'] for shot in plan['shots'] if json.loads((work/f"shot-{shot['index']:02}.json").read_text())['method']=='compatibility-render'])
    args.output.with_suffix('.receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt),flush=True)


if __name__=='__main__':main()
