# Sound and Vision music backend

The music engine is installed on Legion. The current visual design is unchanged; its creation controls now submit durable jobs and the library plays real generated takes.

## What runs where

| Component | Current deployment |
|---|---|
| Browser / React UI | Development Mac, `http://127.0.0.1:5190/music` |
| Private connection | SSH tunnel to Legion; automatic with `npm run dev` |
| App API + queue owner | Legion, user service `sound-vision.service`, loopback `127.0.0.1:5191` |
| API / worker source | `/srv/ai/sound-vision/backend` |
| Isolated Python | `/srv/ai/sound-vision/.venv`, Python 3.12.3 / PyTorch 2.10.0+cu128 |
| Upstream source | `/srv/ai/sound-vision/YuE`, pinned commit in `deploy/source.lock.json` |
| Models | `/srv/ai/models/yue2`, pinned generator and listening decoder subdirectories |
| Durable metadata | `/srv/ai/sound-vision/data/library.sqlite3` |
| Immutable attempts | `/srv/ai/sound-vision/data/runs/<take-id>/attempt-<number>/` |

The current machine at `192.168.1.100` identified itself as `LEGION`, with an RTX 5090 / 32607 MiB total VRAM and 125 GiB RAM. These are deployment observations, not public installation defaults. No shared Python, CUDA, driver, ComfyUI, H3LIX or account environment was changed.

## Use the app

Run `npm run dev` from the app directory. Operator-only `.env.local` supplies the backend URL, service-token file, and SSH host alias. The script opens an independent authenticated SSH connection if needed, then starts Vite. The token is injected by the local proxy and never placed in browser JavaScript, URLs, source control or logs. The API is not exposed on Legion's LAN interfaces. The development proxy rejects foreign Origin/Host and cross-site requests.

Create requires a description/style and reviewed lyrics. Use the connected OpenAI writing assistant to draft lyrics and apply its proposal, or enter your own. Without a backend configured, local preview/draft editing still works. If a previously connected backend is lost, input is preserved and generation reports a connection error rather than inventing a result.

Choose one or two takes. Each receives an independent durable job, recorded seed and cover request. Generated tracks appear in the same existing library with actual stage, elapsed time and duration. Open Track details to cancel, retry, inspect a score, download the generation record, or export WAV, FLAC and MP3. A generated take can be selected as the Video soundtrack; video rendering remains a later phase.

Advanced's Review score before recording pauses after saving the plan. View score, optionally edit a copy, and Approve score & generate. An unchanged plan reloads the exact saved token IDs through `SymbolicPlan.load`. An edit is passed as new ABC; the original plan remains in its earlier attempt directory.

## Verified model contract

See the complete pinned [generation guide](../upstream/yue2/docs/generation.md), [editing guide](../upstream/yue2/docs/editing.md), [covers guide](../upstream/yue2/docs/covers.md), [source notes](../upstream/yue2/docs/source-notes.md), and [notation reference](../upstream/yue2/skills/yue2-music/references/abc-editing.md).

- Generation source: `92a73cc7652fcc1f937855e4b765e0a0edd7ff2e`, package `yue2-infer 0.1.6`.
- Generator: `m-a-p/YuE2-3B@1a96eca688d6ae5d7f0feb88573fec89920fcd19`.
- Listening decoder: `m-a-p/YuE2-Vae@95535e72a97bc0f09b8ada125d26b4009428c0e8`.
- Standard `torch` backend, no quantization, BF16 generator, float32 decoder,24 GiB configured memory budget. No optional vLLM/FP8 acceleration was enabled.
- Pipeline: plan → semantic generation → synthesis → decode. Native token callbacks and stage transitions provide progress. No fabricated completion percentage is displayed.
- Backend validation preserves exact 63-bit integer seeds, handles `cot=full/melody/off`, external ABC, guidance, score/music sampling and synthesis steps. Full/melody defaults and off-mode guidance defaults come from upstream.
- A second explicitly seeded take uses the next seed modulo 2^63. Blank seeds produce independent recorded random seeds.
- Style tempo/language/instrument suggestions are prompt preferences; there is no claim of exact-duration control, waveform-preserving edits or native stems.

## Durable jobs and recovery

