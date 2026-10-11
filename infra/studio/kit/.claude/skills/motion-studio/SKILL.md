---
name: motion-studio
description: The studio rules for motion graphics written as code in Sound / Vision, such as kinetic lyrics, title sequences, lyric videos, animated overlays and whole motion-graphics music videos. Use this whenever the work is designing, writing, rendering or reviewing a motion graphic for a song (the Overlays stage's "Motion graphics written by Claude", a lyric or title animation, a motion-graphics cut of a music video), when wiring that feature into the app, or when the user says "motion studio", "motion graphics", "kinetic type" or "build the film", even if they don't name the skill.
---

# Motion studio

How motion graphics get made here: a short set of files per film, a render contract that keeps every frame
reproducible, and a review loop that has to be passed before anything ships. It comes from an eight-file
"motion studio" spec the user supplied; `source/` holds the sheets as received (four of the eight so far, see
`source/README.md`). The course the sheets belong to is summarized in `references/course-notes.md`: read it before
building or changing the renderer, the springs or the sound, and when planning a film longer than a minute (it has
the spring formulas, the capture pipeline, the gates for long films, and generate-then-trace).

Work like a small production studio (motion director, animator, sound designer and render engineer in one), not a
template generator. The point of the files below is that the decisions get made on paper first, so the animation
code is executing a plan instead of improvising one.

## The files for one film

Write these before any animation code. The examples in `source/` show the format and the level of detail; their
values (the coral palette, the 24-second storyboard, 120 BPM) belong to the example film and are replaced per song.

| File | Holds | In a music video it comes from |
|---|---|---|
| Style guide (`source/03-style-guide.md`) | Reference grammar, palette with a job for each color, type, layout grid, shape language, texture and depth, motion personality, anti-style | The song's style, the story's `style` and `worlds[].colors`, the cover art and keyframes |
| Storyboard (`source/05-storyboard.md`) | A timeline row per scene (time range, name, the one dominant action), then per scene: on-screen text, what happens, and the transition out | The take's `analysis.sections` and `beats`; scenes start on downbeats |
| Audio cues (`source/07-audio-cues.md`) | Session (track, BPM, meter, first downbeat, loudness target), music arc, voice lines with times, sound-effect cues with levels, sync rules, mix | The master take's `analysis` (tempo, beats, sections, lines and words, with hand-corrected timing from `song.timing` on top) |
| Project brief, asset manifest and two more | Not supplied yet | Ask the user for sheets 02, 04, 06 and 08 rather than guessing their contents |

Real assets only: logos come from the app's Branding, pictures from the project's cover art and keyframes. Don't
draw a stand-in for a logo or invent an interface that belongs to someone else.

## Render contract

A film is a pure function of time: `window.seek(t)` paints exactly the frame at `t`, with nothing remembered from
the frame before. That is what lets the editor scrub it, the preview follow the song's clock, and the export render
frames in any order and get the same picture every time.

- No CSS transitions or animations, no `setTimeout`, no `requestAnimationFrame` loop while rendering, no state
  carried from one frame to the next.
- Noise is seeded. `Math.random()` gives a different film on every render.
- Master: 1920×1080, 60 fps, 4 subframes per frame (averaged, for motion blur), H.264 yuv420p, CRF 16. An overlay
  inside a project's timeline follows that project's `width`, `height` and `fps` instead.
- 16:9, 1:1 and 9:16 are each laid out by rule (12-column grid for wide, 6-column for tall, 6% safe area). The
  master is never cropped to make the others, because a crop keeps the layout of a shape it no longer has.

## Visual standard

- Settle one clear visual idea before writing animation code.
- One display face, one interface face, one dominant accent, unless the style guide says otherwise.
- Every frame has one primary subject, supporting information, and negative space that was left on purpose.
- At most three type sizes in a frame; hero content takes 60–70% of it.

## Motion standard

- Springs in closed form: position is computed from the time since the spring was triggered, not stepped frame by
  frame, so it can be evaluated at any `t`. A tiny overshoot for interface elements (2–4%), none for body text.
- A value that moves to several targets over the film is a sum of spring tracks, one per target, each adding its
  own change from its own start time. That keeps it seekable where a chained "current value" would not be.
- Text enters after its container has started moving and leaves before the next transition begins.
- Something meaningful changes every 2–4 seconds.
- Every transition has an owner: an object in the outgoing scene that physically becomes the next one (the swatch
  that grows into the background, the card that opens into the container). No cut to a fresh layout.

## Sync

- Downbeats own scene changes; offbeats own secondary details.
- A visual impact lands no more than one frame ahead of its low-frequency sound, never behind it.
- A whoosh peaks where the motion is fastest, not where it starts.
- Every interface sound has a visible action. Not every label gets a sound.
- Mix: music ducks 3–5 dB under a voice (40 ms attack, 180 ms release), 2 dB of headroom before the limiter,
  −14 LUFS integrated and −1 dBTP, checked on laptop and phone speakers. Stems: music, sfx, voice, mix.

## Banned defaults

These are what a film looks like when nobody decided anything, so each one is a sign to go back to the storyboard:

- A centered title on a generic gradient.
- Everything fading in or sliding upward.
- Decorative corner labels, random particles, fake glass, heavy glow.
- Bounce on every object.
- Dead beats: a beat of the song where nothing on screen answers it.
- Narration copied word for word on screen. (Sung lyrics set as kinetic type are the subject of a lyric video, not
  a caption of it, so they are allowed; a spoken line still isn't repeated as text.)

The style guide adds its own anti-style list per film.

## Order of work

Plan on paper (the files above) and show the storyboard on the beat grid before any code. Then stills for every
scene, then a small rough cut to fix pacing, then the full animation, polish, sound and the final render. Each
step is cheap to redo and the next one isn't, which is why they aren't skipped. A full song is hours of work, not
one pass; say so up front.

## Review gate

Nothing ships on the first render. Three rounds, each one:

1. Render one representative frame per beat.
2. Build a contact sheet, a phone-size sheet (does it read at 360 px wide?) and a strip of consecutive frames
   around the fastest action.
3. Look at them as a harsh director would, and score hook, readability, composition, motion, variety, brand and
   sound, each out of 10.
4. Write down the three largest problems, with their times, and fix them. Re-render only the seconds that changed.

Do not ship while any category is below 8. Report the scores and the problems found in each round as they
actually came out; a round that didn't improve a score says so. Also check that the same stretch rendered twice
comes out identical, and for a loop, that the seam is clean.

## Delivery

`out/final-16x9.mp4`, `out/final-9x16.mp4`, `out/final-1x1.mp4`, `out/poster.png`, `out/contact-sheet.png` and a
`README.md` saying what was made and how to render it again.

## Where this meets the app

Three of the app's six kinds of music video are drawn in code and follow this skill (`web/src/lib/videoTypes.ts`):

- **Code-created film.** The Brief step holds the style guide (the sections above, as fields), the Storyboard step
  holds the scenes on the song's beat grid (name, one dominant action, words on screen, transition), and the Build
  step writes `02_STYLE_GUIDE.md`, `04_STORYBOARD.md` and `06_AUDIO_CUES.md` from them and the take's analysis
  (`web/src/lib/brief.ts`). Those three files are what you build the film from; parts still in [brackets] haven't
  been decided, so settle them with the user before writing code. From the Build step, "Make it with Claude" hands
  them to the Claude studio, which builds, reviews and renders the film (below).
- **Living album art** and **kinetic lyrics.** The monitor draws them live from `web/src/render/`: closed-form
  springs and seeded noise in `motion.ts`, the cover's loops in `album.ts`, the words in `lyrics.ts`. Those functions
  take the project and `t` and nothing else, so they already meet the render contract and are the code an export
  should reuse. Change them to this standard: no timers, no carried state, no `Math.random()`.

**The Claude studio** (`server/sv/studio.py`, `server/sv/films.py`, `infra/studio/`). Kinetic lyrics' Make step and
the code-created film's Build step start a Claude Code session on the GPU machine, in a container under the owner's own Claude
plan (signed in once with `studio.sh signin`; never an API key), with the model and reasoning level the person picks.
Each film is a folder, `data/projects/<pid>/films/<fid>/work/`, seeded from the starter kit (`infra/studio/kit/`: the
engine and tools of the user's own films, this skill and h3-kinetic-type, and a `CLAUDE.md`), with `song/` written by the
app (the master take, its song map, the hand-corrected word timing, the cover, the Branding logos, the brief) and
`analysis/` made from it. Two engines: everything in code, or H3 plates (word-free, the song locked in) under type drawn
in code; either way every word is drawn in code on its sung frame. Claude may edit files in the folder and run only the
kit's tools, ffmpeg and a few listings; renders use the machine's GPU. What it leaves in `out/` (plan, stills, contact sheet,
`review.md`, `final.mp4`, poster) is what the app shows; a note from the person continues the same conversation.

The Overlays stage of the shot-based kinds still has a "Motion graphics written by Claude" panel whose button is not
wired (`web/src/components/inspector/OverlaysInspector.tsx`), and export isn't wired either. When they are built, this
skill is the standard: the graphic honors the render contract (the editor's clock calls `seek`), reads its timing
from the take's analysis, and passes the review gate before it is offered as finished.
