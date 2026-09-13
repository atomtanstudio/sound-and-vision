# Sound and Vision self-hosted release candidate

This package contains the application source, lock files, sample assets and setup guides. It contains no user library, login credentials or model weights. Music video creates thematic full-song films. Experimental lip-sync performance remains **Coming soon**; music, kinetic lyric videos and visualizer videos remain available.

## Before you start

**You need only one computer.** These instructions run the browser app, music backend and optional local AI providers on the same Linux computer. A second computer and SSH are optional.

Have these installed before continuing:

- Linux x86-64 with a working NVIDIA driver and compatible GPU. The current music configuration requires approximately 24 GiB of free VRAM; 16 GiB cards are not a supported baseline. Close other GPU workloads before creating a song.
- Python 3.12 with its `venv` module, Git, FFmpeg (including `ffprobe`) and Node.js 22.18 or newer (including npm).
- Internet access for package/model downloads and enough disk space for the models and your generated audio. Model weights are downloaded separately from this source package.
- A normal user account with a working systemd user session. Run the application and installers as that user, not as root.

Check the prerequisites in a terminal:

```sh
nvidia-smi
python3.12 --version
ffmpeg -version
ffprobe -version
node --version
npm --version
git --version
systemctl --user status
```

Check that FFmpeg includes the encoders used for downloads and video export:

```sh
ffmpeg -hide_banner -encoders | grep -E 'libmp3lame|libx264|aac|flac'
```

Expect all four names. Use a full FFmpeg build if any are missing. You also need a current browser to open the app. RAM and disk requirements depend on selected optional models; this release has not established a tested minimum for either. Check available resources with `free -h` and `df -h .` before large downloads.

### Additional prerequisites by feature

| Feature | Additional requirement | Check before use |
| --- | --- | --- |
| Manually entered lyrics and music generation | YuE2 runtime and weights, installed in step 1 | CUDA check and backend health below |
| Local writing | Running Ollama plus a downloaded writing model, or a compatible text server | `ollama list`, then **Test writing** |
| Docker-based Ollama option | Docker Engine and Compose plugin, available to your user | `docker info` and `docker compose version` |
| Local images | Running ComfyUI, chosen model files, and any nodes required by your workflow | **Test connections & refresh models**, then **Generate test image** |
| OpenAI assistance | Account with access to the requested capabilities, optional account runtime, and `uv` at `~/.local/bin/uv` | Runtime installation below, then in-app sign-in |
| Reference-audio transcription | `uv` at `~/.local/bin/uv`, separate Python/model runtime downloaded by the optional installer | `~/.local/bin/uv --version` before installation |
| Video export | Playwright Chromium and its Linux system libraries, FFmpeg/ffprobe with the encoders above | Chromium install command below |
| Interface on another computer | SSH client and working login to the backend computer | Test `ssh user@backend-host` before configuring the app |

