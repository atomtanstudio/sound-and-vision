# Legion visualizer renderer

The standalone service lives at `/srv/ai/sound-vision-renderer`, uses the existing Node runtime at `/srv/ai/sound-vision/bin/node`, and listens only on `127.0.0.1:5192`. Its user unit is `sound-vision-renderer.service`. It does not restart or reconfigure the music service. Jobs and finished videos persist under `data/renders/<id>` on Legion.

The editor uses `SOUND_VISION_RENDER_BACKEND_URL=http://127.0.0.1:5192`. `scripts/dev-connected.mjs` maintains the additional SSH forward using the existing `SOUND_VISION_SSH_HOST`. Until that setting is enabled, the original Mac renderer remains selected. The relay authenticates server-side with the existing Sound/Vision service token, retains Mac download history, and fails visibly if Legion is unreachable; it never silently submits new jobs to the Mac.

Build the standalone composition with:

```sh
node scripts/video/build-visualizer-renderer.mjs /path/to/release/dist-renderer
```

Deploy the built composition, `scripts/video/{visualizer-export-server,visualizer-export-api,visualizer-export-worker,visualizer-analyze}.mjs`, `src/video/visualizers/schedule.ts`, and the existing Playwright packages. The unit template is `deploy/sound-vision-renderer.service.in`. Browser executable paths are pinned to the installed Chromium; review them when upgrading it.

## Browser sandbox setup

Ubuntu restricts unprivileged user namespaces. Its installed Chrome profile applies only to `/opt/google/chrome/chrome`, so the Playwright browser currently requires the specific profile in `deploy/sound-vision-renderer.apparmor`. This enables Chromium's own sandbox for that executable while leaving the global restriction enabled. Install through an authorized administrator:

```sh
sudo install -m 644 /srv/ai/sound-vision-renderer/deploy/sound-vision-renderer.apparmor /etc/apparmor.d/sound-vision-renderer
sudo apparmor_parser -r /etc/apparmor.d/sound-vision-renderer
```

Do not disable Chromium sandboxing or change the global user-namespace policy. Syntax validation without applying it uses `apparmor_parser --skip-kernel-load --skip-cache FILE`.

## Hardware and verification

The worker explicitly enables Chromium's Vulkan GPU backend and requires an NVIDIA renderer string. This follows Chromium's [headless GPU guidance](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/gpu/using-gpu-hardware-in-headless-chrome.md). It records the actual GPU and encoder in each receipt. FFmpeg uses `h264_nvenc`, preset p5, CQ 18; audio remains AAC 256 kbps with the original timing. PNG frame capture uses the controlled render composition directly, avoiding interactive screenshot stabilization on every frame.

Before switching the editor, run a short clip with lyrics and all eight styles, inspect the output and receipt, verify the NVIDIA GPU, and compare measured render time. Test an authenticated API submission, progress, download/range requests, and cancellation. The Mac editor may close during a Legion job; restart the editor to recover its progress and download links. The SSH tunnel is needed for monitoring and downloads, not for the running render itself.

Run `npm run test:video` and `npm run build` locally. The relay test uses temporary loopback servers and covers remote submissions, legacy downloads, hostile origins, and an unavailable Legion connection.
