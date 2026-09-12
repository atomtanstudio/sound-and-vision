# Video creation, alignment and preview

The Video page generates background images through the connected OpenAI account and short MiniMax H3 clips through the existing Legion H3LIX API. Results attach to the selected song automatically. A scripted full-song kinetic MP4 pipeline is documented in [KINETIC_FILM.md](KINETIC_FILM.md). Finished-video export is not yet a browser control; audio-reactive visualizers and directed storyboards remain unimplemented.

## In the app

1. Choose a finished song, Kinetic lyric video, and 16:9 or 9:16.
2. Choose Slideshow or Animation loops, set the count, and edit the visual theme if desired. **Generate images / Generate clips** submits missing slots. A selected slot has its own Generate / Regenerate button. Existing results remain visible until a successful replacement arrives.
3. H3 content can be thematic scenes, abstract motion graphics, animated text, or alternating scenes and animated text. Short text is a separate field. Generated lettering is baked into the clip and needs visual review; it is not the precisely synchronized sung-lyric layer.
4. **Align lyrics** reads the recorded audio. Review uncertain and missing words in **Word timing**. Click a word to seek to its vocal context; edit its start/end in seconds. Changing video lyrics or language invalidates the previous alignment without changing the original song.
5. Choose Automatic, Word pop, Slam, Rise, Word highlight, Line reveal or Calm. Automatic varies entrances by lyric line. Strength, font, size, color, position, shade and reduced-motion support remain editable.

No word-count-based lyric timing remains. Before alignment, only the title/background is previewed. Automatic alignment is evidence, not a guarantee of correct timing: missing lyrics, ad-libs, repetitions, scraped webpage text, vocal effects and overlapping singers need review. Original lyric text and repeated occurrences are preserved. Unmatched words have null timestamps rather than invented ones. Flagged measured timings remain available to audition and correct.

## Alignment

`backend/alignment_runner.py` runs in `/srv/ai/sound-vision/.venv-alignment`, separate from the music and H3 environments, using CPU only:

- Demucs 4.0.1 `htdemucs` separates vocals. The untouched song is the video soundtrack.
- faster-whisper 1.2.1, Systran large-v3 pinned to `edaa852ec7e145841d8ffdb056a99866b5f0a478`, recognizes word evidence and locates canonical phrases.
- English uses wav2vec2 `WAV2VEC2_ASR_LARGE_LV60K_960H` CTC forced alignment inside those phrases and bounded gaps between recognized phrases. No word timestamps are interpolated across those gaps. Other selectable languages use stable-ts 2.19.1 phrase-constrained alignment; those paths have not received the English live verification.
- Exact canonical text is matched in sequence, preserving repeated line IDs. Low scores without strong independent corroboration, ASR disagreement, missing words, unsupported characters and overlap are flagged. Words recognized outside the canonical sheet are counted for review, not silently inserted.
- Vocal stems and recognition evidence are cached by SHA-256 of the original audio plus language/model revision. Lyric edits can reuse evidence without re-separating audio.

Torch/TorchAudio are pinned to 2.8.0 CPU. TorchAudio's alignment API was deprecated in 2.8 and removed in later releases; do not casually upgrade this runtime. Sources: [TorchAudio forced alignment](https://docs.pytorch.org/audio/2.8/tutorials/ctc_forced_alignment_api_tutorial.html), [stable-ts](https://github.com/jianfch/stable-ts), [Demucs](https://github.com/facebookresearch/demucs), [large-v3 model](https://huggingface.co/Systran/faster-whisper-large-v3).

Install models with `deploy/download_alignment.py` inside the isolated runtime. `alignment.lock.json` records the model revision and checkpoint hashes; `deploy/legion-alignment-freeze.txt` records the tested dependencies. Generation runs offline after model installation. Account images still use the authenticated OpenAI service.

## Backgrounds and timing

Image requests include song/theme/lyric context, distinct composition prompts, aspect and a quiet lyric area. Original provider PNGs are preserved; a center crop produces a 1920×1080 or 1080×1920 preview canvas without stretching. Source pixel dimensions remain in each result. The provider's image size can differ from the canvas; this is not a claim of native 1080p detail or a specific image-model version.

