# VRGDG Audio Drive + H3 Turbo test

## Singularity singing-scene correction — September 12, 2026

Singularity first-pass singing scenes now opt into `audioDrive: "vrgdg-vocal"`. This retains the eight-step Singularity model, sampler, attention settings, storyboard image and character references. The existing VRGDG node is also installed in the standard lab runtime on 8189; the fused Turbo runtime keeps its existing node and four-step mode.

The isolated vocal is cropped to the scene at its original pace and supplied continuously, including held notes, breaths and natural pauses. It is resampled before the scene-end trim, with silence added only for H3's extra frame-grid tail. Approximate word alignments no longer mute audio samples or issue syllable-by-syllable mouth commands in this path. The source vocal is used both as the audio reference and as the joint latent's locked audio, with zero audio denoise mask. Final previews and exports still use the unchanged original song.

This corrects two verified input defects in **Open Source Must Win**, scene 08 (70–80 seconds): its previous Singularity graph bypassed Audio Drive, and the word-based gate removed 30.47% of the isolated vocal's signal energy. In an estimated pause from 4.332 to 7.099 seconds into the scene, the original vocal RMS was 2024.65 on a signed 16-bit scale while the submitted gated audio was effectively silent. The corrected excerpt preserves that interval and has an exactly silent padded tail.

Validation covered synthetic sample preservation, the actual saved scene's audio excerpt and prompt, unchanged Singularity/fused sampling graphs, and provider metadata. No new image or video generation was submitted. Source-audio locking is not a guarantee of perceptually accurate lip sync; a new take still requires playback review. Existing takes and project manifests are retained. Sampled still-image review now preserves the submitted audio policy and does not treat uncertain word gaps as proven silence or certify exact lip sync.

The provider delta is `integrations/h3-singularity-first-pass/vocal-lock.patch`, applied after the first-pass integration. Deployment hashes and the guarded installation/rollback procedure are in `deliveries/vocal-lock-20260912/`. The remaining sections document the earlier fused-Turbo workflow.

Sound/Vision now offers **VRGDG Audio Drive + H3 Turbo · test** when creating a music video. It combines Jean Thompson's source-audio locking technique with the existing H3LIX four-step fused Turbo renderer. This is an adaptation of her construction technique, not the complete upstream Builder UI or its full graph.

Choose a song, create a new project, select this workflow, and enter a video direction. **Use industrial-metal direction** fills a contemporary male factory-worker concept tailored to *A Mouth Beneath the Skin*. Creating the storyboard also creates a fresh shared visual reference. Review that image before rendering.

**Storyboard chooses cuts** is the default. The planner receives the timed lyric phrases from the recording and may vary scene lengths and scene count to fit the action, with a 2–15 second limit and a shorter final tail when needed. The preferred length is guidance, not a fixed duration. **Fixed intervals** remains available. Cuts snap to 24 fps and cover the original song exactly once. Before any scene is rendered, the end-time control on each scene moves the boundary shared with the next scene; invalid adjacent durations are rejected. Once rendering starts, timing is fixed for that project.

Render one scene or the remaining scenes, then use the existing review/export workspace. **Regenerate scene** produces a new whole-scene candidate from the original character reference, the same audio interval and the edited direction. It does not add the previous video or neighboring frames as references. Earlier takes remain available, and a regenerated take must be selected explicitly.

## Actual rendering contract

- Model: `minimax_h3_fused_refdelta_r1024_turbo8_mystic07_int8_convrot.safetensors`, four steps, existing top-k sparse attention, video/audio sigma shifts 12/3, and Fast VAE. It does not select Singularity.
- Same explicit character file in every scene, SHA-256 checked before submission. Exactly one image and one audio excerpt are accepted by the provider adapter.
- Full original mix, cropped to each scene as stereo 44.1 kHz PCM. Recording-based vocal alignment supplies scene classification and local vocal/rest instructions. Vocal separation is used only for analysis; H3 and the final export still receive the full original mix. No word timestamps are inferred from scene length or lyric order.
- The unmodified upstream `VRGDG_MiniMaxH3AudioDrive` node feeds the original audio into the joint AV latent with an audio denoise mask of zero. The same waveform is supplied as the audio reference and passed through for the generated clip's soundtrack.
- H3's extra frame-grid padding is trimmed to the scene's exact frame count. Native 1344×768 or 960×544 output, 24 fps; no resizing or upscaling. Final assembly copies the selected encoded video and adds the original song once.
- No automatic scene repairs, AI visual scoring, color matching, titles or overlays. Source-audio locking does **not** guarantee correct mouth behavior or constant facial identity. Both still require playback review.
- Existing directed projects retain their renderer, timing and repair controls. The new mode is recorded in each project's plan and manifest; the result is rejected if the provider does not confirm Audio Drive.

