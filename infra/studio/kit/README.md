# The film kit

> `.claude/skills/motion-studio/` and `.claude/skills/h3-kinetic-type/` here are **copies** of the repository's skills
> (`/.claude/skills/`). Re-sync them whenever those change, then rebuild the image. From the repository root:
> `rsync -a --delete .claude/skills/motion-studio .claude/skills/h3-kinetic-type infra/studio/kit/.claude/skills/`

What every film written in code by Claude in Sound / Vision starts from: a generic engine and tools generalized from the
user's own Claude-made films (`motiondesignvideos/films/your-woman-2`), a `CLAUDE.md` for the Claude session that works
in a film folder, the two skills, and a demo show so a fresh film renders something correct out of the box.

## How a film is made from it

1. The image build (`infra/studio/studio.sh build`) copies this folder to `/opt/kit`, installs its npm packages
   (`npm ci`, exact versions from `package-lock.json`; Puppeteer drives the image's Chromium and downloads nothing) and
   fetches its fonts (`build/fetch-fonts.mjs`, the ~90 OFL/Apache faces `src/engine/type.js` knows, from the Google
   Fonts repository), then checks it (`build/check-kit.mjs`). Nothing is downloaded at run time.
2. `studio.sh seed <work>` copies `/opt/kit` into the film's folder without replacing anything already there (this
   README and `build/` stay behind); `node_modules` and `fonts` become links into `/opt/kit`, valid inside the studio's
   containers, which is the only place a film's tools run.
3. The app writes `song/` (`song.m4a`, `vocals.m4a`, `songmap.json`, `timing.json`, `meta.json`, cover, logos, brief)
   and runs `studio.sh exec <work> python3 tools/import_song.py`, which measures the song into `analysis/`
   (`analysis.json`, `env.bin`, `wave.bin`) in the format `src/engine/audio.js` reads, with every word's cue.
4. A Claude session (`studio.sh run <work> -p …`) reads `CLAUDE.md`, plans, writes `src/`, renders and reviews with
   `tools/`, and leaves `out/final-16x9.mp4` and friends. `studio.sh exec <work> node tools/render.mjs …` renders
   without Claude.

## What's in it

| Path | |
|---|---|
| `CLAUDE.md` | The film session's instructions: the folder, the render contract, the engine API, words on their sung frames, the review gate, delivery, H3 plates |
| `index.html`, `src/main.js` | The page: `window.FILM` (still, range, sheet, prepare, cues …) and `window.seek(t)`; a live player when opened without `?render` |
| `src/show.js` | The demo show: each lyric line on a dark field, word by word on the cue frames, any plate behind |
| `src/engine/` | `core.js` compositor (GLSL / canvas / three.js layers, linear-light motion blur, finishing chain, `prepare` step), `type.js` HarfBuzz type, `audio.js` the song, `math.js` springs and easing, `draw.js`, `glsl.js`, `three-helpers.js`, `timeline.js`, `plates.js` H3 plates as seekable pictures |
| `tools/import_song.py` | `song/` → `analysis/` (numpy + ffmpeg only) |
| `tools/render.mjs` | Parallel headless render (GPU), muxed with the song; writes `<out>.json` beside the film |
| `tools/shot.mjs` | Stills, contact sheets, one frame per beat, strips, the 360 px phone sheet |
| `tools/qa.py` | Hard cuts, single-frame pops, where each word landed against its cue frame |
| `tools/cues.py` | Every word's sung time, cue and frame |
| `tools/h3plate.py` | One H3 plate (word-free background clip, song locked in) on a ComfyUI with MiniMax H3 (`SV_COMFY_URL`) |
| `tools/server.mjs`, `profile.mjs`, `livecheck.mjs` | Static server + frame sink and Chrome flags; frame timing; live-page check |
| `build/` | Image build only: `fetch-fonts.mjs`, `check-kit.mjs`, `seed.sh` |

Chrome flags come from `SV_CHROME_ARGS` (set by `studio.sh`: the GPU through EGL, or SwiftShader with
`SV_STUDIO_GPU=0`); without it, the GPU on Linux when `/dev/nvidiactl` exists, else SwiftShader, and Metal on macOS.

## Rebuild

On the GPU machine, from the repository: `infra/studio/studio.sh build`. Existing film folders keep their own copies
of the kit's files (seeding never overwrites); to update one, copy the changed files in by hand.
