"""Exercise real encoded inputs: untouched frames must survive the final merge."""
import importlib.util
import json
import subprocess
from pathlib import Path
import pytest


ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('film_compositor',ROOT/'scripts/video/compose-music-film.py')
compositor=importlib.util.module_from_spec(spec);spec.loader.exec_module(compositor)


def hashes(path,selection=None):
    args=['ffmpeg','-v','error','-i',str(path),'-map','0:v:0']
    if selection:args+=['-vf',selection]
    result=subprocess.check_output(args+['-f','framemd5','-'],text=True)
    return [line.rsplit(',',1)[1].strip() for line in result.splitlines() if not line.startswith('#')]


def test_compatible_source_is_copied_and_wrong_format_requires_normalization(tmp_path):
    source=tmp_path/'source.mp4';target=tmp_path/'target.mp4';source.write_bytes(b'encoded-video-fixture')
    video=dict(codec_type='video',codec_name='h264',profile='High',has_b_frames=2,width=1920,height=1080,pix_fmt='yuv420p',sample_aspect_ratio='1:1',
               field_order='progressive',nb_frames='240',r_frame_rate='24/1',avg_frame_rate='24/1',time_base='1/12288',start_time='0')
    assert compositor.prepare_scene(source,target,{'streams':[video]},240,24)=='copied-source'
    assert target.read_bytes()==source.read_bytes()
    target.write_bytes(b'overwrite')
    assert source.read_bytes()==b'encoded-video-fixture' # Never hard-link editable work files to masters.
    for key,value in [('profile','High 4:4:4 Predictive'),('has_b_frames',0),('nb_frames','239'),('time_base','1/90000'),('avg_frame_rate','25/1'),('pix_fmt','yuv444p'),('start_time','.1')]:
        assert not compositor.compatible_scene({'streams':[{**video,key:value}]},240,24)
    assert not compositor.compatible_scene({'streams':[video,{'codec_type':'audio'}]},240,24)


@pytest.mark.parametrize('lossless_middle',[False,True])
def test_title_scenes_render_once_and_middle_scene_stays_pixel_identical(tmp_path,lossless_middle):
    shots=[];clips=tmp_path/'clips'
    for index,color in enumerate(['blue','green','red']):
        folder=clips/f'scene-{index}';folder.mkdir(parents=True)
        pattern='testsrc2=size=1920x1080:rate=24:duration=10' if index==1 else f'color={color}:size=1920x1080:rate=24:duration=10'
        subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i',pattern,
            '-c:v','libx264','-threads','2','-preset','fast','-crf','0' if index==1 and lossless_middle else '18','-pix_fmt','yuv420p',
            '-video_track_timescale','12288',str(folder/'background.mp4')],check=True)
        (folder/'receipt.json').write_text('{}')
        shots.append(dict(index=index,name=f'Scene {index+1}',runId=f'scene-{index}',startFrame=index*240,endFrame=(index+1)*240))
    plan=dict(title='A title',artist='',fps=24,duration=30,shots=shots,output=[1920,1080],
              credits=dict(enabled=True,artist='Artist',songTitle='Song title',recordLabel='Record label'))
    file=tmp_path/'plan.json';file.write_text(json.dumps(plan));audio=tmp_path/'audio.wav'
    subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','sine=frequency=440:duration=30',str(audio)],check=True)
    target=tmp_path/'out/film.mp4'
    import sys
    subprocess.run([sys.executable,str(ROOT/'scripts/video/compose-music-film.py'),'--plan',str(file),'--audio',str(audio),
        '--font',str(ROOT/'public/fonts/LeagueSpartan.ttf'),'--clips',str(clips),'--output',str(target)],check=True)
    receipt=json.loads(target.with_suffix('.receipt.json').read_text())
    assert receipt['videoAssembly']=='stream-copy' and receipt['titleScenes']==[0,2]
    assert int(compositor.probe(target)['streams'][0]['nb_frames'])==720
    expected=target.parent/'composition/shot-01.mp4' if lossless_middle else clips/'scene-1/background.mp4'
    assert hashes(target,'trim=start_frame=240:end_frame=480,setpts=PTS-STARTPTS')==hashes(expected)
    assert receipt['compatibilityScenes']==([1] if lossless_middle else [])
    # A frame inside each title window must have visible burned-in text.
    for index in [0,2]:
        assert hashes(target,f'select=eq(n\\,{index*240+48})')!=hashes(clips/f'scene-{index}/background.mp4','select=eq(n\\,48)')
    log=json.loads((target.parent/'phase.json').read_text())
    assert 'Joining scenes without re-encoding video' in log['phase']