The API transaction inserts the request, one/two takes, jobs and separate cover records before returning HTTP 202. The client retains the submission ID across ambiguous network failures. Repeating the same ID and exact inputs returns the original takes; changing inputs under that ID returns 409.

Only one worker process runs at a time. SQLite WAL and foreign keys preserve relational state. A service lock prevents two API owners using the same database. On restart, formerly running jobs become interrupted/failed and retain their directories; they are not silently resampled. Queued jobs remain queued. Retry creates a fresh attempt for only the selected failed/cancelled take. Completed audio is never overwritten by retry.

Each worker is a child process owned by Sound and Vision. Cancellation sets an owned cancellation flag, uses upstream cancellation callbacks during planning/semantic/synthesis, and terminates only that process if needed. Linux parent-death signaling and systemd control-group shutdown prevent orphaned workers from retaining GPU memory. Decoder cancellation may require terminating the owned worker because upstream does not expose a decoder cancellation callback. This is job restart, not resumable sampling.

The app observes both configured ComfyUI queues, requires at least 23552 MiB free GPU memory and low current utilization, and checks again before starting. YuE2’s configured 24 GiB budget reserves 2 GiB internally, limiting its PyTorch allocation pool to 22 GiB; the admission threshold leaves another 1 GiB for non-pool overhead. This avoids rejecting an otherwise idle 32 GiB device because another service retains a small context. It never calls ComfyUI interrupt/free/unload or stops another service. If external work appears during a run, Sound and Vision yields by cancelling its own worker and keeps the partial attempt for explicit retry. This is conservative contention detection, not an atomic global scheduler: unrelated apps do not honor Sound and Vision's local lock, so races remain possible until all producers share a lease protocol.

## Artifacts and exports

An attempt keeps upstream `audio.flac`, `score.abc`, `plan.json`, `semantic.npy`, `latent.npy`, `request.json`, `config.json`, and `result.json`, plus saved plan files, partial intermediates, worker log and progress. `delivery.json` records SHA-256/size, model/source revisions, effective timing, truncation, duration, sample rate, peak/RMS/clipped fraction and measured process VRAM.

WAV is the float32 decoded original. Upstream FLAC is 24-bit PCM. MP3 is a 320 kbit/s delivery derivative. None implies an increase in source quality. FFprobe checks each output's duration and stereo streams before it becomes downloadable. Non-finite, very short or effectively silent audio fails publication while retaining evidence. Truncation or clipping warnings remain visible rather than silently trimming or discarding the take. Listening quality and complete lyric coverage still require auditioning; structural checks are not a music-quality score.

Only allowed filenames under a take's server-owned attempt directory can be downloaded. Audio stays unavailable until validation succeeds. Requests cannot choose filesystem paths or shell commands.

## Database and optional services

`db/0001_music.sql`, `db/0002_generation_jobs.sql` and `db/0003_assistance.sql` use SQLite-compatible schema and indexes; D1 is not deployed. Local SQLite is the live source of truth for generated music. Model weights and media stay on durable server storage, not in database blobs. A future D1 adapter must retain submission transactions/idempotency and carefully separate remote metadata from Legion's file/job ownership.

OpenAI account sign-in, writing/score proposals, automatic per-take covers and SheetSage2 audio-reference transcription are implemented. Details, pins and routes are in [ASSISTANCE.md](ASSISTANCE.md). The account image capability is discovered; the unverified GPT Image 2.5 label has been removed. No account credentials were copied from H3LIX or another app and no paid API fallback was added.

## Documentation inventory

`docs/upstream/yue2/` contains the upstream README, every documentation guide, original examples, agent-skill references/helpers, package manifest and original license notices. Generator and decoder model cards and weight manifests are in `model-cards/`. These are pinned reference snapshots, not an instruction to activate a skill or install optional transcription models. Runtime weights are outside this source repository.

The first-party application remains Apache-2.0. YuE2 code/docs are Apache-2.0; generator and decoder weights retain CC BY-NC 4.0. Keep source and weight terms separate. Full upstream licenses are included in the documentation snapshot.

Operational setup, restart, connection recovery and backup are in [OPERATIONS.md](OPERATIONS.md). Measurements and checks are in [VERIFICATION.md](VERIFICATION.md).
