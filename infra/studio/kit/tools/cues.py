"""Every lyric word with its sung time, its cue and the frame it lands on, from analysis/analysis.json.

  python3 tools/cues.py                    all lines
  python3 tools/cues.py --from 60 --to 90  words cued in that stretch
  python3 tools/cues.py --lines            one row per line: id, section, start, end, words

Frame i of a render shows song time (i + 0.5) / fps, so a word cued at c lands on frame ceil(c·fps − 0.5): the first
frame whose centre is at or after the cue. `how` is the drum onset key the cue snapped to, or `lead` (sung start − lead).
"""

import argparse
import json
from math import ceil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="a", type=float, default=float("-inf"))
    ap.add_argument("--to", dest="b", type=float, default=float("inf"))
    ap.add_argument("--fps", type=float, default=None)
    ap.add_argument("--lines", action="store_true")
    a = ap.parse_args()
    an = json.loads((ROOT / "analysis/analysis.json").read_text())
    fps = a.fps or an.get("fps") or 60
    bars, meter = an["bars"], an.get("meter", 4)

    def pos(t: float) -> str:
        i = max(0, min(len(bars) - 2, sum(1 for b in bars if b <= t) - 1))
        return f"{i + 1}.{(t - bars[i]) / (bars[i + 1] - bars[i]) * meter + 1:.1f}"

    if a.lines:
        print(f"{'line':>6}  {'section':<14} {'start':>8} {'end':>8}  words")
        for l in an["lyrics"]:
            if a.a <= l["words"][0][3] < a.b:
                print(f"{l['id']:>6}  {str(l['sec']):<14} {l['start']:8.3f} {l['end']:8.3f}  {len(l['words'])}")
        return
    print(f"{'line':>6} {'#':>2}  {'word':<18} {'sung':>9} {'cue':>9} {'how':>6} {'frame':>6} {'bar.beat':>9}")
    for l in an["lyrics"]:
        for i, (text, sung, end, cue, how) in enumerate(l["words"]):
            if a.a <= cue < a.b:
                print(f"{l['id']:>6} {i:>2}  {text:<18} {sung:9.3f} {cue:9.3f} {how:>6} {ceil(cue * fps - 0.5 - 1e-9):>6} {pos(cue):>9}")


if __name__ == "__main__":
    main()
