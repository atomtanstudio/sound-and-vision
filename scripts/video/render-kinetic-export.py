"""Render the browser Kinetic lyric draft to a full-song MP4.

The browser preview remains the editing surface. This worker consumes a
validated, server-owned snapshot of that draft and never reads arbitrary paths
or URLs supplied by the browser.
"""

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
from pathlib import Path


FPS = 24


def run(args, cwd=None):
    subprocess.run([str(item) for item in args], check=True, cwd=cwd)


def probe(path):
    return json.loads(
        subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]
        )
    )


def phase(work, message, frames=0, total_frames=0):
    target = work / "progress.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"phase": message, "frames": frames, "totalFrames": total_frames})
    )
    temporary.replace(target)


def ass_color(value):
    value = value.lstrip("#")
    return f"&H{value[4:6]}{value[2:4]}{value[0:2]}&"


def stamp(seconds):
    centiseconds = round(seconds * 100)
    return f"{centiseconds // 360000}:{centiseconds // 6000 % 60:02}:{centiseconds // 100 % 60:02}.{centiseconds % 100:02}"


def ass_text(text):
    return str(text).replace("\\", "＼").replace("{", "｛").replace("}", "｝").replace("\n", " ").replace("\r", " ")


def write_ass(config, target):
    draft = config["draft"]
    width, height = config["width"], config["height"]
    text_color = ass_color(draft["textColor"])
    highlight_color = ass_color(draft["highlightColor"])
    font_size = round((92 if width < height else 76) * draft["textSize"] / 100)
    align = 2 if draft["placement"] == "lower" else 5
    margin_v = round(height * (0.16 if draft["placement"] == "lower" else 0.5))
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Kinetic,DejaVu Sans,{font_size},{text_color},{text_color},&H90000000,&H90000000,1,0,0,0,100,100,0,0,1,2.4,1.2,{align},80,80,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for cue_index, cue in enumerate(config.get("cues", [])):
        words = cue["words"]
        if not words:
            continue
        # The preview uses a single phrase block. Approximate widths with a
        # conservative character measure so long rap lines still stay inside
        # the safe area without requiring a font parser in the worker.
        rows, row, width_estimate = [], [], 0
        max_width = width * (0.84 if width >= height else 0.78)
        for word in words:
            estimate = max(1, len(word["text"])) * font_size * 0.58
            if row and width_estimate + estimate > max_width:
                rows.append(row)
                row, width_estimate = [], 0
            row.append(word)
            width_estimate += estimate + font_size * 0.28
        if row:
            rows.append(row)
        line_end = min(
            config["duration"] - 0.04,
            (config["cues"][cue_index + 1]["words"][0]["start"] - 0.03)
            if cue_index + 1 < len(config.get("cues", []))
            else cue["words"][-1]["end"] + 0.85,
        )
        line_end = max(line_end, cue["words"][-1]["end"] + 0.04)
        for row_index, row in enumerate(rows):
            total = sum(max(1, len(word["text"])) * font_size * 0.58 for word in row)
            total += font_size * 0.28 * max(0, len(row) - 1)
            x = (width - total) / 2
            y = margin_v if align == 2 else height / 2 + (row_index - (len(rows) - 1) / 2) * font_size * 1.12
            for word in row:
                advance = max(1, len(word["text"])) * font_size * 0.58
                start, end = word["start"], word["end"]
                if end <= start:
                    continue
                motion = draft["lyricMotion"]
                entrance = r"\fscx112\fscy112\t(0,150,\fscx100\fscy100)"
                if motion == "slam":
                    entrance = r"\fscx145\fscy145\t(0,180,\fscx100\fscy100)"
                elif motion == "rise":
                    entrance = rf"\move({round(x + advance / 2)},{round(y + font_size * 0.25)},{round(x + advance / 2)},{round(y)},0,180)"
                elif motion == "calm":
                    entrance = r"\fscx102\fscy102\t(0,220,\fscx100\fscy100)"
                elif motion == "reveal":
                    entrance = r"\fad(180,80)"
                else:
                    entrance = r"\fscx116\fscy88\t(0,170,\fscx100\fscy100)"
                color = rf"\1c{highlight_color}\t({max(1, round((end - start) * 1000))},{max(2, round((end - start) * 1000) + 120)},\1c{text_color})"
                events.append(
                    f"Dialogue: 1,{stamp(start)},{stamp(line_end)},Kinetic,,0,0,0,,"
                    f"{{\\an5\\pos({round(x + advance / 2)},{round(y)}){entrance}{color}}}{ass_text(word['text'])}"
                )
                x += advance + font_size * 0.28
    if not events:
        title = ass_text(config.get("title", "Kinetic lyric video"))
        events.append(
            f"Dialogue: 1,0:00:00.00,0:00:05.00,Kinetic,,0,0,0,,{{\\an5\\pos({width // 2},{height // 2})\\fad(250,500)}}{title}"
        )
    target.write_text(header + "\n".join(events) + "\n", encoding="utf-8")


def encoder_args():
    encoder = os.environ.get("SOUND_VISION_VIDEO_ENCODER", "libx264")
    if encoder == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20", "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p"]


