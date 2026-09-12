"""Run pinned SheetSage2 in its separate Python/PyTorch environment."""

import ctypes, hashlib, json, os, signal, subprocess, sys, time
from pathlib import Path


def main():
    parent = os.getppid()
    ctypes.CDLL(None).prctl(1, signal.SIGTERM)
    if os.getppid() != parent:
        raise InterruptedError("Parent exited")
    source, destination, mode = sys.argv[1:4]
    out = Path(destination)
    lock = json.loads(Path(os.environ["SOUND_VISION_REFERENCE_LOCK"]).read_text())
    started = time.monotonic()
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-format_whitelist",
            "wav,flac,mp3,mov,ogg",
            "-show_entries",
            "format=duration:stream=codec_type",
            "-of",
            "json",
            source,
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    info = json.loads(probe.stdout)
    duration = float(info.get("format", {}).get("duration", 0))
    if not 1 <= duration <= 300 or not any(
        s.get("codec_type") == "audio" for s in info.get("streams", [])
    ):
        raise ValueError(
            "Choose a valid audio recording from 1 second to 5 minutes long."
        )
    # Restrict decoding to local data, normalize bounded audio before loading custom model code.
    normalized = out / "reference.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-protocol_whitelist",
            "file,pipe",
            "-format_whitelist",
            "wav,flac,mp3,mov,ogg",
            "-i",
            source,
            "-map",
            "0:a:0",
            "-vn",
            "-t",
            "300",
            "-ar",
            "24000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(normalized),
        ],
        check=True,
        timeout=60,
    )
    import torch
    from transformers import AutoModel

    torch.cuda.set_per_process_memory_fraction(0.65)
    torch.cuda.reset_peak_memory_stats()
    model = (
        AutoModel.from_pretrained(
            lock["SheetSage2"]["path"], trust_remote_code=True, local_files_only=True
        )
        .eval()
        .to("cuda")
    )
    result = model.transcribe(
        str(normalized),
        output_dir=str(out / "score"),
        melody_only=mode == "melody",
        dtype="bf16",
    )
    if result.get("abc_error") or not result.get("abc", "").strip():
        raise ValueError(
            result.get("abc_error") or "The reference did not produce a usable score."
        )
    data = {
        "abc": result["abc"],
        "duration": duration,
        "warnings": result.get("warnings") or [],
        "input": {"mode": mode},
        "revisions": {k: v["revision"] for k, v in lock.items()},
        "sha256": hashlib.sha256(Path(source).read_bytes()).hexdigest(),
        "elapsedSeconds": time.monotonic() - started,
        "peakAllocatedBytes": torch.cuda.max_memory_allocated(),
    }
    (out / "result.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        (Path(sys.argv[2]) / "failure.json").write_text(
            json.dumps({"message": str(e)[:1500]})
        )
        raise
