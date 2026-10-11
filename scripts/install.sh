#!/usr/bin/env bash
# Sound / Vision: install it, or update it, on the machine it runs on (Linux with an NVIDIA GPU), from this checkout.
# Running it again is safe: it brings everything up to date and keeps your settings (sv.env), data and models.
#
#   scripts/install.sh [options]
#
#   1. checks what the app needs: the NVIDIA driver, Docker with Compose and the NVIDIA Container Toolkit, uv, Node,
#      ffmpeg, curl, systemd and free disk space
#   2. makes sv.env from sv.env.example when there isn't one (this install's settings)
#   3. makes the data and models folders, and downloads the instrumental influence YuE2 needs (CREDITS.md)
#   4. installs the server's Python packages (server/.venv) and builds the web app (web/dist)
#   5. builds the images here, from this checkout (nothing ready-made is pulled): the Claude studio (minutes),
#      sv-comfy (about an hour the first time) and sv-analysis; then starts sv-comfy
#   6. installs the app as a systemd user service (sv-app), starts it and waits for it to answer
#
# Options
#   --open-lan        let devices on this machine's local network use the app without its key: writes that network
#                     (found with `ip`) into SV_OPEN_NETWORKS in sv.env, if that is empty
#   --no-images       build no images and leave sv-comfy as it is (--skip-studio --skip-comfy --skip-analysis)
#   --skip-studio     don't build the Claude studio image
#   --skip-comfy      don't build, set up or start sv-comfy (the ComfyUI that songs, pictures and video run on)
#   --skip-analysis   don't build the sv-analysis image
#   --skip-web        don't build the web app
#   --no-service      don't install, start or restart the sv-app service
#   --force           restart the app and sv-comfy even while jobs are queued or running (those jobs are stopped)
#   --check           only check this machine and list the model files that are missing; change nothing
#   -h, --help        this text
#
# sv-comfy's own settings can go in sv.env or the environment (sv.env wins): SV_COMFY_ROOT (default $SV_DATA/comfy),
# SV_COMFY_IMAGE, SV_COMFY_BIND (default 127.0.0.1, this machine only, when SV_COMFY is a local address),
# SV_COMFY_PORT (default: the port in SV_COMFY), SV_CUDA_ARCH, SV_UID/SV_GID. See infra/legion/comfy/setup.sh.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$REPO/sv.env"
ME="$(id -un)"
COMFY_TAG="sv-comfy:0.39-c9d8a6e"  # infra/legion/comfy/setup.sh's default image

usage() { awk 'NR > 1 && /^set -euo/ {exit} NR > 1 {sub(/^# ?/, ""); print}' "$0"; }

OPEN_LAN=0 STUDIO=1 COMFY=1 ANALYSIS=1 WEB=1 SERVICE=1 FORCE=0 CHECK=0
for a in "$@"; do
  case "$a" in
    --open-lan) OPEN_LAN=1 ;;
    --no-images) STUDIO=0 COMFY=0 ANALYSIS=0 ;;
    --skip-studio) STUDIO=0 ;;
    --skip-comfy) COMFY=0 ;;
    --skip-analysis) ANALYSIS=0 ;;
    --skip-web) WEB=0 ;;
    --no-service) SERVICE=0 ;;
    --force) FORCE=1 ;;
    --check) CHECK=1 ;;
    -h | --help) usage; exit 0 ;;
    *) echo "unknown option: $a (see scripts/install.sh --help)" >&2; exit 2 ;;
  esac
done

# ---- output -------------------------------------------------------------------------------------------------------
B="" R="" Y="" N=""
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then B=$'\e[1m' R=$'\e[31m' Y=$'\e[33m' N=$'\e[0m'; fi
ERRORS=0
step() { printf '\n%s== %s%s\n' "$B" "$*" "$N"; }
ok() { printf '  ok      %s\n' "$*"; }
info() { printf '  --      %s\n' "$*"; }
warn() { printf '  %swarning%s %s\n' "$Y" "$N" "$*"; }
bad() { printf '  %sneeded%s  %s\n' "$R" "$N" "$*"; ERRORS=$((ERRORS + 1)); }
note() { printf '          %s\n' "$*"; }
die() { printf '\n%serror:%s %s\n' "$R" "$N" "$*" >&2; exit 1; }
ask() { local r; read -r -p "  $1 [y/N] " r; [[ "$r" =~ ^[Yy] ]]; }

TMPS=()
trap 'if [ ${#TMPS[@]} -gt 0 ]; then rm -f "${TMPS[@]}"; fi' EXIT

