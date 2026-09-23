// Current studio regression: intercepted providers and synthetic media only.
// This never submits generation or render work to a real service.
import { chromium } from "@playwright/test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { readFile, mkdir, writeFile, mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const evidence = process.env.SOUND_VISION_EVIDENCE || await mkdtemp(join(tmpdir(), "sound-vision-ui-"));
await mkdir(evidence, { recursive: true });
const clip = join(evidence, "synthetic-preview.mp4"), audio = join(evidence, "synthetic-audio.wav");
const ffmpeg = process.env.FFMPEG_BINARY || "ffmpeg";
execFileSync(ffmpeg, ["-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0x24352f:s=320x180:r=30:d=8",
  "-f", "lavfi", "-i", "sine=frequency=440:duration=8", "-c:v", "libx264", "-preset", "ultrafast",
  "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", clip]);
execFileSync(ffmpeg, ["-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=12", audio]);
const image = await readFile("backend/visualizer_references/dream.png");
const dimensions = [image.readUInt32BE(16), image.readUInt32BE(20)], takeId = "a".repeat(32);
const song = { id: takeId, title: "Release check song", subtitle: "Take 2 · Ready", source: "yue2",
  status: "succeeded", project: "Release checks", created: Date.now(), duration: 12, favorite: false,
  cover: "/covers/amber.png", form: { style: "Intimate dream pop, pearl light and soft rain.", lyrics: "[Verse]\nA light waits by the window." } };
