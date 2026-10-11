"""Turn the app's export in song/ into what the engine reads in analysis/ (src/engine/audio.js).

  python3 tools/import_song.py [--lead 0.04] [--snap 0.05]

Reads
  song/song.m4a       the master mix (required)
  song/vocals.m4a     the vocal stem (optional)
  song/stems/         drums.m4a, bass.m4a, other.m4a: the other stems (optional)
  song/songmap.json   the app's song map: beats, bars, drum hits, energy, vocal presence (optional, expected)
  song/timing.json    the word timing, already corrected by hand in the app: the only source of on-screen words
  song/meta.json      title, artist, kind, engine, size, fps, look … (optional)
Writes
  analysis/analysis.json  grid (tempo, meter, beats, bars), sections, onsets per key, lyric lines with every word's
                          sung time and cue, and the layout of the two binaries below
  analysis/env.bin        Float32 envelopes at 120 Hz: the env.keys rows, then env.bands log-spaced bands of the mix
  analysis/wave.bin       Int8 waveforms at 6 kHz for scopes: the wave.keys rows
  analysis/listening.*    the listening report (below)

How each key is made (song/stems/{drums,bass,other}.m4a, the app's HTDemucs stems, are used when they're there):
  onsets  kick, snare, hat   the song map's drum hits (from the app's drum stem); band flux of the mix without one
          hit                kick and snare merged (hats left out, as in the films: the hits the eye should feel)
          vocals             spectral flux of the vocal stem; the sung word starts without one
          bass, other        spectral flux of the bass and other stems; without them, band-limited flux of the mix with
                             the vocal subtracted (magnitude)
          mix                spectral flux of the mix
  env     kick, snare, hat, drums   the drum hits as decaying impulses; bass, other: the stems' RMS (band RMS of the mix
          without the vocal when there are no stems); mix, low, mid, high: band RMS of the mix
          vocals             the vocal stem's RMS (the song map's vocal presence without one); 48 bands, 40 Hz–16 kHz
  wave    mix, vocals; bass and other = the stems (without them, the accompaniment (mix − vocal) below 200 Hz /
          200 Hz–3 kHz); drums = the drum stem (without it, the accompaniment gated by the drum envelope)
Listening report: analysis/listening.json and analysis/listening.md, what the song sounds like in numbers: key and mode
(chroma of the bass and other stems, or the mix, against the Krumhansl–Kessler profiles), tempo feel, the energy arc by
section, brightness, how busy each part is, which instruments carry it, and where the voice is.
Word cues (the frame a word lands on): a word within --snap of a drum hit (hit ≥ 0.5, kick or snare ≥ 0.6) is locked to
that hit, 12 ms early; any other word is cued --lead ahead of its sung start. Only numpy and ffmpeg are used.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SONG, OUT = ROOT / "song", ROOT / "analysis"
SR = 44100
ENV_HZ = 120
WAVE_HZ = 6000
NFFT, HOP = 4096, 256
NB = 48
EARLY = 0.012
SNAP_KEYS = [("hit", 0.5), ("kick", 0.6), ("snare", 0.6)]


def say(*a):
    print(*a, flush=True)


def warn(msg):
    print("warning: " + msg, flush=True)


def load_json(p: Path):
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except ValueError as e:
        sys.exit(f"{p.relative_to(ROOT)} is not valid JSON: {e}")


def decode(path: Path, sr: int) -> np.ndarray:
    """Mono float32 at sr, through ffmpeg."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                       capture_output=True)
    if r.returncode != 0:
        sys.exit(f"ffmpeg could not read {path.relative_to(ROOT)}: {r.stderr.decode(errors='replace')[:400]}")
    return np.frombuffer(r.stdout, np.float32).copy()


# ------------------------------------------------------------------ alignment of the vocal stem with the mix

def vocal_lag(mix: np.ndarray, voc: np.ndarray, max_lag: int = 4096) -> tuple[int, float]:
    """Samples to shift the vocal by so it lines up with the mix, and how well it then correlates (0..1)."""
    n = len(voc)
    blk = SR
    e = np.array([float(np.sum(voc[i:i + blk] ** 2)) for i in range(0, max(1, n - blk), blk)])
    if not len(e) or e.max() <= 0:
        return 0, 0.0
    win = min(20, len(e))
    roll = np.convolve(e, np.ones(win), "valid")
    s = int(np.argmax(roll)) * blk
    a = mix[s:s + win * blk].astype(np.float64)
    b = voc[s:s + win * blk].astype(np.float64)
    m = min(len(a), len(b))
    a, b = a[:m], b[:m]
    size = 1 << int(np.ceil(np.log2(2 * m)))
    xc = np.fft.irfft(np.fft.rfft(a, size) * np.conj(np.fft.rfft(b, size)), size)
    lags = np.concatenate([np.arange(0, max_lag + 1), np.arange(-max_lag, 0)])
    vals = np.concatenate([xc[:max_lag + 1], xc[-max_lag:]])
    k = int(np.argmax(vals))
    r = float(vals[k] / (np.sqrt(np.sum(a * a) * np.sum(b * b)) + 1e-12))
    return int(lags[k]), r


