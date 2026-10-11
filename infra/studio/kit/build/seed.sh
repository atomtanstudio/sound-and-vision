#!/bin/sh
# Run inside the studio image by `studio.sh seed <folder>` (the folder is /work): copy the film kit into it without
# replacing anything that is already there. node_modules and fonts become links into /opt/kit, which exist only inside
# the studio's containers (the only place a film's tools run). The kit's README.md and build/ stay behind.
set -eu
cd /opt/kit
tar --anchored --exclude=./node_modules --exclude=./fonts --exclude=./build --exclude=./README.md -cf - . \
  | tar -C /work --skip-old-files -xf -
for d in node_modules fonts; do
  if [ ! -e "/work/$d" ] && [ ! -L "/work/$d" ]; then ln -s "/opt/kit/$d" "/work/$d"; fi
done
mkdir -p /work/song /work/analysis /work/plates /work/plan /work/out/review
[ -e /work/plates/index.json ] || echo '{"plates": []}' > /work/plates/index.json
echo "seeded $(ls -A /work | tr '\n' ' ')"
