"""Maps a take's music for Sound / Vision: its beats, bars and phrases, its sections (the unsung ones
too) and its drum hits, so a lyric video can land what it does on the music.

Runs in Sound / Vision's analysis environment on Legion (venv-analysis: numpy and soundfile; nothing
else, and nothing that needs numpy 2), after the separator has written the drums and vocals stems
(analysis_separate.py). Every measure is plain numpy, written out here:

- Onsets: a spectrogram (1024-point FFT, 100 frames a second at 22.05 kHz), 40 mel bands, log
  compression, and the positive spectral flux against the loudest neighbouring band two frames
  earlier (SuperFlux, Böck & Widmer 2013), minus its local mean.
- Tempo: the onset envelope's autocorrelation, weighted toward 120 BPM (a log-normal prior), for the
  song; and the same in 8-second windows, one a bar apart, for the local tempo.
- Beats: dynamic programming (Ellis 2007): the best chain of onsets whose steps stay near the local
  period, so a drifting tempo is followed. Each beat is then placed between frames by a robust
  smoothing spline through the onset peaks, trusted by their strength: drum hits anchor the grid,
  and where there are none (an intro of pads) it runs on at the tempo around it.
- Downbeat: each of the four ways the bars could fall is scored with independent cues: where the
  chords change (with the vocals taken out when there is a vocals stem) and where the bass line
  changes, most weight; the kick; the snare (a backbeat on 2 and 4, or half time on 3, whichever
  the song fits); where the arrangement changes; and where the lyric sections start. The scores are
  weighted, summed, and turned into a confidence with a softmax.
- Hits: band-limited spectral flux of the drums stem (kick 30-150 Hz, snare 150-300 Hz body plus
  1.5-6 kHz noise, hats above 6 kHz), adaptive peak picking with a minimum spacing. Without a drums
  stem, the same bands of the mix (less its vocals, when there is a vocals stem).
- Vocal presence: the vocals stem's loudness against the mix's; without it, when words are sung
  (from the lyric timing).
- Sections: bar-level features (chroma, timbre, loudness), a self-similarity matrix and its
  checkerboard novelty; each sung lyric section is a segment starting on the bar line where its
  chords turn over (after a singer's pickup), and the rest is cut at the clearest changes into
  segments of at least four bars (lengths of four and eight preferred); labeled by position,
  loudness, vocals and repeats.
- Phrases: four-bar groups (eight when the music clearly runs in eights) from each section's first bar.

Usage: python analysis_rhythm.py <spec.json>
The spec: {"mix": path, "drums": path|null, "vocals": path|null, "out": path, "timing": path|null}.
Prints JSON lines: {"event": "stage"|"progress"|"done"|"error", ...}; writes the song map to "out".
"""

from __future__ import annotations

import json
import math
import sys
import time
from typing import Callable

import numpy as np

SR = 22050  # everything is analysed at this rate, in mono
FPS = 100  # onset frames per second (a 10 ms step)
N_FFT = 1024  # 46 ms: short enough to place onsets, long enough for the kick band
CHROMA_FFT = 4096  # 186 ms, for pitch
CHROMA_FPS = 20
CURVE_HOP = 0.05  # the energy and vocal curves' step, as in the timing map
METER = 4
# The onset envelope peaks about 5 ms before a sound starts (the flux compares frames two apart, each
# centred on its time; measured on synthetic drums at 90-140 BPM, 44.1 and 22.05 kHz): times are moved
# this much later.
ONSET_SHIFT = 0.005


def emit(**event) -> None:
    print(json.dumps(event), flush=True)