def shift(x: np.ndarray, lag: int) -> np.ndarray:
    """x moved later by lag samples (earlier if negative), same length."""
    if lag == 0:
        return x
    out = np.zeros_like(x)
    if lag > 0:
        out[lag:] = x[:-lag]
    else:
        out[:lag] = x[-lag:]
    return out


# ------------------------------------------------------------------ short-time spectra, in chunks

FREQS = np.fft.rfftfreq(NFFT, 1 / SR)


def band_mask(lo: float, hi: float) -> np.ndarray:
    m = (FREQS >= lo) & (FREQS < hi)
    if not m.any():
        m = np.zeros_like(m)
        m[np.argmin(np.abs(FREQS - (lo + hi) / 2))] = True
    return m


def frames_of(y: np.ndarray, start: int, count: int) -> np.ndarray:
    """Hann-windowed frames start … start+count−1, frame k centred on sample k·HOP."""
    pad = NFFT // 2
    idx = (np.arange(start, start + count) * HOP)[:, None] + np.arange(NFFT)[None, :] - pad
    valid = (idx >= 0) & (idx < len(y))
    fr = np.where(valid, y[np.clip(idx, 0, len(y) - 1)], 0.0).astype(np.float32)
    return fr * np.hanning(NFFT).astype(np.float32)


# chroma: every FFT bin from 55 Hz to 4.2 kHz to its pitch class, each semitone weighted equally whatever its bin count
_CH = np.flatnonzero((FREQS >= 55) & (FREQS <= 4200))
_MIDI = np.round(69 + 12 * np.log2(FREQS[_CH] / 440)).astype(int)
CHROMA_MAP = np.zeros((len(_CH), 12), np.float32)
for _m in np.unique(_MIDI):
    _sel = _MIDI == _m
    CHROMA_MAP[_sel, _m % 12] = 1.0 / _sel.sum()
_CEN = (FREQS >= 30) & (FREQS <= 16000)


def analyse(mix: np.ndarray, voc: np.ndarray | None, subtract: bool, rms_spec: dict, flux_spec: dict,
            stems: dict | None = None, chunk: int = 512):
    """Band RMS rows and positive spectral-flux rows for the whole song, one column per frame, plus the chroma (12 rows,
    C = 0) of the harmonic part (bass + other stems, else the accompaniment) and the mix's spectral centroid (Hz).
    rms_spec / flux_spec: name → (signal 'mix' | 'acc' | 'voc' | a stem name, lo, hi)."""
    stems = stems or {}
    n_frames = 1 + len(mix) // HOP
    rms = {k: np.zeros(n_frames, np.float32) for k in rms_spec}
    flux = {k: np.zeros(n_frames, np.float32) for k in flux_spec}
    chroma = np.zeros((12, n_frames), np.float32)
    centroid = np.zeros(n_frames, np.float32)
    masks = {k: band_mask(lo, hi) for k, (_, lo, hi) in {**rms_spec, **flux_spec}.items()}
    prev = {}
    for start in range(0, n_frames, chunk):
        count = min(chunk, n_frames - start)
        S = {"mix": np.abs(np.fft.rfft(frames_of(mix, start, count), axis=1)).astype(np.float32)}
        if voc is not None:
            S["voc"] = np.abs(np.fft.rfft(frames_of(voc, start, count), axis=1)).astype(np.float32)
            S["acc"] = np.maximum(S["mix"] - S["voc"], 0) if subtract else S["mix"]
        else:
            S["acc"] = S["mix"]
        for name, y in stems.items():
            S[name] = np.abs(np.fft.rfft(frames_of(y, start, count), axis=1)).astype(np.float32)
        H = S["bass"] + S["other"] if ("bass" in S and "other" in S) else S["acc"]
        chroma[:, start:start + count] = (np.log1p(50 * H[:, _CH]) @ CHROMA_MAP).T
        M = S["mix"][:, _CEN]
        centroid[start:start + count] = (M @ FREQS[_CEN]) / (M.sum(axis=1) + 1e-9)
        for k, (sig, _, _) in rms_spec.items():
            if sig in S:
                rms[k][start:start + count] = np.sqrt(np.mean(S[sig][:, masks[k]] ** 2, axis=1))
        logs = {}
        for k, (sig, _, _) in flux_spec.items():
            if sig not in S:
                continue
            if sig not in logs:
                L = np.log1p(50 * S[sig])
                before = prev.get(sig, L[:1])
                logs[sig] = np.maximum(np.diff(np.concatenate([before, L]), axis=0), 0)
                prev[sig] = L[-1:]
            flux[k][start:start + count] = logs[sig][:, masks[k]].mean(axis=1)
    return rms, flux, np.arange(n_frames) * HOP / SR, chroma, centroid


def follow(X: np.ndarray, release: np.ndarray, attack: float = 0.004) -> np.ndarray:
    """Peak follower over each row (rows = signals, columns = analysis frames)."""
    dt = HOP / SR
    a = np.exp(-dt / attack)
    r = np.exp(-dt / np.asarray(release, np.float64))      # one release per row
    out = np.empty_like(X)
    v = np.zeros(X.shape[0])
    for i in range(X.shape[1]):
        s = X[:, i]
        v = np.where(s > v, a * v + (1 - a) * s, r * v + (1 - r) * s)
        out[:, i] = v
    return out


