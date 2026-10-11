#!/usr/bin/env bash
# For working on Sound / Vision from another computer: copy this checkout to the GPU machine and restart the app
# there. (On the GPU machine itself, scripts/install.sh is all you need.)
#
#   scripts/deploy.sh [--web] [--force]
#
# Where to: scripts/deploy.env (not in git), e.g.
#   HOST=192.168.1.100          ssh host of the GPU machine
#   ROOT=/srv/sv                the install there: ROOT/app (server), ROOT/web/dist, ROOT/sv.env (its settings)
#   UV=uv                       uv on that machine
#   COMFY_NODES=                optional: sv-comfy's custom_nodes folder there, to update our sv_nodes in it
#   ADDONS=                     optional: a folder of your own add-ons here, copied to ROOT/addons there (set
#                               SV_ADDONS=ROOT/addons in its sv.env to load them)
#
# The app's own settings (data folder, port, models…) are in ROOT/sv.env on that machine (see sv.env.example).
# A restart stops whatever job is running (a take half-sung is lost), so this refuses while any job is queued or
# running, unless --force.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f scripts/deploy.env ] || { echo "Say where to deploy in scripts/deploy.env (HOST=, ROOT=); see the top of this script." >&2; exit 2; }
# shellcheck disable=SC1091
. scripts/deploy.env
: "${HOST:?HOST is missing from scripts/deploy.env}" "${ROOT:?ROOT is missing from scripts/deploy.env}"
UV=${UV:-uv}
WEB=0 FORCE=0
for a in "$@"; do
  case "$a" in --web) WEB=1 ;; --force) FORCE=1 ;; *) echo "unknown option $a" >&2; exit 2 ;; esac
done
# run on the GPU machine with its settings loaded
there() { ssh "$HOST" "set -a; [ -f $ROOT/sv.env ] && . $ROOT/sv.env; set +a; SV_DATA=\${SV_DATA:-$ROOT/data}; SV_PORT=\${SV_PORT:-7660}; $1"; }
ask='curl -sf -H "Authorization: Bearer $(cat $SV_DATA/secrets/api-token)" http://127.0.0.1:$SV_PORT'

if [ "$FORCE" = 0 ] && ssh "$HOST" 'systemctl --user is-active -q sv-app'; then
  busy=$(there "$ask/api/jobs" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))' 2>/dev/null || echo "?")
  if [ "$busy" != "0" ]; then
    echo "sv-app has ${busy} job(s) queued or running (or didn't answer); deploy later, or pass --force." >&2
    exit 1
  fi
fi

if [ "$WEB" = 1 ]; then
  npm run build --prefix web
fi

there "mkdir -p $ROOT/app $ROOT/web/dist $ROOT/analysis/worker $ROOT/influence ~/.config/systemd/user && [ -f $ROOT/sv.env ] || cp /dev/null $ROOT/sv.env"
rsync -a --delete --exclude .venv --exclude __pycache__ --exclude .pytest_cache --exclude tests server/ "$HOST:$ROOT/app/"
rsync -a --delete --exclude __pycache__ infra/legion/analysis/worker/ "$HOST:$ROOT/analysis/worker/"
rsync -a --delete --exclude __pycache__ infra/legion/influence/ "$HOST:$ROOT/influence/"
there "mkdir -p \${SV_LORAS:-\${SV_MODELS:-$ROOT/models}/comfyui/loras}/soundandvision/yue2"
rsync -a infra/legion/influences/yue2/ "$HOST:$(there 'echo ${SV_LORAS:-${SV_MODELS:-'"$ROOT"'/models}/comfyui/loras}')/soundandvision/yue2/"
[ "$WEB" = 1 ] && rsync -a --delete web/dist/ "$HOST:$ROOT/web/dist/"
[ -n "${COMFY_NODES:-}" ] && rsync -a infra/legion/comfy/custom_nodes/sv_nodes/ "$HOST:$COMFY_NODES/sv_nodes/"
if [ -n "${ADDONS:-}" ]; then
  [ -d "$ADDONS" ] || { echo "ADDONS in scripts/deploy.env isn't a folder: $ADDONS" >&2; exit 2; }
  rsync -a --delete --exclude __pycache__ --exclude tests --exclude .git "$ADDONS/" "$HOST:$ROOT/addons/"
fi
sed -e "s|@SERVER@|$ROOT/app|g" -e "s|@ENV@|$ROOT/sv.env|g" infra/sv-app.service.in | ssh "$HOST" 'cat > ~/.config/systemd/user/sv-app.service'

ssh "$HOST" "cd $ROOT/app && UV_PYTHON=python3.12 $UV sync -q --no-dev && systemctl --user daemon-reload && systemctl --user enable -q sv-app && systemctl --user restart sv-app"
for _ in $(seq 1 30); do
  if there "$ask/api/health" >/dev/null 2>&1; then
    echo "sv-app is up on http://$HOST:$(there 'echo $SV_PORT')"
    exit 0
  fi
  sleep 1
done
echo "sv-app didn't come up; see: ssh $HOST journalctl --user -u sv-app -n 50" >&2
exit 1
