"""Small, conservative fixes for artifacts at the end of generated songs."""

from __future__ import annotations

import math

import numpy as np


def trim_quiet_tail(
    audio: np.ndarray,
    sample_rate: int,
    *,
    window_seconds: float = 5.0,
    minimum_tail_seconds: float = 10.0,
    keep_seconds: float = 2.0,
    threshold_ratio: float = 0.18,
) -> tuple[np.ndarray, dict[str, float | int | str | bool]]:
    """Remove a sustained low-energy continuation after a sharp drop.

    YuE2 can emit its end token while the acoustic model continues a very quiet
    repeated texture. A short low-energy outro is valid, so this only trims a
    suffix of at least ``minimum_tail_seconds`` when every smoothed window in
    that suffix stays far below the song's robust upper-level reference.
    """

    if (
        not isinstance(audio, np.ndarray)
        or audio.ndim != 2
        or audio.shape[0] == 0
        or audio.shape[1] < 1
        or not isinstance(sample_rate, int)
        or sample_rate < 1
        or not math.isfinite(window_seconds)
        or window_seconds <= 0
        or not math.isfinite(minimum_tail_seconds)
        or minimum_tail_seconds <= 0
        or not math.isfinite(keep_seconds)
        or keep_seconds < 0
    ):
        return audio, {"method": "sustained-low-energy-tail-v1", "trimmed": False}

    window = max(1, round(sample_rate * window_seconds))
    energies = np.asarray(
        [
            float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))
            for start in range(0, len(audio), window)
            if len(chunk := audio[start : start + window])
        ],
        dtype=np.float64,
    )
    minimum_windows = max(2, math.ceil(minimum_tail_seconds / window_seconds))
    if len(energies) <= minimum_windows:
        return audio, {"method": "sustained-low-energy-tail-v1", "trimmed": False}

    # The 75th percentile remains stable when the song has quiet verses or a
    # naturally soft outro. The floor avoids trimming a genuinely quiet song.
    reference = float(np.percentile(energies, 75))
    threshold = max(0.015, reference * threshold_ratio)
    candidate = None
    for index in range(1, len(energies) - minimum_windows + 1):
        if energies[index] >= threshold or energies[index - 1] < threshold * 2:
            continue
        tail = energies[index:]
        # Permit small level fluctuations in the tail, but reject a later
        # musical recovery. The previous-window test requires a real drop.
        if len(tail) >= minimum_windows and float(np.max(tail)) <= threshold * 1.5:
            candidate = index
            break
    if candidate is None:
        return audio, {
            "method": "sustained-low-energy-tail-v1",
            "trimmed": False,
            "reference_rms": reference,
            "threshold_rms": threshold,
        }

    trim_at = min(len(audio), candidate * window + round(keep_seconds * sample_rate))
    if trim_at <= 0 or trim_at >= len(audio):
        return audio, {
            "method": "sustained-low-energy-tail-v1",
            "trimmed": False,
            "reference_rms": reference,
            "threshold_rms": threshold,
        }

    result = audio[:trim_at].copy()
    fade = min(round(1.5 * sample_rate), len(result))
    if fade > 1:
        result[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float64)[:, None]
    return result, {
        "method": "sustained-low-energy-tail-v1",
        "trimmed": True,
        "start_seconds": candidate * window / sample_rate,
        "original_seconds": len(audio) / sample_rate,
        "result_seconds": len(result) / sample_rate,
        "trimmed_seconds": (len(audio) - len(result)) / sample_rate,
        "reference_rms": reference,
        "threshold_rms": threshold,
    }
