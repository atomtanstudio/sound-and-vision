#!/usr/bin/env bash
# Sound / Vision's own ComfyUI (sv-comfy): one instance for songs (YuE2, MiniMax Music 3, ACE-Step 1.5) and video
# (MiniMax H3 with VRGameDevGirl's music-video routes). Run it from the repo (infra/legion/comfy/setup.sh) or from the
# deploy folder it fills; running it again is safe.
#
#   1. makes the folders under $SV_COMFY_ROOT: deploy, cache, profile/{custom_nodes,input,output,temp,user}
#   2. builds the image from this folder's Dockerfile, unless $SV_COMFY_IMAGE exists already
#   3. copies docker-compose.yml, extra_model_paths.yaml, node_packs.txt and this script into deploy/, with an .env of
#      the settings below, so that `docker compose up -d` in deploy/ starts it
#   4. fills the profile's custom_nodes: a node pack that isn't there is copied out of the image (pinned commits, see
#      node_packs.txt), and sv_nodes is refreshed from this repo when run from it
#
# It writes only under $SV_COMFY_ROOT, plus the image. The models folder is mounted read-only and never written.
#
# Settings (environment, else the .env next to this script when it runs from deploy/, else Legion's defaults; a
# leading ~ is your home folder):
#   SV_COMFY_ROOT   /srv/ai/sv/comfy          where sv-comfy keeps its profile, cache and deploy files
#   SV_MODELS       /srv/ai/models            the models folder (ComfyUI's model folders are in its comfyui/)
#   SV_COMFY_IMAGE  sv-comfy:0.39-c9d8a6e     the image to build and run
#   SV_COMFY_BIND   0.0.0.0                   the address the API listens on (127.0.0.1: this machine only)
#   SV_COMFY_PORT   8210                      its port
#   SV_UID, SV_GID  you (1000 when run as root)   the user ComfyUI runs as; it must own the folders above
#   SV_CUDA_ARCH    this machine's GPU        "major.minor" SageAttention is compiled for (8.0 8.6 8.9 9.0 12.0)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
home() { case "$1" in "~") printf '%s' "$HOME" ;; "~/"*) printf '%s/%s' "$HOME" "${1#\~/}" ;; *) printf '%s' "$1" ;; esac; }

# settings left unset come from an earlier run's deploy/.env (when run from deploy/)
if [ -f "$here/.env" ]; then
  while IFS='=' read -r k v; do
    case "$k" in SV_*) [ -n "${!k:-}" ] || export "$k=$v" ;; esac
  done < "$here/.env"
fi
root="$(home "${SV_COMFY_ROOT:-/srv/ai/sv/comfy}")"
models="$(home "${SV_MODELS:-/srv/ai/models}")"
image="${SV_COMFY_IMAGE:-sv-comfy:0.39-c9d8a6e}"
bind="${SV_COMFY_BIND:-0.0.0.0}"
port="${SV_COMFY_PORT:-8210}"
uid="${SV_UID:-$(id -u)}" gid="${SV_GID:-$(id -g)}"
if [ "$uid" = 0 ]; then uid=1000 gid=1000; fi

made=("$root" "$root"/{deploy,cache,profile} "$root"/profile/{custom_nodes,input,output,temp,user,user/default,user/default/workflows})
mkdir -p "${made[@]}"
if [ "$(id -u)" = 0 ]; then chown "$uid:$gid" "${made[@]}"; fi
[ -d "$models/comfyui" ] || echo "note: $models has no comfyui/ folder yet; ComfyUI will start without models" >&2

# the image: built here from public sources (Dockerfile), never pulled
if ! docker image inspect "$image" >/dev/null 2>&1; then
  if [ ! -f "$here/Dockerfile" ]; then
    echo "No image $image, and no Dockerfile next to this script: run infra/legion/comfy/setup.sh from the repo." >&2
    exit 1
  fi
  arch="${SV_CUDA_ARCH:-}"
  if [ -z "$arch" ] && command -v nvidia-smi >/dev/null; then
    arch="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | sort -u | paste -sd ';' -)"
  fi
  arch="${arch:-12.0}"
  for a in ${arch//;/ }; do
    case "$a" in 8.0|8.6|8.9|9.0|12.0) ;;
      *) echo "SageAttention 2.2 compiles for GPUs of compute capability 8.0, 8.6, 8.9, 9.0 or 12.0, not $a." >&2; exit 1 ;;
    esac
  done
  echo "building $image for compute capability $arch (about an hour) …"
  docker build --build-arg "TORCH_CUDA_ARCH_LIST=$arch" -t "$image" "$here"
fi

# deploy/: what `docker compose up -d` there needs
if [ "$here" != "$root/deploy" ]; then
  cp "$here/docker-compose.yml" "$here/extra_model_paths.yaml" "$here/setup.sh" "$here/node_packs.txt" "$root/deploy/"
fi
cat > "$root/deploy/.env" <<EOF
# Written by setup.sh: sv-comfy's settings, read by docker compose in this folder.
SV_COMFY_ROOT=$root
SV_MODELS=$models
SV_COMFY_IMAGE=$image
SV_COMFY_BIND=$bind
SV_COMFY_PORT=$port
SV_UID=$uid
SV_GID=$gid
EOF

# the profile's node packs. ComfyUI loads custom nodes from the profile (--base-directory), so the image's pinned
# checkouts are copied there once; a pack already in the profile is left as it is.
nodes="$root/profile/custom_nodes"
packs=(comfyui-vrgamedevgirl comfyui-minimax-h3-audio-T8 Comfyui_Minimax_h3_latent_Upscaler TE-Speed-MiniMaxH3-OSS
       ComfyUI-KJNodes ComfyUI-VideoHelperSuite)
if [ -f "$here/node_packs.txt" ]; then
  packs=()
  while read -r name _; do case "$name" in ''|'#'*) ;; *) packs+=("$name") ;; esac; done < "$here/node_packs.txt"
fi
cid=""
trap '[ -z "$cid" ] || docker rm -f "$cid" >/dev/null' EXIT
from_image() {
  [ -n "$cid" ] || cid="$(docker create "$image")"
  docker cp "$cid:/opt/ComfyUI/custom_nodes/$1" "$nodes/$1"
  if [ "$(id -u)" = 0 ]; then chown -R "$uid:$gid" "$nodes/$1"; fi
}
for d in "${packs[@]}"; do
  [ -d "$nodes/$d" ] || from_image "$d"
  printf '%-40s %s\n' "$d" "$(git -C "$nodes/$d" rev-parse --short HEAD 2>/dev/null || echo '?')"
done
if [ -d "$here/custom_nodes/sv_nodes" ]; then
  mkdir -p "$nodes/sv_nodes"
  cp -R "$here/custom_nodes/sv_nodes/." "$nodes/sv_nodes/"
  if [ "$(id -u)" = 0 ]; then chown -R "$uid:$gid" "$nodes/sv_nodes"; fi
elif [ ! -d "$nodes/sv_nodes" ]; then
  from_image sv_nodes
fi
printf '%-40s %s\n' sv_nodes ours

echo "ready: cd $root/deploy && docker compose up -d   (the API: port $port on $bind)"
