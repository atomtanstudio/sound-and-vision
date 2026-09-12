# Two original songs and full-length films — 2026-09-10

User authorized autonomous production of two different new songs and finished
videos, plus a varied reusable visualizer collection. No reference song was used.

## Songs

| Song | Artist identity | Direction | Take |
| --- | --- | --- | --- |
| Forwarding Address | Rental Hours | Spacious trip-hop / alternative soul, female alto | c6bb67a6f3024be9ac2382ef4297250b |
| Small Repairs | The Sunday Repairs | Warm live-band roots rock / soul, male baritone | f08637d5b1e842eb981b64ff7028f35a |

Both requests, lyrics, original FLAC/MP3, source-generation records and acoustic
alignment are retained under `deliveries/two-films-20260910/`. Neither generator
reported a truncated score or semantic output. Source durations are 256.558667
and 202.878667 seconds respectively; exact values are measured from the audio,
not assumed from the requested arrangement length.

Forwarding Address uses eight original procedural visualizers, selected across
thirteen scenes. Frame-indexed audio analysis drives the rendered effect; scene
boundaries follow measured audio attacks. Kinetic words use separated-vocal,
Whisper and wav2vec2 phonetic timing, refined over full song sections.

Small Repairs uses a fictional repairman/singer with generated reference images
for the workshop, street, kitchen and canal. Its 22 planned shots are 5–15
seconds long, with eight audio-conditioned performance shots totaling about
71.6 seconds, interleaved with narrative scenes. Every shot uses the verified
H3LIX four-step fused Turbo profile. The completed singing pilot is reused.
The film soundtrack remains the original uninterrupted song; H3 provider audio
muxing is disabled to avoid introducing replacements or timing drift.

## Reproducible scripts

- `scripts/video/refine-song.py`: section-level phonetic refinement.
- `scripts/video/plan-small-repairs.py`: measured continuous scene plan.
- `scripts/video/run-music-video.py`: guarded, resumable H3LIX requests, with
  durable intent, request hashes, provider run IDs and immutable scene receipts.
- `scripts/video/compose-music-film.py`: exact-frame composition, optional
  kinetic lyrics, title bookends and continuous original-master soundtrack.
- `scripts/video/verify-film.py`: complete decode, exact frame count and
  original-audio correlation/offset checks.
- `scripts/video/visualizer-*`: original shader analysis/render/verification.

Server production root:
`/srv/ai/sound-vision/data/films/two-films-20260910/`.
The local delivery root mirrors its two song folders. Source video clips stay
in durable H3LIX and Sound and Vision production folders on Legion.

## Timing audit

Machine uncertainty flags are retained; they are not silently converted to
human-reviewed timing. Section refinement removes overlapping word assignments.
In Forwarding Address, the isolated zero-confidence leading "I" before "wrapped
the plates" landed in silence nearly three seconds before the phrase. The lyric
render omits that one unconfirmed prefix and records it in `renderOmissions` in
`alignment-render.json`; the canonical original lyrics and alignment remain
unchanged. The resulting render contains 251 timed words.

Final file-integrity verification does not constitute phoneme-perfect lip-sync
certification. Performance clips are driven by the exact song windows and are
visually reviewed for identity and singing motion; manual aesthetic review
remains possible from the delivered video.

## App integration verification

Video > Visualizer now offers all eight original presets and a response-strength
slider, using the actual shared music player. Background-generation buttons and
unused slideshow controls are hidden in this mode. Exported visualizer plans
contain a procedural background with no unused image/H3 generation requests.
Acoustic-alignment matching ignores trailing whitespace in the lyric text.

Browser checks: an idle shader is visible before Play; Forwarding Address at
71 seconds produced bass 0.792/onset 1 in the shader uniforms, running Web Audio
and no GL/UI errors. Shared-player graph/remount, pause/seek and portrait checks
passed. Eleven video behavior tests passed. TypeScript and Vite production build
passed using a fresh local output directory after the existing mounted dist
directory returned ENOTEMPTY while Vite attempted to clean it.

The full video export path is currently the reproducible production scripts;
the app accurately labels its Download plan action and does not claim its editor
button produces MP4 yet.

## Completed delivery

Both full-length films are published at
`http://127.0.0.1:5190/productions/two-films-20260910/index.html`.
The page provides native playback plus MP4, original FLAC, MP3 and lyrics for
each song. Durable masters remain in the project delivery folders and on Legion.

| Film | Frames at 24 fps | Audio duration | Original-master correlation | Measured offsets |
| --- | ---: | ---: | ---: | --- |
| Forwarding Address | 6,158 | 256.558 s | 0.999950 | 0 ms at all three sampled positions |
| Small Repairs | 4,870 | 202.878 s | 0.999964 | 0 ms at all three sampled positions |

Both 1920×1080 H.264 files passed complete decoding. Small Repairs footage was
generated at the native 1344×768 Turbo size, then cropped and scaled to 1080p;
the visualizers were rendered at 1080p. The source soundtrack is continuous,
encoded once as 320 kbps AAC for each MP4. Original lossless FLACs are included.

Browser verification exercised playback and distant seeks in both films with
zero reported dropped frames or media errors during the checks. All eight
download URLs returned HTTP 200 with their expected media types and lengths.
`browser-verification.json`, per-film verification/receipt files and contact
sheets retain the evidence. All 22 character scenes succeeded; their source
paths, hashes and request hashes are recorded in `scene-receipts.json`.

A final-line comparison for Forwarding Address found that Whisper's alternative
"looked at me" did not have stronger phonetic support than the written "looked
around". The canonical wording remains, with its uncertainty flag; the comparison
is retained as `final-line-comparison.json`. Do not describe either word timing
or generated mouth motion as human-certified or phoneme-perfect.

After confirming both H3LIX and the fused Turbo queue were idle, the production
model cache was released. Legion reported 27,430 MiB free GPU memory afterward;
services and other workloads were left running.
