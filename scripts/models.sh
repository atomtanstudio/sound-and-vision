#!/usr/bin/env bash
# Sound / Vision: download the model files for the features you want, from Hugging Face, into the models folder.
# Each file downloads to .part and carries on by itself after a dropped or stalled connection, is checked against the
# SHA-256 in scripts/models.txt (the one Hugging Face publishes), then moved into place. A file counts as here only at
# its full size: one cut short (a download stopped elsewhere) is fetched again from where it stops. Safe to re-run.
#
#   scripts/models.sh                     list the sets: what each is for, its size, and what's here already
#   scripts/models.sh SET [SET ...]       download those sets
#   scripts/models.sh --verify SET ...    also check the SHA-256 of files already here, and fetch any that don't match
#   scripts/models.sh --file PATH         just that one file of models.txt (scripts/install.sh uses this)
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
TRIES="${SV_DOWNLOAD_TRIES:-20}"   # how many times one file's download carries on after the connection drops

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
MANIFEST="$REPO/scripts/models.txt"
[ -f "$MANIFEST" ] || die "$MANIFEST is missing"
mapfile -t FILES < <(sed -e 's/[[:space:]]*#.*$//' -e '/^[[:space:]]*$/d' "$MANIFEST")
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
found() {  # where the file is: its folder, or ComfyUI's other name for it (clip/ for text_encoders/, unet/ for
  # diffusion_models/); nothing when it isn't there
  local f="$1" alt=""
  if [ -f "$(dest_of "$f")" ]; then dest_of "$f"; return 0; fi
  case "$f" in
    text_encoders/*) alt="clip/${f#text_encoders/}" ;;
    diffusion_models/*) alt="unet/${f#diffusion_models/}" ;;
  esac
  if [ -n "$alt" ] && [ -f "$MODELS/comfyui/$alt" ]; then printf '%s' "$MODELS/comfyui/$alt"; fi
}
size() { wc -c <"$1" | tr -d ' '; }
present() {  # present REL BYTES: the file is there at its full size
  local p
  p="$(found "$1")"
  [ -n "$p" ] && [ "$(size "$p")" = "$2" ]
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
      if [ "${2:-}" = missing ] && present "$rel" "$bytes"; then continue; fi
      total=$((total + bytes))
    done
  fi
  printf '%s' "$total"
}
set_state() {  # "here", "missing", or "n of m files here", saying how many are cut short
  local s="$1" e have=0 short=0 count=0 set rel src sum bytes
  if [ "$s" = whisper ]; then
    if whisper_present; then echo "here"; else echo "missing"; fi
    return
  fi
  for e in "${FILES[@]}"; do
    IFS='|' read -r set rel src sum bytes <<<"$e"
    [ "$set" = "$s" ] || continue
    count=$((count + 1))
    if present "$rel" "$bytes"; then have=$((have + 1))
    elif [ -n "$(found "$rel")" ]; then short=$((short + 1)); fi
  done
  if [ "$short" -gt 0 ]; then echo "$have of $count here, $short cut short"
  elif [ "$have" = "$count" ]; then echo "here"
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

download() {  # download URL PART BYTES: into PART until it holds BYTES, carrying on after drops and stalls
  local url="$1" part="$2" bytes="$3" try=0 have code rc
  while :; do
    have=0
    [ -f "$part" ] && have="$(size "$part")"
    if [ "$have" -gt "$bytes" ]; then rm -f "$part"; have=0; fi   # longer than the file can be: start again
    [ "$have" = "$bytes" ] && return 0
    try=$((try + 1))
    [ "$try" -gt "$TRIES" ] && return 1
    if [ "$try" -gt 1 ]; then
      note "the connection dropped at $(gb "$have"); carrying on (try $try of $TRIES)"
      sleep $((try < 6 ? try * 5 : 30))
    fi
    # a stall (under 4 KB/s for a minute) counts as a drop, so a hung connection can't hold the download forever
    code="$(curl -fL -C - --connect-timeout 30 --speed-limit 4096 --speed-time 60 -w '%{http_code}' -o "$part" "$url")" \
      && rc=0 || rc=$?
    if [ "$rc" = 22 ] && [[ "$code" =~ ^(401|403|404)$ ]]; then
      warn "Hugging Face answered $code for $url"
      return 2
    fi
  done
}

fetch_file() {  # fetch_file REL SRC SHA BYTES
  local rel="$1" src="$2" want="$3" bytes="$4" dest p got
  dest="$(dest_of "$rel")"
  if present "$rel" "$bytes"; then
    if [ "$VERIFY" = 0 ]; then ok "$rel"; return 0; fi
    p="$(found "$rel")"
    if [ "$(sha "$p")" = "$want" ]; then ok "$rel (checked)"; return 0; fi
    warn "$rel doesn't match its published SHA-256; fetching it again"
    rm -f "$p"
  fi
  mkdir -p "$(dirname "$dest")"
  p="$(found "$rel")"
  if [ -n "$p" ]; then   # there, but cut short: carry on from it (the SHA-256 check below catches anything else)
    warn "$rel is $(gb "$(size "$p")") of $(gb "$bytes"): a download that stopped; fetching the rest"
    if [ ! -f "$dest.part" ] && [ "$(size "$p")" -lt "$bytes" ]; then mv "$p" "$dest.part"; else rm -f "$p"; fi
  fi
  info "$rel ($(gb "$bytes"))"
  local repo="${src%%/*}/$(cut -d/ -f2 <<<"$src")" path
  path="${src#"$repo"/}"
  local rc=0
  download "$HF/$repo/resolve/main/$path" "$dest.part" "$bytes" || rc=$?
  if [ "$rc" = 2 ]; then
    die "Hugging Face doesn't have $src any more; scripts/models.txt may need updating (a newer checkout of this repo)"
  elif [ "$rc" != 0 ]; then
    die "the download of $rel stopped at $(gb "$( [ -f "$dest.part" ] && size "$dest.part" || echo 0)") of $(gb "$bytes"); run this again to carry on from there"
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
VERIFY=0
if [ "$1" = --file ]; then   # one file of models.txt, by its folder in comfyui/
  [ -n "${2:-}" ] || die "--file needs a path from scripts/models.txt"
  have curl || die "curl is needed"
  for e in "${FILES[@]}"; do
    IFS='|' read -r set rel src sum bytes <<<"$e"
    if [ "$rel" = "$2" ]; then fetch_file "$rel" "$src" "$sum" "$bytes"; exit 0; fi
  done
  die "'$2' isn't in scripts/models.txt"
fi
want=()
for a in "$@"; do
  case "$a" in
    -h | --help) usage; exit 0 ;;
    --verify) VERIFY=1 ;;
    all) want+=("${SETS[@]}") ;;
    starter) want+=(songs pictures) ;;
    songs | pictures | video | ace | music3 | whisper) want+=("$a") ;;
    *) die "no set called '$a' (see scripts/models.sh --help)" ;;
  esac
done
[ ${#want[@]} -gt 0 ] || die "name the sets to download or check (scripts/models.sh --help)"
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
