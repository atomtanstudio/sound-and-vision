import { chromium } from "@playwright/test";
import assert from "node:assert/strict";
import { writeFile, mkdir } from "node:fs/promises";
const base = process.env.SOUND_VISION_TEST_URL || "http://127.0.0.1:5190";
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH,
});
const receipt = { date: new Date().toISOString(), checks: [], errors: [] };
const check = (name, detail) => {
  receipt.checks.push({ name, detail, result: "pass" });
  console.log("PASS", name);
};
try {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
  });
  const page = await context.newPage();
  page.on("pageerror", (e) => receipt.errors.push(e.message));
  await page.goto(base + "/music");
  await page.getByText("YuE2 connected", { exact: true }).waitFor();
  const health = await (await page.request.get(base + "/api/health")).json();
  assert.equal(health.model, "YuE2-3B");
  assert(health.generation);
  await page
    .getByRole("button", {
      name: "Play City Lights — YuE2 baseline Take 1",
      exact: true,
    })
    .click();
  await page.waitForFunction(
    () =>
      !document.querySelector("audio").paused &&
      document.querySelector("audio").currentTime > 0,
  );
  const measured = await page
    .locator("audio")
    .evaluate((a) => ({ duration: a.duration, url: a.currentSrc }));
  assert(Math.abs(measured.duration - 59.3586667) < 0.2);
  assert(measured.url.includes("/api/takes/"));
  assert(
    Math.abs(
      Number(
        await page
          .getByLabel("Playback position", { exact: true })
          .getAttribute("max"),
      ) - measured.duration,
    ) < 0.2,
  );
  await page.getByLabel("Playback position", { exact: true }).fill("30");
  assert(
    Math.abs(
      (await page.locator("audio").evaluate((a) => a.currentTime)) - 30,
    ) < 2,
  );
  await page
    .getByRole("button", { name: "Pause playback", exact: true })
    .click();
  check(
    "Real generated playback",
    "API-backed baseline plays and seeks; the player uses actual59.36-second duration.",
  );
  await page
    .locator('[data-track="eabe44e7a8da4e8ca9cd8b92a94caa78"] .track-title')
    .click();
  for (const format of ["WAV", "FLAC", "MP3"])
    assert(
      await page.getByRole("link", { name: format, exact: true }).isVisible(),
    );
  await page.getByRole("button", { name: "Make video", exact: true }).click();
  assert.equal(
    await page
      .getByRole("combobox", { name: "Soundtrack", exact: true })
      .inputValue(),
    "eabe44e7a8da4e8ca9cd8b92a94caa78",
  );
  check(
    "Generated delivery and video handoff",
    "All three downloads are available; generated take remains the chosen Video soundtrack.",
  );
  await page.getByRole("button", { name: "Music", exact: true }).click();
  await page
    .getByLabel("Describe your song", { exact: true })
    .fill(
      "English acoustic folk, warm male vocal, fingerpicked guitar, gentle brushed drums, a complete song with an ending.",
    );
  await page
    .getByRole("button", { name: /Add your own lyrics/, exact: true })
    .click();
  await page
    .getByLabel("Your lyrics", { exact: true })
    .fill(
      "[Verse]\nWe leave a light beside the door\nThe road comes home to us once more\n[Chorus]\nLet the morning find us here\nEvery mile is drawing near",
    );
  await page.getByRole("tab", { name: "Advanced", exact: true }).click();
  await page.getByLabel("Song title", { exact: true }).fill("Homeward Light");
  await page
    .getByLabel("Save new songs to project")
    .selectOption("YuE2 verification");
  const submitted = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/generations") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Create 2 takes", exact: true })
    .click();
  const response = await submitted;
  assert.equal(response.status(), 202);
  const request = await response.json();
  assert.equal(request.tracks.length, 2);
  receipt.requestId = request.requestId;
  receipt.takeIds = request.tracks.map((t) => t.id);
  console.log(
    "LIVE_REQUEST",
    JSON.stringify({ requestId: request.requestId, takeIds: receipt.takeIds }),
  );
  check(
    "UI to durable two-take queue",
    "Submitted original lyrics through the real app; backend returned two persistent take IDs.",
  );
  await page.reload();
  await page.getByText("YuE2 connected", { exact: true }).waitFor();
  for (const id of receipt.takeIds)
    await page.locator(`[data-track="${id}"]`).waitFor();
  check(
    "Reload during generation",
    "Both queued/running takes survive browser reload.",
  );
  assert.equal(receipt.errors.length, 0, receipt.errors.join("\n"));
  await page.screenshot({ path: "docs/backend/evidence/live-queue.png" });
} finally {
  await mkdir("docs/backend/evidence", { recursive: true });
  await writeFile(
    "docs/backend/evidence/live-browser.json",
    JSON.stringify(receipt, null, 2),
  );
  await browser.close();
}