def norm(x: np.ndarray, pct: float = 99.5) -> np.ndarray:
    return (x / (np.percentile(x, pct) + 1e-9)).astype(np.float32)


def peaks(f: np.ndarray, ft: np.ndarray, th: float, gap: float) -> list:
    """Onsets from a flux curve: peaks over th (after scaling to its 99.5th percentile) with a prominence of 0.6·th,
    at least `gap` seconds apart (the stronger one wins). [[time, strength ≤ 2], …]"""
    f = f / (np.percentile(f, 99.5) + 1e-9)
    if len(f) < 3:
        return []
    dist = max(1, int(round(gap * SR / HOP)))
    c = np.flatnonzero((f[1:-1] > f[:-2]) & (f[1:-1] >= f[2:]) & (f[1:-1] >= th)) + 1
    w = 2 * dist
    keep = []
    for i in c:
        lo = f[max(0, i - w):i].min() if i > 0 else f[i]
        hi = f[i + 1:i + w + 1].min() if i + 1 < len(f) else f[i]
        if f[i] - max(lo, hi) >= th * 0.6:
            keep.append(i)
    taken = np.zeros(len(f), bool)
    chosen = []
    for i in sorted(keep, key=lambda i: -f[i]):
        if not taken[max(0, i - dist + 1):i + dist].any():
            taken[i] = True
            chosen.append(i)
    return [[round(float(ft[i]), 4), round(float(min(f[i], 2.0)), 3)] for i in sorted(chosen)]


def merge(lists: list, within: float = 0.025) -> list:
    """Union of onset lists; hits closer than `within` become one (the strongest one's time, the highest strength)."""
    allv = sorted((o for l in lists for o in l), key=lambda o: o[0])
    out = []
    for t, s in allv:
        if out and t - out[-1][2] <= within:
            if s > out[-1][1]:
                out[-1][0] = t
            out[-1][1] = max(out[-1][1], s)
        else:
            out.append([t, s, t])
    return [[round(t, 4), round(s, 3)] for t, s, _ in out]


def impulses(hits: list, ft: np.ndarray) -> np.ndarray:
    x = np.zeros(len(ft), np.float32)
    for t, s in hits:
        i = int(round(t * SR / HOP))
        if 0 <= i < len(x):
            x[i] = max(x[i], s)
    return x


def fft_band(x: np.ndarray, sr: int, lo: float, hi: float, soft: float = 0.25) -> np.ndarray:
    """Band-pass by FFT with raised-cosine edges (soft = fraction of the edge frequency)."""
    X = np.fft.rfft(x.astype(np.float64))
    f = np.fft.rfftfreq(len(x), 1 / sr)
    g = np.ones_like(f)
    if lo > 0:
        g *= np.clip((f - lo * (1 - soft)) / (2 * lo * soft), 0, 1)
    if hi < sr / 2:
        g *= np.clip((hi * (1 + soft) - f) / (2 * hi * soft), 0, 1)
    g = 0.5 - 0.5 * np.cos(np.pi * g)
    return np.fft.irfft(X * g, len(x)).astype(np.float32)


def to_int8(w: np.ndarray, n: int) -> np.ndarray:
    w = w / (np.percentile(np.abs(w), 99.9) + 1e-9)
    w = np.pad(w, (0, max(0, n - len(w))))[:n]
    return np.clip(np.round(w * 127), -127, 127).astype(np.int8)


# ------------------------------------------------------------------ grid, sections, words

def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "section"


def bar_pos(bars: list, t: float) -> float:
    b, last = bars, len(bars) - 1
    if t <= b[0]:
        return 1 + (t - b[0]) / (b[1] - b[0])
    if t >= b[last]:
        return 1 + last + (t - b[last]) / (b[last] - b[last - 1])
    i = int(np.searchsorted(b, t, side="right")) - 1
    return 1 + i + (t - b[i]) / (b[i + 1] - b[i])


# ------------------------------------------------------------------ the listening report

PITCH = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])  # Krumhansl–Kessler
MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
BARS = "▁▂▃▄▅▆▇█"


def keys_of(c: np.ndarray) -> list:
    """The 24 keys ranked by how well a chroma vector correlates with their profile: [(name, r), …]."""
    out = []
    for tonic in range(12):
        for mode, prof in (("major", MAJOR), ("minor", MINOR)):
            out.append((f"{PITCH[tonic]} {mode}", float(np.corrcoef(c, np.roll(prof, tonic))[0, 1])))
    return sorted(out, key=lambda k: -k[1])


def level(x: float, cuts=(0.2, 0.4, 0.6, 0.8), words=("very low", "low", "medium", "high", "very high")) -> str:
    return words[int(np.searchsorted(cuts, x))]


