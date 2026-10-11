# This folder

A music video for the song in `song/`, made by you: pictures you make, brought to life with MiniMax H3,
cut and finished by you in code. The person follows along from the Sound / Vision app and gets what you leave in
`out/`.

## The song

- `song/song.m4a`: the master mix, the video's only sound, used unchanged from start to end.
- `song/vocals.m4a` and `song/stems/` (`drums`, `bass`, `other`): stems the app separated, when it has them.
- `song/meta.json`: title, artist, length, the video's size and frame rate, and `feel`: the person's guidance (empty
  means none).
- `song/timing.json`: the lyrics as sung: every line, and every word in it, with its start and end time (the app's
  alignment of the lyric sheet to the vocal; close, but check it against the vocal where it matters).
- `analysis/`: what the app measured automatically: `listening.md` (tempo, key, energy by section, where the voice is),
  `analysis.json` (beats, bars, sections, drum hits, onsets per stem, every word with its time) and `env.bin` /
  `wave.bin` (envelopes and waveforms; layout in `analysis.json`). Automatic measurements can be wrong (an unusual
  meter, a section boundary): use them, check them, or measure your own.

**Never type the song's lyrics out yourself**: not in code, notes, prompts, file names or messages. Anthropic's API
stops any reply that reproduces song lyrics, and the session ends there. Read them as much as you like; refer to lines
by id, number or time ("line 12", "the line at 2:31"), and describe what they bring to mind in your own words.

## Pictures

(How you make this video's pictures is filled in when it starts.)

## Motion

(How your clips are made is filled in when the video starts.)

## Hand back

- `out/opening.mp4`, when you're asked for the opening only: the video from the start of the song, at
  `song/meta.json`'s size and frame rate, H.264 (yuv420p), with `song/song.m4a` (from its start) as its sound.
- `out/final.mp4`: the whole song, the same way.
- `out/poster.png`: one frame that sells the video.
- `README.md`: what you made, in a few plain sentences for the person first, then how it's put together.

The person reads your messages as you go. Scratch files can go in `out/tmp/`. The person may send notes after seeing
it: each continues this conversation, in this folder.
