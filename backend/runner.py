"""One owned generation process. No HTTP handling or shared-service mutations."""

from __future__ import annotations
import argparse, ctypes, hashlib, json, os, signal, subprocess, sys, time
from pathlib import Path


def write_json(path, data):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    os.replace(temporary, path)


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def run(spec_path):
    # Ensure an orphan cannot keep occupying the GPU after the API process dies.
    if sys.platform == "linux":
        parent = os.getppid()
        ctypes.CDLL(None).prctl(1, signal.SIGTERM)
        if os.getppid() != parent:
            raise InterruptedError("Parent exited")
    spec = json.loads(Path(spec_path).read_text())
    out = Path(spec["output"])
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    cancel_path = out / "cancel"
    counts = {}
    last_update = 0.0
    stage_name = "loading"

    def cancelled():
        return cancel_path.exists()

    def report(stage, **extra):
        nonlocal stage_name
        stage_name = stage
        write_json(
            out / "progress.json",
            {
                "stage": stage,
                "elapsed_seconds": round(time.monotonic() - started, 2),
                "updated_at": time.time(),
                **extra,
            },
        )

    def token(phase, _token):
        nonlocal last_update
        counts[phase] = counts.get(phase, 0) + 1
        if time.monotonic() - last_update >= 1:
            report("planning" if phase == "abc" else "generating", tokens=counts[phase])
            last_update = time.monotonic()

    report("loading")
    import numpy as np
    import soundfile as sf
    import torch
    from yue2 import YuE2Pipeline, SymbolicPlan
    from yue2.pipeline import SongResult
    from yue2.protocol import GenerationConfig, SongRequest
    from yue2.storage import identity

    torch.cuda.reset_peak_memory_stats()
    config = GenerationConfig.from_dict(spec["generation"])
    with YuE2Pipeline.from_pretrained(
        spec["model"],
        vae=spec["vae"],
        device="cuda",
        local_files_only=True,
        generation_config=config,
        memory_budget_gib=24,
        backend="torch",
        quantization="none",
        progress=True,
    ) as pipe:
        request = SongRequest(**spec["song"])
        # Fail promptly rather than entering native sampling with an oversized prompt.
        if (
            len(pipe.tokenizer.encode(request.text()))
            + len(pipe.tokenizer.encode(request.abc or ""))
            >= 24000
        ):
            raise ValueError(
                "Lyrics, style and score exceed the model context. Shorten the input."
            )
        report("planning")
        if spec.get("resume_plan") and spec.get("edited_abc") is None:
            plan = SymbolicPlan.load(spec["resume_plan"])
        else:
            if spec.get("edited_abc") is not None:
                request = SongRequest(**{**spec["song"], "abc": spec["edited_abc"]})
            plan = pipe.plan(request=request, cancelled=cancelled, on_token=token)
        plan.save(out / "plan")
        if spec.get("plan_first"):
            write_json(
                out / "plan-ready.json",
                {"truncated": plan.truncated, "timing": plan.timing},
            )
            report("needs-review")
            return
        if cancelled():
            raise InterruptedError("Cancelled")
        report("generating")
        semantic = pipe.generate_semantic(plan, cancelled=cancelled, on_token=token)
        np.save(
            out / "semantic.partial.npy", np.asarray(semantic.tokens, dtype=np.int32)
        )
        report("synthesizing")
        nar_started = time.monotonic()
        latents = pipe.synthesize(semantic, cancelled=cancelled)
        nar_seconds = time.monotonic() - nar_started
        np.save(out / "latent.partial.npy", latents)
        if cancelled():
            raise InterruptedError("Cancelled")
        report("decoding")
        decode_started = time.monotonic()
        audio = pipe.decode(latents)
        if cancelled():
            raise InterruptedError("Cancelled")
        timing = {
            "abc": plan.timing,
            "semantic": semantic.timing,
            "nar_seconds": nar_seconds,
            "vae_seconds": time.monotonic() - decode_started,
            "load": dict(pipe.load_timing),
            "e2e_seconds": time.monotonic() - started,
        }
        effective = pipe.effective_config(plan.request)
        request_identity = identity(
            {
                "request": plan.request.to_dict(),
                "config": effective,
                "weights": pipe.weights,
            }
        )
        song = SongResult(
            audio,
            48000,
            semantic,
            latents,
            effective,
            pipe.weights,
            timing,
            request_identity,
        )
        report("exporting")
        song.save_artifacts(out)
        # Preserve full float decode as the original WAV; upstream also saves 24-bit FLAC.
        sf.write(out / "audio.wav", audio, 48000, subtype="FLOAT")
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-i",
                str(out / "audio.wav"),
                "-codec:a",
                "libmp3lame",
                "-b:a",
                "320k",
                "-y",
                str(out / "audio.mp3"),
            ],
            check=True,
            timeout=300,
        )
        if (
            audio.ndim != 2
            or audio.shape[1] != 2
            or not np.isfinite(audio).all()
            or len(audio) < 48000
        ):
            raise ValueError(
                "Decoded audio failed stereo/finite/duration checks; artifacts retained."
            )
        peak = float(np.max(np.abs(audio)))
        rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
        if rms < 1e-6:
            raise ValueError("Decoded audio is effectively silent; artifacts retained.")
        clipping = float(np.mean(np.abs(audio) >= 0.9999))
        warnings = []
        if any(song.truncated.values()):
            warnings.append(
                "Model reached a token limit; listen for an incomplete ending."
            )
        if clipping > 0.001:
            warnings.append(
                "More than0.1% of samples reach full scale; inspect for clipping."
            )
        for format in ["wav", "flac", "mp3"]:
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "stream=sample_rate,channels:format=duration",
                    "-of",
                    "json",
                    str(out / f"audio.{format}"),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            meta = json.loads(probe.stdout)
            if (
                meta["streams"][0]["channels"] != 2
                or abs(float(meta["format"]["duration"]) - len(audio) / 48000) > 0.2
            ):
                raise ValueError(f"{format} validation failed")
        record = {
            "status": "succeeded",
            "duration": len(audio) / 48000,
            "sample_rate": 48000,
            "channels": 2,
            "peak": peak,
            "rms": rms,
            "clipped_fraction": clipping,
            "truncated": song.truncated,
            "warnings": warnings,
            "timing": timing,
            "peak_vram_allocated_bytes": torch.cuda.max_memory_allocated(),
            "peak_vram_reserved_bytes": torch.cuda.max_memory_reserved(),
            "source_revision": spec["source_revision"],
            "model_revision": spec["model_revision"],
            "vae_revision": spec["vae_revision"],
            "torch": torch.__version__,
            "artifacts": {
                p.name: {"sha256": sha(p), "bytes": p.stat().st_size}
                for p in out.iterdir()
                if p.is_file()
                and p.suffix in {".wav", ".flac", ".mp3", ".json", ".abc", ".npy"}
                and p.name not in {"progress.json", "spec.json"}
            },
        }
        write_json(out / "delivery.json", record)
        report("complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("spec")
    args = parser.parse_args()
    try:
        run(args.spec)
    except BaseException as exc:
        try:
            out = Path(json.loads(Path(args.spec).read_text())["output"])
            write_json(
                out / "failure.json", {"type": type(exc).__name__, "message": str(exc)}
            )
        finally:
            raise
