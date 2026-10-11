# This folder

A music video for the song in `song/`, made by you in code. The person follows along from the Sound / Vision app and
gets what you leave in `out/`.

## The song

- `song/song.m4a`: the master mix, the film's only sound, used unchanged from start to end.
- `song/vocals.m4a` and `song/stems/` (`drums`, `bass`, `other`): stems the app separated, when it has them.
- `song/meta.json`: title, artist, length, the film's size and frame rate, and `feel`: the person's guidance (empty
  means none).
- `song/timing.json`: the lyrics as sung: every line, and every word in it, with its start and end time (the app's
  alignment of the lyric sheet to the vocal; close, but check it against the vocal where it matters). No lines means
  the song has no words.
- `analysis/`: what the app measured automatically: `listening.md` (tempo, key, energy by section, where the voice is),
  `analysis.json` (beats, bars, sections, drum hits, onsets per stem, every word with its time) and `env.bin` /
  `wave.bin` (envelopes and waveforms; layout in `analysis.json`). Automatic measurements can be wrong (an unusual
  meter, a section boundary): use them, check them, or measure your own.

**Never type the song's lyrics out yourself**: not in code, notes, file names or messages. Anthropic's API stops any
reply that reproduces song lyrics, and the session ends there. Your code loads the words from `song/timing.json` when
it renders; refer to lines by id, number or time ("line 12", "the line at 2:31"). Printing them in a tool's output to
look at is fine; typing them back is what gets blocked.

## Hand back

- `out/final.mp4`: the whole song, at `song/meta.json`'s size and frame rate, H.264 (yuv420p), with `song/song.m4a` as
  its sound.
- `out/poster.png`: one frame that sells the film.
- `README.md`: what you made, in a few plain sentences for the person first, then how to render it again.

The person sees the newest images in `out/` while you work, and reads your messages as you go. Scratch files can go in
`out/tmp/`. The person may send notes after seeing it: each continues this conversation, in this folder.