## Implementation and deployment

Sound/Vision: `backend/film_audio_drive.py`, with opt-in branches in film creation, rendering and review. H3LIX: `server/audio-drive.mjs`, plus the small graph/job patch retained under `integrations/h3lix-audio-drive/`. Graph and model baseline checks preserve ordinary H3LIX requests unchanged.

Only the Audio Drive node is installed, via a read-only directory mount in the existing Turbo container. No whole upstream plugin, model download, package install or ComfyUI core change was needed. The node source, upstream notice and revision/hash metadata are retained under `integrations/vrgdg-audio-drive/`.

Current H3LIX release: `/srv/ai/h3lix-releases/20260911-audio-drive`. Previous release: `/srv/ai/h3lix-releases/20260910T150529Z`. Sound/Vision backend backups: `/srv/ai/sound-vision/updates/audio-drive-20260911-backup`. The prior Turbo compose file is `compose.pre-audio-drive-20260911.yaml` in `/srv/ai/research/h3-fused-turbo/deploy/`. Stop/restart only when the app and render queues are idle. Rollback can restore the old H3LIX release link and backed-up backend files; the independent unused custom node may remain installed.

## Verification on September 11, 2026

- H3LIX: 178 tests passed, including complete output-graph comparison with the existing fused Turbo recipe and unchanged quality baseline.
- Sound/Vision backend: 81 tests passed, including variable timing, cut edits, exact frame coverage, reference hash rejection, request isolation, nonduplicating retries, old-take retention and pixel-preserving final assembly.
- Existing offline browser suite: all 16 checks passed with the installed Chromium executable. TypeScript and the Vite build passed.
- Browser: correct song/take, new workflow, native size, editable industrial-metal direction and flexible timing confirmed; the new-project draft survived reload at `/video?film=new`.
- Deployed render and export: one three-second excerpt at 1344×768, 72 final frames, four steps, 35 seconds reported by H3LIX. No internal cut was detected by the existing heuristic. This engineering check used the previously approved reference; it is not a new creative full-song result.
- Installed node: zero audio mask, full video mask, latent fitting, and original waveform identity verified in the actual Turbo container.

Receipts, tests, graph provenance and the reproducible live check are in `docs/backend/evidence/audio-drive-20260911/`.

The prior 18-scene standalone test's saved graphs all name one identical female image and no reference videos. No male image was supplied to those graphs. A male-looking result is consistent with generation drift; the evidence does not establish the model's internal cause.

## Vocal-timing correction (version 2)

The first integration skipped alignment and assigned `performance` to every non-Story scene. This was a bug: a Performance project could label an instrumental intro as singing and also include vocal-delivery instructions in its scene prompt. The short integration test had verified graph execution and export, not this missing classification.

New Audio Drive projects now locate vocals before planning. Singing requires overlap with measured vocal words; each clip receives explicit local start, pause and ending-rest instructions. The full original mix remains the audio-drive source. Flexible storyboard cuts and later cut edits both recompute vocal classification and local offsets. Missing, mismatched or stale timing fails before a render can be submitted.

Older Audio Drive projects show **Update vocal timing**. This reuses timing only when it is traceable to the same audio and lyrics, or runs the existing isolated alignment process. It then corrects scene directions against the timed lyrics without changing the character image or cut points. Existing clips remain intact and are labeled as predating the correction. Use **Regenerate scene** to produce a new candidate; the old clip is not silently replaced.

For the reported 27-scene test, the first word begins at 60.814 s. All six clips ending at 60 s are therefore classified as instrumental, while the next clip waits 0.814 s before the first sung word. Timing confidence flags remain visible; recording alignment does not certify the generated face's behavior.
