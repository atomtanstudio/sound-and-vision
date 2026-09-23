"""Shared 30 fps photographic player renderer, derived from the approved originals.

Copyright 2026 Sound/Vision contributors. SPDX-License-Identifier: Apache-2.0
Analysis and the spectrum/ribbon drawing methods preserve the original films.
All paths come from an isolated render job; scene geometry is also validated by
visualizer-export-api.mjs before this process starts.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import time
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

FPS, SR = 30, 24000
FFMPEG = os.environ.get("FFMPEG_BINARY") or shutil.which("ffmpeg") or "ffmpeg"
FONT = next((str(p) for p in [
    Path("/System/Library/Fonts/Menlo.ttc"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
    Path("/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf"),
] if p.is_file()), None)
if FONT is None:
    raise RuntimeError("Install DejaVu Sans Mono or Liberation Mono for the video renderer.")


def run(args, **kwargs):
    return subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", *args], check=True, **kwargs)


def smooth(data, attack, release):
    result = np.empty_like(data)
    last = np.zeros_like(data[0])
    for i, value in enumerate(data):
        last = last + np.where(value > last, attack, release) * (value - last)
        result[i] = last
    return result

def analyse(audio, work):
    pcm = work / 'analysis.f32'
    if not pcm.exists():
        run(['-y', '-i', str(audio), '-f', 'f32le', '-acodec', 'pcm_f32le', '-ar', str(SR), '-ac', '2', str(pcm)])
    signal = np.fromfile(pcm, dtype='<f4').reshape(-1, 2)
    duration = len(signal) / SR
    count = math.ceil(duration * FPS)
    fft_size, bands = 2048, 48
    centers = np.minimum(np.arange(count) * SR // FPS, len(signal) - 1)
    mono = signal.mean(axis=1)
    padded = np.pad(mono, (fft_size // 2, fft_size // 2))
    stereo = np.pad(signal, ((512, 512), (0, 0)))
    freq = np.fft.rfftfreq(fft_size, 1 / SR)
    edges = np.geomspace(40, 11000, bands + 1)
    bins = []
    for low, high in zip(edges[:-1], edges[1:]):
        use = np.flatnonzero((freq >= low) & (freq < high))
        bins.append(use if len(use) else np.array([np.argmin(abs(freq - (low + high) / 2))]))
    spectrum = np.zeros((count, bands), np.float32)
    rms = np.zeros((count, 2), np.float32)
    wave = np.zeros((count, 300), np.float32)
    for start in range(0, count, 128):
        end = min(count, start + 128)
        locations = centers[start:end]
        windows = padded[locations[:, None] + np.arange(fft_size)]
        power = abs(np.fft.rfft(windows * np.hanning(fft_size), axis=1)) ** 2
        for band, use in enumerate(bins):
            spectrum[start:end, band] = np.sqrt(power[:, use].mean(axis=1))
        samples = stereo[locations[:, None] + np.arange(1024)]
        rms[start:end] = np.sqrt((samples ** 2).mean(axis=1))
        for i, block in enumerate(windows):
            filtered = np.convolve(block, np.ones(11) / 11, mode='same')
            crossing = np.flatnonzero((filtered[350:850] <= 0) & (filtered[351:851] > 0))
            offset = int(crossing[0]) + 350 if len(crossing) else 400
            wave[start + i] = np.interp(np.linspace(0, 700, 300), np.arange(701), filtered[offset:offset + 701])
    db = 20 * np.log10(spectrum + 1e-7)
    ref = np.percentile(db, 96, axis=0)
    spectrum = np.clip((db - ref + 43) / 43, 0, 1)
    rms_db = 20 * np.log10(rms + 1e-8)
    gate = np.clip((rms_db.mean(axis=1) + 65) / 25, 0, 1)
    spectrum *= gate[:, None]
    spectrum = smooth(spectrum, .78, .22)
    levels = smooth(np.clip((rms_db + 48) / 48, 0, 1), .7, .18)
    bass = smooth(spectrum[:, :14].mean(axis=1), .8, .22)
    energy = smooth(np.clip((rms_db.mean(axis=1) + 45) / 35, 0, 1), .7, .2)
    flux = np.maximum(np.diff(spectrum, axis=0, prepend=spectrum[:1]), 0).mean(axis=1)
    onset = np.clip(flux / max(.02, np.percentile(flux, 95)), 0, 1)
    wave = np.clip(wave / max(.04, np.percentile(abs(wave), 98)), -1, 1)
    features = dict(spectrum=spectrum, levels=levels, bass=bass, energy=energy, onset=onset, wave=wave, duration=duration)
    np.savez_compressed(work / 'features.npz', **features)
    report = {'duration_seconds': duration, 'sample_rate_analysis': SR, 'frames': count, 'frequency_bands': bands,
              'frequency_range_hz': [40, 11000], 'source_sha256': hashlib.sha256(audio.read_bytes()).hexdigest(),
              'analysis': 'Centered FFT and RMS windows at each output frame; attack/release smoothing; silence gate.'}
    (work / 'analysis-report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)
    return features

class Surface:
    """Precompute the inverse homography from a physical glass quadrilateral."""
    def __init__(self, quad, size):
        self.width, self.height = size
        points = np.array(quad, dtype=float)
        x0, y0 = np.floor(points.min(axis=0)).astype(int)
        x1, y1 = np.ceil(points.max(axis=0)).astype(int) + 1
        self.box = (int(x0), int(y0), int(x1), int(y1))
        self.patch_size = (int(x1 - x0), int(y1 - y0))
        points -= [x0, y0]
        uv = [(0, 0), (self.width - 1, 0), (self.width - 1, self.height - 1), (0, self.height - 1)]
        matrix, rhs = [], []
        for (x, y), (u, v) in zip(points, uv):
            matrix.extend([[x,y,1,0,0,0,-u*x,-u*y], [0,0,0,x,y,1,-v*x,-v*y]])
            rhs.extend([u,v])
        self.transform = np.linalg.solve(matrix, rhs)
        self.mask = Image.new('L', size, 255).transform(self.patch_size, Image.Transform.PERSPECTIVE,
                                                      self.transform, Image.Resampling.BICUBIC)

    def composite(self, canvas, texture):
        patch = texture.transform(self.patch_size, Image.Transform.PERSPECTIVE,
                                  self.transform, Image.Resampling.BICUBIC)
        canvas.paste(patch, self.box[:2], self.mask)

class ConsoleTexture:
    """Keep the approved screen() and meter() implementations unchanged.

    The static screen header must describe this render, not the original song's
    hard-coded tempo. Frequency labels still match the original 48-band analyzer.
    """
    def __init__(self, features):
        self.features = features
        self.duration = float(features["duration"])
        self.font = ImageFont.truetype(FONT, 17)
        self.small = ImageFont.truetype(FONT, 14)
        self.large = ImageFont.truetype(FONT, 23)
        self.screen_base = Image.new("RGB", (900, 390), (6, 13, 13))
        draw = ImageDraw.Draw(self.screen_base)
        for x in range(25, 900, 42):
            draw.line((x, 58, x, 315), fill=(13, 27, 23))
        for y in range(62, 316, 42):
            draw.line((25, y, 875, y), fill=(13, 27, 23))
        for y in range(0, 390, 4):
            draw.line((0, y, 900, y), fill=(5, 11, 11))
        draw.text((39, 17), "PLAYING", font=self.font, fill=(167, 209, 151))
        draw.text((867, 18), "48 BANDS  /  STEREO", font=self.small,
                  anchor="ra", fill=(128, 159, 127))
        draw.line((26, 46, 874, 46), fill=(58, 79, 56))
        draw.line((26, 325, 874, 325), fill=(58, 79, 56))
        for x, label in [(26, "40 Hz"), (220, "160"), (420, "630"),
                         (630, "2.5k"), (845, "11k")]:
            draw.text((x, 308), label, font=self.small, fill=(97, 125, 96))

    @staticmethod
    def clock(seconds):
        return f'{int(seconds)//60:02}:{int(seconds)%60:02}'

    def screen(self, i):
        f = self.features
        t = i/FPS
        screen = self.screen_base.copy()
        light = Image.new('RGB',screen.size)
        draw = ImageDraw.Draw(light)
        values = f['spectrum'][i]
        for n, value in enumerate(values):
            x = 28+n*17.6
            height = int(float(value)**1.1*160)
            mix = n/47
            color = (int(190-65*mix), int(193+23*mix), int(109+43*mix))
            for y in range(0,height,8):
                draw.rectangle((x,292-y-5,x+10,292-y), fill=color)
            if height>5:draw.line((x,290-height,x+10,290-height),fill=(223,238,189),width=2)
        # The primary curve uses actual filtered samples from the soundtrack.
        # A faint traveling ribbon supplies the soft visual motion of CRT traces.
        xs = np.linspace(28,872,300)
        envelope = np.sin(np.linspace(0,np.pi,300))**.65
        amplitude = 19+float(f['energy'][i])*18
        ys = 132+f['wave'][i]*amplitude*envelope
        draw.line(list(zip(xs,ys)),fill=(214,242,193),width=2)
        flow = 123+np.sin(np.linspace(0,4*np.pi,300)-t*1.7)*envelope*(10+16*float(f['bass'][i]))
        draw.line(list(zip(xs,flow)),fill=(84,149,109),width=1)
        draw.ellipse((25,23,30,28),fill=(151,238,136))
        halo = light.filter(ImageFilter.GaussianBlur(3.5))
        pixels=np.asarray(screen,dtype=np.float32)+np.asarray(light,dtype=np.float32)*.85+np.asarray(halo,dtype=np.float32)*.72
        screen=Image.fromarray(np.uint8(np.clip(pixels,0,255)))
        draw=ImageDraw.Draw(screen)
        draw.text((28,347),self.clock(t),font=self.large,fill=(170,218,149))
        draw.text((873,347),self.clock(self.duration),anchor='ra',font=self.large,fill=(128,169,121))
        draw.line((130,362,770,362),fill=(36,57,42),width=3)
        progress=min(1,t/self.duration)
        draw.line((130,362,130+640*progress,362),fill=(151,200,126),width=3)
        draw.ellipse((128+640*progress,359,134+640*progress,365),fill=(226,237,169))
        return screen

    def meter(self, i, channel):
        image=Image.new('RGB',(60,300),(5,11,10))
        draw=ImageDraw.Draw(image)
        value=float(self.features['levels'][i,channel])
        for segment in range(28):
            y=278-segment*9
            lit=segment/28<value
            color=((156,218,119) if segment<22 else (233,177,91)) if lit else (20,37,25)
            draw.rectangle((10,y,50,y+5),fill=color)
        return image

class DreamTexture:
    def __init__(self, features):
        self.f = features
        self.duration = float(features['duration'])
        self.small = ImageFont.truetype(FONT, 17)
        self.spectrum = smooth(features['spectrum'], .20, .075)
        self.energy = smooth(features['energy'], .10, .045)
        self.bass = smooth(features['bass'], .17, .06)
        self.levels = smooth(features['levels'], .12, .055)
        self.x = np.linspace(50,1150,360)
        self.unit = np.linspace(0,1,360)
        self.envelope = np.sin(self.unit*np.pi)**.85
        self.kernel = np.exp(-np.linspace(-2.5,2.5,17)**2)
        self.kernel /= self.kernel.sum()
        self.colors = [(220,208,238),(163,195,233),(237,176,198)]

    def texture(self, index):
        t = index / FPS
        level = float(self.energy[index])
        bass = float(self.bass[index])
        image = Image.new('RGB',(1200,300))
        draw = ImageDraw.Draw(image)
        # A continuous frequency contour retains measured band differences.
        contour = np.interp(self.unit,np.linspace(0,1,48),self.spectrum[index])
        contour = np.convolve(np.pad(contour,(8,8),mode='edge'),self.kernel,mode='valid')
        trace = np.interp(self.unit,np.linspace(0,1,300),self.f['wave'][index])
        trace = np.convolve(np.pad(trace,(4,4),mode='edge'),np.ones(9)/9,mode='valid')
        gate = float(np.clip(self.f['energy'][index]*2,0,1))
        # Quiet vertical filaments suggest a spectrum without a bank of hard LEDs.
        for k,value in enumerate(self.spectrum[index]):
            p=k/47
            x=52+1096*p
            taper=math.sin(math.pi*p)**.8
            length=(8+float(value)**1.4*66)*taper*gate
            center=181+math.sin(p*math.pi*2-t*.28)*5
            strength=.14+.19*float(value)
            color=tuple(int(v*strength) for v in self.colors[k%3])
            draw.line((x,center-length,x,center+length*.20),fill=color,width=2)
            if value>.4:
                draw.ellipse((x-1.1,center-length-1.1,x+1.1,center-length+1.1),fill=color)
        # Layered ribbons: slow phase drift, frequency-derived shape and volume.
        for layer in range(5):
            phase=t*(.33+layer*.018)+layer*.48
            wave=np.sin(self.unit*np.pi*(2.3+layer*.12)-phase)
            shape=(wave*(20+40*level)+(contour-.48)*(55+12*bass)+trace*(6+8*level))*self.envelope
            y=130+(layer-2)*13+shape*gate
            fade=[.30,.58,.92,.58,.30][layer]
            color=tuple(int(v*fade) for v in self.colors[layer%3])
            draw.line(list(zip(self.x,y)),fill=color,width=3 if layer==2 else 2)
        # The thin pearl trace comes directly from a filtered audio window.
        y=155+trace*(10+12*level)*self.envelope*gate
        draw.line(list(zip(self.x,y)),fill=(126,137,143),width=1)
        # A few very small highlights travel within the glass, never over the room.
        for k in range(7):
            p=(k*.143+t*(.018+.001*k))%1
            x=50+1100*p
            c=float(np.interp(p,self.unit,contour))
            y=113+math.sin(p*math.pi*2.8-t*.36+k*.3)*(15+17*level)+(c-.5)*26
            alpha=(math.sin(math.pi*p)**2)*(.16+.36*float(self.f['onset'][index]))*gate
            color=tuple(int(v*alpha) for v in (232,214,228))
            draw.ellipse((x-1.4,y-1.4,x+1.4,y+1.4),fill=color)
        fine=image.filter(ImageFilter.GaussianBlur(2.5))
        broad=image.filter(ImageFilter.GaussianBlur(9))
        arr=np.asarray(image,dtype=np.float32)*1.05+np.asarray(fine,dtype=np.float32)*.95+np.asarray(broad,dtype=np.float32)*1.6
        image=Image.fromarray(np.uint8(np.clip(arr,0,255)))
        draw=ImageDraw.Draw(image)
        elapsed=f'{int(t)//60}:{int(t)%60:02}'
        total=f'{int(self.duration)//60}:{int(self.duration)%60:02}'
        draw.text((56,251),elapsed,font=self.small,fill=(111,106,114))
        draw.text((1142,251),total,font=self.small,anchor='ra',fill=(100,98,109))
        progress=min(1,t/self.duration)
        draw.line((158,262,1036,262),fill=(24,24,32),width=1)
        draw.line((158,262,158+878*progress,262),fill=(92,80,92),width=1)
        x=158+878*progress
        draw.ellipse((x-1.5,260.5,x+1.5,263.5),fill=(167,150,165))
        return image

def tint(texture, color, accent):
    """Retain the original light's detail while matching the physical artwork."""
    a = np.array([int(color[i:i+2], 16) for i in (1, 3, 5)], np.float32)
    b = np.array([int(accent[i:i+2], 16) for i in (1, 3, 5)], np.float32)
    pixels = np.asarray(texture, dtype=np.float32)
    light = pixels.max(axis=2) / 255
    palette = a[None, :] + (b-a)[None, :] * np.linspace(0, 1, texture.width)[:, None]
    white = np.clip((light-.66)/.34, 0, 1)[..., None] * .18
    rgb = light[..., None] * (palette[None, :, :]*(1-white) + 255*white)
    return Image.fromarray(np.uint8(np.clip(rgb*1.07, 0, 255)))

