"""Make one H3 plate on the machine's ComfyUI: a word-free background clip with the song segment locked into it, for a
hybrid film.

  python3 tools/h3plate.py --name chorus1 --prompt plates/chorus1.txt --start 65.974 --seconds 5.875 \\
                           [--size 1024x576] [--seed 7] [--first f.png] [--pin 91:hold.png] [--pin 69.2s:hold2.png]
  python3 tools/h3plate.py --name intro --from-mp4 some/clip.mp4 --start 0      register a clip made elsewhere
  python3 tools/h3plate.py --name chorus1 --prompt … --dry-run                  check everything, send nothing

What it does: checks the prompt (≤ 7,000 characters, no quoted strings, says there is no text), cuts the song segment
from --start for the clip's length (the smallest 17k + 5 frames at 24 fps covering --seconds) out of song/song.m4a,
uploads it and any pictures to ComfyUI, runs the fused-turbo H3 graph with the segment locked into the audio half of the
latent (MiniMaxH3NativeAudioLock) so only the picture is generated while the model listens to the song, waits its turn
in ComfyUI's queue, and saves:
  plates/<name>.mp4               the clip as H3 made it (with the song segment as its sound)
  plates/<name>/f_00000.jpg …     every frame; frame f shows song time start + f / 24
  plates/<name>/plate.json        start, fps, frames, size, seed, prompt, … (src/engine/plates.js reads it)
  plates/index.json               the list of plates
Scenes then draw it with E.plates.draw(ctx, '<name>', f.t). Plates have NO words: every word is drawn in code.

  --first PNG        the clip's first frame; must be exactly --size (H3 stretches it otherwise)
  --pin F:PNG        pin a picture at frame F of the clip (or at song time Ts with "69.2s:"); repeatable; exactly --size
  --audio song|vocals|none   what is locked in (default song: the master mix)
  --queue-wait S     give up if the job hasn't started after S seconds in ComfyUI's queue (default 1800); it is then
                     taken back out of the queue
  --timeout S        give up if it hasn't finished S seconds after it started (default 900)
ComfyUI: SV_COMFY_URL, default http://127.0.0.1:8210 (sv-comfy on the same machine). Inside the studio container that
address is the container itself, so set SV_COMFY_URL (sv.env) to one the container can reach: the machine's own
network address, with sv-comfy listening on it (SV_COMFY_BIND=0.0.0.0). One job at a time; this never changes
ComfyUI's settings. The graph needs the MiniMaxH3NativeAudioLock node (the ComfyUI-H3-NativeAudioLock pack), which
sv-comfy's pinned node packs don't include, and MiniMax H3's audio VAE (minimax_h3_audio_vae_fp32.safetensors).
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLATES = ROOT / "plates"
COMFY = os.environ.get("SV_COMFY_URL", "http://127.0.0.1:8210").rstrip("/")
UNET = "minimax_h3_fused_refdelta_r1024_turbo8_mystic07_int8_convrot.safetensors"
TEXT_ENCODER = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
VIDEO_VAE = "minimax_h3_video_vae_int8_convrot.safetensors"
AUDIO_VAE = "minimax_h3_audio_vae_fp32.safetensors"
FPS = 24


def say(msg: str) -> None:
    print(msg, flush=True)


def fail(msg: str, code: int = 1) -> None:
    print("h3plate: " + msg, file=sys.stderr, flush=True)
    sys.exit(code)


def on_grid(frames: int) -> int:
    """H3's frame grid is 17k + 5; ComfyUI rounds up, so ask for a length already on it."""
    k = max(1, -(-(frames - 5) // 17))
    return 17 * k + 5


# ------------------------------------------------------------------ ComfyUI

class Comfy:
    def __init__(self, url: str):
        self.url, self.client = url, uuid.uuid4().hex

    def _json(self, path: str, body: dict | None = None, timeout: float = 60):
        req = urllib.request.Request(self.url + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"} if body is not None else {})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{path}: HTTP {e.code} {e.read().decode('utf-8', 'replace')[:1500]}") from None

    def queue(self) -> dict:
        return self._json("/queue", timeout=20)

    def upload(self, path: Path, name: str) -> str:
        boundary = uuid.uuid4().hex
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        body = b"".join([
            f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\nContent-Type: {mime}\r\n\r\n'.encode(),
            path.read_bytes(), b"\r\n",
            f'--{boundary}\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n--{boundary}--\r\n'.encode()])
        req = urllib.request.Request(self.url + "/upload/image", data=body,
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.load(r)["name"]

    def submit(self, g: dict) -> str:
        out = self._json("/prompt", {"prompt": g, "client_id": self.client})
        if out.get("node_errors"):
            raise RuntimeError("ComfyUI rejected the graph: " + json.dumps(out["node_errors"])[:1500])
        return out["prompt_id"]

    def fetch(self, info: dict, dest: Path) -> Path:
        q = urllib.parse.urlencode({"filename": info["filename"], "subfolder": info.get("subfolder", ""), "type": info.get("type", "output")})
        with urllib.request.urlopen(f"{self.url}/view?{q}", timeout=600) as r:
            dest.write_bytes(r.read())
        return dest


def graph(prompt: str, w: int, h: int, length: int, seed: int, prefix: str, *, audio: str | None,
          first: str | None, guides: list[tuple[int, str]], steps: int = 6) -> dict:
    """The fused-turbo H3 graph (as lab/kinetic-h3/kt.py and lab/living-album run it): text to video unless a first
    frame is given, pictures pinned at frames with MiniMaxH3AddGuide, the song locked into the audio half of the latent."""
    g: dict = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "2": {"class_type": "BlockSparseAttention", "inputs": {
            "model": ["1", 0], "selection": "top-k (SLA)", "selection.keep_percent": 10.0, "start_percent": 0.0,
            "end_percent": 1.0, "dense_blocks": "", "min_tokens": 12288, "extra_tokens": 256,
            "sink_conditioning": "exact_kv_and_rows", "verbose": False}},
        "3": {"class_type": "MiniMaxH3SigmaShift", "inputs": {"model": ["2", 0], "shift_video": 12.0, "shift_audio": 3.0}},
        "4": {"class_type": "CLIPLoader", "inputs": {"clip_name": TEXT_ENCODER, "type": "minimax", "device": "default"}},
        "5": {"class_type": "VAELoader", "inputs": {"vae_name": VIDEO_VAE}},
        "7": {"class_type": "MiniMaxH3ImageToVideo", "inputs": {
            "clip": ["4", 0], "vae": ["5", 0], "prompt": prompt, "width": w, "height": h, "length": length}},
        "8": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "10": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "13": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["5", 0]}},
        "14": {"class_type": "CreateVideo", "inputs": {"images": ["13", 0], "fps": float(FPS)}},
        "15": {"class_type": "SaveVideo", "inputs": {"video": ["14", 0], "filename_prefix": prefix, "format": "mp4", "codec": "h264"}},
    }
    if first:
        g["6"] = {"class_type": "LoadImage", "inputs": {"image": first}}
        g["7"]["inputs"]["first_frame"] = ["6", 0]
    model, latent, positive = ["3", 0], ["7", 1], ["7", 0]
    for i, (frame, name) in enumerate(guides):
        img, node = str(40 + i), str(50 + i)
        g[img] = {"class_type": "LoadImage", "inputs": {"image": name}}
        g[node] = {"class_type": "MiniMaxH3AddGuide", "inputs": {
            "positive": positive, "latent": latent, "frame_idx": frame, "vae": ["5", 0], "image": [img, 0]}}
        positive = [node, 0]
    if audio:
        g["30"] = {"class_type": "VAELoader", "inputs": {"vae_name": AUDIO_VAE}}
        g["31"] = {"class_type": "LoadAudio", "inputs": {"audio": audio}}
        g["32"] = {"class_type": "MiniMaxH3NativeAudioLock", "inputs": {
            "model": model, "av_latent": latent, "audio_vae": ["30", 0], "audio": ["31", 0]}}
        model, latent = ["32", 0], ["32", 1]
        g["14"]["inputs"]["audio"] = ["32", 2]
    g["9"] = {"class_type": "BasicGuider", "inputs": {"model": model, "conditioning": positive}}
    g["11"] = {"class_type": "BasicScheduler", "inputs": {"model": model, "scheduler": "simple", "steps": steps, "denoise": 1.0}}
    g["12"] = {"class_type": "SamplerCustomAdvanced", "inputs": {
        "noise": ["8", 0], "guider": ["9", 0], "sampler": ["10", 0], "sigmas": ["11", 0], "latent_image": latent}}
    return g


