# Installation and operations

## Reproduce on a Linux GPU host

Use an operator-owned installation directory and model disk. The runtime needs Linux, Python 3.12, FFmpeg and an NVIDIA BF16 GPU with the documented 24 GiB baseline. Do not reuse another model application's virtual environment.

1. Extract the release source into the chosen installation root. Keep `backend/`, `db/`, `deploy/`, `scripts/video/` and `public/fonts/` in their original relative locations; the video and shared credit-preview helpers use those files.
2. Clone `https://github.com/multimodal-art-projection/YuE.git` into `<root>/YuE`, then check out `92a73cc7652fcc1f937855e4b765e0a0edd7ff2e`.
3. Create `<root>/.venv` with `python3.12 -m venv`. If the host lacks ensurepip, use `--without-pip` and bootstrap pip from the official `https://bootstrap.pypa.io/get-pip.py` **only into that venv**, or install the OS's Python 3.12 venv support. Do not change shared Python/GPU packages.
4. Install `<root>/YuE` and `-r <root>/backend/requirements.txt` using that venv's Python. `deploy/legion-python-freeze.txt` records the exact observed environment; the source install and lock file, not an owner-specific direct-URL line from pip freeze, define portable setup.
5. Set `SOUND_VISION_MODELS=<model-storage>` and run `<venv>/bin/python <root>/deploy/download_models.py`. Only pinned generator and listening decoder files are downloaded. No SheetSage/MERT model is needed for basic generation.
6. Run `<venv>/bin/python -m pytest backend/test_api.py -q` from the root. Then use `deploy/install_service.py --root <root> --models <model-storage> --comfy-urls <comma-separated-existing-queue-URLs>`. This creates a service-owned token, configuration and a systemd **user** unit. If multiple GPU services are present, include each supported queue in that list.
7. Verify `systemctl --user status sound-vision.service`. User lingering must be enabled for startup without an interactive login. It was already enabled on the current Legion; the installer does not alter that machine policy.
8. Use the credential-file helper to check `/api/health`, then submit an original request. `deploy/verify_runtime.py --root <root> --generate` deliberately creates inference work and is an opt-in verification helper, not an installation step.

The first run verifies hashes against the downloaded upstream weight manifests. Keep `deploy/source.lock.json`, installed package versions, model cards and source license notices with the deployment. Do not commit weights or operator credentials.

## Current service controls

On Legion, as `richgates`:

```sh
systemctl --user status sound-vision.service
journalctl --user -u sound-vision.service -n 100 --no-pager
systemctl --user restart sound-vision.service
```

Restart only when no generation is active unless interruption is intentional. A restart preserves queued jobs and successful outputs; an in-flight attempt becomes interrupted and can be retried. Never restart ComfyUI/H3LIX to manage Sound and Vision.

Health without printing the token:

```sh
python3 /srv/ai/sound-vision/deploy/api_request.py /api/health --root /srv/ai/sound-vision
```

The API configuration and token are `/srv/ai/sound-vision/service.env` and `service.token`, mode 0600; the root/data are owner-only. The API binds only to Legion loopback 5191.

### Storyboard image generation

Music-video creation, scene rendering and recovery below are internal development features, disabled in this release. See [AI setup](LOCAL_PROVIDERS.md) for the release gate and supported local providers.

`SOUND_VISION_IMAGE_CONCURRENCY` in `service.env` sets the shared image-request limit. It defaults to 8 and accepts integers from 1 through 32. This is an application resource limit: the installed Codex runtime and the official documentation do not disclose an account-specific ImageGen concurrency maximum. Increasing it does not establish provider capacity. Apply changes by restarting Sound and Vision when idle.

Character sheets run in parallel first. The first storyboard image for each location runs next, followed by the other frames using those saved location and character references. Results stay in scene order. A failed request stops further scheduling while other in-flight requests finish and save; recovery reuses matching completed images.

Each illustrated frame has **Re-render frame**. Its dialog loads the exact saved image prompt, allows edits, and submits one replacement image with the original reference attachments. It retains the prior image and existing video takes; already rendered clips do not change. Opening or cancelling the dialog does not submit an image request.

Each existing scene video has **Re-render video**. This submits one fresh take from the current storyboard and song excerpt through `POST /api/films/{id}/scenes/{index}/rerender`, using `{requestId, revision}`. Progress appears beside the video. When ready, the new take appears for review; earlier takes remain in the **Video take** selector. **Use this take** selects the displayed video for the film. Re-rendering alone does not change the selected take or existing exports.

## App connection

Copy `.env.example` to `.env.local` on the development machine. Put a securely transferred service-token copy in `.secrets/service.token`, mode 0600, and set its path in `SOUND_VISION_TOKEN_FILE`. Set `SOUND_VISION_SSH_HOST` to an already configured SSH host/user. The current deployment uses the `legion` alias and `.secrets/legion-service.token`; these private files are ignored by source control.

