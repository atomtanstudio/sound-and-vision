import { chromium, expect } from "@playwright/test";
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
let nextState = "failed";
let nextLyrics = "A misheard line";
let polls = 0;
let rejectSubmit = false;
let sequence = 0;
await p.route("**/api/video/jobs/*/retry", async (r) => {
  transcriptJobs = [
    {
      ...transcriptJobs[0],
      id: "retry-001",
      state: "running",
      error: null,
      result: { phase: "Recognizing the isolated vocal" },
    },
  ];
  await r.fulfill({ status: 202, json: transcriptJobs[0] });
});
await p.route("**/api/takes/*/video", async (r) => {
  if (r.request().method() === "POST") {
    const input = r.request().postDataJSON();
    if (rejectSubmit) {
      await r.fulfill({
        status: 503,
        json: { detail: "Transcription service unavailable" },
      });
      return;
    }
    transcriptJobs = [
      {
        id: `transcript-test-${++sequence}`,
        kind: "lyric-transcription",
        state: nextState,
        error:
          nextState === "failed"
            ? "Object of type int64 is not JSON serializable"
            : null,
        input,
        result: {
          lyrics: nextLyrics,
          duration: 93,
          requiresReview: true,
        },
      },
    ];
    await r.fulfill({ status: 202, json: transcriptJobs[0] });
  } else {
    polls++;
    await r.fulfill({
      json: { jobs: transcriptJobs, alignmentInstalled: true },
    });
  }
});
await p.goto("http://127.0.0.1:5190/video");
await p.getByLabel("Import song", { exact: true }).setInputFiles({
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
await expect(
  p.getByRole("button", { name: "Transcribe lyrics from song", exact: true }),
).toBeVisible();
await p
  .getByRole("button", { name: "Paste or type lyrics", exact: true })
  .click();
await p.getByLabel("Video lyrics", { exact: true }).fill("My existing lyrics");
await p
  .getByRole("button", { name: "Transcribe lyrics from song", exact: true })
  .click();
await expect(
  p.getByText("Transcription failed", { exact: true }),
).toBeVisible();
await expect(
  p.getByText("Object of type int64 is not JSON serializable", { exact: true }),
).toBeVisible();
await p
  .getByRole("button", { name: "Retry transcription", exact: true })
  .click();
await expect(
  p.getByText("Recognizing the isolated vocal", { exact: true }),
).toBeVisible();
await expect(
  p.getByRole("button", { name: "Transcribing song…", exact: true }),
).toBeDisabled();
transcriptJobs = [
  {
    ...transcriptJobs[0],
    state: "succeeded",
    result: { lyrics: nextLyrics, duration: 93, requiresReview: true },
  },
];
await p.getByLabel("Review transcribed lyrics", { exact: true }).waitFor();
assert.equal(
  await p.getByLabel("Video lyrics", { exact: true }).inputValue(),
  "My existing lyrics",
);
await p
  .getByLabel("Review transcribed lyrics", { exact: true })
  .fill("My corrected line");
await p.reload();
await expect(
  p.getByLabel("Review transcribed lyrics", { exact: true }),
).toHaveValue("My corrected line");
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
// A completed empty result must be explicit, and request errors must survive successful polling.
nextState = "succeeded";
nextLyrics = "";
await p
  .getByRole("button", { name: "Transcribe lyrics from song", exact: true })
  .click();
await expect(
  p.getByText("No lyrics were recognized", { exact: true }),
).toBeVisible();
rejectSubmit = true;
await p
  .getByRole("button", { name: "Transcribe lyrics from song", exact: true })
  .click();
await expect(
  p.getByText("Transcription service unavailable", { exact: true }),
).toBeVisible();
const beforePolls = polls;
await expect
  .poll(() => polls, { timeout: 10000 })
  .toBeGreaterThan(beforePolls + 1);
await expect(
  p.getByText("Transcription service unavailable", { exact: true }),
).toBeVisible();
await expect(p.getByLabel("Video lyrics", { exact: true })).toHaveValue(
  "My corrected line",
);
console.log(
  "PASS visible failure, retry, progress, empty result, persistent request errors, review draft reload",
);
await p.setViewportSize({ width: 390, height: 844 });
await p
  .getByRole("heading", { name: "Soundtrack", exact: true })
  .scrollIntoViewIfNeeded();
await p.screenshot({ path: "/private/tmp/import-ui-mobile.png" });
assert(
  await p.evaluate(
    () => document.documentElement.scrollWidth <= window.innerWidth,
  ),
);
assert(await p.getByLabel("Import song", { exact: true }).isEnabled());
console.log(
  "PASS import upload, automatic selection, correct duration, visualizer choice, reload, mobile control",
);
await b.close();
