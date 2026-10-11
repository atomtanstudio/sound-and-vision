# The Claude studio (`sv-claude-studio`)

The container Sound / Vision runs Claude Code in, for the films it writes in code (motion graphics, a living cover's
finish) and for the Claude writer. It holds Anthropic's Claude Code CLI (from Anthropic's signed apt repository,
unmodified), Chromium with the EGL loader (WebGL on the NVIDIA GPU), ffmpeg, Node 24, Python 3.11 with numpy and Pillow,
and the film kit at `/opt/kit` (npm packages, about ninety open-licensed fonts, `tools/import_song.py` and the rest).
`server/sv/video/MACHINE.md` is what a film session is told about it.

| File | |
|---|---|
| `Dockerfile` | The image. `kit/` is copied to `/opt/kit`. |
| `studio.sh` | Everything the app does with it: `build`, `signin`, `status`, `seed`, `run`, `exec` (usage at the top). `scripts/install.sh` runs `build`. |
| `kit/` | The film kit. Text only: the npm packages (`package-lock.json`) and the fonts (`build/fetch-fonts.mjs`) are fetched while the image builds, and `build/check-kit.mjs` fails the build if anything is missing. |

## Needs

Linux with Docker and the NVIDIA Container Toolkit (`docker run --gpus all …` must work). Without a GPU, set
`SV_STUDIO_GPU=0` and Chromium draws in software (much slower renders).

## Set up

```sh
infra/studio/studio.sh build          # builds sv-claude-studio:latest; the container's user gets your uid/gid
infra/studio/studio.sh signin         # once, in a terminal: Claude Code's own login with your Claude subscription
infra/studio/studio.sh status         # {"loggedIn": true, …}
```

The image turns Claude Code's auto-updater off. `studio.sh build --no-cache` updates it (a plain `build` reuses Docker's
cache, so it only picks up changes to the kit); the Dockerfile's `CLAUDE_CHANNEL` build argument picks Anthropic's apt
channel, `latest` by default.

## Settings

| Variable | Default | |
|---|---|---|
| `SV_STUDIO_LOGIN` | `$SV_STUDIO/claude` | The folder Claude Code keeps its login in (mode 0700). |
| `SV_STUDIO` | `$SV_DATA/studio`, or `data/studio` at the top of the repo | The studio's own folder. |
| `SV_STUDIO_IMAGE` | `sv-claude-studio:latest` | The image `build` makes and the other commands run. |
| `SV_STUDIO_GPU` | `1` | `0`: no GPU, Chromium's software renderer. |
| `SV_STUDIO_NAME` | | Names the container, so the app can stop it. |
| `SV_COMFY_URL` | | Passed into the container for the kit's `tools/h3plate.py`. |

The app finds this script through `SV_STUDIO_SH` (default `infra/studio/studio.sh`) and passes its own environment
through, so these can go in `sv.env`.

## What never happens

No API key is set in the image or passed to it, so nothing here can bill an API account. The login is written and
read only by Claude Code inside the container, and only `run`, `signin` and `status` mount it; the app reads container
output, never that folder. A container gets no host environment and no folder but the one it works on. Never commit
the login folder: when it sits inside this checkout, `studio.sh` puts a `.gitignore` in it that ignores everything.
