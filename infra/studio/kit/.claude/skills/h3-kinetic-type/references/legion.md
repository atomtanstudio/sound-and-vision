# H3 on the machine

H3 here is MiniMax H3 in the ComfyUI on the user's own GPU machine (sv-comfy). What follows was read on 2026-10-04 from a
ComfyUI with the same H3 nodes (`GET /object_info` and the node source), plus the numbers from the owner's lab runs
(`lab/living-album/`, `lab/kinetic-h3/`, not part of this kit). "Verified" means seen in source or measured in the lab;
everything else is marked.

## Where it runs, and the house rules

- ComfyUI is at `SV_COMFY_URL` (default `http://127.0.0.1:8210`, sv-comfy on the same machine; from inside the studio
  container it must be an address the container can reach, see `tools/h3plate.py`). The app's own H3 graph is
  `server/sv/video/h3.py`: the Living Album Cover's loops and a music video's scenes (`tools/h3.py`) both use it.
- Send a job only when the user has asked for a render in this session. Read `GET /queue` first and wait your turn; one job
  at a time. Never change ComfyUI's settings, models, nodes or files, and never restart anything.
- Nothing in the app sends lyric shots to H3 yet.

## The models

| Kind | Files |
|---|---|
| UNET used by us | `minimax_h3_fused_refdelta_r1024_turbo8_mystic07_int8_convrot.safetensors` (6 steps; first/last frame and text-to-video path) |
| Other UNETs | `minimax_h3_fl2va_*` (first/last frame, text to video) and `minimax_h3_ref2va_*` (reference-to-video), in bf16, int8 and pruned builds (Comfy-Org/MiniMax-H3); community merges and turbo LoRAs exist too |
| Text encoder | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` (CLIPLoader type `minimax`); also `_int8_convrot` |
| VAEs | video `minimax_h3_video_vae_int8_convrot` (or `_fp16`); audio `minimax_h3_audio_vae_fp32` |

H3 has two weight families: **fl2va** (text-to-video, first frame, first + last frame; node `MiniMaxH3ImageToVideo`) and
**ref2va** (up to 9 pictures, 3 videos, 3 audios; node `MiniMaxH3ReferenceToVideo`). The H3 Studio node switches weights by
mode the same way.

## The graph we already run (`server/sv/video/h3.py`, from the lab's `la/h3.py`)

`UNETLoader` (fused turbo) → `BlockSparseAttention` (top-k SLA, keep 10%) → `MiniMaxH3SigmaShift` (video 12, audio 3) ·
`CLIPLoader` (Qwen3-VL 32B) · `VAELoader` (video) · `LoadImage` → `MiniMaxH3ImageToVideo` (prompt, width, height, length,
`first_frame`, `last_frame`) → [`MiniMaxH3AddGuide` × pins] → `BasicGuider` → `SamplerCustomAdvanced` (`RandomNoise`,
`KSamplerSelect res_multistep`, `BasicScheduler simple`, 6 steps) → `VAEDecode` (video VAE) → `CreateVideo` (24 fps) →
`SaveVideo` (mp4, h264). The audio side is left out: the output has no sound and the song is added afterwards.

## Route (a): text to video

The same graph with no `first_frame` and no `last_frame`: `MiniMaxH3ImageToVideo` with no pictures is H3's text-to-video
(verified in source; H3 Studio uses it this way). The prompt uses the three official fields with no alignment line. Whether
the fused turbo UNET is as good at pure text-to-video as at first/last frame: **untested**.

## Route (b): a code-drawn typographic still, animated by H3

1. Draw the frame in code at exactly the generation size (for kinetic lyrics, `drawLyricLine` in `web/src/render/lyrics.ts`
   at the moment wanted, onto a canvas, kept as a PNG the way `web/src/render/layerexport.ts` keeps the album title layer;
   a lyric still exporter doesn't exist yet). Use motion-studio's type rules for the lettering.
2. Feed it to `MiniMaxH3ImageToVideo`:
   - `first_frame` is **stretched to the canvas** without keeping its aspect (verified in source), so a still of the wrong
     shape distorts every letter. Render it at the exact `width × height`.
   - `last_frame` is cover-cropped to the canvas (center), keeping its aspect.
   - Both pictures are also passed to the Qwen3-VL text encoder with the prompt (verified: `clip.tokenize(prompt,
     images=images)`), so the encoder sees the lettering; the prompt names them `<Picture 1>` and `<Picture 2>` and starts
     with the alignment sentence (see SKILL.md).
3. `MiniMaxH3AddGuide` pins a picture (or a short clip) at any frame: `frame_idx` (negative counts from the end), `vae` for
   pictures, `audio_vae` for audio. A batch of 5 or more frames is anchored as a clip and cut down to 5, 22, 39 … (17k + 5)
   frames; fewer than 5 uses only the first. The guide must fit: `frame_idx + guide_frames ≤ length`. Chain several. The lab
   pins the cover inside loops this way (`inner_pins`), and a pin measurably holds the picture to it.
4. The idea for exact lyrics (**untested**): pin the frames where a word must be readable (one still, or a 22-frame ≈ 0.9 s
   readable hold) with AddGuide; H3 makes the entrances, exits and everything between pins. A pin fixes the whole picture,
   not just the letters, so the pinned frame must be right everywhere: draw it entirely in code when the backdrop is
   code-drawn or a still (a cover, a color field); for an H3-made world, render once, repaint the lettering correctly over
   that pass's hold frame in code, and render again with the same prompt and seed with the repaired frame pinned. Words
   can still drift between pins, so check those frames.
5. Tail to head: for a shot that continues the previous one, take the previous clip's frame at the cut (after trimming)
   as the next `first_frame`.

## Route (c): the real song in the clip

H3 makes picture and sound together as one latent (`[video, audio]`, audio at 40 latent frames per second). Its own sound is
invented; muting it and laying the song on top afterwards gives a picture that never moved to the song. These nodes put the real
audio into the latent instead (which of them a given ComfyUI has depends on its node packs; sv-comfy has the VRGDG and
H3 audio packs, not `ComfyUI-H3-NativeAudioLock` or Pixaroma's):

| Node | What it does (from its source/description) | Notes |
|---|---|---|
| `MiniMaxH3NativeAudioLock` (custom node `ComfyUI-H3-NativeAudioLock`) | Inputs `model`, `av_latent`, `audio_vae`, `audio`. Encodes the audio with the audio VAE (resampled to the VAE's rate), pads or cuts it to the clip's length, puts it in the latent and sets a noise mask of 1 for video and 0 for audio, so only the picture is denoised while the model attends to the song. Outputs the patched `model`, the locked `av_latent` and the untouched `exact_audio` for muxing. | The mask path is real (ComfyUI's H3 model turns the audio mask into a zero timestep for the audio stream); the extra `minimax_h3_lock_audio_clean` option it sets isn't read anywhere, which looks harmless. Not yet run by us. |
| `PixaromaH3AudioSync` | Same idea; works out the clip length itself, pads with silence or loops a short track, warns past ~15 s. Inputs `model`, `latent`, `audio_vae`, `track`. | Not run by us. |
| `VRGDG_MiniMaxH3AudioDrive` | Replaces the blank audio latent with the encoded track under a zero denoise mask; passes the original audio through. With `MiniMaxH3ReferenceToVideo`, connect the same audio to `ref_audio_0` and call it `<Audio 1>` in the prompt. | A Sound / Vision A/B graph from 2026-09-12 used it: ref2va Singularity + 4-step turbo LoRA, 1344×768, 243 frames, 8 steps (euler, beta), an isolated vocal track as the audio. Its output exists; not reviewed. |
| `MiniMaxH3AddGuide` with `audio` | Anchors a soundtrack from `frame_idx`, cut to the remaining length, as conditioning re-injected every step. | A softer anchor than the lock; not run by us. |

Wiring for the fl2va path (**untested as a whole**): `MiniMaxH3SigmaShift` model and `MiniMaxH3ImageToVideo` LATENT →
`MiniMaxH3NativeAudioLock` (+ `VAELoader minimax_h3_audio_vae_fp32`, + `LoadAudio` → `TrimAudioDuration start_index=<shot's
song start> duration=<length/24>`) → its `model` into `BasicGuider` and `BasicScheduler`, its `av_latent` into
`SamplerCustomAdvanced.latent_image`; `VAEDecode` (video VAE) as before; `CreateVideo` gets `audio = exact_audio`.

- The audio must start exactly at the clip's first frame: frame `f` of the clip is song time `start + f/24`.
- Upload the segment or the whole master to ComfyUI's input folder the same way `la/h3.py` uploads the still
  (`/upload/image`; ComfyUI keeps any file there, but our client has only sent images so far, **unverified for audio**).
- The full mix gives the beat; an isolated vocal (a take's `vocals` stem) is what the A/B lip-sync test used. For kinetic
  type with no singer on screen, use the full mix.
- Say in the prompt that the supplied song plays unchanged (see the sound lines in SKILL.md). Whether describing the song
  in the prompt improves the lock: **unknown**.
- In the edit the master take's audio is laid once, continuous; the clip's audio is dropped either way.

## Frame grid and timing math (verified in source)

- 24 fps. `length` must be 17k + 5 frames; ComfyUI rounds **up** to the grid (the H3 Studio node does too; the lab's
  `snap_length` rounds to the nearest, so ask for a length that's already on the grid).
- Trained range ≈ 124–362 frames (5.2–15.1 s); longer is untested (the node's own note) and shorter is outside the range
  too, so a 2–4 s shot is made at 124 frames or more and trimmed in the edit.

| Frames | 124 | 141 | 158 | 175 | 192 | 209 | 226 | 243 | 260 | 277 | 294 | 311 | 328 | 345 | 362 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Seconds | 5.17 | 5.88 | 6.58 | 7.29 | 8.00 | 8.71 | 9.42 | 10.13 | 10.83 | 11.54 | 12.25 | 12.96 | 13.67 | 14.38 | 15.08 |

- Pick the smallest length ≥ the shot's duration; generate from the shot's song start; trim the tail at the cut.
- Song time `t` inside a clip starting at `s` is frame `round((t − s) × 24)`. Use it for guide frames and for checking.

## Resolution

- ComfyUI's H3 code caps the canvas at 768 × 1344 pixels of area (≈ 1.03 MP) on a 768 short edge, sides in multiples of 32
  (verified). H3 Studio's presets: 832×480, 960×544, 1088×608 (balanced), 1344×768 (native), the 9:16 mirrors, 1024×1024,
  896×1120, 1120×896.
- The fused turbo UNET: the user's note is a ~1024 px long side; the lab made 768² and 1024² clips with it. Use 1024×1024
  (1:1), 1024×576 (16:9) and 576×1024 (9:16) with it. 1344×768 is for the full fl2va or ref2va UNETs (not tried in the lab).
- At these sizes, small H3-drawn text is the first to break; see SKILL.md section 1. Whether upscalers (SeedVR2,
  Topaz) keep letters intact is **untested**.

## Speed (lab, ComfyUI's own execution time, models loaded, 6 steps, no audio)

| Clip | Render |
|---|---|
| 768², 5.9 s (141 frames) | 30 s |
| 1024², 5.9 s | 46–48 s |
| 1024², 12.2 s (294 frames) | 106 s |

An 8 s 1024² clip should take roughly 65–75 s (interpolated, not measured); audio lock and guides add little in principle
(**not measured**). A 3-minute song cut into ~40 shots is on the order of an hour of GPU time per full pass, before retries.

## Prompt facts from the H3 Studio node (`ComfyUI-MiniMax-H3-Studio/core.py`)

- Text-to-video: exactly `integrated_multimodal_description`, `overall_soundscape`, `non_diegetic_music`; start with
  `[Shot 1]`, later shots with increasing cut times.
- First frame: begins "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully
  referenced." First + last: an alignment sentence mapping `<Picture 1>` to 0.00 s and `<Picture 2>` to the end time.
- Reference mode: six sections, `subject_definitions`, `summary`, `retention_analysis`, `detailed_description`,
  `overall_soundscape`, `non_diegetic_music`, using only the labels that are connected.
- Write the prompt in English; keep dialogue and visible text in their own language; stable speaker IDs `(S1)`; dialogue as
  `<d>[Language] text</d>`; concrete camera motion, amplitude, speed, blocking, light and sound rather than mood words.
- From our own measurement (`server/sv/video/h3.py`): given a still and only "locked-off camera", H3 cut to close-ups and back
  in three of four clips; saying "one continuous shot, no cuts, seen from the same distance" stopped it. Say explicitly
  whether a lyric shot may cut inside itself.

## Not verified

- The audio lock, AddGuide audio, the code-drawn pinned hold, text-to-video with the fused UNET, audio upload through our
  client, and render times with audio: none run by us yet.
- Whether the 7,000-character prompt cap of MiniMax's hosted API applies to the open weights (no limit was found in the
  ComfyUI node; we keep under it).
- Spelling reliability of H3-drawn words at our sizes: no measurement yet; the only evidence is MiniMax's own fallback rules
  and garbled text baked into a generated reference video.
