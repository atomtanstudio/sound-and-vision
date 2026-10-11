# Phase 0 results: Legion consolidation and spikes

Run on 2026-10-08 against the new `sv-comfy` (ComfyUI 0.39, :8210) and `sv-analysis` on
Legion. Setup and file locations are in `infra/legion/README.md`; the test scripts are in
`spikes/`. Test audio and video are in `spikes/out/`, which git ignores.

## 1. The three music models through ComfyUI's API: **pass**

`spikes/comfy_music.py` uses API graphs written from ComfyUI's own templates. Each run used
the same original test lyric and style, 60 s asked.

| Model | 60 s of song took (cold, model load included) | Peak GPU | Graph notes |
|---|---|---|---|
| ACE-Step 1.5 XL turbo | **14.1 s** | ~20 GB | `ModelSamplingAuraFlow` shift 3, 8 steps euler/simple, cfg 1; Qwen 0.6B + 1.7B |
| YuE2 3B (bf16) | **30.5 s** | ~20 GB | ABC plan, then music, then 32 steps dpm_2/sgm_uniform |
| MiniMax Music 3 (fp16 DiT) | **86.8 s** | 23.5 GB | 30 steps euler/simple, cfg 1.7 |

- **YuE2 is the default model** (the user's call).
- **The user's ear is still the judge** of quality against the old direct runners.
- **Measuring GPU memory:** the scheduler should read `/system_stats` from ComfyUI rather than `nvidia-smi` right
  after `/free`, because `/free` takes effect a moment after the call returns.

## 2. Influences (LoRAs) in ComfyUI: **pass, pending a listen**

- **DreamPop:** the AI-Toolkit file `sv_dreampop_yue2_s1000_v1` carries both branches, `text_encoders.*` (AR) and
  `diffusion_model.*`. It went through ComfyUI's ordinary `LoraLoader` on YuE2 at 0.6 with **zero "lora key not
  loaded" warnings**, so no converter is needed. The run took 91 s, a cold load plus patching.
- **Instrumental:** the influence already had a ComfyUI-format copy (AR branch, `lora_down`/`lora_up`).
- **To do:** the user should listen to `2 YuE2 + DreamPop influence 0.6` against the old app's DreamPop takes.

## 3. Section replace (ACE-Step "repaint"): **pass**

ComfyUI has no ACE-Step 1.5 repaint node, and its `SetLatentNoiseMask` can't shape a mask for audio. The fix:

1. **Our node, `sv_nodes/SVAudioRangeMask`,** puts an audio-shaped mask on the source song's latent. ComfyUI's ordinary
   sampler then re-generates only inside the range.
2. **The splice:** the app crossfades the new stretch into the original audio (equal power, 1 s). Without the splice,
   the parts outside the range pick up the VAE round trip, about −16 dB of difference.

Measured on seconds 20–32 of the 60 s ACE-Step song:

| | Inside the range | Outside the range |
|---|---|---|
| Change | completely new (+2 dB difference) | **−180 dB, bit-exact** |
| Time | 14 s | |

Also found: ACE-Step 1.5's "Set Reference Audio" (`ReferenceTimbreAudio`) switches the model into cover mode, so
ACE-Step covers are native.

## 4. `sv-analysis`: stems and word timing on the GPU: **pass**

- **Stems.** Measured on Rapture (3:52):

  | Pass | Model | Output | Time |
  |---|---|---|---|
  | 1 | MelBand RoFormer (Kimberley Jensen, vocals SDR 12.6) | vocals + rest | 7.7 s |
  | 2 | htdemucs_6s on the vocal-free rest | drums, bass, guitar, piano, other | 11.0 s |
  | **Whole song** | | | **18.8 s** |

  The old app's HTDemucs ran on the CPU and took minutes.
- **Word timing.** The old aligner (wav2vec2 CTC) on each vocal stem, scored against the user's Rapture LRC line starts
  (`spikes/align_compare.py`, numbers only):

  | Vocal stem | Median error | Within 0.3 s | Worst line, no hints | Worst line, anchored on the LRC |
  |---|---|---|---|---|
  | Old HTDemucs | 0.056 s | 35/36 | 20.1 s (one repeated line placed on its other repeat) | 0.93 s |
  | **New MelBand RoFormer** | 0.059 s | 35/36 | 20.2 s (same line) | 1.05 s |

  Timing is just as accurate and the stems are about 10× faster. The one stray line is the same in both runs.
- **The image.** `sv-analysis:20261008` is sv-comfy's Torch build plus audio-separator 0.47, faster-whisper 1.2,
  beat_this 1.1, audioread and pyloudnorm.

## 5. VRGameDevGirl's H3 music-video route in sv-comfy: **pass (same quality)**

- **What was run:** the vrgdg-h3-film skill and a slim copy of the Rapture project (520 MB), placed in sv-comfy's
  profile and pointed at :8210. Then `render_scenes.py` re-rendered scene 7 with the original seed. It used the
  Builder endpoint, 2-pass ref2va plus the turbo LoRA, the latent upscale, and trimming.
- **Render time:** 341 s for one 6.4 s scene, the same as on the VRGDG instance.
- **Format:** identical (1920×1080, 24 fps, 155 frames). **The song-locked audio is bit-identical** (same MD5).
- **The picture:** not identical (SSIM 0.76). ComfyUI 0.39 computes differently from 0.34, so the same seed gives a
  different take. The new take is clean and on-model: the Host's white streak, tux and mic in the purple club. It stays
  in the singing close-up where the original opened on a wide shot.
- **Lip-follow** (`qa_music.py`):

  | Scene 7 | Shot 1 | Shot 2 |
  |---|---|---|
  | Original | 0.30 | 0.67 |
  | sv-comfy | **0.08 (flagged)** | 0.65 |

  One take can't tell the version change apart from H3's usual luck, so scenes 8–10 were rendered too.

**Scenes 7–10, same seeds.** Lip-follow on the sung shots, with sync in brackets:

| Scene | Original (0.34) | sv-comfy (0.39) |
|---|---|---|
| 7 | 0.30, 0.67 (0 ms) | 0.08, 0.65 (0 ms) |
| 8 | 0.11 (0 ms) | 0.34 (0 ms) |
| 9 | no sung shot (0 ms) | no sung shot (0 ms) |
| 10 | 0.48 (0 ms) | 0.50 (0 ms) |
| **Mean, sung shots** | **0.39** | **0.39** |

- **Quality is the same.** Each take wins or loses on the seed, as before, and the re-roll step handles weak shots.
- **Speed:** each scene took 310–341 s.
- **Conclusion:** sv-comfy can carry the music videos, and the VRGDG instance on :8199 can retire once the app runs
  them.

## 6. MCP: **pass**

- **Python client:** the `mcp` 2.3 SDK connects over stdio. Blender's server lists 9 tools. Blender itself wasn't
  open, so no tool was called.
  - Keyword labelling is too crude, so labels come from the writer LLM.
  - Blender's add-on on the Mac is out of date. Fix it with `uvx mcp-for-blender install-addon`.
- **A hosted image MCP server:** a standard MCP OAuth setup (protected-resource metadata, dynamic registration, PKCE
  S256). The app's Connect button can do this generically.
- **Connectors on the Claude account:** Claude Code in the studio container, signed in with the user's plan, lists the
  account's claude.ai connectors as connected, so Claude Director runs can use them with no extra setup.
- **Not done yet:** Claude Code calling the app's own `sv` MCP server. That comes with the server in Phase 1, and the
  test spends a little of the plan.
