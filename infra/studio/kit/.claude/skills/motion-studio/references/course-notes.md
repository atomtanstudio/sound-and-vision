# Notes on the companion course

Source: "How to build motion design studio with Opus 5.5 (Full-course)" by Movez (@0xMovez), 27 Sep 2026,
https://x.com/0xMovez/status/2104216919033192746. Read on 2026-10-02. These are notes in our own words, kept short;
go to the article for its prompts and code listings. The eight spec sheets in `../source/` are the course boiled
down to files.

Its argument: a model can't output a video, it writes a program that draws one. The clips that looked good did not
come from a clever sentence but from what surrounded it: a reference, a deterministic renderer, measured audio, and
the model looking at its own frames and fixing them. Roughly a tenth prompt, the rest harness.

## How the frames get made

- One page exposes `seek(t)` and draws the frame for that moment. A headless browser steps through time, captures
  every step, and the captures are piped straight into ffmpeg. Because no timer is involved, two renders are
  identical, and a change is an edit plus a re-render of the seconds it touched.
- Motion blur: render several subframes per output frame (four at 60 fps means 240 steps a second) and average each
  group in the encoder.
- Wait for fonts to finish loading before the first capture, or text falls back to a default face.
- The page can run a real-time loop for previewing, but only when it isn't being driven by the renderer.
- Left to itself the model writes this with no dependencies: one HTML file, one canvas. Frameworks are the other
  route (Remotion for React and data-driven series, HyperFrames for HTML with GSAP). Name one if it is wanted.
- Scenes are a list of objects with a start, an end and a draw function given the time since the scene began.

## Springs

- Use the damped spring's exact solution so the position at any time is a formula, not a simulation.
  With stiffness k and damping d (unit mass): ω₀ = √k, ζ = d / (2√k). Underdamped (ζ < 1), with
  ω_d = ω₀√(1 − ζ²): x(t) = 1 − e^(−ζω₀t) · (cos ω_d t + (ζω₀ / ω_d) sin ω_d t). Critically damped:
  x(t) = 1 − e^(−ω₀t) · (1 + ω₀t). Zero before the trigger.
- A value that changes target several times is its first value plus, for each later change, that change's size
  times a spring started at that change's time. Motion stays continuous and any frame can be computed alone.
- A stretching indicator: drive its two edges with springs of different stiffness, the leading edge stiffer.
- Text inside a container that is changing shape fades in shortly after the change starts and out shortly before
  the next one.
- Four characters of spring are enough: snappy (buttons, leading edges), default (cards, containers, camera),
  heavy (big type, lockups), playful with visible overshoot (mascots only).
- For a loop, the last frame equals the first, including where the cursor is and how fast it is moving.

## Sound

- A supplied track is measured, not guessed: tempo, beat times, downbeats, and onset peaks. Scene and state changes
  go on beats, big moments on downbeats, sound effects on the peaks. Sound / Vision already has this for every take
  (`analysis.tempo`, `beats`, `sections`, word timings), so nothing new has to be measured.
- With no track, music and effects are synthesized in code on the same timeline as the picture, with seeded noise.
- Mix to −14 LUFS.

## Prompt patterns, from least to most

1. One line ("a showreel, go all out"). Tests the engine, carries no idea, and everyone's result looks alike.
2. Brand: give the product's address and insist on its real screenshots, logo, colors and fonts, gathered and
   listed before animating. Nothing redrawn from imagination.
3. Reference: one frame, a video, or a folder of your own work. Have a style guide written from it first (palette,
   type, shot lengths, transitions, texture, how text comes and goes), then a shot list, and approve both before
   any code. Take the grammar, never the content. Say what look and constraints are wanted and let the model pick
   the technique.
4. Spec: a state list laid on the beat grid. One element that never cuts and changes size, corner and fill from
   state to state, a cursor causing each change. Ask to see the state list on the beats before code.
5. Director's brief, for long pieces: the film in one line; references and what to keep of them; tools, keys and
   budget; a character bible with an identity that survives style changes; a beat sheet with a hook in the first
   two seconds and a payoff every three to five; when on-screen words go huge and when they sit like subtitles;
   gates; a critique loop; deliverables.

## Gates for a long film

Plan (style guide and shot list) → stills for every shot, on a contact sheet → a small animatic with placeholder
sound, to fix pacing before polish → full animation → polish → sound → final render. For chapters worked in
parallel by sub-agents, write one animation guide first so they all code in the same style.

## Generate, then trace

The 142-second music video the trend is known for (about five minutes of dictated brief, about twelve hours of
unattended work) used a video model for base shots, for the motion and physics that are hard to write by hand, and
then redrew every shot in code on top, so the viewer sees only the drawn layer and the look stays consistent.
This is the bridge between Sound / Vision's generated shots and a code-drawn film.

## Looking at the result

- Contact sheet at two frames a second; a strip of a dozen consecutive frames around the fastest action, to catch
  pops and overlaps; a sheet scaled to 360 px wide for the phone; the film played twice end to end to check a loop
  seam; the same stretch rendered twice and hashed to prove it is deterministic.
- Things to hunt for: text overlapping during a swap, anything sliding on a fixed curve, corner labels and frame
  borders, a centered-on-gradient shot, text blurred by scaling, a beat with nothing happening, a stutter at the
  seam.
- Re-render only the seconds that changed. Iteration is the method: one of the better shorts took 163 model calls
  and nearly seven hours and said so.

## Formats

Write scenes against a layout function, not fixed pixel positions, and render each shape from the same timeline.

## Repositories it points to (not installed or vetted here)

- Music video: https://github.com/JohnHeibel/PDoomVideo
- Starter: https://github.com/JohnHeibel/ClaudeAnimationBase
- Node canvas skill: https://github.com/buildwithhanif/claude-animation-skill
- HyperFrames: https://github.com/heygen-com/hyperframes
- Remotion skills: https://www.remotion.dev/docs/ai/skills
- Long form: https://github.com/WinterArc21/Battle-of-Austerlitz-Film
- Prompt library: https://github.com/guanmo-ai/awesome-ai-motion
- Dataset of the trend's videos: https://github.com/athemeroy/awesome-opus-5-5-videos
