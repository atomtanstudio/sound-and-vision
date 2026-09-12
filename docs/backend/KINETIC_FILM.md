# Full-song kinetic film pipeline

The Good Company production uses one continuous approved song master, acoustic
word alignment, measured beat cuts, thirteen separately generated H3 backgrounds,
and FFmpeg/libass typography. Artist: **Guest Policy**. The source recording is
193.398667 seconds. No reference song was used to create the music.

This is a reproducible server workflow, currently driven by scripts. The browser
editor still exports an editing manifest rather than submitting this full render.

## Inputs and stages

1. `backend/video_analysis.py SOURCE.flac analysis.json` tracks beats using
   librosa and refines nearby low-frequency attacks. Cuts are selected near
   fifteen seconds and quantized to native 24 fps. The last section covers the
   exact remaining audio; no footage is looped to fill gaps.
2. The existing alignment job separates vocals with Demucs and obtains Whisper
   recognition plus phonetic timing. `scripts/video/refine-good-company.py`
   aligns full verses/choruses/bridge sections as monotonic acoustic paths to
   prevent independently aligned line overlaps. It preserves all 203 canonical
   words. It retains uncertainty flags rather than pretending machine confidence
   is a listening review. No word times are inferred from lyric length.
3. `scripts/video/plan-good-company.py` saves a shot plan and prompts. A single
   generated image defines chrome, black lacquer, smoked glass and scarlet light.
   Each H3 job receives the corresponding excerpt of the actual approved song.
4. `scripts/video/run-film.py --plan PLAN.json --root /srv/ai/sound-vision`
   submits each slot through Sound/Vision. It locks against duplicate runners,
   uses stable request IDs, records actual retry IDs in `job-map.json`, and
   persists progress in `batch-status.json`. Successful clips are reused.
5. `scripts/video/render-kinetic-film.py` validates non-null, ordered acoustic
   words, crops native H3 frames to 16:9 without stretching, trims each shot to
   an exact integer frame count, then concatenates them and adds kinetic text.
   The original continuous FLAC supplies audio, encoded once to 320 kb/s AAC.

## H3 workflow

Motion defaults to the **existing H3LIX fused Turbo workflow**. The deployed
2026-09-10 profile uses
`minimax_h3_fused_refdelta_r1024_turbo8_mystic07_int8_convrot.safetensors`, four
sampling steps, top-k SLA at 10%, sigma shifts, Fast VAE and native 24 fps.
H3LIX selects the runtime and protects its queues. These are observed deployment
settings; its canonical graph remains owned by H3LIX.

The completed opening pilot used the older quality request and is retained.
The second quality job was cancelled after verifying it was the only running
prompt, when Rich requested Turbo. Remaining request IDs use `-turbo-v1`.

The original pilot's provider audio mux failed after successful video generation.
Its complete 379-frame video was verified with FFprobe and recovered without
resampling. `recovery-receipt.json` and the original failed checkpoint are kept
with that job. Subsequent requests use audio as conditioning but disable the
redundant provider final-audio mux; final film assembly uses the untouched master.

## Rendering

The rendering runtime is `/srv/ai/sound-vision/.venv-alignment`. In addition to its
alignment dependencies, it has librosa 0.11.0, SciPy 1.16.2, Pillow 12.3.0 and
fonttools 4.59.1 with WOFF support. FFmpeg must include libass and libx264.

```sh
/srv/ai/sound-vision/.venv-alignment/bin/python scripts/video/render-kinetic-film.py \
  --plan /srv/ai/sound-vision/data/films/good-company/film-plan.json \
  --alignment /srv/ai/sound-vision/data/films/good-company/alignment-sections.json \
  --font /srv/ai/sound-vision/data/films/good-company/fonts/SV-Manrope.ttf \
  --media-root /srv/ai/sound-vision/data/video \
  --audio /srv/ai/sound-vision/data/runs/55c92ee597594740997721f987b1cfa3/attempt-001/audio.flac \
  --output /srv/ai/sound-vision/data/films/good-company/Good-Company-Guest-Policy.mp4
```

`--ass-only` validates timing and builds typography without requiring completed
H3 footage. The current composition supports 1920×1080. Manrope ExtraBold is
instantiated from the project's existing variable font and renamed SV Manrope.
Its OFL license accompanies the font. Pillow em metrics are adjusted to libass's
ascender-to-descender sizing so independently animated words align correctly.

Opening/closing titles show the artist and song once each. Sung words use
alternating pop, rise/rotate and compressed slam entrances at their measured
onsets. The active word uses a scarlet accent and then settles to white.

Normalized clips are cached against source SHA-256, dimensions, fps and frame
count. Too-short footage is rejected rather than extended or silently looped.
Final checks enforce frame count and audio duration. The receipt records the
master checksum, output checksum, native/generated clip count and timing method.
Rendered 1080p is a delivery canvas; H3's observed landscape source is 1344×768.

## Timing limits

Beat-cut error is at most half a 24 fps frame. ASS stores hundredths of a second,
so word onsets are rounded by at most 5 ms before frame sampling. Generation is
conditioned by music, but that alone does not guarantee every internal object
movement lands on a beat. The edit boundaries are measured independently.
Automatic vocal alignment remains evidence to review; low confidence and ASR
disagreement are retained in the render's `lyrics.json` audit.
