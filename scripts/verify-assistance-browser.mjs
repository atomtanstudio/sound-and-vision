// Explicit live check: one account request and one transcription of our original song.
import { chromium, expect } from "@playwright/test";
import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
if (!process.argv.includes("--live"))
  throw new Error("Pass --live to authorize account and reference requests.");
const base = process.env.SOUND_VISION_TEST_URL || "http://127.0.0.1:5190";
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH,
});
const previous = process.argv.includes("--resume")
  ? JSON.parse(
      await readFile("docs/backend/evidence/assistance-browser.json", "utf8"),
    )
  : null;
const evidence = { date: new Date().toISOString(), checks: [], errors: [] };
const check = (text) => {
  evidence.checks.push(text);
  console.log("PASS", text);
};
try {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
  });
  if (previous)
    await context.addInitScript((p) => {
      if (!sessionStorage.getItem("test-seeded")) {
        localStorage.setItem("sv-writing-request", JSON.stringify(p.writingId));
        localStorage.setItem(
          "sv-reference-request",
          JSON.stringify(p.referenceId),
        );
        sessionStorage.setItem("test-seeded", "1");
      }
    }, previous);
  const page = await context.newPage();
  page.on("pageerror", (e) => evidence.errors.push(e.message));
  await page.goto(base + "/music");
  await page
    .getByRole("button", { name: "Your account, connected", exact: true })
    .waitFor();
  await page
    .getByRole("button", { name: "Your account, connected", exact: true })
    .click();
  assert(
    await page.getByRole("button", { name: "Disconnect OpenAI" }).isVisible(),
  );
  await page.keyboard.press("Escape");
  check("Signed-in account is reflected in the browser");
  assert.equal(await page.locator('a[href*="map-yue2"]').count(), 0);
  const brief =
    "English folk songs about small acts of kindness in a coastal town";
  await page.getByLabel("Describe your song", { exact: true }).fill(brief);
  await page
    .locator("summary")
    .filter({ hasText: "Writing assistant" })
    .click();
  await page
    .getByLabel("Writing task", { exact: true })
    .selectOption("Song ideas");
  await page
    .getByLabel("Instructions", { exact: true })
    .fill("Give me three distinct original ideas with concrete settings.");
  if (!previous) {
    const submitted = page.waitForResponse(
      (r) =>
        r.url().endsWith("/api/assistance") && r.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Generate proposal", exact: true })
      .click();
    evidence.writingId = (await (await submitted).json()).id;
  } else evidence.writingId = previous.writingId;
  await page
    .getByRole("button", { name: "Review proposal", exact: true })
    .waitFor({ timeout: 200000 });
  await page
    .getByRole("button", { name: "Review proposal", exact: true })
    .click();
  assert.equal(
    await page
      .getByRole("button", { name: "Use this idea", exact: true })
      .count(),
    3,
  );
  await page
    .getByRole("button", { name: "Use this idea", exact: true })
    .first()
    .click();
  assert.notEqual(
    await page.getByLabel("Describe your song", { exact: true }).inputValue(),
    brief,
  );
  await page
    .getByRole("button", { name: "Undo applied proposal", exact: true })
    .click();
  assert.equal(
    await page.getByLabel("Describe your song", { exact: true }).inputValue(),
    brief,
  );
  check("Live ideas produce three choices; apply and undo preserve the draft");
  await page.locator("summary").filter({ hasText: "Reference song" }).click();
  if (!previous) {
    const response = await context.request.get(
      base + "/api/takes/eabe44e7a8da4e8ca9cd8b92a94caa78/files/audio.mp3",
    );
    assert(response.ok());
    const uploadResponse = page.waitForResponse(
      (r) =>
        r.url().includes("/api/references?") && r.request().method() === "POST",
    );
    await page
      .getByLabel("Audio file", { exact: true })
      .setInputFiles({
        name: "City-Lights-browser-reference.mp3",
        mimeType: "audio/mpeg",
        buffer: await response.body(),
      });
    await page.getByRole("button", {name: "Generate score", exact: true}).click();
    evidence.referenceId = (await (await uploadResponse).json()).id;
  } else evidence.referenceId = previous.referenceId;
  await page
    .getByRole("button", { name: "Use this score", exact: true })
    .waitFor({ timeout: 120000 });
  const abc = await page
    .getByLabel("Transcribed score", { exact: true })
    .inputValue();
  assert(abc.includes("K:"));
  await page
    .getByRole("button", { name: "Use this score", exact: true })
    .click();
  const form = await page.evaluate(() =>
    JSON.parse(localStorage.getItem("sv-form-v2")),
  );
  assert.equal(form.abc, abc);
  assert.equal(form.cot, "melody");
  assert.equal(form.referenceId, evidence.referenceId);
  await page.reload();
  const reloaded = await page.evaluate(() =>
    JSON.parse(localStorage.getItem("sv-form-v2")),
  );
  assert.equal(reloaded.referenceId, evidence.referenceId);
  check(
    "Audio upload, score application, melody mode and reference provenance survive reload",
  );
  await page
    .getByLabel("Filter by genre", { exact: true })
    .selectOption("Indie folk");
  await page
    .getByRole("button", {
      name: "City Lights — reference cover test",
      exact: true,
    })
    .waitFor();
  check("Genre filtering finds the reference-generated take");
  await page.screenshot({
    path: "docs/backend/evidence/assistance-browser.png",
    fullPage: true,
  });
  await page.getByRole('button', {name:'City Lights — reference cover test',exact:true}).click();
  await page.locator('.detail-cover img').waitFor();
  assert(await page.locator('.detail-cover img').evaluate(image => image.complete && image.naturalWidth > 0));
  await page.getByRole('button', {name:'Edit with assistant',exact:true}).click();
  await expect(page.getByRole('tab', {name:'Advanced', exact:true})).toHaveAttribute('aria-selected','true',{timeout:15000});
  await page.waitForFunction(() => JSON.parse(localStorage.getItem('sv-form-v2') || '{}').sourceTakeId === 'b684135c0b5443038650f94524adcea9');
  assert.equal(await page.getByRole('tab',{name:'Advanced',exact:true}).getAttribute('aria-selected'), 'true');
  const edit = await page.evaluate(() => JSON.parse(localStorage.getItem('sv-form-v2')));
  assert.equal(edit.sourceTakeId,'b684135c0b5443038650f94524adcea9');
  assert.equal(edit.writingTask,'Edit score');
  assert(edit.abc.includes('V: Vocal'));
  check('Generated cover displays and track editing loads its score with original-take provenance');
  assert.deepEqual(evidence.errors, []);
} finally {
  await mkdir("docs/backend/evidence", { recursive: true });
  await writeFile(
    "docs/backend/evidence/assistance-browser.json",
    JSON.stringify(evidence, null, 2) + "\n",
  );
  await browser.close();
}