# ------------------------------------------------------------------ checks

def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as f:
        head = f.read(24)
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout.strip().split(",")
    return int(out[0]), int(out[1])


def check_prompt(text: str) -> None:
    n = len(text)
    if n > 7000:
        fail(f"the prompt is {n} characters; H3 prompts stay under 7,000 (h3-kinetic-type skill)")
    quoted = re.findall(r"[\"“]([^\"”]{1,60})[\"”]", text)
    if quoted:
        say(f"  warning: the prompt quotes {quoted[:5]}: quoted strings read as on-screen text, and a plate has none")
    if not re.search(r"no (readable )?(text|letters|words|lettering)|on-screen text:\s*none|without (any )?(text|letters|words)", text, re.I):
        say("  warning: the prompt doesn't say there is no text (e.g. \"ON-SCREEN TEXT: none. No letters, numbers, signs, "
            "logos, captions or subtitles anywhere, at any time\"); H3 adds lettering when it isn't told not to")
    if "integrated_multimodal_description" not in text:
        say("  warning: the prompt doesn't use H3's fields (integrated_multimodal_description, overall_soundscape, non_diegetic_music)")


def extract(mp4: Path, dest: Path) -> int:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(mp4), "-fps_mode", "passthrough", "-start_number", "0",
                        "-q:v", "2", str(dest / "f_%05d.jpg")], capture_output=True, text=True)
    if r.returncode:
        fail(f"ffmpeg couldn't read {mp4.name}: {r.stderr[:400]}")
    return len(list(dest.glob("f_*.jpg")))