# ---- settings -----------------------------------------------------------------------------------------------------
# The app reads only sv.env (through systemd), so its settings come from sv.env and the defaults, never from this
# shell; sv-comfy's install-time settings may also come from the environment.
home() { case "$1" in "~") printf '%s' "$HOME" ;; "~/"*) printf '%s/%s' "$HOME" "${1#\~/}" ;; *) printf '%s' "$1" ;; esac; }
INSTALL_ONLY=(SV_COMFY_ROOT SV_COMFY_IMAGE SV_COMFY_BIND SV_COMFY_PORT SV_CUDA_ARCH SV_UID SV_GID)
for k in "${INSTALL_ONLY[@]}"; do printf -v "SAVED_$k" '%s' "${!k:-}"; done

url_host() { local r="${1#*://}"; r="${r%%/*}"; r="${r%:*}"; printf '%s' "${r:-127.0.0.1}"; }
url_port() {
  local r="${1#*://}"; r="${r%%/*}"
  case "$r" in *:*) r="${r##*:}" ;; *) r="" ;; esac
  case "$r" in '' | *[!0-9]*) printf '8210' ;; *) printf '%s' "$r" ;; esac
}

load_settings() {
  local name line k v s
  local re_dq='^"(.*)"$' re_sq="^'(.*)'\$"
  while IFS= read -r name; do case "$name" in SV_*) unset "$name" ;; esac; done < <(compgen -e)
  if [ -f "$ENV_FILE" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
      line="${line#"${line%%[![:space:]]*}"}"
      line="${line#export }"
      [[ "$line" =~ ^(SV_[A-Z0-9_]+)=(.*)$ ]] || continue
      k="${BASH_REMATCH[1]}" v="${BASH_REMATCH[2]}"
      v="${v%"${v##*[![:space:]]}"}"
      if [[ "$v" =~ $re_dq || "$v" =~ $re_sq ]]; then v="${BASH_REMATCH[1]}"; fi
      export "$k=$v"
    done < "$ENV_FILE"
  fi
  for k in "${INSTALL_ONLY[@]}"; do
    s="SAVED_$k"
    if [ -z "${!k:-}" ] && [ -n "${!s}" ]; then export "$k=${!s}"; fi
  done
  DATA="$(home "${SV_DATA:-$REPO/data}")"
  MODELS="$(home "${SV_MODELS:-$REPO/models}")"
  PORT="${SV_PORT:-7660}"
  LORAS="$(home "${SV_LORAS:-$MODELS/comfyui/loras}")"
  ANALYSIS_MODELS="$(home "${SV_ANALYSIS_MODELS:-$MODELS/audio-separation/sv}")"
  WHISPER="$(home "${SV_WHISPER:-$MODELS/huggingface/models--Systran--faster-whisper-large-v3}")"
  ANALYSIS_IMAGE="${SV_ANALYSIS_IMAGE:-sv-analysis:latest}"
  STUDIO_IMAGE="${SV_STUDIO_IMAGE:-sv-claude-studio:latest}"
  FFMPEG="${SV_FFMPEG:-ffmpeg}"
  COMFY_URL="${SV_COMFY:-http://127.0.0.1:8210}"
  COMFY_ROOT="$(home "${SV_COMFY_ROOT:-$DATA/comfy}")"
  COMFY_IMAGE="${SV_COMFY_IMAGE:-$COMFY_TAG}"
  COMFY_PORT="${SV_COMFY_PORT:-$(url_port "$COMFY_URL")}"
  case "$(url_host "$COMFY_URL")" in
    127.0.0.1 | localhost | "[::1]") COMFY_BIND="${SV_COMFY_BIND:-127.0.0.1}" ;;
    *) COMFY_BIND="${SV_COMFY_BIND:-0.0.0.0}" ;;
  esac
  case "$PORT" in '' | *[!0-9]*) die "SV_PORT in sv.env isn't a port number: $PORT" ;; esac
}

