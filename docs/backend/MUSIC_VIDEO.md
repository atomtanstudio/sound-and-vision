# Guided music videos

The default for a generated or imported library song is a guided scene-based music video. It sends no audio reference to H3. Prompts avoid singing, speech, mouthing and microphones and favor environments, objects, abstraction and distant figures. Prompt compliance is imperfect; review the resulting video. This does not enable the older experimental performance/lip-sync pipeline.

1. Choose a soundtrack. The backend measures duration from the saved delivery.
2. Edit the suggested theme. Suggestions use the title, style and supplied lyrics; they do not claim to listen to or classify the recording.
3. Choose full-song footage or a smaller repeating set. Enable on-screen lyrics if desired; manually enter or review a transcription.
4. Prepare video writes an internal storyboard with the configured text provider. No GPU video generation starts here. The resulting count is shown for review.
5. Create video aligns lyrics when necessary, generates clips one at a time, then exports the full MP4. The render request preserves the entire lyric sheet, including untimed lines. Missing or conflicting word timestamps are shown before rendering. Correct them in **Edit lyric timing**, or explicitly select **Omit words with unusable timing** to render only the remaining timed words. Omission is off by default, never invents timestamps, and does not change the saved lyrics. Completed exports record the omitted-word count. Existing user-edited word timing is preserved.

The waveform editor can delete words/phrases, insert pasted phrases, or duplicate repeated lyrics while preserving the surrounding timings. Lyric-only changes retain the prepared storyboard and completed clips; the next export validates against the edited lyric sheet and rebuilds the lyric overlay. Previous exports and the saved storyboard retain their original text. Automatic alignment caching includes the lyric text and language so a new lyric sheet cannot reuse an older word list. See [editing lyrics and timing](VIDEO_EDITOR.md#remove-add-and-repeat-lyrics).

Advanced controls select 5-, 10- or 15-second clips, landscape/portrait 1080p, cuts, half-second dissolves or continued scene pairs. Dissolves count their overlaps when calculating coverage. Continued pairs use the prior clip's selected final frame as the next clip's start image; every other clip begins a new scene. Matching endpoint images does not guarantee motion continuity. Repeating footage uses the configured transitions and trims the final placement to the song duration. There is no automatic beat detection or audio-based genre inference in this flow.

The assembly worker normalizes video without provider audio, builds frame-exact bodies and short blend segments, then combines them with the original continuous soundtrack. On-screen lyrics use timed karaoke highlighting rendered by libass. The existing granular kinetic editor and its motion styles remain separate. Exports are H.264/AAC with fast-start metadata and preserve the song length to within one video frame.

## Installation

Requires the configured text provider, the existing H3LIX API (`SOUND_VISION_H3_URL`, default loopback port 7310), FFmpeg and ffprobe. Turbo On, native tier and nativeAudio Off use the H3 service's existing workflow. Continuation uses Frames to Video with a start-frame image. The app formats plain storyboard prose into the official T2VA three-field structure; continuation prompts prepend the official I2VA first-frame instruction. Provider validation stays enabled. Existing saved plans receive this formatting on render/resume, so a formatting fix does not require another storyboard. No second model graph is bundled. Lyrics require the separate `.venv-alignment` runtime unless complete reviewed timing is supplied, and an FFmpeg build containing the `ass` filter. See [self-hosted setup](../../SELF_HOSTED.md).

## Persistence and recovery

SQLite `assistance_jobs` records theme, plan and render jobs. Immutable plan snapshots and child-job IDs are under `data/music-videos/<planId>/`; H3 inputs, checkpoints and clips use the existing `data/video/<childId>/` folders. Each completed export has its own render-job folder. A backend restart marks active jobs interrupted; Resume video reuses finished clips and reattaches to known H3 runs. An ambiguous provider submission without a returned ID is refused rather than automatically duplicated. Stop after current clip never sends a global ComfyUI interrupt. It finishes any active clip before stopping remaining work; assembly already underway may finish.

Theme and plan edits invalidate the pending Create video action until a new plan is prepared. Successful files remain available regardless of subsequent edits. Browser drafts retain controls; server jobs retain the approved snapshot. No external publication happens automatically.

## API and tests

All routes use the existing bearer authentication and single-owner service boundary:

- `GET /api/takes/{takeId}/music-video`: saved jobs and results.
- `POST /api/takes/{takeId}/music-video/theme`: propose a theme.
- `POST /api/takes/{takeId}/music-video/plan`: prepare a reviewable plan.
- `POST /api/takes/{takeId}/music-video/render`: execute a successful same-song plan with optional reviewed word cues and an optional `lyrics` override for this export. Omitting `lyrics` keeps the plan's original sheet. Ownership and exact word matching are still enforced.
- `POST /api/music-video/jobs/{id}/stop`: finish the current clip, then stop.
- `GET /api/music-video/jobs/{id}/media`: play the finished video inline; `?download=1` downloads it.

Run `python -m pytest backend/test_music_video.py backend/test_video.py -q` and `node scripts/verify-music-video.mjs`. Backend tests cover full-duration scheduling, actual FFmpeg cuts/blends/repeats and lyric rendering, plan ownership, idempotency and recovery without regenerating finished clips. Browser fixtures cover plan review, edited-theme invalidation, failure/resume, downloads and responsive layout. Real H3 visual quality and transition smoothness still need user testing before release.

For the provider contract regression, set `SOUND_VISION_H3_VALIDATOR` to H3LIX’s `server/prompting.mjs` and run `python -m pytest backend/test_h3_prompts.py`. This imports the actual provider validator and checks both text-to-video and first-frame prompts without submitting a render.