`npm run dev` checks the backend and creates a dedicated SSH tunnel when needed. Explicit `ControlMaster=no` / `ControlPath=none` keep its lifecycle separate from other applications' shared SSH sessions. Vite sends the service token only from its server-side proxy. The browser uses relative `/api` URLs and has no credential to copy.

If the SSH connection closes, the development command exits with a clear error; restart `npm run dev` to reconnect. Jobs keep running on Legion and reappear after connection recovery. Do not repeatedly click Create with modified inputs to recover an uncertain response: the app retains an idempotency ID for unchanged inputs, so retrying those inputs cannot duplicate the original GPU jobs.

The development server is loopback-only. A public/Cloudflare deployment needs its own user authentication, server-side secrets and model-host connectivity; copying the private proxy onto a public host is not an authentication design.

## API contract

All routes require the service bearer token. The trusted local proxy supplies it; direct API requests without it receive 401.

| Route | Purpose |
|---|---|
| `GET /api/health` | Model revision/capability/format disclosure |
| `GET /api/library` | Persistent generated takes with current job state |
| `GET /api/library?include_deleted=true` | Includes recoverable items in Trash |
| `GET /api/projects` / `POST /api/projects` | Persistent folders, including empty folders |
| `POST /api/library/actions` | Atomic batch `move`, `trash`, or `restore`; 1–200 unique take IDs |
| `POST /api/generations` | `{requestId, form}`; returns 202 and one/two take IDs; idempotent |
| `PATCH /api/takes/{id}` | Title, project or favorite metadata |
| `POST /api/takes/{id}/cancel` | Cancel only this queued/running/plan-review take |
| `POST /api/takes/{id}/retry` | Fresh attempt for a failed/cancelled take |
| `GET /api/takes/{id}/plan` | Read retained ABC |
| `POST /api/takes/{id}/continue` | Approve exact plan; optional `{abc}` creates an edited-plan recording |
| `GET /api/takes/{id}/files/{name}` | Allowed validated audio or retained generation artifacts |

The typed validation contract is `backend/contracts.py`, with a saved JSON schema alongside the verification evidence. No request accepts a shell command or storage path. The application adapter makes one native YuE2 call per take, not a nonexistent upstream two-output option.

### Library management

Use Select, item checkboxes, Shift-click, or drag across covers/rows to select items. The bottom selection bar edits one item, moves a selection to an existing or new project, downloads a ZIP, or moves items to Trash. Cmd/Ctrl+A selects the visible filtered items when the library is focused; Escape clears selection. Grid/list changes retain selection; changing filters clears it.

Project moves and Trash/restore for generated tracks are transactional on Legion. Empty projects are saved in the same SQLite/D1-compatible projects table. Tracks in queued, waiting, or running generations must be cancelled or completed before moving to Trash; a rejected batch changes nothing. Trash preserves all artifacts and is reversible through the Trash filter. There is no automatic purge or permanent delete in this version. Local sample tracks and offline drafts retain their metadata in browser storage.

Downloads produce one ZIP with chosen MP3, WAV, or FLAC audio and creation settings per item. Drafts include settings only. The browser limits each bundle to 256 MB; use MP3 or a smaller selection for larger libraries. Sample tracks support MP3 and WAV. Renaming/project changes in Track details require Save changes; failed saves keep the editable values visible for retry. Editing a score still creates a new take and preserves the original recording.

Verification: run `pytest backend/test_api.py backend/test_assistance.py backend/test_library.py -q` with the isolated service environment. `npm test` writes UI evidence outside the source tree (override with `SOUND_VISION_EVIDENCE`).

## Backup and recovery

- Back up the metadata database **and** `data/runs/`; either alone is incomplete.
- Stop this service for a consistent filesystem copy, or use SQLite's online backup API for the DB and copy only immutable completed attempts, recording the snapshot point.
- Keep credentials/configuration in a separate protected operator backup. Weights can be restored from pinned repositories; retaining them locally avoids re-download and repository availability risk.
- Do not remove earlier failed/cancelled attempt directories automatically; they hold recovery evidence and original plans.
- Restore into a separate test root first. Check database foreign keys and delivery hashes before selecting it as live storage.
- Rollback: stop/disable `sound-vision.service`, restore the prior backend source/version, and retain data. Existing unrelated services need no changes.

## Account and reference setup

See [ASSISTANCE.md](ASSISTANCE.md) for the isolated Codex account runtime, private login store, separate SheetSage2 environment, upload limits, additional routes and verification commands. Back up `data/references/` and `data/covers/` with the library and generation runs. Keep `openai-account/` private; reconnect after migration rather than publishing credentials.
