"""Stems for one song, on the GPU, in two passes:

1. MelBand RoFormer (Kimberley Jensen, vocals SDR 12.6): vocals + the rest ("instrumental").
2. Demucs v4 htdemucs_6s on the rest (already vocal-free): drums, bass, guitar, piano, other.
   Its own vocal output is leftover bleed and is dropped.

Measured on Rapture (3:52): 7.7 s + 11.0 s. Used by analyze.py, or alone:

    python stems.py SONG OUT_DIR [--models DIR]
"""

import argparse
import json
import os
import shutil
import sys
import time

VOCALS_MODEL = "vocals_mel_band_roformer.ckpt"
INSTR_MODEL = "htdemucs_6s.yaml"


def separate(song: str, out: str, models: str, emit=lambda **kv: None) -> dict:
    from audio_separator.separator import Separator

    os.makedirs(out, exist_ok=True)
    tmp = os.path.join(out, ".work")
    os.makedirs(tmp, exist_ok=True)
    timings = {}
    t0 = time.time()
    sep = Separator(model_file_dir=models, output_dir=tmp, output_format="FLAC", log_level=30)
    sep.load_model(VOCALS_MODEL)
    files = [os.path.join(tmp, f) for f in sep.separate(song)]
    vocals = next(f for f in files if "(vocals)" in f.lower())
    rest = next(f for f in files if f != vocals)
    shutil.move(vocals, os.path.join(out, "vocals.flac"))
    shutil.move(rest, os.path.join(out, "instrumental.flac"))
    timings["vocals_s"] = round(time.time() - t0, 1)
    emit(event="progress", stage="stems", done=1, total=2)

    t1 = time.time()
    sep = Separator(model_file_dir=models, output_dir=tmp, output_format="FLAC", log_level=30)
    sep.load_model(INSTR_MODEL)
    for f in sep.separate(os.path.join(out, "instrumental.flac")):
        f = os.path.join(tmp, f)
        name = f.rsplit("(", 1)[-1].split(")", 1)[0].lower()
        if name in ("drums", "bass", "guitar", "piano", "other"):
            shutil.move(f, os.path.join(out, f"{name}.flac"))
        else:
            os.remove(f)
    timings["instruments_s"] = round(time.time() - t1, 1)
    emit(event="progress", stage="stems", done=2, total=2)
    shutil.rmtree(tmp, ignore_errors=True)
    info = {"models": {"vocals": VOCALS_MODEL, "instruments": INSTR_MODEL}, "timings": timings,
            "total_s": round(time.time() - t0, 1)}
    with open(os.path.join(out, "stems.json"), "w") as fh:
        json.dump(info, fh, indent=2)
    return info


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("song")
    ap.add_argument("out")
    ap.add_argument("--models", default="/models")
    a = ap.parse_args()
    print(json.dumps(separate(a.song, a.out, a.models)))
    sys.exit(0)
