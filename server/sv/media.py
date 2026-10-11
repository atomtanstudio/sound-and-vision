"""Audio files for the browser: a lossless master (FLAC), an AAC copy for playing, and waveform
peaks. Peaks are min/max pairs at 100 per second (int8), from which the interface draws any zoom
by taking the true min and max over each pixel's range."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

PEAK_RATE = 100  # pairs per second


def duration(path: Path, ffmpeg: str = "ffmpeg") -> float:
    probe = ffmpeg.replace("ffmpeg", "ffprobe") if ffmpeg.endswith("ffmpeg") else "ffprobe"
    out = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip()
    return round(float(out), 3)


def to_m4a(src: Path, dest: Path, ffmpeg: str = "ffmpeg") -> Path:
    subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(src), "-map", "0:a:0", "-vn", "-c:a", "aac", "-b:a", "256k",
                    "-movflags", "+faststart", str(dest)], check=True, capture_output=True)
    return dest


def peaks(src: Path, dest: Path, ffmpeg: str = "ffmpeg") -> Path:
    rate = 8000
    raw = subprocess.run([ffmpeg, "-v", "error", "-i", str(src), "-map", "0:a:0", "-ac", "1", "-ar", str(rate),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype=np.float32)
    hop = rate // PEAK_RATE
    n = len(x) // hop
    x = x[: n * hop].reshape(n, hop)
    lo = np.clip(np.round(x.min(axis=1) * 127), -127, 127).astype(int)
    hi = np.clip(np.round(x.max(axis=1) * 127), -127, 127).astype(int)
    # loudness (RMS) beside the peaks: a mastered song's peaks fill the frame, its RMS shows the shape
    rms = np.clip(np.round(np.sqrt((x.astype(np.float64) ** 2).mean(axis=1)) * 127 * 1.414), 0, 127).astype(int)
    dest.write_text(json.dumps({"rate": PEAK_RATE, "min": lo.tolist(), "max": hi.tolist(), "rms": rms.tolist()},
                               separators=(",", ":")))
    return dest


def to_flac(src: Path, dest: Path, ffmpeg: str = "ffmpeg") -> Path:
    """Any audio file (or a video's sound) as the app's master: FLAC, 44.1 kHz, stereo."""
    subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(src), "-map", "0:a:0", "-vn", "-ac", "2", "-ar", "44100",
                    "-sample_fmt", "s16", "-c:a", "flac", str(dest)], check=True, capture_output=True)
    return dest


def tags(path: Path, ffmpeg: str = "ffmpeg") -> dict[str, str]:
    """The file's own tags (title, artist, album, lyrics …), keys in lower case; {} when it has none."""
    probe = ffmpeg.replace("ffmpeg", "ffprobe") if ffmpeg.endswith("ffmpeg") else "ffprobe"
    out = subprocess.run([probe, "-v", "error", "-show_entries", "format_tags:stream_tags", "-of", "json", str(path)],
                         capture_output=True, text=True)
    try:
        data = json.loads(out.stdout or "{}")
    except ValueError:
        return {}
    found: dict[str, str] = {}
    for block in [data.get("format") or {}, *(data.get("streams") or [])]:
        for k, v in (block.get("tags") or {}).items():
            found.setdefault(k.lower(), str(v))
    return found


def artwork(src: Path, dest: Path, ffmpeg: str = "ffmpeg") -> Path | None:
    """The picture embedded in the file (an MP3's or M4A's cover art), or None."""
    r = subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(src), "-map", "0:v:0", "-frames:v", "1", "-an", str(dest)],
                       capture_output=True)
    return dest if r.returncode == 0 and dest.exists() and dest.stat().st_size > 1000 else None
