# Worked example: one 7.5 s lyric shot

Everything here is made up for illustration: the song, its line and its timing. No real lyric is used.

## The facts the prompt is built from

- Song: a mid-tempo track at 96 BPM in 4/4 (a beat every 0.625 s, a bar every 2.5 s). Master take analysis, with
  `song.timing` corrections applied, puts downbeats at 40.00, 42.50, 45.00, 47.50 s.
- The line (locked lyric): `copper rain on Juniper Street`. Words: copper 41.25–41.70, rain 41.70–42.40, on 42.60–42.75,
  Juniper 42.75–43.40, Street 43.40–44.10. A short drum fill 44.1–45.0. The next line starts at 47.70.
- The song's look sets capitals, so the exact on-screen strings are the locked words uppercased, nothing else changed.
- Shot: from the downbeat at 40.00 to the downbeat at 47.50 (7.5 s; the cut sits in the breath before 47.70). Generated at
  192 frames (8.00 s) from 40.00 and trimmed to 180 frames. Clip time = song time − 40.00.
- 16:9 at 1024 × 576, the fused turbo UNET, route (a) text-to-video with route (c) the song locked. The hybrid keeps the
  same prompt and pins corrected hold frames (see "Pinned frames" below and legion.md).
- Main event: "COPPER RAIN" lands on the vocal and lies across the wet street. Display B "ON JUNIPER STREET" is the one
  supporting line. Exit: rain washes both into unreadable copper streaks before the cut.

## The prompt (4,463 characters)

```text
integrated_multimodal_description: [Shot 1] STYLE LOCK: Night city realism with a painted-type layer. Wet black asphalt, sodium-orange street light from the upper left, fine 35 mm grain, deep shadows that keep detail, shallow depth of field. Palette: near-black #07090D background, warm white #F4F1EA type, copper #C8642B accent; no other hues. Type belongs to the world: painted, lit and rained on like everything else. Hard cuts only.
SHOT: 8.0 seconds, 16:9, one continuous shot with no cuts. A kinetic lyric shot in the chorus of a 96 BPM song; the words land with the sung vocal.
IDEA: A low camera glides down an empty rain-soaked street; the sung words land as giant letters painted flat on the wet asphalt, a second line appears on the brick wall ahead, and the rain washes both away before the next phrase.
WORLD: Floor: wet black asphalt with shallow puddles. Back plane: a dark brick wall 20 metres ahead. Depth: rain streaks in front, the painted letters on the road in the middle, the wall behind. Vanishing point at frame center. Sodium-orange key light from the upper left; a copper reflection travels along the puddles and only the floor letters answer it.
CAMERA: Starts 40 cm above the asphalt looking down the street, glides forward at walking speed, rises slowly to 1.5 m by the end; no zoom, no shake.
TYPE CAST: Display A: extra-condensed heavy grotesk, all capitals, letter width about 60 percent of height, weight 900, straight cut terminals, rectangular counters, tight spacing, flat warm white road paint with slightly worn edges. Display B: high-contrast serif, all capitals, hairline horizontals and heavy verticals, sharp serifs, copper paint, about one quarter the height of Display A. Marks: one thin copper baseline and the falling rain; marks are never letters or numbers.
COLOR SCRIPT: First the near-black street with warm light pools; then warm white letters on black asphalt; then the copper accent takes the baseline and the wall line; the end returns to the dark street with one copper line.
MECHANISMS: The hero grows up out of a baseline; the road and the wall form one type corridor.
ON-SCREEN TEXT, exact and case-sensitive: "COPPER RAIN" (Display A, built word by word as sung) and "ON JUNIPER STREET" (Display B). Only these two strings may ever be readable, each only in its window below. No other letters, numbers, signs, logos, captions or subtitles at any time; the wall and the street carry no other writing.
STATE 1 | 0.00-1.25 s | The camera starts low over the empty wet street; rain falls through the light. On the kick at 0.00 a thin copper line slides across the asphalt from the left edge and stops in the lower third. No readable text.
STATE 2 | 1.25-2.60 s | As it is sung at 1.25, "COPPER" rises out of the copper line as warm white paint lying flat on the road in perspective, 70 percent of the frame width; "RAIN" joins it at 1.70 on the same baseline. "COPPER RAIN" is complete from 1.85 and stays fixed to the road. On the downbeat at 2.50 the copper reflection ripples once across the letters; the letters themselves do not move.
STATE 3 | 2.60-4.40 s | The camera glides over the painted letters, which slide toward the lower foreground and stay readable. At 2.60 "ON JUNIPER STREET" appears on the brick wall ahead in copper paint, centered, as one group, complete from 2.80. The copper baseline brightens once at 2.75.
STATE 4 | 4.40-6.40 s | The camera rises; both lines stay complete until 4.90. On the downbeat at 5.00 the copper spreads along the baseline to the right edge. From 4.90 heavier rain runs across the floor letters, then the wall line, breaking them into unreadable copper and white streaks by 6.40; no part of a word is readable after 6.40.
TRANSITION OUT | 6.40-8.00 s | A stable frame: the empty wet street, the bare brick wall, one copper line reaching the right edge. Nothing new enters; the frame stays calm to the end.
CONTINUITY: The street, wall, light direction, palette and both letterforms stay the same throughout; the letters keep their exact spelling whenever readable. No person appears.

overall_soundscape: The supplied song plays unchanged as the only sound: a 96 BPM groove with a soft kick on every beat, a clap on two and four, warm electric piano and a lead vocal; the vocal phrase runs from 1.25 to 4.10 seconds, then a short drum fill. No added sound effects, no rain sound, no other voices.

non_diegetic_music: The supplied song only; no other music.
```