# ---- helpers ------------------------------------------------------------------------------------------------------
have() { command -v "$1" >/dev/null 2>&1; }
py() {
  if [ -x "$REPO/server/.venv/bin/python" ]; then "$REPO/server/.venv/bin/python" "$@"
  elif have python3; then python3 "$@"
  else return 1; fi
}
version_ge() {  # version_ge 13.2 13.2: true when the first is the same or newer
  local IFS=. i x y
  local -a a b
  read -r -a a <<<"$1"
  read -r -a b <<<"$2"
  for i in 0 1 2; do
    x="${a[i]:-0}" y="${b[i]:-0}"
    x="${x//[!0-9]/}" y="${y//[!0-9]/}"
    x="${x:-0}" y="${y:-0}"
    if ((10#$x > 10#$y)); then return 0; fi
    if ((10#$x < 10#$y)); then return 1; fi
  done
  return 0
}
free_gb() {  # free space, in GB, on the disk a folder is (or would be) on
  local d="$1"
  while [ ! -d "$d" ]; do d="$(dirname "$d")"; done
  df -Pk "$d" | awk 'NR == 2 {print int($4 / 1048576)}'
}
canon() { if [ -d "$1" ]; then (cd -P "$1" && pwd); else printf '%s' "${1%/}"; fi; }  # a folder's real path
sed_escape() { printf '%s' "$1" | sed -e 's/[\\|&]/\\&/g'; }
tree_sum() {  # a checksum of a folder's files ("" when it doesn't exist)
  [ -d "$1" ] || return 0
  (cd "$1" && find . -type f ! -path '*/__pycache__/*' -print0 | sort -z | xargs -0 -r sha256sum | sha256sum | cut -c1-16)
}
# the app's own API, with its key sent on stdin so it never appears in a process list
api() {
  local f="$DATA/secrets/api-token" tok
  [ -r "$f" ] || return 1
  tok="$(<"$f")"
  tok="${tok//[[:space:]]/}"
  printf 'Authorization: Bearer %s\n' "$tok" | curl -fsS --max-time 5 -H @- "http://127.0.0.1:$PORT$1"
}
# how many jobs the running app has queued or running ("?" when it didn't say); fails when it isn't running
app_busy() {
  systemctl --user is-active -q sv-app 2>/dev/null || return 1
  local body n
  body="$(api /api/jobs 2>/dev/null)" || { echo "?"; return 0; }
  n="$(printf '%s' "$body" | py -c 'import json, sys; print(len(json.load(sys.stdin)))' 2>/dev/null)" || n="?"
  echo "$n"
}
guard_jobs() {  # a restart stops whatever job is running (a take half-sung is lost)
  [ "$FORCE" = 0 ] || return 0
  local n
  n="$(app_busy)" || return 0
  [ "$n" != 0 ] || return 0
  die "sv-app has $n job(s) queued or running (or didn't answer), and $1 would stop them. Run this again when they're done, or with --force."
}
# this machine's local network (the one its default route goes out on), when it is a private one
lan_network() {
  have ip || return 1
  local dev net
  dev="$(ip -4 route show default 2>/dev/null | awk '{for (i = 1; i < NF; i++) if ($i == "dev") {print $(i + 1); exit}}')"
  [ -n "$dev" ] || return 1
  net="$(ip -4 route show dev "$dev" scope link proto kernel 2>/dev/null | awk '$1 ~ /\// {print $1; exit}')"
  case "$net" in
    10.* | 192.168.* | 172.1[6-9].* | 172.2[0-9].* | 172.3[01].*) printf '%s' "$net" ;;
    *) return 1 ;;
  esac
}
set_env_value() {  # set_env_value KEY VALUE: replaces the first KEY= line in sv.env, or adds one at the end
  local tmp
  tmp="$(mktemp "$ENV_FILE.XXXXXX")"
  TMPS+=("$tmp")
  awk -v k="$1" -v v="$2" '!done && $0 ~ "^[[:space:]]*" k "=" {print k "=" v; done = 1; next} {print}
    END {if (!done) print k "=" v}' "$ENV_FILE" > "$tmp"
  chmod 600 "$tmp"
  mv "$tmp" "$ENV_FILE"
}

# ---- 1. the machine -----------------------------------------------------------------------------------------------
check_machine() {
  step "Checking this machine"
  local gpu mib cuda cap need path_dirs dir tool where

  # the NVIDIA driver and GPU
  if have nvidia-smi && nvidia-smi -L >/dev/null 2>&1; then
    gpu="$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits | head -n1)"
    mib="${gpu##*, }"
    mib="${mib//[!0-9]/}"
    mib="${mib:-0}"
    if [ "$mib" -ge 24000 ]; then ok "GPU: ${gpu%,*}, $(((mib + 512) / 1024)) GB"
    else warn "GPU: ${gpu%,*} has $(((mib + 512) / 1024)) GB; the models are sized for 24 GB or more (32 GB on the reference machine)"; fi
    cuda="$(nvidia-smi | sed -n 's/.*CUDA Version: *\([0-9][0-9.]*\).*/\1/p' | head -n1)"
    if [ -n "$cuda" ] && version_ge "$cuda" 13.2; then ok "NVIDIA driver for CUDA $cuda"
    else bad "an NVIDIA driver for CUDA 13.2 or newer (this one: ${cuda:-unknown}); the images are built on CUDA 13.2"; fi
    cap="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -n1 | tr -d ' ')"
    case "$cap" in
      8.0 | 8.6 | 8.9 | 9.0 | 12.0) ;;
      *)
        if [ "$COMFY" = 1 ] && [ -z "${SV_CUDA_ARCH:-}" ] && ! docker image inspect "$COMFY_IMAGE" >/dev/null 2>&1; then
          bad "sv-comfy's SageAttention build supports GPUs of compute capability 8.0, 8.6, 8.9, 9.0 or 12.0; this one is ${cap:-unknown}"
        fi ;;
    esac
  else
    bad "an NVIDIA GPU with its driver (nvidia-smi doesn't work)"
  fi

  # Docker, Compose and the NVIDIA Container Toolkit
  DOCKER_OK=0
  if ! have docker; then
    bad "Docker Engine (https://docs.docker.com/engine/install/)"
  elif ! docker info >/dev/null 2>&1; then
    bad "Docker, usable by $ME: start it, or add yourself to the docker group (sudo usermod -aG docker $ME, then log in again)"
  else
    DOCKER_OK=1
    ok "Docker $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo '')"
    if docker compose version >/dev/null 2>&1; then ok "Docker Compose $(docker compose version --short 2>/dev/null || echo '')"
    else bad "Docker Compose v2 (the 'docker compose' plugin)"; fi
    local runtimes cdi
    # shellcheck disable=SC2016
    runtimes="$(docker info --format '{{range $k, $v := .Runtimes}}{{$k}} {{end}}' 2>/dev/null || true)"
    cdi="$(docker info 2>/dev/null | grep -c 'nvidia.com/gpu' || true)"
    if [[ " $runtimes " == *" nvidia "* ]] || [ "${cdi:-0}" -gt 0 ] || have nvidia-container-runtime-hook; then
      ok "NVIDIA Container Toolkit"
    else
      bad "the NVIDIA Container Toolkit, set up for Docker (https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)"
    fi
  fi

  # the server, the web app and the media tools
  if have uv; then ok "uv $(uv --version 2>/dev/null | awk '{print $2}')"
  else bad "uv, which installs the server's Python (https://docs.astral.sh/uv/getting-started/installation/)"; fi
  if have python3.12; then ok "Python 3.12"; else info "no python3.12 here: uv will fetch one"; fi
  if [ "$WEB" = 1 ]; then
    if have node && have npm; then
      local v
      v="$(node --version 2>/dev/null)"
      v="${v#v}"
      if { version_ge "$v" 20.19 && ! version_ge "$v" 21; } || version_ge "$v" 22.12; then ok "Node $v"
      else bad "Node 20.19 or newer (22.12 or newer on Node 22), to build the web app; this is $v"; fi
    else
      bad "Node.js with npm (20.19 or newer), to build the web app"
    fi
  elif [ ! -f "$REPO/web/dist/index.html" ]; then
    warn "--skip-web and no web/dist yet: the app will run without its interface"
  fi
  if have "$FFMPEG"; then ok "ffmpeg"; else bad "ffmpeg (or SV_FFMPEG in sv.env pointing at it)"; fi
  if have ffprobe; then ok "ffprobe"; else bad "ffprobe (it comes with ffmpeg)"; fi
  if have curl; then ok "curl"; else bad "curl"; fi
  case "${SV_MUSIC:-}" in smb://*) have smbclient || warn "SV_MUSIC is a network share; reading it needs smbclient" ;; esac

  # systemd, and whether the service will find the tools
  if [ "$SERVICE" = 1 ]; then
    case "$REPO" in *[[:space:]]*) bad "a checkout path without spaces (the service file can't hold $REPO)" ;; esac
    if systemctl --user show-environment >/dev/null 2>&1; then
      ok "systemd user services"
      path_dirs="$(systemctl --user show-environment 2>/dev/null | sed -n 's/^PATH=//p')"
      path_dirs="${path_dirs:-/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin}"
      for tool in docker "$FFMPEG" ffprobe; do
        where="$(command -v "$tool" 2>/dev/null || true)"
        case "$where" in /*) ;; *) continue ;; esac
        dir="$(dirname "$where")"
        case ":$path_dirs:" in *":$dir:"*) ;; *)
          case "$tool" in /*) ;; *) warn "the service's PATH ($path_dirs) has no $dir, so it won't find $tool; add PATH=… to sv.env" ;; esac ;;
        esac
      done
    else
      bad "systemd user services (systemctl --user) in this session: log in as $ME directly or over ssh (not su or sudo), or use --no-service"
    fi
  fi
  if [ "$(id -u)" != 1000 ]; then
    warn "song analysis containers run as uid 1000 and write into your data folder; as uid $(id -u), give uid 1000 write access to $DATA"
  fi

  # disk
  need=5
  if [ "$DOCKER_OK" = 1 ]; then
    if [ "$COMFY" = 1 ] && ! docker image inspect "$COMFY_IMAGE" >/dev/null 2>&1; then need=50; fi
    local root free
    root="$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || echo /var/lib/docker)"
    free="$(free_gb "$root")"
    if [ "$free" -ge "$need" ]; then ok "$free GB free for Docker images ($root)"
    else bad "$need GB free for Docker images in $root (there are $free); sv-comfy and sv-analysis take about 45 GB"; fi
  fi
  local fm fd
  fm="$(free_gb "$MODELS")"
  fd="$(free_gb "$DATA")"
  if [ "$fm" -ge 110 ]; then ok "$fm GB free for models ($MODELS)"
  else warn "$fm GB free for models in $MODELS; every model together is about 110 GB (fewer if you leave features out)"; fi
  if [ "$fd" -ge 20 ]; then ok "$fd GB free for songs and videos ($DATA)"
  else warn "$fd GB free for songs and videos in $DATA"; fi

  if [ "$ERRORS" -gt 0 ] && [ "$CHECK" = 0 ]; then die "$ERRORS thing(s) to put right first (marked 'needed' above); then run this again."; fi
}

# ---- 2. sv.env ----------------------------------------------------------------------------------------------------
make_env() {
  step "Settings (sv.env)"
  local made=0 net
  if [ ! -f "$ENV_FILE" ]; then
    cp "$REPO/sv.env.example" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    made=1
    ok "made sv.env from sv.env.example: data in data/, models in models/, port 7660"
  else
    ok "keeping your sv.env"
  fi
  load_settings
  if [ -n "${SV_OPEN_NETWORKS:-}" ]; then
    ok "open without a key to $SV_OPEN_NETWORKS (SV_OPEN_NETWORKS)"
    return 0
  fi
  if [ "$OPEN_LAN" = 1 ] || { [ "$made" = 1 ] && [ -t 0 ] && [ -t 1 ]; }; then
    if net="$(lan_network)"; then
      if [ "$OPEN_LAN" = 1 ] || ask "Let devices on $net (this machine's local network) use the app without its key?"; then
        set_env_value SV_OPEN_NETWORKS "$net"
        load_settings
        ok "open without a key to $net (SV_OPEN_NETWORKS)"
        return 0
      fi
    else
      warn "couldn't find this machine's private local network; set SV_OPEN_NETWORKS in sv.env by hand (e.g. 192.168.1.0/24)"
    fi
  fi
  ok "every browser pairs once with the app's key (SV_OPEN_NETWORKS is empty)"
}

# ---- 3. folders ---------------------------------------------------------------------------------------------------
make_folders() {
  step "Folders"
  local k side model
  mkdir -p "$DATA"
  for k in checkpoints clip clip_vision controlnet diffusion_models embeddings loras text_encoders upscale_models \
           latent_upscale_models vae vae_approx audio_encoders model_patches; do
    mkdir -p "$MODELS/comfyui/$k"
  done
  mkdir -p "$LORAS/soundandvision/yue2" "$LORAS/soundandvision/ace15" "$LORAS/soundandvision/music3" \
           "$ANALYSIS_MODELS/torch/hub/checkpoints" "$MODELS/huggingface"
  # the descriptions of the influences the app knows by name (their weights aren't in the repo)
  for side in "$REPO"/infra/legion/influences/*/*.json; do
    [ -e "$side" ] || continue
    model="$(basename "$(dirname "$side")")"
    mkdir -p "$LORAS/soundandvision/$model"
    cp "$side" "$LORAS/soundandvision/$model/"
  done
  ok "data   $DATA"
  ok "models $MODELS (ComfyUI's folders are in comfyui/)"
}

