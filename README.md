# Sound / Vision

Sound / Vision is a self-hosted studio for making songs and the covers and videos that go with them. It runs on one
Linux machine with an NVIDIA GPU, keeps the models on that machine, and serves its web interface to the other devices
on your home network. The music, picture and video models run locally in ComfyUI. The language models you connect
(a local model, or frontier ones under your own accounts) write the lyrics, plan the pictures and direct the videos;
you choose which does what.

- **Music.** Songs from your lyrics and a style, with YuE2 (the default), ACE-Step 1.5 or MiniMax Music 3. Several
  takes, covers of a song (YuE2), new versions of a few bars (ACE-Step), or your own uploaded songs. Every song is
  analysed: stems, beats and sections, and its words timed.
- **Album covers.** From ChatGPT's image tool ("Sign in with ChatGPT"), Krea 2 on your GPU, or an image MCP server of
  your own, with the title and logos laid out in your house look.
- **Video.** Three kinds:
  - *Living Album Cover*: the cover, gently moving, as a seamless loop made with MiniMax H3.
  - *Motion Graphics*: a film your director model writes in code (kinetic type and graphics on the song's real timing),
    rendered in a headless browser on your GPU.
  - *Music Video*: Performance, Hybrid or Surreal, directed by your director model, with every scene filmed by MiniMax H3 on
    your GPU. Performance and Hybrid lip-sync the real vocal with VRGameDevGirl's Video Builder (optional, see below).
- **Library, Brand and Share.** Your songs and videos in folders. Your logos and house look. Clips cut for TikTok,
  Reels, Shorts and posts.
- **Influence Engine.** Trains a style LoRA (an "influence") for YuE2. Your chosen model picks the artists and songs that define
  the sound, you supply the audio from your own music folder or by upload, MOSS-Music captions it, FL YuE2 trains,
  and you pick a checkpoint by ear. Nothing is downloaded from any music service.
- **Models.** A local model through Ollama, or Claude (Claude Code in the studio container), ChatGPT (OpenAI's Codex
  CLI) or Grok (xAI's CLI), each signed in with your own account (no API keys; Ollama needs none). You choose who does
  what in Settings; the interface names a model only once you've connected it. Videos made in code need a director that
  can write and run code: today that's Claude Code.
- **MCP servers.** Add your own (streamable HTTP, with a key or their OAuth sign-in) in Settings. Your director model
  can use them while it works, and they can make pictures or animate scenes. Servers marked paid ask before each job.

## Set it up, step by step

Plan an afternoon. The first install builds the app's containers (about an hour), and the models are big downloads
(about 28 GB to make songs and covers, 41 GB more for videos). Everything below happens in a terminal on the GPU
machine, logged in as the account the app will run as: at its keyboard, or over `ssh`, but not through `su` or `sudo`.

### 1. Check the machine

You need Linux on x86_64 (developed on Ubuntu; the reference machine runs Ubuntu 26.04), an NVIDIA GPU with 24 to
32 GB of memory, and about 200 GB of free disk. The full list is under [Requirements](#requirements).

### 2. Install what the app runs on

These are the commands for Ubuntu. On another distribution, follow each project's own guide.

**The NVIDIA driver.** Install the recommended driver, restart, then check it:

```sh
sudo ubuntu-drivers install
sudo reboot
nvidia-smi
```

`nvidia-smi` must list your GPU and show "CUDA Version: 13.2" or higher (the reference machine runs driver 595.99).
If the version is lower, install a newer driver from [NVIDIA](https://www.nvidia.com/en-us/drivers/).

**Docker.** Install Docker Engine with its Compose plugin, and let your account use it:

```sh
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
```

Log out and back in, so the new group takes effect. `docker run --rm hello-world` should then work without `sudo`.

**NVIDIA Container Toolkit.** This lets containers use the GPU. These are
[NVIDIA's commands](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html):

```sh
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
docker run --rm --gpus all ubuntu nvidia-smi
```

The last command should print the same GPU table as before, from inside a container.

**The rest:** git, ffmpeg, curl, [uv](https://docs.astral.sh/uv/) and Node.js 22.

```sh
sudo apt-get install -y git ffmpeg curl
curl -LsSf https://astral.sh/uv/install.sh | sh
sudo apt-get install -y nodejs npm
node --version
```

Open a new terminal afterwards, so `uv` is on your `PATH`. If `node --version` is older than 22.12, install Node 22
from [NodeSource](https://github.com/nodesource/distributions) instead.

### 3. Install Sound / Vision

```sh
git clone https://github.com/atomtanstudio/sound-and-vision.git
cd sound-and-vision
scripts/install.sh --check
```

`--check` changes nothing. It lists anything still missing, marked `needed`. Put those right, then install:

```sh
scripts/install.sh --open-lan
```

`--open-lan` lets the devices on your home network use the app without a key. Leave it out if other people share your
network. The first run takes about an hour, most of it building the `sv-comfy` image. It ends by printing the
addresses to open. If it says linger needs an administrator, run the `sudo loginctl enable-linger` command it prints,
so the app starts with the machine. [What install.sh does](#what-installsh-does) has the details.

### 4. Download the models

```sh
scripts/models.sh                  # what each set is for, its size, and what's here already
scripts/models.sh starter          # songs, covers and pictures (about 28 GB)
scripts/models.sh video            # Living Album Covers and music videos (41 GB more)
```

The other sets are `ace` and `music3` (two more song models), `whisper` (hears the words of songs you upload without
lyrics) and `all`. Each file is checked against its published checksum. An interrupted download carries on where it
stopped when you run the command again. Each model has its own licence; see [Licences](#licences). MiniMax H3's
licence doesn't cover use in the US, the EU, the UK or Korea.

### 5. Connect a language model

A language model writes the lyrics, names things and plans the pictures. Connect at least one.

- **On the machine itself.** Install [Ollama](https://ollama.com) and pull a model; it shows up in Settings. A small
  model leaves the GPU to the music and video models (the reference machine runs `qwen3.5:4b`):

  ```sh
  curl -fsSL https://ollama.com/install.sh | sh
  ollama pull qwen3.5:4b
  ```

- **A frontier model under your own account.** Claude, ChatGPT or Grok: see [Sign-ins](#sign-ins). Motion Graphics
  and music videos need a director that writes and runs code, which today is Claude Code. Sign it in once from this
  checkout:

  ```sh
  infra/studio/studio.sh signin
  ```

  It prints a link. Open it in any browser, approve, and paste the code back.

### 6. Open it and make something

On your phone or laptop, open `http://<machine>:7660`, using the name or address install.sh printed. (Without
`--open-lan`, pair the browser first: see [Open it](#open-it).)

1. Open **Settings** (top right). Check that your language model shows as connected, and choose who does each job
   under **Who does what**.
2. On **Home**, describe a song in a sentence. You get the lyrics and takes to listen to, then stems and timed words.
3. Open a song's cover to paint one. Then go to **Video** to make a Living Album Cover, Motion Graphics or a Music Video.

### If something goes wrong

| What you see | What to do |
|---|---|
| install.sh stops with things marked `needed` | Install those (step 2), then run it again. Running it again is always safe. |
| `permission denied` from Docker | Log out and back in after `usermod -aG docker`, or restart the machine. |
| GPU containers fail with "Driver/library version mismatch" | The NVIDIA packages updated underneath the running driver. Restart the machine. |
| The page doesn't load from another device | Check the address and port 7660. If you turned on a firewall (`ufw`), allow port 7660 from your home network. To use a name the app doesn't know, add it to `SV_HOSTS`. |
| The page asks for a key | Your device isn't on a network in `SV_OPEN_NETWORKS`. Pair it once with the key: see [Open it](#open-it). |
| Songs, pictures or videos fail straight away | `scripts/install.sh --check` lists the model files still missing. `docker logs sv-comfy` shows ComfyUI's side. |
| Anything else | The app's log: `journalctl --user -u sv-app -n 100`. |

## How it fits together

Everything runs on the one machine:

| Piece | What it is |
|---|---|
| **sv-app** | The app: a FastAPI server (`server/`) that also serves the built web app (`web/`, Vite + React). A systemd user service on `0.0.0.0:7660`. It queues the jobs and gives the GPU to one at a time. |
| **sv-comfy** | Sound / Vision's own ComfyUI in a container, built from `infra/legion/comfy/`. Songs, pictures and video run on it. |
| **sv-analysis** | One short-lived container per song analysis (stems, word timing, beats), from `infra/legion/analysis/`. |
| **sv-claude-studio** | One container per Claude session: Claude Code, Chromium on the GPU, ffmpeg and the film kit (`infra/studio/`). It signs in once with your Claude account and never sees an API key. |
| Optional | VRGameDevGirl's Video Builder (a ComfyUI container), the FL YuE2 trainer (a ComfyUI container) and MOSS-Music for the Influence Engine, Ollama, the Codex and Grok CLIs. |

`infra/legion/README.md` describes each piece in detail, including the owner's reference machine.

## Requirements

- Linux on x86_64 (developed on Ubuntu), with systemd.
- An NVIDIA GPU with 24 to 32 GB of memory (the reference machine has an RTX 5090 with 32 GB), of compute capability
  8.0, 8.6, 8.9, 9.0 or 12.0 (A100, RTX 30xx, RTX 40xx, H100, RTX 50xx), and a driver for CUDA 13.2 or newer
  (`nvidia-smi` shows "CUDA Version: 13.2" or higher).
- System memory: the reference machine has 128 GB. MiniMax H3's files alone come to about 40 GB, and ComfyUI stages
  models through system memory, so plan on 64 GB or more.
- Docker Engine with Compose v2 and the
  [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
  (`docker run --gpus all …` must work), usable by your account (the `docker` group).
- [uv](https://docs.astral.sh/uv/) and Python 3.12 (uv fetches Python 3.12 if it isn't installed).
- Node.js 20.19 or newer (22.12 or newer on Node 22) with npm, to build the web app.
- ffmpeg and ffprobe, and curl.
- Disk: about 50 GB for the images (sv-comfy and sv-analysis share about 45 GB; building sv-comfy needs 50 GB free and
  takes about an hour), up to about 110 GB for the models, and room for your songs and videos.
- For the videos made in code (Motion Graphics, Music Video, a living cover's finish): a Claude account with Claude
  Code, the director the studio runs today. Songs, covers and everything else work with a local model alone.
- Optional: `smbclient`, to read your music from a network share.

## What install.sh does

`scripts/install.sh` runs on the GPU machine, as the account the app should run as (not root). It checks the machine
first and says what's missing (`scripts/install.sh --check` only checks). Then it:

1. makes `sv.env` from `sv.env.example` if there isn't one, and, when run in a terminal, offers to open the app to
   your local network (see [Open it](#open-it));
2. makes the data folder (`data/`) and the models folder layout (`models/comfyui/…`);
3. installs the server's Python packages into `server/.venv` (`uv sync`) and builds the web app into `web/dist`;
4. builds the images on this machine, from this checkout: `sv-claude-studio`, `sv-comfy` (about an hour the first
   time) and `sv-analysis`, then starts sv-comfy (`docker compose`, restarting with Docker);
5. installs the `sv-app` systemd user service, starts it, turns on linger so it starts with the machine (or prints the
   `sudo loginctl enable-linger` command when that needs an administrator), and waits for it to answer;
6. lists the model files that are missing and prints the addresses to open.

| Option | |
|---|---|
| `--open-lan` | Let devices on this machine's local network in without the key (writes `SV_OPEN_NETWORKS`). |
| `--no-images` | Build no images (same as `--skip-studio --skip-comfy --skip-analysis`). |
| `--skip-studio`, `--skip-comfy`, `--skip-analysis` | Skip one image. With `--skip-comfy`, sv-comfy isn't set up or started either. |
| `--skip-web` | Don't rebuild the web app. |
| `--no-service` | Don't install or restart the `sv-app` service. |
| `--force` | Restart even while jobs are running (they're stopped). Without it, the script refuses. |
| `--check` | Only check the machine and the models; change nothing. |

### Sign-ins

- **Claude.** `infra/studio/studio.sh signin` in a terminal on the machine (or `ssh -t`). It prints a link: open it in
  any browser, approve, and paste the code back. `infra/studio/studio.sh status` shows whether it's signed in. The
  login stays in `data/studio/claude`, read only by Claude Code inside the studio container. If your `sv.env` moves
  the data or studio folder, sign in with its settings loaded:
  `(set -a; . ./sv.env; set +a; infra/studio/studio.sh signin)`.
- **ChatGPT** (writing, and covers and pictures with ChatGPT's image tool, under your ChatGPT plan). Install OpenAI's
  Codex CLI on the machine (`npm i -g @openai/codex`), then Settings → Sign in with ChatGPT: approve the code it shows
  in any browser. If `codex` isn't on the service's `PATH`, set `SV_CODEX_BIN` (and `SV_CODEX_PATH` for its Node).
- **Grok.** Install xAI's Grok CLI on the machine (`grok`, or `SV_GROK_BIN`), then sign in from Settings the same way.
- **A local model.** Run [Ollama](https://ollama.com) on the machine (`SV_OLLAMA`, default `http://127.0.0.1:11434`)
  and pull a model; it shows up in Settings.

## Open it

From any device on your network: `http://<machine>:7660` (the machine's name or address; install.sh prints both).
The app answers to its IP addresses, `localhost`, the machine's own name and `<name>.local`. To open it by any other
name (one your router gives it, say `studio.lan`), add that name to `SV_HOSTS`.

- Devices on the networks in `SV_OPEN_NETWORKS` (for example `192.168.1.0/24`) come straight in.
- Anyone else pairs each browser once with the app's key: on the machine, `cat data/secrets/api-token`, and paste it
  into the pairing screen. The browser keeps it as a cookie for a year.

The app listens on every address of the machine. Put only your own home network in `SV_OPEN_NETWORKS`, and don't
expose port 7660 to the internet.

## Configuration

All of an install's settings are in `sv.env` at the top of the checkout. `sv.env.example` lists every one with its
default; anything left out uses the default. The ones you're most likely to change:

| Setting | Default | |
|---|---|---|
| `SV_DATA` | `data/` | Songs, videos, the database, the key and the Claude login. |
| `SV_MODELS` | `models/` | The model files (ComfyUI's folders are in `comfyui/`). |
| `SV_PORT` | `7660` | The app's port. |
| `SV_OPEN_NETWORKS` | empty | Networks that need no key (comma-separated). Empty: every browser pairs. |
| `SV_HOSTS` | empty | Other names you open the app by (comma-separated). |
| `SV_MACHINE` | "the server" | What the interface calls this machine. |
| `SV_COMFY` | `http://127.0.0.1:8210` | sv-comfy. |
| `SV_OTHER_COMFYS` | empty | Other ComfyUIs on the machine to ask to unload their models before a big job. |
| `SV_MUSIC` | empty | Your music for the Influence Engine: a folder (`Artist/…/Song.flac`) or `smb://host/share/path`. |

After changing `sv.env`: `systemctl --user restart sv-app`. The app's log: `journalctl --user -u sv-app -f`.

The service runs with systemd's default `PATH`. If Docker, ffmpeg or a CLI lives elsewhere, add a `PATH=…` line to
`sv.env` or use the `SV_*_BIN` settings.

## Models

The app runs without any model; each feature needs its own. `scripts/models.sh` downloads them by set (see
[step 4](#4-download-the-models)), checks each against its published SHA-256 and puts it in place;
`scripts/install.sh --check` lists what's missing. Model files go in `models/comfyui/<folder>/` (or
`$SV_MODELS/comfyui/`). To fetch one by hand, a file's address on Hugging Face is
`https://huggingface.co/<repository>/resolve/main/<path in the repository>`. Each model has its own licence (see
[Licences](#licences)).

| For | File | Folder in `models/comfyui/` | Size | Hugging Face repository, path |
|---|---|---|---|---|
| Songs with YuE2 (the default song model) | `yue2_3b_bf16.safetensors` | `checkpoints/` | 7.8 GB | `Comfy-Org/YuE2`, `checkpoints/` |
| Covering a song with YuE2 | `sheetsage2_bf16.safetensors` | `audio_encoders/` | 1.4 GB | `Comfy-Org/YuE2`, `audio_encoders/` |
| Instrumentals with YuE2 (downloaded by `scripts/install.sh`) | `ar_lora_inst_v3abc_comfyui.safetensors` | `loras/soundandvision/yue2/` | 0.2 GB | `Mothersuperior/YuE2-instrumental-cot-full-loras`, root ([credit](CREDITS.md)) |
| Songs with ACE-Step 1.5 | `acestep_v1.5_xl_turbo_bf16.safetensors` | `diffusion_models/ace_step_1.5/` | 10 GB | `Comfy-Org/ace_step_1.5_ComfyUI_files`, `split_files/…` |
| | `qwen_0.6b_ace15.safetensors`, `qwen_1.7b_ace15.safetensors` | `text_encoders/ace_step_1.5/` | 1.2 + 3.7 GB | same |
| | `ace_1.5_vae.safetensors` | `vae/ace_step_1.5/` | 0.3 GB | same |
| Songs with MiniMax Music 3 | `minimax_music3_dit_fp16.safetensors` | `diffusion_models/minimax_music3/` | 4.9 GB | `Comfy-Org/MiniMax-Music-3`, `diffusion_models/` |
| | `minimax_music3_text_encoder_pruned_int8_convrot.safetensors` | `text_encoders/minimax_music3/` | 9.2 GB | same, `text_encoders/` |
| | `minimax_music3_dav.safetensors` | `vae/minimax_music3/` | 0.2 GB | same, `vae/` |
| Covers and pictures on your GPU (Krea 2) | `krea2_turbo_fp8_scaled.safetensors` | `diffusion_models/` | 13.1 GB | `Comfy-Org/Krea-2`, `diffusion_models/` |
| | `qwen3vl_4b_fp8_scaled.safetensors` | `text_encoders/` | 5.2 GB | same, `text_encoders/` |
| | `wan_2.1_vae.safetensors` | `vae/` | 0.25 GB | `Comfy-Org/Wan_2.1_ComfyUI_repackaged`, `split_files/vae/` |
| Sharper covers (optional; otherwise scaled plainly) | `4x-ClearRealityV1.pth` | `upscale_models/` | 9 MB | `Kim2091/ClearRealityV1` |
| Video with MiniMax H3 (Living Album Cover, Music Video) | `minimax_h3_fused_refdelta_r1024_turbo8_mystic07_int8_convrot.safetensors` | `diffusion_models/` | 21 GB | `MATLOWAI/minimax-h3-fused-turbo-int8-convrot`, `diffusion_models/` |
| | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | `text_encoders/` | 15.7 GB | `Comfy-Org/MiniMax-H3`, `text_encoders/` |
| | `minimax_h3_video_vae_int8_convrot.safetensors` | `vae/` | 2.8 GB | `Comfy-Org/MiniMax-H3`, `vae/` |
| Living Album Cover: keeping people still | `sam3.1_multiplex_fp16.safetensors` | `checkpoints/` | 1.75 GB | `Comfy-Org/sam3.1`, `checkpoints/` |

Two more, outside `models/comfyui/`:

- **Hearing the words of your own songs** (an upload that came without lyrics): Whisper large-v3,
  `Systran/faster-whisper-large-v3`, about 3 GB, kept as a Hugging Face cache folder (`scripts/models.sh whisper`).
- **Stems and word timing**: MelBand RoFormer, htdemucs_6s and wav2vec2 are fetched into
  `models/audio-separation/sv/` the first time a song is analysed (about 3 GB).

YuE2 needs the instrumental influence for instrumentals; `scripts/install.sh` downloads it (and so does
`scripts/models.sh songs`). The Video Builder brings its own model list (see below). MiniMax H3's audio VAE
(`minimax_h3_audio_vae_fp32.safetensors`, `Comfy-Org/MiniMax-H3`, `vae/`) is only used by the film kit's
`tools/h3plate.py`.

## Optional extras

- **VRGameDevGirl's Video Builder** (Performance and Hybrid music videos, with people singing). A separate ComfyUI
  container with her node pack ([comfyui-vrgamedevgirl](https://github.com/vrgamegirl19/comfyui-vrgamedevgirl)) and
  her H3 film skill, set up as her own instructions say, plus the models her skill lists. The app runs her scripts in
  it; the `SV_VRGDG_*` settings say where it is. What the container must provide:
  [infra/legion/README.md](infra/legion/README.md#vrgamedevgirls-video-builder). Surreal music videos, Living Album
  Covers and Motion Graphics don't need it.
- **The Influence Engine.** Needs [FL YuE2](https://github.com/filliptm/ComfyUI-FL-YuE2)'s trainer in its own ComfyUI
  container, MOSS-Music (a venv with its code and the MOSS-Music-8B-Instruct model) for the captions, and your music
  (`SV_MUSIC`, or upload the songs to a run). Settings `SV_TRAINER*`, `SV_LISTEN_PYTHON`, `SV_MOSS_*`; details in
  [infra/legion/README.md](infra/legion/README.md#the-influence-engines-pieces).
- **ChatGPT, Grok and Ollama**: see [Sign-ins](#sign-ins).
- **MCP servers**: Settings → MCP servers. Give the address (streamable HTTP) and, if it needs one, a key, or sign in
  to it in the browser. Keys are kept in `data/secrets/mcp.json` and never sent back to a browser.

## Updating

```sh
git pull
scripts/install.sh
```

It refuses while jobs are queued or running (a restart stops them) unless you pass `--force`. Each run reinstalls the
server's packages, rebuilds the web app, rebuilds the studio image from Docker's cache (so it picks up changes to the
film kit), refreshes sv-comfy's own nodes and restarts the app. sv-comfy's image is built only when its tag is
missing, so a release that changes it changes its tag. For a newer Claude Code in the studio:
`infra/studio/studio.sh build --no-cache`.

If GPU containers stop starting with "Driver/library version mismatch" after an automatic update of NVIDIA's packages,
reboot the machine. Keeping NVIDIA's packages (and the kernel, whose NVIDIA modules come with it on Ubuntu) out of
unattended upgrades avoids it.

## Developing

| Folder | |
|---|---|
| `server/` | The app's server (Python 3.12, FastAPI). `sv/config.py` reads every `SV_*` setting. |
| `web/` | The web app (Vite, React, TypeScript). |
| `infra/studio/` | The Claude studio image, `studio.sh` and the film kit. |
| `infra/legion/` | sv-comfy, sv-analysis, the Influence Engine's tools. |
| `infra/sv-app.service.in` | The systemd user service. |
| `scripts/` | `install.sh`, `models.sh`, and `deploy.sh` for working from another computer. |
| `docs/PLAN.md` | The plan the app was built to. |

- **Server tests:** `cd server && uv run pytest`.
- **Web app with hot reload**, on any computer with Node: `cd web && npm ci && SV_SERVER=http://<machine>:7660 npm run dev`,
  then open `http://127.0.0.1:5480`. It passes the API through to the app. From a network the app isn't open to, copy
  the key to `~/.config/sv/token` (mode 0600; or point `SV_TOKEN_FILE` at it) and the proxy sends it.
- **Deploying from another computer:** `scripts/deploy.sh [--web] [--force]` copies the server, workers and (with
  `--web`) the built web app to the GPU machine over ssh and restarts the app there. Say where in
  `scripts/deploy.env` (`HOST=`, `ROOT=`; see the top of the script). It installs the same `sv-app` service as
  install.sh, so use one or the other on a machine.

## Licences

Sound / Vision's own code is under the MIT licence (`LICENSE`). The models it runs and the third-party software in its
images have their own licences, which you must check and follow, especially before any commercial use:

- **YuE2's weights**: CC BY-NC (non-commercial), with a separate permission for individual creators.
- **The instrumental influence**, "YuE2-instrumental-cot-full-loras" by Mothersuperior, and the tokenizer the optional
  trainer uses, "yue2-mothersuperior-realaudio-tokenizer-v4", also by Mothersuperior: CC BY-NC 4.0 (non-commercial,
  with credit). See [CREDITS.md](CREDITS.md).
- **MiniMax H3's weights**, and models derived from them such as the fused turbo build: the MiniMax H3 Community
  License, which doesn't cover use in the US, the EU, the UK or Korea.
- **MiniMax Music 3, ACE-Step 1.5, Krea 2, SAM 3.1, Whisper, MOSS-Music, the separation models and the upscaler**: each
  under its own licence, on its model page.
- **VRGameDevGirl's node pack** (in sv-comfy) and her Video Builder skill: her own community/commercial licence.
- **ComfyUI** and **ComfyUI-KJNodes** are GPL-3.0; so is the patch to KJNodes in
  `infra/legion/comfy/patches/ComfyUI-KJNodes-minimax.patch`. The other node packs pinned in
  `infra/legion/comfy/node_packs.txt` have their own licences.
- **nvidia-vfx** (in sv-comfy's lock file) is NVIDIA's proprietary Video Effects binding, under NVIDIA's terms; the
  images are built on NVIDIA's CUDA base image, under NVIDIA's licence.
- **The ComfyUI workflow templates** in `infra/legion/comfy/templates/` come from Comfy-Org and keep their licence.
- **Claude Code**, OpenAI's Codex CLI and xAI's Grok CLI are used under their providers' terms; the studio installs
  Claude Code unmodified from Anthropic's repository. The film kit's fonts are open-licensed faces fetched while the
  studio image builds.

Build the images on your own machine, as `scripts/install.sh` does. Don't publish the built images: they contain
third-party and proprietary components that aren't yours to redistribute.
