# Writing, images and reference songs

**September 12 update:** Installations can choose OpenAI or local text and ComfyUI image providers. See [Local providers and self-hosted setup](LOCAL_PROVIDERS.md). The account-specific instructions below apply only when OpenAI is selected. Local mode does not start the OpenAI runtime.

Implemented on Legion, 10 September 2026. The existing visual layout is retained.

## Using the interface

- **Your account → Connect OpenAI** starts OpenAI's device-code flow. Complete sign-in on OpenAI's page. Sound and Vision polls account state; the authenticated account's available models populate Advanced's writing model selector.
- **Describe your song wand** submits `Describe song` to the connected account immediately and fills that field. Empty input gets one fresh direction; partial notes are expanded while retaining genre, vocalist and other constraints. Named artist influences are translated into musical and vocal attributes rather than artist-name tokens or promises of an exact voice. The description is the `style` field in the existing structured proposal contract; the UI writes it into `description` and clears a stale advanced style so generation uses the visible text. Title, lyrics, score and settings remain intact. Undo restores only description/style; if either was edited while waiting, the result is shown as a suggestion instead of overwriting it. Requests survive reload and uncertain POST retries reuse the request ID. This action writes text only; it does not start music or cover generation.
- **Writing assistant** remains available in Simple and Advanced for three song ideas, lyrics, section rewrites, style refinement, translation and score edits. The lyrics and advanced-style wands open those tasks. Generate a proposal, review it, and apply it. Applying is separate from music generation. Undo restores the previous in-memory form. Applying a proposal against a changed draft is rejected so newer edits are retained.
- **Reference song** accepts WAV, FLAC, MP3, M4A, or OGG, 1 second–5 minutes, at most 50 MiB. Choose a reference song, then choose melody only for a new arrangement or melody and chords to retain harmony. Selecting a file does not upload or transcribe it. Press **Generate score**, review the result, then choose **Use this score**. Choosing another song immediately clears the previous score and reference identifiers while retaining lyrics, style, title and project. **Clear score** removes either a preview or an applied score and keeps the selected local file available for regeneration; the remove button also clears the selected file. Replaced/cancelled jobs cannot repopulate the panel from late responses. A file selected but not submitted must be chosen again after a page reload. Supply the target style and lyrics, then Create. The original upload and transcription remain on Legion.
- **Track details → Edit with assistant** loads the existing generated score and song inputs into Advanced. A subsequent generation creates a new take; the original recording remains intact and the new form records `sourceTakeId`.
- New music submissions schedule one cover per take when the account supports images. Existing takes have **Create cover art** / **Create another cover** in Track details. Cover failure does not discard audio. Earlier cover files are retained when a new one succeeds.
- Advanced includes a genre field. The library can filter by genre and sort Genre A–Z. Genres are user-supplied labels, not an automatic audio classifier.

SheetSage2 extracts melody, harmony and musical timing. It does **not** transcribe sung words, clone the original singer, or return a natural-language style description. Add lyrics yourself or use the writing assistant. This is the documented YuE2 cover workflow: audio → symbolic score → reviewed lyrics/style/score → a new recording. It is not waveform-preserving audio editing.

## OpenAI connection

