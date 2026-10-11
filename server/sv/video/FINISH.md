# This folder

One living album cover, finished by you. The cover art has been painted and brought gently to life as a few short
loops; your part is what makes it look like nothing else: anything made in code that runs over it for the whole song. A
treatment, an overlay, motion graphics, type, something that answers the music, a different way of putting the loops
together. The idea, the look, the tools and the code are yours. The person watches from the Sound / Vision app and gets
what you leave in `out/`.

It plays while people listen to the song, so it should hold the eye without pulling attention from the music. How far to
go is your call, guided by `song/brief.md`.

Two things the person has asked for, always:

- **Nothing plays backwards.** No reversed footage, no back-and-forth (ping-pong) looping of a clip or part of one:
  motion that rewinds reads to them as a mistake. If part of a loop goes wrong, leave that part out, or blend past it
  going forward.
- **Say what you changed.** If you leave a loop out, cut part of one, or put them together differently from
  `living/schedule.json`, say so plainly in `out/summary.json` (below), so the app can tell them.

## What's here

- `song/brief.md`: the art director's idea for this cover (the picture, the motion, and what the finish should add),
  plus anything the person asked for. A starting point, not a cage: if something better occurs to you, do it.
- `song/song.m4a`: the master mix, the video's only sound, used unchanged from start to end.
- `song/meta.json`: title, artist, length, size (1080 × 1080) and frame rate (24).
- `song/picture.png`: the cover art, square, without its title.
- `song/sleeve.png`: the title and the logos set the way the app sets them, on a transparent square the size of the
  video. The finished video must show the title and the logos: use this layer as it is, or set the title yourself in a
  way that belongs to your finish (the logos in `song/logos/` then go in too, as they are).
- `living/loop-*.mp4`: the loops, made by a video model (MiniMax H3), 1024 × 1024, 24 fps. Each repeats seamlessly on
  its own (its end flows into its start).
- `living/schedule.json`: when each loop plays through the song (they take turns at the song's sections) and how the app
  changes between them. `living/base.mp4` is that, already put together, for the whole song, without the title.
- `analysis/`: what the app measured automatically: `listening.md` (tempo, key, energy by section, which instruments
  carry each part), `analysis.json` (beats, bars, sections, drum hits, onsets, timed words when the song has them) and
  `env.bin` / `wave.bin` (envelopes and waveforms; layout in `analysis.json`). Automatic measurements can be wrong: use
  them, check them, or measure your own.
- `song/timing.json`: the song's timed words, when it has them.

**Never write the song's lyrics out yourself**: not in code, notes, file names or messages. Anthropic's API stops any
reply that reproduces song lyrics, and the session ends there. If words from the song appear on screen, your code loads
them from `song/timing.json` or `analysis/analysis.json` when it renders. Refer to lines by id or time.

## Hand back

- `out/final.mp4`: the whole song (exactly as long as `song/song.m4a`), 1080 × 1080, 24 fps, H.264 (yuv420p), with
  `song/song.m4a` as its sound. The app takes the picture from it and lays the song under it again itself.
- `out/poster.png`: one frame that shows it at its best.
- `out/summary.json`: `{"about": "one or two plain sentences for the person: what you made", "loopsUsed": ["a", "c"],
  "leftOut": {"b": "why, in plain words"}}` (`leftOut` empty when every loop is used).
- `README.md`: what you made, in a few plain sentences for the person, and how to render it again.

Scratch files go in `out/tmp/`; delete what you no longer need once it's done.
