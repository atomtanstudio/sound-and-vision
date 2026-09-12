// Purpose-built offline video renderer. It uses the editor's actual WebGL and
// lyric components in an isolated headless browser, never the user's open tab.
import { chromium } from "@playwright/test";
import {
  readFileSync,
  writeFileSync,
  renameSync,
  existsSync,
  readdirSync,
  statSync,
  mkdirSync,
} from "node:fs";
import { resolve, join } from "node:path";
import { homedir } from "node:os";
import { spawn, execFileSync } from "node:child_process";
import { once } from "node:events";
const [work, origin, id] = process.argv.slice(2);
if (
  !work ||
  !/^http:\/\/(localhost|127\.0\.0\.1):519[02]$/.test(origin) ||
  !/^[a-f0-9]{32}$/.test(id)
)
  throw Error("Invalid local renderer invocation");
const config = JSON.parse(readFileSync(join(work, "config.json"), "utf8"));
const totalFrames = Math.ceil(config.duration * 24);
const began = Date.now();
function progress(phase, frames = 0) {
  const p = join(work, "progress.json");
  writeFileSync(
    p + ".tmp",
    JSON.stringify({
      phase,
      frames,
      totalFrames,
      elapsedSeconds: (Date.now() - began) / 1000,
    }),
  );
  renameSync(p + ".tmp", p);
}
let browser,
  encoder,
  analyzer,
  stopping = false;
