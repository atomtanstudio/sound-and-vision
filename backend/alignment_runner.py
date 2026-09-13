"""Audio-derived canonical word timings; no proportional/interpolated fallback."""

import hashlib, json, re, sys, traceback
from difflib import SequenceMatcher
from pathlib import Path


def normalize(word):
    return "".join(c for c in word.casefold() if c.isalnum())


def canonical_lines(lyrics):
    return [
        line.strip()
        for line in lyrics.splitlines()
        if line.strip() and not re.fullmatch(r"\[[^\]]+\]", line.strip())
    ]


def reconcile(lyrics, aligned, heard, duration, aligned_indexes=None):
    lines = canonical_lines(lyrics)
    tokens = [word for line in lines for word in line.split()]
    norms = [normalize(w) for w in tokens]

    def matches(evidence):
        mapping = {}
        for block in SequenceMatcher(
            None, norms, [normalize(w["word"]) for w in evidence], autojunk=False
        ).get_matching_blocks():
            for offset in range(block.size):
                mapping[block.a + offset] = evidence[block.b + offset]
        return mapping

    anchors, checks = (
        aligned_indexes if aligned_indexes is not None else matches(aligned)
    ), matches(heard)
    words = []
    for index, token in enumerate(tokens):
        anchor, check = anchors.get(index), checks.get(index)
        start, end, reason = None, None, "No reliable alignment for this word"
        confidence = float(anchor.get("probability", 0)) if anchor else 0
        if anchor and 0 <= anchor["start"] < anchor["end"] <= duration + 0.05:
            start, end = round(anchor["start"], 3), round(
                min(duration, anchor["end"]), 3
            )
            reason = None
            corroborated = (
                check
                and float(check.get("probability", 0)) >= 0.8
                and abs(check["start"] - start) <= 0.25
                and confidence >= 0.1
            )
            if confidence < 0.35 and not corroborated:
                reason = "Low alignment confidence"
            elif end - start > 8:
                reason = "Unusually long word; check the vocal"
            elif not check or float(check.get("probability", 0)) < 0.35:
                reason = "Word not confirmed by independent transcription"
            elif abs(check["start"] - start) > 0.8:
                reason = "Alignment and transcription disagree; check the start"
        words.append(
            {
                "text": token,
                "start": start,
                "end": end,
                "confidence": round(confidence, 3),
                "review": reason,
            }
        )
    cues, offset = [], 0
    for index, line in enumerate(lines):
        count = len(line.split())
        chunk = words[offset : offset + count]
        offset += count
        timed = [w for w in chunk if w["start"] is not None]
        cues.append(
            {
                "id": f"line-{index}",
                "text": line,
                "start": min((w["start"] for w in timed), default=None),
                "end": max((w["end"] for w in timed), default=None),
                "words": chunk,
            }
        )
    # Monotonicity is checked across line boundaries, including repeated choruses.
    previous_end = -1
    for cue in cues:
        for word in cue["words"]:
            if word["start"] is not None:
                if word["start"] < previous_end - 0.05:
                    word["review"] = "Overlapping vocal timing; review this word"
                previous_end = max(previous_end, word["end"])
    return {
        "unmatchedVocalWords": max(0, len(heard) - len(checks)),
        "lyrics": lyrics,
        "duration": duration,
        "cues": cues,
        "reviewCount": sum(bool(w["review"]) for w in words),
        "wordCount": len(words),
        "method": "Demucs vocals + large-v3 recognition anchors + phrase-constrained forced alignment",
        "timingStatus": (
            "audio-aligned-needs-review"
            if any(w["review"] for w in words)
            else "audio-aligned"
        ),
        "automatic": True,
    }


def fill_phrase_gaps(windows, offsets, tokens, duration):
    """Give CTC the canonical text between measured anchors, never interpolated times."""
    result, starts, cursor, previous_end = [], [], 0, 0.0
    for window, offset in zip(
        windows + [{"start": duration, "end": duration, "text": ""}],
        offsets + [len(tokens)],
    ):
        if offset > cursor and 0.08 < window["start"] - previous_end <= 45:
            result.append(
                {
                    "start": previous_end,
                    "end": window["start"],
                    "text": " ".join(tokens[cursor:offset]),
                }
            )
            starts.append(cursor)
        if window["text"]:
            result.append(window)
            starts.append(offset)
        cursor = offset + len(window["text"].split())
        previous_end = window["end"]
    return result, starts


def transcript_draft(heard, duration):
    """Recognition is an editable proposal, never a verified lyric alignment."""
    lines, current, previous_end = [], [], None
    for word in heard:
        text = str(word.get("word", "")).strip()
        if not text:
            continue
        if current and (len(current) >= 9 or (previous_end is not None and word["start"] - previous_end > 0.7)):
            lines.append(" ".join(current)); current = []
        current.append(text)
        previous_end = word["end"]
    if current:
        lines.append(" ".join(current))
    return {"lyrics": "\n".join(lines), "duration": duration, "requiresReview": True,
            "method": "Demucs vocal isolation + Whisper large-v3 transcription",
            "reviewCount": sum(w.get("probability", 0) < 0.65 for w in heard),
            "warning": "Review every line against the song. Singing and instrumental passages can produce incorrect or invented words."}