def register(name: str, meta: dict) -> None:
    (PLATES / name / "plate.json").write_text(json.dumps(meta, indent=1))
    idx = PLATES / "index.json"
    names = []
    if idx.exists():
        try:
            names = json.loads(idx.read_text()).get("plates", [])
        except ValueError:
            names = []
    if name not in names:
        names.append(name)
    tmp = idx.with_suffix(".tmp")
    tmp.write_text(json.dumps({"plates": names}, indent=1))
    tmp.replace(idx)


# ------------------------------------------------------------------ main

def main() -> None:
    ap = argparse.ArgumentParser(description="One H3 plate (see the top of this file).")
    ap.add_argument("--name", required=True)
    ap.add_argument("--prompt", type=Path)
    ap.add_argument("--start", type=float, required=True, help="song time of the clip's first frame (s)")
    ap.add_argument("--seconds", type=float, help="how much of the song the plate must cover (s)")
    ap.add_argument("--size", default=None, help="WxH (default by the film's aspect: 1024x576, 576x1024 or 1024x1024)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--first", type=Path)
    ap.add_argument("--pin", action="append", default=[], help="F:PNG or Ts:PNG (song seconds)")
    ap.add_argument("--audio", choices=["song", "vocals", "none"], default="song")
    ap.add_argument("--steps", type=int, default=6)
    ap.add_argument("--queue-wait", type=float, default=1800)
    ap.add_argument("--timeout", type=float, default=900)
    ap.add_argument("--from-mp4", type=Path, help="register an existing clip as the plate instead of making one")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,40}", a.name):
        fail("--name: lowercase letters, digits, - and _ only (it becomes a folder name)")
    PLATES.mkdir(exist_ok=True)
    meta_film = {}
    if (ROOT / "song/meta.json").exists():
        meta_film = json.loads((ROOT / "song/meta.json").read_text())

    if a.from_mp4:
        if not a.from_mp4.exists():
            fail(f"{a.from_mp4} doesn't exist")
        dest = PLATES / f"{a.name}.mp4"
        if a.from_mp4.resolve() != dest.resolve():
            shutil.copyfile(a.from_mp4, dest)
        n = extract(dest, PLATES / a.name)
        w, h = png_size(PLATES / a.name / "f_00000.jpg")
        register(a.name, {"name": a.name, "start": a.start, "fps": FPS, "frames": n, "width": w, "height": h,
                          "seconds": round(n / FPS, 4), "source": str(a.from_mp4), "made": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        say(f"plate {a.name}: {n} frames ({n / FPS:.3f} s) from {a.from_mp4}, song {a.start:.3f}–{a.start + n / FPS:.3f} s")
        return

    if not a.prompt or a.seconds is None:
        fail("--prompt and --seconds are needed to make a plate (or --from-mp4 to register one)")
    if not a.prompt.exists():
        fail(f"{a.prompt} doesn't exist")
    if a.size:
        m = re.fullmatch(r"(\d+)x(\d+)", a.size)
        if not m:
            fail("--size is WxH, e.g. 1024x576")
        w, h = int(m[1]), int(m[2])
    else:
        fw, fh = meta_film.get("width", 1920), meta_film.get("height", 1080)
        w, h = (1024, 1024) if fw == fh else (1024, 576) if fw > fh else (576, 1024)
    if w % 32 or h % 32:
        say(f"  warning: {w}x{h} is not a multiple of 32 on both sides; H3 sizes are")
    length = on_grid(round(a.seconds * FPS))
    if not 124 <= length <= 362:
        say(f"  warning: {length} frames is outside the ~124–362 H3 was trained on")
    prompt = a.prompt.read_text().strip()
    say(f"plate {a.name}: {w}x{h}, {length} frames ({length / FPS:.3f} s) from song {a.start:.3f} s, seed {a.seed}, "
        f"prompt {len(prompt)} characters")
    check_prompt(prompt)
    pics = []
    if a.first:
        pics.append(("first", a.first))
    pins = []
    for p in a.pin:
        if ":" not in p:
            fail(f"--pin {p}: expected F:PNG")
        at, pic = p.split(":", 1)
        frame = round((float(at[:-1]) - a.start) * FPS) if at.endswith("s") else int(at)
        if frame < 0:
            frame += length
        if not 0 <= frame < length:
            fail(f"--pin {p}: frame {frame} is outside the clip (0–{length - 1})")
        pins.append((frame, Path(pic)))
        pics.append((f"pin {frame}", Path(pic)))
    for label, pic in pics:
        if not pic.exists():
            fail(f"{label}: {pic} doesn't exist")
        pw, ph = png_size(pic)
        if (pw, ph) != (w, h):
            fail(f"{label}: {pic} is {pw}x{ph}; it must be exactly {w}x{h} (H3 stretches a first frame to the canvas)")
    song_file = {"song": ROOT / "song/song.m4a", "vocals": ROOT / "song/vocals.m4a"}.get(a.audio)
    if song_file and not song_file.exists():
        fail(f"{song_file.relative_to(ROOT)} is missing")

    comfy = Comfy(COMFY)
    say(f"checking ComfyUI at {COMFY} …")
    try:
        q = comfy.queue()
    except (OSError, RuntimeError) as e:
        fail(f"ComfyUI isn't reachable at {COMFY} ({e}). Is it running, and reachable from here? (SV_COMFY_URL sets the address.)", 2)
    say(f"  reachable: {len(q.get('queue_running', []))} running, {len(q.get('queue_pending', []))} waiting")
    if a.dry_run:
        g = graph(prompt, w, h, length, a.seed, f"video/sv-plates/{a.name}", audio="segment.wav" if song_file else None,
                  first="first.png" if a.first else None, guides=[(f, "pin.png") for f, _ in pins], steps=a.steps)
        say(f"dry run: graph of {len(g)} nodes ready; nothing sent")
        return

    tmp = PLATES / f".{a.name}.tmp"
    tmp.mkdir(exist_ok=True)
    audio_name = None
    if song_file:
        seg = tmp / "segment.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-ss", f"{a.start:.3f}", "-t", f"{length / FPS:.4f}", "-i", str(song_file),
                        "-ac", "2", "-ar", "48000", str(seg)], check=True)
        say(f"uploading the song segment {a.start:.3f}–{a.start + length / FPS:.3f} s …")
        audio_name = comfy.upload(seg, f"sv-plate-{a.name}-{uuid.uuid4().hex[:6]}.wav")
    first = comfy.upload(a.first, f"sv-plate-{a.name}-first.png") if a.first else None
    guides = [(f, comfy.upload(p, f"sv-plate-{a.name}-pin{f}.png")) for f, p in pins]
    g = graph(prompt, w, h, length, a.seed, f"video/sv-plates/{a.name}", audio=audio_name, first=first, guides=guides, steps=a.steps)
    pid = comfy.submit(g)
    say(f"submitted {pid[:8]} (audio {'locked: ' + a.audio if audio_name else 'none'}, first frame {'yes' if first else 'no'}, "
        f"pins {[f for f, _ in guides] or 'none'})")

    t_sub = time.monotonic()
    t_run = None
    said = -1e9
    entry = None
    while True:
        try:
            h_ = comfy._json(f"/history/{pid}", timeout=30)
        except (OSError, RuntimeError) as e:
            say(f"  ComfyUI didn't answer ({e}); trying again")
            time.sleep(5)
            continue
        if pid in h_:
            e = h_[pid]
            st = e.get("status", {})
            if st.get("status_str") == "error":
                msgs = [m for m in st.get("messages", []) if m[0] == "execution_error"]
                fail("the run failed in ComfyUI: " + json.dumps(msgs[-1][1] if msgs else st)[:1800])
            if e.get("outputs") and st.get("completed", True):
                entry = e
                break
        q = comfy.queue()
        running = [x[1] for x in q.get("queue_running", [])]
        pending = sorted(q.get("queue_pending", []), key=lambda x: x[0])
        now = time.monotonic()
        if pid in running:
            if t_run is None:
                t_run = now
                say(f"  running (waited {now - t_sub:.0f} s in the queue)")
            elif now - said >= 15:
                said = now
                say(f"  running {now - t_run:.0f} s")
            if now - t_run > a.timeout:
                fail(f"still running after {a.timeout:.0f} s; left to finish in ComfyUI (prompt {pid}), nothing saved here", 3)
        else:
            ahead = next((i for i, x in enumerate(pending) if x[1] == pid), None)
            if ahead is not None:
                if now - said >= 15:
                    said = now
                    say(f"  waiting in ComfyUI's queue: {len(running)} running, {ahead} ahead of us ({now - t_sub:.0f} s)")
                if now - t_sub > a.queue_wait:
                    try:
                        comfy._json("/queue", {"delete": [pid]})
                        note = "taken back out of the queue"
                    except (OSError, RuntimeError):
                        note = "could not be taken out of the queue"
                    fail(f"ComfyUI stayed busy for {a.queue_wait:.0f} s; the job was {note}. Try again later.", 3)
        time.sleep(3)

    vids = [o for node in entry["outputs"].values() for key in ("videos", "images", "gifs")
            for o in node.get(key, []) if str(o.get("filename", "")).endswith(".mp4")]
    if not vids:
        fail("ComfyUI finished without a video: " + json.dumps(entry["outputs"])[:600])
    dest = comfy.fetch(vids[0], PLATES / f"{a.name}.mp4")
    took = time.monotonic() - (t_run or t_sub)
    n = extract(dest, PLATES / a.name)
    fw, fh = png_size(PLATES / a.name / "f_00000.jpg")
    register(a.name, {
        "name": a.name, "start": a.start, "fps": FPS, "frames": n, "width": fw, "height": fh, "seconds": round(n / FPS, 4),
        "requestedSeconds": a.seconds, "length": length, "seed": a.seed, "steps": a.steps,
        "prompt": str(a.prompt), "promptChars": len(prompt), "audio": a.audio,
        "first": str(a.first) if a.first else None, "pins": [[f, str(p)] for f, p in pins],
        "comfy": {"url": COMFY, "promptId": pid, "seconds": round(took, 1)},
        "made": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    shutil.rmtree(tmp, ignore_errors=True)
    if n != length:
        say(f"  note: the clip has {n} frames, {length} were asked for")
    say(f"plate {a.name} ready in {took:.0f} s on the GPU: plates/{a.name}.mp4, {n} frames in plates/{a.name}/ "
        f"(song {a.start:.3f}–{a.start + n / FPS:.3f} s). Look at its frames for stray letters before using it.")


if __name__ == "__main__":
    main()