The existing H3LIX API at `SOUND_VISION_H3_URL` (default loopback port 7310) owns the model graph. Motion requests use its fused Turbo workflow: native tier, Turbo On, provider-default four steps, 24 fps, top-k SLA sparse attention and Fast VAE. H3LIX routes this internally to its dedicated Turbo runtime. Sound/Vision does not maintain a second copy of the graph. Returned H3 audio is removed with FFmpeg. H3 can return a slightly longer clip than requested; the timeline uses the requested segment length, trimming the excess. Seamless loops and exact generated lettering are not guaranteed.

For audio-conditioned motion, supply `audioStart` and `referenceImageJobId` together. The image must be a completed image job for the same song and aspect. The server extracts the exact audio window from the original FLAC and submits both references to H3LIX Reference to Video. Provider-side final soundtrack mux is disabled because final composition uses the uninterrupted original song. `seconds` supports half-second durations. The precise planned cuts are separate integer frame boundaries, not model-generated edits. The full-film prompts use the official reference headers, including subject definitions and retention analysis.

The original audio element is the master clock. Preview uses explicit time/frame calculations for words, backgrounds, fades and kinetic transforms, including after seeks. Images divide the full song into equal frame spans (rounding differs by at most one frame); ten images across 180 seconds receive 18 seconds each. Clips repeat at normal speed and the final placement ends at the song's final frame. Background audio is always muted.

## Jobs, recovery and safety

- `POST /api/takes/{takeId}/video`: one image, clip or alignment request with caller idempotency key.
- `GET /api/takes/{takeId}/video`: persistent jobs and results for the song.
- `POST /api/video/jobs/{id}/retry`: retries a failed/cancelled part; completed parts are kept.
- `POST /api/video/jobs/{id}/cancel`: cancels queued work or an owned image/alignment operation. Once H3 is rendering, that clip finishes safely; queued clips remain cancellable. No global ComfyUI interrupt is sent.
- `GET /api/video/jobs/{id}/media`: authenticated immutable result file.

Jobs use the existing SQLite assistance_jobs table and recover as interrupted/failed after a backend restart. Explicit retry reattaches to a known H3 job via replayable events; completed H3 library outputs can be recovered after provider restart. An ambiguous submission with no returned ID is blocked from automatic resubmission to avoid duplicate work. H3 API submission and media recovery stay on the server; no provider credential reaches the browser.

Images serialize with cover generation through the shared account image semaphore. Clips hold Sound/Vision's music GPU lock, wait for H3 and Comfy queues, and defer to H3LIX's queue checks. Alignment has its own CPU queue. Successful assets survive partial failure and browser reload. The current app remains a private single-owner service.

## Storage and scope

Generated files, input records, provider checkpoints and alignment evidence live under `data/video/` on Legion. Editing settings/word corrections remain per-take browser drafts; local imports use IndexedDB. Drafts are not yet server-synchronized. Generated images/clips are server-persistent. JSON export is an editing manifest, not an MP4, and includes generated asset URLs plus word timings; imported media must accompany it on another device.

Visualizer and Music video tabs remain setup paths. Neither claims a finished audio-reactive visualizer, directed film, singing lip sync or export.

## Checks

`npm run test:video`, `npm test`, `npm run build`, and `python -m pytest backend/test_video.py backend/test_api.py backend/test_assistance.py backend/test_library.py -q` cover timeline logic, word uncertainty, deterministic animation, API idempotency/authentication, original app behavior and build validity. Live checks cover an account-generated image, a native H3 scene clip, H3 typography, real song alignment and browser reload/seek behavior. Machine alignment results still require listening review.

Kinetic entrance math is adapted from Rich Gates's MaxMusic `render/engine.mjs` (MIT; notice in `docs/licenses/MaxMusic-MIT.txt`). Sound/Vision uses DOM word spans and the shared audio clock, not the old song-specific renderer. Model and package licenses remain separate from the app's Apache-2.0 license; consult each upstream model card before redistribution.
