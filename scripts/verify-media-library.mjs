import { chromium, expect } from "@playwright/test";
import assert from "node:assert/strict";
import { readFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { execFileSync } from "node:child_process";
const temp = mkdtempSync(join(tmpdir(), "sv-library-test-"));
execFileSync("ffmpeg", [
  "-v",
  "error",
  "-f",
  "lavfi",
  "-i",
  "color=c=0x302631:s=160x90:r=10:d=3",
  "-c:v",
  "libx264",
  "-pix_fmt",
  "yuv420p",
  "-movflags",
  "+faststart",
  join(temp, "video.mp4"),
]);
const mp4 = readFileSync(join(temp, "video.mp4"));
const browser = await chromium.launch({
  executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH,
});
try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const alpha = "a".repeat(32),
    beta = "b".repeat(32),
    deleted = "c".repeat(32);
  const tracks = [alpha, beta, deleted].map((id, i) => ({
    id,
    source: "imported",
    status: "succeeded",
    title: ["Copper Signals", "Night Drive", "Deleted song"][i],
    project: "Album",
    subtitle: "Imported song",
    duration: 31,
    created: i + 100,
    audioUrl: `/api/takes/${id}/files/audio.mp3`,
    deletedAt: i === 2 ? 123 : null,
    form: { lyrics: "Test words" },
  }));
  let unavailable = false;
  await page.route("**/api/**", (r) =>
    r.fulfill({ status: 503, json: { detail: "Isolated fixture" } }),
  );
  await page.route("**/api/health", (r) =>
    r.fulfill({ json: { connected: true } }),
  );
  await page.route("**/api/library?*", (r) => r.fulfill({ json: { tracks } }));
  await page.route("**/api/library/videos", (r) =>
    unavailable
      ? r.fulfill({ status: 503 })
      : r.fulfill({
          json: {
            missingFiles: 0,
            videos: [
              ...[1, 2].map((i) => ({
                id: `music-video:movie-${i}`,
                kind: "music-video",
                title: "Copper Signals",
                takeId: alpha,
                created: 200 + i,
                duration: 31,
                videoUrl: `/fixture/movie-${i}.mp4`,
                downloadUrl: `/fixture/movie-${i}.mp4?download=1`,
              })),
              {
                id: "film:legacy:one",
                kind: "film",
                filmId: "film-legacy",
                title: "Legacy Film",
                takeId: beta,
                created: 199,
                duration: 31,
                videoUrl: "/fixture/legacy.mp4",
                downloadUrl: "/fixture/legacy.mp4",
              },
            ],
          },
        }),
  );
  await page.route("**/local-api/visualizer-renders", (r) =>
    r.fulfill({
      json: {
        available: true,
        jobs: [
          {
            id: "v".repeat(32),
            state: "succeeded",
            takeId: beta,
            title: "Visualizer",
            created: 198,
            duration: 31,
            videoUrl: "/fixture/visualizer.mp4",
            downloadUrl: "/fixture/visualizer.mp4?download=1",
          },
          { id: "failed", state: "failed", takeId: alpha },
          {
            id: "deleted",
            state: "succeeded",
            takeId: deleted,
            videoUrl: "/fixture/deleted.mp4",
          },
        ],
      },
    }),
  );
  await page.route("**/fixture/*.mp4*", (r) =>
    r.fulfill({ contentType: "video/mp4", body: mp4 }),
  );
  await page.route("**/api/takes/*/files/audio.mp3", async (r) => {
    // Use the bundled sample recording for actual shared-player playback.
    const response = await page.request.get(
      "http://127.0.0.1:5190/media/desert-afterglow-1.mp3",
    );
    await r.fulfill({ response });
  });
  await page.goto("http://127.0.0.1:5190/library");
  const library = page.getByRole("region", {
    name: "Media library",
    exact: true,
  });
  await expect(
    library.getByRole("heading", { name: "Library", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Library", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  await expect(library.locator("video")).toHaveCount(4);
  await expect(library.getByText("Deleted song", { exact: true })).toHaveCount(
    0,
  );
  await library.getByRole("button", { name: "Videos", exact: true }).click();
  await expect(library.locator("article")).toHaveCount(4);
  await library.getByLabel("Search library", { exact: true }).fill("Copper");
  await expect(library.locator("article")).toHaveCount(2);
  await library.getByRole("button", { name: "Music", exact: true }).click();
  await expect(library.locator("article")).toHaveCount(1);
  await library
    .getByRole("button", { name: "Play Copper Signals", exact: true })
    .click();
  await expect
    .poll(() => page.locator("audio").evaluate((a) => a.paused))
    .toBe(false);
  await library.getByRole("button", { name: "Videos", exact: true }).click();
  await library
    .locator("video")
    .first()
    .evaluate((v) => v.play());
  await expect
    .poll(() => page.locator("audio").evaluate((a) => a.paused))
    .toBe(true);
  await library
    .locator("video")
    .nth(1)
    .evaluate((v) => v.play());
  await expect
    .poll(() =>
      library
        .locator("video")
        .first()
        .evaluate((v) => v.paused),
    )
    .toBe(true);
  await expect(
    library.getByRole("link", { name: "Download", exact: true }).first(),
  ).toHaveAttribute("href", /download=1/);
  // Partial service failure retains a loaded history instead of replacing it with an empty library.
  unavailable = true;
  await expect(
    library.getByText(/Music-video history is unavailable/),
  ).toBeVisible({ timeout: 15000 });
  await expect(library.locator("article")).toHaveCount(2);
  unavailable = false;
  await library.getByLabel("Search library", { exact: true }).fill("");
  await library.screenshot({ path: "/private/tmp/sv-library-desktop.png" });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() =>
      page
        .locator(".primary-rail")
        .evaluate((e) => Math.round(e.getBoundingClientRect().width)),
    )
    .toBe(72);
  assert(await library.evaluate((e) => e.scrollWidth <= e.clientWidth));
  await library
    .getByRole("heading", { name: "Library", exact: true })
    .scrollIntoViewIfNeeded();
  await page.screenshot({ path: "/private/tmp/sv-library-mobile.png" });
  await page.reload();
  await expect(library.locator("video")).toHaveCount(4);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await library
    .getByRole("article", {
      name: "Visualizer video: Night Drive",
      exact: true,
    })
    .getByRole("button", { name: "Open editor", exact: true })
    .click();
  await expect(page).toHaveURL(/\/video$/);
  await expect(
    page.getByRole("radio", { name: "Visualizer video", exact: true }),
  ).toBeChecked();
  assert.equal(
    await page.evaluate(() => localStorage.getItem("sv-video-source-v1")),
    JSON.stringify(beta),
  );
  await page.goBack();
  await expect(
    library.getByRole("heading", { name: "Library", exact: true }),
  ).toBeVisible();
  await expect(page).toHaveTitle("Sound/Vision — Library");
  assert.deepEqual(errors, []);
  console.log(
    "PASS Library catalog, type/search filters, export versions, trash exclusion, inline playback, downloads, service failure, persistence, navigation and responsive layout",
  );
} finally {
  await browser.close();
  rmSync(temp, { recursive: true, force: true });
}
