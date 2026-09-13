"""Bounded CPU assembly: frame-exact cuts/blends, optional karaoke, original audio."""
import json
import math
import subprocess
import sys
from pathlib import Path


def requirements(lyrics=False):
    import shutil
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise ValueError('Install FFmpeg and ffprobe on the backend before creating a music video.')
    if lyrics:
        filters = subprocess.check_output(['ffmpeg', '-v', 'error', '-filters'], text=True)
        if not any(line.split()[1:2] == ['ass'] for line in filters.splitlines()):
            raise ValueError('On-screen lyrics require FFmpeg with libass support. Install the full FFmpeg build on the backend, or turn off on-screen lyrics.')


def run(command, cwd):
    subprocess.run([str(x) for x in command], cwd=cwd, check=True)


def probe(path):
    return json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))


def phase(work, message):
    temp = work/'phase.next.json'; temp.write_text(json.dumps({'phase': message})); temp.replace(work/'phase.json')


def timestamp(seconds):
    cs = round(seconds * 100)
    return f'{cs // 360000}:{cs // 6000 % 60:02}:{cs // 100 % 60:02}.{cs % 100:02}'


def ass_text(text):
    return str(text).replace('\\', '＼').replace('{', '｛').replace('}', '｝').replace('\n', ' ').replace('\r', ' ')


def subtitles(cues, target, width, height):
    header = f'''[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Lyrics,Manrope,{round(width*.046)},&H00FFFFFF,&H008999ED,&H00151515,&H90000000,-1,0,0,0,100,100,0,0,1,3,1,2,{round(width*.08)},{round(width*.08)},{round(height*.12)},1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    events = []
    # Short phrases stay readable on both landscape and portrait video.
    for cue in cues:
        words = cue['words']
        for offset in range(0, len(words), 7):
            group = words[offset:offset + 7]
            cursor = group[0]['start']; text = ''
            for word in group:
                gap = max(0, round((word['start'] - cursor) * 100))
                if gap: text += '{\\k' + str(gap) + '}'
                text += '{\\kf' + str(max(1, round((word['end'] - word['start']) * 100))) + '}' + ass_text(word['text']) + ' '
                cursor = word['end']
            events.append(f'Dialogue: 0,{timestamp(group[0]["start"])},{timestamp(group[-1]["end"])},Lyrics,,0,0,0,,{text.strip()}\n')
    target.write_text(header + ''.join(events), encoding='utf-8')


def compose(work, data):
    plan = data['plan']; fps = plan['fps']; overlap = plan['overlapFrames']
    width, height = (1920, 1080) if plan['aspect'] == '16:9' else (1080, 1920)
    # Tests can select small dimensions without changing any timing behavior.
    width, height = data.get('dimensions', [width, height])
    placements = plan['placements']
    prefix = ['ffmpeg', '-y', '-v', 'error', '-threads', '2']
    encode = ['-an', '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-threads', '4', '-pix_fmt', 'yuv420p', '-video_track_timescale', '12288']
    for i, clip in enumerate(data['clips']):
        phase(work, f'Preparing clip {i + 1}/{len(data["clips"])} for export')
        info = probe(clip['path']); stream = next(s for s in info['streams'] if s['codec_type'] == 'video')
        needed = max(p['endFrame'] - p['startFrame'] for p in placements if p['asset'] == i)
        if float(stream.get('duration', info['format']['duration'])) + .001 < needed/fps:
            raise ValueError(f'Clip {i + 1} is shorter than its planned duration. Its source is retained for review.')
        run([*prefix, '-i', clip['path'], '-vf', f'fps={fps},scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,setpts=PTS-STARTPTS', '-frames:v', needed, *encode, f'clip-{i}.mp4'], work)
    parts = []
    for i, placement in enumerate(placements):
        frames = placement['endFrame'] - placement['startFrame']
        head = overlap if i else 0
        tail = overlap if i < len(placements) - 1 else 0
        phase(work, f'Assembling scene {i + 1}/{len(placements)}')
        name = f'body-{i}.mp4'
        run([*prefix, '-i', f'clip-{placement["asset"]}.mp4', '-vf', f'trim=start_frame={head}:end_frame={frames-tail},setpts=PTS-STARTPTS', *encode, name], work)
        parts.append(name)
        if tail:
            next_p = placements[i + 1]
            name = f'blend-{i}.mp4'
            filters = (f'[0:v]trim=start_frame={frames-overlap}:end_frame={frames},setpts=PTS-STARTPTS[a];'
                       f'[1:v]trim=end_frame={overlap},setpts=PTS-STARTPTS[b];'
                       f"[a][b]blend=all_expr='A*(1-min(1,T/{overlap/fps}))+B*min(1,T/{overlap/fps})'[out]")
            run([*prefix, '-i', f'clip-{placement["asset"]}.mp4', '-i', f'clip-{next_p["asset"]}.mp4', '-filter_complex_threads', '2', '-filter_complex', filters, '-map', '[out]', '-frames:v', overlap, *encode, name], work)
            parts.append(name)
    (work/'sequence.ffconcat').write_text('ffconcat version 1.0\n' + ''.join(f"file '{name}'\n" for name in parts))
    phase(work, 'Adding the original song and timed lyrics')
    video = ['-c:v', 'copy']
    if data['cues']:
        subtitles(data['cues'], work/'lyrics.ass', width, height)
        fonts = Path(__file__).resolve().parent.parent/'assets/fonts'
        # Fixed file names keep user text out of FFmpeg filter syntax.
        import shutil
        if (fonts/'SV-Manrope.ttf').is_file():
            (work/'fonts').mkdir(exist_ok=True); shutil.copyfile(fonts/'SV-Manrope.ttf', work/'fonts/SV-Manrope.ttf')
        video = ['-vf', 'ass=lyrics.ass:fontsdir=fonts', '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-threads', '4', '-pix_fmt', 'yuv420p']
    run([*prefix, '-f', 'concat', '-safe', '0', '-i', 'sequence.ffconcat', '-i', data['audio'], '-map', '0:v:0', '-map', '1:a:0', *video, '-frames:v', plan['frames'], '-t', plan['duration'], '-c:a', 'aac', '-b:a', '320k', '-movflags', '+faststart', 'movie.partial.mp4'], work)
    info = probe(work/'movie.partial.mp4'); stream = next(s for s in info['streams'] if s['codec_type'] == 'video')
    if abs(float(stream.get('duration', 0)) - plan['duration']) > 1/fps + .005 or int(stream['nb_frames']) != plan['frames']:
        raise ValueError('The export did not cover the full song. Source clips are retained.')
    (work/'movie.partial.mp4').replace(work/'movie.mp4')
    (work/'checks.json').write_text(json.dumps({'frames': plan['frames'], 'duration': plan['duration'], 'dimensions': [width, height], 'originalAudio': True}))


if __name__ == '__main__':
    work = Path(sys.argv[1]).resolve()
    try:
        compose(work, json.loads((work/'input.json').read_text()))
    except Exception as error:
        (work/'failure.json').write_text(json.dumps({'message': str(error)})); raise