def listening_report(meta, dur, music_end, tempo, meter, bars, sections, lines, ons, env, t_env, chroma, centroid, ft,
                     has_vocal, stems) -> dict:
    """What the song sounds like, measured: everything Claude can't hear, in numbers and plain words."""
    loud = np.interp(ft, t_env, env["mix"]) > 0.05
    c_all = chroma[:, loud].mean(axis=1) if loud.any() else chroma.mean(axis=1)
    ranked = keys_of(c_all)
    best, second = ranked[0], next(k for k in ranked[1:] if k[0] != ranked[0][0])

    def span_mean(x, tx, a, b):
        sel = (tx >= a) & (tx < b)
        return float(x[sel].mean()) if sel.any() else 0.0

    def rate(key, a, b):
        return sum(1 for t, s in ons.get(key, []) if a <= t < b and s >= 0.3) / max(b - a, 1e-6)

    secs = sections or [{"id": "song", "name": "whole song", "start": 0.0, "end": dur, "bar0": 1, "bar1": len(bars)}]
    song_bright = float(np.median(centroid[loud])) if loud.any() else float(np.median(centroid))
    rows = []
    for s in secs:
        a, b = s["start"], s["end"]
        sel = (ft >= a) & (ft < b)
        k = keys_of(chroma[:, sel & loud].mean(axis=1)) if (sel & loud).sum() > 20 else [("?", 0.0)]
        layers = {n: round(span_mean(env[n], t_env, a, b), 3) for n in ("drums", "bass", "other", "vocals")}
        voice = float((env["vocals"][(t_env >= a) & (t_env < b)] > 0.25).mean()) if ((t_env >= a) & (t_env < b)).any() else 0.0
        bright = float(np.median(centroid[sel & loud])) if (sel & loud).any() else 0.0
        rows.append({
            "id": s["id"], "name": s["name"], "start": round(a, 2), "end": round(b, 2), "bars": [s.get("bar0"), s.get("bar1")],
            "energy": round(span_mean(env["mix"], t_env, a, b), 3), "low": round(span_mean(env["low"], t_env, a, b), 3),
            "high": round(span_mean(env["high"], t_env, a, b), 3),
            "brightnessHz": round(bright), "brightness": "brighter" if bright > song_bright * 1.12 else "darker" if bright < song_bright * 0.88 else "as the song",
            "hitsPerSec": round(rate("hit", a, b), 2), "hatsPerSec": round(rate("hat", a, b), 2), "otherPerSec": round(rate("other", a, b), 2),
            "layers": layers, "carriedBy": [n for n, v in sorted(layers.items(), key=lambda kv: -kv[1]) if v >= 0.18][:3],
            "voice": round(voice, 2), "lines": sum(1 for ln in lines if a <= (ln["start"] + ln["end"]) / 2 < b),
            "key": k[0][0], "keyR": round(k[0][1], 2),
        })
    e = np.array([r["energy"] for r in rows])
    lifts = sorted(((rows[i]["start"], float(e[i] - e[i - 1]), rows[i - 1]["name"], rows[i]["name"]) for i in range(1, len(rows))),
                   key=lambda x: -abs(x[1]))
    # the loudest eight bars
    win = 8 * 60 / tempo * meter if tempo else 16.0
    step = int(ENV_HZ)
    best_t, best_v = 0.0, -1.0
    for i in range(0, max(1, len(t_env) - int(win * ENV_HZ)), step):
        v = float(env["mix"][i:i + int(win * ENV_HZ)].mean())
        if v > best_v:
            best_t, best_v = float(t_env[i]), v
    # where the voice is: vocal envelope over 0.25 for at least 0.6 s, gaps under 0.6 s joined
    moments = []
    if has_vocal or env["vocals"].any():
        on = env["vocals"] > 0.25
        i = 0
        while i < len(on):
            if on[i]:
                j = i
                while j < len(on) and on[j]:
                    j += 1
                a, b = float(t_env[i]), float(t_env[min(j, len(t_env) - 1)])
                if moments and a - moments[-1][1] < 0.6:
                    moments[-1][1] = b
                else:
                    moments.append([a, b])
                i = j
            else:
                i += 1
        moments = [[round(a, 2), round(b, 2)] for a, b in moments if b - a >= 0.6]
    timed = [(ln["start"], ln["end"]) for ln in lines]
    voice = [{"start": a, "end": b, "words": any(s < b and e2 > a for s, e2 in timed)} for a, b in moments]
    mix_env = env["mix"][t_env < music_end]
    feel = ("slow" if tempo < 85 else "relaxed" if tempo < 100 else "mid-tempo" if tempo < 115 else "dance tempo" if tempo < 135
            else "fast") if tempo else "unknown"
    return {
        "title": meta.get("title") or "", "artist": meta.get("artist") or "",
        "tagKey": (meta.get("tags") or {}).get("key"),
        "duration": round(dur, 2), "musicEnd": round(music_end, 2), "tempo": tempo, "meter": meter, "tempoFeel": feel,
        "halfOrDouble": f"could also be felt at {tempo / 2:.1f} or {tempo * 2:.1f} BPM; judge by the drum pattern" if tempo else None,
        "key": {"name": best[0], "confidence": round(best[1], 2), "next": second[0], "nextConfidence": round(second[1], 2),
                "note": "measured from " + ("the bass and other stems" if "bass" in stems else "the mix")
                        + "; relative major/minor and modal songs are easy to confuse, so treat it as a lean, not a fact"},
        "energy": {"peak": {"start": round(best_t, 2), "end": round(best_t + win, 2), "level": round(best_v, 3)},
                   "dynamics": level(float(np.percentile(mix_env, 95) - np.percentile(mix_env, 10)) if len(mix_env) else 0.0,
                                     (0.25, 0.4, 0.55, 0.7), ("very compressed", "compressed", "moderate", "wide", "very wide")),
                   "biggestChanges": [{"at": round(t, 2), "change": round(d, 3), "from": f, "to": to} for t, d, f, to in lifts[:5]]},
        "brightnessHz": round(song_bright),
        "sections": rows,
        "voice": {"stem": has_vocal, "moments": voice, "firstAt": voice[0]["start"] if voice else None,
                  "lastAt": voice[-1]["end"] if voice else None,
                  "share": round(sum(v["end"] - v["start"] for v in voice) / max(music_end, 1e-6), 3),
                  "timedLines": len(lines)},
        "stems": stems,
    }


