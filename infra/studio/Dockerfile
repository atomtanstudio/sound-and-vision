# The Claude studio: Anthropic's Claude Code CLI, installed from Anthropic's signed apt repository and never modified,
# plus what a film written in code needs to render itself: Chromium for headless frame capture (with the EGL loader, so
# it can draw on the machine's NVIDIA GPU when the container is given one), ffmpeg, Python with numpy for the analysis
# and QA tools, and the film kit (kit/ → /opt/kit): the engine, tools, CLAUDE.md and skills every film starts from, with
# its npm packages and fonts installed here, at build time, so nothing is downloaded while a film is made.
#
# Sound / Vision runs one container per film, mounting only that film's folder (/work) and, for Claude sessions, the
# studio's login folder (/studio/claude). The person who owns the machine signs in to that folder once with their own
# Claude subscription (studio.sh signin), through Anthropic's own login; the app never sees, relays or stores the login.
# No API key is set anywhere in this image, so nothing here can bill an API account.
#
# Build: studio.sh build   (passes your uid/gid, so the container's user owns the folders it's given)
FROM node:24-bookworm-slim

ARG CLAUDE_CHANNEL=latest
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl gnupg git ripgrep procps jq tini \
      chromium libegl1 libgles2 ffmpeg python3 python3-numpy python3-pil python3-venv \
      fonts-dejavu-core fonts-liberation fonts-noto-core fonts-noto-color-emoji \
 && install -d -m 0755 /etc/apt/keyrings \
 && curl -fsSL https://downloads.claude.ai/keys/claude-code.asc -o /etc/apt/keyrings/claude-code.asc \
 && gpg --show-keys --with-colons /etc/apt/keyrings/claude-code.asc | grep -q '^fpr:.*31DDDE24DDFAB679F42D7BD2BAA929FF1A7ECACE' \
 && echo "deb [signed-by=/etc/apt/keyrings/claude-code.asc] https://downloads.claude.ai/claude-code/apt/${CLAUDE_CHANNEL} ${CLAUDE_CHANNEL} main" \
      > /etc/apt/sources.list.d/claude-code.list \
 && apt-get update && apt-get install -y --no-install-recommends claude-code \
 && rm -rf /var/lib/apt/lists/*

# The container's user ("node") takes the uid/gid of the account that owns the mounted folders; studio.sh build passes
# them. The node image's own default is 1000:1000.
ARG STUDIO_UID=1000
ARG STUDIO_GID=1000
RUN if [ "$STUDIO_UID" != 1000 ] || [ "$STUDIO_GID" != 1000 ]; then \
      groupmod -o -g "$STUDIO_GID" node && usermod -o -u "$STUDIO_UID" -g "$STUDIO_GID" node && chown -R node:node /home/node; \
    fi \
 && mkdir -p /studio/claude /work && chown node:node /studio/claude /work

# Puppeteer drives the Chromium above; it never downloads a browser of its own.
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium \
    PUPPETEER_SKIP_DOWNLOAD=1 \
    CHROME_PATH=/usr/bin/chromium

# The film kit. Its npm packages (exact versions from package-lock.json) and its fonts (open-licensed faces fetched from
# the Google Fonts repository) are layers of their own, so changing the kit's code doesn't download them again. A film
# folder copies or links its node_modules and fonts from here.
COPY kit/package.json kit/package-lock.json /opt/kit/
RUN cd /opt/kit && npm ci --omit=dev --no-audit --no-fund && npm cache clean --force
COPY kit/build/fetch-fonts.mjs /opt/kit/build/
RUN node /opt/kit/build/fetch-fonts.mjs /opt/kit/fonts
COPY kit/ /opt/kit/
RUN chmod -R a+rX /opt/kit && chmod a+x /opt/kit/build/seed.sh && node /opt/kit/build/check-kit.mjs && rm -rf /tmp/* /root/.npm

# Claude Code keeps its login and settings in CLAUDE_CONFIG_DIR; updates come from rebuilding the image.
ENV CLAUDE_CONFIG_DIR=/studio/claude \
    DISABLE_AUTOUPDATER=1
USER node
WORKDIR /work
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["claude"]
