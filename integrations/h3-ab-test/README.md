# H3 matched A/B test

Installed September 12, 2026. No renders were submitted during setup.

Open **Workflows > SoundVision A-B Tests** in each runtime:

| Preset | ComfyUI | Saved workflow |
|---|---|---|
| A: Helix fused Turbo, 4 steps | http://192.168.1.100:8194 | A - Helix 4 step Turbo |
| B: Singularity first pass + Turbo LoRA, 8 steps | http://192.168.1.100:8189 | B - Singularity 8 step Turbo |

The workflows use separate runtimes because the fused checkpoint needs the fused engine's multihead support. The production engines and apps were left unchanged. Both canvases have the same labeled input controls; edits do **not** synchronize between them.

## Run a comparison

1. Ensure other app renders have finished. Before the first comparison, use the Comfy menu at top left > **Edit > Unload Models and Execution Cache** in both runtimes.
2. Leave the prefilled controls unchanged for the first pair, or make the same input changes in both canvases.
3. Run A. Wait until it finishes, then use **Edit > Unload Models and Execution Cache** in A.
4. Run B. Wait until it finishes and unload B before switching back to A.
5. Compare the video previews or the saved output files. Run only one runtime at a time: they share the same GPU. Keep the seed's **control after generate** set to **fixed**.

For another source image, upload the identical file to both canvases. Picture 1 is the scene frame; Picture 2 is the character sheet. Keep picture ordering and prompt tags consistent. For another prompt, paste the same text into both PROMPT controls. For another seed or frame count, update both copies.

## Matched inputs

- Open Source Must Win, scene 08 / Held Close, song interval 1:10–1:20.
- Source job: `7ca060d9-2960-449d-bd8e-eaebdf251698`.
- Identical prompt, storyboard frame, character sheet, and continuous isolated vocal excerpt.
- Seed `256623654`; native size 1344 × 768; 243 frames at 24 fps (10.125 seconds).
- Reference sizing `match`, denoise 1.0, continuous source vocal locked into the audio latent on both paths.
- No face refinement passes, upscaling or frame interpolation.

The source files are copied byte-for-byte into each runtime's input directory as `SV-AB-scene08-reference-1.png`, `SV-AB-scene08-reference-2.png`, and `SV-AB-scene08-vocal.wav`. These ComfyUI versions only list top-level inputs in their file pickers.

## Preset differences

| Setting | A | B |
|---|---|---|
| Checkpoint | `minimax_h3_fused_refdelta_r1024_turbo8_mystic07_int8_convrot.safetensors` | `singularity/Minimax-h3_Singularity_ref2va_Pruned_v1.3_int8.safetensors` |
| Turbo | Baked into fused checkpoint | `singularity/minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors`, strength 1.0 |
| Steps / sampler / scheduler | 4 / res_multistep / simple | 8 / euler / beta |
| Attention | SLA top-k, keep 10%, active 0–100% | Sage patch + Sol-Attn tau 1.3, active 20–100% |
| Sigma shift | Video 12, audio 3 | None |
| Video decoding | Fast VAE, tile batch 4 | Standard VAE, with cache cleanup before decoding |
| MP4 encoding | Native SaveVideo H.264 auto | VHS H.264, yuv420p, CRF 16 |

This is a comparison of the two complete presets. Differences cannot be attributed to the checkpoint alone: sampler, attention, decoder, encoding and runtime also differ. Both use the same video/audio VAEs and Qwen text encoder. Both retain the same reference/audio conditioning, including both reference images, even though the older Helix audio-drive UI restricts its asset picker to one image.

## Outputs and verification

- A outputs: `/srv/ai/research/h3-fused-turbo/profile/output/soundvision-ab/A-Helix-4-step/`
- B outputs: `/srv/ai/comfyui/profiles/lab/output/soundvision-ab/B-Singularity-8-step/`
- `A-workflow.json` and `B-workflow.json`: native ComfyUI saved canvases.
- `A-export-api.json` and `B-export-api.json`: the executable graphs exported after reopening the saved canvases.
- `verification.json`: checks and matching SHA-256 hashes. Both queues were idle at verification.
- `case.json`: source paths and the original prompt.

Validation covered native frontend import/save/reload, exact input round trips, fixed seeds, registered nodes/models/media, numeric bounds, output links and absence of graph cycles. It did not evaluate generated video quality or GPU execution. The saved canvases were serialized by each runtime's own frontend, using ComfyUI's [workflow format](https://docs.comfy.org/specs/workflow_json).