def listening_md(r: dict) -> str:
    """The report as a page Claude reads before planning."""
    k, en, v = r["key"], r["energy"], r["voice"]
    out = [f"# Listening report: {r['title'] or 'the song'}" + (f" by {r['artist']}" if r["artist"] else ""), "",
           "Measured from the audio by tools/import_song.py. These are measurements, not taste: read them with",
           "song/meta.json (what the person said about the feel, if anything) and song/background.md (what the song is",
           "and where it comes from, when the app could look it up).", "",
           f"- **Length** {r['duration']:.1f} s (music ends {r['musicEnd']:.1f} s)",
           f"- **Tempo** {r['tempo']} BPM in {r['meter']}, {r['tempoFeel']}" + (f"; {r['halfOrDouble']}" if r["halfOrDouble"] else ""),
           f"- **Key** leans {k['name']} (r {k['confidence']}), next {k['next']} (r {k['nextConfidence']}); {k['note']}"
           + (f". The song file's tag says {r['tagKey']}" + (" (they agree)" if r["tagKey"] in (k["name"], k["next"]) else
              " (they disagree: a relative or neighbouring key is common; let the mood decide, not the label)") if r.get("tagKey") else ""),
           f"- **Dynamics** {en['dynamics']}; loudest eight bars {en['peak']['start']:.1f}–{en['peak']['end']:.1f} s",
           f"- **Brightness** median spectral centroid {r['brightnessHz']} Hz (per section below, relative to this)",
           f"- **Voice** in {len(v['moments'])} stretches, {v['share'] * 100:.0f}% of the song"
           + (f", first at {v['firstAt']:.1f} s, last ends {v['lastAt']:.1f} s" if v["moments"] else "")
           + f"; {v['timedLines']} lyric lines timed" + ("" if v["stem"] else " (no vocal stem: presence from the song map)"),
           f"- **Stems** {', '.join(['vocals'] * v['stem'] + r['stems']) or 'none'}", "",
           "## Energy arc", "",
           "| Section | Time | Energy | Brightness | Hits/s | Hats/s | Carried by | Voice | Lines | Key |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for s in r["sections"]:
        bar = BARS[min(7, int(s["energy"] * 8))]
        out.append(f"| {s['name']} | {s['start']:.1f}–{s['end']:.1f} | {bar} {s['energy']:.2f} | {s['brightness']} ({s['brightnessHz']} Hz) "
                   f"| {s['hitsPerSec']} | {s['hatsPerSec']} | {', '.join(s['carriedBy']) or 'little'} | {s['voice'] * 100:.0f}% "
                   f"| {s['lines']} | {s['key']} |")
    out += ["", "Energy is the mix's loudness envelope (0–1 against the song's own loudest moments). Carried by: the stems",
            "whose level in the section is highest. Voice: the share of the section where the vocal is clearly present.", "",
            "## Biggest changes", ""]
    out += [f"- {c['at']:.1f} s, {c['from']} → {c['to']}: energy {'up' if c['change'] > 0 else 'down'} {abs(c['change']):.2f}"
            for c in en["biggestChanges"]]
    out += ["", "## Where the voice is", ""]
    if v["moments"]:
        out += [f"- {m['start']:.1f}–{m['end']:.1f} s" + (" (timed words)" if m["words"] else " (no timed words)") for m in v["moments"][:60]]
        if len(v["moments"]) > 60:
            out.append(f"- … {len(v['moments']) - 60} more in listening.json")
    else:
        out.append("- No clear voice: an instrumental, or the vocal stem is very quiet.")
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="song/ → analysis/ (see the top of this file)")
    ap.add_argument("--lead", type=float, default=0.04, help="how far ahead of its sung start a word is cued (s)")
    ap.add_argument("--snap", type=float, default=0.05, help="a word this close to a drum hit lands on the hit (s)")
    args = ap.parse_args()

    if not (SONG / "song.m4a").exists():
        sys.exit("song/song.m4a is missing: the app writes song/ before this runs")
    meta = load_json(SONG / "meta.json") or {}
    timing = load_json(SONG / "timing.json")
    songmap = load_json(SONG / "songmap.json")
    if timing is None:
        warn("song/timing.json is missing: no lyric lines, and the grid comes from the song map")
        timing = {}
    if songmap is None:
        warn("song/songmap.json is missing: drum hits are measured from the mix instead")
        songmap = {}
    OUT.mkdir(exist_ok=True)

    say("decoding song/song.m4a …")
    mix = decode(SONG / "song.m4a", SR)
    dur = len(mix) / SR
    voc = None
    subtract = False
    lag = 0
    if (SONG / "vocals.m4a").exists():
        say("decoding song/vocals.m4a …")
        voc = decode(SONG / "vocals.m4a", SR)
        voc = np.pad(voc, (0, max(0, len(mix) - len(voc))))[:len(mix)]
        lag, r = vocal_lag(mix, voc)
        subtract = r >= 0.1
        if lag:
            voc = shift(voc, lag)
        say(f"  the vocal lines up with the mix at {lag} samples ({lag / SR * 1000:.1f} ms), correlation {r:.2f}"
            + ("" if subtract else ": too weak to subtract it from the mix; using it for vocal onsets and envelope only"))
    else:
        warn("song/vocals.m4a is missing: vocal onsets are the sung word starts, the vocal envelope the song map's presence")
    stems = {}
    for k in ("drums", "bass", "other"):
        path = SONG / "stems" / f"{k}.m4a"
        if path.exists():
            say(f"decoding song/stems/{k}.m4a …")
            y = decode(path, SR)
            stems[k] = shift(np.pad(y, (0, max(0, len(mix) - len(y))))[:len(mix)], lag)  # made with the vocal: same lag
    if not stems:
        say("  no song/stems/: bass and other are measured from the mix with the vocal taken out")

    # ---------------- spectra
    say("measuring spectra …")
    edges = np.geomspace(40, 16000, NB + 1)
    have_stems = "bass" in stems and "other" in stems
    rms_spec = {"bass": ("bass", 30, 400) if have_stems else ("acc", 30, 250),
                "other": ("other", 150, 12000) if have_stems else ("acc", 250, 12000), "vocals": ("voc", 80, 10000),
                "mix": ("mix", 30, 16000), "low": ("mix", 30, 150), "mid": ("mix", 300, 2500), "high": ("mix", 5000, 16000)}
    for i in range(NB):
        rms_spec[f"b{i}"] = ("mix", edges[i], edges[i + 1])
    hits = songmap.get("hits") or {}
    have_hits = all(isinstance(hits.get(k), list) for k in ("kick", "snare", "hat"))
    flux_spec = {"bass": ("bass", 30, 300) if have_stems else ("acc", 30, 200),
                 "other": ("other", 150, 8000) if have_stems else ("acc", 150, 6000),
                 "vocals": ("voc", 80, 8000), "mix": ("mix", 30, 12000)}
    if not have_hits:
        flux_spec.update({"kick": ("acc", 30, 130), "snare": ("acc", 180, 4000), "hat": ("acc", 7000, 16000)})
    rms, flux, ft, chroma, centroid = analyse(mix, voc, subtract, rms_spec, flux_spec, stems)

    # ---------------- onsets
    ons = {}
    if have_hits:
        for k in ("kick", "snare", "hat"):
            ons[k] = [[round(float(h[0]), 4), round(float(h[1]), 3)] for h in hits[k] if 0 <= h[0] <= dur]
    else:
        ons["kick"] = peaks(flux["kick"], ft, 0.2, 0.09)
        ons["snare"] = peaks(flux["snare"], ft, 0.22, 0.09)
        ons["hat"] = peaks(flux["hat"], ft, 0.25, 0.07)
    ons["hit"] = merge([ons["kick"], ons["snare"]])
    ons["bass"] = peaks(flux["bass"], ft, 0.22, 0.09)
    ons["other"] = peaks(flux["other"], ft, 0.3, 0.09)
    ons["mix"] = peaks(flux["mix"], ft, 0.3, 0.09)
    if voc is not None:
        ons["vocals"] = peaks(flux["vocals"], ft, 0.25, 0.1)

    # ---------------- envelopes
    t_env = np.arange(int(np.ceil(dur * ENV_HZ))) / ENV_HZ
    keys = ["kick", "snare", "hat", "drums", "bass", "other", "vocals", "mix", "low", "mid", "high"]
    release = {"kick": 0.07, "snare": 0.06, "hat": 0.04, "bass": 0.08, "other": 0.06, "vocals": 0.08, "mix": 0.08,
               "low": 0.08, "mid": 0.06, "high": 0.04}
    env = {}
    drum_rows = np.stack([impulses(ons[k], ft) for k in ("kick", "snare", "hat")])
    drum_env = follow(drum_rows, np.array([release["kick"], release["snare"], release["hat"]]))
    for i, k in enumerate(("kick", "snare", "hat")):
        x = np.interp(t_env, ft, drum_env[i])
        env[k] = (x / (x.max() + 1e-9)).astype(np.float32)
    d = env["kick"] + env["snare"] + 0.6 * env["hat"]
    env["drums"] = (d / (d.max() + 1e-9)).astype(np.float32)
    names = ["bass", "other", "vocals", "mix", "low", "mid", "high"]
    F = follow(np.stack([rms[k] for k in names]), np.array([release[k] for k in names]))
    for i, k in enumerate(names):
        env[k] = norm(np.interp(t_env, ft, F[i]))
    if voc is None:
        pres = (songmap.get("vocal") or {}).get("presence")
        hop = (songmap.get("vocal") or {}).get("hop", 0.05)
        env["vocals"] = (np.interp(t_env, np.arange(len(pres)) * hop, pres).astype(np.float32) if pres
                         else np.zeros(len(t_env), np.float32))
    B = follow(np.stack([rms[f"b{i}"] for i in range(NB)]), np.full(NB, 0.07))
    bands = np.stack([np.interp(t_env, ft, B[i]) for i in range(NB)])
    bands = (bands / (np.percentile(bands, 99.5, axis=1, keepdims=True) + 1e-9)).astype(np.float32)
    mix_env = env["mix"]
    loud = np.flatnonzero(mix_env > 0.03)
    music_end = float(t_env[loud[-1]]) if len(loud) else dur

    # ---------------- grid
    meter = int(timing.get("meter") or songmap.get("meter") or 4)
    beats = timing.get("beats") or songmap.get("beats") or []
    down = timing.get("downbeat")
    if down is None:
        down = (songmap.get("downbeat") or {}).get("first", 0)
    tempo = timing.get("tempo") or (songmap.get("tempo") or {}).get("bpm") or 0
    if len(beats) >= 2 * meter:
        bars = [round(float(b), 4) for b in beats[int(down)::meter]]
    else:
        bars = [round(float(b), 4) for b in (songmap.get("bars") or [])]
    if len(bars) < 2:
        if not tempo:
            sys.exit("no beats in song/timing.json or song/songmap.json, and no tempo: can't make a bar grid")
        warn("no beat grid: bars made from the tempo alone, starting at 0")
        bar_len = 60 / tempo * meter
        bars = [round(i * bar_len, 4) for i in range(int(dur / bar_len) + 2)]
    if songmap.get("bars") and timing.get("beats"):
        sb = np.array(songmap["bars"])
        diffs = [float(np.min(np.abs(sb - b))) for b in bars]
        if np.median(diffs) > 0.02:
            warn(f"the bars from timing.json differ from the song map's by {np.median(diffs) * 1000:.0f} ms (median); "
                 "timing.json wins")

    # ---------------- sections
    secs_in = timing.get("sections") or [
        {"name": s.get("label") or s.get("kind") or f"part {i + 1}", "start": s["start"], "end": s["end"]}
        for i, s in enumerate(songmap.get("segments") or [])]
    sections, used = [], {}
    for s in secs_in:
        name = str(s.get("name") or s.get("label") or "section")
        base = slug(name)
        used[base] = used.get(base, 0) + 1
        sid = base if used[base] == 1 else f"{base}-{used[base]}"
        b0, b1 = bar_pos(bars, s["start"]), bar_pos(bars, s["end"])
        b0, b1 = [round(x) if abs(x - round(x)) < 0.02 else round(x, 3) for x in (b0, b1)]
        sections.append({"id": sid, "name": name, "start": round(float(s["start"]), 4), "end": round(float(s["end"]), 4),
                         "bar0": b0, "bar1": b1})

    def section_of(t: float, label=None) -> str | None:
        """The section a line belongs to: the one its label names, else the one containing t (its middle)."""
        if isinstance(label, str) and label.strip():
            named = [s for s in sections if slug(s["name"]) == slug(label)]
            if len(named) == 1:
                return named[0]["id"]
            if named:
                return min(named, key=lambda s: 0 if s["start"] <= t < s["end"] else min(abs(t - s["start"]), abs(t - s["end"])))["id"]
        for s in sections:
            if s["start"] <= t < s["end"]:
                return s["id"]
        before = [s for s in sections if s["start"] <= t]
        return before[-1]["id"] if before else (sections[0]["id"] if sections else None)

    # ---------------- lyric lines and cues
    def cue(t: float) -> tuple[float, str]:
        best = None
        for key, mn in SNAP_KEYS:
            for ot, os in ons.get(key, []):
                if ot < t - args.snap:
                    continue
                if ot > t + args.snap:
                    break
                if os >= mn and (best is None or abs(ot - t) < abs(best[0] - t)):
                    best = (ot, key)
        return (round(best[0] - EARLY, 4), best[1]) if best else (round(t - args.lead, 4), "lead")

    lines, ids, n_words, n_snapped = [], set(), 0, 0
    for n, ln in enumerate(timing.get("lines") or []):
        words = [w for w in (ln.get("words") or []) if str(w.get("text", "")).strip()]
        lid = str(ln.get("id") or f"l{n + 1}")
        if lid in ids:
            lid = f"{lid}-{n + 1}"
        ids.add(lid)
        if not words:
            warn(f"line {lid} has no timed words; left out")
            continue
        for a, b in zip(words, words[1:]):
            if b["start"] < a["start"]:
                warn(f"line {lid}: word {b['text']!r} starts before the word before it; kept as given")
        out_words = []
        for w in words:
            c, how = cue(float(w["start"]))
            n_words += 1
            n_snapped += how != "lead"
            out_words.append([str(w["text"]), round(float(w["start"]), 4), round(float(w.get("end", w["start"])), 4), c, how])
        start = float(ln.get("start", words[0]["start"]))
        mid = (float(words[0]["start"]) + float(words[-1].get("end", words[-1]["start"]))) / 2
        lines.append({"id": lid, "sec": section_of(mid, ln.get("section")), "section": ln.get("section"),
                      "text": ln.get("text") or " ".join(w[0] for w in out_words),
                      "start": round(start, 4), "end": round(float(ln.get("end", words[-1].get("end", start))), 4),
                      "words": out_words})
    if voc is None:
        ons["vocals"] = [[w[1], 1.0] for l in lines for w in l["words"]]

    # ---------------- waveforms
    say("making waveforms …")
    n_wave = int(np.ceil(dur * WAVE_HZ))
    mix6 = decode(SONG / "song.m4a", WAVE_HZ)
    voc6 = None
    if voc is not None:
        voc6 = decode(SONG / "vocals.m4a", WAVE_HZ)
        voc6 = np.pad(voc6, (0, max(0, len(mix6) - len(voc6))))[:len(mix6)]
        voc6 = shift(voc6, int(round(lag * WAVE_HZ / SR)))
    acc6 = mix6 - voc6 if (voc6 is not None and subtract) else mix6
    drum_gate = np.interp(np.arange(len(acc6)) / WAVE_HZ, t_env, env["drums"]).astype(np.float32)

    def stem6(k: str, fallback: np.ndarray) -> np.ndarray:
        if k not in stems:
            return fallback
        y = decode(SONG / "stems" / f"{k}.m4a", WAVE_HZ)
        return shift(np.pad(y, (0, max(0, len(mix6) - len(y))))[:len(mix6)], int(round(lag * WAVE_HZ / SR)))
    wave_keys = ["mix", "bass", "other", "vocals", "drums"]
    waves = np.stack([to_int8(mix6, n_wave), to_int8(stem6("bass", fft_band(acc6, WAVE_HZ, 0, 200)), n_wave),
                      to_int8(stem6("other", fft_band(acc6, WAVE_HZ, 200, 2900)), n_wave),
                      to_int8(voc6 if voc6 is not None else np.zeros(n_wave, np.float32), n_wave),
                      to_int8(stem6("drums", acc6 * drum_gate), n_wave)])

    # ---------------- write
    env_arr = np.concatenate([np.stack([env[k] for k in keys]), bands]).astype(np.float32)
    env_arr.tofile(OUT / "env.bin")
    waves.tofile(OUT / "wave.bin")
    analysis = {
        "version": 2,
        "title": meta.get("title") or "", "artist": meta.get("artist") or "",
        "kind": meta.get("kind"), "engine": meta.get("engine"), "fps": meta.get("fps", 60),
        "duration": round(dur, 4), "musicEnd": round(music_end, 4),
        "tempo": tempo, "meter": meter, "downbeat": int(down),
        "bars": bars, "beats": [round(float(b), 4) for b in beats],
        "sections": sections,
        "lyrics": lines,
        "cueRule": {"lead": args.lead, "snap": args.snap, "early": EARLY, "drums": SNAP_KEYS,
                    "words": "[text, sung start, sung end, cue, how] — how: the onset key it snapped to, or 'lead'"},
        "onsets": ons,
        "env": {"hz": ENV_HZ, "n": len(t_env), "keys": keys, "bands": NB, "bandEdges": [round(float(e), 1) for e in edges]},
        "wave": {"hz": WAVE_HZ, "n": n_wave, "keys": wave_keys},
        "source": {"vocals": voc is not None, "stems": sorted(stems), "vocalLagMs": round(lag / SR * 1000, 2), "vocalSubtracted": subtract,
                   "drumHits": "song map" if have_hits else "measured from the mix",
                   "grid": "timing.json" if timing.get("beats") else "songmap.json"},
    }
    (OUT / "analysis.json").write_text(json.dumps(analysis, separators=(",", ":"), ensure_ascii=False))
    report = listening_report(meta, dur, music_end, tempo, meter, bars, sections, lines, ons, env, t_env, chroma, centroid,
                              ft, voc is not None, sorted(stems))
    (OUT / "listening.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    (OUT / "listening.md").write_text(listening_md(report))

    say(f"duration {dur:.2f} s (music ends {music_end:.2f} s) · {tempo} BPM in {meter} · {len(bars)} bars from "
        f"{bars[0]:.3f} s · {len(sections)} sections")
    say("onsets: " + ", ".join(f"{k} {len(v)}" for k, v in ons.items()))
    say(f"lyrics: {len(lines)} lines, {n_words} words; {n_snapped} cued on a drum hit, {n_words - n_snapped} "
        f"{args.lead * 1000:.0f} ms ahead of the voice")
    say(f"key {report['key']['name']} (confidence {report['key']['confidence']}) · energy peak at "
        f"{report['energy']['peak']['start']:.1f} s · voice in {len(report['voice']['moments'])} stretches")
    say(f"wrote analysis/analysis.json, env.bin {env_arr.shape}, wave.bin {waves.shape}, listening.json, listening.md")


if __name__ == "__main__":
    main()
