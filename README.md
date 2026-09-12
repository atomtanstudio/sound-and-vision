# Sound/Vision

A free, self-hosted music workspace with local YuE2 generation, writing assistance, cover art, kinetic lyric videos and visualizer videos. Choose an OpenAI account or local writing and ComfyUI image models. **Music video is Coming soon** while scene generation and character consistency are refined; existing music-video projects are preserved.

Start with the [self-hosted installation guide](SELF_HOSTED.md), then [AI setup](docs/backend/LOCAL_PROVIDERS.md) for **Qwen3.5 + Ollama**, **Krea 2 Turbo**, SDXL or a custom ComfyUI workflow. Local mode needs no OpenAI account. The music backend currently targets Linux and a compatible NVIDIA GPU; this is a single-owner installation, not a public multi-user service.

## Installation

**One Linux computer is enough:** the app, music backend, and optional local AI providers can all run together. The current music baseline is a compatible NVIDIA GPU with approximately 24 GiB free VRAM.

Follow the [step-by-step setup guide](SELF_HOSTED.md). It covers prerequisites, backend installation, the private local connection, optional AI providers, and your first song. Start there before running `npm run dev`; installing the frontend alone does not install the music backend. A second computer and SSH are optional.

## Working music flow

- Describe the song and supply lyrics in Simple or Advanced.
- Generate one or two independent takes with a persistent queue and recorded seeds.
- Follow actual stages, leave/reload the browser, and return to the same durable jobs.
- Use the documented YuE2 style, lyrics, composition, external ABC, guidance and sampling controls.
- Optionally review a saved score before recording; preserve exact plans or edit a new version.
- Play and seek generated songs using their actual duration; download original WAV, FLAC or MP3.
- Cancel a job, retry only a failed/cancelled take, and retain earlier attempts and artifacts.
- Rename, favorite, move to a project, and select a generated song as the Video soundtrack.

The isolated backend service uses Python 3.12, pinned YuE2/PyTorch/model revisions, SQLite metadata and filesystem media. It observes existing GPU queues, serializes its own jobs and releases its model memory afterward. It does not modify or unload existing ComfyUI/H3 services.

## Documentation

- [Backend architecture and model mapping](docs/backend/README.md)
- [Installation, connection, restart and backup](docs/backend/OPERATIONS.md)
- [Verification and feature/evidence matrix](docs/backend/VERIFICATION.md)
- [Video editor, timing rules and current preview limits](docs/backend/VIDEO_EDITOR.md)
- [VRGDG Audio Drive + H3 Turbo music-video test](docs/backend/AUDIO_DRIVE.md)
- [Pinned official YuE2 README](docs/upstream/yue2/README.md)
- [Official generation](docs/upstream/yue2/docs/generation.md), [editing](docs/upstream/yue2/docs/editing.md) and [cover/transcription](docs/upstream/yue2/docs/covers.md) guides
- [Pinned source and model revisions](deploy/source.lock.json)
- [API schema](docs/backend/submission.schema.json)
- [Current project status](STATUS.md)

The complete upstream documentation, examples, skill references, model cards and license notices are retained under `docs/upstream/yue2/`. Model weights, credentials and generated production media stay outside the repository.

## Still separate

OpenAI account sign-in, local providers, reviewed song ideas/lyrics/style/score edits, per-take cover art, and reference-audio transcription are connected. See [Assistance and reference songs](docs/backend/ASSISTANCE.md) for usage and installation. Music creation uses reviewed lyrics; reference audio supplies a melody or full score, not sung-word transcription. Public D1 hosting remains separate. Music-video generation is disabled in the release. The two original instrumental fixtures remain samples, not YuE2 output.

The browser's local draft editor still works without a configured backend. Generated takes and their metadata live on your backend computer. A public multi-user deployment needs a separate user-access/authentication layer; the current service is a private single-owner installation.

## Checks

```sh
npm run build
npm test
```

`npm test` deliberately simulates an offline provider while exercising the existing UI; it submits no GPU jobs. `scripts/verify-live-music.mjs` is an explicit live inference check and creates two real takes. Backend tests run with the isolated Python environment:

```sh
python -m pytest backend/test_api.py -q
```

Browser scripts require installed Playwright Chromium or `PLAYWRIGHT_EXECUTABLE_PATH`. Concrete live evidence is retained under `docs/backend/evidence/`.

First-party application code: Apache-2.0. YuE2 code/docs: Apache-2.0. YuE2 model weights: CC BY-NC 4.0. See [third-party notices](THIRD_PARTY_NOTICES.md); application source licensing does not replace model/provider terms.
