#!/usr/bin/env bash
# The Claude studio: Claude Code in a container, signed in with the owner's own Claude subscription, plus the film kit
# (/opt/kit in the image: engine, tools, CLAUDE.md, skills, npm packages, fonts) every film starts from.
#
#   studio.sh build [--no-cache]    build (or update) the image from this folder's Dockerfile (kit/ goes to /opt/kit);
#                                   --no-cache also fetches the newest Claude Code
#   studio.sh signin                sign in once, interactively, in a terminal (ssh -t <machine> …/studio.sh signin)
#   studio.sh status                is the studio signed in? (prints Claude Code's own status as JSON)
#   studio.sh seed <folder>         copy the film kit into <folder>; never replaces a file that is already there
#   studio.sh run <folder> [args]   run `claude [args]` with <folder> as its only working folder
#   studio.sh exec <folder> <cmd…>  run one command with <folder> as /work (python3 tools/import_song.py, a render …)
#
# run and exec get the machine's NVIDIA GPU (Chromium draws WebGL through it; SV_CHROME_ARGS tells the film's tools
# how), unless SV_STUDIO_GPU=0, which gives them Chromium's software renderer instead. SV_STUDIO_NAME names the
# container so the app can stop it; SV_COMFY_URL, when set, is passed through for tools/h3plate.py.
#
# Where things are (environment; a leading ~ is your home folder):
#   SV_STUDIO_LOGIN  the folder Claude Code keeps its login in        default: $SV_STUDIO/claude
#   SV_STUDIO        the studio's own folder                          default: $SV_DATA/studio, else data/studio here
#   SV_STUDIO_IMAGE  the image                                        default: sv-claude-studio:latest
#
# The login folder is 0700, written and read only by Claude Code inside the container; only `run`, `signin` and
# `status` mount it. The app starts containers and reads their output; it never reads that folder.
# Containers get no API key, no host environment, and no folder but the one they work on.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
home() { case "$1" in "~") printf '%s' "$HOME" ;; "~/"*) printf '%s/%s' "$HOME" "${1#\~/}" ;; *) printf '%s' "$1" ;; esac; }
DATA="$(home "${SV_DATA:-$REPO/data}")"
STUDIO="$(home "${SV_STUDIO:-$DATA/studio}")"
CONFIG="$(home "${SV_STUDIO_LOGIN:-$STUDIO/claude}")"
IMAGE="${SV_STUDIO_IMAGE:-sv-claude-studio:latest}"
mkdir -p "$CONFIG" && chmod 700 "$CONFIG"
if [ "$(dirname "$CONFIG")" = "$STUDIO" ]; then chmod 700 "$STUDIO"; fi
# inside this checkout (the default), keep the login out of git whatever the top-level .gitignore says
case "$CONFIG/" in "$REPO/"*) [ -e "$CONFIG/.gitignore" ] || printf '*\n' > "$CONFIG/.gitignore" ;; esac

base=(--rm --network bridge --shm-size 2g)
common=("${base[@]}" -v "$CONFIG:/studio/claude")
named=()
if [ -n "${SV_STUDIO_NAME:-}" ]; then named=(--name "$SV_STUDIO_NAME"); fi
GPU_CHROME="--no-sandbox --ozone-platform=headless --use-angle=gl-egl --use-gl=angle --ignore-gpu-blocklist --enable-gpu"
CPU_CHROME="--no-sandbox --ozone-platform=headless --use-angle=swiftshader --enable-unsafe-swiftshader"
if [ "${SV_STUDIO_GPU:-1}" = "0" ]; then
  gpu=(-e "SV_CHROME_ARGS=$CPU_CHROME")
else
  gpu=(--gpus all -e NVIDIA_DRIVER_CAPABILITIES=all -e "SV_CHROME_ARGS=$GPU_CHROME")
fi
extra=()
if [ -n "${SV_COMFY_URL:-}" ]; then extra=(-e "SV_COMFY_URL=$SV_COMFY_URL"); fi

case "${1:-}" in
  build)
    shift
    # the container's user gets this account's uid/gid, so it owns the folders it's given (root builds keep 1000)
    uid="$(id -u)" gid="$(id -g)"
    if [ "$uid" = 0 ]; then uid=1000 gid=1000; fi
    docker build --pull "$@" --build-arg "STUDIO_UID=$uid" --build-arg "STUDIO_GID=$gid" -t "$IMAGE" "$HERE"
    docker run --rm "$IMAGE" claude --version
    docker run --rm "$IMAGE" node /opt/kit/build/check-kit.mjs
    ;;
  signin)
    # Claude Code's own subscription login: open the link it prints in any browser, approve, and paste the code the
    # browser shows back here. The login is saved in $CONFIG by Claude Code; nothing else touches it.
    docker run -it "${common[@]}" "$IMAGE" claude auth login --claudeai
    docker run "${common[@]}" "$IMAGE" claude auth status
    ;;
  status)
    exec docker run "${common[@]}" "$IMAGE" claude auth status
    ;;
  seed)
    folder="$(realpath -m "${2:?a folder to seed}")"
    mkdir -p "$folder"
    exec docker run --rm --network none -v "$folder:/work" "$IMAGE" /opt/kit/build/seed.sh
    ;;
  run)
    folder="$(realpath "${2:?a folder to work in}")"
    shift 2
    exec docker run -i "${common[@]}" ${named[@]+"${named[@]}"} "${gpu[@]}" ${extra[@]+"${extra[@]}"} -v "$folder:/work" "$IMAGE" claude "$@"
    ;;
  exec)
    folder="$(realpath "${2:?a folder to work in}")"
    shift 2
    if [ $# -eq 0 ]; then echo "studio.sh exec <folder> <command…>" >&2; exit 2; fi
    tty=()
    if [ -t 0 ] && [ -t 1 ]; then tty=(-it); fi
    exec docker run ${tty[@]+"${tty[@]}"} "${base[@]}" ${named[@]+"${named[@]}"} "${gpu[@]}" ${extra[@]+"${extra[@]}"} -v "$folder:/work" "$IMAGE" "$@"
    ;;
  *)
    sed -n '2,24p' "$0"
    exit 2
    ;;
esac
