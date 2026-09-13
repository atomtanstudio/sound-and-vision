# Video creation, alignment and preview

The Video page generates background images through the connected OpenAI account and short MiniMax H3 clips through the existing Legion H3LIX API. Results attach to the selected song automatically. A scripted full-song kinetic MP4 pipeline is documented in [KINETIC_FILM.md](KINETIC_FILM.md). Finished-video export is not yet a browser control; audio-reactive visualizers and directed storyboards remain unimplemented.

## In the app

1. Choose a finished song, Kinetic lyric video, and 16:9 or 9:16.
2. Choose Slideshow or Video clips, set the count, and edit the visual theme if desired. **Generate images / Generate clips** submits missing slots. A selected slot has its own Generate / Regenerate button. Existing results remain visible until a successful replacement arrives.
3. H3 content can be thematic scenes, abstract motion graphics, animated text, or alternating scenes and animated text. Short text is a separate field. Generated lettering is baked into the clip and needs visual review; it is not the precisely synchronized sung-lyric layer.
4. **Align lyrics** reads the recorded audio. Then open **Edit lyric timing**, directly below Lyrics, to review and correct the alignment against the song waveform. Changing video lyrics or language invalidates the previous alignment without changing the original song.
5. Choose Automatic, Word pop, Slam, Rise, Word highlight, Line reveal or Calm. Automatic varies entrances by lyric line. Strength, font, size, color, position, shade and reduced-motion support remain editable.

Automatic alignment does not invent timing for unmatched words. Before alignment, only the title/background is previewed. Automatic alignment is evidence, not a guarantee of correct timing: missing lyrics, ad-libs, repetitions, scraped webpage text, vocal effects and overlapping singers need review. Original lyric text and repeated occurrences are preserved. Unmatched words have null timestamps until you time them manually. Flagged measured timings remain available to audition and correct.

## Correct timing on the waveform

The same editor is available for Music video, Kinetic lyric video, and Visualizer video with lyrics enabled. Automatic alignment remains the starting point.

1. Open **Edit lyric timing** under Lyrics. **Next to review** finds a line with missing, conflicting, or uncertain words; all lines remain selectable in the list, including lines with no timestamps.
   Each phrase in the left-hand list has an **Insert at playhead** button. Scrub to the phrase's vocal entrance, then click that button to place the entire existing phrase in one action. It keeps the playhead in place, preserves complete word spacing, and moves the phrase's lyric-sheet position when needed without duplicating it. For missing or invalid word timing, it creates a provisional, evenly spaced phrase block, bounded by the next phrase or song end and marked for review. Fine-tune the word times or use tap timing while listening. Undo restores the previous timing and lyric order. A fully timed phrase that would run past the song end is rejected rather than shifted away from the playhead.
2. Use the **arrow tool** to click or drag on the waveform and scrub the song. Switch to the **hand tool** to drag the waveform or lyric tracks left/right without moving the playhead or editing timestamps. Play/Pause, zoom, and the range slider remain available. Follow playback keeps the current position in view.
3. Drag a line block to move all its timed words together, preserving their spacing and pauses. Missing endpoints stay missing. Focus a block and use arrow keys for 0.05-second nudges, or Shift+arrow for 0.5 seconds.
4. Select a word to drag it separately or resize its start/end edges. Numeric start/end fields and **Set start/end at playhead** allow precise corrections. Clear an endpoint to remove its timing. Overlaps and words in the wrong order remain flagged for review.
5. For a missing or badly timed line, choose **Time this line by tapping**. Play the song, then click the Mark button (or focus it and press Space) as each word starts. Mark the line's end after the last word. Taps are temporary until that final mark; Cancel leaves saved timings unchanged. These are manual timings: each word initially ends at the next tap, so shorten word endings afterward where you hear pauses.

Undo/redo can revert a drag, a complete tap session, or a text edit. **Reset line** reverses timing adjustments since the most recent timeline text edit (or restores automatic timing if no text edits have been made). The detailed **Word timing** table remains below the waveform.

### Remove, add, and repeat lyrics

- Select a word, then **Delete word** to remove unwanted text and its timestamp. **Delete phrase** removes the entire selected line. All other words keep their current timing. Undo restores text and timing together.
- **Add phrase** accepts typed or pasted lyrics; each newline becomes a separate phrase. Choose a position near the playhead, before/after the selected line, or at the end of the sheet. New words start untimed and can be placed using tap timing or individual start/end controls.
- **Duplicate word** or **Duplicate phrase** opens a copy in the insertion form. Move the playhead to the new vocal entrance, keep **Reuse copied timing at playhead** checked, then insert. The copy retains word lengths and pauses and is flagged for review. This is useful for repeated words such as “Megalomaniac.” Uncheck reuse to place the copy's words manually instead.

Timeline text edits update the video lyric sheet and save a complete local timing snapshot, preserving existing corrections even after word indices change or the page reloads. They do not require full-song realignment. Editing the separate freeform lyric sheet or changing language still invalidates timing; **Align lyrics again** replaces manual timing with a new automatic pass.

Corrections save with the per-song browser draft and feed new previews and exports through the existing word-edit payload. They do not rewrite a previously rendered video or synchronize to another browser. The waveform is decoded locally from the selected editing audio, using a reduced sample rate and a small peak cache. A waveform load error leaves playback and numeric timing controls available.

### Live preview and vocal monitoring

The **Live lyric preview** shows the current line against a plain background and highlights the active word while playing or scrubbing, without rendering a video. It also marks untimed words and gaps between words so they can be reviewed.