let gpuRenderer = null;
const useNvenc = process.env.SOUND_VISION_VIDEO_ENCODER === "h264_nvenc";
const stop = async () => {
  if (stopping) return;
  stopping = true;
  analyzer?.kill("SIGTERM");
  encoder?.kill("SIGTERM");
  await browser?.close().catch(() => {});
};
process.on("SIGTERM", () => {
  void stop().finally(() => process.exit(130));
});
process.on("SIGINT", () => {
  void stop().finally(() => process.exit(130));
});
function launchPath() {
  const provided = process.env.PLAYWRIGHT_EXECUTABLE_PATH;
  if (provided) return provided;
  if (existsSync(chromium.executablePath())) return undefined;
  const base = join(homedir(), "Library/Caches/ms-playwright");
  if (existsSync(base))
    for (const dir of readdirSync(base)
      .filter((n) => /^chromium_headless_shell-\d+$/.test(n))
      .sort()
      .reverse()) {
      for (const arch of ["arm64", "x64"]) {
        const p = join(
          base,
          dir,
          `chrome-headless-shell-mac-${arch}/chrome-headless-shell`,
        );
        if (existsSync(p)) return p;
      }
    }
  throw Error(
    "The local render browser is missing. Install it with npx playwright install chromium, then retry.",
  );
}
try {
  progress("Analyzing the song");
  analyzer = spawn(
    process.execPath,
    [
      resolve("scripts/video/visualizer-analyze.mjs"),
      "--audio",
      join(work, "audio.flac"),
      "--output",
      join(work, "analysis.json"),
      "--fps",
      "24",
    ],
    { stdio: ["ignore", "inherit", "inherit"] },
  );
  const [analyzed] = await once(analyzer, "close");
  if (analyzed !== 0) throw Error("Audio analysis failed");
  const partial = join(work, "video.partial.mp4");
  const native = process.platform === "darwin" && !config.draft.showLyrics;
  if (native) {
    progress("Preparing accelerated rendering");
    analyzer = spawn(
      process.execPath,
      [
        resolve("scripts/video/visualizer-render.mjs"),
        "--analysis",
        join(work, "analysis.json"),
        "--audio",
        join(work, "audio.flac"),
        "--output",
        partial,
        "--width",
        String(config.width),
        "--height",
        String(config.height),
        "--duration",
        String(config.duration),
        "--visualizer",
        config.draft.visualizer,
        "--strength",
        String(config.draft.visualizerStrength),
        "--shade",
        String(config.draft.shade),
        "--progress",
        join(work, "progress.json"),
      ],
      { stdio: ["ignore", "inherit", "inherit"] },
    );
    const [code] = await once(analyzer, "close");
    if (code !== 0)
      throw Error(
        "Accelerated visualizer rendering failed; worker log retained.",
      );
  } else {
    progress("Preparing the visualizer");
    browser = await chromium.launch({
      headless: true,
      chromiumSandbox: process.platform === "linux",
      executablePath: launchPath(),
      args:
        process.platform === "darwin"
          ? ["--use-gl=angle", "--use-angle=metal"]
          : [
              "--enable-gpu",
              "--use-angle=vulkan",
              "--use-gl=angle",
            ],
    });
    const analysis = JSON.parse(
      readFileSync(join(work, "analysis.json"), "utf8"),
    );
    let pageError = null;
    const pages = await Promise.all(
      Array.from({ length: 4 }, async () => {
        const page = await browser.newPage({
          viewport: { width: config.width, height: config.height },
          deviceScaleFactor: 1,
        });
        // Each isolated page can seek any frame; the encoder still receives them in order.
        await page.addInitScript(
          ({ config, analysis }) => {
            window.visualizerRenderInput = { config, analysis };
          },
          { config, analysis },
        );
        page.on("pageerror", (error) => {
          pageError = error;
        });
        await page.goto(`${origin}/visualizer-render.html`, {
          waitUntil: "networkidle",
          timeout: 60000,
        });
        await page.waitForFunction(
          () => window.visualizerRenderReady || window.visualizerRenderError,
          undefined,
          { timeout: 60000 },
        );
        const error = await page.evaluate(() => window.visualizerRenderError);
        if (error) throw Error(error);
        return page;
      }),
    );
    gpuRenderer = await pages[0].evaluate(() => {
      const gl = document.querySelector("canvas").getContext("webgl2");
      const info = gl.getExtension("WEBGL_debug_renderer_info");
      return info
        ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL)
        : gl.getParameter(gl.RENDERER);
    });
    console.log(`Visualizer GPU: ${gpuRenderer}`);
    if (
      process.env.SOUND_VISION_REQUIRE_GPU === "1" &&
      !/NVIDIA/i.test(gpuRenderer)
    )
      throw Error(
        `Hardware rendering required, but Chromium selected ${gpuRenderer}`,
      );
    const captures = await Promise.all(
      pages.map((page) => page.context().newCDPSession(page)),
    );
    encoder = spawn(
      "ffmpeg",
      [
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "image2pipe",
        "-vcodec",
        "png",
        "-framerate",
        "24",
        "-i",
        "pipe:0",
        "-i",
        join(work, "audio.flac"),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        useNvenc ? "h264_nvenc" : "libx264",
        "-preset",
        useNvenc ? "p5" : "fast",
        useNvenc ? "-cq" : "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-threads",
        "4",
        "-c:a",
        "aac",
        "-b:a",
        "256k",
        "-af",
        `atrim=duration=${config.duration}`,
        "-frames:v",
        String(totalFrames),
        "-movflags",
        "+faststart",
        partial,
      ],
      { stdio: ["pipe", "ignore", "inherit"] },
    );
    let encodeError = null;
    encoder.stdin.on("error", (error) => {
      encodeError = error;
    });
    encoder.on("error", (error) => {
      encodeError = error;
    });
    const finished = once(encoder, "close");
    mkdirSync(join(work, "proof"), { recursive: true });
    const proofFrames = new Set(
      config.schedule.map((s) =>
        Math.min(totalFrames - 1, Math.floor((s.startFrame + s.endFrame) / 2)),
      ),
    );
    for (let first = 0; first < totalFrames; first += pages.length) {
      if (pageError || encodeError) throw pageError || encodeError;
      const images = await Promise.all(
        pages
          .slice(0, Math.min(pages.length, totalFrames - first))
          .map(async (page, offset) => {
            const frame = first + offset;
            await page.evaluate((frame) => {
              window.renderVisualizerFrame(frame);
              if (window.visualizerRenderError)
                throw Error(window.visualizerRenderError);
            }, frame);
            // Frame state and fonts are already controlled by this composition.
            // Avoid editor-style screenshot stabilization on every video frame.
            const shot = await captures[offset].send("Page.captureScreenshot", {
              format: "png",
              captureBeyondViewport: false,
              optimizeForSpeed: true,
            });
            return Buffer.from(shot.data, "base64");
          }),
      );
      for (const [offset, png] of images.entries()) {
        if (proofFrames.has(first + offset))
          writeFileSync(join(work, "proof", `${first + offset}.png`), png);
        if (!encoder.stdin.write(png)) await once(encoder.stdin, "drain");
      }
      progress("Rendering video", first + images.length);
    }
    progress("Finishing MP4", totalFrames);
    encoder.stdin.end();
    const [code] = await finished;
    if (code !== 0) throw Error("MP4 encoder failed");
  }
  const media = JSON.parse(
    execFileSync(
      "ffprobe",
      ["-v", "error", "-show_streams", "-show_format", "-of", "json", partial],
      { encoding: "utf8" },
    ),
  );
  const v = media.streams.find((s) => s.codec_type === "video"),
    a = media.streams.find((s) => s.codec_type === "audio");
  if (
    !v ||
    !a ||
    Number(v.nb_frames) !== totalFrames ||
    v.width !== config.width ||
    v.height !== config.height ||
    Math.abs(Number(media.format.duration) - config.duration) > 1 / 24 + 0.01 ||
    Math.abs(Number(a.duration) - config.duration) > 0.05
  )
    throw Error("Export failed duration, audio, or frame verification");
  renameSync(partial, join(work, "video.mp4"));
  writeFileSync(
    join(work, "receipt.json"),
    JSON.stringify(
      {
        width: v.width,
        height: v.height,
        fps: 24,
        frames: totalFrames,
        duration: Number(media.format.duration),
        audioDuration: Number(a.duration),
        audioChannels: a.channels,
        bytes: statSync(join(work, "video.mp4")).size,
        schedule: config.schedule,
        selection: config.draft.visualizer,
        lyrics: config.draft.showLyrics,
        strength: config.draft.visualizerStrength,
        renderSeconds: (Date.now() - began) / 1000,
        renderer: native ? "native-opengl" : "browser-webgl",
        gpuRenderer,
        encoder: useNvenc && !native ? "h264_nvenc" : "libx264",
      },
      null,
      2,
    ),
  );
  progress("MP4 ready", totalFrames);
} catch (error) {
  writeFileSync(
    join(work, "failure.json"),
    JSON.stringify({ message: String(error.message || error) }),
  );
  throw error;
} finally {
  await stop();
}
