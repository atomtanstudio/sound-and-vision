# Original audio-reactive visualizer library

Eight original GLSL compositions are available at `/visualizers/index.html`. They share a
renderer and audio interface, but use different geometry and motion. They are
project code under Apache-2.0. No community FragCoord shader code, shader-gallery
assets, paid presets, or externally hosted runtime scripts are included.

| ID  | Preset     | Structure                                              |
| --- | ---------- | ------------------------------------------------------ |
| 0   | Vault      | Perspective tunnel with flowing sculptural rings       |
| 1   | Mercury    | Procedural reflective liquid surface                   |
| 2   | Satellites | Depth-weighted particles and orbital paths             |
| 3   | Strata     | Multiscale topographic contour lines                   |
| 4   | Index      | Counter-rotating radial rings and fine ticks           |
| 5   | Silk       | Layered luminous ribbon surfaces                       |
| 6   | Facet      | Refractive crystal cluster with traced interior facets |
| 7   | Afterimage | Warm interference between warped wave fields           |

The contact sheet is `public/visualizers/previews/collection.png`; thumbnails
are actual GPU renders, not image-generator approximations. The source is
`public/visualizers/collection.frag`. The React-facing manifest and audio-frame
types are in `src/video/visualizers/library.ts`.

`src/video/visualizers/VisualizerCanvas.tsx` exports the app component. Its props
are `audioRef`, `active` (the selected song owns the shared player), `playing`,
`time`, `preset`, optional `strength` from 0 to 2, `reduceMotion`, `className`, and
`onError`. When inactive it still displays the selected shader using the supplied
preview time, with silent features; another song's playback cannot drive it.
Reduced motion freezes geometry and suppresses transient movement.

The component keeps one audio graph per HTML audio element in a global
`Symbol.for`-keyed WeakMap, which survives React view changes and HMR. The source
stays connected after visualizer unmount so normal music playback continues.
Only component event listeners and GL resources are disposed. AudioContext
resume is requested on the element's `play` event and is never awaited before
setting a source or showing playback controls. The shader clock uses the actual
audio element's currentTime while that source is active. Pause, seek, and source
changes clear residual band/onset data.

## Audio and rendering contract

The shader expects output resolution, exact timeline time, preset ID, next
preset ID, transition mix, response strength, normalized bass/mid/treble/onset
features, and overall energy. These are explicit uniforms. The collection does
not interpret lyrics or infer an emotion from the FFT. Selecting visual mood and
scene order remains an editorial decision.

The browser preview accepts local audio, the new Forwarding Address demo, and a
clearly labeled diagnostic rhythm. Browser playback supplies the animation
clock. Pausing freezes the song's timeline and current response; seeking moves
to the new time. The preview's automatic cycle is a simple 20-second audition
cycle. Finished renders use the analyzed onset timeline instead.

The offline analyzer uses FFmpeg to decode real PCM at 22,050 Hz, centered
2,048-sample Hann windows, and an original radix-2 FFT. Bands cover approximately
35–190 Hz, 190–2,400 Hz, and 2,400–10,000 Hz. Robust per-song normalization keeps
quiet and loud material useful without depending on a single absolute volume.
Attack is immediate, with 110 ms release; transient release is 130 ms. Silence
is suppressed. Onsets are measured positive spectral-flux peaks with a minimum
270 ms separation. **They are not a promised BPM/downbeat grid.** The legacy
`beats` field mirrors these measured onsets so the renderer can accept either
this analysis or a more sophisticated upstream beat tracker.

The frame data format is:

```json
{
  "version": 1,
  "fps": 24,
  "duration": 256.558685,
  "frames": [
    { "time": 0, "bass": 0, "mid": 0, "treble": 0, "onset": 0, "energy": 0 }
  ],
  "onsets": [0.75, 1.458333],
  "beats": [0.75, 1.458333]
}
```

`frames` must contain one entry for every output frame, from time zero. Feature
values are normalized to `[0,1]`. The renderer always uses `frameIndex / fps`
as its clock, not wall time, and never records live preview frame timing.

## Finished-video renderer

```sh
node scripts/video/visualizer-analyze.mjs \
  --audio path/to/song.flac --output path/to/analysis.json

node scripts/video/visualizer-render.mjs \
  --analysis path/to/analysis.json --output path/to/background.mp4 \
  --sequence 2,1,5,3,0,7,4,6 --interval 20 --fade 1.3
```

