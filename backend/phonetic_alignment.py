"""Pinned TorchAudio 2.8 CTC word boundaries inside recognized vocal phrases."""


def align_english(vocals_file, windows, offsets, progress):
    import json, re
    import soundfile as sf
    import torch, torchaudio

    bundle = torchaudio.pipelines.WAV2VEC2_ASR_LARGE_LV60K_960H
    model = bundle.get_model().cpu().eval()
    labels = {label: i for i, label in enumerate(bundle.get_labels())}
    samples, rate = sf.read(vocals_file, dtype="float32", always_2d=True)
    audio = torchaudio.functional.resample(
        torch.from_numpy(samples.mean(1)), rate, bundle.sample_rate
    )
    anchors = {}
    for number, (window, offset) in enumerate(zip(windows, offsets)):
        progress.write_text(
            json.dumps(
                {
                    "phase": f"Aligning vocal sounds · phrase {number+1} of {len(windows)}"
                }
            )
        )
        words = window["text"].split()
        cleaned = [re.sub(r"[^A-Z']", "", w.upper().replace("’", "'")) for w in words]
        # Never silently turn unsupported text into an unrelated pronounceable word.
        if any(
            not w
            or any(c.isdigit() for c in raw)
            or any(c.isalpha() and not c.isascii() for c in raw)
            for w, raw in zip(cleaned, words)
        ):
            continue
        text = "|".join(cleaned)
        target = torch.tensor([[labels[c] for c in text]], dtype=torch.int32)
        start = max(0, window["start"] - 0.25)
        end = min(len(audio) / bundle.sample_rate, window["end"] + 0.25)
        piece = audio[
            round(start * bundle.sample_rate) : round(end * bundle.sample_rate)
        ]
        if len(piece) < 400:
            continue
        with torch.inference_mode():
            emissions, _ = model(piece[None])
            logp = emissions.log_softmax(-1)
            try:
                path, scores = torchaudio.functional.forced_align(logp, target, blank=0)
            except RuntimeError:
                continue
            spans = torchaudio.functional.merge_tokens(
                path[0], scores[0].exp(), blank=0
            )
        if len(spans) != len(text):
            continue
        ratio = len(piece) / bundle.sample_rate / emissions.shape[1]
        cursor = 0
        for i, word in enumerate(cleaned):
            parts = spans[cursor : cursor + len(word)]
            cursor += len(word) + 1
            size = sum(p.end - p.start for p in parts)
            confidence = sum(p.score * (p.end - p.start) for p in parts) / max(1, size)
            anchors[offset + i] = {
                "word": words[i],
                "start": start + parts[0].start * ratio,
                "end": start + parts[-1].end * ratio,
                "probability": confidence,
            }
    return anchors