def normalize_background(source, target, frames, width, height, draft, kind, work):
    if kind == "images":
        scale = f"fps={FPS},scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,crop={width}:{height},setsar=1"
        if draft["pan"]:
            scale += f",zoompan=z='min(zoom+0.0007,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={width}x{height}:fps={FPS}"
        command = ["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", source, "-vf", scale]
    else:
        scale = f"fps={FPS},scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,crop={width}:{height},setsar=1"
        command = ["ffmpeg", "-y", "-v", "error", "-stream_loop", "-1", "-i", source, "-vf", scale]
    if draft["shade"]:
        scale += f",drawbox=x=0:y=0:w=iw:h=ih:color=black@{draft['shade'] / 100:.4f}:t=fill"
        command[command.index("-vf") + 1] = scale
    run([*command, "-frames:v", frames, *encoder_args(), "-an", "-video_track_timescale", str(FPS * 512), target], cwd=work)


def transition_sequence(normalized, placements, draft, work):
    if draft["transition"] == "cut" or len(normalized) < 2:
        return normalized
    parts = []
    for index, source in enumerate(normalized):
        frames = placements[index]["endFrame"] - placements[index]["startFrame"]
        next_frames = (
            placements[index + 1]["endFrame"] - placements[index + 1]["startFrame"]
            if index + 1 < len(placements)
            else 0
        )
        overlap = min(14, frames // 3, next_frames // 3) if next_frames else 0
        if overlap:
            blend = work / f"dissolve-{index:04}.mp4"
            filters = (
                f"[0:v]trim=end_frame={frames - overlap},setpts=PTS-STARTPTS[head];"
                f"[0:v]trim=start_frame={frames - overlap}:end_frame={frames},setpts=PTS-STARTPTS[old];"
                f"[1:v]trim=end_frame={overlap},setpts=PTS-STARTPTS[new];"
                f"[old][new]blend=all_expr='A*(1-min(1,T/{overlap / FPS}))+B*min(1,T/{overlap / FPS})'[blend];"
                f"[head][blend]concat=n=2:v=1:a=0[out]"
            )
            run([
                "ffmpeg", "-y", "-v", "error", "-i", source,
                "-i", normalized[index + 1], "-filter_complex_threads", "2",
                "-filter_complex", filters, "-map", "[out]", "-frames:v", frames,
                *encoder_args(), "-an", blend,
            ], cwd=work)
            parts.append(blend)
        else:
            parts.append(source)
    return parts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    work = args.output.parent
    total_frames = math.ceil(config["duration"] * config["fps"])
    try:
        write_ass(config, work / "lyrics.ass")
        normalized = []
        asset_map = {(item["kind"], item["slot"]): item["path"] for item in config["assets"]}
        draft = config["draft"]
        for index, placement in enumerate(config["placements"]):
            frames = placement["endFrame"] - placement["startFrame"]
            kind = draft["background"]
            source = asset_map[(kind, placement["assetIndex"])]
            target = work / f"background-{index:04}.mp4"
            phase(work, f"Preparing background {index + 1}/{len(config['placements'])}", placement["startFrame"], total_frames)
            normalize_background(source, target, frames, config["width"], config["height"], draft, kind, work)
            normalized.append(target)
        normalized = transition_sequence(normalized, config["placements"], draft, work)
        concat = work / "backgrounds.ffconcat"
        concat.write_text("ffconcat version 1.0\n" + "".join(f"file '{item.name}'\n" for item in normalized))
        phase(work, "Adding timed lyrics and original soundtrack", 0, total_frames)
        audio_filter = f"atrim=duration={config['duration']},asetpts=PTS-STARTPTS"
        fade = draft.get("audioFade")
        if fade:
            curve = "tri" if fade.get("curve") == "linear" else "hsin"
            audio_filter = f"afade=t=out:st={float(fade['start'])}:d={max(0.25, float(fade['end']) - float(fade['start']))}:curve={curve},{audio_filter}"
        partial = args.output.with_suffix(".partial.mp4")
        video_filter = ["-vf", "ass=filename=lyrics.ass"] if config.get("cues") else []
        run([
            "ffmpeg", "-y", "-v", "warning", "-threads", "4",
            "-f", "concat", "-safe", "0", "-i", concat,
            "-i", config["audio"], "-map", "0:v:0", "-map", "1:a:0",
            *video_filter, "-frames:v", total_frames, "-t", config["duration"],
            *encoder_args(), "-c:a", "aac", "-b:a", "320k", "-af", audio_filter,
            "-metadata", f"title={config.get('title', 'Kinetic lyric video')}",
            "-movflags", "+faststart", partial,
        ], cwd=work)
        result = probe(partial)
        video = next(stream for stream in result["streams"] if stream["codec_type"] == "video")
        audio = next(stream for stream in result["streams"] if stream["codec_type"] == "audio")
        if int(video.get("nb_frames", 0)) != total_frames:
            raise ValueError(f"Kinetic render frame mismatch: expected {total_frames}, got {video.get('nb_frames')}")
        if abs(float(audio.get("duration", 0)) - config["duration"]) > 0.08:
            raise ValueError("Kinetic render audio duration does not match the selected song range")
        partial.replace(args.output)
        receipt = {
            "title": config.get("title", "Kinetic lyric video"),
            "frames": total_frames,
            "fps": config["fps"],
            "duration": config["duration"],
            "dimensions": [video["width"], video["height"]],
            "lyrics": bool(config.get("cues")),
            "backgroundKind": draft["background"],
            "assetCount": len(config["assets"]),
            "audioSha256": hashlib.file_digest(Path(config["audio"]).open("rb"), "sha256").hexdigest(),
            "outputSha256": hashlib.file_digest(args.output.open("rb"), "sha256").hexdigest(),
        }
        (work / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        phase(work, "MP4 ready", total_frames, total_frames)
    except Exception as error:
        (work / "failure.json").write_text(json.dumps({"message": str(error)}) + "\n")
        raise


if __name__ == "__main__":
    main()
