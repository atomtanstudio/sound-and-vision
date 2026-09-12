# Sound/Vision self-hosted release candidate

This package contains the application source, lock files, sample assets and setup guides. It contains no user library, login credentials or model weights. Music video is marked **Coming soon** and disabled; music, kinetic lyric videos and visualizer videos remain available.

## 1. Install the music backend

Use a Linux host with Python 3.12, FFmpeg and a compatible NVIDIA GPU. The documented unquantized music baseline is 24 GiB of VRAM. Follow [backend installation](docs/backend/OPERATIONS.md#reproduce-on-a-linux-gpu-host) to install the pinned YuE2 runtime, download the models and create the private service. Keep this extracted folder's relative paths intact.

The backend creates `<root>/service.token` and listens on `127.0.0.1:5191`. Keep the token private. The installer does not download OpenAI or local writing/image models automatically.

## 2. Connect the browser application

Install Node.js 22.18 or newer. In this extracted directory:

```sh
npm ci
cp .env.example .env.local
```

Edit `.env.local`: set `SOUND_VISION_BACKEND_URL` to `http://127.0.0.1:5191` and `SOUND_VISION_TOKEN_FILE` to the absolute path of the backend's `service.token`. When the browser app runs on a different computer, securely copy the token there and set `SOUND_VISION_SSH_HOST` to your existing SSH host alias; the launcher creates a loopback tunnel. The service token is added by the local proxy, never embedded in browser assets.

```sh
npm run dev
```

Open `http://127.0.0.1:5190/music`. Keep the launcher running. This release uses the existing loopback app launcher; it is not a public web-hosting package. `npm run build` also verifies and builds frontend assets, but a static file host alone does not supply the required API proxy and video-render routes.

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

For reference-audio transcription, install the optional reference runtime with `deploy/install_assistance.py --skip-openai`; local writing itself does not require it. Video export also needs FFmpeg and Playwright Chromium (`npx playwright install chromium`) on the rendering computer. The separate Linux GPU visualizer renderer is optional; its installation is documented separately in `docs/backend/LEGION_VISUALIZER_RENDERER.md`.

## Release verification and boundaries

Initial Linux GPU checks passed for Qwen3.5 4B song descriptions and a complete lyric draft, plus native ComfyUI Krea 2 image generation and cache release. The 4B model's advanced ABC score-edit sample failed validation and was refused with the original preserved. The subsequent security-reviewed revision passed 155 backend tests locally with patched FastAPI/Starlette dependencies. Browser checks cover the provider setup and video labels. A clean GPU-host installation of this revised dependency stack has not been verified. Other checkpoints and custom workflows require their own sample test. See [security and privacy](SECURITY.md).

This is a single-owner, self-hosted release. Model licenses remain separate from the Apache-2.0 application license: see [third-party notices](THIRD_PARTY_NOTICES.md), including YuE2's noncommercial weight license and Krea 2's Community License.
