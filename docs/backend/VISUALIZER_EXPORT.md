# Visualizer MP4 export

In **Video → Visualizer**, choose a finished library song and a visual style, then use **Render video**. Progress and **Download MP4** appear in the same panel. Rendering continues when leaving the Video page. In Mac mode, the local server must remain running. With the [Legion renderer](LEGION_VISUALIZER_RENDERER.md) configured and verified, jobs continue on Legion even when the editor closes.

**All visualizers — equal time across the song** uses all eight styles once, in list order. The full song's output frames are partitioned into eight adjacent segments; lengths differ by no more than one frame at 24 fps. There is no beat snapping, repeated cycle, or extra ending. Preview, timeline buttons, exported manifest, and renderer share `src/video/visualizers/schedule.ts`.

Exports honor landscape/portrait 1080p, response strength, background shade, and the current lyric typography, colors, placement, and motion settings. With **Show lyrics** on, nonempty lyrics require usable word alignment. The UI explains missing or overlapping timing; turn lyrics off to export just the visualizer. Review low-confidence transcription while listening. User reduced-motion preference applies to the interactive preview, not the requested animated video.

## Architecture

The Vite development server exposes `/local-api/visualizer-renders`. Without a render-backend setting it uses the Mac queue; with `SOUND_VISION_RENDER_BACKEND_URL` it relays new jobs to the standalone Legion service through SSH. The queue is separate from music generation. Legion mode uses the NVIDIA GPU for graphics and encoding, without changing model services. Original FLAC is retrieved from the configured authenticated music backend. Browser requests supply a validated take ID and settings, not arbitrary source URLs, file paths, shell commands, or credentials.

Each job is written under `../output/visualizer-renders/<job-id>/` before it starts. It retains the validated input, original audio, analysis, worker log, exact frame schedule, receipt, and final MP4. Successful videos are not overwritten. Repeated submissions of the same request/settings or an already-active identical render return the existing job. Cancel stops only that export's download and owned render processes. On server restart, queued jobs resume; interrupted running jobs become visibly failed and retain their artifacts for inspection.

On macOS, exports without lyrics use the existing native OpenGL renderer with the same shader, response/shade controls, and exact frame schedule. Exports with lyrics (and exports on other platforms) open isolated headless Chromium pages that mount the same `VisualizerCanvas` and `LyricOverlay` components as the editor. Measured offline audio frames drive both renderers. Browser frames are captured in parallel and delivered to FFmpeg in chronological order. The soundtrack is encoded to source-channel AAC at 256 kbps from the original FLAC. The final file is only published after verifying audio presence/duration, video dimensions, and exact frame count. Download routes support HTTP byte ranges and seeking.

The editor endpoint applies loopback Host/Origin protections and rejects cross-site requests. The standalone Legion endpoint additionally requires service authentication and binds only to loopback; SSH carries requests from the Mac. A static frontend build alone does not provide either endpoint.

## Runtime and checks

Uses the existing Node, FFmpeg, and `@playwright/test` installations. The native macOS path compiles its cached renderer with the installed Clang and OpenGL framework. For lyric exports, Chromium is discovered from Playwright's installed executable or the installed macOS headless-shell cache. `PLAYWRIGHT_EXECUTABLE_PATH` may select a compatible installed browser. If Chromium is absent, the surfaced worker error explains `npx playwright install chromium`. No generation API or paid model is involved.

```sh
npm run dev
node --experimental-strip-types --test scripts/test-video-timing.mjs scripts/test-visualizer-export.mjs
npm run build
```

The native command-line renderer retains its earlier beat-aligned sequence workflow. The in-app exporter passes `--visualizer all` or one style number to select the shared schedule, without beat snapping or crossfades that would change each style's allocated duration.
