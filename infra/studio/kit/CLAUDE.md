# A film for Sound / Vision

This folder is one music video written in code, for one song. Sound / Vision (the app) made it from the studio's film
kit, put the song in `song/` and measured it into `analysis/`; you write the film in `src/`, check it with the tools,
and leave the finished files in `out/`. The person who asked for it watches from the app and can answer between your
runs (end your turn with the question; their note resumes this session).

`METHOD.md` is how the person's own kinetic-type films were made (what worked, what failed, how the music drove them):
read it before you plan. Two skills hold the house rules, and they win over anything here: **motion-studio** (`.claude/skills/motion-studio/`,
everything drawn in code: render contract, visual and motion standard, sync, banned defaults, review gate) and
**h3-kinetic-type** (`.claude/skills/h3-kinetic-type/`, H3 prompts; for hybrid films). Read motion-studio before you
plan. Both skills mention files of the Sound / Vision repository (`web/`, `server/`, `lab/`); those aren't here, and
the parts that apply to this folder are restated below.

## What you can run

Only these, from this folder: `node tools/<x>.mjs …`, `node --check <file>`, `python3 tools/<x>.py …`, `ffmpeg …`,
`ffprobe …`, `ls`, `mkdir`, `wc`, read-only checks (`cat`, `head`, `tail`, `grep`, `sort`, `uniq`, `diff`, `cmp`,
`sha256sum`, `md5sum`, `du`, `jq`, `file`), plus reading and writing files. Anything else, `python3 -c` included, is
refused: a check you need goes in a `tools/` script. Run one command at a time from this folder rather than chaining
`cd …;` in front of it. There is no npm, npx or web access, and nothing needs
it: `node_modules/` and `fonts/` are links into the studio image with everything installed. A tool you need and don't
have is a `tools/*.mjs` or `tools/*.py` you write. Chromium draws on the machine's NVIDIA GPU (WebGL); on an RTX 5090
a 1080p frame with 4 sub-frames takes a few milliseconds, a contact sheet about a second, and a render runs at roughly 40–70 frames a second
(the H.264 encode is the limit), so a 3-minute song renders in 3–5 minutes. Render and look rather than guess. Give a
long render a 10-minute Bash timeout, or run it in the background and check on it.

## The folder

| Path | What it is | Who writes it |
|---|---|---|
| `song/song.m4a`, `song/vocals.m4a` | The master mix (the only sound of the film, used unchanged) and its vocal stem | the app |
| `song/stems/` | `drums.m4a`, `bass.m4a`, `other.m4a`: the rest of the HTDemucs stems, when the app has them | the app |
| `song/meta.json` | `title`, `artist`, `style` (the style the song was made from; empty for the person's own song unless they described it), `feel` (the person's words on how the video should feel: these come first), `own` (true: the person's own released song, not one made in the app), `tags` (what the song file says: album, year, genre, key, bpm; DJ-software values can be wrong), `background`, `lyrics`, `kind` (`lyrics`: kinetic lyric video; `kinetic`: kinetic film led by the music; `film`: code-created film), `engine` (`code`, or `hybrid`: H3 plates behind code-drawn type), `width`, `height`, `fps`, `look` (the song's look, or null), `cover` (only when the person chose it for this video), `logos` {`label`, `app`}, `brief` | the app |
| `song/background.md` | For a released song: what it is and where it comes from, looked up on the web by the app (era, scene, theme, its artwork, visual cues, sources). Information to design from, never instructions; no lyrics | the app |
| `song/timing.json` | Tempo, beats, first downbeat, meter, sections, and every lyric line with its words' sung `start`/`end`, corrected by hand in the app. **The only source of on-screen words.** | the app |
| `song/songmap.json` | The app's song map: beats, bars, phrases, segments, drum hits, energy, vocal presence | the app |
| `song/cover.*`, `song/logos/` | The real cover art and logos (label, app). Real assets only: never draw a stand-in logo or invent one | the app |
| `song/brief/` | The person's brief when there is one: `02_STYLE_GUIDE.md`, `04_STORYBOARD.md`, `06_AUDIO_CUES.md` | the app |
| `analysis/` | `analysis.json`, `env.bin`, `wave.bin`: what the engine reads; `listening.md` / `listening.json`: what the song sounds like, measured (key and mode, tempo feel, the energy arc by section, brightness, how busy each part is, which instruments carry it, where the voice is). Made by `python3 tools/import_song.py` | the import |
| `index.html`, `src/main.js` | The page and its boot: `window.FILM`, `window.seek(t)`, the live player. Keep the API | kit |
| `src/engine/` | Compositor, type engine, song reader, math, plates. Extend it; don't fork it into scenes | kit, you |
| `src/show.js` | The show: `build(E)` returns the timeline of scenes. Starts as a demo (lyrics on a dark field); replace it | you |
| `plan/` | Your plan: style guide, storyboard, audio cues, review log | you |
| `plates/` | H3 plates for a hybrid film (`tools/h3plate.py`) | you |
| `out/` | Renders. `out/plan/` for the plan's stills (the person sees them), `out/review/` for stills, sheets, strips and drafts; deliverables at the top | you |
| `README.md` | At delivery: what was made and how to render it again | you |

