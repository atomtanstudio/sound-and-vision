"""Render a measured shot plan and acoustic word cues with FFmpeg/libass.

No timing is inferred here. Missing/overlapping cues fail validation. H3 video
is trimmed on integer frames; the uncut approved master supplies all audio.
"""

import argparse
import hashlib
import json
import math
import subprocess
import time
from pathlib import Path

from PIL import ImageFont
from fontTools.ttLib import TTFont


def run(args):
    subprocess.run([str(a) for a in args], check=True)


def probe(path):
    return json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(path),
            ]
        )
    )


def stamp(value):
    cs = round(value * 100)
    return f"{cs // 360000}:{cs // 6000 % 60:02}:{cs // 100 % 60:02}.{cs % 100:02}"


def plain(text):
    return text.replace("\\", "").replace("{", "").replace("}", "").replace("\n", " ")


def write_ass(plan, alignment, font_path, target):
    width, height = plan["output"]
    if [width, height] != [1920, 1080]:
        raise ValueError("This composition currently requires a 1920 × 1080 canvas")
    cues = alignment["cues"]
    metrics = TTFont(font_path)
    # libass sizes a font by ascender-to-descender height; Pillow uses em size.
    # Account for this difference when centering independently animated words.
    em_scale = metrics["head"].unitsPerEm / (
        metrics["hhea"].ascent - metrics["hhea"].descent
    )
    events, audit = [], []
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes
WrapStyle: 2
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Word,SV Manrope,100,&H00F0F1F4,&H00F0F1F4,&H80000000,&HC0000000,0,0,0,0,100,100,0,0,1,1.2,0,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def event(start, end, text, tags, layer=1):
        if end <= start:
            return
        events.append(
            f"Dialogue: {layer},{stamp(start)},{stamp(end)},Word,,0,0,0,,{{{tags}}}{plain(text)}"
        )

    # Opening and closing labels only. No persistent branding over the lyrics.
    for start, end in [
        (0.7, min(cues[0]["start"] - 0.6, 7.6)),
        (max(cues[-1]["end"] + 1.4, plan["duration"] - 9.5), plan["duration"] - 0.8),
    ]:
        event(
            start,
            end,
            plan["artist"].upper(),
            r"\an4\pos(166,392)\fs29\fsp6\1c&H8A929E&\fad(320,500)",
        )
        event(
            start + 0.15,
            end,
            plan["title"].upper(),
            r"\an4\move(155,495,166,495,0,420)\fs145\fsp-4\fad(250,500)",
        )

    last_word_end = -1
    chorus_lines = {
        i
        for section in alignment["sections"]
        if section["label"] == "[Chorus]"
        for i in range(
            int(section["firstLine"].split("-")[-1]),
            int(section["lastLine"].split("-")[-1]) + 1,
        )
    }
    bridge_lines = {
        i
        for section in alignment["sections"]
        if section["label"] == "[Bridge]"
        for i in range(
            int(section["firstLine"].split("-")[-1]),
            int(section["lastLine"].split("-")[-1]) + 1,
        )
    }
    for ci, cue in enumerate(cues):
        words = cue["words"]
        for word in words:
            a, b = word["start"], word["end"]
            if (
                a is None
                or b is None
                or not math.isfinite(a + b)
                or a < 0
                or b <= a
                or b > plan["duration"]
            ):
                raise ValueError(
                    f"Missing or invalid acoustic timing: {cue['id']} {word['text']}"
                )
            if a < last_word_end - 0.001:
                raise ValueError(
                    f"Overlapping acoustic words: {cue['id']} {word['text']}"
                )
            last_word_end = b
        chorus, bridge = ci in chorus_lines, ci in bridge_lines
        size = 186 if chorus else 172 if bridge else 140
        if len(words) == 1:
            size = 342
        font = ImageFont.truetype(str(font_path), round(size * em_scale))
        gap = font.getlength(" ") * 1.2
        advances = [font.getlength(w["text"].upper()) for w in words]
        total = sum(advances) + gap * (len(words) - 1)
        split = len(words)
        if total > 1450:
            split = min(
                range(1, len(words)),
                key=lambda i: abs(
                    sum(advances[:i])
                    + gap * (i - 1)
                    - sum(advances[i:])
                    - gap * (len(words) - i - 1)
                ),
            )
        rows = [list(range(split))] + (
            [list(range(split, len(words)))] if split < len(words) else []
        )
        line_end = min(
            cue["end"] + (1.5 if bridge else 1.2 if chorus else 1.0),
            (
                cues[ci + 1]["start"] - 0.045
                if ci + 1 < len(cues)
                else plan["duration"] - 0.5
            ),
        )
        slots = {}
        for ri, row in enumerate(rows):
            span = sum(advances[i] for i in row) + gap * (len(row) - 1)
            x = (width - span) / 2
            y = 535 + (ri - (len(rows) - 1) / 2) * size * 0.92
            for i in row:
                slots[i] = (round(x + advances[i] / 2), round(y))
                x += advances[i] + gap
        for wi, word in enumerate(words):
            x, y = slots[wi]
            start, finish = word["start"], word["end"]
            style = ci % 3
            pop = 140 if chorus else 128
            # Current word arrives at its measured onset; previous words settle
            # to white. No grey future lyric is presented before it is sung.
            base = rf"\fs{size}\an5\1c&H6579EE&\bord1.2\fad(0,100)"
            if style == 0:
                motion = (
                    rf"\pos({x},{y})\fscx112\fscy{pop}\t(0,190,0.7,\fscx100\fscy100)"
                )
            elif style == 1:
                angle = 3 if wi % 2 else -3
                motion = rf"\move({x},{y+24},{x},{y},0,170)\frz{angle}\fscx112\fscy112\t(0,180,0.7,\frz0\fscx100\fscy100)"
            else:
                motion = rf"\pos({x},{y})\fscx112\fscy80\t(0,100,\fscx97\fscy105)\t(100,210,\fscx100\fscy100)"
            settle = max(90, round((finish - start) * 1000))
            color = rf"\t({settle},{settle+100},\1c&HF0F1F4&)"
            event(start, line_end, word["text"].upper(), base + motion + color)
            audit.append(
                {
                    "cue": cue["id"],
                    "word": word["text"],
                    "sourceStart": start,
                    "renderStart": round(start * 100) / 100,
                    "sourceEnd": finish,
                    "position": [x, y],
                    "size": size,
                    "review": word.get("review"),
                }
            )
    target.write_text(header + "\n".join(events) + "\n")
    target.with_suffix(".json").write_text(
        json.dumps(
            {
                "method": alignment["method"],
                "wordCount": len(audit),
                "reviewCount": alignment["reviewCount"],
                "words": audit,
            },
            indent=2,
        )
        + "\n"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--alignment", type=Path, required=True)
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--media-root", type=Path, required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ass-only", action="store_true")
    parser.add_argument("--wait-for-clips", action="store_true")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    alignment = json.loads(args.alignment.read_text())
    work = args.output.parent / "render"
    work.mkdir(parents=True, exist_ok=True)

    def status(phase, **extra):
        temp = args.output.parent / "render-status.tmp"
        temp.write_text(
            json.dumps({"phase": phase, "updated": time.time(), **extra}, indent=2)
            + "\n"
        )
        temp.replace(args.output.parent / "render-status.json")

    ass = work / "lyrics.ass"
    write_ass(plan, alignment, args.font, ass)
    if args.ass_only:
        print(ass)
        return
    fps = plan["fps"]
    normalized = []
    mappings_path = args.plan.parent / "job-map.json"
    mappings = json.loads(mappings_path.read_text()) if mappings_path.exists() else {}
    for shot in plan["shots"]:
        request_id = shot["request"]["requestId"]
        deadline = time.monotonic() + 1800
        while True:
            mappings = (
                json.loads(mappings_path.read_text()) if mappings_path.exists() else {}
            )
            source = (
                args.media_root
                / mappings.get(request_id, request_id)
                / "background.mp4"
            )
            batch_path = args.plan.parent / "batch-status.json"
            batch = json.loads(batch_path.read_text()) if batch_path.exists() else {}
            # A file can appear before its writer finishes. Require the
            # batch's completed-job receipt before probing or encoding it.
            if not args.wait_for_clips or (
                source.exists() and request_id in batch.get("completed", [])
            ):
                break
            status(
                "Waiting for generated clip",
                shot=shot["index"] + 1,
                total=len(plan["shots"]),
            )
            if batch.get("state") in {"failed", "cancelled"}:
                raise RuntimeError(
                    "Background generation stopped; inspect batch-status.json"
                )
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"Waiting too long for {request_id}; successful render parts retained"
                )
            time.sleep(10)
        media = probe(source)
        stream = next(s for s in media["streams"] if s["codec_type"] == "video")
        frames = shot["endFrame"] - shot["startFrame"]
        duration = float(stream.get("duration", media["format"]["duration"]))
        if duration + 1 / fps < frames / fps:
            raise ValueError(f"Clip is too short; refusing to loop it: {source}")
        target = work / f"shot-{shot['index']:02}.mp4"
        normalized.append(target)
        source_hash = hashlib.file_digest(source.open("rb"), "sha256").hexdigest()
        cache = target.with_suffix(".json")
        expected = {
            "sourceSha256": source_hash,
            "frames": frames,
            "fps": fps,
            "canvas": [1920, 1080],
        }
        if (
            target.exists()
            and cache.exists()
            and json.loads(cache.read_text()) == expected
            and int(probe(target)["streams"][0]["nb_frames"]) == frames
        ):
            continue
        print(f"Normalizing shot {shot['index']+1}/{len(plan['shots'])}", flush=True)
        status(
            "Preparing generated clip", shot=shot["index"] + 1, total=len(plan["shots"])
        )
        run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-threads",
                "4",
                "-i",
                source,
                "-an",
                "-vf",
                f"fps={fps},scale=1920:1080:force_original_aspect_ratio=increase:flags=lanczos,crop=1920:1080,setsar=1",
                "-frames:v",
                frames,
                "-c:v",
                "libx264",
                "-threads",
                "6",
                "-preset",
                "fast",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-video_track_timescale",
                "24000",
                target,
            ]
        )
        cache.write_text(json.dumps(expected, indent=2) + "\n")
    concat = work / "clips.ffconcat"
    concat.write_text(
        "ffconcat version 1.0\n" + "".join(f"file '{p.name}'\n" for p in normalized)
    )
    # Use relative filter paths under a controlled render directory to avoid
    # escaping arbitrary apostrophes/colons in ffmpeg's filter mini-language.
    import shutil

    fonts = work / "fonts"
    fonts.mkdir(exist_ok=True)
    shutil.copyfile(args.font, fonts / args.font.name)
    frames = plan["shots"][-1]["endFrame"]
    temp = args.output.with_suffix(".partial.mp4").resolve()
    audio_path = args.audio.resolve()
    command = [
        "ffmpeg",
        "-y",
        "-v",
        "warning",
        "-threads",
        "4",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        "clips.ffconcat",
        "-i",
        str(audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-vf",
        "ass=lyrics.ass:fontsdir=fonts",
        "-frames:v",
        str(frames),
        "-c:v",
        "libx264",
        "-threads",
        "12",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "320k",
        "-ar",
        "48000",
        "-metadata",
        f"title={plan['title']}",
        "-metadata",
        f"artist={plan['artist']}",
        "-movflags",
        "+faststart",
        str(temp),
    ]
    status("Rendering complete film", frames=frames)
    subprocess.run(command, cwd=work, check=True)
    result = probe(temp)
    video = next(s for s in result["streams"] if s["codec_type"] == "video")
    audio = next(s for s in result["streams"] if s["codec_type"] == "audio")
    if (
        int(video["nb_frames"]) != frames
        or abs(float(audio["duration"]) - plan["duration"]) > 0.06
    ):
        raise ValueError("Rendered duration does not match the complete approved song")
    temp.replace(args.output)
    checksum = hashlib.file_digest(args.output.open("rb"), "sha256").hexdigest()
    receipt = {
        "title": plan["title"],
        "artist": plan["artist"],
        "sha256": checksum,
        "videoFrames": frames,
        "fps": fps,
        "dimensions": [video["width"], video["height"]],
        "videoDuration": video["duration"],
        "audioDuration": audio["duration"],
        "sourceAudio": str(args.audio),
        "audioMasterSha256": hashlib.file_digest(
            args.audio.open("rb"), "sha256"
        ).hexdigest(),
        "uniqueGeneratedClips": len(normalized),
        "alignmentMethod": alignment["method"],
        "automaticTimingReviewCount": alignment["reviewCount"],
        "words": alignment["wordCount"],
    }
    args.output.with_suffix(".json").write_text(json.dumps(receipt, indent=2) + "\n")
    status("Complete", output=str(args.output), receipt=receipt)
    print(json.dumps(receipt), flush=True)


if __name__ == "__main__":
    main()
