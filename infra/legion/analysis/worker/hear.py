"""Hearing the words of a song that came without its lyrics (your own song, uploaded): faster-whisper large-v3 on
the vocal stem. Ported from the old app (soundandvision.old/server/workers/words_listen.py).

Speech recognition on singing mishears and invents, so lines it isn't sure of, lines it heard in silence and the stock
phrases it makes up from noise are left out. (This image's CTranslate2 wants CUDA 12's cuBLAS and the image has CUDA 13,
so it runs on the CPU: under a minute for a 4½-minute song, measured 2026-10-09.) The result is a draft: the aligner then times it to the vocal, and the
person can correct the words on the song page.
"""

from __future__ import annotations

import ctypes
import glob
import math
import os
import re
import site

# what Whisper says when it hears music and no words (from captioned video in its training data)
INVENTED = re.compile(r"thank(s| you) for (watching|listening)|subtitles? (by|from)|subscribe|amara\.org|transcribed by|"
                      r"^\W*(music|instrumental|applause|laughter)\W*$|♪", re.I)
GAP, SHORT_GAP, MAX_WORDS = 1.2, 0.45, 12  # silence that ends a line (any length / four words or more); a line's longest
STANZA_GAP = 3.5  # silence between lines that starts a new part


def cuda_libs() -> None:
    """CTranslate2 looks for cuBLAS and cuDNN on the library path; pip puts them inside the environment."""
    for base in site.getsitepackages():
        for pattern in ("nvidia/cublas/lib/libcublasLt.so.*", "nvidia/cublas/lib/libcublas.so.*", "nvidia/cudnn/lib/libcudnn*.so.*"):
            for f in sorted(glob.glob(os.path.join(base, pattern))):
                try:
                    ctypes.CDLL(f, mode=ctypes.RTLD_GLOBAL)
                except OSError:
                    pass


def _transcribe(model_dir: str, audio: str, device: str, language: str | None, emit):
    from faster_whisper import WhisperModel
    model = WhisperModel(model_dir, device=device, compute_type="float16" if device == "cuda" else "int8")
    segments, info = model.transcribe(
        audio, language=language, language_detection_segments=4, language_detection_threshold=0.6,
        beam_size=5, vad_filter=True, vad_parameters={"min_silence_duration_ms": 500},
        condition_on_previous_text=False, no_speech_threshold=0.6, log_prob_threshold=-1.0,
        compression_ratio_threshold=2.4, temperature=[0.0, 0.2, 0.4], word_timestamps=True)
    out = []
    for s in segments:  # the work happens here, segment by segment
        emit(event="progress", stage="listen", done=round(s.end, 1), total=round(info.duration, 1))
        out.append(s)
    return out, info


def _line(words: list) -> dict:
    text = " ".join("".join(w.word for w in words).split())
    sure = sum(w.probability for w in words) / len(words)
    return {"text": text, "start": round(words[0].start, 2), "end": round(words[-1].end, 2), "sure": round(sure, 2)}


def hear(model_dir: str, audio: str, emit, language: str | None = None) -> dict:
    """{"language", "lines": [{text, start, end, sure}], "dropped"} for the vocals in `audio`."""
    cuda_libs()
    device = "cuda"
    try:
        segments, info = _transcribe(model_dir, audio, device, language, emit)
    except Exception:  # noqa: BLE001  no usable CUDA: slower on the CPU, same words
        device = "cpu"
        segments, info = _transcribe(model_dir, audio, device, language, emit)
    # Telling the language from singing is shaky: an unsure guess other than English is checked by listening again
    # as English, and the more confident of the two is kept.
    if not language and info.language != "en" and info.language_probability < 0.9:
        en_segments, en_info = _transcribe(model_dir, audio, device, "en", emit)
        mean = lambda segs: sum(s.avg_logprob for s in segs) / len(segs) if segs else -9.0  # noqa: E731
        if mean(en_segments) >= mean(segments) - 0.1:
            segments, info = en_segments, en_info
    lines, dropped = [], 0
    for s in segments:
        text = " ".join(s.text.split())
        if not text:
            continue
        # On singing, Whisper's "no speech" score runs high (0.65-0.87 measured on sung lines it heard well): like
        # Whisper's own rule, it only drops a segment when the words are unsure too
        if (s.no_speech_prob > 0.6 and s.avg_logprob < -1.0) or s.avg_logprob < -1.2 or s.compression_ratio > 2.4 \
                or INVENTED.search(text):
            dropped += 1
            continue
        # a stretch of singing comes back as one segment: break it into sung lines where the voice pauses
        words = [w for w in (s.words or []) if w.word.strip()]
        if not words:
            lines.append({"text": text, "start": round(s.start, 2), "end": round(s.end, 2), "sure": round(math.exp(s.avg_logprob), 2)})
            continue
        group = [words[0]]
        for w in words[1:]:
            gap = w.start - group[-1].end
            if gap > GAP or (gap > SHORT_GAP and len(group) >= 4) or len(group) >= MAX_WORDS:
                lines.append(_line(group))
                group = []
            group.append(w)
        lines.append(_line(group))
    return {"language": info.language, "languageProbability": round(info.language_probability, 2), "lines": lines,
            "dropped": dropped}


def parts(lines: list[dict]) -> list[dict]:
    """Heard lines as the aligner's sections: a new part wherever the voice rests for a while."""
    out: list[dict] = []
    for ln in lines:
        if not out or ln["start"] - out[-1]["end"] > STANZA_GAP:
            out.append({"id": f"s{len(out)}", "label": f"Part {len(out) + 1}", "lines": [], "end": ln["end"]})
        out[-1]["lines"].append(ln["text"])
        out[-1]["end"] = ln["end"]
    return [{k: v for k, v in s.items() if k != "end"} for s in out]