Never edit `song/` or `analysis/` by hand. If the analysis looks wrong (a grid off the beat, a word time wrong), say so
to the person: corrections are made in the app and come back through a new `song/` and a re-import.

## Order of work

1. **Read** `song/meta.json`, `analysis/listening.md`, `song/background.md` if any, the brief in `song/brief/` if any,
   the cover if any, and the song's shape: `python3 tools/cues.py --lines` (lines and sections), `python3 tools/cues.py`
   (every word with its cue and frame). You can't hear the song; the listening report, the stems' envelopes and the
   background are your ears. Design from them: tempo and groove, key and mode, the energy arc, brightness, which
   instruments carry each part, the era and scene, what it's about. A genre word or a tag is not a design, and when the
   style text or tags disagree with the measurements, the measurements win (say so in the plan).
2. **Plan on paper first** (motion-studio "The files for one film"): `plan/02_STYLE_GUIDE.md`, `plan/04_STORYBOARD.md`
   (one row per scene on the bar grid: time range, name, the one dominant action, words on screen, transition out),
   `plan/06_AUDIO_CUES.md`. Start from the brief's files when they exist; anything still in [brackets] is the person's
   decision, so ask rather than decide it. Scenes start on downbeats; something meaningful changes every 2–4 s.
3. **Stills** for every scene (`node tools/shot.mjs still …`), then a rough cut of a stretch, then the full film,
   polish, the final render. A whole song is hours of work: say so, and keep going stretch by stretch.
4. **Review gate** (below), three rounds, before anything is called finished.

## The render contract

A frame is a pure function of song time: `window.seek(t)` paints exactly the frame at `t`, whatever was painted before.

- No `Math.random()`, `Date`, `performance.now()` in drawing, timers, CSS animation, or state carried from frame to frame.
  Noise is seeded (`rng(seed)`, `noise1/2`, `hash`); a value with several targets is a sum of spring tracks (`track`).
- Anything async (a picture, a plate frame) is loaded in a `prepare` step, never during `render`: `engine.prepare(t)`
  loads every plate frame the frame's sub-frames need, and calls each active scene's `prepare(times, E)` hook. The tools
  await it before every frame; `render(t)` itself never waits.
- Output frame `i` shows song time `(i + 0.5) / fps` (frames are centred). A thing cued at `c` is first up on frame
  `ceil(c·fps − 0.5)`. Motion blur: `nsub` sub-frames spread over a 0.5 shutter, averaged in linear light.
- `window.FILM` (keep it working; the tools and the app use it): `still(t, {nsub})`, `range({from, to, fps, nsub, job})`
  (frame indices), `sheet(times, {cols, tw, nsub})`, `prepare(t)`, `cues(from, to)`, `frameTime(i)`, `cueFrame(t)`,
  `frameJPEG()`, `framePNG()`, and `engine`, `song`, `timeline`, `plates`, `meta`, `W`, `H`, `fps`, `ready`.
- Master: `width`×`height` and `fps` from `song/meta.json` (normally 1920×1080, 60 fps), 4 sub-frames, H.264 yuv420p,
  CRF 16. Another aspect (9:16, 1:1) is laid out again by rule from `f.W`/`f.H`, never cropped from the master.

## Words land on their sung frame