# ---- the instrumental influence -----------------------------------------------------------------------------------
# "YuE2-instrumental-cot-full-loras" by Mothersuperior, CC BY-NC 4.0 (non-commercial use only): YuE2 uses it for every
# instrumental. Downloaded unmodified from the author's own page and checked; it isn't in this repo (CREDITS.md).
INST_FILE="ar_lora_inst_v3abc_comfyui.safetensors"
INST_URL="https://huggingface.co/Mothersuperior/YuE2-instrumental-cot-full-loras/resolve/main/$INST_FILE"
INST_SHA="de6a11d5701df103a191c87dc73115266e2420f3834739319dec5c24d2119f31"

fetch_instrumental() {
  step "The instrumental influence"
  local dest="$LORAS/soundandvision/yue2/$INST_FILE"
  if [ -f "$dest" ]; then
    ok "$INST_FILE is here"
    return
  fi
  note "\"YuE2-instrumental-cot-full-loras\" by Mothersuperior, CC BY-NC 4.0 (non-commercial use only; see CREDITS.md)"
  if curl -fL --retry 3 -o "$dest.part" "$INST_URL" && printf '%s  %s\n' "$INST_SHA" "$dest.part" | sha256sum -c --status; then
    mv "$dest.part" "$dest"
    ok "downloaded $INST_FILE (213 MB) from huggingface.co/Mothersuperior"
  else
    rm -f "$dest.part"
    warn "couldn't download $INST_FILE; YuE2 instrumentals need it: $INST_URL"
  fi
}

