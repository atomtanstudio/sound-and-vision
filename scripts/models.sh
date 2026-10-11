#!/usr/bin/env bash
# Sound / Vision: download the model files for the features you want, from Hugging Face, into the models folder.
# Each file downloads to .part (an interrupted download picks up where it stopped), is checked against the SHA-256
# below (the one Hugging Face publishes), then moved into place. Files already there are kept. Safe to re-run.
#
#   scripts/models.sh                 list the sets: what each is for, its size, and what's here already
#   scripts/models.sh SET [SET ...]   download those sets
#
# Sets
#   starter    songs + pictures: songs, covers and pictures on your GPU (about 28 GB)
#   songs      YuE2, the default song model, with covering a song and instrumentals (9.4 GB)
#   pictures   Krea 2 for covers and music video pictures, and the 4x upscaler for sharper covers (18.6 GB)
#   video      MiniMax H3 for Living Album Covers and music videos, and SAM 3.1 (41.2 GB)
#   ace        ACE-Step 1.5: a second song model, and new versions of a few bars (15.2 GB)
#   music3     MiniMax Music 3: a third song model (14.3 GB)
#   whisper    Whisper large-v3: hears the words of songs you upload without lyrics (3.1 GB; needs uv)
#   all        every set (about 102 GB)
#
# The folders come from SV_MODELS, SV_LORAS and SV_WHISPER: from the environment, else this install's sv.env, else
# the app's defaults (models/ at the top of this checkout). Each model has its own licence: README.md, "Licences".
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$REPO/sv.env"
HF=https://huggingface.co

usage() { awk 'NR > 1 && /^set -euo/ {exit} NR > 1 {sub(/^# ?/, ""); print}' "$0"; }