# ------------------------------------------------------------------ audio and spectra
def to_rate(x: np.ndarray, rate: int) -> np.ndarray:
    """Mono audio at SR (band-limited resampling in the frequency domain, as the separator does)."""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 2:
        x = x.mean(axis=1) if x.shape[1] <= 8 else x.mean(axis=0)
    if rate == SR:
        return x.astype(np.float32)
    n_out = int(round(len(x) * SR / rate))
    spectrum = np.fft.rfft(x)
    out = np.zeros(n_out // 2 + 1, dtype=complex)
    keep = min(len(spectrum), len(out))
    out[:keep] = spectrum[:keep]
    return (np.fft.irfft(out, n_out) * (n_out / len(x))).astype(np.float32)


def spectrogram(x: np.ndarray, n_fft: int, fps: float) -> np.ndarray:
    """Magnitudes (frames, n_fft // 2 + 1), Hann window, frame k centred on k / fps seconds."""
    hop = SR / fps
    count = int(len(x) / hop) + 1
    pad = n_fft // 2
    padded = np.concatenate([np.zeros(pad, np.float32), x.astype(np.float32), np.zeros(n_fft, np.float32)])
    window = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n_fft) / n_fft)).astype(np.float32)
    starts = np.round(np.arange(count) * hop).astype(np.int64)
    idx = np.arange(n_fft)
    out = np.empty((count, n_fft // 2 + 1), np.float32)
    for a in range(0, count, 512):
        s = starts[a : a + 512]
        out[a : a + len(s)] = np.abs(np.fft.rfft(padded[s[:, None] + idx] * window, axis=1))
    return out


def freqs(n_fft: int) -> np.ndarray:
    return np.fft.rfftfreq(n_fft, 1.0 / SR)


def mel_bank(n_fft: int, bands: int = 40, fmin: float = 30.0, fmax: float = 11000.0) -> np.ndarray:
    """Triangular filters evenly spaced on the mel scale: (bands, bins)."""
    mel = lambda f: 2595.0 * np.log10(1.0 + f / 700.0)
    hz = lambda m: 700.0 * (10 ** (m / 2595.0) - 1.0)
    f = freqs(n_fft)
    edges = hz(np.linspace(mel(fmin), mel(fmax), bands + 2))
    bank = np.zeros((bands, len(f)), np.float32)
    for b in range(bands):
        lo, mid, hi = edges[b], edges[b + 1], edges[b + 2]
        bank[b] = np.maximum(0, np.minimum((f - lo) / (mid - lo), (hi - f) / (hi - mid)))
        if not bank[b].any():  # a band narrower than a bin takes its nearest bin
            bank[b, int(np.argmin(np.abs(f - mid)))] = 1.0
    return bank


def moving_average(x: np.ndarray, width: int) -> np.ndarray:
    width = max(1, int(width))
    if width == 1:
        return x.astype(float)
    kernel = np.ones(width) / width
    padded = np.pad(x.astype(float), (width // 2, width - 1 - width // 2), mode="edge")
    return np.convolve(padded, kernel, mode="valid")


def max_filter(x: np.ndarray, radius: int) -> np.ndarray:
    out = x.copy()
    for d in range(1, radius + 1):
        out[d:] = np.maximum(out[d:], x[:-d])
        out[:-d] = np.maximum(out[:-d], x[d:])
    return out


def normalize(x: np.ndarray, lo_pct: float = 5, hi_pct: float = 95) -> np.ndarray:
    """0-1 against the song's own range (5th to 95th percentile), clipped."""
    if len(x) == 0:
        return x
    lo, hi = np.percentile(x, lo_pct), np.percentile(x, hi_pct)
    return np.clip((x - lo) / max(hi - lo, 1e-9), 0, 1)


def db(x: np.ndarray) -> np.ndarray:
    return 20 * np.log10(np.maximum(x, 1e-7))


# ------------------------------------------------------------------ onsets
def log_bands(S: np.ndarray, bank: np.ndarray) -> np.ndarray:
    """Log-compressed band magnitudes, scaled to the song's loud frames (about 60 dB of range)."""
    bands = S @ bank.T
    ref = np.percentile(bands.max(axis=1), 95) + 1e-9
    return np.log1p(1000.0 * bands / ref)


def onset_envelope(S: np.ndarray, bank: np.ndarray, lag: int = 2) -> np.ndarray:
    """SuperFlux: rises in each mel band against the loudest of its neighbours `lag` frames earlier,
    summed, minus the local mean (a quarter second each side), scaled to unit spread."""
    L = log_bands(S, bank)
    ref = L.copy()
    ref[:, 1:] = np.maximum(ref[:, 1:], L[:, :-1])
    ref[:, :-1] = np.maximum(ref[:, :-1], L[:, 1:])
    flux = np.zeros(len(L))
    flux[lag:] = np.maximum(0, L[lag:] - ref[:-lag]).sum(axis=1)
    env = np.maximum(0, flux - moving_average(flux, int(0.5 * FPS)))
    return env / (env.std() + 1e-9)


# ------------------------------------------------------------------ tempo and beats
def autocorrelation(x: np.ndarray, max_lag: int) -> np.ndarray:
    """Unbiased, normalized (lag 0 is 1)."""
    x = x - x.mean()
    n = len(x)
    f = np.fft.rfft(x, 2 * n)
    ac = np.fft.irfft(np.abs(f) ** 2)[: max_lag + 1]
    ac = ac / np.maximum(n - np.arange(max_lag + 1), 1)
    return ac / (ac[0] + 1e-12)


def peak_between(y: np.ndarray, i: int) -> float:
    """A peak's position between samples: a parabola through it and its neighbours."""
    if 0 < i < len(y) - 1:
        a, b, c = y[i - 1], y[i], y[i + 1]
        d = a - 2 * b + c
        if d < 0:
            return i + float(np.clip(0.5 * (a - c) / d, -0.5, 0.5))
    return float(i)


def song_tempo(env: np.ndarray) -> tuple[float, float]:
    """The song's beat period in frames, and how strongly periodic the onsets are (0-1)."""
    lo, hi = int(FPS * 60 / 200), int(FPS * 60 / 60)
    if len(env) < 2 * hi or env.std() < 1e-6:  # too short, or no onsets at all: 120 BPM, and no confidence in it
        return FPS * 0.5, 0.0
    ac = autocorrelation(env, hi + 1)
    lags = np.arange(lo, hi + 1)
    bpm = 60.0 * FPS / lags
    prior = np.exp(-0.5 * (np.log2(bpm / 120.0) / 0.9) ** 2)
    best = int(np.argmax(ac[lo : hi + 1] * prior)) + lo
    period = peak_between(ac, best)
    # Periodicity: how far the chosen peak stands above the autocorrelation's typical level.
    strength = float(np.clip((ac[best] - np.median(ac[lo : hi + 1])) / 0.3, 0, 1))
    return period, strength


def tempo_curve(env: np.ndarray, period: float, window_s: float = 8.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The local beat period: the autocorrelation peak within 12% of the song's, in 8 s windows one bar
    apart. Returns the window centres (frames), the periods (frames) and each window's peak strength."""
    win = int(window_s * FPS)
    step = max(1, int(round(METER * period)))
    lo, hi = int(period * 0.88), int(math.ceil(period * 1.12))
    centres, periods, strengths = [], [], []
    for c in range(win // 2, max(win // 2 + 1, len(env) - win // 2 + 1), step):
        seg = env[max(0, c - win // 2) : c + win // 2]
        if len(seg) < 3 * hi or seg.std() < 1e-6:
            continue
        ac = autocorrelation(seg, hi + 1)
        i = int(np.argmax(ac[lo : hi + 1])) + lo
        centres.append(c)
        periods.append(peak_between(ac, i))
        strengths.append(float(ac[i]))
    if not centres:
        return np.array([len(env) / 2]), np.array([period]), np.array([0.0])
    periods_a, strengths_a = np.array(periods), np.array(strengths)
    # A window with no clear pulse (a break) takes the song's period rather than a guess.
    weak = strengths_a < 0.1
    periods_a[weak] = period
    if len(periods_a) >= 3:  # a median of three steadies single outliers
        padded = np.concatenate([[periods_a[0]], periods_a, [periods_a[-1]]])
        periods_a = np.median(np.stack([padded[:-2], padded[1:-1], padded[2:]]), axis=0)
    return np.array(centres, dtype=float), periods_a, strengths_a


def track_beats(env: np.ndarray, period_at: np.ndarray, tightness: float = 400.0) -> np.ndarray:
    """Ellis's dynamic programme: each frame's best score is its onset strength plus the best earlier
    beat's score, less a penalty on how far the step between them is from the local period (squared
    log ratio). The best chain, traced back from the end, is the beats (as frames). The tightness is
    four times librosa's: made music keeps time, so a weak onset off the grid (in a sparse intro)
    shouldn't bend it; a 5% longer or shorter step costs as much as a typical onset is worth."""
    n = len(env)
    smooth = np.convolve(env, np.exp(-0.5 * (np.arange(-6, 7) / 1.5) ** 2), mode="same")
    score = np.zeros(n)
    back = np.full(n, -1)
    for t in range(n):
        p = period_at[t]
        a, b = t - int(math.ceil(1.4 * p)), t - int(0.7 * p)
        if b < 0:
            score[t] = smooth[t]
            continue
        prev = np.arange(max(0, a), b + 1)
        cand = score[prev] - tightness * np.log((t - prev) / p) ** 2
        k = int(np.argmax(cand))
        if cand[k] > 0:
            score[t] = smooth[t] + cand[k]
            back[t] = prev[k]
        else:
            score[t] = smooth[t]
    # The chain ends at the best score within the last period and a half.
    tail = max(0, n - int(1.5 * period_at[-1]))
    t = tail + int(np.argmax(score[tail:]))
    beats = [t]
    while back[t] >= 0:
        t = back[t]
        beats.append(t)
    return np.array(beats[::-1])


def solve_pentadiagonal(d0: np.ndarray, d1: np.ndarray, d2: np.ndarray, rhs: np.ndarray) -> np.ndarray:
    """Solves A x = rhs for a symmetric positive-definite A with five bands (LDL^T): d0 the diagonal,
    d1 and d2 the first and second bands below it."""
    n = len(d0)
    D, a, b = np.zeros(n), np.zeros(n), np.zeros(n)
    for i in range(n):
        D[i] = d0[i] - (a[i - 1] ** 2 * D[i - 1] if i >= 1 else 0.0) - (b[i - 2] ** 2 * D[i - 2] if i >= 2 else 0.0)
        if i + 1 < n:
            a[i] = (d1[i] - (b[i - 1] * a[i - 1] * D[i - 1] if i >= 1 else 0.0)) / D[i]
        if i + 2 < n:
            b[i] = d2[i] / D[i]
    y = np.zeros(n)
    for i in range(n):
        y[i] = rhs[i] - (a[i - 1] * y[i - 1] if i >= 1 else 0.0) - (b[i - 2] * y[i - 2] if i >= 2 else 0.0)
    x = y / D
    for i in range(n - 1, -1, -1):
        x[i] -= (a[i] * x[i + 1] if i + 1 < n else 0.0) + (b[i] * x[i + 2] if i + 2 < n else 0.0)
    return x


def smooth_grid(pos: np.ndarray, weight: np.ndarray, stiffness: float) -> np.ndarray:
    """The beat times closest to `pos` (by `weight`) whose steps change least: minimises
    sum w (t - pos)^2 + stiffness * sum (t[i+1] - 2 t[i] + t[i-1])^2, a smoothing spline over the
    beats. Where nothing is heard (weight near zero) the grid runs straight on at the tempo around it."""
    n = len(pos)
    d0, d1, d2 = weight.astype(float).copy(), np.zeros(n), np.zeros(n)
    for i in range(n - 2):  # each second difference (i, i+1, i+2) adds stiffness * [1, -2, 1]^T [1, -2, 1]
        d0[i] += stiffness
        d0[i + 1] += 4 * stiffness
        d0[i + 2] += stiffness
        d1[i] -= 2 * stiffness
        d1[i + 1] -= 2 * stiffness
        d2[i] += stiffness
    return solve_pentadiagonal(d0 + 1e-9, d1, d2, weight * pos)


def refine_beats(env: np.ndarray, frames: np.ndarray, stiffness: float = 400.0) -> np.ndarray:
    """Beat positions between frames. Each beat is heard at the onset peak it sits on (within 30 ms,
    between frames by a parabola), trusted by that onset's strength (fully from about three spreads
    of the envelope up, the strength of a drum hit; a soft pad's slow attack peaks late and counts
    little). The grid is then the smoothing spline through what was heard: it keeps the steps even
    unless the music moves (a steady tempo comes out as an even grid, and a drifting one, or a song
    that pushes a few milliseconds ahead, is followed), and where nothing clear is heard (an intro or a
    break of pads) it runs straight on at the tempo the drums keep around it. Twice more, beats heard
    more than 40 ms from the grid count less (bisquare), so a stray onset can't pull it."""
    n = len(frames)
    if n < 4:
        return frames.astype(float)
    pos, strength = np.zeros(n), np.zeros(n)
    for i, f in enumerate(frames):
        a, b = max(0, f - 3), min(len(env), f + 4)
        j = a + int(np.argmax(env[a:b]))
        pos[i] = peak_between(env, j) if env[j] > 0 else float(f)
        strength[i] = max(float(env[j]), 0.0)
    trust = np.minimum(strength / 3.0, 1.0) ** 2 + 1e-4
    weight = trust.copy()
    grid = smooth_grid(pos, weight, stiffness)
    for _ in range(2):
        r = np.abs(pos - grid) / 4.0
        weight = trust * np.where(r < 1, (1 - r**2) ** 2, 0.0) + 1e-4
        grid = smooth_grid(pos, weight, stiffness)
    return grid


def beats_and_tempo(env: np.ndarray, rms_db: np.ndarray) -> dict:
    """Beats (seconds), their strengths, the song's tempo and its local curve."""
    period, periodicity = song_tempo(env)
    centres, periods, strengths = tempo_curve(env, period)
    period_at = np.interp(np.arange(len(env)), centres, periods)
    frames = track_beats(env, period_at)
    times = refine_beats(env, frames) / FPS + ONSET_SHIFT
    # Beats in the silence before the music starts or after it ends are dropped (silence: 45 dB under
    # the song's loud parts for a whole second, so the gaps between drum hits don't count).
    quiet = max_filter(rms_db, int(0.5 / CURVE_HOP)) < (np.percentile(rms_db, 95) - 45)
    hop_at = lambda t: min(len(rms_db) - 1, max(0, int(round(t / CURVE_HOP))))
    keep = np.array([not quiet[hop_at(t)] for t in times], dtype=bool)
    if keep.any():
        times = times[int(np.argmax(keep)) : len(keep) - int(np.argmax(keep[::-1]))]
    times = times[(times >= 0) & (times <= len(env) / FPS)]
    ibi = np.diff(times)
    bpm = 60.0 / float(np.median(ibi)) if len(ibi) else 60.0 * FPS / period
    # The local tempo at each bar: 60 / the median step over the four beats around it.
    curve = []
    for i in range(0, len(times), METER):
        seg = ibi[max(0, i - 2) : i + 2]
        if len(seg):
            curve.append([round(float(times[i]), 2), round(60.0 / float(np.median(seg)), 1)])
    values = np.array([c[1] for c in curve]) if curve else np.array([bpm])
    spread = float(np.percentile(values, 95) - np.percentile(values, 5)) if len(values) > 1 else 0.0
    # How sure: the onsets' periodicity, and how much more onset energy sits on the beats than off them.
    on = np.array([env[max(0, int(round((t - ONSET_SHIFT) * FPS)) - 2) : int(round((t - ONSET_SHIFT) * FPS)) + 3].max(initial=0) for t in times])
    contrast = float(np.clip((on.mean() / (env.mean() + 1e-9) - 1.0) / 3.0, 0, 1)) if len(on) else 0.0
    # (Periodicity leads: a beatless song still gets beats, and they find what onsets there are.)
    confidence = round(periodicity * (0.6 + 0.4 * contrast) * (1.0 if len(times) >= 8 else 0.3), 3)
    strength = normalize(on, 0, 95) if len(on) else on
    return {
        "bpm": round(bpm, 1),
        "confidence": confidence,
        "stable": spread <= max(1.0, 0.015 * bpm),
        "curve": curve,
        "beats": times,
        "strength": strength,
        "spread": spread,
    }


# ------------------------------------------------------------------ features over beats and bars
def span_means(F: np.ndarray, fps: float, edges: np.ndarray) -> np.ndarray:
    """The mean of frame features F (frames, dims) over each span between consecutive edge times."""
    F = np.asarray(F, dtype=float)
    if F.ndim == 1:
        F = F[:, None]
    cs = np.vstack([np.zeros((1, F.shape[1])), np.cumsum(F, axis=0)])
    idx = np.clip(np.round(np.asarray(edges, dtype=float) * fps).astype(int), 0, len(F))
    b = np.minimum(np.maximum(idx[1:], idx[:-1] + 1), len(F))
    a = np.clip(np.minimum(idx[:-1], b - 1), 0, None)
    return (cs[b] - cs[a]) / np.maximum(b - a, 1)[:, None]


def unit(v: np.ndarray) -> np.ndarray:
    return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-9)


def standardize(F: np.ndarray) -> np.ndarray:
    return (F - F.mean(axis=0)) / (F.std(axis=0) + 1e-9)


def chromagram(x: np.ndarray, n_fft: int = CHROMA_FFT, fmin: float = 55.0, fmax: float = 2000.0) -> np.ndarray:
    """12 pitch classes, 20 frames a second: the log-compressed spectrum from fmin to fmax folded onto
    the nearest semitone, each bin weighted by how close it is to one."""
    S = spectrogram(x, n_fft, CHROMA_FPS)
    f = freqs(n_fft)
    sel = (f >= fmin) & (f <= fmax)
    midi = 69 + 12 * np.log2(f[sel] / 440.0)
    near = np.round(midi)
    pc = near.astype(int) % 12
    ref = np.percentile(S[:, sel].max(axis=1), 95) + 1e-9
    L = np.log1p(100.0 * S[:, sel] / ref) * np.cos(np.pi * (midi - near))
    C = np.zeros((len(S), 12))
    for k in range(12):
        C[:, k] = L[:, pc == k].sum(axis=1)
    return C


def signed_ranks(v: np.ndarray) -> np.ndarray:
    """Each value's rank among them all, from -1 (lowest) to 1 (highest); ties share their mean rank."""
    n = len(v)
    order = np.argsort(v, kind="mergesort")
    r = np.empty(n)
    r[order] = np.arange(n)
    sv = v[order]
    i = 0
    while i < n:
        j = i
        while j + 1 < n and sv[j + 1] == sv[i]:
            j += 1
        if j > i:
            r[order[i : j + 1]] = (i + j) / 2
        i = j + 1
    return r / max(n - 1, 1) * 2 - 1


def phase_scores(values: np.ndarray) -> np.ndarray:
    """For each of the four phases, how high its beats rank among all beats (-1..1); NaN is no value."""
    ok = ~np.isnan(values)
    idx = np.nonzero(ok)[0]
    if len(idx) < METER:
        return np.zeros(METER)
    r = signed_ranks(values[ok])
    return np.array([r[idx % METER == p].mean() if np.any(idx % METER == p) else 0.0 for p in range(METER)])


def phase_shares(values: np.ndarray, top: float = 0.2) -> np.ndarray:
    """Where the biggest values fall: of the top fifth of beats, each phase's share of how far they
    rise above that cut, as 2 * (share - 1/4) (-0.5..1.5). For changes that come only every other bar
    (two-bar chords), a mean over all of a phase's beats would halve the signal; this doesn't."""
    ok = ~np.isnan(values)
    idx = np.nonzero(ok)[0]
    if len(idx) < 2 * METER:
        return np.zeros(METER)
    cut_at = float(np.quantile(values[ok], 1 - top))
    sel = idx[values[ok] >= cut_at]
    w = values[sel] - cut_at + 1e-9
    h = np.array([w[sel % METER == p].sum() for p in range(METER)])
    return 2 * (h / h.sum() - 1.0 / METER)


# ------------------------------------------------------------------ downbeat
# How much each cue counts. Harmony leads (chords, and the bass line most of all, change at bar lines
# in almost every style); the kick and snare mostly tell beats 1 and 3 from 2 and 4; where the
# arrangement changes and where the lyric sections start tell the bar line from the half bar (a
# singer's pickup makes the lyric cue the loosest).
CUE_WEIGHTS = {"harmony": 1.0, "bass": 1.0, "kick": 0.5, "snare": 0.75, "novelty": 0.75, "sections": 0.35}
SOFTMAX = 3.0  # a lead of 1 (a cue that is fully decisive on its own) gives about 0.9


def change_across(C: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """How much pitch content changes across each beat: the two beats before it against the two
    after, plus half of the four before against the four after (1 - cosine of the mean chroma)."""
    n = len(edges) - 1
    Cb = unit(span_means(C, CHROMA_FPS, edges))
    change = np.full(n, np.nan)
    for i in range(2, n - 1):
        d = 1 - float(unit(Cb[i - 2 : i].mean(0)) @ unit(Cb[i : i + 2].mean(0)))
        if 4 <= i <= n - 4:
            d += 0.5 * (1 - float(unit(Cb[i - 4 : i].mean(0)) @ unit(Cb[i : i + 4].mean(0))))
        change[i] = d
    return change


def downbeat(beats: np.ndarray, chroma: np.ndarray, bass: np.ndarray, timbre: np.ndarray, kick_at: np.ndarray, snare_at: np.ndarray,
             section_starts: list[float]) -> dict:
    """Which of the first four beats is the first "one", scored by each cue for each of the four
    phases (the beats i with i % 4 == phase being the bar lines), weighted and summed, then a
    softmax. Returns first, confidence (the winner's share), scores (every phase's share) and cues."""
    n = len(beats)
    if n < 3 * METER:
        return {"first": 0, "confidence": 0.25, "scores": [0.25] * METER, "cues": {}}
    edges = np.append(beats, beats[-1] + float(np.median(np.diff(beats))))
    cues: dict[str, np.ndarray] = {}
    # Harmony: where the chords change (55 Hz-2 kHz, the vocals taken out when there is a vocals
    # stem, since a melody moves on every beat), and where the bass line changes note (40-250 Hz).
    cues["harmony"] = phase_shares(change_across(chroma, edges))
    cues["bass"] = phase_shares(change_across(bass, edges))
    # Kick: beat 1 carries one in nearly every groove.
    cues["kick"] = phase_scores(kick_at)
    # Snare: on beats 2 and 4 (a backbeat), or on beat 3 alone (half time, as in many pop and dance
    # drops); whichever pattern the song fits better.
    m = phase_scores(snare_at)
    backbeat = np.array([(m[(p + 1) % METER] + m[(p + 3) % METER] - m[p] - m[(p + 2) % METER]) / 2 for p in range(METER)])
    halftime = np.array([m[(p + 2) % METER] - (m[p] + m[(p + 1) % METER] + m[(p + 3) % METER]) / 3 for p in range(METER)])
    cues["snare"] = halftime if halftime.max() > backbeat.max() else backbeat
    # Arrangement changes (timbre and loudness, eight beats before against eight after) peak on the
    # bar lines where sections and phrases begin: which phase the clear peaks fall on.
    W = 2 * METER
    if n >= 4 * W:
        Z = standardize(span_means(timbre, FPS, edges))
        nov = np.full(n, np.nan)
        for i in range(W, n - W + 1):
            nov[i] = np.linalg.norm(Z[i : i + W].mean(0) - Z[i - W : i].mean(0)) / math.sqrt(Z.shape[1])
        valid = nov[~np.isnan(nov)]
        med, top = float(np.median(valid)), float(np.max(valid))
        hist, count = np.zeros(METER), 0
        for i in range(W, n - W + 1):
            window = nov[max(W, i - 3) : i + 4]
            if nov[i] >= np.nanmax(window) and nov[i] > med + 0.35 * (top - med):
                hist[i % METER] += (nov[i] - med) / (top - med + 1e-9)
                count += 1
        if count:
            cues["novelty"] = 2 * (hist / hist.sum() - 1 / METER) * min(1.0, count / 6)
    # Where the lyric sections start (the beat nearest each first word).
    if section_starts:
        hist = np.zeros(METER)
        for t in section_starts:
            hist[int(np.argmin(np.abs(beats - t))) % METER] += 1
        cues["sections"] = 2 * (hist / hist.sum() - 1 / METER) * min(1.0, len(section_starts) / 4)
    total = sum(CUE_WEIGHTS[k] * v for k, v in cues.items())
    p = np.exp(SOFTMAX * (total - total.max()))
    p /= p.sum()
    first = int(np.argmax(p))
    return {"first": first, "confidence": round(float(p[first]), 3), "scores": [round(float(v), 3) for v in p],
            "cues": {k: [round(float(x), 3) for x in v] for k, v in cues.items()}}


def bars_from(beats: list[float], first: int, meter: int = METER) -> list[float]:
    """Bar lines: every `meter`th beat from the first "one"; the beats before it are a pickup."""
    return list(beats[first % meter :: meter]) if len(beats) else []


# ------------------------------------------------------------------ drum hits
# Each kind of hit: its bands (low Hz, high Hz, weight), how hard the band's level is compressed
# before its rises are measured, and the least a peak must reach (the kind's big hits being 1). The
# kick band is compressed least, so a snare's or a chord's small spill into the lows counts little.
HIT_BANDS = {
    "kick": ((30, 150, 1.0),),
    "snare": ((150, 300, 0.35), (1500, 6000, 0.65)),
    "hat": ((6000, 11025, 1.0),),
}
HIT_GAIN = {"kick": 10.0, "snare": 100.0, "hat": 100.0}
HIT_FLOOR = {"kick": 0.35, "snare": 0.2, "hat": 0.15}
HIT_GAP = {"kick": 0.09, "snare": 0.09, "hat": 0.05}  # seconds: no two hits of a kind closer than this
# Where each kind's detection peaks against the sound's start differs a little from the onset
# envelope's (the lightly compressed kick band peaks later, as the kick's low end builds): measured
# on the synthetic drums in tests/synth_song.py, hits are moved by these instead of ONSET_SHIFT.
HIT_SHIFT = {"kick": -0.001, "snare": 0.002, "hat": 0.002}


def band_flux(S: np.ndarray, lo: float, hi: float, gain: float = 100.0, lag: int = 2) -> np.ndarray:
    """The mean rise across a band's bins (log-compressed), scaled so the band's big hits are about 1."""
    f = freqs(N_FFT)
    B = S[:, (f >= lo) & (f < hi)].astype(float)
    ref = np.percentile(B.max(axis=1), 99) + 1e-9
    L = np.log1p(gain * B / ref)
    d = np.zeros(len(B))
    d[lag:] = np.maximum(0, L[lag:] - L[:-lag]).mean(axis=1)
    return d / (np.percentile(d, 99.5) + 1e-9)


def pick_peaks(curve: np.ndarray, gap_s: float, delta: float = 0.1, floor: float = 0.15) -> np.ndarray:
    """Frames where the curve peaks: the highest point within half the gap each side, above its local
    mean (a quarter second each side) by `delta` and above `floor`; then no two closer than the gap,
    the stronger kept."""
    local = moving_average(curve, int(0.5 * FPS))
    radius = max(1, int(gap_s * FPS / 2))
    cand = np.nonzero((curve >= max_filter(curve, radius)) & (curve >= local + delta) & (curve >= floor))[0]
    blocked = np.zeros(len(curve), dtype=bool)
    gap = int(round(gap_s * FPS))
    kept = []
    for c in cand[np.argsort(-curve[cand], kind="mergesort")]:
        if not blocked[c]:
            kept.append(c)
            blocked[max(0, c - gap + 1) : c + gap] = True
    return np.array(sorted(kept), dtype=int)


def drum_hits(S: np.ndarray) -> tuple[dict, dict]:
    """Kick, snare and hat hits as [[time, strength 0-1], ...], and each band's detection curve."""
    curves = {name: sum(w * band_flux(S, lo, hi, HIT_GAIN[name]) for lo, hi, w in bands) for name, bands in HIT_BANDS.items()}
    noise = band_flux(S, 1500, 6000)
    hits = {}
    for name, curve in curves.items():
        frames = pick_peaks(curve, HIT_GAP[name], floor=HIT_FLOOR[name])
        if name == "snare" and len(frames):  # a snare has noise in it: a rise in the body band alone is a kick or a bass note
            frames = frames[noise[frames] >= 0.25]
        if len(frames):
            top = float(np.percentile(curve[frames], 95)) + 1e-9
            hits[name] = [[round(peak_between(curve, int(f)) / FPS + HIT_SHIFT[name], 3), round(float(min(1.0, curve[f] / top)), 3)] for f in frames]
        else:
            hits[name] = []
    return hits, curves


def strength_at(curve: np.ndarray, times: np.ndarray, radius_s: float = 0.05) -> np.ndarray:
    """The curve's highest value within `radius_s` of each time."""
    r = int(radius_s * FPS)
    out = np.zeros(len(times))
    for i, t in enumerate(times):
        c = int(round((t - ONSET_SHIFT) * FPS))
        seg = curve[max(0, c - r) : c + r + 1]
        out[i] = float(seg.max()) if len(seg) else 0.0
    return out


# ------------------------------------------------------------------ loudness and vocals
def block_rms(x: np.ndarray, count: int) -> np.ndarray:
    edges = np.minimum(np.round(np.arange(count + 1) * CURVE_HOP * SR).astype(int), len(x))
    cs = np.concatenate([[0.0], np.cumsum(x.astype(float) ** 2)])
    return np.sqrt((cs[edges[1:]] - cs[edges[:-1]]) / np.maximum(np.diff(edges), 1))


def energy_curves(x: np.ndarray, S: np.ndarray, count: int) -> tuple[dict, np.ndarray]:
    """Loudness every 50 ms (in dB, then 0-1 over the song's own range): all of it, and below 250 Hz,
    250 Hz-4 kHz and above 4 kHz. Also returns the loudness in dB, for finding silence."""
    rms_db = db(block_rms(x, count))
    f = freqs(N_FFT)
    P = S.astype(float) ** 2
    times = np.arange(count + 1) * CURVE_HOP

    def band(lo: float, hi: float) -> np.ndarray:
        return normalize(db(np.sqrt(span_means(P[:, (f >= lo) & (f < hi)].sum(axis=1), FPS, times)[:, 0])))

    curves = {"hop": CURVE_HOP, "rms": normalize(rms_db), "low": band(20, 250), "mid": band(250, 4000), "high": band(4000, SR / 2)}
    return curves, rms_db


# The separated vocals' loudness against the mix's, in 50 ms blocks: presence is 0 at this far below
# it and 1 at this. On "Hold the Spark" (HTDemucs vocals, Take D), blocks with a timed word sit at -4
# dB (median; 5th percentile -16.5 dB) and the gaps between sung lines at -19 dB (median).
VOCAL_FLOOR_DB = -24.0
VOCAL_FULL_DB = -12.0


def vocal_presence(x: np.ndarray, vocals: np.ndarray | None, words: list[dict], count: int) -> tuple[np.ndarray | None, str]:
    """0-1 every 50 ms: how present the voice is. From the vocals stem when there is one; else from
    when the lyric timing's words are sung; else unknown (None)."""
    if vocals is not None and len(vocals):
        ratio = db(block_rms(vocals, count)) - db(block_rms(x, count))
        p = np.clip((ratio - VOCAL_FLOOR_DB) / (VOCAL_FULL_DB - VOCAL_FLOOR_DB), 0, 1)
        return np.clip(moving_average(p, 5), 0, 1), "vocals stem against the mix"
    if words:
        p = np.zeros(count)
        spans = sorted((float(w["start"]), float(w["end"])) for w in words if w.get("end", 0) > w.get("start", 0))
        merged: list[list[float]] = []
        for a, b in spans:  # words less than 0.35 s apart are one sung stretch
            if merged and a - merged[-1][1] < 0.35:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        for a, b in merged:
            p[max(0, int(a / CURVE_HOP)) : min(count, int(math.ceil(b / CURVE_HOP)))] = 1.0
        return np.clip(moving_average(p, 3), 0, 1), "when the lyric timing's words are sung"
    return None, "none"


# ------------------------------------------------------------------ sections
HIGH_ENERGY = 0.6  # an unsung stretch this loud (0-1, the song's own range) is a drop
LOW_ENERGY = 0.35  # and this quiet, a break
REPEAT = 0.7  # bar-by-bar similarity (-1..1) above which a segment repeats an earlier one
SEGMENT_COST = 0.27  # the least novelty a cut needs (see structure); tuned on ten YuE2 takes


def label_kind(label: str) -> str:
    """A lyric section's kind from its label ("Verse 2", "Pre-Chorus", "Hook")."""
    text = label.lower().replace("-", " ")
    if text == "pre" or text.startswith("pre ") or "pre chorus" in text or "prechorus" in text:
        return "prechorus"
    for word, kind in (("chorus", "chorus"), ("hook", "chorus"), ("refrain", "chorus"), ("verse", "verse"), ("bridge", "bridge"),
                       ("intro", "intro"), ("outro", "outro"), ("coda", "outro"), ("break", "break"), ("drop", "drop"),
                       ("build", "build"), ("solo", "instrumental"), ("instrumental", "instrumental")):
        if word in text:
            return kind
    return "verse"


def checkerboard(sim: np.ndarray, half: int = 4) -> np.ndarray:
    """Novelty at each bar line j (the start of bar j): a Gaussian-tapered checkerboard kernel slid
    along the self-similarity matrix's diagonal (Foote 2000). High where the bars before are alike,
    the bars after are alike, and the two differ."""
    n = len(sim)
    offs = np.arange(-half, half) + 0.5
    g = np.exp(-0.5 * (offs / (half / 2)) ** 2) * np.sign(offs)
    K = np.outer(g, g)
    out = np.zeros(n + 1)
    for j in range(1, n):
        a, b = max(0, j - half), min(n, j + half)
        k = K[a - j + half : b - j + half, a - j + half : b - j + half]
        out[j] = float((sim[a:b, a:b] * k).sum() / (np.abs(k).sum() + 1e-9))
    return out


def step_at(v: np.ndarray, j: int, width: int = 2) -> float:
    """How much a bar-level curve changes at bar line j (the two bars after against the two before)."""
    before, after = v[max(0, j - width) : j], v[j : j + width]
    return abs(float(after.mean()) - float(before.mean())) if len(before) and len(after) else 0.0


def cut(nov: np.ndarray, lo: int, hi: int, cost: float, min_len: int = 4, min_first: int = 4, min_last: int = 4) -> list[int]:
    """Where to cut bars lo..hi into segments of at least min_len bars (the first at least min_first,
    the last at least min_last: an intro or outro at the song's very edge may be short): the cuts that
    maximise the novelty at them, less `cost` for each segment, a little for each length that isn't a
    multiple of eight bars (more when it isn't a multiple of four) and for each bar past sixteen
    (sections rarely run longer), by dynamic programming over the bar lines."""
    n = hi - lo
    if n < min_first + min_last:
        return []
    long = lambda length: 0.015 * max(0, length - 16)
    irregular = lambda length: (0.0 if length % 8 == 0 else 0.05 if length % 4 == 0 else 0.1) + long(length)
    best = np.full(n + 1, -np.inf)
    back = np.full(n + 1, -1)
    best[0] = 0.0
    shortest = lambda i, j: 0 if (i == 0 and j == n) else min_first if i == 0 else min_last if j == n else min_len
    # A short intro or outro at the song's edge has whatever length the song gives it.
    edge = lambda i, j: (i == 0 and min_first < min_len) or (j == n and min_last < min_len)
    for j in range(1, n + 1):
        here = nov[lo + j] if j < n else 0.0
        if j < n and n - j < min(min_len, min_last):
            continue  # no room left for the last segment
        for i in range(0, j):
            if j - i < shortest(i, j):
                continue
            if best[i] > -np.inf:
                v = best[i] - (long(j - i) if edge(i, j) else irregular(j - i)) - cost + here
                if v > best[j]:
                    best[j], back[j] = v, i
    cuts, j = [], n
    while j > 0:
        j = int(back[j])
        if j > 0:
            cuts.append(lo + j)
    return sorted(cuts)


def structure(edges: np.ndarray, duration: float, beat_len: float, chroma: np.ndarray, bass: np.ndarray, timbre: np.ndarray,
              rms: np.ndarray, vocal: np.ndarray | None, lyric: list[dict]) -> tuple[list[dict], np.ndarray]:
    """The song's segments over its bars (edges: every bar line, then the last bar's end), labeled.

    Bar-level features (chroma, timbre, loudness) give a self-similarity matrix and its checkerboard
    novelty, with the changes in loudness and vocal presence. Where the lyric timing says a section is
    sung, it is one segment, from the bar its first word is in (or, after a singer's pickup, the next
    bar line, if the chords turn over there) to the bar line after its last word; a gap of a bar or
    less before the next section stays with it. Without lyric timing, the vocals stem's sung
    stretches play that part. Everything else (the intro, gaps between sections, the outro; or the
    whole song with no vocal information) is cut where the novelty is high, in segments of at least
    four bars, four- and eight-bar lengths preferred; an unsung gap of two or three bars between sung
    sections stands alone. Returns the segments (bar ranges a..b and labels) and the bars' feature
    vectors (for phrases)."""
    nb = len(edges) - 1
    bar_hz = 1.0 / CURVE_HOP
    chroma_bar = span_means(chroma, CHROMA_FPS, edges)
    timbre_bar = span_means(timbre, FPS, edges)
    energy_bar = span_means(rms, bar_hz, edges)[:, 0]
    vocal_bar = span_means(vocal, bar_hz, edges)[:, 0] if vocal is not None else None
    F = np.hstack([standardize(unit(chroma_bar)), standardize(timbre_bar), 2 * standardize(energy_bar[:, None])])
    U = unit(F)
    sim = U @ U.T
    # Novelty at every bar line, on absolute scales so a song with no clear changes isn't cut up: the
    # checkerboard (0-1: about 0.1 inside a section, 0.3-0.7 at a clear change), and steps in loudness
    # and in vocal presence (0-1 curves). A cut must beat the larger of SEGMENT_COST and the song's
    # own 85th percentile of novelty, so each song is cut at its most marked changes.
    nov = np.maximum(checkerboard(sim, 4), 0) + 0.5 * np.array([step_at(energy_bar, j) for j in range(nb + 1)])
    if vocal_bar is not None:
        nov += 0.3 * np.array([step_at(vocal_bar, j) for j in range(nb + 1)])
    cost = max(SEGMENT_COST, float(np.percentile(nov[1:nb], 85))) if nb > 2 else SEGMENT_COST

    # Sung spans, as bar ranges: from the lyric sections, or else from the vocals stem.
    spans: list[tuple[int, int, int | None]] = []
    if lyric:
        # Where the bass line changes note at a bar line (sections start where the chords turn over).
        bass_bar = unit(span_means(bass, CHROMA_FPS, edges))
        turn = np.zeros(nb + 1)
        turn[1:nb] = [1 - float(bass_bar[j - 1] @ bass_bar[j]) for j in range(1, nb)]
        turn /= (np.percentile(turn[1:nb], 90) if nb > 2 else 1.0) + 1e-9

        def near(t: float) -> int:
            """The bar a sung section starts on: the bar its first word is in, or, when the word comes
            1.5 beats or more into that bar (a pickup into the next), whichever of the two bar lines
            the music and the chords change at more, the nearer one a little favoured."""
            a = int(np.clip(np.searchsorted(edges[:nb], t + 0.25 * beat_len, side="right") - 1, 0, nb - 1))
            if a + 1 < nb and (t - edges[a]) / beat_len >= 1.5:
                score = lambda j: nov[j] + min(turn[j], 2.0) - 0.15 * abs(t - edges[j]) / beat_len
                return a + 1 if score(a + 1) >= score(a) else a
            return a

        def after(t: float) -> int:
            """The bar line a sung section ends at: the first after its last word, or the one a bar
            later when the music changes clearly more there (a bar's tag or breakdown after the words)."""
            b = int(np.clip(np.searchsorted(edges, t - 0.5 * beat_len, side="left"), 1, nb))
            return b + 1 if b + 1 < nb and nov[b + 1] > nov[b] + 0.1 else b

        starts = [near(float(s["start"])) for s in lyric]
        for k, s in enumerate(lyric):
            a = starts[k]
            b = max(after(float(s["end"])), a + 1)
            if k + 1 < len(lyric) and (b > starts[k + 1] or starts[k + 1] - b <= 1):
                b = max(starts[k + 1], a + 1)  # a gap of a bar or less belongs to the section before it
            if spans and a < spans[-1][1]:
                a = spans[-1][1]
            if b > a:
                spans.append((a, min(b, nb), k))
    elif vocal_bar is not None:
        sung = vocal_bar >= 0.5
        for j in range(1, nb - 1):  # a one-bar breath doesn't end a sung stretch, nor does one bar make one
            if not sung[j] and sung[j - 1] and sung[j + 1]:
                sung[j] = True
        j = 0
        while j < nb:
            if sung[j]:
                k = j
                while k < nb and sung[k]:
                    k += 1
                if k - j >= 2:
                    spans.append((j, k, None))
                j = k
            else:
                j += 1

    segs: list[dict] = []

    def add(a: int, b: int, sung: bool, k: int | None) -> None:
        segs.append({"a": a, "b": b, "sung": sung, "lyric": k})

    def unsung(a: int, b: int, edge: bool) -> None:
        if b - a < (1 if edge else 2):  # too short to stand alone: the end of what came before
            if segs:
                segs[-1]["b"] = b
            elif b > a:
                add(a, b, False, None)
            return
        # At the song's very start and end, an intro or outro of two bars may stand alone.
        bounds = [a, *cut(nov, a, b, cost, min_first=2 if a == 0 else 4, min_last=2 if b == nb else 4), b]
        for x, y in zip(bounds, bounds[1:]):
            add(x, y, False, None)

    pos = 0
    for a, b, k in spans:
        if a > pos:
            unsung(pos, a, edge=pos == 0)
        if k is not None:
            add(a, b, True, k)
        else:
            bounds = [a, *cut(nov, a, b, cost), b]
            for x, y in zip(bounds, bounds[1:]):
                add(x, y, True, None)
        pos = b
    if pos < nb:
        unsung(pos, nb, edge=True)
    if not segs:
        add(0, nb, False, None)

    # Measures, repeats and kinds.
    t_of = lambda j: 0.0 if j == 0 else (duration if j >= nb else float(edges[j]))
    for s in segs:
        s["start"], s["end"] = t_of(s["a"]), t_of(s["b"])
        lo, hi = int(s["start"] / CURVE_HOP), max(int(s["start"] / CURVE_HOP) + 1, int(s["end"] / CURVE_HOP))
        s["energy"] = float(rms[lo:hi].mean()) if lo < len(rms) else 0.0
        s["vocal"] = float(vocal[lo:hi].mean()) if vocal is not None and lo < len(vocal) else None
        s["label"] = str(lyric[s["lyric"]].get("label") or "") or None if s["lyric"] is not None else None
        s["repeat_of"] = None
    for j, s in enumerate(segs):
        for i in range(j):
            o = segs[i]
            la, lb = o["b"] - o["a"], s["b"] - s["a"]
            if not 0.5 <= la / max(lb, 1) <= 2:
                continue
            same_label = bool(s["label"] and o["label"] and s["label"].strip().lower() == o["label"].strip().lower())
            best = -1.0
            for off in (-1, 0, 1):
                pairs = [(o["a"] + m, s["a"] + m + off) for m in range(min(la, lb)) if s["a"] <= s["a"] + m + off < s["b"]]
                if pairs:
                    best = max(best, float(np.mean([sim[p, q] for p, q in pairs])))
            if best >= REPEAT or (same_label and best >= 0.3):
                s["repeat_of"] = o["repeat_of"] if o["repeat_of"] is not None else i
                break
    sung_energy = [s["energy"] for s in segs if s["sung"]]
    loud = float(np.median(sung_energy)) if sung_energy else HIGH_ENERGY
    first_sung = next((j for j, s in enumerate(segs) if s["sung"]), None)
    for j, s in enumerate(segs):
        nxt = segs[j + 1] if j + 1 < len(segs) else None
        if s["sung"]:
            if s["label"]:
                s["kind"] = label_kind(s["label"])
            else:  # no lyrics: the loud sections that come back are choruses
                repeated = s["repeat_of"] is not None or any(o["repeat_of"] == j for o in segs[j + 1 :])
                s["kind"] = "chorus" if repeated and s["energy"] >= max(loud, 0.5) else "verse"
            continue
        bars_e = energy_bar[s["a"] : s["b"]]
        rising = len(bars_e) >= 2 and float(bars_e[-1] - bars_e[0]) >= 0.2 and float(np.polyfit(np.arange(len(bars_e)), bars_e, 1)[0]) > 0
        louder_next = nxt is not None and nxt["energy"] >= max(HIGH_ENERGY, s["energy"] + 0.1)
        if j == 0:
            s["kind"] = "intro"
        elif nxt is None:
            s["kind"] = "outro"
        elif rising and louder_next:
            s["kind"] = "build"
        elif s["energy"] >= HIGH_ENERGY:
            s["kind"] = "drop"
        elif first_sung is not None and j < first_sung:
            s["kind"] = "intro"  # still before the singing starts
        elif s["energy"] <= LOW_ENERGY:
            s["kind"] = "break"
        else:
            s["kind"] = "instrumental"
    return segs, U


def phrases(segs: list[dict], edges: np.ndarray, duration: float, U: np.ndarray) -> list[dict]:
    """Four-bar phrases from each segment's first bar line; eight-bar ones where the segment is a
    multiple of eight bars and its bars match eight bars on far better than four bars on (the music
    clearly runs in eights). A segment's leftover bars make a shorter last phrase."""
    nb = len(edges) - 1
    out = []
    for s in segs:
        a, b = s["a"], s["b"]
        size = 4
        if b - a >= 16 and (b - a) % 8 == 0:
            s4 = float(np.mean([U[k] @ U[k + 4] for k in range(a, b - 4)]))
            s8 = float(np.mean([U[k] @ U[k + 8] for k in range(a, b - 8)]))
            if s8 >= 0.6 and s8 - s4 >= 0.25:
                size = 8
        for k in range(a, b, size):
            e = min(k + size, b)
            out.append({"start": round(float(edges[k]), 3), "end": round(duration if e >= nb else float(edges[e]), 3), "bars": e - k})
    return out


# ------------------------------------------------------------------ the song map
def rounded(values, digits: int = 3) -> list:
    return [round(float(v), digits) for v in values]


def analyse(mix: np.ndarray, rate: int, drums: np.ndarray | None = None, drums_rate: int | None = None,
            vocals: np.ndarray | None = None, vocals_rate: int | None = None, timing: dict | None = None,
            progress: Callable[[int, int, str], None] | None = None) -> dict:
    """The song map of a mix (any rate, mono or channels last), with its drums and vocals stems when
    there are, and its lyric timing when there is."""
    step = progress or (lambda done, total, message: None)
    total = 6
    x = to_rate(mix, rate)
    duration = len(x) / SR
    if duration < 1.0:
        raise ValueError(f"The take is {duration:.2f} s long, too short to map.")
    count = int(duration / CURVE_HOP)
    step(0, total, "Reading the mix")
    S = spectrogram(x, N_FFT, FPS)
    curves, rms_db = energy_curves(x, S, count)
    env = onset_envelope(S, mel_bank(N_FFT))
    step(1, total, "Finding the beat")
    bt = beats_and_tempo(env, rms_db)
    beats = bt["beats"]
    beat_len = float(np.median(np.diff(beats))) if len(beats) > 1 else 0.5
    step(2, total, "Finding the drum hits")
    same_length = lambda y: np.pad(y, (0, max(0, len(x) - len(y))))[: len(x)]
    v = same_length(to_rate(vocals, vocals_rate or rate)) if vocals is not None else None
    # Without the voice (when there is a vocals stem): the accompaniment, for the harmony (a melody
    # moves on every beat) and, with no drums stem, for the hits (sung consonants are noise bursts).
    backing = x - v if v is not None else x
    d = same_length(to_rate(drums, drums_rate or rate)) if drums is not None else None
    hits, hit_curves = drum_hits(spectrogram(d, N_FFT, FPS) if d is not None else spectrogram(backing, N_FFT, FPS) if v is not None else S)
    step(3, total, "Finding the bars")
    chroma = chromagram(x)
    chords = chromagram(backing) if v is not None else chroma
    bass = chromagram(backing, 8192, 40.0, 250.0)
    timbre = log_bands(S, mel_bank(N_FFT, 20))
    timing = timing or {}
    words = [w for w in timing.get("words") or [] if isinstance(w, dict) and "start" in w and "end" in w]
    lyric = [s for s in timing.get("sections") or [] if isinstance(s, dict) and "start" in s and "end" in s]
    lyric.sort(key=lambda s: float(s["start"]))
    down = downbeat(beats, chords, bass, timbre, strength_at(hit_curves["kick"], beats), strength_at(hit_curves["snare"], beats),
                    [float(s["start"]) for s in lyric])
    beat_list = rounded(beats)
    bars = bars_from(beat_list, down["first"])
    step(4, total, "Finding the sections")
    presence, vocal_source = vocal_presence(x, v, words, count)
    if len(bars) >= 2:
        edges = np.append(np.array(bars), min(duration, bars[-1] + METER * beat_len))
        segs, U = structure(edges, duration, beat_len, chroma, bass, timbre, curves["rms"], presence, lyric)
        phrase_list = phrases(segs, edges, duration, U)
    else:  # too few beats for bars: the whole song is one segment
        segs = [{"a": 0, "b": 1, "start": 0.0, "end": duration, "sung": bool(words), "lyric": None, "label": None, "repeat_of": None,
                 "energy": float(curves["rms"].mean()) if count else 0.0, "vocal": float(presence.mean()) if presence is not None and count else None,
                 "kind": "verse" if words else "instrumental"}]
        phrase_list = []
    step(5, total, "Writing the song map")
    segments = [{
        "start": round(s["start"], 3), "end": round(s["end"], 3), "kind": s["kind"], "sung": bool(s["sung"]),
        "energy": round(s["energy"], 3), "vocal": None if s["vocal"] is None else round(s["vocal"], 3),
        "repeat_of": s["repeat_of"], "label": s["label"],
        "section": None if s["lyric"] is None else lyric[s["lyric"]].get("section", s["lyric"]),
    } for s in segs]
    has_lyrics = bool(lyric)
    return {
        "version": 1,
        "duration": round(duration, 3),
        "method": {
            "onsets": "SuperFlux on 40 mel bands (1024-point FFT, 100 frames/s at 22.05 kHz), less its local mean",
            "tempo": "onset autocorrelation with a log-normal prior at 120 BPM; local tempo from 8 s windows a bar apart",
            "beats": "dynamic programming (Ellis 2007, tightness 400) on the local period, then a robust smoothing spline through the onset peaks, anchored by clear attacks",
            "downbeat": "chord change" + (" (vocals removed)" if v is not None else "") + ", bass-line change, kick, snare (backbeat or half time), "
                        "arrangement novelty" + (" and lyric section starts" if has_lyrics else "") + ", scored per bar phase, weighted, softmax",
            "hits": "drums stem" if d is not None else "mix bands",
            "vocal": vocal_source,
            "structure": "bar self-similarity (chroma, timbre, loudness), checkerboard novelty, loudness and vocal steps; "
                         + ("sung sections from the lyric timing, the rest cut at novelty peaks" if has_lyrics else "cut at novelty peaks")
                         + " (at least 4 bars, 4 and 8 preferred)",
        },
        "tempo": {"bpm": bt["bpm"], "confidence": bt["confidence"], "stable": bool(bt["stable"]), "curve": bt["curve"]},
        "beats": beat_list,
        "beat_strength": rounded(bt["strength"]),
        "meter": METER,
        "downbeat": {"first": down["first"], "confidence": down["confidence"], "scores": down["scores"], "corrected": False, "cues": down["cues"]},
        "bars": bars,
        "phrases": phrase_list,
        "segments": segments,
        "hits": hits,
        "energy": {"hop": CURVE_HOP, **{k: rounded(curves[k]) for k in ("rms", "low", "mid", "high")}},
        "vocal": {"hop": CURVE_HOP, "presence": rounded(presence) if presence is not None else []},
    }


def main() -> None:
    spec = json.loads(open(sys.argv[1]).read())
    started = time.monotonic()
    try:
        import soundfile as sf

        emit(event="stage", stage="rhythm", message="Mapping the song")
        mix, rate = sf.read(spec["mix"], dtype="float32", always_2d=True)
        stems = {}
        for name in ("drums", "vocals"):
            if spec.get(name):
                stems[name] = sf.read(spec[name], dtype="float32", always_2d=True)
        timing = None
        if spec.get("timing"):
            with open(spec["timing"]) as f:
                timing = json.load(f)
        song = analyse(mix, rate,
                       *(stems["drums"] if "drums" in stems else (None, None)),
                       *(stems["vocals"] if "vocals" in stems else (None, None)),
                       timing=timing,
                       progress=lambda done, total, message: emit(event="progress", stage="rhythm", done=done, total=total, message=message))
        with open(spec["out"], "w") as f:
            json.dump(song, f, separators=(",", ":"))
        emit(event="done", seconds=round(time.monotonic() - started, 1), tempo=song["tempo"]["bpm"], beats=len(song["beats"]),
             downbeat=song["downbeat"]["first"], confidence=song["downbeat"]["confidence"], segments=len(song["segments"]),
             hits=song["method"]["hits"])
    except Exception as exc:  # the orchestrator reads this as the reason
        emit(event="error", message=f"{type(exc).__name__}: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
