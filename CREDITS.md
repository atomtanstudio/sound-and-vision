# Credits

Sound / Vision is built on other people's work. The models below are not in this repository; they're downloaded from
their authors' own pages and used as published. Their licences, not this project's MIT licence, govern them.

## Instrumentals: "YuE2-instrumental-cot-full-loras" by Mothersuperior

Every YuE2 instrumental uses this influence (a LoRA for YuE2-3B's planner that makes it write instrumental music with a
section plan, instead of singing).

- Author: **Mothersuperior**
- Source: <https://huggingface.co/Mothersuperior/YuE2-instrumental-cot-full-loras>
- File: `ar_lora_inst_v3abc_comfyui.safetensors` (the author's ComfyUI-layout file), used unmodified.
  `scripts/install.sh` downloads it from the author's page and checks its SHA-256
  (`de6a11d5701df103a191c87dc73115266e2420f3834739319dec5c24d2119f31`).
- Licence: [Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)](https://creativecommons.org/licenses/by-nc/4.0/).
  It may be used and shared for non-commercial purposes, with credit to the author. Anything you make with it is
  bound by the same non-commercial term.

## Influence Engine training: "yue2-mothersuperior-realaudio-tokenizer-v4" by Mothersuperior

The optional FL YuE2 trainer the Influence Engine drives loads `tokenizer_head_joint_v4.pt` from this release. The
app doesn't download it; you add it to the trainer's own models folder (infra/legion/README.md).

- Author: **Mothersuperior**
- Source: <https://huggingface.co/Mothersuperior/yue2-mothersuperior-realaudio-tokenizer-v4>
- Licence: [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/).

## Everything else

The models each feature runs (YuE2, ACE-Step 1.5, MiniMax Music 3, Krea 2, MiniMax H3, SAM 3.1, Whisper, MOSS-Music,
the separation models and the upscaler), and the third-party software in the images (ComfyUI and its node packs,
VRGameDevGirl's Video Builder, NVIDIA's components, Claude Code and the other CLIs), are listed with their sources in
README.md ("Models") and their licences in README.md ("Licences").
