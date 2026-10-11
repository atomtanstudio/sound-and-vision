"""Times a take's lyrics against its vocals, and measures its tempo, beats and energy.

Runs in the sv-analysis image (torch and torchaudio), called by analyze.py.
Lyrics: wav2vec2 (WAV2VEC2_ASR_LARGE_LV60K_960H, English characters, weights already in the torch
hub cache) turns the separated vocals into per-frame character probabilities; CTC forced alignment
(torchaudio.functional.forced_align) places the known lyrics on them. Every word gets a start, an
end and a score (the mean probability of its characters); lines and sections take their words'
extent. Tempo, beats and energy come from the full mix: an onset envelope (spectral flux of a mel
spectrogram), its autocorrelation for the tempo, and the best-fitting beat grid.

Lines heard elsewhere (spec "heard": [{"text", "start", "end"}, ...], or a path to words_listen.py's JSON) anchor the
alignment: each lyric line is matched, in order, to the heard line it reads like (lines with no match fill the gap
between their neighbours); lines that run into each other form a block, and each block is placed on its own, only near
where it was heard. Without anchors one forced alignment covers the whole take, which is right for a song sung from end
to end but drags a few lines spread over a long song to the wrong places.

Usage: python analysis_align.py <spec.json>
The spec: {"mix": path, "vocals": path, "sections": [{"id", "label", "lines": [...]}...], "out": path,
           "device": "cuda"|"cpu", "heard": optional}. Sections come in sung order, repeats resolved.
Prints JSON lines: {"event": "stage"|"progress"|"done"|"error", ...}; writes the timing map to "out".
"""

from __future__ import annotations

import difflib
import json
import math
import re
import sys
import time

import soundfile as sf
import torch
import torchaudio
import torchaudio.functional as F

WINDOW_S = 20.0  # the model hears the vocals 20 s at a time (its attention grows with the square of the length)
CONTEXT_S = 1.0  # plus a second each side, dropped from the result
HOP_S = 0.05  # the energy curve's step


def emit(**event) -> None:
    print(json.dumps(event), flush=True)


def load_mono(path: str, rate: int) -> torch.Tensor:
    audio, sr = sf.read(path, dtype="float32", always_2d=True)
    wave = torch.from_numpy(audio.T).mean(0, keepdim=True)
    if sr != rate:
        wave = torchaudio.functional.resample(wave, sr, rate)
    return wave


# ------------------------------------------------------------------ lyrics
def normalize(word: str) -> str:
    return re.sub(r"[^A-Z']", "", word.upper().replace("’", "'"))


def emissions(wave: torch.Tensor, model: torch.nn.Module, rate: int, device: str) -> tuple[torch.Tensor, float]:
    """Log-probabilities for the whole take, (frames, labels), and seconds per frame."""
    step, ctx = int(WINDOW_S * rate), int(CONTEXT_S * rate)
    n = wave.shape[-1]
    parts: list[torch.Tensor] = []
    frame_s = None
    starts = list(range(0, n, step))
    for i, start in enumerate(starts):
        a, b = max(0, start - ctx), min(n, start + step + ctx)
        with torch.inference_mode():
            out, _ = model(wave[:, a:b].to(device))
        lp = torch.log_softmax(out[0].float(), dim=-1).cpu()
        per = (b - a) / lp.shape[0]  # samples per frame (320 at 16 kHz)
        frame_s = per / rate
        lo = round((start - a) / per)
        hi = lo + round((min(start + step, n) - start) / per)
        parts.append(lp[lo:hi])
        emit(event="progress", stage="listen", done=i + 1, total=len(starts))
    return torch.cat(parts), frame_s


def _place(words: list[dict], logp: torch.Tensor, frame_s: float, index: dict, offset_s: float = 0.0) -> list[dict]:
    """Forced alignment of these words on these frames (which start offset_s into the take)."""
    targets: list[int] = []
    for k, w in enumerate(words):
        if k:
            targets.append(index["|"])
        targets.extend(index[c] for c in w["token"] if c in index)
    tgt = torch.tensor([targets], dtype=torch.int32)
    ali, scores = F.forced_align(logp[None], tgt, blank=0)
    spans = F.merge_tokens(ali[0], scores[0].exp())
    # Split the character spans into words at each "|".
    sep = index["|"]
    groups, cur = [], []
    for sp in spans:
        if sp.token == sep:
            if cur:
                groups.append(cur)
            cur = []
        else:
            cur.append(sp)
    if cur:
        groups.append(cur)
    out_words = []
    for w, g in zip(words, groups):
        start, end = offset_s + g[0].start * frame_s, offset_s + g[-1].end * frame_s
        score = sum(float(sp.score) for sp in g) / len(g)
        # A word held far longer than singing allows swallowed something the lyrics don't have (an
        # ad-lib, a repeat, the outro): it keeps its start, gets a sung length, and is marked unsure.
        longest = max(1.5, 0.35 * len(w["token"]))
        stretched = end - start > longest
        if stretched:
            end, score = start + longest, score * 0.5
        out_words.append({
            "section": w["section"], "line": w["line"], "text": w["text"],
            "start": round(start, 3), "end": round(end, 3), "score": round(score, 3),
            **({"stretched": True} if stretched else {}),
        })
    return out_words


