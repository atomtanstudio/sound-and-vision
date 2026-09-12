# Blue Hour: original audio-reactive shader study

Created for Rich's example of a melancholy, low-fi/ambient song: blue-gray
color, slow layered movement, soft illumination and restrained reactions.
The shader is new project code; no community gallery shader was imported.
It follows Sound/Vision's Apache-2.0 license. The included Manrope font retains
its OFL license.

Preview: `/shader-studies/blue-hour/index.html` on the existing Sound/Vision
development server. `blue-hour.html` is the downloadable, self-contained
version: shader, runtime and font are embedded; a chosen local song stays in
the browser. `blue-hour.frag` is the editable shader source.

The composition is three wind-folded translucent sheets with parallax, soft
contour illumination, fine threads and grain. Current low-frequency energy
controls expansion, deformation and highlight strength. A rise above older
low-frequency energy adds a visible pulse to the folds and their contours.
Upper-frequency energy affects the fine texture. The Strength slider ranges from
25% to 200%, with 100% as the default; colors remain in the blue-gray palette.

## Mood and musical response

Mood is an art-direction choice informed by a song brief, genre, lyrics and
human preference; the study does not claim to infer melancholy from an FFT.
Audio measurements control movement within that selected visual direction.
Other directions can use different geometry, color, pacing and response curves.

The study uses a real Web Audio analyser and a 512×512 history texture. The
shader reads the blue/raw-FFT channel documented by FragCoord. Its bass
band is compared against older samples to preserve attacks instead of averaging
them away. This is an onset response, not a BPM estimator or a beat grid. The preview
also fills the waveform channel; its unused red channel duplicates raw FFT rather
than pretending to reproduce FragCoord's unspecified perceptual weighting.

With a song loaded, `u_time` follows the media element's playback time. Pausing
freezes motion and the current audio history. Seeking clears history so the prior
position does not contaminate the new one. A true offline video renderer must
precompute FFT/history at a fixed sample cadence and reconstruct it at every
seek/frame; this live study does not yet implement that export path.

The 72 BPM test rhythm is a small synthesized diagnostic (kick plus quiet
D-minor tones), explicitly labelled as a test. It is not a generated song.
The local connected preview can also play the approved Good Company take.

## FragCoord

The shader declares `u_resolution`, `u_time`, and `u_audio` and is written for
FragCoord's documented GLSL input format. It compiles and renders in the local
WebGL2 study. A live FragCoord-editor compatibility check is **not yet verified**:
automatic approval review rejected transferring the new project source to that
external editor without more explicit destination approval. No code was pasted
there and no shader was published.

The optional custom `u_response` uniform controls strength. If unset (zero), the
shader uses the normal strength of 1.0. The local response-off toggle feeds a silent
audio texture, which removes all audio-driven deformation and illumination.

Sources: [uniforms and audio](https://fragcoord.xyz/docs#uniforms-rendering),
[the author's editor overview](https://mini.gmshaders.com/p/fragcoord).

## Rebuild

```sh
node scripts/video/build-shader-study.mjs
```

The public study consists of `index.html`, `study.js`, `blue-hour.frag`, the font
and its license. The build script embeds those in `blue-hour.html`. None of these
files changes the existing video workspace or backend generation jobs.

## Verification — 2026-09-10

- WebGL2 compilation and rendering passed in the connected preview and the
  standalone `file:` page; no shader errors and WebGL `getError()` returned 0.
- The approved Good Company audio played through a real analyser. In the
  standalone file test, 62 audio-history frames were sampled by 2.085 seconds;
  peak normalized bass energy was 0.621. The synthetic test was checked separately.
- At the same paused song timestamp, disabling audio response changed the canvas
  pixels, confirming that the shader uses measured audio rather than time alone.
- Both 16:9 and 9:16 rendered. The portrait canvas settled at 480×855 on desktop
  and 310×552 at a 390-pixel viewport; no horizontal overflow was observed.
- File selection now exposes the player even when automatic playback is blocked.
  Pressing its native Play button successfully starts both playback and analysis.
- Runtime and builder passed `node --check`. The builder checks that the script
  and font embed points exist and rejects leftover external script/font references.

This is a working preset study, not an integrated visualizer export pipeline.
Offline repeatable audio analysis, automatic visual-direction selection, lyric
compositing and final-video export remain separate implementation work.

### Audio-response correction

User review found the first version's response too subtle. Its pixel-difference
test established audio connectivity but did not establish perceptually useful
movement. Reduced analyser smoothing from 0.72 to 0.28, replaced the shader's
four-sample averaged bass with current bass plus an onset comparison, increased
fold expansion/contour illumination, and added the Strength slider.

Verified Good Company at playback seconds 46–50.6: approximately 29.6 rendered
frames/second, running audio context, bass energy 0.529–0.766, and no shader
errors. Captured test-rhythm states showed visibly different fold positions and
contour brightness. Readback captures stall the GPU, so their capture cadence is
not used as a measure of playback smoothness or synchronization accuracy.

Regression checks passed: paused canvas and playback time remained unchanged;
seeking cleared prior audio history; response-off removed the audio effect;
25%, 100%, and 200% produced progressively stronger illumination at the same
paused song timestamp. The 390-pixel portrait layout had no horizontal overflow.