Optional runtime installation uses [Astral's uv installer](https://docs.astral.sh/uv/getting-started/installation/). If uv is missing, download and inspect the official installer, then run it as your normal user:

```sh
curl -LsSf https://astral.sh/uv/install.sh -o /tmp/soundvision-uv-install.sh
less /tmp/soundvision-uv-install.sh
sh /tmp/soundvision-uv-install.sh
"$HOME/.local/bin/uv" --version
```

This download command requires `curl` and working HTTPS certificates. If you installed uv elsewhere, ensure the installer-required path `~/.local/bin/uv` exists before continuing. You do not need uv for the basic music installation.

Install any missing prerequisite using your Linux distribution's instructions before proceeding. The installer does not install NVIDIA drivers or system packages. Read the model-license note at the end before downloading weights.

## 1. Install the music backend on this computer

Extract this package into a permanent, user-owned folder such as `~/sound-vision`. Open a terminal **inside that folder**. Keep the folder's relative paths intact; do not move it after installing the service without updating its paths. Use a path without spaces for this installation.

Run the following in the same terminal. The variables capture your actual folder, so no `/srv/ai` or Legion-specific path is required:

```sh
export SV_ROOT="$PWD"
export SOUND_VISION_MODELS="$SV_ROOT/models"
python3.12 -m venv "$SV_ROOT/.venv"
"$SV_ROOT/.venv/bin/python" -m pip install --upgrade pip

git clone https://github.com/multimodal-art-projection/YuE.git "$SV_ROOT/YuE"
git -C "$SV_ROOT/YuE" checkout 92a73cc7652fcc1f937855e4b765e0a0edd7ff2e
"$SV_ROOT/.venv/bin/python" -m pip install "$SV_ROOT/YuE" -r "$SV_ROOT/backend/requirements.txt"
"$SV_ROOT/.venv/bin/python" -c 'import torch; print("CUDA available:", torch.cuda.is_available()); assert torch.cuda.is_available(), "Fix the NVIDIA driver/PyTorch installation before continuing"'
"$SV_ROOT/.venv/bin/python" "$SV_ROOT/deploy/download_models.py"
"$SV_ROOT/.venv/bin/python" -m pytest backend/test_api.py -q
"$SV_ROOT/.venv/bin/python" "$SV_ROOT/deploy/install_service.py" \
  --root "$SV_ROOT" --models "$SOUND_VISION_MODELS"
```

To use another disk, change `SOUND_VISION_MODELS` to an absolute, writable folder before running the download and install commands. Downloads can take time. Wait for each command to finish successfully; stop and resolve errors before continuing. These are first-install commands: do not rerun the service installer over a configured installation, since it rewrites `service.env`.

Confirm that the backend started:

```sh
systemctl --user is-active sound-vision.service
"$SV_ROOT/.venv/bin/python" "$SV_ROOT/deploy/api_request.py" /api/health --root "$SV_ROOT"
```

Expect `active` and JSON containing `"connected":true`. The service listens on `127.0.0.1:5191`. Its token is in `service.token`; keep it private. For startup before login, your administrator may need to enable user lingering. See [backend operations](docs/backend/OPERATIONS.md) for service and backup details.

## 2. Start the browser app on the same computer

Still inside the extracted folder:

```sh
npm ci
cp .env.example .env.local
```

Edit `.env.local` to contain the following, replacing `/absolute/path/to/sound-vision` with the folder printed by `pwd`. Do not paste the token itself:

```dotenv
SOUND_VISION_BACKEND_URL=http://127.0.0.1:5191
SOUND_VISION_TOKEN_FILE=/absolute/path/to/sound-vision/service.token
SOUND_VISION_SSH_HOST=
```

Leave `SOUND_VISION_SSH_HOST` empty for a single-machine installation. Then start the app:

```sh
npm run dev
```

Open **http://127.0.0.1:5190/music** in a browser on this computer. Keep this terminal running. The backend runs as a service; the browser app launcher runs until you stop it with Ctrl+C. To reopen the app later, enter its folder and run `npm run dev` again.

The service token is added by the local proxy, never embedded in browser assets. `npm run build` checks and builds frontend assets, but a static file host alone cannot supply the API proxy and video-render routes. This package is for a private local installation, not public web hosting.

### Optional: put the browser app on a second computer

Only use this if you want a separate computer for the interface. Securely copy the backend token to that computer, point `SOUND_VISION_TOKEN_FILE` at that copy, and set `SOUND_VISION_SSH_HOST` to your existing SSH host alias or `user@backend-host`. Keep the backend URL at `http://127.0.0.1:5191`; the launcher creates the tunnel. Install the frontend dependencies on that computer with `npm ci`. Local AI provider URLs are still interpreted from the **backend computer**.

## 3. Choose your AI providers

Open **Your account → AI setup**.

- **OpenAI account:** install the [account runtime](docs/backend/ASSISTANCE.md), then connect in the app.
- **Local models:** install Ollama, pull `qwen3.5:4b`, and select it for writing. Connect a current ComfyUI with **Krea 2 Turbo**, choose an **SDXL checkpoint**, or import another working **ComfyUI API workflow**. [Local provider setup](docs/backend/LOCAL_PROVIDERS.md) lists the model files and alternative model-folder configuration.

Optional Docker installation for CPU-only writing, on the backend host:

```sh
docker compose -f deploy/ollama.compose.yaml up -d
docker compose -f deploy/ollama.compose.yaml exec ollama ollama pull qwen3.5:4b
```

The example uses the tested Ollama 0.34.0 image by digest, binds only to loopback, and keeps model downloads in a named volume. Skip it if you already run Ollama on port 11434. It requires Docker Compose; adjust its CPU/RAM limits for your machine. Native Ollama works too.

In AI setup, use **Test connections & refresh models**, **Test writing**, and **Generate test image**, then **Save AI setup**. Test results do not change a song. CPU writing is the default; local images release their idle ComfyUI cache after completion so music can use the GPU.

Local writing does not require the reference-audio runtime. If you want reference-audio transcription, first install `uv` at `~/.local/bin/uv` as required by the optional installer, then run from the application folder (use your chosen model folder):

```sh
.venv/bin/python deploy/install_assistance.py --skip-openai \
  --root "$PWD" --models "$PWD/models"
```

The OpenAI runtime installer also installs reference transcription and needs that same `uv` prerequisite; see [account setup](docs/backend/ASSISTANCE.md#installation).

For video export, install Chromium on this same computer:

```sh
npx playwright install --with-deps chromium
```

FFmpeg must also be on its PATH. The [Playwright dependency installer](https://playwright.dev/docs/browsers#install-system-dependencies) may request administrator privileges for Linux system packages. A separate GPU renderer is optional; it is not needed for the single-machine setup.

## 4. Verify your first song

1. Confirm the app reports the music backend is connected.
2. Enter a song description and lyrics yourself, or use your tested writing provider.
3. Choose one take and create a song. This runs real GPU generation; it can take time.
4. Confirm it finishes, plays, and downloads. Reload the page to confirm the saved song remains available.

Writing and image providers are optional for this first test when you supply the text yourself. They do not replace the YuE2 music model.

## Use an existing recording

In **Video**, choose **Import song**. WAV, FLAC, MP3, M4A, and OGG are supported, up to 100 MB and 10 minutes. FFmpeg on the backend validates and converts the recording; no music-generation model or reference-transcription runtime is used for import. The original upload is preserved privately, and playback copies are saved in the backend library under **Imported songs**.

For a lyric video, add the song’s lyrics in the editor and align them (alignment still requires its separate runtime). Import itself does not transcribe lyrics; the Lyrics section shows the next step. In the visible **Lyrics** section below **Soundtrack**, choose **Transcribe lyrics from song** to isolate the vocal and run local Whisper speech-to-text. Review and edit the draft, then choose **Use reviewed lyrics** and **Align lyrics**. This separate transcription step requires the same local runtime as lyric alignment; it does not use OpenAI. For a visualizer without words, leave lyrics empty. Imports remain available after reload and support normal library rename, move, and Trash controls.

## Scene-based music videos

Choose **Music video** in Video to use the guided theme → plan → render flow. This requires a configured writing provider (OpenAI account or local LLM), the existing [H3LIX integration](docs/backend/VIDEO_EDITOR.md) H3 service reachable from the backend, and FFmpeg/ffprobe. Set `SOUND_VISION_H3_URL` in the backend environment to its private API address (default `http://127.0.0.1:7310`). The service must support Text to Video and Frames to Video with Turbo enabled. It can run on the same GPU computer; the app serializes clips with music generation.

For **On-screen lyrics**, install the local lyric-alignment runtime described in [the video editor guide](docs/backend/VIDEO_EDITOR.md). The backend's FFmpeg must include the `ass` filter (libass): check `ffmpeg -filters`. On macOS, use a full FFmpeg build with libass if the default build omits it. These exports run on the backend and do not require Chromium. The app checks FFmpeg and its lyric-rendering capability before starting clip generation.

Review transcription errors before using lyrics. Missing or conflicting word timing is shown before video generation; use Advanced controls → Word timing to correct it. Alternatively, explicitly select **Omit words with unusable timing** to leave those words off the video while preserving the lyric sheet. Re-aligning may return the same gaps. Full-song footage, repeats, blends and continued scene pairs are explained in [Music-video workflow](docs/backend/MUSIC_VIDEO.md).

## If something does not work

| Symptom | What to check |
| --- | --- |
| Backend disconnected | Run the health command from step 1; check `systemctl --user status sound-vision.service`. |
| Unauthorized / HTTP 401 | Check the absolute token-file path in `.env.local`. Restart `npm run dev` after editing it. Do not put the token in a browser URL. |
| Backend service fails | Run `journalctl --user -u sound-vision.service -n 50 --no-pager`. Review/redact logs before sharing them. |
| Song waits for GPU memory | Check `nvidia-smi` and let other GPU jobs finish. The current music configuration expects about 24 GiB free. |
| Local writing or images cannot connect | Ensure Ollama/ComfyUI is running; test the address from the backend computer, then refresh models in AI setup. |
| Port 5190 already in use | Stop the previous app launcher, then start it once. |
| Video export cannot launch Chromium | Run `npx playwright install --with-deps chromium` on the computer running the app, and resolve any missing Linux libraries it reports. |

Before upgrading, back up the application’s `data/`, `service.env`, `service.token`, and any account/provider state privately. Restart the backend only while no generation or assistance job is active. Do not publish these backups.

## Release verification and boundaries

Initial Linux GPU checks passed for Qwen3.5 4B song descriptions and a complete lyric draft, plus native ComfyUI Krea 2 image generation and cache release. The 4B model's advanced ABC score-edit sample failed validation and was refused with the original preserved. The security-reviewed revision passed 155 backend tests both locally and on the updated Linux service with patched FastAPI/Starlette dependencies. Browser checks cover the provider setup and video labels. A clean GPU-host installation of this revised dependency stack has not been verified. Other checkpoints and custom workflows require their own sample test. See [security and privacy](SECURITY.md).

This is a single-owner, self-hosted release. Model licenses remain separate from the Apache-2.0 application license: see [third-party notices](THIRD_PARTY_NOTICES.md), including YuE2's noncommercial weight license and Krea 2's Community License.
