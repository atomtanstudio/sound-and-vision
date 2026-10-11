"""One take, listened to, inside sv-analysis (one container per job, GPU):

1. stems: MelBand RoFormer vocals + the rest; htdemucs_6s on the rest for drums, bass, guitar,
   piano, other (stems.py).
2. words: the old app's aligner (legacy/analysis_align.py, wav2vec2 CTC) places the known lyrics on
   the vocals stem. Skipped for an instrumental. A song uploaded without its lyrics ("hear") is first
   heard by faster-whisper large-v3 (hear.py), and those words are placed; lines with known times (an
   LRC file, "heard") keep each lyric line near where it's sung.
3. song map: the old app's rhythm map (legacy/analysis_rhythm.py): beats, downbeat, bars, sections,
   drum hits.

    python analyze.py SPEC.json      spec: {"song": path, "out": dir, "sections": [{label, lines}],
                                            "hear": {"model": dir}?, "heard": [{text, start, end}]?, "heardFrom": str?}

Events on stdout, one JSON object a line: {"event": "stage"|"progress"|"warning"|"done"|"error"}.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import hear  # noqa: E402
import stems  # noqa: E402

LEGACY = Path(__file__).parent / "legacy"


def emit(**ev):
    print(json.dumps(ev), flush=True)


def relay(cmd: list[str], stage: str) -> dict:
    """Run a legacy stage, pass its stage/progress events on, return its done event."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    done, error, current = None, None, stage
    for line in proc.stdout:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        kind = ev.get("event")
        if kind == "progress":
            emit(event="progress", stage=current, done=ev.get("done"), total=ev.get("total"))
        elif kind == "stage" and ev.get("stage") in ("listen", "align", "rhythm") and ev["stage"] != current:
            current = ev["stage"]
            emit(event="stage", stage=current)
        elif kind == "done":
            done = ev
        elif kind == "error":
            error = ev.get("message")
    err = proc.stderr.read()
    if proc.wait() != 0 or done is None:
        raise RuntimeError(error or (err.strip().splitlines()[-1] if err.strip() else f"{stage} stopped"))
    return done


def main():
    spec = json.loads(Path(sys.argv[1]).read_text())
    out = Path(spec["out"])
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    warnings: list[str] = []
    try:
        emit(event="stage", stage="stems")
        stems.separate(spec["song"], str(out), "/models", emit)
        mix = out / "mix.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", spec["song"], "-ac", "2", str(mix)], check=True)

        timing = None
        heard, heard_from = spec.get("heard"), spec.get("heardFrom")
        if not spec.get("sections") and spec.get("hear"):
            emit(event="stage", stage="hear")
            got = hear.hear(spec["hear"]["model"], str(out / "vocals.flac"), emit, spec["hear"].get("language"))
            (out / "heard.json").write_text(json.dumps(got))
            spec["sections"] = hear.parts(got["lines"])
            heard, heard_from = got["lines"], "Whisper heard it"
            if not got["lines"]:
                warnings.append("No words were heard: it's treated as an instrumental.")
        if spec.get("sections"):
            emit(event="stage", stage="listen")
            align_spec = out / "align-spec.json"
            align_spec.write_text(json.dumps({"vocals": str(out / "vocals.flac"), "mix": str(mix),
                                              "sections": spec["sections"], "out": str(out / "timing.json"),
                                              **({"heard": heard, "heardFrom": heard_from} if heard else {})}))
            relay([sys.executable, str(LEGACY / "analysis_align.py"), str(align_spec)], "listen")
            timing = out / "timing.json"

        emit(event="stage", stage="rhythm")
        rhythm_spec = out / "rhythm-spec.json"
        rhythm_spec.write_text(json.dumps({"mix": str(mix), "drums": str(out / "drums.flac"), "vocals": str(out / "vocals.flac"),
                                           "timing": str(timing) if timing else None, "out": str(out / "songmap.json")}))
        try:
            relay([sys.executable, str(LEGACY / "analysis_rhythm.py"), str(rhythm_spec)], "rhythm")
        except RuntimeError as exc:
            warnings.append(f"The song map couldn't be made: {exc}")
        mix.unlink(missing_ok=True)
        emit(event="done", seconds=round(time.monotonic() - started, 1), warnings=warnings)
    except Exception as exc:  # the job reads this as its reason
        emit(event="error", message=f"{type(exc).__name__}: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
