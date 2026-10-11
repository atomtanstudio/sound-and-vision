# This folder

A music video for the song in `song/`, made by you, in which people sing it. This folder is a project of
VRGameDevGirl's Video Builder: her ComfyUI pack on this machine and its H3 film skill, the way the person's "Rapture" video
was made. You make the pictures (see Pictures below). Her Builder renders each scene with MiniMax H3, with that scene's slice of
the song locked in, so the performers lip-sync the real vocal. The edit, the title and anything on top are yours, in
code. The person follows along from the Sound / Vision app and gets what you leave in `out/`.

## Her guide

`reference/SKILL.md` is the skill's own guide. Its "Music videos" section is the path, from step 4: the song is already
imported, and the install was checked. Its prompt rules, "Fixing takes" and "Reference images from an image MCP" all
apply. Where it says `remote.sh run <script>` or `python scripts/<script>`, use `python3 tools/vrgdg.py <script> .`
here, and skip its installs, `check_env.py` and `remote.sh`.

## The song (already imported)

- `song/song.wav`: the master at 48 kHz, what every scene's audio is cut from and what the final carries. Also
  `song/song.m4a` and `song/song.flac`.
- `song/vocals.wav` / `song/vocals.m4a`: the vocal stem. `song/stems/` has the drums, bass and other.
- `song/timing.json`: every sung line (`id`, start, end, section) and its words with their times. This is the only
  source of sung words. The screenplay names lines (`{sing:key}`, `{sing:key|l3,l4}`), and `build_prompts.py` fills
  the words in on this machine.
- `song/songmap.json`: beats, bars, and sections with whether they're sung and how much energy they have (from the
  app's analysis and the master's loudness). `song/meta.json`: title, artist, length, and `feel`, the person's
  guidance.
- `analysis/`: the app's measurements, as in its other films (`listening.md`, `analysis.json`). Automatic, so they
  can be wrong.
- `settings.json`, the starter `screenplay.json` and the folders: from `new_project.py --kind music_video` (16:9,
  1920 × 1080, 24 fps).

**Never type the song's lyrics out yourself**: not in the screenplay, prompts, notes, file names or messages.
Anthropic's API stops any reply that reproduces song lyrics, and the session ends there. Refer to lines by id and
time. `build_prompts.py --show N` prints a scene with the sung words masked.

## Running her scripts: `tools/vrgdg.py`

    python3 tools/vrgdg.py song_plan.py .
    python3 tools/vrgdg.py build_prompts.py . --show 3
    python3 tools/vrgdg.py --no-wait render_scenes.py . 1 2 3     (prints an id)
    tail -n 20 vrgdg/logs/<id>.log
    python3 tools/vrgdg.py qa_music.py . 1 2 3

- The scripts run in her ComfyUI container, on this very folder: what they write appears here, and what you write
  here they see. `.` is this project.
- Renders run one at a time on the GPU, about 5–6 minutes a scene. `render_scenes.py` skips a scene that already has a
  clip (it says "already" and "skip"): add `--force` to re-render one. Re-rolls queue behind renders already asked
  for, in order. Rapture's 40 scenes, with re-rolls, took about 4.5
  hours. Before each render the app asks the other ComfyUIs to free their memory.
- The scripts: `song_plan.py`, `build_prompts.py`, `render_scenes.py`, `qa_music.py`, `cut_sheet.py`,
  `continuity_frame.py`, `retrim.py`, `adopt_render.py`, `assemble.py`, `sync_check.py`, `save_refs.py`, `gen_refs.py`.
- What was learned on Rapture:
  - In first-frame mode, a "setting" sentence made H3 open on an establishing wide.
  - The lip-follow measure under-reads fast rap and held notes, so look at the frames before re-rolling.
  - GPT Image 2.5 refused some outfits (leggings fixed a high-cut bodysuit).
  - Text laid over a singer reads best beside the face. Subtitles need about 66 px to read on a phone.

## Pictures

(How you make this video's pictures is filled in when it starts.)

## Also here

- `tools/h3.py`: plain MiniMax H3 through the app's own ComfyUI (a still and a prompt, no singing). Use it for
  inserts if you like. Anyone singing goes through the Builder.

## Hand back

- `out/opening.mp4`, when you're asked for the opening only: the video from the start of the song, 1920 × 1080,
  24 fps, H.264 (yuv420p), with `song/song.m4a` (from its start) as its sound.
- `out/final.mp4`: the whole song, the same way. Her `assemble.py` writes `final/<TITLE>_clean.mp4` with the song put
  back sample-accurately. The title screen and anything on top of it are yours.
- `out/poster.png`: one frame that sells the video.
- `README.md`: what you made, in a few plain sentences for the person first, then how it's put together.

The person reads your messages as you go. Scratch files can go in `out/tmp/`. The person may send notes after seeing
it: each continues this conversation, in this folder.
