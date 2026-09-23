# Song Reactive Visualizer

The user starts with a finished song, its genre/mood, lyrics and optional creative notes. There is no initial visualizer picker. The app creates one cohesive photographic artwork and fits measured audio motion inside its listening object. The saved video kind remains `visualizer`; the optional Classic collection retains its existing settings.

## User workflow

1. Open **Video → Song Reactive Visualizer** and select a finished library take.
2. Review the prefilled genre/mood and lyric sheet. Add any important era, place or visual details, then choose **Create song artwork**.
3. Review the generated artwork and its explanation. **Create another version** preserves previous versions.
4. Choose **Preview motion** for an eight-second sample, then **Watch preview**. This uses the same server renderer as the full video. The editor's initial image is explicitly labeled as an artwork preview.
5. Choose **Render video** for the full selected soundtrack. The finished MP4 is available in the Video page and Library.

Lyrics guide the artwork even when **Show lyrics** is off. The photographic recipe currently requires that switch off; overlaid lyric animation remains available in the classic workflow. Changing frame shape requires artwork composed for that shape.

## Automatic direction and artwork

`backend/song_reactive.py` owns jobs under `/api/takes/{takeId}/reactive-artwork`. The app and `scripts/video/create-reactive-artwork.py` call the same `create_artwork` pipeline.

The connected OpenAI writing/vision provider reads the song's title, genre, description, lyrics and notes. It sees three bundled, Sound/Vision-generated quality references and fills the bounded `CreativeBrief` schema in `backend/visualizer_brief.py`: a specific hero object, setting, lighting, selective props, exact title layout, palette and motion treatment. Reference choice is internal; it does not appear as a preset picker. The song's own mood and era govern the new scene. These are interpretations of supplied text, not claims to have listened or isolated instruments.

A fixed prompt composer adds the photographic materials, coherent composition, blank reactive glass and typography requirements. The writing model cannot rewrite away those requirements. Title lines must reproduce the actual song title, allowing only case and whitespace changes. The selected reference is sent to the connected image tool with that complete brief. No third-party reference photos or unlicensed renderer source are bundled.

The vision provider inspects the actual generated image, reads its visible title and locates the glass's four interior corners. Validation checks title identity, reported quality, confidence, convex geometry, usable area, display proportions and matching surface IDs. These checks can reject a visibly unsuitable result; a provider score is not a substitute for the user's aesthetic judgement.

This recipe requires the connected OpenAI image provider because it uses image references. Existing local image presets do not support this contract and fail with a clear message rather than silently omitting the reference. The app does not switch providers or introduce an API-key fallback.

Prompts, structured brief, original image bytes, image receipt, registration, image SHA-256 and final scene are retained per version. Failed registration can reuse the retained image through the verification CLI. An uncertain image submission cannot automatically request another image. Song text and image lettering are creative data, not tool instructions.

## Original photographic renderer

New scenes declare `renderer: reference-player-v1`. `scripts/video/reference_player.py` is a portable version of the original approved American Soviets and DreamPop renderers, with the successful review adapter's perspective placement and palette tinting. It contains our original analysis and drawing code, with no standalone-path dependency.

The analyzer decodes the original soundtrack to 24 kHz stereo and measures centered 2048-sample windows at 30 fps. It retains 48 logarithmic frequency bands from 40 Hz to 11 kHz, stereo levels, bass, energy, onsets and an actual sampled waveform. The director selects the detailed phosphor spectrum or the flowing DreamPop ribbon treatment. These are frequency and amplitude measurements, not separated instruments or an invented beat grid. Motion stays inside the registered glass; the surrounding artwork is stationary.

Both motion previews and full exports run this same Pillow renderer on the server. Output is 1920×1080 or 1080×1920, 30 fps, H.264/libx264 CRF 18 with 320 kbps AAC from the original audio. There is no automatic gain adjustment in this path. Configured soundtrack fades use source time, including when a preview starts inside the fade. A preview begins at the earlier of 30 seconds or one quarter of the selected duration and lasts up to eight seconds. The displayed total remains the full selected soundtrack duration.

The queue fetches only a saved artwork job belonging to the take. It verifies take ownership, frame shape, geometry and image SHA-256 before starting the worker. It accepts no caller-supplied image URL. Final MP4 promotion requires audio presence/duration, expected dimensions and frame-count verification; exact-duration trimming may omit one final frame. Source audio, analysis, progress, logs and receipts remain with each job.

Legacy song scenes and classic visualizers retain their 24 fps analysis/shader paths. Old saved export requests without song mode keep their previous serialization. The original 24-band song shader remains for those saved scenes; it is not the renderer used by the new photographic recipe.

## Installation and verification

Install the backend module, brief composer and `backend/visualizer_references/`, along with the API route and image queue registration. Install the matching export API/worker, `reference_player.py`, shared scene/schedule/audio-fade modules and compiled renderer bundle. Build the bundle with `node scripts/video/build-visualizer-renderer.mjs`.

The reference path requires Python with NumPy and Pillow, FFmpeg/FFprobe, and a suitable installed monospace font. `SOUND_VISION_VISUALIZER_PYTHON` selects the interpreter; the Legion worker otherwise uses the existing backend virtual environment. Linux uses DejaVu Sans Mono or Liberation Mono; Apple fonts are not redistributed. The classic renderer's Chromium/GPU setup remains separate and unchanged.

