"""Check complete decoding, frame coverage and soundtrack alignment at three points."""

import argparse
import json
import subprocess
import hashlib
from pathlib import Path

import numpy as np


def decode(path):
    return np.frombuffer(
        subprocess.check_output(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "8000",
                "-f",
                "f32le",
                "-c:a",
                "pcm_f32le",
                "-",
            ]
        ),
        dtype="<f4",
    )


def frame_hashes(path):
    output=subprocess.check_output(['ffmpeg','-v','error','-xerror','-i',str(path),'-map','0:v:0',
        '-fps_mode','passthrough','-pix_fmt','yuv420p','-f','framemd5','-'],text=True)
    return [line.rsplit(',',1)[1].strip() for line in output.splitlines() if not line.startswith('#')]


def verify_join(film,plan):
    receipt_path=film.with_suffix('.receipt.json')
    if not receipt_path.exists():return None
    receipt=json.loads(receipt_path.read_text())
    if receipt.get('videoAssembly')!='stream-copy':return None
    actual=frame_hashes(film)
    assert len(actual)==plan['shots'][-1]['endFrame'],'Decoded frame count differs from the saved timeline'
    results=[];work=film.parent/'composition'
    for shot in plan['shots']:
        index=shot['index'];titled=index in receipt['titleScenes']
        prepared=work/f"{'titled' if titled else 'shot'}-{index:02}.mp4"
        expected=frame_hashes(prepared)
        assert expected==actual[shot['startFrame']:shot['endFrame']],f'Picture preservation failed in scene {index+1}; export withheld'
        prep=json.loads((work/f'shot-{index:02}.json').read_text())
        untouched=not titled and prep['method']=='copied-source'
        if untouched:
            assert hashlib.file_digest(prepared.open('rb'),'sha256').hexdigest()==prep['sourceSha256'],'Prepared source file changed'
        results.append({'scene':index+1,'frames':len(expected),'identicalToPreparedVideo':True,'unchangedFromSource':untouched})
        temporary=film.parent/'phase.next.json';temporary.write_text(json.dumps({'phase':f'Verifying picture preservation · scene {index+1}/{len(plan["shots"])}'}))
        temporary.replace(film.parent/'phase.json')
    return {'scenes':results,'unchangedSourceFrames':sum(r['frames'] for r in results if r['unchangedFromSource'])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--film", type=Path, required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    media = json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(args.film),
            ]
        )
    )
    video = next(s for s in media["streams"] if s["codec_type"] == "video")
    audio = next(s for s in media["streams"] if s["codec_type"] == "audio")
    assert int(video["nb_frames"]) == plan["shots"][-1]["endFrame"]
    assert [video["width"], video["height"]] == plan["output"]
    assert abs(float(audio["duration"]) - plan["duration"]) < 0.06
    # FFmpeg omits empty metadata tags; an optional blank artist is valid.
    assert media["format"].get("tags", {}).get("artist", "") == plan["artist"]
    picture_check=verify_join(args.film,plan)
    if picture_check is None:subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-xerror",
            "-i",
            str(args.film),
            "-map",
            "0:v:0",
            "-f",
            "null",
            "-",
        ],
        check=True,
    )
    source, delivered = decode(args.audio), decode(args.film)
    length = min(len(source), len(delivered))
    assert abs(len(source) - len(delivered)) <= 480
    correlation = float(np.corrcoef(source[:length], delivered[:length])[0, 1])
    assert (
        correlation > 0.98
    ), f"Soundtrack differs from the approved master: {correlation}"
    evidence = []
    for fraction in (0.07, 0.47, 0.86):
        start = int(length * fraction)
        window = min(80000, length - start - 81)
        reference = source[start : start + window].astype(np.float64)
        scores = []
        for offset in range(-80, 81):
            candidate = delivered[start + offset : start + offset + window]
            scores.append(float(np.dot(reference, candidate)))
        offset = int(np.argmax(scores)) - 80
        assert abs(offset) <= 2, f"Audio offset at {start / 8000}s: {offset / 8}ms"
        evidence.append(
            {
                "sourceTime": start / 8000,
                "offsetSamplesAt8kHz": offset,
                "offsetMs": offset / 8,
            }
        )
    result = {
        "decode": "complete",
        "frames": int(video["nb_frames"]),
        "dimensions": [video["width"], video["height"]],
        "videoDuration": float(video["duration"]),
        "audioDuration": float(audio["duration"]),
        "audioCorrelationAt8kHz": correlation,
        "audioOffsetChecks": evidence,
        "title": plan["title"],
        "artist": plan["artist"],
        "scope": "File integrity and original-master timing. This is not a human listening review of lyric alignment.",
    }
    if picture_check:result['picturePreservation']=picture_check
    args.film.with_suffix(".verification.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
