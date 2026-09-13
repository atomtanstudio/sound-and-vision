import { chromium, expect } from "@playwright/test";
import assert from "node:assert/strict";
const browser = await chromium.launch({
  executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH,
});
try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const track = {
    id: "a".repeat(32),
    source: "imported",
    title: "Copper Signals",
    subtitle: "Imported song",
    project: "Imported songs",
    duration: 31,
    status: "succeeded",
    stage: "imported",
    audioUrl: "/media/desert-afterglow-1.mp3",
    form: {
      lyrics: "One\nLost line\nTwo",
      title: "Copper Signals",
      description: "Industrial electronic instrumental",
    },
  };
  let jobs = [],
    renders = 0,
    sequence = 0;
  await page.route("**/api/library?*", (r) =>
    r.fulfill({ json: { tracks: [track] } }),
  );
  await page.route("**/api/takes/*/video", (r) =>
    r.fulfill({
      json: {
        jobs: [
          {
            id: "alignment-fixture",
            kind: "lyric-alignment",
            state: "succeeded",
            input: {
              lyrics: track.form.lyrics,
              language: "en",
              kind: "alignment",
              takeId: track.id,
              slot: 0,
              aspect: "16:9",
            },
            result: {
              lyrics: track.form.lyrics,
              duration: 31,
              wordCount: 4,
              reviewCount: 2,
              cues: [
                {
                  id: "line-0",
                  text: "One",
                  words: [
                    {
                      text: "One",
                      start: 1,
                      end: 2,
                      confidence: 1,
                      review: null,
                    },
                  ],
                },
                {
                  id: "line-1",
                  text: "Lost line",
                  words: [
                    {
                      text: "Lost",
                      start: null,
                      end: null,
                      confidence: 0,
                      review: "Missing",
                    },
                    {
                      text: "line",
                      start: null,
                      end: null,
                      confidence: 0,
                      review: "Missing",
                    },
                  ],
                },
                {
                  id: "line-2",
                  text: "Two",
                  words: [
                    {
                      text: "Two",
                      start: 3,
                      end: 4,
                      confidence: 1,
                      review: null,
                    },
                  ],
                },
              ],
            },
          },
        ],
        alignmentInstalled: true,
      },
    }),
  );
  await page.route("**/api/takes/*/music-video**", async (r) => {
    const url = new URL(r.request().url());
    if (r.request().method() === "GET") {
      await r.fulfill({ json: { jobs } });
      return;
    }
    const input = r.request().postDataJSON();
    let job = {
      id: `job-${++sequence}`,
      kind: "song-video-" + url.pathname.split("/").at(-1),
      state: "succeeded",
      input,
      result: null,
    };
    if (job.kind === "song-video-theme")
      job.result = {
        theme:
          "Copper light sweeps through an empty industrial city. Slow cranes reveal machinery and rain reflecting on steel.",
      };
    if (job.kind === "song-video-plan") {
      const full = Math.ceil(
        (31 - (input.join === "dissolve" ? 0.5 : 0)) /
          (input.clipSeconds - (input.join === "dissolve" ? 0.5 : 0)),
      );
      const count =
        input.coverage === "full" ? full : Math.min(full, input.clipCount);
      job.result = {
        ...input,
        clipCount: count,
        fullClipCount: full,
        duration: 31,
        scenes: Array.from({ length: count }, (_, i) => ({
          name: `Scene ${i + 1}`,
          prompt: "A quiet industrial landscape in copper light.",
        })),
      };
    }
    if (job.kind === "song-video-render") {
      assert.equal(input.cues.length, 3);
      assert.deepEqual(
        input.cues.flatMap((c) => c.words.map((w) => w.text)),
        ["One", "Lost", "line", "Two"],
      );
      assert.equal(input.omitUnusableWords, true);
      renders++;
      job.state = "running";
      job.result = { phase: "Clip 1/2 · Generating on H3" };
    }
    jobs.push(job);
    await r.fulfill({ status: 202, json: job });
  });
  await page.goto("http://127.0.0.1:5190/video");
  await expect(
    page.getByRole("heading", { name: "Create a music video", exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Music video theme")).toHaveValue(
    /Copper light/,
  );
  await expect(
    page.getByRole("radio", { name: "Lip-sync music video", exact: true }),
  ).toBeDisabled();
  await page.getByText("A smaller set that repeats", { exact: true }).click();
  await page.getByLabel("Unique music video clips").fill("2");
  await page.getByText("Advanced controls", { exact: false }).first().click();
  await page.getByLabel("Join music video clips").selectOption("continue");
  await page
    .getByRole("button", { name: "Prepare video", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Create video", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("region", { name: "Lyric timing review", exact: true }),
  ).toBeVisible();
  assert.equal(renders, 0);
  await expect(
    page.getByText("2 clips · 0:31 video", { exact: true }),
  ).toBeVisible();
  // A changed theme invalidates the prepared plan until it is reviewed again.
  await page
    .getByLabel("Music video theme")
    .fill("Ocean waves and distant storm clouds.");
  await expect(
    page.getByRole("button", { name: "Prepare video", exact: true }),
  ).toBeVisible();
  assert.equal(
    await page
      .getByRole("button", { name: "Create video", exact: true })
      .count(),
    0,
  );
  await page
    .getByRole("button", { name: "Prepare video", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Create video", exact: true }),
  ).toBeDisabled();
  await page
    .getByLabel("Omit words with unusable timing", { exact: true })
    .check();
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: "2 words will use their existing timing" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Create video", exact: true }).click();
  assert.equal(renders, 1);
  await expect(
    page.getByText("Clip 1/2 · Generating on H3", { exact: true }),
  ).toBeVisible();
  jobs[jobs.length - 1] = {
    ...jobs.at(-1),
    state: "failed",
    error: "Provider disconnected",
    result: null,
  };
  await expect(
    page.getByRole("button", { name: "Resume video", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Resume video", exact: true }).click();
  assert.equal(renders, 2);
  jobs[jobs.length - 1] = {
    ...jobs.at(-1),
    state: "succeeded",
    result: {
      videoUrl: "/test-movie.mp4",
      downloadUrl: "/test-movie.mp4?download=1",
    },
  };
  await expect(
    page.getByRole("link", { name: "Download MP4", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.reload();
  await expect(
    page.getByRole("link", { name: "Download MP4", exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Music video theme")).toHaveValue(
    "Ocean waves and distant storm clouds.",
  );
  await expect(page.getByLabel("Unique music video clips")).toHaveValue("2");
  await page.screenshot({
    path: "/private/tmp/sv-music-video-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(async () =>
      Math.round(
        await page
          .locator(".primary-rail")
          .evaluate((el) => el.getBoundingClientRect().width),
      ),
    )
    .toBe(72);
  assert(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  );
  await page.screenshot({ path: "/private/tmp/sv-music-video-mobile.png" });
  assert.deepEqual(errors, []);
  console.log(
    "PASS theme suggestion, reviewed clip count, plan invalidation, explicit render start, failure/resume, completion, reload, mobile and runtime",
  );
} finally {
  await browser.close();
}
