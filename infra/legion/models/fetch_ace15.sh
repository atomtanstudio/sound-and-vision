#!/usr/bin/env bash
# ACE-Step 1.5 for ComfyUI (Comfy-Org's split files, from Hugging Face): the XL turbo DiT, the two Qwen text encoders
# and the VAE, about 15 GB, into the models folder's comfyui/ under ace_step_1.5/ subfolders. Each file downloads to
# .part, is checked against the SHA-256 Hugging Face publishes, then moved into place. Safe to re-run.
#
#   infra/legion/models/fetch_ace15.sh
#
# The models folder is SV_MODELS: from the environment, else from the install's sv.env, else models/ at the top of
# this checkout (the app's own default). A leading ~ is your home folder.
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/../../.." && pwd)"
home() { case "$1" in "~") printf '%s' "$HOME" ;; "~/"*) printf '%s/%s' "$HOME" "${1#\~/}" ;; *) printf '%s' "$1" ;; esac; }

models="${SV_MODELS:-}"
if [ -z "$models" ] && [ -f "$repo_root/sv.env" ]; then
  models="$(sed -n 's/^[[:space:]]*SV_MODELS=//p' "$repo_root/sv.env" | tail -n1)"
  models="${models%"${models##*[![:space:]]}"}"
  models="${models#\"}" models="${models%\"}" models="${models#\'}" models="${models%\'}"
fi
models="$(home "${models:-$repo_root/models}")"
base="$models/comfyui"
repo=https://huggingface.co/Comfy-Org/ace_step_1.5_ComfyUI_files/resolve/main/split_files

files=(
  "diffusion_models acestep_v1.5_xl_turbo_bf16.safetensors 86a1afb0a1f711f0e3304ff65d874df3ae6783db683dcf982513fb9b6d14ae71"
  "text_encoders qwen_0.6b_ace15.safetensors fd4590c82153b8ddb67e15a2e7aaa8afa8b83a858c8a9b82a4831063156aa7a7"
  "text_encoders qwen_1.7b_ace15.safetensors ed63e9247d1f55f3ace04fa11e95b085fc82d459c82c5626f0b2e37b91ebd710"
  "vae ace_1.5_vae.safetensors 6de92e3a862acd287e08b024ac90f0783a8635451b728721a33ff03565bcb2bb"
)

echo "into $base"
for entry in "${files[@]}"; do
  read -r kind name sha <<<"$entry"
  dir="$base/$kind/ace_step_1.5"
  dest="$dir/$name"
  mkdir -p "$dir"
  if [ -f "$dest" ]; then
    echo "have $kind/ace_step_1.5/$name"
    continue
  fi
  echo "fetch $kind/ace_step_1.5/$name"
  curl -fL --retry 5 --retry-delay 10 -C - -o "$dest.part" "$repo/$kind/$name"
  got=$(sha256sum "$dest.part" | cut -d' ' -f1)
  if [ "$got" != "$sha" ]; then
    echo "checksum mismatch for $name: $got" >&2
    exit 1
  fi
  mv "$dest.part" "$dest"
  echo "ok $name"
done
echo "ACE-Step 1.5 files ready"