- On-screen words come from `analysis/` (`S.lines`, `S.lineList`, `S.words`), which comes from `song/timing.json`.
  Never retype a lyric into the source, translate, fix or paraphrase it: build every string from the line's words (case
  changes are fine; the look's `caps` says when). That way a timing correction in the app flows straight through.
- Every word has a cue (`w.t`): within 50 ms of a drum hit (hit ≥ 0.5, kick or snare ≥ 0.6) it is locked to the hit,
  12 ms early (the first new frame is up when the hit sounds); otherwise it is cued 40 ms ahead of the voice, because an
  entrance needs a moment to read as landing on the syllable. `w.raw` is the sung start, `w.end` the sung end, `w.how`
  what it snapped to. A word is readable from its cue frame: no fade-in that leaves it unreadable for frames after it
  is sung. `python3 tools/cues.py --from A --to B` lists cues and frames; `python3 tools/qa.py <render>` checks where
  each word actually landed in a render. With motion blur an instant entrance is spread over the shutter, so a word cued
  just after a frame's centre shows faintly on the frame before; that is expected, not early.
- A word is gone, or unreadable, before the next line needs the space; nothing readable is left in a stretch with no
  singing unless the plan puts it there (a title, the cover).

## The engine, briefly

Read the source for details; this is the map. Design units: the short side is always 1080 (`f.W × f.H` is 1920×1080
at 16:9, 1080×1920 at 9:16), whatever the output size.

**Show and scenes** (`src/show.js`, `engine/timeline.js`). `export const FONTS = [...]` names the faces to load (keys of
`FONT_FILES` in `engine/type.js`: about 90 open-licensed families, e.g. `anton`, `archivo` (variable wdth/wght),
`bodoni`, `fraunces`, `dela`, `mono`, `jet`, `playfair`, `unbounded`, `instrument`…; a face not listed fails loudly).
`export async function build(E, { meta })` returns `new Timeline()` with `tl.add(scene, t0, t1)` per shot (later clips
win where they overlap) and `tl.overlay(scene)` for things over everything. A scene is
`{ id, init?(E), prepare?(times, E), render(f, clip) }`. Organize big films as `src/shots/<section>.js` modules that
export their clips, with shared helpers in `src/lib/`.

**The frame `f`** (`engine/core.js`), handed to `render`: `f.t` song time, `f.lt` time since the clip started, `f.dur`,
`f.p` (0..1 through the clip), `f.W`, `f.H`, `f.song`, `f.frameIndex`.
- `f.clear(color)`; `f.canvas((ctx, f) => …, { blend, opacity, blur, glow: {radius, strength}, shadow: {radius, opacity, dx, dy} })`
  draws a 2D layer (design units) and composites it; blends: over, add, screen, multiply, difference, overlay, invert,
  mask, behind, lighten, darken, shadow.
- `f.layer(draw)` → texture; `f.put(tex, opts)`; `f.snapshot()` (the comp so far, for feedback/refraction);
  `f.sub(scene, t)` renders another scene to a texture (transitions where one scene becomes the next).
- `f.shader(fsMaterial(glsl, uniforms), uniforms)` a full-screen GLSL pass over the comp (`tPrev`, `uRes`, `uTime`,
  the helpers in `engine/glsl.js`: hashes, value/simplex noise, fbm, SDFs, `toLinear/toSRGB`).
- `f.three(scene, camera, { tone: 'aces'|'neutral'|'none', exposure, opacity, blend, glow })` composites a three.js
  scene; `engine/three-helpers.js`: `studioEnv` (PMREM studio light), `textGeometry`/`glyphGeometries` (extruded type),
  `lineShapes`, `pxPerUnit`.
- `f.post({...})` sets the finishing chain for this frame (defaults `POST_DEFAULTS`): bloom, bloomThreshold, ca, split,
  barrel, shake [x,y], rot, zoom, glitch, pixel, mirror, wave, grain, vignette, fade, flash, flashColor, saturation,
  contrast, lift, gain, invert, letterbox, scan, halftone, paper.

