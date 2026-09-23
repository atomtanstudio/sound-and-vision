// Durable full-song renderer for the granular Kinetic lyric editor.
// The browser owns the draft and IndexedDB media; this service owns only a
// copy of the selected assets and the rendered MP4. It never accepts source
// paths, shell commands, or audio URLs from the browser.
import {
  createReadStream,
  createWriteStream,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  renameSync,
  statSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { randomBytes, createHash } from "node:crypto";
import { resolve, join } from "node:path";
import { spawn, execFileSync } from "node:child_process";
import { Readable, Transform } from "node:stream";
import { pipeline } from "node:stream/promises";

const ACTIVE = new Set(["queued", "running"]);
const takePattern = /^[a-f0-9]{32}$/;
const idPattern = /^[a-zA-Z0-9_-]{8,80}$/;
const kindValues = ["images", "motion"];
const transitionValues = ["dissolve", "cut"];
const motionValues = [
  "auto",
  "pop",
  "slam",
  "rise",
  "highlight",
  "reveal",
  "calm",
];
const fontValues = ["bold", "soft", "editorial"];
const placementValues = ["center", "lower"];
const FPS = 24;

function finite(value, min, max, label) {
  if (
    typeof value !== "number" ||
    !Number.isFinite(value) ||
    value < min ||
    value > max
  )
    throw Error(`Invalid ${label}`);
  return value;
}

function integer(value, min, max, label) {
  const result = finite(value, min, max, label);
  if (!Number.isInteger(result)) throw Error(`${label} must be an integer`);
  return result;
}

function enumValue(value, values, label) {
  if (!values.includes(value)) throw Error(`Invalid ${label}`);
  return value;
}

function normalizeFade(value, duration) {
  if (value == null) return null;
  if (typeof value !== "object") throw Error("Invalid audio fade");
  const start = finite(value.start, 0, duration, "fade start");
  const end = finite(value.end, 0, duration, "fade end");
  if (end <= start || end - start < 0.25) throw Error("Invalid audio fade");
  return { start, end, curve: value.curve === "linear" ? "linear" : "smooth" };
}

export function kineticPlacements(duration, draft) {
  const total = Math.ceil(duration * FPS);
  if (!total) return [];
  if (draft.background === "images") {
    const count = Math.max(
      1,
      Math.min(total, Math.round(draft.imageCount * draft.imageCycles)),
    );
    return Array.from({ length: count }, (_, index) => ({
      assetIndex: index % draft.imageCount,
      startFrame: Math.round((index * total) / count),
      endFrame: Math.round(((index + 1) * total) / count),
    }));
  }
  const clipFrames = Math.max(1, Math.round(draft.clipSeconds * FPS));
  return Array.from({ length: Math.ceil(total / clipFrames) }, (_, index) => ({
    assetIndex: index % draft.clipCount,
    startFrame: index * clipFrames,
    endFrame: Math.min(total, (index + 1) * clipFrames),
  }));
}

function validateCue(cue, duration) {
  if (
    !cue ||
    typeof cue.id !== "string" ||
    !/^line-\d+$/.test(cue.id) ||
    typeof cue.text !== "string" ||
    cue.text.length > 1500 ||
    !Array.isArray(cue.words) ||
    cue.words.length !== cue.text.trim().split(/\s+/).filter(Boolean).length
  )
    throw Error("Invalid lyric timing");
  const startFrame = integer(
    cue.startFrame,
    0,
    Math.ceil(duration * FPS),
    "lyric start",
  );
  const endFrame = integer(
    cue.endFrame,
    startFrame + 1,
    Math.ceil(duration * FPS) + 1,
    "lyric end",
  );
  const words = cue.words.map((word) => {
    if (!word || typeof word.text !== "string" || word.text.length > 200)
      throw Error("Invalid lyric word");
    const start = finite(word.start, 0, duration, "word start");
    const end = finite(word.end, start + 0.001, duration + 0.05, "word end");
    return { text: word.text, start, end, review: null };
  });
  if (words.some((word, index) => index && word.start < words[index - 1].start))
    throw Error("Lyric words must follow their vocal order.");
  return { id: cue.id, text: cue.text, startFrame, endFrame, words };
}

function stagedAssetPath(stage, kind, slot) {
  return join(stage, "assets", `${kind}-${slot}.bin`);
}

function assetKey(kind, slot) {
  return `${kind}:${slot}`;
}

function validateAssetMetadata(assets, draft) {
  if (!Array.isArray(assets) || assets.length > 100)
    throw Error("Invalid background assets");
  const max = draft.background === "images" ? draft.imageCount : draft.clipCount;
  const seen = new Set();
  const normalized = assets.map((asset) => {
    if (!asset || !kindValues.includes(asset.kind))
      throw Error("Invalid background asset kind");
    const slot = integer(asset.slot, 0, max - 1, "background slot");
    const key = assetKey(asset.kind, slot);
    if (asset.kind !== draft.background || seen.has(key))
      throw Error("Background assets do not match this draft");
    seen.add(key);
    return {
      kind: asset.kind,
      slot,
      name: typeof asset.name === "string" ? asset.name.slice(0, 240) : "Background",
    };
  });
  for (let slot = 0; slot < max; slot++) {
    if (!seen.has(assetKey(draft.background, slot)))
      throw Error(`Add background ${slot + 1} before rendering the video.`);
  }
  return normalized;
}

export function validateKineticExport(body, stage) {
  if (
    !body ||
    !takePattern.test(body.takeId || "") ||
    !idPattern.test(body.requestId || "")
  )
    throw Error("Choose a saved, generated song before rendering.");
  const input = body.draft || {};
  const draft = {
    aspect: enumValue(input.aspect, ["16:9", "9:16"], "aspect ratio"),
    background: enumValue(input.background, kindValues, "background kind"),
    imageCount: integer(input.imageCount, 1, 100, "image count"),
    imageCycles: integer(input.imageCycles, 1, 8, "image repetitions"),
    clipCount: integer(input.clipCount, 1, 24, "clip count"),
    clipSeconds: finite(input.clipSeconds, 4, 15, "clip length"),
    pan: Boolean(input.pan),
    transition: enumValue(input.transition, transitionValues, "transition"),
    shade: finite(input.shade, 0, 85, "background shade"),
    font: enumValue(input.font, fontValues, "font"),
    textSize: finite(input.textSize, 60, 150, "text size"),
    placement: enumValue(input.placement, placementValues, "text position"),
    lyricMotion: enumValue(input.lyricMotion, motionValues, "lyric motion"),
    intensity: finite(input.intensity, 0.5, 1.5, "motion strength"),
    textColor: input.textColor,
    highlightColor: input.highlightColor,
    lyrics: typeof input.lyrics === "string" ? input.lyrics.slice(0, 30000) : "",
    language:
      typeof input.language === "string" && /^[a-z]{2,3}$/.test(input.language)
        ? input.language
        : "en",
    audioFade: null,
  };
  for (const field of ["textColor", "highlightColor"])
    if (!/^#[a-fA-F0-9]{6}$/.test(draft[field] || ""))
      throw Error("Invalid text color");
  const duration = finite(body.duration, 1, 3600, "song duration");
  draft.audioFade = normalizeFade(input.audioFade, duration);
  if (!Array.isArray(body.cues) || body.cues.length > 1500)
    throw Error("Invalid lyric timing");
  const cues = body.cues.map((cue) => validateCue(cue, duration));
  if (cues.some((cue, index) => index && cue.startFrame < cues[index - 1].endFrame))
    throw Error("Fix overlapping lyric lines before rendering.");
  if (draft.lyrics.trim() && cues.some((cue) => cue.words.length === 0))
    throw Error("Align lyrics before rendering.");
  const assets = validateAssetMetadata(body.assets, draft);
  for (const asset of assets) {
    if (!existsSync(stagedAssetPath(stage, asset.kind, asset.slot)))
      throw Error(`Background ${asset.slot + 1} has not finished uploading.`);
  }
  return {
    requestId: body.requestId,
    takeId: body.takeId,
    title: typeof body.title === "string" ? body.title.slice(0, 240) : "Kinetic lyric video",
    duration,
    draft,
    cues,
    assets,
    placements: kineticPlacements(duration, draft),
  };
}

function atomic(path, value) {
  writeFileSync(`${path}.tmp`, JSON.stringify(value, null, 2));
  renameSync(`${path}.tmp`, path);
}

function trustedLocalRequest(req, options = {}) {
  const allowedHosts = new Set(
    options.allowedHosts || ["localhost:5190", "127.0.0.1:5190"],
  );
  const allowedOrigins = new Set(
    options.allowedOrigins || [
      "http://localhost:5190",
      "http://127.0.0.1:5190",
    ],
  );
  return (
    allowedHosts.has(req.headers.host || "") &&
    (!req.headers.origin ||
      allowedOrigins.has(req.headers.origin)) &&
    !["cross-site", "same-site"].includes(req.headers["sec-fetch-site"])
  );
}

function byteRange(header, size) {
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

async function writeUpload(req, target, limit) {
  let bytes = 0;
  const limiter = new Transform({
    transform(chunk, encoding, callback) {
      bytes += chunk.length;
      if (bytes > limit) {
        callback(Error(`Background asset exceeds the ${Math.round(limit / 1024 ** 2)} MB limit.`));
        return;
      }
      callback(null, chunk);
    },
  });
  const temporary = `${target}.tmp-${randomBytes(6).toString("hex")}`;
  try {
    await pipeline(req, limiter, createWriteStream(temporary, { mode: 0o600 }));
    renameSync(temporary, target);
  } catch (error) {
    try { unlinkSync(temporary); } catch {}
    throw error;
  }
}

function choosePython(projectRoot, explicit) {
  const candidates = [
    explicit,
    process.env.SOUND_VISION_KINETIC_PYTHON,
    resolve(projectRoot, ".venv-alignment/bin/python"),
    "/srv/ai/sound-vision/.venv-alignment/bin/python",
    "python3",
  ].filter(Boolean);
  for (const candidate of candidates) {
    try {
      if (candidate === "python3" || existsSync(candidate)) return candidate;
    } catch {}
  }
  return "python3";
}

export function createKineticExports({
  projectRoot,
  backend,
  token,
  outputRoot = resolve(projectRoot, "../output/kinetic-renders"),
  renderHost = "Mac",
  pythonPath,
  renderScript = resolve(projectRoot, "scripts/video/render-kinetic-export.py"),
  allowedHosts,
  allowedOrigins,
}) {
  mkdirSync(outputRoot, { recursive: true });
  const stagingRoot = join(outputRoot, ".staging");
  mkdirSync(stagingRoot, { recursive: true });
  const jobs = new Map();
  let current = null;
  let closed = false;
  const workFor = (id) => join(outputRoot, id);
  const save = (job) => atomic(join(workFor(job.id), "job.json"), job);
  for (const id of readdirSync(outputRoot).filter((item) => idPattern.test(item))) {
    try {
      const job = JSON.parse(readFileSync(join(workFor(id), "job.json"), "utf8"));
      if (job.id !== id) continue;
      if (job.state === "running") {
        job.state = "failed";
        job.phase = "Render interrupted";
        job.error = "The renderer restarted. Start a new render; the previous files are retained.";
        save(job);
      }
      jobs.set(id, job);
    } catch {
      /* Retain incomplete folders for inspection without exposing them. */
    }
  }
  const pending = () => [...jobs.values()]
    .filter((job) => ACTIVE.has(job.state))
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
    framesPerSecond: job.elapsedSeconds > 0 && job.frames > 0
      ? job.frames / job.elapsedSeconds
      : null,
    remainingSeconds: job.elapsedSeconds > 0 && job.frames > 0
      ? Math.max(0, ((job.totalFrames - job.frames) * job.elapsedSeconds) / job.frames)
      : null,
    queuePosition: ACTIVE.has(job.state)
      ? pending().findIndex((item) => item.id === job.id) + 1
      : null,
    background: job.input.draft.background,
    aspect: job.input.draft.aspect,
    lyrics: job.input.cues.length > 0,
    assetCount: job.input.assets.length,
    downloadUrl: job.state === "succeeded"
      ? `/local-api/kinetic-renders/${job.id}/video?download=1`
      : null,
    videoUrl: job.state === "succeeded"
      ? `/local-api/kinetic-renders/${job.id}/video`
      : null,
    duration: job.duration || job.input.duration,
    bytes: job.bytes || 0,
  });
  const update = (job, data) => {
    Object.assign(job, data, { updated: Date.now() });
    save(job);
  };
  async function remote(path, signal) {
    if (!backend || !token) throw Error("Connect the music backend before rendering.");
    const response = await fetch(new URL(path, backend), {
      headers: { Authorization: `Bearer ${token}` },
      signal,
    });
    if (!response.ok)
      throw Error(`Music backend returned ${response.status}. Confirm the song is ready and retry.`);
    return response;
  }
  async function run(job) {
    const work = workFor(job.id);
    const abort = new AbortController();
    current = { job, abort, child: null };
    const began = Date.now();
    update(job, { state: "running", phase: "Preparing original soundtrack", error: null });
    try {
      const signal = AbortSignal.any([abort.signal, AbortSignal.timeout(120000)]);
      const library = await (await remote("/api/library", signal)).json();
      const track = library.tracks.find(
        (item) => item.id === job.input.takeId && item.status === "succeeded",
      );
      if (!track) throw Error("The song must finish generating before video rendering.");
      update(job, { title: track.title });
      const response = await remote(`/api/takes/${job.input.takeId}/files/audio.flac`, signal);
      await pipeline(
        Readable.fromWeb(response.body),
        createWriteStream(join(work, "audio.flac"), { mode: 0o600 }),
        { signal },
      );
      const sourceDuration = Number(JSON.parse(execFileSync(
        "ffprobe",
        ["-v", "error", "-show_format", "-of", "json", join(work, "audio.flac")],
        { encoding: "utf8", timeout: 15000 },
      )).format.duration);
      if (!Number.isFinite(sourceDuration) || sourceDuration < 1)
        throw Error("Could not measure the original soundtrack.");
      if (job.input.duration > sourceDuration + 0.25)
        throw Error("The requested render is longer than the recording. Refresh the song and render again.");
      const duration = Math.min(job.input.duration, sourceDuration);
      const width = job.input.draft.aspect === "9:16" ? 1080 : 1920;
      const height = job.input.draft.aspect === "9:16" ? 1920 : 1080;
      atomic(join(work, "config.json"), {
        ...job.input,
        duration,
        width,
        height,
        fps: FPS,
        audio: join(work, "audio.flac"),
        assets: job.input.assets.map((asset) => ({
          ...asset,
          path: stagedAssetPath(join(work, ""), asset.kind, asset.slot),
        })),
      });
      update(job, {
        phase: "Rendering kinetic backgrounds and lyrics",
        duration,
        totalFrames: Math.ceil(duration * FPS),
      });
      if (abort.signal.aborted) throw Error("Cancelled");
      const log = createWriteStream(join(work, "worker.log"), { flags: "a" });
      const child = spawn(
        choosePython(projectRoot, pythonPath),
        [renderScript, "--config", join(work, "config.json"), "--output", join(work, "video.mp4")],
        { cwd: projectRoot, detached: true, stdio: ["ignore", "pipe", "pipe"], env: { ...process.env } },
      );
      current.child = child;
      child.stdout.pipe(log, { end: false });
      child.stderr.pipe(log, { end: false });
      const timer = setInterval(() => {
        try {
          const progress = JSON.parse(readFileSync(join(work, "progress.json"), "utf8"));
          if (job.state === "running")
            update(job, { phase: progress.phase, frames: progress.frames || 0, totalFrames: progress.totalFrames || job.totalFrames, elapsedSeconds: (Date.now() - began) / 1000 });
        } catch {}
      }, 1000);
      try {
        await new Promise((resolvePromise, reject) => {
          child.once("error", reject);
          child.once("close", (code) => {
            if (code === 0) return resolvePromise();
            let message = `Render stopped (${code ?? "signal"}). Start a new render to retry.`;
            try { message = JSON.parse(readFileSync(join(work, "failure.json"), "utf8")).message; } catch {}
            reject(Error(message));
          });
        });
      } finally {
        clearInterval(timer);
        log.end();
      }
      if (abort.signal.aborted) throw Error("Cancelled");
      const receipt = JSON.parse(readFileSync(join(work, "receipt.json"), "utf8"));
      update(job, {
        state: "succeeded",
        phase: "MP4 ready",
        frames: receipt.frames,
        totalFrames: receipt.frames,
        bytes: statSync(join(work, "video.mp4")).size,
        elapsedSeconds: (Date.now() - began) / 1000,
      });
    } catch (error) {
      update(job, {
        state: abort.signal.aborted && !closed ? "cancelled" : "failed",
        phase: closed ? "Render interrupted" : abort.signal.aborted ? "Cancelled" : "Render needs attention",
        error: abort.signal.aborted ? (closed ? "The renderer stopped. Start a new render; files are retained." : null) : String(error.message || error),
      });
    } finally {
      current = null;
      void pump();
    }
  }
  async function pump() {
    if (closed || current) return;
    const next = pending().find((job) => job.state === "queued");
    if (next) await run(next);
  }
  function cancel() {
    if (!current) return;
    current.abort.abort();
    if (current.child) {
      try { process.kill(-current.child.pid, "SIGTERM"); } catch {}
    }
  }
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
    if (!url.pathname.startsWith("/local-api/kinetic-renders")) return next();
    if (!trustedLocalRequest(req, { allowedHosts, allowedOrigins }))
      return send(res, 403, { detail: "Forbidden" });
    try {
      const base = "/local-api/kinetic-renders";
      const tail = url.pathname.slice(base.length).split("/").filter(Boolean);
      if (!tail.length && req.method === "GET") {
        const takeId = url.searchParams.get("takeId");
        if (takeId && !takePattern.test(takeId)) return send(res, 400, { detail: "Invalid take" });
        return send(res, 200, {
          available: !!backend,
          renderer: renderHost,
          jobs: [...jobs.values()]
            .filter((job) => !takeId || job.input.takeId === takeId)
            .sort((a, b) => b.created - a.created)
            .map(publicJob),
        });
      }
      if (tail[0] === "assets" && tail.length === 1 && req.method === "POST") {
        const body = await jsonBody(req);
        if (!takePattern.test(body.takeId || "") || !idPattern.test(body.requestId || ""))
          throw Error("Choose a saved, generated song before uploading media.");
        const stage = join(stagingRoot, body.requestId);
        mkdirSync(join(stage, "assets"), { recursive: true, mode: 0o700 });
        atomic(join(stage, "input.json"), {
          takeId: body.takeId,
          requestId: body.requestId,
          assets: body.assets,
        });
        return send(res, 200, { requestId: body.requestId, uploaded: [] });
      }
      if (tail[0] === "assets" && tail.length === 4 && req.method === "PUT") {
        const requestId = tail[1];
        const kind = tail[2];
        const slot = Number(tail[3]);
        if (!idPattern.test(requestId) || !kindValues.includes(kind) || !Number.isInteger(slot) || slot < 0 || slot > 99)
          throw Error("Invalid background upload");
        const stage = join(stagingRoot, requestId);
        const metadata = JSON.parse(readFileSync(join(stage, "input.json"), "utf8"));
        if (!metadata.assets?.some((asset) => asset.kind === kind && asset.slot === slot))
          throw Error("This background slot was not declared for the render.");
        await writeUpload(req, stagedAssetPath(stage, kind, slot), kind === "images" ? 30 * 1024 ** 2 : 170 * 1024 ** 2);
        return send(res, 200, { requestId, kind, slot, uploaded: true });
      }
      if (!tail.length && req.method === "POST") {
        const body = await jsonBody(req);
        const stage = join(stagingRoot, body.requestId || "");
        const input = validateKineticExport(body, stage);
        const signature = createHash("sha256")
          .update(JSON.stringify({ ...input, requestId: undefined }))
          .digest("hex");
        const previous = [...jobs.values()].find(
          (job) => job.input.requestId === input.requestId || (ACTIVE.has(job.state) && job.signature === signature),
        );
        if (previous)
          return send(res, previous.signature === signature ? 200 : 409, previous.signature === signature ? publicJob(previous) : { detail: "This request ID already belongs to different settings." });
        if (!backend) return send(res, 503, { detail: "Music backend not connected" });
        const id = randomBytes(16).toString("hex");
        const created = Date.now();
        const work = workFor(id);
        mkdirSync(work, { recursive: true, mode: 0o700 });
        renameSync(join(stage, "assets"), join(work, "assets"));
        try { unlinkSync(join(stage, "input.json")); } catch {}
        const job = {
          id,
          input,
          signature,
          created,
          updated: created,
          title: input.title,
          duration: input.duration,
          state: "queued",
          phase: "Queued for rendering",
          error: null,
        };
        jobs.set(id, job);
        save(job);
        send(res, 202, publicJob(job));
        void pump();
        return;
      }
      const id = tail[0];
      const job = idPattern.test(id || "") && jobs.get(id);
      if (!job) return send(res, 404, { detail: "Render not found" });
      if (tail[1] === "cancel" && req.method === "POST") {
        if (!ACTIVE.has(job.state)) return send(res, 409, { detail: "This render has already finished" });
        if (current?.job.id === id) cancel();
        else update(job, { state: "cancelled", phase: "Cancelled", error: null });
        return send(res, 200, publicJob(job));
      }
      if (tail[1] === "video" && ["GET", "HEAD"].includes(req.method)) {
        if (job.state !== "succeeded") return send(res, 409, { detail: "The video is not ready yet" });
        const file = join(workFor(id), "video.mp4");
        const size = statSync(file).size;
        const range = byteRange(req.headers.range, size);
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
        if (partial) res.setHeader("Content-Range", `bytes ${start}-${end}/${size}`);
        if (url.searchParams.has("download"))
          res.setHeader("Content-Disposition", `attachment; filename="${String(job.title).replace(/[^a-z0-9]+/gi, "-").slice(0, 90)}-kinetic.mp4"`);
        if (req.method === "HEAD") return res.end();
        const stream = createReadStream(file, { start, end });
        stream.on("error", () => res.destroy());
        res.on("close", () => stream.destroy());
        return stream.pipe(res);
      }
      return send(res, 405, { detail: "Unsupported render operation" });
    } catch (error) {
      if (!res.headersSent) send(res, 400, { detail: String(error.message || error) });
      else res.destroy();
    }
  }
  return {
    middleware,
    start: pump,
    close,
    has: (id) => jobs.has(id),
    list: (takeId) => [...jobs.values()]
      .filter((job) => !takeId || job.input.takeId === takeId)
      .map(publicJob),
  };
}