# ---- 4. server and web app ----------------------------------------------------------------------------------------
build_server() {
  step "Server (Python packages in server/.venv)"
  (cd "$REPO/server" && env -u UV_PROJECT_ENVIRONMENT -u VIRTUAL_ENV uv sync --no-dev --python 3.12)
  ok "server/.venv"
}

build_web() {
  step "Web app (web/dist)"
  (cd "$REPO/web" && npm ci --no-audit --no-fund && npm run build)
  ok "web/dist"
}

# ---- 5. images ----------------------------------------------------------------------------------------------------
build_studio() {
  step "The Claude studio image ($STUDIO_IMAGE)"
  bash "$REPO/infra/studio/studio.sh" build
  ok "$STUDIO_IMAGE"
}

setup_comfy() {
  step "sv-comfy ($COMFY_IMAGE, port $COMFY_PORT on $COMFY_BIND)"
  local mounted before after host
  if docker container inspect sv-comfy >/dev/null 2>&1; then
    mounted="$(docker container inspect sv-comfy \
      --format '{{range .Mounts}}{{if eq .Destination "/sv/profile"}}{{.Source}}{{end}}{{end}}' 2>/dev/null || true)"
    if [ -z "$mounted" ] || [ "$(canon "$mounted")" != "$(canon "$COMFY_ROOT/profile")" ]; then
      warn "a container named sv-comfy already exists${mounted:+, with its profile in $mounted}; leaving it alone"
      [ -z "$mounted" ] || note "to look after that one from here, set SV_COMFY_ROOT=$(dirname "$mounted") in sv.env"
      return 0
    fi
  fi
  before="$(tree_sum "$COMFY_ROOT/profile/custom_nodes/sv_nodes")"
  SV_COMFY_ROOT="$COMFY_ROOT" SV_MODELS="$MODELS" SV_COMFY_IMAGE="$COMFY_IMAGE" SV_COMFY_BIND="$COMFY_BIND" \
    SV_COMFY_PORT="$COMFY_PORT" bash "$REPO/infra/legion/comfy/setup.sh"
  after="$(tree_sum "$COMFY_ROOT/profile/custom_nodes/sv_nodes")"
  guard_jobs "restarting sv-comfy"
  (cd "$COMFY_ROOT/deploy" && docker compose up -d) \
    || die "sv-comfy didn't start; see: cd $COMFY_ROOT/deploy && docker compose logs comfy"
  if [ -n "$before" ] && [ "$before" != "$after" ]; then
    (cd "$COMFY_ROOT/deploy" && docker compose restart comfy)
  fi
  host="$COMFY_BIND"
  case "$host" in 0.0.0.0 | "") host=127.0.0.1 ;; esac
  for _ in $(seq 1 90); do
    if curl -fsS --max-time 3 "http://$host:$COMFY_PORT/system_stats" >/dev/null 2>&1; then
      ok "sv-comfy answers on http://$host:$COMFY_PORT"
      if [ "$(url_port "$COMFY_URL")" != "$COMFY_PORT" ]; then
        warn "the app looks for ComfyUI at $COMFY_URL (SV_COMFY in sv.env), not on port $COMFY_PORT"
      fi
      return 0
    fi
    sleep 2
  done
  warn "sv-comfy hasn't answered yet (it can take a few minutes the first time); see: docker logs sv-comfy"
}