Count it before sending: copy the block into a file and run `wc -m` (this one is 4,463 including newlines; aim for
2,500–4,500 at this length, never over 7,000).

## Why it's written this way

- Words appear exactly when sung: "COPPER" at 1.25 = song 41.25, "RAIN" at 1.70; the second line at 2.60 = 42.60. Nothing
  readable before, nothing readable after 6.40, well before the next line at 7.70.
- Holds: the hero is complete for 3.05 s (1.85–4.90) and the second line for 2.1 s (2.80–4.90) before the wash; the only
  response during the holds is the reflection and the baseline, never the letters.
- One main event (the hero landing), one supporting line, one exit, and a stable 1.1 s before the cut at 7.50 (the last
  0.5 s of the clip is trimmed).
- Role names, color names and hex values never sit inside quotes; the only quoted strings are the two whitelisted ones and
  the hero's first word while it builds. The wall and street are told to carry no other writing, because a real-looking
  street invites invented signs.
- "One continuous shot with no cuts" stops H3 from inventing internal cuts (measured in `server/sv/albums.py`).
- The style lock paragraph is the song's header: the next shot starts with the same paragraph word for word.

## Pinned frames for the hybrid (untested)

A pin fixes the whole picture at that frame, not only the letters, so the pinned frame must be right everywhere. Code can't
draw this moving street, so here the hybrid is a repair pass: render once; if frame 46 (clip 1.92 s, song 41.92 s) or
frame 74 (clip 3.08 s, song 43.08 s) shows a wrong letter, repaint the correct lettering over that frame in code, matching
its perspective, then render again with the same prompt and seed, pinning the repaired frames with `MiniMaxH3AddGuide`
(`frame_idx` 46 and 74, `vae` the video VAE). When the backdrop itself is code-drawn or a still (a cover, a color field),
draw the pinned frames from scratch instead, and a 22-frame clip starting at frame 46 can pin the whole read. Either way,
check every frame between 1.85 and 4.90 s for spelling afterwards: words can still drift between pins.

## Checks for this clip

1. Frames 30–153 (1.25–6.40 s): read every word in every frame; any wrong letter while a word is meant to be readable fails.
2. Frames 0–29 and 154–191: no readable letters anywhere.
3. Phone size: the 360 px wide contact sheet still reads "COPPER RAIN" in the hold.
4. Beat: "COPPER" first visible within ±2 frames of frame 30 (song 41.25); the reflection ripple on frame 60 (song 42.50).
5. The final frame (after trimming, frame 179) is the next shot's first frame if the next shot continues the street.