The queue advertises `songScenes: 1`, `referencePlayer: 1` and `motionPreviews: 1`. The UI explains a missing matching renderer update before allowing export. A static frontend build alone does not provide these endpoints.

Required checks are `npm run build`, `npm run test:video`, `npm run test:security` and `python -m pytest backend/test_song_reactive.py -q`. They cover song-owned assets, hostile inputs, idempotency, retained images, uncertain submissions, title and display rejection, preview serialization, geometry and classic compatibility. The portable renderer also reproduced the reviewed Mouth frame exactly on the original platform/font. A real text-only director check produced a complete early-1990s courtside boombox brief from Rucker's saved song data.

The September 22 private integration passed a real **Preview motion → Watch preview** run using the reviewed Rucker v004 artwork: 240 frames, 1080p/30 fps, eight seconds of stereo audio, and successful playback/seeking. Three audio sections matched their source positions with zero sample offset and correlations above 0.9998; frame differences were confined to the registered display apart from negligible encoding noise. Desktop and 390 px mobile checks found no overflow or browser exceptions. The classic option remains available, and short previews stay in the Video workspace instead of appearing as full Library videos.

That artwork was deliberately directed in the earlier review; this smoke test does not establish unattended new-song aesthetic quality. Artwork suitability still requires visual review. Publication of the integrated workflow was subsequently authorized separately from the technical smoke test.

## Why the earlier studies differed

Earlier automatic studies requested painted/paper textures, literal scenes and weaker typography, and used a simplified 24-band shader. The restored recipe preserves the original photographic brief requirements and original 48-band renderer. All original approved films, rejected studies and subsequent v004 review artifacts remain in their standalone history; none were overwritten by this integration.

## Preserved style directions

All 16 directions from the earlier catalogue remain in `src/video/visualizers/directions.ts`. They are references and future work, not a picker of supposedly implemented features. Two rejected Tremor studies remain archived. The earlier standalone films are preserved, and the procedural Ink study remains available in source for old saved exports.

| Style                                | Status                                 | Best image surface                            | Audio response                                                                                       | Useful for                                             |
| ------------------------------------ | -------------------------------------- | --------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| Segmented CRT spectrum and VU meters | Built: `american-soviets-v001`         | Rectangular glass, equipment                  | Frequency bands, stereo energy, bass lamp                                                            | Electronic, radio, retro dance                         |
| Luminous ribbon field                | Built: `the-number-i-still-know-v001`  | Wide curved glass, atmospheric image          | Smoothed spectral contour, waveform, restrained energy                                               | Dreampop, ambient, ballads                             |
| Eclipse tachometer                   | Built: `no-one-knows-v001`             | Circular sun, wheel, dial, iris               | Radial frequency blades, bass pulse, drum flashes                                                    | Rock, driving rhythms, desert/noir imagery             |
| Etched-glass resonance contours      | Archived study; rejected for this song | Dark glass, open architectural space          | Nested spectral contour deformation, bass pressure, transient glints                                 | Trip-hop, art-pop, intimate electronic music           |
| Acoustic string resonance            | Archived study; rejected for this song | Existing exposed piano strings and soundboard | Frequency-dependent string glints, one-pixel vibration echoes, low-band light traveling from hammers | Piano-led trip-hop, art-pop, intimate electronic music |
| Analog needle pair                   | Candidate                              | Two physical meters                           | Left/right RMS with peak hold and inertia                                                            | Blues, jazz, live recording, vintage images            |
| Speaker-cone displacement            | Candidate                              | Visible woofer or membrane                    | Low-frequency displacement, transient recoil                                                         | Bass-forward music, hip-hop, dub                       |
| Topographic contour field            | Candidate                              | Terrain, map, water, or paper                 | Spectral bands become breathing contour lines                                                        | Cinematic, folk, ambient, experimental                 |
| Prism or stained-glass cells         | Candidate                              | Window or faceted object                      | Separate low/mid/high energy lights and color shifts                                                 | Orchestral, psychedelic, luminous pop                  |
| Particle constellation               | Candidate                              | Night sky, dust, or open dark space           | Onsets release particles; energy sets density                                                        | Dreamy electronic, spacious tracks                     |
| Film-sprocket pulses                 | Candidate                              | Projector, film strip, photographic scene     | Beat-driven frame-edge flashes and gate motion                                                       | Garage rock, punk, archival mood                       |
| Ink-in-water bloom                   | Candidate                              | Liquid, glass, paper                          | Bass pushes bloom; high frequencies break edges                                                      | Slow, organic, immersive songs                         |
| Neon sign flicker                    | Candidate                              | Physical sign and empty letters               | Per-band lamp intensity with restrained transient flicker                                            | City-pop, synth, nocturnal songs                       |
| Mechanical shutter grid              | Candidate                              | Slats, vents, louvers, architectural frame    | Drums open/close selected cells; sustained sound holds them                                          | Industrial, post-punk, hard electronic                 |
| Oscilloscope Lissajous               | Candidate                              | Small circular/rectangular scope              | True left/right phase trace with persistence                                                         | Instrumental, experimental, electronic                 |
| Vinyl-groove halo                    | Candidate                              | Record, turntable, circular label             | Groove ripple from bass, stylus flicker on transients                                                | Soul, disco, sample-based music                        |