The integration uses the official [Codex app-server protocol](https://learn.chatgpt.com/docs/app-server), through local JSONL stdio. It uses `account/login/start` with `chatgptDeviceCode`, `account/read`, `account/login/cancel`, `account/logout`, `model/list`, `modelProvider/capabilities/read`, `skills/list`, `thread/start`, `turn/start`, and lifecycle notifications. No OAuth tokens are sent to the browser or copied from another application. There is no API-key or separately billed API fallback.

Runtime: official complete Codex **0.154.0** Linux package, pinned URL and SHA-256 in `deploy/openai-runtime.lock.json`. The tested installation also includes private Node 24.21.0 (`deploy/node-runtime.lock.json`), without changing system Node. Install the **package**, not the standalone CLI asset: native image generation also needs the sibling `codex-code-mode-host` executable and package resources. The initial standalone install advertised image capability but could not start its host; the complete package fixed the live test. No sandbox protections were disabled.

Private account store: `/srv/ai/sound-vision/openai-account` (directory 0700, auth file 0600). Assistant working directory: `/srv/ai/sound-vision/assistant-work`. Account state survives service restart. Sign-out removes this installation's account authorization without affecting Codex Desktop or H3LIX. Diagnostic stderr stays in `/srv/ai/sound-vision/openai-runtime.log` (0600); do not publish it without reviewing/redacting it.

Each writing request gets an ephemeral thread with shell, web search, app/plugin and multi-agent features disabled, read-only sandbox, no network access for sandboxed operations, rejected interactive tool requests, structured output, and a 180-second turn timeout. Only the supplied song inputs enter the prompt. Non-target fields are restored server-side even if the model changes them. Score edits with **Keep melody and timing** must pass the upstream native-ABC structural comparison before becoming an applicable proposal. That comparison checks sounding notes, durations, bar/meter grids and tempo, not generated-audio similarity or arbitrary ABC dialects.

Images use Codex's account-backed native `image_gen` path with its built-in `imagegen` skill. The app discovers capability rather than assuming an image model identifier. The earlier UI label “GPT Image 2.5” was not a verified callable model and is removed. The returned PNG is decoded, checked, and converted with Pillow before serving. The metadata records the supervising model separately from `codex-image-generation`; it does not mislabel that text model as the image model.

Writing and image queues are separate, each with concurrency one. The image timeout is ten minutes. Cancellation interrupts only the owned turn. Account limits and provider errors surface on the request; there is no automatic quota reset or purchase.

## Reference runtime

The official [SheetSage2 model card](https://huggingface.co/m-a-p/SheetSage2) and pinned snapshots are in `docs/upstream/sheetsage2`. YuE2's existing `docs/covers.md` and `docs/editing.md` remain the generation contracts.

| Component | Pin / deployment |
|---|---|
| Python | 3.11.16, `/srv/ai/sound-vision/.venv-reference` |
| Torch / torchaudio | 2.8.0+cu128; verified `sm_120` support |
| Transformers | 4.45.2 |
| FFmpeg | Host 6.1.1, including shared libraries |
| SheetSage2 | `eab522a8168e8b8b8c4856bf8609cd86198f01fe` |
| MERT-v2-FullSong parent | `d8ba1c745e733b3908ce6ad16ebeb17ac7600a42` |
| Model paths | `/srv/ai/models/yue2/reference.lock.json` |

This is a separate environment because SheetSage2's Transformers/numpy pins differ from YuE2's. CUDA 12.8 wheels retain the upstream Torch version while supporting Legion's RTX 5090. Exact installed dependencies are recorded in `deploy/legion-reference-freeze.txt`.

The downloader uses public, revision-pinned repositories with `token=False`. Custom model Python code was inspected before activation: the parent is revision-pinned, the model uses safetensors, and decoding/export operations were reviewed. Runtime model loading is offline. Upload decoding allows only local file/pipe protocols and expected audio containers, checks duration, then normalizes to bounded 24 kHz mono audio before invoking SheetSage2.

Reference transcription shares Sound and Vision's GPU mutex and external-queue/free-memory admission policy with YuE2. It never interrupts or unloads another app. If other GPU work appears, only its own process is terminated. Linux parent-death signaling and service control-group shutdown prevent orphaned workers. This remains a private application mutex, not a global lease honored by other services.

## Persistence and routes

`db/0003_assistance.sql` adds SQLite/D1-compatible job metadata. Input and final proposal/transcription/cover metadata are durable. Active/queued assistance requests become failed on restart with original input retained; they are not silently re-billed. Browser pending IDs survive reload. Writing submissions are idempotent by request ID and exact input; repeated image requests for a take reuse its active job.

| Route | Purpose |
|---|---|
| GET `/api/openai/account` | Non-secret account status, models, capabilities, pending device code |
| POST `/api/openai/login` | Start sign-in |
| POST `/api/openai/login/cancel` | Cancel pending sign-in |
| POST `/api/openai/logout` | Disconnect this installation after active assistance finishes |
| POST `/api/assistance` | Queue a structured writing/score proposal |
| GET `/api/assistance/{id}` | Poll state/result/error |
| POST `/api/assistance/{id}/cancel` | Cancel an owned request |
| POST `/api/references?mode=melody\|full` | Stream private raw audio upload; `X-Filename` is an encoded display name |
| POST `/api/takes/{id}/cover` | Queue/retry a cover for an existing take |
| GET `/api/takes/{id}/cover` | Serve the current validated PNG |

All routes retain the existing server-token authentication and same-origin local proxy. Public hosting and per-user access control are not supplied by ChatGPT account login. Reference inputs, normalized audio, worker log, ABC/MIDI/timed annotations and result metadata are under `data/references/{id}`. Cover attempts are under `data/covers/{takeId}/{requestId}.png`. Include these with the database and original generation runs in backups; keep account credentials separate and private.

## Official demos

The demo page, repository README and complete repository tree were checked on 10 September 2026. No root license or explicit grant to republish the demo recordings was found. Third-party font/player licenses and model-weight licenses do not establish permission to reuse the recordings. Therefore no official demo audio was imported, no cover-art batch was made from those demos, and no external demo links were added to the interface. This is an unresolved reuse permission, not a claim that reuse is expressly forbidden. The saved provenance receipt is `docs/upstream/sheetsage2/sources.json`.

## Install / verify

After the base YuE2 service installation, stop only `sound-vision.service` before installing/updating its runtimes, then copy `backend/`, `db/`, and `deploy/` into the service root. Run `python3 deploy/install_assistance.py --root /srv/ai/sound-vision --models /srv/ai/models/yue2` on Legion as the service owner. It verifies the official Codex package, creates a separate Python 3.11 runtime using the installed `uv`, installs pinned reference dependencies, and downloads the two pinned public models. Install the updated base `backend/requirements.txt`, then start/restart `sound-vision.service`. Sign in using the app's account panel.

`deploy/verify_assistance.py --submit` deliberately spends account usage and transcribes an existing original song. Without `--submit`, it only polls the retained run. `scripts/verify-assistance-browser.mjs --live` similarly makes one real idea request and one reference upload. `--resume` reuses recorded results after a browser-check interruption. The normal `npm test` suite mocks API calls and creates no music/account jobs.

## Installation

First complete the [main installation guide](../../SELF_HOSTED.md). The optional installer currently expects `uv` at `~/.local/bin/uv` and installs both the account runtime and a separate reference-transcription environment. It downloads additional packages and model weights. Run as the backend service owner, from the application folder, using the same model directory selected during setup:

```sh
.venv/bin/python deploy/install_assistance.py --root "$PWD" --models "$PWD/models"
```

Use `--skip-openai` if you want only reference transcription. Local writing and ComfyUI images do not require this installer. After installation, connect the OpenAI account through **Your account** if you chose that provider. The pinned account binaries target Linux x86-64; this optional installation is not a macOS or Windows installer.