**Type** (`engine/type.js`, HarfBuzz-shaped outlines, not the browser's text): `Type.line(str, { font, size, vars,
tracking, features })` → layout with per-glyph boxes, `width`, `cap`, `ascent`; `Type.draw(ctx, L, x, y, { fill,
stroke, align, baseline, each(g, i) → {dx, dy, rot, s, sx, sy, skew, alpha, fill, skip} })` for per-glyph animation;
`Type.text(ctx, str, x, y, opts)`; `Type.fitSize(str, width, opts)`; `Type.linePath` (clip masks); `Type.outlines`
then `Type.trim(ctx, outs, a, b)` (write-on), `Type.fillWarped`, `Type.samplePoints`; `Type.fontInfo(name)` (cap, x-height,
axes). `engine/draw.js`: ring, disc, rule, arrow, label, typedLabel, polyTrim, cam, shake, arcText, stack (poster stacks).

**Motion** (`engine/math.js`, all pure functions): springs in closed form `sp(t, SPRING.snappy|default|heavy|playful)`
and `track(t, [[t0, v0], [t1, v1], …], preset)` / `trackV` (several targets, each a spring from its own start); eases
`E.snap, swift, heavy, soft, drop, whip, over, anticipate` and `ease.*`; `tw(t, t0, dur, e)`, `span`, `inOut`, `decay`,
`spring`, `ring`, `stepTime`; for hits and words `inn(t, t0, d)`, `punch(t, t0, tau)`, `slap(t, t0)`, `passed`,
`sung(line, t)`; seeded `rng(seed)`, `hash`, `noise1/noise2`, `fbm1/fbm2`, `wiggle`; colour `mixHex`, `withAlpha`,
`hexToRgb`. Overshoot only on interface elements (2–4%), none on body text.

**The song** (`E.song` / `f.song`, `engine/audio.js`): grid `bar(n)` (1 = first downbeat, fractional ok), `bt(bar, beat)`,
`st(bar, step)`, `beat(i)`, `beatAt(t)`, `barPos(t)`, `beatPhase(t)`, `tempo`, `meter`, `beats`, `bars`, `sectionList`,
`sectionAt(t)`; onsets (keys kick, snare, hat, hit, bass, other, vocals, mix) `pulse(key, t, tau, minS)` (the
workhorse), `last`, `next`, `count`, `list`; envelopes `env(key, t)` (kick, snare, hat, drums, bass, other, vocals, mix,
low, mid, high), `band(i, t)` (48 log bands 40 Hz–16 kHz), `wave(key, t, span, n, out)` (mix, bass, other, vocals,
drums); words `lines[id]`, `lineList`, `words`, `lineAt(t)`, `wordAt(t)`, `cueFrame(t, fps)`. Kick/snare/hat are the
app's drum hits; bass and other come from their own stems when `song/stems/` has them (`analysis.json` `source.stems`),
otherwise from the mix with the vocal taken out (see the top of `tools/import_song.py`). The song map can count a slow
song in double time; judge bars by the drum pattern.

## Look at it

- `node tools/shot.mjs still 66.05 70.2 [--png]` full-size stills in `out/review/` (exactly what the render holds).
- `node tools/shot.mjs sheet 60:90:0.5 [--phone]`, `beats 60 90` (one frame just after each beat), `bars 30 38 --per 4`,
  `sections`, `strip 66.0 --n 12` (consecutive frames: pops, overlaps, the fastest move), `phone 0:180:2` (tiles 360 px
  wide: does it read on a phone?). Then read the images: you can see them.
- `node tools/render.mjs --from 60 --to 75 --out out/review/chorus.mp4` renders a stretch with its sound; `python3
  tools/qa.py out/review/chorus.mp4` lists hard cuts, single-frame pops and where each word landed against its cue frame.
- `node tools/profile.mjs 12 66 120` times frames; `node tools/livecheck.mjs 66` checks the live player page.
- `node --check src/show.js` before a render saves a failed boot.

## Songs with few words

A kinetic film (`kind: "kinetic"`), or any song where the voice is a small part (the listening report's voice share and
moments say so), is led by the music. The few sung lines are the hero moments: plan the film so they arrive as events
(the biggest type, a change of world), still exactly as timed. Between them, the picture is typography and graphic
material that the instruments play: a part per stem (the bass moves the big masses, the drums cut and punch, the other
instruments draw the detail), building and releasing with the energy arc, a new idea at each section change. Type that
isn't a sung word is allowed when it's the song's own (its title, the artist) or pure graphic matter (shapes of letters,
numerals of the bar count, the key); never invented slogans or fake lyrics. Words that are sung but not timed are not
shown.

## The plan stage

When the app asks for the plan only, stop after the plan files, a few stills of the key moments in `out/plan/`
(`node tools/shot.mjs still <t> <t> … --out out/plan`) and `plan/CONCEPT.md`: one page for the person in plain words (the
idea, how the music and the song's background shaped it, the look, the scenes with their times). The person approves it
with Go or sends a note; a note means revise the plan and the stills and stop again.

## Review gate (motion-studio; nothing ships before it)

Three rounds. Each round: one representative frame per beat (`shot.mjs beats`), a contact sheet, the 360 px phone sheet,
a strip of consecutive frames around the fastest action; look at them as a harsh director; score hook, readability,
composition, motion, variety, brand and sound sync out of 10; write down the three largest problems with their times;
fix them and re-render only the seconds that changed. Log every round in `plan/review-log.md` as it actually came out
(a score that didn't move says so). Nothing ships while any score is under 8. Also: render one stretch twice and check
the files are identical (`ffmpeg -i a.mp4 -f framemd5 -` on both), check every sung word lands within a frame of its
cue (`qa.py`), and nothing in the banned-defaults list of motion-studio.

## Delivery

`out/final-16x9.mp4` (the master at `song/meta.json`'s size: `node tools/render.mjs --out out/final-16x9.mp4`; the
whole song carries `song/song.m4a` as a bit-exact stream copy), `out/poster.png` (`shot.mjs still <t> --png`, then copy),
`out/contact-sheet.png`, and `out/final-9x16.mp4` / `out/final-1x1.mp4` when asked (`--w 1080 --h 1920`, laid out again
by rule). `README.md` here: what was made, the idea, the scenes, what was checked and how, and how to render it again.
Report the review scores per round honestly.

## Hybrid films (`engine: "hybrid"`): H3 plates

H3 (MiniMax's video model on the machine's ComfyUI) paints the world; code draws every word. **A plate has no words**: no
letters, numbers, signs, logos, captions anywhere, ever. Follow h3-kinetic-type for prompts (its template, the STYLE
LOCK header pasted byte-identical into every plate, the song locked in, one continuous shot or cuts said in words) with
the type parts replaced by "ON-SCREEN TEXT: none. No letters, numbers, signs, logos, posters, captions or subtitles
anywhere, at any time" and a plain surface left where the words will go.

1. Plan which storyboard rows get plates. Each plate starts at its shot's song start (a downbeat in a gap between words)
   and is 17k + 5 frames at 24 fps (124–362 frames; 141 = 5.875 s); it is trimmed at the cut. Sizes 1024×576 (16:9),
   576×1024 (9:16), 1024×1024 (1:1); the comp scales it up.
2. Write the prompt to `plates/<name>.txt` (under 7,000 characters, `wc -m`), then
   `python3 tools/h3plate.py --name <name> --prompt plates/<name>.txt --start <s> --seconds <s> [--seed 7]
   [--first plates/<name>-first.png] [--pin 91:plates/<name>-hold.png]`. It waits its turn in ComfyUI's queue (about
   1–3 min per 6 s plate once it runs), then writes `plates/<name>.mp4`, its frames `plates/<name>/f_%05d.jpg` (frame f =
   song time start + f/24) and registers it in `plates/index.json`. `--dry-run` checks everything without sending.
   `engine: "hybrid"` in `song/meta.json` is the person's go-ahead to make plates; make the ones the storyboard needs,
   one at a time, not dozens of variations.
3. Look at every plate before using it: `ffmpeg -i plates/<name>.mp4 -vf "fps=4,scale=320:-1,tile=6x4" -frames:v 1
   out/review/<name>-plate.jpg` and read it. Any readable letter, a sign, a logo, a person who shouldn't be there: new
   seed if it looks like chance, a changed prompt if not. Record what failed.
4. In a scene, `E.plates.draw(ctx, '<name>', f.t, { fit: 'cover' })` inside `f.canvas`, or `f.layer(ctx => …)` to use it
   as a texture in a shader. A plate covering `f.t` is loaded automatically before each frame; to show one at another
   time (a hold, slow motion, a loop) load it in the scene's `prepare(times, E)` hook with `E.plates.load(name, t)`.
   Grade the plate and the type as one picture (shared grain, light that answers the plate, the type's color from the
   plate's palette); the type still lands on its cue frames like any other film.
