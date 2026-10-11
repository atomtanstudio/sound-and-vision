# What runs beside the app

This folder is named after the reference machine, Legion: the owner's Ubuntu box with an RTX 5090 (32 GB), where
Sound / Vision is developed. Nothing here needs that machine. `scripts/install.sh` builds and starts these pieces for
an install from a checkout, with the paths in `sv.env` (see `sv.env.example`). Where this page describes the owner's
own machine, it says "the reference machine"; you don't need to copy that layout.

| Piece | Built from | Runs as | What it does |
|---|---|---|---|
| **sv-comfy** | `comfy/` | container `sv-comfy`, compose project `sv` in `$SV_COMFY_ROOT/deploy/`, port 8210 | The one ComfyUI for Sound / Vision: YuE2, MiniMax Music 3 and ACE-Step 1.5 (ComfyUI's native nodes), Krea 2 pictures, SAM 3.1, and MiniMax H3 with VRGameDevGirl's music-video routes. The app uses it only through its API (`SV_COMFY`). |
| **sv-analysis** | `analysis/` | image `$SV_ANALYSIS_IMAGE` (default `sv-analysis:latest`), one `docker run --rm --gpus all` per job | Stems (MelBand RoFormer vocals, htdemucs_6s instruments), word timing (wav2vec2 CTC), Whisper, beats. Holds no VRAM between jobs. |
| **sv-claude-studio** | `../studio/` | image `sv-claude-studio:latest`, one container per Claude session | Claude Code under the owner's own Claude plan, with Chromium on the GPU, ffmpeg and the film kit. See `infra/studio/README.md`. |
| Influence Engine tools | `influence/` | started by the app | `listen.py` (MOSS-Music captions) and `convert.py` (FL YuE2 checkpoints to ComfyUI LoRAs). |
| Influence descriptions | `influences/yue2/` | copied to `$SV_LORAS/soundandvision/yue2/` | The sidecar JSON of the two influences the app knows by name (their weights aren't in this repository). |
| ACE-Step 1.5 fetcher | `models/fetch_ace15.sh` | by hand | Downloads ACE-Step 1.5's four files into `$SV_MODELS/comfyui`, checksummed. |

## sv-comfy

- **Image.** `sv-comfy:0.39-c9d8a6e`, built on your machine from public sources by `comfy/Dockerfile`: ComfyUI 0.39 at
  core `c9d8a6e`, CUDA 13.2 with cuDNN 9.20 (Ubuntu 24.04, Python 3.12), Torch 2.11 + cu130, SageAttention 2.2
  compiled for your GPU (`TORCH_CUDA_ARCH_LIST`, read from `nvidia-smi`: 12.0 for RTX 50xx, 8.9 for RTX 40xx, 8.6 for
  RTX 30xx, 8.0 for A100, 9.0 for H100), every other Python package pinned in `comfy/requirements.lock.txt`, and the
  node packs below. It reproduces the image the reference machine runs (read from that image's history, its build
  files and the running container on 2026-10-10). Build it where it runs; it isn't published anywhere.
- **Profile.** `$SV_COMFY_ROOT/profile/` (install.sh's default: `$SV_DATA/comfy/profile/`) holds `custom_nodes`,
  `input`, `output`, `temp` and `user`.
- **Caches.** `$SV_COMFY_ROOT/cache/`. Hugging Face is offline: ComfyUI never downloads a model by itself.
- **Models.** `$SV_MODELS` is mounted read-only at `/srv/ai/models` inside the container. That inside path is fixed:
  `comfy/extra_model_paths.yaml` and VRGameDevGirl's scripts use it. ComfyUI's model folders are
  `$SV_MODELS/comfyui/<kind>/` (`checkpoints`, `diffusion_models`, `text_encoders`, `vae`, `loras` …).
- **Flags.** `--disable-dynamic-vram`, `--reserve-vram 2`, `--disable-api-nodes`, `--preview-method none`. They come
  from running the VRGDG H3 routes on the 5090: estimate-based loading keeps a 1080p H3 refine pass from running out of
  memory, and 2 GB stays free for the app's renders.
- **Access.** It runs as you (`SV_UID:SV_GID`) with no capabilities, on `SV_COMFY_BIND:SV_COMFY_PORT`. ComfyUI has no
  sign-in, so install.sh binds it to `127.0.0.1` when `SV_COMFY` is a local address. Set `SV_COMFY_BIND=0.0.0.0` only
  when another machine, or a container on the bridge network, needs to reach it.
- **Custom nodes.** Checked out in the image at the commits in `comfy/node_packs.txt`. `comfy/setup.sh` copies any that
  are missing into the profile, where ComfyUI loads them (`--base-directory`). They match the reference machine's
  working VRGDG H3 checkouts file for file.

  | Node pack | Commit | Note |
  |---|---|---|
  | [comfyui-vrgamedevgirl](https://github.com/vrgamegirl19/comfyui-vrgamedevgirl) | 3432b03 | its own community/commercial licence |
  | [comfyui-minimax-h3-audio-T8](https://github.com/T8mars/comfyui-minimax-h3-audio-T8) | 8b7408e | |
  | [Comfyui_Minimax_h3_latent_Upscaler](https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler) | 40316cf | |
  | [TE-Speed-MiniMaxH3-OSS](https://github.com/HELPMEEADICE/TE-Speed-MiniMaxH3-OSS) | c1dacf4 | core patch not applied |
  | [ComfyUI-KJNodes](https://github.com/kijai/ComfyUI-KJNodes) | 195d312 | GPL-3.0; with local fixes, `comfy/patches/ComfyUI-KJNodes-minimax.patch` (GPL-3.0 too) |
  | [ComfyUI-VideoHelperSuite](https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite) | 4ee72c0 | |
  | **sv_nodes** | ours, `comfy/custom_nodes/sv_nodes` | |

  The VRGDG pack's `nodes.py` and `GeneralVideoNodes.py` (they need librosa) and its LTX looping sampler don't load,
  and H3 doesn't need them. The packs' own requirements files aren't installed: the lock file is what they were tested
  with. It includes `nvidia-vfx`, NVIDIA's proprietary Video Effects binding (from NVIDIA's own package index), which
  KJNodes' `nvidia_rtx_vsr` resize uses.
- **sv_nodes.** `SVAudioRangeMask` marks a time range of an audio latent for re-generation. ComfyUI's
  `SetLatentNoiseMask` only makes image-shaped masks. This node is what makes ACE-Step's "replace these bars" work.

**Set it up.** `scripts/install.sh` does it all. By hand, from the repo (the first run builds the image, about an
hour; the host needs Docker, the NVIDIA Container Toolkit and a driver for CUDA 13.2 or newer):

```sh
SV_COMFY_ROOT=$PWD/data/comfy SV_MODELS=$PWD/models infra/legion/comfy/setup.sh
cd data/comfy/deploy && docker compose up -d
```

Always pass `SV_COMFY_ROOT` and `SV_MODELS`: `setup.sh`'s own defaults are the reference machine's paths. Its other
settings (`SV_COMFY_IMAGE`, `SV_COMFY_BIND`, `SV_COMFY_PORT`, `SV_UID`/`SV_GID`, `SV_CUDA_ARCH`) are listed at the top
of `comfy/setup.sh`; it writes them all to `deploy/.env`, which compose reads. To rebuild the image (new pins, another
GPU), remove it or pick a new `SV_COMFY_IMAGE` tag and run `setup.sh` again, then `docker compose up -d` in the deploy
folder. To update sv_nodes, run `setup.sh` again (install.sh does, and restarts sv-comfy when they changed).

## sv-analysis

A thin layer over the sv-comfy image (same Torch build): `docker build -t sv-analysis:latest infra/legion/analysis`
(`--build-arg BASE_IMAGE=…` for another sv-comfy tag). The app runs one container per job with `--user 1000:1000`,
mounting the take's folder, `infra/legion/analysis/worker` (`SV_ANALYSIS_WORKER`) read-only, and these models:

- `$SV_ANALYSIS_MODELS` (default `$SV_MODELS/audio-separation/sv`), read-write, also its `TORCH_HOME`. The first
  analysis fetches what's missing: `vocals_mel_band_roformer.ckpt` (about 0.9 GB) and htdemucs_6s through
  audio-separator, and wav2vec2 large (LV60K, 960 h, about 1.2 GB) through torchaudio into `torch/hub/checkpoints/`.
  The container needs internet access then, and uid 1000 needs write access to this folder and to the data folder.
- `$SV_WHISPER` (default `$SV_MODELS/huggingface/models--Systran--faster-whisper-large-v3`, a Hugging Face cache
  folder with `snapshots/`), read-only. Only used to hear the words of your own uploaded songs that came without
  lyrics; without it those songs get beats and sections but no word timing.

## Influences

`influences/yue2/` holds the sidecars of the influences the app knows by name:

| File | Folder under `$SV_MODELS/comfyui/` | Size | What |
|---|---|---|---|
| `ar_lora_inst_v3abc_comfyui.safetensors` | `loras/soundandvision/yue2/` | 203 MB | Keeps YuE2 from singing; the app uses it for every YuE2 instrumental. "YuE2-instrumental-cot-full-loras" by Mothersuperior (CC BY-NC 4.0), downloaded unmodified from the author's page by `scripts/install.sh` (see `CREDITS.md`). |
| `sv_dreampop_v1.safetensors` | same folder | 112 MB | "Dream pop", trained with AI-Toolkit on the owner's own set; only on the reference machine. |

An influence the library lists is a `.safetensors` file in `loras/soundandvision/<model>/` (`yue2`, `ace15`,
`music3`) with a sidecar `<name>.json` beside it. The app writes both when you train one or add one.

## GPU sharing

Before a big job the app may ask the other ComfyUI instances on the machine (`SV_OTHER_COMFYS`, comma-separated) to
unload their idle models with `POST /free`. That is no restart, and nothing stops. `/free` is lazy: ComfyUI acts on
it a moment later, not when the call returns. `SV_FREE_OTHERS=0` never asks. On the reference machine four other
ComfyUI instances share the card, and the owner allowed this.

## The Influence Engine's pieces

The app trains influences itself (the Influence Engine). It needs these, which you set up beside it; without them the
rest of the app works.

- **Trainer.** [FL YuE2](https://github.com/filliptm/ComfyUI-FL-YuE2) (its `FL_YuE2_*` training nodes) in its own
  ComfyUI container: the container `SV_TRAINER_CONTAINER` (default `ai-comfy-fl-yue2`), its API at `SV_TRAINER`
  (default `http://127.0.0.1:8196`), ComfyUI at `/opt/ComfyUI-YuE2` inside, with its `input/` and `output/` folders
  mounted from `$SV_TRAINER_ROOT/input` and `$SV_TRAINER_ROOT/output` (default `$SV_DATA/trainer`). The app submits
  FL's five training nodes as an API graph (the standard recipe with the sound branch, `train_acoustic`), follows each
  step in the worker log (`output/yue2_training/jobs/*.log`) and the run record at each checkpoint
  (`output/yue2_training/<run>/run.json`), and copies the previews out. Training sets are written to
  `input/training/sv-<style>-<id>/` (FLAC plus `.caption.txt`, `.lyrics.txt`, `.song.txt`). FL writes its outputs as
  root, readable only inside the container, so the app reads them with `docker exec … cat`. The graph asks FL not to
  download anything (`download_missing: false`), so the trainer's own files (`tokenizer_head_joint_v4.pt`,
  `minted_regularizer_pack.pt` and the YuE2 weights it trains on) must already be in its models folder.
- **Converter.** `influence/convert.py` (`SV_INFLUENCE_TOOLS`), piped into the trainer's container. FL saves split
  q/k/v and gate/up projections; ComfyUI's YuE2 fuses them, so each group becomes one LoRA (shared down-projection:
  stacked ups; separate ones: stacked downs and block-diagonal ups), checked against FL's own product, stored as bf16.
  The sound branch's latent-projection changes go as `.diff` / `.diff_b`. Converted copies land in
  `output/sv-export/<run>/`, then in the library (`$SV_LORAS/soundandvision/yue2/`).
- **Listening.** `influence/listen.py`, run with `SV_LISTEN_PYTHON` (a venv with PyTorch for CUDA and what MOSS-Music
  needs; default `$SV_DATA/listen/venv/bin/python`), MOSS-Music's code (`SV_MOSS_CODE`, default `MOSS-Music/` beside
  the venv) and its model (`SV_MOSS_MODEL`, default `models/MOSS-Music-8B-Instruct` beside the venv). It writes a
  caption per song, and lyrics only for songs that have none yet (from an `.lrc` file or the file's tags). Lyrics go
  only to the sidecar files and are never printed.
- **Songs.** Your own music. `SV_MUSIC` is a folder laid out `Artist/…/Song.flac`, or a network share as
  `smb://host/share/path` (read as a guest with `smbclient`). A song that isn't there, you add by hand to the run.
  Nothing is downloaded from any service.
- **GPU.** Before MOSS (about 19 GB) or training (about 13 GB plus previews) every ComfyUI is asked to `/free`, and the
  app waits until the memory really is free. Training holds the GPU lane: songs made meanwhile wait their turn.

## VRGameDevGirl's Video Builder

Performance and Hybrid music videos (people singing the song, lip-synced) run VRGameDevGirl's H3 film skill
(`vrgdg-h3-film`) in a ComfyUI container that has her node pack, which you set up beside the app. The app starts her
scripts in it with `docker exec`, so the container must have:

- the name `SV_VRGDG_BOX` (default `ai-comfy-vrgdg`) and its API at `SV_VRGDG_URL` (default `http://127.0.0.1:8199`);
- its profile folder at `/vrgdg/profile`, mounted from the host; the films folder inside it, `SV_VRGDG_FILMS_IN`
  (default `/vrgdg/profile/output/films`), is `SV_VRGDG_FILMS` on the host (default
  `$SV_DATA/video-builder/output/films`);
- the skill inside that profile, at `SV_VRGDG_SKILL` (default `/vrgdg/profile/claude/vrgdg-h3-film`), run with
  `SV_VRGDG_PYTHON` (default `/opt/venv/bin/python`);
- the models folder at `/srv/ai/models`, as in sv-comfy, with the models her skill's README lists.

## The reference machine's layout

For the owner's own deployment; an install from a checkout keeps everything under the checkout instead.

| What | On the reference machine |
|---|---|
| The app, deployed from another computer with `scripts/deploy.sh` | `/srv/ai/sv`: `app/` (the server), `web/dist`, `sv.env`, `analysis/worker`, `influence` |
| Data (`SV_DATA`) | `/srv/ai/sv/data` |
| Models (`SV_MODELS`) | `/srv/ai/models`, shared with its other ComfyUI instances |
| sv-comfy (`SV_COMFY_ROOT`) | `/srv/ai/sv/comfy` (the defaults in `comfy/setup.sh` and `comfy/docker-compose.yml`); the image is still the tag it was first given (`sha256:6cd2bfc0…`, built from the lab image) |
| sv-analysis | `sv-analysis:20261008` (`SV_ANALYSIS_IMAGE`) |
| FL YuE2 trainer | container `ai-comfy-fl-yue2` on port 8196, `SV_TRAINER_ROOT=/srv/ai/comfyui/profiles/fl-yue2` |
| MOSS-Music | venv `/srv/ai/sv/listen/venv`, model `/srv/ai/models/moss-music/MOSS-Music-8B-Instruct` |
| Video Builder | container `ai-comfy-vrgdg` on port 8199, profile `/srv/ai/research/vrgdg-h3/profile`, with a locally changed copy of the VRGDG skill (its `CHANGES-LOCAL.md`) that isn't in this repository |
