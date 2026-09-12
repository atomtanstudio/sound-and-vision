// Local, durable render queue. Only the trusted app may submit work; audio
// comes from the configured music backend, never a URL supplied by a browser.
import {
  mkdirSync,
  readFileSync,
  writeFileSync,
  renameSync,
  readdirSync,
  statSync,
  createReadStream,
  createWriteStream,
} from "node:fs";
import { resolve, join } from "node:path";
import { randomBytes, createHash } from "node:crypto";
import { spawn, execFileSync } from "node:child_process";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { visualizerSchedule } from "../../src/video/visualizers/schedule.ts";

const ACTIVE = new Set(["queued", "running"]);
const takePattern = /^[a-f0-9]{32}$/;
const idPattern = /^[a-zA-Z0-9_-]{8,80}$/;
const enumValue = (value, values, label) => {
  if (!values.includes(value)) throw Error(`Invalid ${label}`);
  return value;
};
const number = (value, min, max, label) => {
  if (
    typeof value !== "number" ||
    !Number.isFinite(value) ||
    value < min ||
    value > max
  )
    throw Error(`Invalid ${label}`);
  return value;
};
export function validateExport(body) {
  if (
    !body ||
    !takePattern.test(body.takeId || "") ||
    !idPattern.test(body.requestId || "")
  )
    throw Error("Choose a saved, generated song before rendering.");
  const input = body.draft || {},
    draft = {};
  draft.aspect = enumValue(input.aspect, ["16:9", "9:16"], "aspect ratio");
  draft.visualizer = enumValue(
    input.visualizer,
    [
      "all",
      "waveform",
      "spectrum",
      "orbit",
      "0",
      "1",
      "2",
      "3",
      "4",
      "5",
      "6",
      "7",
    ],
    "visualizer",
  );
  draft.visualizerStrength = number(
    input.visualizerStrength,
    0.25,
    2,
    "response strength",
  );
  draft.shade = number(input.shade, 0, 100, "background shade");
  if (typeof input.showLyrics !== "boolean")
    throw Error("Invalid lyric option");
  draft.showLyrics = input.showLyrics;
  draft.font = enumValue(input.font, ["bold", "soft", "editorial"], "font");
  draft.textSize = number(input.textSize, 60, 150, "text size");
  draft.placement = enumValue(
    input.placement,
    ["center", "lower"],
    "text position",
  );
  draft.lyricMotion = enumValue(
    input.lyricMotion,
    ["auto", "pop", "slam", "rise", "highlight", "reveal", "calm"],
    "lyric motion",
  );
  draft.intensity = number(input.intensity, 0.5, 1.5, "motion strength");
  for (const field of ["textColor", "highlightColor"]) {
    if (!/^#[a-fA-F0-9]{6}$/.test(input[field] || ""))
      throw Error("Invalid text color");
    draft[field] = input[field];
  }
  const duration = number(body.duration, 1, 3600, "song duration");
  if (!Array.isArray(body.cues) || body.cues.length > 1500)
    throw Error("Invalid lyric timing");
  const cues = draft.showLyrics
    ? body.cues.map((cue) => {
        if (
          typeof cue.id !== "string" ||
          !/^line-\d+$/.test(cue.id) ||
          typeof cue.text !== "string" ||
          cue.text.length > 1500
        )
          throw Error("Invalid lyric line");
        const startFrame = number(
          cue.startFrame,
          0,
          Math.ceil(duration * 24),
          "lyric start",
        );
        const endFrame = number(
          cue.endFrame,
          startFrame + 1,
          Math.ceil(duration * 24) + 1,
          "lyric end",
        );
        if (!Number.isInteger(startFrame) || !Number.isInteger(endFrame))
          throw Error("Lyric frames must be integers");
        if (
          !Array.isArray(cue.words) ||
          cue.words.length !== cue.text.split(/\s+/).length
        )
          throw Error("Align every lyric word before rendering.");
        const words = cue.words.map((word) => {
          if (typeof word.text !== "string" || word.text.length > 200)
            throw Error("Invalid lyric word");
          const start = number(word.start, 0, duration, "word start");
          const end = number(
            word.end,
            start + 0.001,
            duration + 0.05,
            "word end",
          );
          return { text: word.text, start, end, review: null };
        });
        if (words.some((w, i) => i && w.start < words[i - 1].start))
          throw Error("Lyric words must follow their vocal order.");
        return { id: cue.id, text: cue.text, startFrame, endFrame, words };
      })
    : [];
  if (cues.some((cue, i) => i && cue.startFrame < cues[i - 1].endFrame))
    throw Error("Fix overlapping lyric lines before rendering.");
  if (
    draft.showLyrics &&
    typeof input.lyrics === "string" &&
    input.lyrics.trim() &&
    !cues.length
  )
    throw Error(
      "Align lyrics first, or turn off Show lyrics to render just the visualizer.",
    );
  return {
    requestId: body.requestId,
    takeId: body.takeId,
    duration,
    draft,
    cues,
  };
}
export function trustedLocalRequest(req) {
  return (
    /^(localhost|127\.0\.0\.1):5190$/.test(req.headers.host || "") &&
    (!req.headers.origin ||
      ["http://localhost:5190", "http://127.0.0.1:5190"].includes(
        req.headers.origin,
      )) &&
    !["cross-site", "same-site"].includes(req.headers["sec-fetch-site"])
  );
}
export function byteRange(header, size) {
  if (!header) return { start: 0, end: size - 1, partial: false };
  const match = /^bytes=(\d*)-(\d*)$/.exec(header);
  if (!match || (!match[1] && !match[2])) return null;
  const start = match[1]
    ? Number(match[1])
    : Math.max(0, size - Number(match[2]));
  const end = match[1]
    ? match[2]
      ? Math.min(size - 1, Number(match[2]))
      : size - 1
    : size - 1;
  return Number.isSafeInteger(start) &&
    Number.isSafeInteger(end) &&
    start <= end &&
    start < size
    ? { start, end, partial: true }
    : null;
}
function atomic(path, value) {
  writeFileSync(path + ".tmp", JSON.stringify(value, null, 2));
  renameSync(path + ".tmp", path);
}
async function jsonBody(req) {
  if (!/^application\/json(?:;|$)/.test(req.headers["content-type"] || ""))
    throw Error("Use a JSON request");
  let size = 0;
  const parts = [];
  for await (const part of req) {
    size += part.length;
    if (size > 2 * 1024 ** 2) throw Error("Render settings are too large");
    parts.push(part);
  }
  return JSON.parse(Buffer.concat(parts).toString());
}

export function createVisualizerExports({
  projectRoot,
  backend,
  token,
  renderOrigin = "http://127.0.0.1:5190",
  renderHost = "Mac",
  outputRoot = resolve(projectRoot, "../output/visualizer-renders"),
  workerPath = resolve(
    projectRoot,
    "scripts/video/visualizer-export-worker.mjs",
  ),
}) {
  mkdirSync(outputRoot, { recursive: true });
  const jobs = new Map();
  let current = null,
    closed = false;
  const workFor = (id) => join(outputRoot, id);
  const save = (job) => atomic(join(workFor(job.id), "job.json"), job);
  for (const id of readdirSync(outputRoot).filter((id) =>
    takePattern.test(id),
  )) {
    try {
      const job = JSON.parse(
        readFileSync(join(workFor(id), "job.json"), "utf8"),
      );
      if (job.id !== id) continue;
      if (job.state === "running") {
        job.state = "failed";
        job.phase = "Render interrupted";
        job.error =
          "The local server restarted. Start a new render; the previous files are retained.";
        save(job);
      }
      jobs.set(id, job);
    } catch {
      /* Incomplete non-published folders are retained for inspection. */
    }
  }
  const pending = () =>
    [...jobs.values()]
      .filter((j) => ACTIVE.has(j.state))
      .sort((a, b) => a.created - b.created);
  const publicJob = (job) => ({
    renderHost,
    id: job.id,
    takeId: job.input.takeId,
    title: job.title,
    state: job.state,
    phase: job.phase,
    error: job.error,
    created: job.created,
    updated: job.updated,
    frames: job.frames || 0,
    totalFrames: job.totalFrames || 0,
    framesPerSecond:
      job.elapsedSeconds > 0 && job.frames > 0
        ? job.frames / job.elapsedSeconds
        : null,
    remainingSeconds:
      job.elapsedSeconds > 0 && job.frames > 0
        ? Math.max(
            0,
            ((job.totalFrames - job.frames) * job.elapsedSeconds) / job.frames,
          )
        : null,
    queuePosition: ACTIVE.has(job.state)
      ? pending().findIndex((j) => j.id === job.id) + 1
      : null,
    selection: job.input.draft.visualizer,
    aspect: job.input.draft.aspect,
    lyrics: job.input.draft.showLyrics,
    downloadUrl:
      job.state === "succeeded"
        ? `/local-api/visualizer-renders/${job.id}/video?download=1`
        : null,
    videoUrl:
      job.state === "succeeded"
        ? `/local-api/visualizer-renders/${job.id}/video`
        : null,
    duration: job.duration || job.input.duration,
    bytes: job.bytes || 0,
  });
  const update = (job, data) => {
    Object.assign(job, data, { updated: Date.now() });
    save(job);
  };
  async function remote(path, signal) {
    if (!backend || !token)
      throw Error("Connect the music backend before rendering.");
    const response = await fetch(new URL(path, backend), {
      headers: { Authorization: `Bearer ${token}` },
      signal,
    });
    if (!response.ok)
      throw Error(
        `Music backend returned ${response.status}. Confirm the song is ready and retry.`,
      );
    return response;
  }
  async function run(job) {
    const work = workFor(job.id),
      abort = new AbortController();
    current = { job, abort, child: null };
    update(job, {
      state: "running",
      phase: "Preparing original soundtrack",
      error: null,
    });
    try {
      const signal = AbortSignal.any([
        abort.signal,
        AbortSignal.timeout(120000),
      ]);
      const library = await (await remote("/api/library", signal)).json();
      const track = library.tracks.find(
        (t) => t.id === job.input.takeId && t.status === "succeeded",
      );
      if (!track)
        throw Error("The song must finish generating before video rendering.");
      update(job, { title: track.title });
      const response = await remote(
        `/api/takes/${job.input.takeId}/files/audio.flac`,
        signal,
      );
      let bytes = 0;
      async function* limited(source) {
        for await (const part of source) {
          bytes += part.length;
          if (bytes > 512 * 1024 ** 2)
            throw Error("Audio exceeds the 512 MB export limit");
          yield part;
        }
      }
      await pipeline(
        Readable.fromWeb(response.body),
        limited,
        createWriteStream(join(work, "audio.flac")),
        { signal },
      );
      const info = JSON.parse(
        execFileSync(
          "ffprobe",
          [
            "-v",
            "error",
            "-show_format",
            "-of",
            "json",
            join(work, "audio.flac"),
          ],
          { encoding: "utf8", timeout: 15000 },
        ),
      );
      const duration = number(
        Number(info.format.duration),
        1,
        3600,
        "recording duration",
      );
      if (Math.abs(duration - job.input.duration) > 0.25)
        throw Error(
          "The recording duration changed. Refresh the song and render again.",
        );
      const width = job.input.draft.aspect === "9:16" ? 1080 : 1920,
        height = job.input.draft.aspect === "9:16" ? 1920 : 1080;
      atomic(join(work, "config.json"), {
        ...job.input,
        title: job.title,
        duration,
        width,
        height,
        schedule: visualizerSchedule(duration, job.input.draft.visualizer),
      });
      update(job, {
        phase: "Analyzing the song",
        duration,
        totalFrames: Math.ceil(duration * 24),
      });
      if (abort.signal.aborted) throw Error("Cancelled");
      const child = spawn(
        process.execPath,
        [workerPath, work, renderOrigin, job.id],
        { cwd: projectRoot, detached: true, stdio: ["ignore", "pipe", "pipe"] },
      );
      current.child = child;
      const log = createWriteStream(join(work, "worker.log"), { flags: "a" });
      child.stdout.pipe(log, { end: false });
      child.stderr.pipe(log, { end: false });
      const timer = setInterval(() => {
        try {
          const progress = JSON.parse(
            readFileSync(join(work, "progress.json"), "utf8"),
          );
          if (job.state === "running") update(job, progress);
        } catch {}
      }, 1000);
      try {
        await new Promise((res, rej) => {
          child.once("error", rej);
          child.once("close", (code) => {
            if (code === 0) return res();
            let message = `Render stopped (${code ?? "signal"}). Start a new render to retry.`;
            try {
              message = JSON.parse(
                readFileSync(join(work, "failure.json"), "utf8"),
              ).message;
            } catch {}
            rej(Error(message));
          });
        });
      } finally {
        clearInterval(timer);
        log.end();
      }
      if (abort.signal.aborted) throw Error("Cancelled");
      const receipt = JSON.parse(
        readFileSync(join(work, "receipt.json"), "utf8"),
      );
      update(job, {
        state: "succeeded",
        phase: "MP4 ready",
        frames: receipt.frames,
        bytes: statSync(join(work, "video.mp4")).size,
      });
    } catch (error) {
      update(job, {
        state: abort.signal.aborted && !closed ? "cancelled" : "failed",
        phase: closed
          ? "Render interrupted"
          : abort.signal.aborted
            ? "Cancelled"
            : "Render needs attention",
        error: abort.signal.aborted
          ? closed
            ? "The local server stopped. Start a new render; files are retained."
            : null
          : String(error.message || error),
      });
    } finally {
      current = null;
      void pump();
    }
  }
  async function pump() {
    if (closed || current) return;
    const next = pending().find((j) => j.state === "queued");
    if (next) await run(next);
  }
  const cancel = () => {
    if (!current) return;
    current.abort.abort();
    if (current.child) {
      try {
        process.kill(-current.child.pid, "SIGTERM");
      } catch {}
    }
  };
  function close() {
    closed = true;
    cancel();
  }
  const send = (res, status, data) => {
    res.statusCode = status;
    res.setHeader("Content-Type", "application/json");
    res.setHeader("Cache-Control", "no-store");
    res.end(JSON.stringify(data));
  };
  async function middleware(req, res, next) {
    const url = new URL(req.url, "http://127.0.0.1:5190");
    if (!url.pathname.startsWith("/local-api/visualizer-renders"))
      return next();
    if (!trustedLocalRequest(req))
      return send(res, 403, { detail: "Forbidden" });
    try {
      const parts = url.pathname.split("/").filter(Boolean),
        id = parts[2],
        operation = parts[3];
      if (!id && req.method === "GET") {
        const takeId = url.searchParams.get("takeId");
        if (takeId && !takePattern.test(takeId))
          return send(res, 400, { detail: "Invalid take" });
        return send(res, 200, {
          available: !!backend,
          renderer: renderHost,
          jobs: [...jobs.values()]
            .filter((j) => !takeId || j.input.takeId === takeId)
            .sort((a, b) => b.created - a.created)
            .map(publicJob),
        });
      }
      if (!id && req.method === "POST") {
        const input = validateExport(await jsonBody(req));
        const signature = createHash("sha256")
          .update(JSON.stringify({ ...input, requestId: undefined }))
          .digest("hex");
        const previous = [...jobs.values()].find(
          (j) =>
            j.input.requestId === input.requestId ||
            (ACTIVE.has(j.state) && j.signature === signature),
        );
        if (previous)
          return send(
            res,
            previous.signature === signature ? 200 : 409,
            previous.signature === signature
              ? publicJob(previous)
              : {
                  detail:
                    "This request ID already belongs to different settings.",
                },
          );
        if (!backend)
          return send(res, 503, { detail: "Music backend not connected" });
        const id = randomBytes(16).toString("hex"),
          created = Date.now();
        mkdirSync(workFor(id));
        const job = {
          id,
          input,
          signature,
          created,
          updated: created,
          title: "Visualizer video",
          state: "queued",
          phase: "Queued for local rendering",
          error: null,
        };
        jobs.set(id, job);
        save(job);
        send(res, 202, publicJob(job));
        void pump();
        return;
      }
      const job = takePattern.test(id || "") && jobs.get(id);
      if (!job) return send(res, 404, { detail: "Render not found" });
      if (operation === "cancel" && req.method === "POST") {
        if (!ACTIVE.has(job.state))
          return send(res, 409, { detail: "This render has already finished" });
        if (current?.job.id === id) cancel();
        else
          update(job, { state: "cancelled", phase: "Cancelled", error: null });
        return send(res, 200, publicJob(job));
      }
      if (operation === "video" && ["GET", "HEAD"].includes(req.method)) {
        if (job.state !== "succeeded")
          return send(res, 409, { detail: "The video is not ready yet" });
        const file = join(workFor(id), "video.mp4"),
          size = statSync(file).size,
          range = byteRange(req.headers.range, size);
        res.setHeader("Accept-Ranges", "bytes");
        res.setHeader("Content-Type", "video/mp4");
        if (!range) {
          res.setHeader("Content-Range", `bytes */${size}`);
          res.statusCode = 416;
          return res.end();
        }
        const { start, end, partial } = range;
        res.statusCode = partial ? 206 : 200;
        res.setHeader("Content-Length", end - start + 1);
        if (partial)
          res.setHeader("Content-Range", `bytes ${start}-${end}/${size}`);
        if (url.searchParams.has("download"))
          res.setHeader(
            "Content-Disposition",
            `attachment; filename="${String(job.title)
              .replace(/[^a-z0-9]+/gi, "-")
              .slice(0, 90)}-visualizer.mp4"`,
          );
        if (req.method === "HEAD") return res.end();
        const stream = createReadStream(file, { start, end });
        stream.on("error", () => res.destroy());
        res.on("close", () => stream.destroy());
        return stream.pipe(res);
      }
      return send(res, 405, { detail: "Unsupported render operation" });
    } catch (error) {
      if (!res.headersSent)
        send(res, 400, { detail: String(error.message || error) });
      else res.destroy();
    }
  }
  return {
    middleware,
    start: pump,
    close,
    has: (id) => jobs.has(id),
    list: (takeId) =>
      [...jobs.values()]
        .filter((j) => !takeId || j.input.takeId === takeId)
        .map(publicJob),
  };
}