build_analysis() {
  step "The sv-analysis image ($ANALYSIS_IMAGE)"
  if ! docker image inspect "$COMFY_IMAGE" >/dev/null 2>&1; then
    warn "it builds on $COMFY_IMAGE, which isn't here yet: skipped (run this again without --skip-comfy)"
    return 0
  fi
  docker build --build-arg "BASE_IMAGE=$COMFY_IMAGE" -t "$ANALYSIS_IMAGE" "$REPO/infra/legion/analysis"
  ok "$ANALYSIS_IMAGE"
}

# ---- 6. the service -----------------------------------------------------------------------------------------------
install_service() {
  step "The app's service (sv-app)"
  local dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user" unit tmp old body
  unit="$dir/sv-app.service"
  mkdir -p "$dir"
  tmp="$(mktemp "$dir/.sv-app.XXXXXX")"
  TMPS+=("$tmp")
  sed -e "s|@SERVER@|$(sed_escape "$REPO/server")|g" -e "s|@ENV@|$(sed_escape "$ENV_FILE")|g" \
    "$REPO/infra/sv-app.service.in" > "$tmp"
  if [ -f "$unit" ]; then
    old="$(sed -n 's/^WorkingDirectory=//p' "$unit" | head -n1)"
    if [ "$old" != "$REPO/server" ]; then note "replacing the sv-app service that ran from ${old:-somewhere else}"; fi
  fi
  chmod 644 "$tmp"
  mv "$tmp" "$unit"
  guard_jobs "restarting the app"
  systemctl --user daemon-reload
  systemctl --user enable -q sv-app
  systemctl --user restart sv-app
  ok "$unit"

  if [ "$(loginctl show-user "$ME" --property=Linger --value 2>/dev/null || true)" = yes ]; then
    ok "it starts with the machine (linger is on for $ME)"
  elif loginctl --no-ask-password enable-linger "$ME" >/dev/null 2>&1; then
    ok "it starts with the machine (turned linger on for $ME)"
  else
    warn "until linger is on for $ME, the app stops when you log out and doesn't start with the machine; an administrator can turn it on:"
    note "sudo loginctl enable-linger $ME"
  fi

  for _ in $(seq 1 60); do
    if body="$(api /api/health 2>/dev/null)"; then
      ok "the app answers on port $PORT"
      if [ "$(printf '%s' "$body" | py -c 'import json, sys; print(bool((json.load(sys.stdin).get("comfy") or {}).get("ok")))' 2>/dev/null)" != True ]; then
        warn "the app can't reach ComfyUI at $COMFY_URL yet"
      fi
      return 0
    fi
    sleep 1
  done
  die "sv-app didn't answer within a minute; see: journalctl --user -u sv-app -n 50"
}