The renderer compiles the original GLSL with native macOS offscreen OpenGL,
streams RGB pixels directly into FFmpeg, and encodes H.264 at 1920×1080, 24 fps,
CRF 18 by default. It does not take browser screenshots per frame. The shader
source is shared with the portable WebGL2 preview. macOS CGL is the current
offline backend; Linux/EGL support has not been implemented or claimed.

The Mac sandbox must permit GPU access. Otherwise CGL can report that no
accelerated pixel format is available. On the verified machine the renderer
is Apple M5 Max, OpenGL 4.1 through Metal. No Legion generation GPU is involved.

Scene targets default to 20-second intervals. The nearest measured onset within
2.5 seconds is selected, and the crossfade completes at that onset. The original
audio is never chopped or stretched. Optional `--audio` muxes a continuous source
track; leave it out when the parent composition adds lyrics, titles, and audio.
`--width`, `--height`, `--duration`, `--sequence`, `--interval`, and `--fade` are
supported. A `.scenes.json` audit records boundaries and shader SHA-256; a
`.frames.csv` sidecar records the exact uniform values used on every frame.
The `.shader.frag` sidecar preserves the exact shader bytes used for that render,
so source edits during or after a render cannot invalidate its provenance.
Encoding uses an exact frame count, verifies the resulting count with FFprobe,
then atomically promotes the completed file. A fractional audio duration is
covered by the last full video frame, with at most one frame of visual padding.

This is a native shader library rather than a FragCoord embed. FragCoord's
reserved `u_audio` is an audio texture, while this library's `u_audio` is a
four-component analyzed vector; direct editor import needs a small adapter.
No source code has been sent to FragCoord as part of this package.

## Verification

Run `node scripts/video/visualizer-verify.mjs` with local GPU access. It compiles
the real collection, renders all eight presets, compares repeated identical
frames, checks image dynamic range, and verifies that changing the audio
features changes the pixels at the exact same timestamp.

The initial native check passed for all eight: mean absolute pixel differences
between quiet and active audio ranged from 5.569 to 33.429 on the 0–255 scale.
Repeated identical frames were byte-identical. Results and hashes are in
`public/visualizers/verification.json`.

Browser checks also passed with the actual Forwarding Address FLAC and the
diagnostic rhythm. WebGL2 compiled without errors. At an actual song timestamp
of 49.06 seconds, bass measured 0.452 and onset 0.094; the test rhythm reached
onset 1.0. All eight preset controls were present. Desktop, 9:16 portrait, and
390-pixel-wide layouts had no horizontal overflow. Audio was paused after QA.
A fractional-duration export test produced exactly 27 frames over 1.125 seconds,
with a continuous audio stream of exactly 1.1 seconds, as requested.
Known-frequency diagnostic tones at 86.13 Hz, 807.50 Hz, and 6,007.32 Hz were
correctly assigned to bass, midrange, and treble respectively.

A temporary React harness verified inactive rendering at exactly 7 seconds with
zero audio bands; active playback produced measured bass/onset values with the
shader clock within 5 ms of the player's sampled time. Unmount/remount reused
the identical graph, playback stayed unpaused, and the analyser remained active
(peak bin 213/255). Returning to inactive mode restored the supplied preview time
and zero bands without stopping the other track. Paused seeking set the shader
to exactly 100 seconds and cleared audio envelopes. No graph or GL errors were
reported. The temporary harness was removed after verification.

## Forwarding Address example

For **Forwarding Address — Rental Hours**, analysis uses the actual generated
FLAC, with 6,158 output frames and 509 detected spectral-flux onsets over
256.558685 seconds. The chosen sequence starts with Satellites, then Mercury,
Silk, Strata, Vault, Afterimage, Index, and Facet, followed by reprises.
The full background is delivered alongside the song; acoustic lyric alignment
and final typography are separate composition steps owned by the parent task.

Final background verification: H.264, 1920×1080, 24 fps, exactly 6,158 frames,
256.583333 seconds, 124,374,700 bytes. The complete file decoded without errors.
The renderer preserved the continuous source timeline and left a final visual
padding interval shorter than one frame. The rendered source snapshot and the
current library both have SHA-256
`b2c4acdab631761bff438db257201421f56ed6bd431c969e6ecd2342928281c1`.
The final contact sheet sampled from the encoded film is
`public/visualizers/previews/forwarding-address.png`.