def _letters(text: str) -> str:
    return "".join(normalize(w) for w in text.split()).lower()


BLOCK_GAP_S = 2.5  # heard lines closer than this are sung as one stretch and placed together
BLOCK_PAD_S = 1.0  # how far outside where a stretch was heard its words may land


def windows(flat: list[tuple[int, int, str]], heard: list[dict], duration: float, pad: float = 0.0) -> list[tuple[float, float]]:
    """A time window per lyric line from the heard lines: matched in order (a heard line may be skipped, a lyric line
    may go unmatched), each matched line within its heard line ± pad, each unmatched one between its neighbours."""
    found: list[tuple[float, float] | None] = []
    j = 0
    for _, _, text in flat:
        want = _letters(text)
        best, best_k = 0.0, None
        for k in range(j, min(len(heard), j + 6)):
            r = difflib.SequenceMatcher(None, want, _letters(heard[k]["text"])).ratio()
            if r > best:
                best, best_k = r, k
        if best_k is not None and best >= 0.45:
            h = heard[best_k]
            found.append((max(0.0, h["start"] - pad), min(duration, h["end"] + pad)))
            j = best_k + 1
        else:
            found.append(None)
    out: list[tuple[float, float]] = []
    for i, w in enumerate(found):
        if w:
            out.append(w)
            continue
        before = next((found[k][1] for k in range(i - 1, -1, -1) if found[k]), 0.0)
        after = next((found[k][0] for k in range(i + 1, len(found)) if found[k]), duration)
        out.append((before, max(after, before + 2.0)))
    return out


def align(sections: list[dict], logp: torch.Tensor, frame_s: float, labels: tuple[str, ...], heard: list[dict] | None = None) -> tuple[list, list, list]:
    index = {c: i for i, c in enumerate(labels)}
    words: list[dict] = []  # every sung word, in order, with where it belongs
    flat: list[tuple[int, int, str]] = []
    for si, s in enumerate(sections):
        for li, line in enumerate(s.get("lines") or []):
            flat.append((si, li, line))
            for w in line.split():
                token = normalize(w)
                if token:
                    words.append({"section": si, "line": li, "text": w, "token": token})
    if not words:
        return [], [], []
    if heard:
        duration = logp.shape[0] * frame_s
        blocks: list[dict] = []
        for i, (a, b) in enumerate(windows(flat, heard, duration)):
            if blocks and a - blocks[-1]["b"] < BLOCK_GAP_S:
                blocks[-1]["b"] = max(blocks[-1]["b"], b)
                blocks[-1]["lines"].append(flat[i][:2])
            else:
                blocks.append({"a": a, "b": b, "lines": [flat[i][:2]]})
        out_words = []
        for k, bl in enumerate(blocks):
            a = max(bl["a"] - BLOCK_PAD_S, blocks[k - 1]["b"] if k else 0.0)  # never into the stretch before or after
            b = min(bl["b"] + BLOCK_PAD_S, blocks[k + 1]["a"] if k + 1 < len(blocks) else duration)
            ws = [w for w in words if (w["section"], w["line"]) in bl["lines"]]
            if not ws:
                continue
            fa, fb = int(a / frame_s), min(logp.shape[0], int(b / frame_s) + 1)
            need = sum(len(w["token"]) for w in ws) * 2 + len(ws)
            if fb - fa < need:  # too short a window for the letters: widen it around its middle
                mid = (fa + fb) // 2
                fa, fb = max(0, mid - need), min(logp.shape[0], mid + need)
            out_words += _place(ws, logp[fa:fb], frame_s, index, fa * frame_s)
    else:
        out_words = _place(words, logp, frame_s, index)
    lines, secs = [], []
    for si, s in enumerate(sections):
        in_sec = [w for w in out_words if w["section"] == si]
        for li, text in enumerate(s.get("lines") or []):
            ws = [w for w in in_sec if w["line"] == li]
            if ws:
                lines.append({"section": si, "line": li, "text": text, "start": ws[0]["start"], "end": ws[-1]["end"],
                              "score": round(sum(w["score"] for w in ws) / len(ws), 3)})
        if in_sec:
            secs.append({"section": si, "id": s.get("id"), "label": s.get("label"), "start": in_sec[0]["start"], "end": in_sec[-1]["end"]})
    return secs, lines, out_words


