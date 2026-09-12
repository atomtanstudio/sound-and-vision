"""Section-level phonetic check: keep chorus words in one monotonic acoustic path."""

import json, sys, re, hashlib
from pathlib import Path

root = Path("/srv/ai/sound-vision")
sys.path.insert(0, str(root / "backend"))
from phonetic_alignment import align_english
from alignment_runner import reconcile
import torch

torch.set_num_threads(8)
work = root / "data/films/good-company"
old = json.loads(
    (root / "data/video/good-company-alignment-20260910-01/result.json").read_text()
)
heard = json.loads(
    (
        root / "data/video/good-company-alignment-20260910-01/transcription.json"
    ).read_text()
)
groups = []
current = None
offset = 0
line_index = 0
for line in old["lyrics"].splitlines():
    line = line.strip()
    if not line:
        continue
    if re.fullmatch(r"\[[^\]]+\]", line):
        current = {"label": line, "lines": [], "offset": offset}
        groups.append(current)
    else:
        if current is None:
            current = {"label": "[Verse]", "lines": [], "offset": offset}
            groups.append(current)
        current["lines"].append(old["cues"][line_index])
        line_index += 1
        offset += len(line.split())
windows = []
offsets = []
for i, g in enumerate(groups):
    start = min(q["start"] for q in g["lines"])
    end = max(q["end"] for q in g["lines"])
    previous = max(q["end"] for q in groups[i - 1]["lines"]) if i else 0
    following = (
        min(q["start"] for q in groups[i + 1]["lines"])
        if i < len(groups) - 1
        else old["duration"]
    )
    windows.append(
        {
            "start": max(0, start - 1.2, (previous + start) / 2 if i else 0),
            "end": min(old["duration"], end + 2, (end + following) / 2),
            "text": " ".join(q["text"] for q in g["lines"]),
        }
    )
    offsets.append(g["offset"])
audio = root / "data/runs/55c92ee597594740997721f987b1cfa3/attempt-001/audio.flac"
vocals = (
    root
    / "data/video/audio-cache"
    / hashlib.sha256(audio.read_bytes()).hexdigest()
    / "vocals.wav"
)
anchors = align_english(vocals, windows, offsets, work / "alignment-phase.json")
result = reconcile(old["lyrics"], [], heard, old["duration"], anchors)
result["method"] = (
    "Section-constrained wav2vec2 phonetic alignment, checked against phrase alignment and Whisper recognition"
)
result["sectionWindows"] = windows
result["sections"] = [
    {
        "label": g["label"],
        "firstLine": g["lines"][0]["id"],
        "lastLine": g["lines"][-1]["id"],
    }
    for g in groups
]
(work / "alignment-sections.json").write_text(json.dumps(result, indent=2) + "\n")
print(
    "wordCount",
    result["wordCount"],
    "null",
    sum(w["start"] is None for q in result["cues"] for w in q["words"]),
    "flagged",
    result["reviewCount"],
)
for q in result["cues"]:
    print(q["id"], q["start"], q["end"], q["text"])