B="" R="" Y="" N=""
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then B=$'\e[1m' R=$'\e[31m' Y=$'\e[33m' N=$'\e[0m'; fi
step() { printf '\n%s== %s%s\n' "$B" "$*" "$N"; }
ok() { printf '  ok      %s\n' "$*"; }
info() { printf '  --      %s\n' "$*"; }
warn() { printf '  %swarning%s %s\n' "$Y" "$N" "$*"; }
note() { printf '          %s\n' "$*"; }
die() { printf '\n%serror:%s %s\n' "$R" "$N" "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

# ---- settings: the environment, else sv.env, else the app's defaults ---------------------------------------------
home() { case "$1" in "~") printf '%s' "$HOME" ;; "~/"*) printf '%s/%s' "$HOME" "${1#\~/}" ;; *) printf '%s' "$1" ;; esac; }
setting() {  # setting KEY: its value from the environment, else from sv.env ("" when neither has it)
  local v="${!1:-}"
  if [ -z "$v" ] && [ -f "$ENV_FILE" ]; then
    v="$(sed -n "s/^[[:space:]]*\(export \)\{0,1\}$1=//p" "$ENV_FILE" | tail -n1)"
    v="${v%"${v##*[![:space:]]}"}"
    v="${v#\"}" v="${v%\"}" v="${v#\'}" v="${v%\'}"
  fi
  printf '%s' "$v"
}
MODELS="$(home "$(setting SV_MODELS)")"
MODELS="${MODELS:-$REPO/models}"
LORAS="$(home "$(setting SV_LORAS)")"
LORAS="${LORAS:-$MODELS/comfyui/loras}"
WHISPER="$(home "$(setting SV_WHISPER)")"
WHISPER="${WHISPER:-$MODELS/huggingface/models--Systran--faster-whisper-large-v3}"

# ---- the files ----------------------------------------------------------------------------------------------------
# set | folder in comfyui/ (loras/… goes under SV_LORAS) | Hugging Face repository/path | SHA-256 | bytes
FILES=(
  "songs|checkpoints/yue2_3b_bf16.safetensors|Comfy-Org/YuE2/checkpoints/yue2_3b_bf16.safetensors|33765adbf9813c9a50318218760b2fd819a319862460a04884607581961c6fee|7799983228"
  "songs|audio_encoders/sheetsage2_bf16.safetensors|Comfy-Org/YuE2/audio_encoders/sheetsage2_bf16.safetensors|5fd960ce3df281e3f3a889d174584d88f96247711480cf96377b12d7e8b6adc5|1386868122"
  "songs|loras/soundandvision/yue2/ar_lora_inst_v3abc_comfyui.safetensors|Mothersuperior/YuE2-instrumental-cot-full-loras/ar_lora_inst_v3abc_comfyui.safetensors|de6a11d5701df103a191c87dc73115266e2420f3834739319dec5c24d2119f31|212891736"
  "pictures|diffusion_models/krea2_turbo_fp8_scaled.safetensors|Comfy-Org/Krea-2/diffusion_models/krea2_turbo_fp8_scaled.safetensors|eb4dd8c612cfd10f64f25b057e6e6bbcb5737c94a7372177e456dbf7579502f1|13141730784"
  "pictures|text_encoders/qwen3vl_4b_fp8_scaled.safetensors|Comfy-Org/Krea-2/text_encoders/qwen3vl_4b_fp8_scaled.safetensors|54bd5144df0bbc25dd6ccadfcb826b521445a1b06ae5a42570bdd2974ca87094|5242467968"
  "pictures|vae/wan_2.1_vae.safetensors|Comfy-Org/Wan_2.1_ComfyUI_repackaged/split_files/vae/wan_2.1_vae.safetensors|2fc39d31359a4b0a64f55876d8ff7fa8d780956ae2cb13463b0223e15148976b|253815318"
  "pictures|upscale_models/4x-ClearRealityV1.pth|Kim2091/ClearRealityV1/4x-ClearRealityV1.pth|a4cd3a25b00e0be949d4302fc774eb4d7f2ed5f47cdb51551e2d75fa6562e51e|9016074"
  "video|diffusion_models/minimax_h3_fused_refdelta_r1024_turbo8_mystic07_int8_convrot.safetensors|MATLOWAI/minimax-h3-fused-turbo-int8-convrot/diffusion_models/minimax_h3_fused_refdelta_r1024_turbo8_mystic07_int8_convrot.safetensors|4262e4e9963c553fa00016bbe83961407a4fc0a888be95fd836c8d4f2304e48b|20980178976"
  "video|text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors|Comfy-Org/MiniMax-H3/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors|35a88d51044231fe332301d7a62aa81e3f2cba62febeb446e2c1e3e0ef76f2c6|15687142551"
  "video|vae/minimax_h3_video_vae_int8_convrot.safetensors|Comfy-Org/MiniMax-H3/vae/minimax_h3_video_vae_int8_convrot.safetensors|52a2c8c73583c86e4f41cdcce3a6ad0ea562987bc0bf3d60a0cef5f5c8e60c0e|2811065184"
  "video|checkpoints/sam3.1_multiplex_fp16.safetensors|Comfy-Org/sam3.1/checkpoints/sam3.1_multiplex_fp16.safetensors|9ba99c92703c2e8b4f47de2d34a539bb8e18923049e238b780d70dbe6368eb03|1745546848"
  "ace|diffusion_models/ace_step_1.5/acestep_v1.5_xl_turbo_bf16.safetensors|Comfy-Org/ace_step_1.5_ComfyUI_files/split_files/diffusion_models/acestep_v1.5_xl_turbo_bf16.safetensors|86a1afb0a1f711f0e3304ff65d874df3ae6783db683dcf982513fb9b6d14ae71|9974719892"
  "ace|text_encoders/ace_step_1.5/qwen_0.6b_ace15.safetensors|Comfy-Org/ace_step_1.5_ComfyUI_files/split_files/text_encoders/qwen_0.6b_ace15.safetensors|fd4590c82153b8ddb67e15a2e7aaa8afa8b83a858c8a9b82a4831063156aa7a7|1191588248"
  "ace|text_encoders/ace_step_1.5/qwen_1.7b_ace15.safetensors|Comfy-Org/ace_step_1.5_ComfyUI_files/split_files/text_encoders/qwen_1.7b_ace15.safetensors|ed63e9247d1f55f3ace04fa11e95b085fc82d459c82c5626f0b2e37b91ebd710|3708523360"
  "ace|vae/ace_step_1.5/ace_1.5_vae.safetensors|Comfy-Org/ace_step_1.5_ComfyUI_files/split_files/vae/ace_1.5_vae.safetensors|6de92e3a862acd287e08b024ac90f0783a8635451b728721a33ff03565bcb2bb|337431732"
  "music3|diffusion_models/minimax_music3/minimax_music3_dit_fp16.safetensors|Comfy-Org/MiniMax-Music-3/diffusion_models/minimax_music3_dit_fp16.safetensors|45494a2b6b69af115902ff28eaf54118d19067aa54da01000f3e3efce7ba0e34|4914197682"
  "music3|text_encoders/minimax_music3/minimax_music3_text_encoder_pruned_int8_convrot.safetensors|Comfy-Org/MiniMax-Music-3/text_encoders/minimax_music3_text_encoder_pruned_int8_convrot.safetensors|010b7416d2336a08c711bc22ee65849c9623069ddb7d89bec011a75699e52014|9196611886"
  "music3|vae/minimax_music3/minimax_music3_dav.safetensors|Comfy-Org/MiniMax-Music-3/vae/minimax_music3_dav.safetensors|2a32155b769be01445fcc2a8663b910fc9e1751e18dc1c3ec528064512d9ef0c|216696128"
)
WHISPER_BYTES=3090839273
SETS=(songs pictures video ace music3 whisper)
declare -A ABOUT=(
  [songs]="YuE2, the default song model, with covering a song and instrumentals"
  [pictures]="Krea 2 for covers and music video pictures, and the 4x upscaler"
  [video]="MiniMax H3 for Living Album Covers and music videos, and SAM 3.1"
  [ace]="ACE-Step 1.5: a second song model, and new versions of a few bars"
  [music3]="MiniMax Music 3: a third song model"
  [whisper]="Whisper large-v3: hears the words of songs you upload without lyrics"
)
declare -A LICENCE=(
  [songs]="YuE2's weights: CC BY-NC (non-commercial), with a separate permission for individual creators. The instrumental influence, by Mothersuperior: CC BY-NC 4.0 (CREDITS.md)."
  [pictures]="Krea 2, the Wan 2.1 VAE and ClearReality: each under its own licence, on its model page."
  [video]="MiniMax H3: the MiniMax H3 Community License, which doesn't cover use in the US, the EU, the UK or Korea. SAM 3.1: its own licence."
  [ace]="ACE-Step 1.5: its own licence, on its model page."
  [music3]="MiniMax Music 3: its own licence, on its model page."
  [whisper]="Whisper large-v3 (Systran's faster-whisper conversion): MIT."
)

# ---- helpers ------------------------------------------------------------------------------------------------------
dest_of() {  # where a file goes
  case "$1" in loras/*) printf '%s/%s' "$LORAS" "${1#loras/}" ;; *) printf '%s/comfyui/%s' "$MODELS" "$1" ;; esac
}
present() {  # the file, or ComfyUI's other name for its folder (clip/ for text_encoders/, unet/ for diffusion_models/)
  local f="$1" alt=""
  [ -f "$(dest_of "$f")" ] && return 0
  case "$f" in
    text_encoders/*) alt="clip/${f#text_encoders/}" ;;
    diffusion_models/*) alt="unet/${f#diffusion_models/}" ;;
  esac
  [ -n "$alt" ] && [ -f "$MODELS/comfyui/$alt" ]
}
whisper_present() { compgen -G "$WHISPER/snapshots/*/model.bin" >/dev/null; }
gb() { awk -v b="$1" 'BEGIN {printf "%.1f GB", b / 1e9}'; }
free_bytes() {
  local d="$1"
  while [ ! -d "$d" ]; do d="$(dirname "$d")"; done
  df -Pk "$d" | awk 'NR == 2 {printf "%.0f", $4 * 1024}'
}
sha() { if have sha256sum; then sha256sum "$1"; else shasum -a 256 "$1"; fi | cut -d' ' -f1; }
set_bytes() {  # set_bytes SET [missing]: the set's size (only what's missing, with "missing")
  local s="$1" e total=0 set rel src sum bytes
  if [ "$s" = whisper ]; then
    if [ "${2:-}" != missing ] || ! whisper_present; then total=$WHISPER_BYTES; fi
  else
    for e in "${FILES[@]}"; do
      IFS='|' read -r set rel src sum bytes <<<"$e"
      [ "$set" = "$s" ] || continue
      if [ "${2:-}" = missing ] && present "$rel"; then continue; fi
      total=$((total + bytes))
    done
  fi
  printf '%s' "$total"
}
set_state() {  # "all here", "missing", or "n of m here"
  local s="$1" e have=0 count=0 set rel src sum bytes
  if [ "$s" = whisper ]; then
    if whisper_present; then echo "here"; else echo "missing"; fi
    return
  fi
  for e in "${FILES[@]}"; do
    IFS='|' read -r set rel src sum bytes <<<"$e"
    [ "$set" = "$s" ] || continue
    count=$((count + 1))
    if present "$rel"; then have=$((have + 1)); fi
  done
  if [ "$have" = "$count" ]; then echo "here"
  elif [ "$have" = 0 ]; then echo "missing"
  else echo "$have of $count files here"; fi
}

list() {
  step "Model sets (into $MODELS)"
  local s
  for s in "${SETS[@]}"; do
    printf '  %-9s %-9s %-28s %s\n' "$s" "$(gb "$(set_bytes "$s")")" "$(set_state "$s")" "${ABOUT[$s]}"
  done
  printf '\n  %s\n' "Download with: scripts/models.sh SET [SET ...]   (starter = songs + pictures; all = every set)"
}

fetch_file() {  # fetch_file REL SRC SHA BYTES
  local rel="$1" src="$2" want="$3" bytes="$4" dest got
  dest="$(dest_of "$rel")"
  if present "$rel"; then ok "$rel"; return 0; fi
  mkdir -p "$(dirname "$dest")"
  info "$rel ($(gb "$bytes"))"
  local repo="${src%%/*}/$(cut -d/ -f2 <<<"$src")" path
  path="${src#"$repo"/}"
  # (a .part that's already whole was stopped between downloading and checking: just check it)
  if [ ! -f "$dest.part" ] || [ "$(wc -c <"$dest.part" | tr -d ' ')" != "$bytes" ]; then
    curl -fL --retry 5 --retry-delay 10 -C - -o "$dest.part" "$HF/$repo/resolve/main/$path" \
      || die "the download of $rel stopped; run this again to carry on from where it got to"
  fi
  got="$(sha "$dest.part")"
  if [ "$got" != "$want" ]; then
    rm -f "$dest.part"
    die "$rel didn't match its published SHA-256 (got $got); it was removed, run this again to fetch it afresh"
  fi
  mv "$dest.part" "$dest"
  ok "$rel"
}

fetch_whisper() {
  if whisper_present; then ok "Whisper large-v3"; return 0; fi
  have uv || { warn "Whisper needs uv (https://docs.astral.sh/uv/), which scripts/install.sh also needs; skipped"; return 0; }
  info "Whisper large-v3 ($(gb "$WHISPER_BYTES"))"
  mkdir -p "$(dirname "$WHISPER")"
  uv tool run --from huggingface_hub hf download Systran/faster-whisper-large-v3 --cache-dir "$(dirname "$WHISPER")" >/dev/null \
    || die "the Whisper download stopped; run this again to carry on"
  whisper_present || die "Whisper downloaded, but not into $WHISPER (SV_WHISPER); see README.md, \"Models\""
  ok "Whisper large-v3"
}

# ---- run ----------------------------------------------------------------------------------------------------------
if [ $# -eq 0 ]; then list; exit 0; fi
want=()
for a in "$@"; do
  case "$a" in
    -h | --help) usage; exit 0 ;;
    all) want+=("${SETS[@]}") ;;
    starter) want+=(songs pictures) ;;
    songs | pictures | video | ace | music3 | whisper) want+=("$a") ;;
    *) die "no set called '$a' (see scripts/models.sh --help)" ;;
  esac
done
# each set once, in the order asked
declare -A seen=()
sets=()
for s in "${want[@]}"; do [ -n "${seen[$s]:-}" ] || { seen[$s]=1; sets+=("$s"); }; done

have curl || die "curl is needed"
need=0
for s in "${sets[@]}"; do need=$((need + $(set_bytes "$s" missing))); done
free="$(free_bytes "$MODELS")"
if [ "$need" -gt "$free" ]; then
  die "these sets need $(gb "$need") more, and $MODELS has $(gb "$free") free"
fi
info "$(gb "$need") to download into $MODELS ($(gb "$free") free)"

for s in "${sets[@]}"; do
  step "$s: ${ABOUT[$s]}"
  note "${LICENCE[$s]}"
  if [ "$s" = whisper ]; then fetch_whisper; continue; fi
  for e in "${FILES[@]}"; do
    IFS='|' read -r set rel src sum bytes <<<"$e"
    [ "$set" = "$s" ] || continue
    fetch_file "$rel" "$src" "$sum" "$bytes"
  done
done
step "Done"
note "scripts/install.sh --check lists what's still missing."
