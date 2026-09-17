# Trained styles and artists

Place locally trained **YuE2** LoRAs here on the computer running the Sound and
Vision backend. The default is `<app>/loras`; `SOUND_VISION_LORAS` can select
another folder. Weights are not included in source control.

```text
loras/
  styles/
    DreamPop/
      lora.json
      step-0100.safetensors
      step-0200.safetensors
  artists/
    My artist/
      lora.json
      my-artist.safetensors
```

Use one folder per style or artist. Its checkpoints appear together in the
creation page's **Trained styles & artists** selector. Refresh the page or use
the scan button after adding files. Copy to a temporary extension first and
rename to `.safetensors` when complete. Missing, incomplete or unsupported files
are reported in **LoRA folder** rather than silently used.

An optional `lora.json` in each group folder supplies display metadata:

```json
{
  "name": "DreamPop",
  "kind": "style",
  "trigger": "sv_dreampop",
  "preferred_step": 600,
  "generation": {
    "cot": "off",
    "cfg_scale": 1,
    "ode_steps": 32
  }
}
```

Only `name`, `kind`, and `trigger` are normally needed. Use `kind: "artist"`
for an artist. Without a sidecar, the folder name becomes the display name;
the `artists/` location sets its kind. A single training tag and checkpoint
step can be read from AI Toolkit metadata. Loose files in `loras/` work too,
each as its own entry. Provide a trigger in the sidecar if the exporter omitted
it or recorded several tags.

Generation defaults are optional and apply when selecting a group; switching
checkpoints preserves the current prompt, lyrics, seed, and sampling controls.
Selecting a LoRA never changes the song's generation budget. Short training-preview
limits do not belong in a style preset. The temporary duration selector has been
removed. A one-time draft migration restores its 2/4/8-minute choices (and the
original two-minute LoRA preset) to the app's original 9,000-token safety ceiling,
about six minutes, preserving the rest of the draft. Later Advanced sampling
edits are preserved across reloads. The model may stop earlier by emitting its
end-of-song token; lyric length alone does not determine the stopping point.
Takes that reach their ceiling before the model signals an ending are labeled
**Length limit reached** in the music library. A longer allowance does not
guarantee a natural ending. Changing the generation budget can change a seeded
performance; preserve the original when making another take.
Selecting **Original model · no LoRA** removes the adapter and its automatic
trigger while preserving those controls for comparison. The seed is never
set implicitly. For controlled listening tests use one take, the same fixed
seed, lyrics, prompt, strength, and generation settings.

Supported format: YuE2-3B AI Toolkit PEFT exports containing
`text_encoders.model.layers.*` (AR) and/or `diffusion_model.model.layers.*`
(NAR), using `lora_A.weight`/`lora_B.weight`, with optional per-module `alpha`.
Both experts are applied when present. Fused Q/K/V and gate/up projections are
mapped to the pinned native YuE2 engine's split layers. Missing alpha means
rank, matching this PEFT export format. Arbitrary image LoRAs, full models,
other adapter layouts, and implicit companion-adapter dependencies are not
supported. No AI Toolkit installation is required for generation.

The backend scans metadata without loading Torch/GPU weights. It accepts only
catalog IDs and SHA-256 hashes from the browser, checks the file again before
generation, and merges into the worker's in-memory model before CUDA graph
capture. The source model and adapter files are never overwritten. Every take
retains its selected style/artist, step, trigger, strength and hash in the
library and generation artifacts, even if the original adapter is later moved.

Native generation uses the app's unquantized BF16 YuE2 base and listening VAE.
AI Toolkit previews may use a quantized base and different synthesis/decoding
implementation. Matching the LoRA and controls does not promise identical
waveforms between engines; judge results in the app.

For adapters trained on the AI Toolkit ConvRot8 YuE2 checkpoint, the operator can
configure the matched inference engine described in
[operations](../docs/backend/OPERATIONS.md#matched-yue2-lora-inference).
Selected LoRAs then use the original ConvRot8 backbone, unmerged FP32 adapters,
sampler and embedded VAE inside the app's existing queue. Both AR and NAR weights
remain active when present. Ordinary generation continues through the native
engine. Guidance must be 1 (or blank for the matched engine's default of 1).
This uses an already installed inference runtime; it does not start training or
install packages. Each take records the actual engine, checkpoint digest and
runtime source hashes. A missing configured engine fails visibly instead of
silently changing the generation method.
