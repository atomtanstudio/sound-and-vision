"""Listen to a training set with MOSS-Music and write the sidecars FL's trainer reads beside each
recording: <name>.caption.txt (how it sounds) and <name>.lyrics.txt (the words; empty when it is
instrumental). The trainer prefixes the influence's trigger to every caption. A song whose lyrics sidecar is
already there (its published words, from an .lrc or a tag) keeps it and is only described.

Lyrics go only to their sidecar file: this script never prints them, and captions are scrubbed of
anything quoted (MOSS likes to quote a line or two when it describes a song).

    venv/bin/python listen.py FOLDER [--only track-001 ...]

One JSON line per song on stdout: {"i", "n", "name", "seconds", "captionChars", "lyricLines", "instrumental", "stuck"}.
"instrumental" means no words were found: the app decides afterwards whether the song really is instrumental. A
transcription that went round and round on a word or two is thrown away ("stuck").
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import torch

# MOSS-Music's code (a checkout of its repo) and its model folder: SV_MOSS_CODE and SV_MOSS_MODEL, or beside this venv
HERE = Path(sys.prefix).parent  # the venv is <listen>/venv
sys.path.insert(0, os.environ.get("SV_MOSS_CODE") or str(HERE / "MOSS-Music"))
from src.modeling_moss_music import MossMusicModel  # noqa: E402
from src.processing_moss_music import MossMusicProcessor  # noqa: E402

MODEL = os.environ.get("SV_MOSS_MODEL") or str(HERE / "models" / "MOSS-Music-8B-Instruct")
CAPTION = ("Describe how this recording sounds, in two or three sentences, as a caption for training a music "
           "generator: the genre and sub-genre, the era it evokes, the main instruments, the production and mix, the "
           "lead vocal (gender, timbre, delivery and effects) or that it is instrumental, the mood, and the tempo in BPM. "
           "Do not quote, paraphrase or mention any lyrics, and do not name the artist or the song.")
LYRICS = "Transcribe the lyrics of this song."
MIN_WORDS = 12


def load_audio(path: Path, rate: int) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(rate), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def ask(model, proc, audio, prompt: str, most: int) -> str:
    inputs = proc(text=prompt, audios=[audio], return_tensors="pt").to(model.device)
    if inputs.get("audio_data") is not None:
        inputs["audio_data"] = inputs["audio_data"].to(model.dtype)
    inputs["audio_input_mask"] = inputs["input_ids"] == proc.audio_token_id
    with torch.no_grad():
        ids = model.generate(**inputs, max_new_tokens=most, do_sample=True, temperature=0.6, top_p=0.8, top_k=50,
                             use_cache=True)
    return proc.decode(ids[0, inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()


def scrub_caption(text: str) -> str:
    """Drop quoted words and any sentence that talks about the words, then tidy."""
    text = re.sub(r"[\"“”][^\"“”]{0,400}[\"“”]", "", text)
    text = re.sub(r"(?<!\w)'[^']{3,200}'(?!\w)", "", text)
    keep = [s for s in re.split(r"(?<=[.!?])\s+", text)
            if s.strip() and not re.search(r"\blyric|\bsings? about|\bthe words\b|\bline[s]? like\b|\btitle", s, re.I)]
    out = " ".join(" ".join(keep).split())
    return re.sub(r"\s+([,.])", r"\1", out)[:700]


def tidy_lyrics(text: str) -> str:
    """One sung line per line: time markers, headings and notes removed."""
    lines = []
    for raw in text.splitlines():
        line = re.sub(r"\[?\(?\d{1,2}:\d{2}(?:\.\d+)?\)?\]?", "", raw)
        line = re.sub(r"^\s*(lyrics|transcription)\s*:?\s*$", "", line, flags=re.I)
        line = re.sub(r"^\s*\[(?:[^\]]*)\]\s*$", "", line)
        line = " ".join(line.split())
        if line:
            lines.append(line)
    return "\n".join(lines)


def stuck(text: str) -> bool:
    """A transcription that went round and round on a word or two (MOSS does on shouted or distorted singing): not the
    song's words."""
    words = [w.lower().strip(",.!?;:'\"") for w in text.split()]
    if len(words) < 20:
        return False
    unique = len(set(words)) / len(words)
    return unique < 0.1 or (len(words) > 900 and unique < 0.25)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    files = sorted(p for p in a.folder.iterdir() if p.suffix == ".flac" and (not a.only or p.stem in a.only))
    t0 = time.time()
    model = MossMusicModel.from_pretrained(MODEL, trust_remote_code=True, dtype="auto", device_map="cuda:0").eval()
    proc = MossMusicProcessor.from_pretrained(MODEL, trust_remote_code=True, enable_time_marker=False)
    print(json.dumps({"loaded": round(time.time() - t0, 1)}), flush=True)
    for i, f in enumerate(files, 1):
        t = time.time()
        audio = load_audio(f, proc.config.mel_sr)
        caption = scrub_caption(ask(model, proc, audio, CAPTION, 400))
        side = f.with_suffix(".lyrics.txt")
        published = side.exists() and len(side.read_text(encoding="utf-8").split()) >= MIN_WORDS
        lyrics = side.read_text(encoding="utf-8").strip() if published else tidy_lyrics(ask(model, proc, audio, LYRICS, 1500))
        went_round = not published and stuck(lyrics)
        if went_round:
            lyrics = ""
        instrumental = len(lyrics.split()) < MIN_WORDS
        f.with_suffix(".caption.txt").write_text(caption + "\n", encoding="utf-8")
        if not published:
            side.write_text("" if instrumental else lyrics + "\n", encoding="utf-8")
        print(json.dumps({"i": i, "n": len(files), "name": f.stem, "seconds": round(time.time() - t, 1),
                          "captionChars": len(caption), "lyricLines": 0 if instrumental else lyrics.count("\n") + 1,
                          "instrumental": instrumental, "published": published, "stuck": went_round}), flush=True)


if __name__ == "__main__":
    main()
