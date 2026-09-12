# Self-hosted AI setup

Sound/Vision supports two installation choices: an OpenAI account, or local text and image servers. Choose **Your account → AI setup**. Saving changes which providers handle future requests; it never silently falls back to OpenAI. Existing recordings, cover images and OpenAI sign-in credentials are preserved.

Music video is **Coming soon** in this release. Its navigation choice is disabled, and saved-project links show a holding page. Backend film generation and recovery requests are blocked. Existing projects and exports remain on disk. Kinetic lyric videos and visualizer videos remain available. Internal development can explicitly enable both `VITE_ENABLE_MUSIC_VIDEO=true` when building the frontend and `SOUND_VISION_ENABLE_MUSIC_VIDEO=1` for the backend; neither is enabled in the release.

## Choose local writing

Install [Ollama](https://ollama.com/download) on the backend computer or a private-network text server:

```sh
ollama pull qwen3.5:4b
```

In AI setup select **Local models**, **Ollama**, its URL (normally `http://127.0.0.1:11434`), and `qwen3.5:4b`. The [official 4B distribution](https://ollama.com/library/qwen3.5:4b) is approximately 3.4 GB. Its upstream [Qwen model card](https://huggingface.co/Qwen/Qwen3.5-4B) lists Apache-2.0. The 9B variant is an optional larger model; installed models appear when you refresh the list. This is a practical starting preset, not a claim of parity with every OpenAI model.

Ollama uses CPU by default to leave the music GPU available. Responses use structured JSON, with thinking disabled and automatic model unloading (`keep_alive: 0`). Large string-length constraints are omitted from the server's decoding grammar for llama.cpp compatibility; the application still validates the complete proposal schema, including those limits. **Share the music GPU for writing** changes Ollama to GPU use and serializes its requests with music and local image work. All existing writing tasks, including score edits, use the selected text provider. Protected score edits must still pass the melody/timing comparison before applying. Very long requests and truncated/invalid responses fail without changing the user's draft.

For LM Studio, llama.cpp or another local OpenAI-compatible server, choose that server type and use its base URL, such as `http://127.0.0.1:1234/v1`. It must support `/models`, `/chat/completions`, and JSON-schema structured responses. Set CPU use or automatic unloading in that server; the compatibility API does not provide a universal unload command. An optional API key is stored only in private backend configuration and is never returned to browser JavaScript.

**Test writing** uses the real proposal path with a small original sample. It changes no song. A model appearing in the list proves availability, not writing quality; review its generated sample.

Release testing with Qwen3.5 4B passed song-description and complete lyric-draft requests. The more demanding ABC chord-edit sample failed score validation and was refused, preserving the original. Use a larger capable model for precise score work; 9B is selectable but was not benchmarked in this release check. Local prompts request only the current task's editable fields, and the app preserves every unrelated draft field itself.

## Choose ComfyUI images

Use a current [ComfyUI installation](https://docs.comfy.org/installation). Enter its URL, such as `http://127.0.0.1:8188`. These addresses are reached **from the Sound/Vision backend**, not from the browser. For containers use a private reachable address; `localhost` always refers to the process's own network namespace.

**Krea 2 Turbo** is the default. The built-in graph follows Comfy's [official Krea 2 template](https://docs.comfy.org/tutorials/image/krea/krea-2): 8 steps, Euler/simple, CFG 1, a Qwen3VL text encoder and the Qwen image VAE. The selected local writing model turns the cover's song context into a visual prompt before ComfyUI renders it. No account-backed Krea API is used.

Install the [ComfyUI model files](https://huggingface.co/Comfy-Org/Krea-2):

| Folder under ComfyUI's models root | Default file |
| --- | --- |
| `diffusion_models` | `krea2_turbo_fp8_scaled.safetensors` |
| `text_encoders` | `qwen3vl_4b_fp8_scaled.safetensors` |
| `vae` | `qwen_image_vae.safetensors` |

Click **Test connections & refresh models** to discover the real filenames indexed by that ComfyUI server. Pick another compatible Krea 2 model from the list, or choose **SDXL checkpoint** for a standard checkpoint-based workflow. No large model downloads happen just from selecting a provider.

For another architecture, export a working text-to-image graph from ComfyUI in **API format**, import it, select its positive prompt field and **SaveImage** output. The application keeps the graph's model, resolution and sampler settings, except for a fresh sampler seed and its output filename prefix. This supports user-supplied workflows; it does not imply every model or custom node has been tested. The configured graph and required models/nodes are checked before submission. A model filename alone cannot change one model architecture into another.

**Generate test image** renders a real sample, displays it in setup and preserves the test outside the song library. Test requests remain pollable after reload. Local presets generate new images; reference-image editing is not offered in this release.

## Models on another disk

ComfyUI owns model discovery. Sound/Vision reads its index rather than searching the user's filesystem or assuming the browser and model host share a disk.

Under **Models stored in another folder**, enter the models root as seen by ComfyUI, save, then download `soundvision-model-paths.yaml`. Load it with:

```sh
python main.py --extra-model-paths-config /path/to/soundvision-model-paths.yaml
```

The file maps `diffusion_models`, `checkpoints`, `text_encoders`, `vae`, and `loras` below that root. Restart ComfyUI when idle, then refresh the model list. In Docker, first mount the model disk and enter its **container** path. Existing ComfyUI model folders also continue to work without this configuration.

## GPU sharing and cancellation

Local image requests share the music service's GPU mutex and check the configured external queues before submission. They keep a prompt-ID receipt, poll that specific ComfyUI job, and release the selected server's idle model cache after completion. This avoids keeping the just-used image model resident and blocking YuE2. Cache release is skipped while ComfyUI has other work; unrelated services are never interrupted.

Canceling a queued test removes only its own ComfyUI prompt. A running local image is allowed to finish before releasing the shared GPU; it does not send a global interrupt. A connection loss during submission is not automatically retried. Inspect the retained receipt in `data/provider-jobs/` before starting another attempt if the outcome is uncertain.

This is coordination within Sound/Vision, not a global GPU scheduler for every application. Other model servers must manage their own memory, and external applications can still submit work independently.

## Installation and configuration

The existing [Linux GPU backend installation](OPERATIONS.md) remains required for YuE2 music. Local providers do not replace its GPU/model requirements. After installation, configure through AI setup, or use:

```sh
<root>/.venv/bin/python <root>/deploy/configure_providers.py \
  --root <root> --provider local \
  --text-url http://127.0.0.1:11434 --text-model qwen3.5:4b \
  --comfy-url http://127.0.0.1:8188 \
  --image-model krea2_turbo_fp8_scaled.safetensors
```

Use `--model-root` for another ComfyUI models root, or `--image-preset sdxl --image-model filename.safetensors`. The UI also supports API-workflow import. The private `providers.json` has mode 0600. Back it up separately from any public release; API keys are excluded from public status responses. Restart Sound/Vision while idle after CLI configuration. UI saves apply without a restart and are blocked during active assistance work.

OpenAI users install the existing account runtime. Local-only users can omit it; if reference-audio transcription is wanted, `deploy/install_assistance.py --skip-openai --root <root> --models <models>` installs just the reference runtime. No OpenAI account is needed for local writing, cover art, lyric-video images or music generation.

## Licenses and release scope

The application is Apache-2.0; model licenses are separate. YuE2 weights use [CC BY-NC 4.0](https://huggingface.co/m-a-p/YuE2-3B/blob/main/LICENSE). Krea 2 weights use the [Krea 2 Community License](https://www.krea.ai/krea-2-licensing), not the Apache license of its inference code. Check the chosen checkpoint's terms, including commercial-use conditions. Model downloads and license acceptance remain the installer's choice.

This release is a self-hosted, single-owner application. Do not expose its private backend/proxy publicly without a separate authentication design. Local mode accepts only loopback/private-network providers and does not follow redirects to public services.
