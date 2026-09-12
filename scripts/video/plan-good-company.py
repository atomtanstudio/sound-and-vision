"""Reproducible shot plan for the approved Good Company demonstration."""

import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
p = root / "deliveries/good-company-20260910/video"
analysis = json.loads((p / "analysis.json").read_text())
scenes = [
    (
        "Opening room",
        "A wide low-angle view of the empty black lacquer room from the image. The chrome chair sits at the right third beside the tall vertical scarlet slit. The camera tracks sideways with small amplitude at slow speed, revealing the thin chrome curve at the left edge. Light travels across the chrome in clean rhythmic sweeps, while the central dark wall remains clear.",
    ),
    (
        "Chrome detail",
        "An extreme close view of a tubular chrome chair arm and the corner of its black leather seat. Frame the curved tube across the bottom and right edges with an uncluttered dark centre. The camera slowly arcs through forty degrees, revealing travelling silver reflections. Narrow red highlights pulse delicately with the music rather than flashing across the frame.",
    ),
    (
        "The door",
        "A straight-on wide view of two tall smoked-glass wall panels separated by a thin red light slit, using the same stone and polished black floor. The panels breathe outward by a few centimetres and settle back with the kick rhythm. The camera pushes in with small amplitude at slow speed. Keep the central glass almost black and avoid any lettering.",
    ),
    (
        "First chorus",
        "A medium-wide scene of a sculptural polished chrome ribbon suspended over the dark stage. Its long shape folds and unfolds in a measured rhythm without changing material or breaking apart. Red light grazes its outer edge; silver reflections roll across the underside. The camera makes a slow forty-five-degree arc. The moving shape stays to the outer thirds, leaving the centre open.",
    ),
    (
        "Floor level",
        "A ground-level tracking view across black stone reflections toward the chrome chair. The chrome legs extend into the upper right, and a red light line reflects diagonally through the left edge. A subtle ripple of light travels across the floor with each strong bass attack. The camera slowly trucks left, maintaining the chair scale and stable perspective.",
    ),
    (
        "Closing times",
        "A medium-wide architectural view of three tall smoked-glass fins. They turn gradually through a small angle, opening and closing narrow red-lit gaps in rhythm. The black stone, chrome edges and dramatic fashion lighting match the reference. Use a slow lateral camera track that exposes the geometry without any cut. The middle third stays dark.",
    ),
    (
        "Room for one",
        "An overhead oblique view of four black leather and tubular chrome chairs in a loose square on the same black lacquer floor. One chair slides calmly outward, opening the arrangement. The camera holds steady while silver reflections sweep in time with the kick. The chairs sit around a large empty centre; movement is precise and physically grounded.",
    ),
    (
        "The key",
        "A macro photographic view of an oversized brushed-chrome key sculpture lying on smoked glass. Its broad circular bow sits to the right, with its shaft following the lower edge and no writing engraved on it. A soft scarlet light slit is reflected behind it. The camera slowly arcs thirty-five degrees; small light accents respond to the original bass rhythm.",
    ),
    (
        "Second chorus",
        "A wide shot of two sculptural chrome loops rising from the black floor at opposite edges. They rotate slowly in opposing directions, creating an open oval of dark space between them. Lighting is controlled silver with one deep red edge. The camera pushes forward smoothly with small amplitude while reflected highlights respond to the kick accents.",
    ),
    (
        "Take the floor",
        "A low oblique wide view of the chrome chair set farther back on the black stage, while two smoked-glass panels glide outward toward the frame edges. The cleared central floor becomes the dominant shape. The camera tracks slowly toward the open space. Reflections sharpen on the stronger beats, remaining restrained and continuous.",
    ),
    (
        "Refusal",
        "A nearly still close view of the vertical scarlet light slit reflected in heavy smoked glass. A thin brushed-metal blade crosses the outer edge and slowly turns away, widening the dark centre. Reduce movement and keep the lighting controlled through the sparse part of the music. The camera makes one slow minimal push, with no flicker.",
    ),
    (
        "Final chorus",
        "A sweeping wide view of the full architectural room, chrome chair and broad folded metal sculpture, maintaining the reference materials. The chair moves a short distance aside and the metal sculpture slowly opens like a fan along the far right. The camera arcs smoothly by forty degrees. Bass-responsive reflections add energy while leaving the centre clear for the final sung words.",
    ),
    (
        "Exit",
        "A long wide view of the emptied black stage with the chrome chair at the far right and the red slit receding behind it. The camera pulls out at slow speed. The chair and room remain physically stable; reflected light gradually softens as the music winds down. End on a composed dark frame with generous space at the left for closing titles.",
    ),
]
base = "The target video is a tactile photographic electroclash art film, with controlled silver reflections, black lacquer, smoked glass, oxblood light and fine natural film grain. The visual identity comes from <Picture 1>, not from copying its exact framing."
shots = []
for section, (name, scene) in zip(analysis["sections"], scenes):
    duration = section["generationSeconds"]
    i = section["index"]
    local_beats = [
        round(b - section["start"], 3)
        for b in analysis["beats"]
        if section["start"] <= b < section["end"]
    ]
    detailed = f"""{base}
[Shot 1] {scene} <Subject 1> retains the deep black architectural surfaces, believable chrome reflections, sparse red accent and empty, quietly imposing atmosphere of <Picture 1>. The room contains no people or faces. The props have stable proportions, realistic weight, and continuous material reflections. Use physically believable soft reflections and a shallow layer of haze near the distant wall, avoiding decorative particles or busy detail. The movement should feel deliberate and confident rather than frantic. Use the actual rhythmic accents in <Audio 1> as timing guidance for small changes in the practical light and prop motion, with the first strong kick establishing their phase. Keep the visual movement secondary to the song. The image remains legible beneath a separate layer of large kinetic lyric typography that will be composited later. Do not draw that typography, the song title, an artist name, labels, logos or watermarks into this clip. Preserve a clean dark area spanning the middle of the frame, with important objects and brighter reflections predominantly along the edges. Maintain one continuous camera move through the full {duration:.2f}-second clip, with no internal edits, title cards, freeze frames, scene changes or rapid flashes. <Audio 1> plays in its original timing and pitch for the complete shot; do not create a singer, dialogue, sound effects or an alternative music track. The end frame is a natural continuation of the camera and object motion, suitable for a clean cut to the next section."""
    prompt = f"""subject_definitions:
<Subject 1> is the recurring black-lacquer performance space and its chrome, smoked-glass and restrained scarlet visual language, sourced from <Picture 1>.
<Picture 1> is the supplied visual reference image for the materials, lighting and empty architectural setting.
<Audio 1> is the exact excerpt of the approved song Good Company, beginning at {section['start']:.6f} seconds in the song; it supplies the rhythm and final soundtrack for this segment.

summary:
[reference generation + audio reuse] Create one continuous {duration:.2f}-second background shot using <Subject 1> and the visual identity of <Picture 1>, with movement guided by the actual rhythm of <Audio 1>. Keep the lyric area quiet and reuse the source audio without changing its timing.

retention_analysis:
<Subject 1> (appears in [Shot 1]): partially_preserved - retain its materials, lighting and spatial language while adopting the shot's specified props and framing.
<Picture 1> ([Shot 1] visual reference): weak_reference - use the reference's photographic material and light treatment, with a new camera composition.
<Audio 1>: fully_copy - reuse the entire supplied audio window as this clip's complete final audio track, keeping pitch and timing unchanged.

detailed_description:
{detailed}

overall_soundscape:
The supplied <Audio 1> is the only audible track; retain it without added ambience or effects.

non_diegetic_music:
<Audio 1> supplies the original electroclash song, with the existing heavy electronic kick, synth bass and female vocal unchanged."""
    body = {
        "requestId": f"good-company-film-{i:02}-" + ("v1" if i == 0 else "turbo-v1"),
        "kind": "motion",
        "slot": i,
        "aspect": "16:9",
        "seconds": duration,
        "prompt": prompt,
        "audioStart": section["start"],
        "referenceImageJobId": "good-company-visual-anchor-20260910-01",
    }
    shots.append({**section, "name": name, "localBeats": local_beats, "request": body})
plan = {
    "title": "Good Company",
    "artist": "Guest Policy",
    "takeId": "55c92ee597594740997721f987b1cfa3",
    "fps": 24,
    "output": [1920, 1080],
    "duration": analysis["duration"],
    "referenceImage": "visual-reference.png",
    "soundtrack": "../take-1/audio.flac",
    "motionWorkflow": "H3LIX fused Turbo, provider default 4 steps; completed quality pilot retained",
    "shots": shots,
}
(p / "film-plan.json").write_text(json.dumps(plan, indent=2) + "\n")
(p / "pilot-request.json").write_text(json.dumps(shots[0]["request"], indent=2) + "\n")
print(
    "Planned",
    len(shots),
    "unique audio-conditioned H3 clips for",
    analysis["duration"],
    "seconds",
)
