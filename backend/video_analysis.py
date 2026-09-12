"""Measured beat/cut map for a song; no assumed fifteen-second beat grid."""

import json, sys
from pathlib import Path


def analyze(source, out):
    import numpy as np, soundfile as sf, librosa
    from scipy.signal import butter, sosfiltfilt, find_peaks, resample_poly

    audio, sr = sf.read(source, dtype="float32", always_2d=True)
    duration = len(audio) / sr
    mono = audio.mean(1)
    y = librosa.resample(mono, orig_sr=sr, target_sr=22050)
    hop = 220
    onset = librosa.onset.onset_strength(
        y=y, sr=22050, hop_length=hop, aggregate=np.median
    )
    tempo, frames = librosa.beat.beat_track(
        onset_envelope=onset,
        sr=22050,
        hop_length=hop,
        start_bpm=128,
        tightness=160,
        trim=False,
    )
    coarse = librosa.frames_to_time(frames, sr=22050, hop_length=hop)
    low = sosfiltfilt(butter(4, [35, 180], btype="bandpass", fs=22050, output="sos"), y)
    energy = np.sqrt(np.convolve(low**2, np.ones(220) / 220, mode="same"))
    # Measure each kick attack near the tracked beat, preserving tempo variations.
    smooth = energy[::110]
    delta = np.maximum(0, np.diff(smooth, prepend=smooth[0]))
    peaks, _ = find_peaks(
        delta,
        distance=int(0.22 * 22050 / 110),
        prominence=np.quantile(delta, 0.88) * 0.25,
    )
    peak_times = peaks * 110 / 22050
    beats = []
    snapped = 0
    for beat in coarse:
        nearby = np.where(np.abs(peak_times - beat) < 0.085)[0]
        if len(nearby):
            best = nearby[np.argmax(delta[peaks[nearby]])]
            beat = float(peak_times[best])
            snapped += 1
        if not beats or beat - beats[-1] > 0.2:
            beats.append(round(float(beat), 5))
    cuts = [0.0]
    cut_evidence = []
    while duration - cuts[-1] > 19:
        target = cuts[-1] + 15
        candidates = [b for b in beats if 12 < b - cuts[-1] < 17 and duration - b > 4]
        if not candidates:
            raise ValueError("No measured beat near the next cut")
        beat = min(candidates, key=lambda b: abs(b - target))
        frame = round(beat * 24)
        time = frame / 24
        cuts.append(time)
        cut_evidence.append(
            {
                "frame": frame,
                "time": time,
                "measuredBeat": beat,
                "errorMs": round(abs(time - beat) * 1000, 3),
            }
        )
    cuts.append(duration)
    sections = [
        {
            "index": i,
            "start": a,
            "end": b,
            "duration": b - a,
            "startFrame": round(a * 24),
            "endFrame": (
                round(b * 24) if i < len(cuts) - 2 else int(np.ceil(duration * 24))
            ),
            "generationSeconds": float(np.ceil((b - a) * 2) / 2),
        }
        for i, (a, b) in enumerate(zip(cuts, cuts[1:]))
    ]
    envelope = librosa.feature.rms(y=y, frame_length=1024, hop_length=hop)[0]
    payload = {
        "duration": duration,
        "fps": 24,
        "estimatedBpm": float(np.asarray(tempo).flat[0]),
        "medianBeatBpm": float(60 / np.median(np.diff(beats))),
        "beats": beats,
        "trackedBeats": len(coarse),
        "kickRefinedBeats": snapped,
        "cutEvidence": cut_evidence,
        "sections": sections,
        "levelHopSeconds": hop / 22050,
        "levels": np.round(
            envelope / max(float(np.quantile(envelope, 0.97)), 1e-6), 3
        ).tolist(),
    }
    Path(out).write_text(json.dumps(payload, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: payload[k]
                for k in (
                    "duration",
                    "estimatedBpm",
                    "medianBeatBpm",
                    "trackedBeats",
                    "kickRefinedBeats",
                )
            }
        )
    )
    print(
        "Sections",
        [(x["index"], round(x["start"], 3), round(x["duration"], 3)) for x in sections],
    )


if __name__ == "__main__":
    analyze(*sys.argv[1:])