def main(source, work, lock_path):
    import numpy as np
    import soundfile as sf
    import torch, torchaudio
    from demucs.pretrained import get_model
    from demucs.apply import apply_model
    import stable_whisper

    torch.set_num_threads(8)
    payload = json.loads((work / "input.json").read_text())
    lock = json.loads(lock_path.read_text())
    lyrics = "\n".join(canonical_lines(payload["lyrics"]))
    if not lyrics and payload.get("kind") != "transcription":
        raise ValueError("There are no lyric words to align.")
    progress = work / "phase.json"
    progress.write_text(json.dumps({"phase": "Separating vocals on CPU"}))
    audio, rate = sf.read(source, dtype="float32", always_2d=True)
    duration = len(audio) / rate
    fingerprint = hashlib.sha256(source.read_bytes()).hexdigest()
    cache = work.parent / "audio-cache" / fingerprint
    cache.mkdir(parents=True, exist_ok=True)
    vocals_file = cache / "vocals.wav"
    if not vocals_file.exists():
        model = get_model(lock["demucs"]).cpu().eval()
        waveform = torch.from_numpy(audio.T.copy())
        if waveform.shape[0] == 1:
            waveform = waveform.repeat(2, 1)
        waveform = torchaudio.functional.resample(waveform[:2], rate, model.samplerate)
        ref = waveform.mean(0)
        mean, std = ref.mean(), ref.std().clamp(min=1e-8)
        with torch.inference_mode():
            stems = apply_model(
                model,
                ((waveform - mean) / std)[None],
                device="cpu",
                shifts=0,
                split=True,
                overlap=0.25,
                progress=True,
                num_workers=0,
            )[0]
        vocal = stems[model.sources.index("vocals")] * std + mean
        sf.write(
            cache / "vocals.partial.wav",
            vocal.T.numpy(),
            model.samplerate,
            subtype="PCM_24",
        )
        (cache / "vocals.partial.wav").replace(vocals_file)
        del model, stems, vocal, waveform
    progress.write_text(
        json.dumps({"phase": "Recognizing the isolated vocal to locate sung phrases"})
    )
    model = stable_whisper.load_faster_whisper(
        lock["path"],
        device="cpu",
        compute_type="int8",
        cpu_threads=8,
        local_files_only=True,
    )
    transcript_file = cache / (payload["language"] + "-" + lock["revision"] + ".json")
    if transcript_file.exists():
        heard = json.loads(transcript_file.read_text())
    else:
        segments, info = model.transcribe_original(
            str(vocals_file),
            language=payload["language"],
            beam_size=5,
            word_timestamps=True,
            condition_on_previous_text=False,
            vad_filter=False,
        )
        heard = [
            {
                "word": w.word,
                "start": w.start,
                "end": w.end,
                "probability": w.probability,
            }
            for s in segments
            for w in (s.words or [])
        ]
        temp = transcript_file.with_suffix(".partial")
        temp.write_text(json.dumps(heard))
        temp.replace(transcript_file)
    (work / "transcription.json").write_text(json.dumps(heard))
    if payload.get("kind") == "transcription":
        (work / "result.json").write_text(json.dumps(transcript_draft(heard, duration)))
        return
    lines = canonical_lines(payload["lyrics"])
    tokens = [normalize(w) for line in lines for w in line.split()]
    checks = {}
    for block in SequenceMatcher(
        None, tokens, [normalize(w["word"]) for w in heard], autojunk=False
    ).get_matching_blocks():
        for offset in range(block.size):
            checks[block.a + offset] = heard[block.b + offset]
    windows, line_offsets = [], []
    offset = 0
    for line in lines:
        words = line.split()
        confirmed = [
            checks[i]
            for i in range(offset, offset + len(words))
            if i in checks and checks[i]["probability"] >= 0.35
        ]
        # No voiced anchor means no guessed line window. Keep it unmatched for review.
        if confirmed and len(confirmed) >= max(1, len(words) // 2):
            start, end = min(w["start"] for w in confirmed), max(
                w["end"] for w in confirmed
            )
            # A line mapped across separate repetitions is not a reliable phrase.
            if windows:
                start = max(start, windows[-1]["end"])
            if end > start and end - start <= 20:
                windows.append(
                    {"start": max(0, start), "end": min(duration, end), "text": line}
                )
                line_offsets.append(offset)
        offset += len(words)
    progress.write_text(
        json.dumps(
            {"phase": "Refining word boundaries inside recognized vocal phrases"}
        )
    )
    anchors = {}
    if windows and payload["language"] == "en" and lock.get("englishCTC"):
        from phonetic_alignment import align_english

        del model
        windows, line_offsets = fill_phrase_gaps(
            windows, line_offsets, [w for line in lines for w in line.split()], duration
        )
        anchors = align_english(vocals_file, windows, line_offsets, progress)
    elif windows:
        result = model.align_words(
            str(vocals_file),
            windows,
            language=payload["language"],
            regroup=False,
            suppress_silence=True,
            verbose=False,
        )
        result.save_as_json(str(work / "raw-alignment.json"))
        for offset, window, segment in zip(
            line_offsets, windows, result.to_dict()["segments"]
        ):
            originals = [normalize(w) for w in window["text"].split()]
            words = segment.get("words", [])
            for block in SequenceMatcher(
                None, originals, [normalize(w["word"]) for w in words], autojunk=False
            ).get_matching_blocks():
                for i in range(block.size):
                    anchors[offset + block.a + i] = words[block.b + i]
    output = reconcile(payload["lyrics"], [], heard, duration, anchors)
    if payload["language"] == "en" and lock.get("englishCTC"):
        output["method"] = (
            "Demucs vocals + Whisper large-v3 phrase recognition + wav2vec2 phonetic forced alignment"
        )
    output["modelRevision"] = lock["revision"]
    (work / "result.json").write_text(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    source, work, lock = map(Path, sys.argv[1:])
    try:
        main(source, work, lock)
    except Exception as error:
        (work / "failure.json").write_text(json.dumps({"message": str(error)[:1200]}))
        traceback.print_exc()
        raise SystemExit(1)
