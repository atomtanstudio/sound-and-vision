import numpy as np

from .audio_cleanup import trim_quiet_tail


def tone(seconds, amplitude, rate=1000):
    t = np.arange(round(seconds * rate)) / rate
    mono = amplitude * np.sin(2 * np.pi * 7 * t)
    return np.column_stack((mono, mono))


def test_trims_a_sustained_quiet_continuation_and_fades_it():
    audio = np.concatenate((tone(40, 0.4), tone(20, 0.01)))
    result, info = trim_quiet_tail(audio, 1000)

    assert info["trimmed"] is True
    assert 41.5 <= info["result_seconds"] <= 44
    assert 16 <= info["trimmed_seconds"] <= 18
    assert np.max(np.abs(result[-1])) < 1e-8


def test_keeps_a_short_quiet_outro():
    audio = np.concatenate((tone(40, 0.4), tone(5, 0.01)))
    result, info = trim_quiet_tail(audio, 1000)

    assert info["trimmed"] is False
    assert len(result) == len(audio)


def test_does_not_trim_when_the_tail_recovers():
    audio = np.concatenate((tone(40, 0.4), tone(12, 0.01), tone(12, 0.35)))
    result, info = trim_quiet_tail(audio, 1000)

    assert info["trimmed"] is False
    assert len(result) == len(audio)