Choose **Listen to → Vocals only** to hear the existing Demucs stem and view its waveform. This becomes available after local alignment or transcription has cached the stem for that recording. The untouched song remains the clock; the monitor follows its playback, seeks, volume, and pause state. Closing the timing editor, leaving the video page, or switching back to Original mix restores normal listening. A missing or failed stem falls back to the mix. No additional separation job starts, and exports always use the original soundtrack.

The authenticated `/api/takes/{takeId}/vocal-preview` endpoint reports availability; its `/audio` route serves the song's matching cached WAV with range support. The association comes from the exact source audio hash, never a client-supplied file path.

## Finding completed media

The **Library** sidebar page combines playable songs with completed guided music-video exports, visualizer exports (including retained local render history), and older film exports. It provides search, Music/Videos filters, inline playback, downloads, and editor handoff for supported modes. Each completed export remains a separate version. Trashed media and unfinished or missing video files are excluded, with an availability notice when a history source cannot be reached. Existing song management and generation controls stay on Music.

`/api/library/videos` reads completed music-video jobs and existing film manifests. Visualizer history comes from the existing `/local-api/visualizer-renders` service. Library is a view over those durable stores; it does not copy files or submit generation work.

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

The existing H3LIX API at `SOUND_VISION_H3_URL` (default loopback port 7310) owns the model graph. Motion requests use its fused Turbo workflow: native tier, Turbo On, provider-default four steps, 24 fps, top-k SLA sparse attention and Fast VAE. H3LIX routes this internally to its dedicated Turbo runtime. Sound and Vision does not maintain a second copy of the graph. Returned H3 audio is removed with FFmpeg. H3 can return a slightly longer clip than requested; the timeline uses the requested segment length, trimming the excess. Seamless loops and exact generated lettering are not guaranteed.

For audio-conditioned motion, supply `audioStart` and `referenceImageJobId` together. The image must be a completed image job for the same song and aspect. The server extracts the exact audio window from the original FLAC and submits both references to H3LIX Reference to Video. Provider-side final soundtrack mux is disabled because final composition uses the uninterrupted original song. `seconds` supports half-second durations. The precise planned cuts are separate integer frame boundaries, not model-generated edits. The full-film prompts use the official reference headers, including subject definitions and retention analysis.

The original audio element is the master clock. Preview uses explicit time/frame calculations for words, backgrounds, fades and kinetic transforms, including after seeks. Images divide the full song into equal frame spans (rounding differs by at most one frame); ten images across 180 seconds receive 18 seconds each. Clips repeat at normal speed and the final placement ends at the song's final frame. Background audio is always muted.

## Jobs, recovery and safety

- `POST /api/takes/{takeId}/video`: one image, clip or alignment request with caller idempotency key.
- `GET /api/takes/{takeId}/video`: persistent jobs and results for the song.
- `POST /api/video/jobs/{id}/retry`: retries a failed/cancelled part; completed parts are kept.
- `POST /api/video/jobs/{id}/cancel`: cancels queued work or an owned image/alignment operation. Once H3 is rendering, that clip finishes safely; queued clips remain cancellable. No global ComfyUI interrupt is sent.
- `GET /api/video/jobs/{id}/media`: authenticated immutable result file.

Jobs use the existing SQLite assistance_jobs table and recover as interrupted/failed after a backend restart. Explicit retry reattaches to a known H3 job via replayable events; completed H3 library outputs can be recovered after provider restart. An ambiguous submission with no returned ID is blocked from automatic resubmission to avoid duplicate work. H3 API submission and media recovery stay on the server; no provider credential reaches the browser.

Images serialize with cover generation through the shared account image semaphore. Clips hold Sound and Vision's music GPU lock, wait for H3 and Comfy queues, and defer to H3LIX's queue checks. Alignment has its own CPU queue. Successful assets survive partial failure and browser reload. The current app remains a private single-owner service.

## Storage and scope

Generated files, input records, provider checkpoints and alignment evidence live under `data/video/` on Legion. Editing settings/word corrections remain per-take browser drafts; local imports use IndexedDB. Drafts are not yet server-synchronized. Generated images/clips are server-persistent. JSON export is an editing manifest, not an MP4, and includes generated asset URLs plus word timings; imported media must accompany it on another device.

Visualizer video exports are available through the existing renderer. The guided [Music video](MUSIC_VIDEO.md) flow now assembles complete MP4s from sequential H3 scenes. The granular Kinetic lyric video background editor retains its existing controls. Experimental lip-sync performance remains gated.

## Checks

`npm run test:video`, `npm test`, `npm run build`, and `python -m pytest backend/test_video.py backend/test_api.py backend/test_assistance.py backend/test_library.py -q` cover timeline logic, word uncertainty, deterministic animation, API idempotency/authentication, original app behavior and build validity. Live checks cover an account-generated image, a native H3 scene clip, H3 typography, real song alignment and browser reload/seek behavior. Machine alignment results still require listening review.

With the development app running on port 5190, `node scripts/verify-lyric-timeline.mjs` checks waveform decoding, dragging/resizing, shared audio scrubbing, tap repairs, undo/redo, draft persistence, responsive layout, and the corrected export payload using an isolated library and seekable audio fixture. It does not submit real generation jobs.

Kinetic entrance math is adapted from Rich Gates's MaxMusic `render/engine.mjs` (MIT; notice in `docs/licenses/MaxMusic-MIT.txt`). Sound and Vision uses DOM word spans and the shared audio clock, not the old song-specific renderer. Model and package licenses remain separate from the app's Apache-2.0 license; consult each upstream model card before redistribution.