const artJobs = [], renders = [], submissions = [];
const receipt = { date: new Date().toISOString(), checks: [], errors: [] };
const check = (name) => { receipt.checks.push(name); console.log("PASS", name); };
const browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH });
const base = process.env.SOUND_VISION_TEST_URL || "http://127.0.0.1:5190";
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await context.addInitScript((id) => {
    if (!localStorage.getItem("release-fixture-ready")) {
      localStorage.setItem("sv-video-source-v1", JSON.stringify(id));
      localStorage.setItem("release-fixture-ready", "true");
    }
  }, takeId);
  const json = (route, body, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  await context.route("**/api/**", async (route) => {
    const req = route.request(), path = new URL(req.url()).pathname;
    if (path === "/api/health") return json(route, { connected: true, generation: true, model: "Test fixture" });
    if (path === "/api/library") return json(route, { tracks: [song] });
    if (path === "/api/library/videos") return json(route, { videos: [] });
    if (path === "/api/loras") return json(route, { groups: [] });
    if (path === "/api/openai/account") return json(route, { connected: true, available: true, images: true, provider: "Fixture" });
    if (path === `/api/takes/${takeId}/video`) return json(route, { jobs: [] });
    if (path.endsWith("/files/audio.flac")) return route.fulfill({ contentType: "audio/wav", path: audio });
    if (path.endsWith("/image")) return route.fulfill({ contentType: "image/png", body: image });
    if (path === `/api/takes/${takeId}/reactive-artwork`) {
      if (req.method() === "GET") return json(route, { available: true, jobs: artJobs });
      const input = req.postDataJSON();
      submissions.push({ kind: "artwork", input });
      const result = { version: 1, renderer: "reference-player-v1", aspect: input.aspect,
        takeId, artworkJobId: input.requestId, artworkUrl: `${path}/${input.requestId}/image`,
        artworkSha256: createHash("sha256").update(image).digest("hex"), dimensions,
        title: song.title, concept: "A listening room at dusk", mood: "Soft and intimate",
        reasoning: "The supplied dream-pop description and window lyric guide the room and pearl light.",
        evidence: ["The supplied lyric describes a light by the window."], observations: "Fixture glass registration", quality: .95,
        surfaces: [{ name: "Glass", effect: "ribbon", color: "#aabbcc", accent: "#ddeeff", strength: 1,
          confidence: .95, reason: "Gentle measured curves", corners: [[.2,.3],[.8,.3],[.8,.6],[.2,.6]] }] };
      const job = { id: input.requestId, kind: "reactive-artwork", state: "succeeded", created: Date.now(), error: null,
        input: { takeId, aspect: input.aspect, song: input }, result };
      artJobs.push(job);
      return json(route, job, 202);
    }
    return json(route, { detail: "No real backend in this test" }, 503);
  });
  await context.route("**/local-api/**", async (route) => {
    const req = route.request(), path = new URL(req.url()).pathname;
    if (path.endsWith("/video")) return route.fulfill({ contentType: "video/mp4", path: clip });
    if (path === "/local-api/visualizer-renders") {
      if (req.method() === "GET") return json(route, { available: true, renderer: "Fixture",
        capabilities: { songScenes: 1, referencePlayer: 1, motionPreviews: 1 }, jobs: renders });
      const input = req.postDataJSON();
      submissions.push({ kind: "render", input });
      const id = String(renders.length + 1).repeat(32);
      const job = { id, state: "succeeded", title: song.title, takeId, preview: !!input.preview,
        artworkId: input.draft.reactiveArtworkId, created: Date.now(), duration: input.preview ? 8 : input.duration,
        aspect: input.draft.aspect, lyrics: input.draft.showLyrics, renderHost: "Fixture",
        videoUrl: `/local-api/visualizer-renders/${id}/video`, downloadUrl: `/local-api/visualizer-renders/${id}/video?download=1` };
      renders.unshift(job);
      return json(route, job, 202);
    }
    return json(route, { available: true, jobs: [] });
  });
  const page = await context.newPage();
  page.on("pageerror", (error) => receipt.errors.push(error.message));
  await page.goto(base + "/music");
  await page.getByRole("heading", { name: "New song", exact: true }).waitFor();
  const description = page.getByLabel("Describe the song", { exact: true });
  await description.fill("Keep this draft through navigation and reload.");
  await page.getByRole("button", { name: "Synthesis controls" }).click();
  assert.equal(await page.getByRole("button", { name: "Hide synthesis controls" }).getAttribute("aria-expanded"), "true");
  await page.reload();
  assert.equal(await description.inputValue(), "Keep this draft through navigation and reload.");
  await page.getByRole("button", { name: "Switch to daylight" }).click();
  await page.reload();
  assert.equal(await page.locator("html").getAttribute("data-theme"), "light");
  check("Music draft and theme survive reload");
  const navigate = (name) => page.getByRole("navigation", { name: "Primary" }).getByRole("button", { name, exact: true }).click();
  await navigate("Video");
  await page.getByRole("heading", { name: "A scene for your song" }).waitFor();
  assert.equal(await page.getByRole("tab", { name: "Song Reactive Visualizer", exact: true }).getAttribute("aria-selected"), "true");
  assert.equal(await page.locator(".classic-styles").evaluate((n) => n.open), false);
  assert.equal(await page.getByRole("switch", { name: "Show lyrics" }).getAttribute("aria-checked"), "false");
  await page.getByRole("button", { name: "Create song artwork", exact: true }).click();
  await page.locator(".song-artwork-still").waitFor();
  assert.equal(submissions[0].input.genre, song.form.style);
  assert.equal(submissions[0].input.lyrics, song.form.lyrics);
  assert.equal(await page.locator(".stage-badge").count(), 0);
  check("Song metadata reaches artwork creation without a preset choice");
  await page.getByRole("button", { name: "Preview motion", exact: true }).click();
  await page.getByRole("button", { name: "Watch preview", exact: true }).click();
  const video = page.locator("video.song-motion-preview");
  await page.waitForFunction(() => document.querySelector("video.song-motion-preview")?.readyState >= 2);
  assert.equal(submissions.at(-1).input.preview, true);
  assert.equal(submissions.at(-1).input.takeId, takeId);
  assert.equal(submissions.at(-1).input.draft.reactiveArtworkId, artJobs[0].id);
  await video.evaluate((v) => v.play());
  await page.waitForFunction(() => document.querySelector("video.song-motion-preview").currentTime > .2);
  await video.evaluate((v) => { v.pause(); v.currentTime = 4; });
  await page.waitForFunction(() => !document.querySelector("video.song-motion-preview").seeking);
  assert.equal(await video.evaluate((v) => v.duration), 8);
  await page.screenshot({ path: join(evidence, "motion-preview.png") });
  await page.getByRole("button", { name: "Close", exact: true }).click();
  check("Explicit preview opens a playable and seekable modal");
  await page.getByRole("switch", { name: "Show lyrics" }).click();
  assert.equal(await page.getByRole("button", { name: "Render video", exact: true }).isEnabled(), false);
  await page.getByRole("switch", { name: "Show lyrics" }).click();
  await page.getByRole("button", { name: "Render video", exact: true }).click();
  await page.getByRole("button", { name: "Watch video", exact: true }).waitFor();
  assert.equal(submissions.at(-1).input.preview, undefined);
  assert.equal(submissions.at(-1).input.duration, 12);
  await page.reload();
  await page.locator(".song-artwork-still").waitFor();
  await page.getByRole("button", { name: "Watch preview", exact: true }).waitFor();
  check("Full export and preview remain distinct and survive reload");
  await navigate("Library");
  await page.getByRole("tab", { name: "Videos 1", exact: true }).click();
  assert.equal(await page.locator(".video-card").count(), 1);
  assert.equal(await page.locator(".video-card video").getAttribute("src"), renders.find((r) => !r.preview).videoUrl);
  await page.getByRole("button", { name: "Open editor", exact: true }).click();
  await page.locator(".song-artwork-still").waitFor();
  await page.locator(".classic-styles summary").click();
  await page.getByRole("button", { name: /^Vault/ }).click();
  assert.equal(await page.getByRole("button", { name: "Preview motion", exact: true }).count(), 0);
  await page.getByRole("button", { name: "Create a scene for this song", exact: true }).click();
  await page.locator(".song-artwork-still").waitFor();
  check("Library shows full exports; classics and song artwork are preserved");
  for (const width of [1440, 820, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.getByRole("button", { name: "Preview motion", exact: true }).scrollIntoViewIfNeeded();
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `Overflow at ${width}`);
    const box = await page.getByRole("button", { name: "Preview motion", exact: true }).boundingBox();
    assert(box.x >= 0 && box.x + box.width <= width);
  }
  await page.getByRole("button", { name: "Watch preview", exact: true }).click();
  const box = await video.boundingBox();
  assert(box.x >= 0 && box.x + box.width <= 390);
  await page.screenshot({ path: join(evidence, "mobile-preview.png") });
  check("Desktop and mobile preview controls fit the viewport");
  assert.deepEqual(receipt.errors, []);
  assert.equal(submissions.filter((s) => s.kind === "artwork").length, 1);
  assert.equal(submissions.filter((s) => s.kind === "render").length, 2);
  check("No uncaught browser errors or duplicate submissions");
} finally {
  await writeFile(join(evidence, "verification.json"), JSON.stringify(receipt, null, 2));
  await browser.close();
  console.log("Evidence:", evidence);
}