# ---- models -------------------------------------------------------------------------------------------------------
# what each feature loads, under $SV_MODELS/comfyui (README.md, "Models", says where each comes from)
MODEL_FILES=(
  "Songs with YuE2 (the default)|checkpoints/yue2_3b_bf16.safetensors"
  "Covering a song with YuE2|audio_encoders/sheetsage2_bf16.safetensors"
  "Instrumentals with YuE2 (downloaded by this script)|loras/soundandvision/yue2/ar_lora_inst_v3abc_comfyui.safetensors"
  "Songs with ACE-Step 1.5 (infra/legion/models/fetch_ace15.sh)|diffusion_models/ace_step_1.5/acestep_v1.5_xl_turbo_bf16.safetensors text_encoders/ace_step_1.5/qwen_0.6b_ace15.safetensors text_encoders/ace_step_1.5/qwen_1.7b_ace15.safetensors vae/ace_step_1.5/ace_1.5_vae.safetensors"
  "Songs with MiniMax Music 3|diffusion_models/minimax_music3/minimax_music3_dit_fp16.safetensors text_encoders/minimax_music3/minimax_music3_text_encoder_pruned_int8_convrot.safetensors vae/minimax_music3/minimax_music3_dav.safetensors"
  "Pictures on this GPU (Krea 2)|diffusion_models/krea2_turbo_fp8_scaled.safetensors text_encoders/qwen3vl_4b_fp8_scaled.safetensors vae/wan_2.1_vae.safetensors"
  "Sharper covers (4x upscale)|upscale_models/4x-ClearRealityV1.pth"
  "Video with MiniMax H3 (Living Album Cover, Music Video)|diffusion_models/minimax_h3_fused_refdelta_r1024_turbo8_mystic07_int8_convrot.safetensors text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors vae/minimax_h3_video_vae_int8_convrot.safetensors"
  "Living Album Cover: keeping people still (SAM 3.1)|checkpoints/sam3.1_multiplex_fp16.safetensors"
)