class Film:
    def __init__(self, features, scene, artwork, strength=1, shade=0):
        if strength != 1:
            features = {**features, **{k: np.clip(features[k]*strength, -1 if k == "wave" else 0, 1) for k in ["spectrum", "levels", "energy", "bass", "onset", "wave"]}}
        self.features, self.scene = features, scene
        self.duration = float(features["duration"])
        self.art = Image.open(artwork).convert("RGB")
        if shade:
            self.art = ImageEnhance.Brightness(self.art).enhance(1-.0085*shade)
        self.console = ConsoleTexture(features)
        self.ribbon = None
        self.surfaces = []
        for idea in scene["surfaces"]:
            if idea["effect"] not in {"spectrum", "ribbon"}:
                raise ValueError("The photographic player supports spectrum and ribbon surfaces.")
            quad = [[x*self.art.width, y*self.art.height] for x, y in idea["corners"]]
            width = np.linalg.norm(np.subtract(quad[1], quad[0]))
            height = np.linalg.norm(np.subtract(quad[3], quad[0]))
            if not 1.7 <= width/height <= 8:
                raise ValueError("The glass would distort the approved display; revise its physical proportions first.")
            # A period radio LCD has room for the signal, not a full console's
            # clock/header. Keep the actual original waveform and 48-band field
            # at a readable scale instead of squeezing in microscopic labels.
            compact = idea["effect"] == "spectrum" and width/height > 4.7
            size = ((864, 226) if compact else (900, 390)) if idea["effect"] == "spectrum" else (1200, 300)
            surface = Surface(quad, size)
            self.surfaces.append((idea, surface, compact))
            if idea["effect"] == "ribbon" and self.ribbon is None:
                self.ribbon = DreamTexture(features)

    def frame(self, index):
        index = min(max(0, index), len(self.features["energy"])-1)
        image = self.art.copy()
        for idea, surface, compact in self.surfaces:
            source = (self.console.screen(index) if idea["effect"] == "spectrum"
                      else self.ribbon.texture(index))
            if compact:
                source = source.crop((20, 78, 884, 304))
            texture = tint(source, idea["color"], idea["accent"])
            if idea["effect"] == "spectrum":
                surface.composite(image, texture)
            else:
                # The original DreamPop renderer adds emitted light to the glass.
                patch = texture.transform(surface.patch_size, Image.Transform.PERSPECTIVE,
                                          surface.transform, Image.Resampling.BICUBIC)
                base = np.asarray(image.crop(surface.box), dtype=np.float32)
                emitted = np.asarray(patch, dtype=np.float32)
                result = 255-(255-base)*(1-emitted/255)
                image.paste(Image.fromarray(np.uint8(np.clip(result, 0, 255))), surface.box[:2])
        return image