def hearing(lines: list[dict], logp: torch.Tensor, frame_s: float, labels: tuple[str, ...]) -> None:
    """What the model hears in each line, without being told the lyrics (greedy CTC), and how closely
    it matches the line as written (0–1, by characters): a low match flags a line that may not be sung
    as written (a skipped, changed or slurred word). Singing is heard loosely, so this is a hint to
    listen, not a transcription to trust."""
    blank = 0
    for ln in lines:
        a = max(0, int(ln["start"] / frame_s) - 5)
        b = min(logp.shape[0], int(ln["end"] / frame_s) + 5)
        ids = torch.argmax(logp[a:b], dim=-1).tolist()
        out, prev = [], None
        for i in ids:
            if i != prev and i != blank:
                out.append(labels[i])
            prev = i
        heard = re.sub(r"\|+", " ", "".join(out)).strip().lower()
        want = " ".join(normalize(w) for w in ln["text"].split() if normalize(w)).lower()
        ln["heard"] = heard
        ln["match"] = round(difflib.SequenceMatcher(None, want.replace(" ", ""), heard.replace(" ", "")).ratio(), 3)


# ------------------------------------------------------------------ tempo, beats, energy
def rhythm(mix: torch.Tensor, rate: int) -> dict:
    hop = 512
    mel = torchaudio.transforms.MelSpectrogram(rate, n_fft=2048, hop_length=hop, n_mels=64)(mix)[0]
    db = torch.log1p(mel * 1000)
    flux = torch.clamp(db[:, 1:] - db[:, :-1], min=0).sum(0)
    flux = flux - flux.mean()
    env = torch.clamp(flux, min=0)
    fps = rate / hop
    # Tempo: the autocorrelation peak between 70 and 180 BPM, weighted gently toward 120.
    ac = torch.fft.irfft(torch.fft.rfft(env, n=2 * env.numel()).abs() ** 2)[: env.numel()]
    lags = torch.arange(env.numel())
    lo, hi = int(fps * 60 / 180), int(fps * 60 / 70)
    bpm = 60 * fps / lags[lo:hi].float()
    weight = torch.exp(-0.5 * (torch.log2(bpm / 120) / 0.9) ** 2)
    best = int(torch.argmax(ac[lo:hi] * weight)) + lo
    # The peak between frames (a parabola through it and its neighbours), so the grid doesn't drift.
    y0, y1, y2 = (float(ac[best + d]) for d in (-1, 0, 1))
    period = best + (0.5 * (y0 - y2) / (y0 - 2 * y1 + y2) if (y0 - 2 * y1 + y2) != 0 else 0.0)
    # Beats: the phase whose grid collects the most onset energy.
    count = int((env.numel() - 1) / period)
    grid = lambda ph: torch.clamp(torch.round(ph + period * torch.arange(count)).long(), max=env.numel() - 1)
    phase = max(range(int(period)), key=lambda ph: float(env[grid(ph)].sum()))
    beats = [round((phase + k * period) / fps, 3) for k in range(count) if phase + k * period < env.numel()]
    # Energy: RMS every 50 ms, scaled to the take's own loudest moment.
    step = int(HOP_S * rate)
    frames = mix[0, : (mix.shape[-1] // step) * step].reshape(-1, step)
    rms = frames.pow(2).mean(1).sqrt()
    rms = rms / (rms.max() + 1e-9)
    return {"tempo": round(60 * fps / period, 1), "beats": beats, "energy": {"hop": HOP_S, "values": [round(float(v), 3) for v in rms]}}


def main() -> None:
    spec = json.loads(open(sys.argv[1]).read())
    started = time.monotonic()
    device = spec.get("device") or ("cuda" if torch.cuda.is_available() else "cpu")
    try:
        emit(event="stage", stage="listen", message="Reading the vocals")
        bundle = torchaudio.pipelines.WAV2VEC2_ASR_LARGE_LV60K_960H
        model = bundle.get_model().to(device).eval()
        vocals = load_mono(spec["vocals"], bundle.sample_rate)
        logp, frame_s = emissions(vocals, model, bundle.sample_rate, device)
        del model
        if device == "cuda":
            torch.cuda.empty_cache()
        emit(event="stage", stage="align", message="Placing the words")
        heard = spec.get("heard")
        if isinstance(heard, str):
            try:
                heard = json.loads(open(heard).read()).get("lines")
            except (OSError, ValueError):
                heard = None
        sections, lines, words = align(spec["sections"], logp, frame_s, bundle.get_labels(), heard or None)
        hearing(lines, logp, frame_s, bundle.get_labels())
        emit(event="stage", stage="rhythm", message="Finding the beat")
        mix = load_mono(spec["mix"], 22050)
        timing = {
            "version": 1,
            "duration": round(mix.shape[-1] / 22050, 3),
            "method": {"lyrics": "wav2vec2 large (LV60K, 960 h) CTC forced alignment on Demucs v4 vocals"
                                 + (f", each line near where {spec.get('heardFrom') or 'Whisper heard it'}" if heard else ""), "rhythm": "mel spectral flux, autocorrelation"},
            **rhythm(mix, 22050),
            "sections": sections,
            "lines": lines,
            "words": words,
        }
        with open(spec["out"], "w") as f:
            json.dump(timing, f)
        emit(event="done", seconds=round(time.monotonic() - started, 1), words=len(words), lines=len(lines), tempo=timing["tempo"])
    except Exception as exc:  # the scheduler reads this as the job's reason
        emit(event="error", message=f"{type(exc).__name__}: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
