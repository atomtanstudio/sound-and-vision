# Video integration verification — 2026-09-10

Implemented and deployed to `/srv/ai/sound-vision`; browser application at `http://127.0.0.1:5190/video`. Backend rollback copy: `/srv/ai/sound-vision/backups/video-20260910T102352`.

## Real provider results

- OpenAI account image job `bbe99f8b03294c68bcba641a24148540`: succeeded. Original 1672×941 PNG, retained with an exact 1920×1080 crop for preview.
- H3 scene job `f11dde372a2247db931e115f680e043a`: succeeded and attached to the song automatically.
- H3 typography job `4463c9ba-f96a-4858-94b2-74606a989ea3`: submitted from the browser and succeeded. The sampled frame visibly spells EMERGE. FFprobe: H.264, 1344×768, 24 fps, 4.458333 seconds, video stream only. Requested four-second timeline placement uses four seconds.
- Both H3 clips and the image remain attached after backend restart and browser reload. No separate upload was required.

## Lyric timing remains reviewable, not certified exact

- Take `331ed5fa46b242c49ef211729324f5bc`, final alignment job `b1d791639be94bcea408b98a177a8b10`: 229 canonical words, 111 flagged, 39 without reliable times. The lyric sheet contains a title label and pasted webpage recommendations. Additional differences arise from recognition uncertainty and repeated vocals.
- Take `e26625a7e5584167b51f3be1b95eeb22`, final alignment job `3b857d11adaa48278d663aea268e370a`: 196 canonical words, 116 flagged, 22 without reliable times. ASR recognizes the opening verse but struggles with later sung phrases. Phonetic alignment supplies candidate boundaries in bounded gaps without replacing canonical text.
- Flag counts are conservative heuristic review indicators, not calibrated probabilities of error. Recognition disagreement does not establish that the saved lyric is wrong.
- Earlier whole-song attention alignment drifted and was replaced with recognized phrase anchors plus phonetic forced alignment. Missing words are never assigned proportional timing. Original lyrics/audio were not rewritten.
- Word seek selected the correct audio master. Preview at 42.9229 seconds highlighted the word whose measured interval contained that time; H3 audio stayed muted and only one song audio element existed. This verifies clock wiring, not perceptual correctness of every word.

## Checks passed

- 20 backend tests: API authentication, idempotency, immutable asset output, conflicting requests, cancellation, ambiguous H3 submission recovery, repeated words, missing/invalid timing and corroboration logic, plus existing music/library/assistance behavior.
- 10 timeline/kinetic tests; 12 existing app regression groups; TypeScript and production build.
- Browser: generation submission, per-song results, edit/reset of word times, audio/clip seek, reduced motion, portrait/landscape, light/dark, reload recovery, desktop and 390/320-pixel layouts. No app console exceptions. The narrow viewport's layout was checked after responsive transitions settled.
- Final database quick_check: ok. Final music/OpenAI health: connected. No active jobs before the final backend restart.

Screenshots retained in `/private/tmp/sv-generation-final-dark.png`, `/private/tmp/sv-generation-final-light.png`, `/private/tmp/sv-generation-mobile-light.png`, and `/private/tmp/sv-generation-mobile-dark.png`.

Remaining at that checkpoint: listening review/correction of uncertain words for exact sync; MP4 composition/export; functional audio-reactive visualization and directed video production. H3 lettering is a generated design element, independent of the editable sung-lyric layer.

## Good Company full-song test — 2026-09-10

The scripted full-film pipeline now exports `Good-Company-Guest-Policy.mp4`.
See [KINETIC_FILM.md](KINETIC_FILM.md) for reproduction and scope. The browser
editor's export control still produces its editing manifest.

- 193.416667-second 1920×1080, 24 fps H.264 video; exactly 4,642 frames.
- Thirteen unique H3 clips cover the complete song with no repeated footage.
  The completed quality pilot was retained. The other twelve used the live
  H3LIX fused Turbo graph, four steps, reference image and actual song excerpts.
  Verified completion times: 100–120 seconds, mean 115 seconds per Turbo clip.
- Twelve cuts selected from measured beats, at most 19.33 ms from a detected
  beat after frame quantization. Clip boundaries are continuous.
- All 203 canonical words have acoustic timings; no overlaps or missing times.
  ASS onset rounding is at most 5 ms. Sixty words retain machine-review flags;
  these are not represented as having passed a human listening review.
- Opening and closing identify Guest Policy / Good Company. Sampled final
  frames cover opening, verses, choruses, bridge and closing. Typography remains
  a separate timed layer over the generated H3 footage.
- Complete video decoding passed. AAC audio duration is 193.398 seconds.
  Decoded audio correlation to the original master at 8 kHz is 0.999928;
  offset checks near 13.54, 90.90 and 166.32 seconds all measured 0 ms.
- The copied local MP4 matches the Legion SHA-256 receipt. Final file size is
  156,331,988 bytes. Receipts, the shot plan and editable ASS/JSON lyric timing
  are saved beside the video in `deliveries/good-company-20260910/video/`.
- Twenty-one backend regression tests passed after audio-reference validation
  and the Turbo/default changes. The provider graph remains owned by H3LIX.