have_model() {  # ComfyUI reads clip/ as text_encoders/ and unet/ as diffusion_models/
  local f="$1" base="$MODELS/comfyui" alt=""
  case "$f" in
    loras/*) [ -f "$LORAS/${f#loras/}" ]; return ;;
    text_encoders/*) alt="clip/${f#text_encoders/}" ;;
    diffusion_models/*) alt="unet/${f#diffusion_models/}" ;;
  esac
  [ -f "$base/$f" ] || { [ -n "$alt" ] && [ -f "$base/$alt" ]; }
}

models_report() {
  step "Models ($MODELS)"
  local entry what f
  local -a files missing
  for entry in "${MODEL_FILES[@]}"; do
    what="${entry%%|*}"
    read -r -a files <<<"${entry#*|}"
    missing=()
    for f in "${files[@]}"; do have_model "$f" || missing+=("$f"); done
    if [ ${#missing[@]} -eq 0 ]; then ok "$what"
    else
      info "$what: missing"
      for f in "${missing[@]}"; do note "$f"; done
    fi
  done
  if compgen -G "$WHISPER/snapshots/*/model.bin" >/dev/null; then ok "Hearing the words of your own songs (Whisper large-v3)"
  else info "Hearing the words of your own songs (Whisper large-v3): missing, in $WHISPER"; fi
  info "Stems and word timing: fetched into $ANALYSIS_MODELS the first time a song is analysed"
  note "What each feature needs and where the files come from: README.md, \"Models\"."
}

# ---- the end ------------------------------------------------------------------------------------------------------
summary() {
  step "Open it"
  local ip ips
  printf '  http://%s:%s\n' "$(uname -n)" "$PORT"
  ips="$(ip -4 -o addr show scope global 2>/dev/null \
    | awk '$2 !~ /^(docker|br-|veth|virbr|cni|flannel|podman|lxc)/ {split($4, a, "/"); print a[1]}' || true)"
  for ip in $ips; do printf '  http://%s:%s\n' "$ip" "$PORT"; done
  if [ -n "${SV_OPEN_NETWORKS:-}" ]; then
    note "Devices on $SV_OPEN_NETWORKS come straight in. Anyone else pairs once with the key in"
  else
    note "Each browser pairs once with the key in"
  fi
  note "$DATA/secrets/api-token (cat it on this machine and paste it into the app)."

  step "Next"
  local n=1 signin="infra/studio/studio.sh signin"
  if grep -qE '^[[:space:]]*SV_(DATA|STUDIO|STUDIO_LOGIN|STUDIO_IMAGE)=.' "$ENV_FILE" 2>/dev/null; then
    signin="(set -a; . ./sv.env; set +a; infra/studio/studio.sh signin)"
  fi
  if [ "${DOCKER_OK:-0}" = 1 ] && docker image inspect "$STUDIO_IMAGE" >/dev/null 2>&1 \
     && bash "$REPO/infra/studio/studio.sh" status 2>/dev/null | grep -qE '"loggedIn": *true'; then
    ok "Claude is signed in"
  else
    printf '  %d. Sign in to Claude once, in a terminal on this machine (or ssh -t), from %s:\n' "$n" "$REPO"
    note "$signin"
    n=$((n + 1))
  fi
  printf '  %d. Put the model files for the features you want in %s/comfyui (see README.md, "Models").\n' "$n" "$MODELS"
  n=$((n + 1))
  printf '  %d. In the app, Settings: sign in to ChatGPT or Grok, add MCP servers, and choose who does what.\n' "$n"
  note "Settings are in sv.env; after changing it: systemctl --user restart sv-app"
}

# ---- run ----------------------------------------------------------------------------------------------------------
[ "$(uname -s)" = Linux ] || die "This installs Sound / Vision on the Linux GPU machine it runs on. To work on it from another computer, see scripts/deploy.sh."
[ "$(uname -m)" = x86_64 ] || die "Sound / Vision's images are built for x86_64 (this machine is $(uname -m))."
[ "$(id -u)" != 0 ] || die "Run this as the account the app should run as, not as root: it installs a systemd user service and needs no sudo."

load_settings
check_machine
if [ "$CHECK" = 1 ]; then
  models_report
  [ "$ERRORS" = 0 ] || exit 1
  exit 0
fi
if [ "$SERVICE" = 1 ] || [ "$COMFY" = 1 ]; then guard_jobs "updating"; fi
make_env
make_folders
fetch_instrumental
build_server
if [ "$WEB" = 1 ]; then build_web; fi
if [ "$STUDIO" = 1 ]; then build_studio; fi
if [ "$COMFY" = 1 ]; then setup_comfy; fi
if [ "$ANALYSIS" = 1 ]; then build_analysis; fi
if [ "$SERVICE" = 1 ]; then install_service; fi
models_report
summary
