import { chromium } from "@playwright/test";
import assert from "node:assert/strict";
const b = await chromium.launch({
  executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH,
});
const p = await b.newPage({ viewport: { width: 1440, height: 1000 } });
let tracks = [];
let imports = 0;
const track = {
  id: "abcdef0123456789abcdef0123456789",
  source: "imported",
  title: "User track",
  subtitle: "Imported song",
  project: "Imported songs",
  favorite: false,
  created: 1,
  duration: 93,
  status: "succeeded",
  stage: "imported",
  audioUrl: "/media/desert-afterglow-1.mp3",
  form: { lyrics: "", description: "Imported audio", title: "User track" },
};
await p.route("**/api/library?*", (r) => r.fulfill({ json: { tracks } }));
await p.route("**/api/songs/import", async (r) => {
  imports++;
  assert(r.request().headers()["x-filename"] === "user.wav");
  tracks = [track];
  await r.fulfill({ status: 201, json: track });
});
let transcriptJobs = [];
await p.route("**/api/takes/*/video", async (r) => {
  if (r.request().method() === "POST") {
    const input = r.request().postDataJSON();
    transcriptJobs = [
      {
        id: "transcript-test-001",
        kind: "lyric-transcription",
        state: "succeeded",
        input,
        result: {
          lyrics: "A misheard line",
          duration: 93,
          requiresReview: true,
        },
      },
    ];
    await r.fulfill({ status: 202, json: transcriptJobs[0] });
  } else
    await r.fulfill({
      json: { jobs: transcriptJobs, alignmentInstalled: true },
    });
});
await p.goto("http://127.0.0.1:5190/video");
await p
  .getByLabel("Import song", { exact: true })
  .setInputFiles({
    name: "user.wav",
    mimeType: "audio/wav",
    buffer: Buffer.from("UI transport fixture"),
  });
await p.getByRole("combobox", { name: "Soundtrack", exact: true }).waitFor();
await p.waitForFunction(
  () =>
    document.querySelector('select[aria-label="Soundtrack"]')?.value ===
    "abcdef0123456789abcdef0123456789",
);
assert.equal(imports, 1);
assert(
  (
    await p
      .getByRole("combobox", { name: "Soundtrack", exact: true })
      .textContent()
  ).includes("Imported song"),
);
assert((await p.locator("body").innerText()).includes("1:33"));
await p.getByText("Visualizer video", { exact: true }).click();
await p.screenshot({ path: "/private/tmp/import-ui-desktop.png" });
await p.reload();
await p.waitForFunction(
  () =>
    document.querySelector('select[aria-label="Soundtrack"]')?.value ===
    "abcdef0123456789abcdef0123456789",
);
await p.getByText("Lyrics & timing", { exact: false }).first().click();
await p.getByLabel("Video lyrics", { exact: true }).fill("My existing lyrics");
await p
  .getByRole("button", { name: "Transcribe lyrics from song", exact: true })
  .click();
await p.getByLabel("Review transcribed lyrics", { exact: true }).waitFor();
assert.equal(
  await p.getByLabel("Video lyrics", { exact: true }).inputValue(),
  "My existing lyrics",
);
await p
  .getByLabel("Review transcribed lyrics", { exact: true })
  .fill("My corrected line");
await p
  .getByRole("button", {
    name: "Use reviewed lyrics (replace current lyrics)",
    exact: true,
  })
  .click();
assert.equal(
  await p.getByLabel("Video lyrics", { exact: true }).inputValue(),
  "My corrected line",
);
console.log(
  "PASS transcription review does not overwrite lyrics; explicit application uses edited draft",
);
await p.setViewportSize({ width: 390, height: 844 });
await p.screenshot({ path: "/private/tmp/import-ui-mobile.png" });
assert(await p.getByLabel("Import song", { exact: true }).isEnabled());
console.log(
  "PASS import upload, automatic selection, correct duration, visualizer choice, reload, mobile control",
);
await b.close();
