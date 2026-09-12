"""Publish only verified finished film files to the local review page."""
from pathlib import Path
import errno, hashlib, html, json, os, shutil, subprocess

root=Path(__file__).resolve().parents[2]
delivery=root/'deliveries/two-films-20260910'
public=root/'public/productions/two-films-20260910'
films=[
    {'slug':'forwarding-address','title':'Forwarding Address','artist':'Rental Hours',
     'file':'Forwarding-Address-Rental-Hours','style':'Trip-hop / alternative soul','time':'4:16',
     'detail':'Kinetic lyrics over thirteen scenes using eight original audio-reactive visualizers.'},
    {'slug':'small-repairs','title':'Small Repairs','artist':'The Sunday Repairs',
     'file':'Small-Repairs-The-Sunday-Repairs','style':'Roots rock / soul','time':'3:23',
     'detail':'Twenty-two narrative and performance scenes, including eight audio-driven singing shots.'},
]
for film in films:
    folder=delivery/film['slug'];video=folder/(film['file']+'.mp4')
    verification=json.loads(video.with_suffix('.verification.json').read_text())
    receipt=json.loads(video.with_suffix('.receipt.json').read_text())
    if verification['decode']!='complete' or verification['frames']!=receipt['frames']:
        raise RuntimeError('Film is not verified: '+film['title'])
    if hashlib.file_digest(video.open('rb'),'sha256').hexdigest()!=receipt['outputSha256']:
        raise RuntimeError('Film checksum does not match its receipt')
public.mkdir(parents=True,exist_ok=True)

def link(source,name):
    target=public/name
    if target.is_symlink():
        if target.resolve()!=source.resolve():raise RuntimeError('Unexpected existing link: '+str(target))
    elif target.exists():
        if hashlib.file_digest(target.open('rb'),'sha256').digest()!=hashlib.file_digest(source.open('rb'),'sha256').digest():
            raise RuntimeError('Refusing to replace a different existing file: '+str(target))
    else:
        try:target.symlink_to(os.path.relpath(source,public))
        except OSError as error:
            if error.errno not in {errno.ENOTSUP,errno.EOPNOTSUPP}:raise
            shutil.copyfile(source,target)

cards=[]
for film in films:
    folder=delivery/film['slug'];stem=film['file'];poster=folder/(stem+'.jpg')
    subprocess.run(['ffmpeg','-y','-v','error','-ss','3','-i',str(folder/(stem+'.mp4')),
        '-vf','scale=1280:720','-frames:v','1','-q:v','2',str(poster)],check=True)
    link(folder/(stem+'.mp4'),stem+'.mp4');link(poster,stem+'.jpg')
    link(folder/'audio.flac',stem+'.flac');link(folder/'audio.mp3',stem+'.mp3')
    link(folder/'lyrics.txt',stem+'-lyrics.txt')
    cards.append(f'''<article id="{film['slug']}">
<div class="identity"><h2>{html.escape(film['title'])}</h2><p>{html.escape(film['artist'])}</p></div>
<video controls playsinline preload="metadata" poster="./{stem}.jpg"><source src="./{stem}.mp4" type="video/mp4"></video>
<div class="meta"><span>{film['style']}</span><span>{film['time']} · 1080p</span></div>
<p class="description">{film['detail']}</p>
<nav class="downloads" aria-label="Download {film['title']}"><a href="./{stem}.mp4" download>Download MP4</a><a href="./{stem}.flac" download>FLAC</a><a href="./{stem}.mp3" download>MP3</a><a href="./{stem}-lyrics.txt" download>Lyrics</a></nav>
</article>''')
page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Two films · Sound/Vision</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#111316;color:#e5e3df;font:14px/1.5 system-ui,-apple-system,sans-serif}a{color:inherit}header,main,footer{max-width:1500px;margin:auto;padding:28px 40px}header{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #303034;font-size:12px;color:#adaaa5;letter-spacing:.08em}header a{text-decoration:none}h1{font:400 34px Georgia,serif;margin:12px 0 30px}section{display:grid;grid-template-columns:1fr 1fr;gap:36px}article{min-width:0}.identity{min-height:86px}h2{font:400 27px Georgia,serif;margin:0 0 5px}.identity p{margin:0;color:#a39f99}video{display:block;width:100%;aspect-ratio:16/9;background:#07090c;border:1px solid #33343a;border-radius:7px}.meta{display:flex;justify-content:space-between;gap:15px;margin:18px 0 12px;font-size:12px;color:#aaa6a0}.description{max-width:520px;min-height:44px;color:#cbc6be}.downloads{display:flex;flex-wrap:wrap;gap:9px}.downloads a{padding:9px 14px;border:1px solid #414046;border-radius:5px;text-decoration:none;font-size:12px}.downloads a:first-child{background:#dfd4c4;color:#211d19;border-color:#dfd4c4}.downloads a:hover{border-color:#b5a894}footer{color:#8e8b86;font-size:12px;border-top:1px solid #303034;margin-top:30px}footer a{margin-right:22px}@media(max-width:850px){header,main,footer{padding:22px}section{grid-template-columns:1fr;gap:42px}.identity{min-height:76px}.description{min-height:0}}
</style><header><a href="/video">SOUND / VISION</a><span>24 FPS · ORIGINAL SOUNDTRACKS</span></header><main><h1>Two films</h1><section>'''+''.join(cards)+'''</section></main><footer><a href="/visualizers/index.html">Explore the eight visualizers</a><a href="/video">Open the video workspace</a><p>The visualizer collection is original Apache-2.0 code. Audio-conditioned singing shots and lyric alignment remain reviewable in the production records.</p></footer></html>'''
(public/'index.html').write_text(page)
(delivery/'review-page.json').write_text(json.dumps({'url':'http://127.0.0.1:5190/productions/two-films-20260910/index.html','films':films},indent=2)+'\n')
print('http://127.0.0.1:5190/productions/two-films-20260910/index.html')