def render_job(work, frame=None):
    work = Path(work).resolve()
    config = json.loads((work / "config.json").read_text())
    scene = config["scene"]
    artwork, audio = work / "artwork.png", work / "audio.flac"
    if hashlib.sha256(artwork.read_bytes()).hexdigest() != scene["artworkSha256"]:
        raise ValueError("Artwork does not match the saved scene.")
    if scene.get("renderer") != "reference-player-v1":
        raise ValueError("Unsupported photographic player version.")
    if config["draft"].get("showLyrics"):
        raise ValueError("Turn off the lyric overlay for this photographic player.")
    width, height = config["width"], config["height"]
    if (width, height) not in {(1920, 1080), (1080, 1920)}:
        raise ValueError("Unsupported export dimensions.")
    duration, start = float(config["duration"]), float(config.get("sourceStart", 0))
    if not all(math.isfinite(x) for x in [duration, start]) or duration <= 0 or start < 0:
        raise ValueError("Invalid render interval.")
    count = math.ceil(duration * FPS)
    began = time.monotonic()
    def progress(phase, frames=0):
        data = {"phase": phase, "frames": frames, "totalFrames": count,
                "elapsedSeconds": time.monotonic()-began}
        path = work / "progress.json"
        path.with_suffix(".tmp").write_text(json.dumps(data))
        path.with_suffix(".tmp").replace(path)
    progress("Analyzing the recording")
    # Every queue job has an isolated directory. Identify the cache so a resumed
    # job can never accidentally use measurements from a different source.
    identity = {"audioSha256": hashlib.sha256(audio.read_bytes()).hexdigest(),
                "analyzer": "original-centered-48bands-v1", "fps": FPS}
    key = work / "analysis-identity.json"
    cache = work / "features.npz"
    if cache.exists() and (not key.exists() or json.loads(key.read_text()) != identity):
        raise ValueError("The saved analysis belongs to another recording.")
    key.write_text(json.dumps(identity))
    features = dict(np.load(cache)) if cache.exists() else analyse(audio, work)
    if start + duration > float(features["duration"]) + .05:
        raise ValueError("Render interval exceeds the recording.")
    # Progress and the displayed total time follow the chosen soundtrack end.
    features["duration"] = config.get("songDuration", config["sourceDuration"])
    film = Film(features, scene, artwork, config["draft"].get("visualizerStrength", 1),
                config["draft"].get("shade", 0))
    if frame is not None:
        film.frame(round(frame*FPS)).resize((width, height), Image.Resampling.LANCZOS).save(work / "proof.png")
        return
    output = work / "video.partial.mp4"
    command = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",
               "-pix_fmt", "rgb24", "-s", f"{film.art.width}x{film.art.height}", "-r", str(FPS),
               "-i", "pipe:0", "-ss", str(start), "-i", str(audio),
               "-map", "0:v:0", "-map", "1:a:0", "-map_metadata", "-1",
               "-vf", f"scale={width}:{height}:flags=lanczos,setsar=1", "-c:v", "libx264",
               "-preset", "fast", "-crf", "18", "-threads", "4", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "320k", "-ar", "48000"]
    fade = config["draft"].get("audioFade")
    if fade:
        a, b = float(fade["start"])-start, float(fade["end"])-start
        # A source-time expression also handles previews that begin inside a fade.
        phase = f"min(1,max(0,(t-({a}))/{b-a}))"
        gain = f"1-({phase})" if fade["curve"] == "linear" else f"cos(({phase})*PI/2)"
        command += ["-af", f"volume='{gain}':eval=frame"]
    command += ["-t", str(duration), "-movflags", "+faststart", "-metadata",
                f"title={scene['title']}", str(output)]
    progress("Rendering photographic player")
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    try:
        for index in range(count):
            process.stdin.write(film.frame(round(start*FPS)+index).tobytes())
            if index % 30 == 0 or index == count-1:
                progress("Rendering photographic player", index+1)
        process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError("The MP4 encoder failed.")
    except BaseException:
        process.kill()
        process.wait()
        raise
    progress("Verifying MP4", count)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--frame", type=float, help="Render one source-time frame for verification.")
    args = parser.parse_args()
    render_job(args.work, args.frame)
