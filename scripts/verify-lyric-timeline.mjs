import { chromium, expect } from "@playwright/test";
import assert from "node:assert/strict";

// Isolated library and audio fixtures: no user jobs or drafts are touched.
const browser = await chromium.launch({
  executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH,
});
const id = "b".repeat(32),
  lyrics = "Stay right here\nLost line\nBring me home";
const words = (text, times) =>
  text.split(" ").map((text, i) => ({
    text,
    start: times[i]?.[0] ?? null,
    end: times[i]?.[1] ?? null,
    confidence: times[i] ? 1 : 0,
    review: times[i] ? null : "Missing timing",
  }));
const alignment = {
  lyrics,
  duration: 31,
  wordCount: 8,
  reviewCount: 2,
  cues: [
    {
      id: "line-0",
      text: "Stay right here",
      words: words("Stay right here", [
        [1, 1.5],
        [2, 2.5],
        [3, 4],
      ]),
    },
    { id: "line-1", text: "Lost line", words: words("Lost line", []) },
    {
      id: "line-2",
      text: "Bring me home",
      words: words("Bring me home", [
        [15, 15.5],
        [16, 16.5],
        [17, 18],
      ]),
    },
  ],
};
const rate = 8000,
  samples = 31 * rate,
  wav = Buffer.alloc(44 + samples * 2);
wav.write("RIFF");
wav.writeUInt32LE(wav.length - 8, 4);
wav.write("WAVEfmt ", 8);
wav.writeUInt32LE(16, 16);
wav.writeUInt16LE(1, 20);
wav.writeUInt16LE(1, 22);
wav.writeUInt32LE(rate, 24);
wav.writeUInt32LE(rate * 2, 28);
wav.writeUInt16LE(2, 32);
wav.writeUInt16LE(16, 34);
wav.write("data", 36);
wav.writeUInt32LE(samples * 2, 40);
for (let i = 0; i < samples; i++)
  wav.writeInt16LE(
    Math.round(
      Math.sin((i * 2 * Math.PI * 220) / rate) *
        (5000 + 2000 * Math.cos((i / rate) * 5)),
    ),
    44 + i * 2,
  );
try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1100 },
  });
  const errors = [];
  page.on("pageerror", (e) => (errors.push(e.message), console.error(e.stack)));
  await page.route("**/api/**", (r) =>
    r.fulfill({ status: 503, json: { detail: "Isolated fixture" } }),
  );
  await page.route("**/api/health", (r) =>
    r.fulfill({
      json: {
        connected: true,
        generation: false,
        writing: false,
        covers: false,
      },
    }),
  );
  await page.route("**/api/library?*", (r) =>
    r.fulfill({
      json: {
        tracks: [
          {
            id,
            source: "imported",
            title: "Timing review",
            project: "Imported songs",
            subtitle: "Imported song",
            duration: 31,
            audioUrl: `/api/takes/${id}/files/audio.mp3`,
            status: "succeeded",
            form: { title: "Timing review", lyrics },
          },
        ],
      },
    }),
  );
  let brokenAudio = false;
  let brokenVocal = false;
  await page.route("**/api/takes/*/vocal-preview", (r) =>
    r.fulfill({ json: { available: true } }),
  );
  const vocalWav = Buffer.from(wav);
  for (let i = 44; i < vocalWav.length; i += 2)
    vocalWav.writeInt16LE(Math.round(vocalWav.readInt16LE(i) * 0.2), i);
  await page.route("**/api/takes/*/vocal-preview/audio", (r) => {
    if (brokenVocal) return r.fulfill({ status: 404 });
    const range = r
      .request()
      .headers()
      .range?.match(/bytes=(\d+)-(\d*)/);
    const start = range ? Number(range[1]) : 0,
      end = range?.[2] ? Number(range[2]) : vocalWav.length - 1;
    const body = vocalWav.subarray(start, end + 1);
    return r.fulfill({
      status: range ? 206 : 200,
      contentType: "audio/wav",
      body,
      headers: {
        "accept-ranges": "bytes",
        "content-length": String(body.length),
        ...(range
          ? { "content-range": `bytes ${start}-${end}/${vocalWav.length}` }
          : {}),
      },
    });
  });
  await page.route("**/api/takes/*/files/audio.mp3", (r) => {
    if (brokenAudio) return r.fulfill({ status: 404 });
    const range = r
      .request()
      .headers()
      .range?.match(/bytes=(\d+)-(\d*)/);
    const start = range ? Number(range[1]) : 0,
      end = range?.[2] ? Number(range[2]) : wav.length - 1;
    const body = wav.subarray(start, end + 1);
    return r.fulfill({
      status: range ? 206 : 200,
      contentType: "audio/wav",
      body,
      headers: {
        "accept-ranges": "bytes",
        "content-length": String(body.length),
        ...(range
          ? { "content-range": `bytes ${start}-${end}/${wav.length}` }
          : {}),
      },
    });
  });
  await page.route("**/api/takes/*/video", (r) =>
    r.fulfill({
      json: {
        alignmentInstalled: true,
        jobs: [
          {
            id: "timing",
            kind: "lyric-alignment",
            state: "succeeded",
            input: { takeId: id, lyrics, language: "en" },
            result: alignment,
          },
        ],
      },
    }),
  );
  let jobs = [],
    submitted = null;
  await page.route("**/api/takes/*/music-video**", (r) => {
    if (r.request().method() === "GET") return r.fulfill({ json: { jobs } });
    const input = r.request().postDataJSON(),
      kind = r.request().url().split("/").at(-1);
    const job = {
      id: `${kind}-${jobs.length}`,
      kind: `song-video-${kind}`,
      state: "succeeded",
      input,
      result:
        kind === "theme"
          ? { theme: "Copper light and rain in an empty city" }
          : kind === "plan"
            ? {
                ...input,
                duration: 31,
                clipCount: 3,
                fullClipCount: 3,
                scenes: [1, 2, 3].map((i) => ({
                  name: `Scene ${i}`,
                  prompt: "Rain and copper light",
                })),
              }
            : { phase: "Fixture render accepted" },
    };
    if (kind === "render") {
      submitted = input;
      job.state = "running";
    }
    jobs.push(job);
    return r.fulfill({ json: job, status: 202 });
  });
  await page.goto("http://127.0.0.1:5190/video");
  await page
    .getByRole("button", { name: "Edit lyric timing", exact: true })
    .click({ timeout: 10000 })
    .catch(async (error) => {
      console.error(await page.locator("body").innerText());
      throw error;
    });
  const editor = page.getByRole("region", {
    name: "Lyric timing editor",
    exact: true,
  });
  await expect(editor.locator(".lyric-waveform path")).toHaveAttribute(
    "d",
    /M/,
  );
  const source = page.locator("audio:not([data-vocal-monitor])");
  const persisted = () =>
    page.evaluate(
      (id) => JSON.parse(localStorage.getItem(`sv-video-draft-v1:${id}`)),
      id,
    );
  await expect(
    editor.getByText("6 words timed · 2 missing · 0 conflicts", {
      exact: true,
    }),
  ).toBeVisible();
  const block = editor.getByRole("button", {
    name: "Move line 1: Stay right here",
    exact: true,
  });
  await block.click({ trial: true });
  const box = await block.boundingBox(),
    width = await editor
      .locator(".lyric-line-track")
      .evaluate((e) => e.clientWidth);
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(
    box.x + box.width / 2 + (width * 2) / 20,
    box.y + box.height / 2,
    { steps: 8 },
  );
  await page.mouse.up();
  await expect
    .poll(async () => (await persisted()).wordEdits["line-0:0"]?.start)
    .toBeCloseTo(3, 1);
  let edits = (await persisted()).wordEdits;
  assert(
    Math.abs(edits["line-0:1"].start - edits["line-0:0"].end - 0.5) < 0.01,
  );
  await editor.getByRole("button", { name: "Undo timing change" }).click();
  await expect
    .poll(async () => Object.keys((await persisted()).wordEdits).length)
    .toBe(0);
  await editor.getByRole("button", { name: "Redo timing change" }).click();
  await expect
    .poll(async () => (await persisted()).wordEdits["line-0:0"]?.start)
    .toBeCloseTo(3, 1);
  await block.focus();
  await page.keyboard.press("ArrowRight");
  await expect
    .poll(async () => (await persisted()).wordEdits["line-0:0"]?.start)
    .toBeCloseTo(edits["line-0:0"].start + 0.05, 2);
  await editor.getByRole("button", { name: "Reset line", exact: true }).click();
  // Moving just one word and resizing its end do not move the other words.
  const wordBlock = editor.getByRole("button", {
    name: "Move word 1: Stay",
    exact: true,
  });
  await wordBlock.focus();
  await page.keyboard.press("ArrowRight");
  await expect(
    editor.getByLabel("Selected word start", { exact: true }),
  ).toHaveValue("1.05");
  const edgeControl = editor.getByRole("button", {
    name: "Drag Stay end",
    exact: true,
  });
  await edgeControl.click({ trial: true });
  const edge = await edgeControl.boundingBox();
  await page.mouse.move(edge.x + edge.width / 2, edge.y + edge.height / 2);
  await page.mouse.down();
  await page.mouse.move(
    edge.x + edge.width / 2 + (width * 0.2) / 20,
    edge.y + edge.height / 2,
  );
  await page.mouse.up();
  await expect
    .poll(async () =>
      Number(
        await editor
          .getByLabel("Selected word end", { exact: true })
          .inputValue(),
      ),
    )
    .toBeCloseTo(1.75, 1);
  await editor.getByRole("button", { name: "Reset line", exact: true }).click();

  // Scrubbing controls the actual shared audio; untimed lyrics are repaired by explicit taps.
  const waveform = editor.getByRole("slider", {
    name: "Audio waveform playhead",
  });
  async function scrub(time) {
    const box = await waveform.boundingBox();
    const offset = Number(
      await editor
        .getByLabel("Timeline window start", { exact: true })
        .inputValue(),
    );
    const span = Math.min(
      31,
      Number(
        await editor.getByLabel("Timeline zoom", { exact: true }).inputValue(),
      ),
    );
    await waveform.click({
      position: { x: (box.width * (time - offset)) / span, y: 30 },
    });
    await expect
      .poll(async () => Number(await waveform.getAttribute("aria-valuenow")))
      .toBeCloseTo(time, 1)
      .catch(async (error) => {
        console.error(
          await source.evaluate((a) => ({
            src: a.currentSrc,
            time: a.currentTime,
            duration: a.duration,
            ready: a.readyState,
            error: a.error?.message,
            seekable: Array.from({ length: a.seekable.length }, (_, i) => [
              a.seekable.start(i),
              a.seekable.end(i),
            ]),
          })),
        );
        console.error(await editor.innerText());
        throw error;
      });
    await expect
      .poll(async () => source.evaluate((a) => a.currentTime))
      .toBeCloseTo(time, 1);
  }
  // The per-phrase button must not select/seek the row before placing all its words.
  const phraseRow = (text) =>
    editor.getByRole("group", { name: text, exact: true });
  await scrub(8);
  await phraseRow("Phrase 2: Lost line")
    .getByRole("button", { name: "Insert at playhead", exact: true })
    .click();
  await expect(
    editor.getByRole("heading", { name: "2. Lost line", exact: true }),
  ).toBeVisible();
  let placed = (await persisted()).lyricRevision.alignment;
  assert.equal(placed.cues.length, 3);
  assert.equal(placed.cues[1].words.length, 2);
  assert(Math.abs(placed.cues[1].words[0].start - 8) < 0.05);
  assert(
    placed.cues[1].words.every(
      (w) =>
        w.start !== null &&
        w.end !== null &&
        w.review.includes("Manual phrase placement"),
    ),
  );
  assert(Math.abs((await source.evaluate((a) => a.currentTime)) - 8) < 0.05);
  await expect(
    editor.getByRole("region", { name: "Live lyric preview", exact: true }),
  ).toContainText("Lost line");
  await expect(
    editor.getByRole("button", { name: "Move line 2: Lost line", exact: true }),
  ).toHaveCount(1);
  await scrub(9);
  await phraseRow("Phrase 2: Lost line")
    .getByRole("button", { name: "Insert at playhead", exact: true })
    .click();
  assert.equal((await persisted()).lyricRevision.alignment.cues.length, 3);
  await editor.getByRole("button", { name: "Undo timing change" }).click();
  await editor.getByRole("button", { name: "Undo timing change" }).click();
  await expect(
    editor.getByText("6 words timed · 2 missing · 0 conflicts", {
      exact: true,
    }),
  ).toBeVisible();
  await scrub(12);
  await phraseRow("Phrase 1: Stay right here")
    .getByRole("button", { name: "Insert at playhead", exact: true })
    .click();
  placed = (await persisted()).lyricRevision.alignment;
  const moved = placed.cues.find((c) => c.id === "line-0");
  assert(Math.abs(moved.words[0].start - 12) < 0.05);
  assert(Math.abs(moved.words[1].start - moved.words[0].end - 0.5) < 0.001);
  assert(Math.abs((await source.evaluate((a) => a.currentTime)) - 12) < 0.05);
  await editor.getByRole("button", { name: "Undo timing change" }).click();
  await editor.getByLabel("Timeline window start", { exact: true }).fill("0");
  await editor
    .getByRole("button", { name: "Next to review", exact: true })
    .click();
  await expect(
    editor.getByRole("heading", { name: "2. Lost line", exact: true }),
  ).toBeVisible();
  await editor
    .getByRole("button", { name: "Time this line by tapping", exact: true })
    .click();
  await scrub(7);
  await editor
    .getByRole("button", { name: "Mark “Lost”", exact: true })
    .click();
  assert(!Object.hasOwn((await persisted()).wordEdits, "line-1:0"));
  await scrub(8);
  await editor
    .getByRole("button", { name: "Mark “line”", exact: true })
    .click();
  await scrub(9);
  await editor
    .getByRole("button", { name: "Mark line end", exact: true })
    .click();
  await expect(
    editor.getByText("8 words timed · 0 missing · 0 conflicts", {
      exact: true,
    }),
  ).toBeVisible();
  await expect
    .poll(async () => (await persisted()).wordEdits["line-1:1"]?.end)
    .toBeCloseTo(9, 1);
  // Numeric edits remain available for pauses and undo restores an entire tap session.
  await editor.getByRole("button", { name: "Undo timing change" }).click();
  await expect(
    editor.getByText("6 words timed · 2 missing · 0 conflicts", {
      exact: true,
    }),
  ).toBeVisible();
  await editor.getByRole("button", { name: "Redo timing change" }).click();
  await editor.getByLabel("Selected word end", { exact: true }).fill("8.7");
  await page.reload();
  await page
    .getByRole("button", { name: "Edit lyric timing", exact: true })
    .click();
  await expect(
    editor.getByText("8 words timed · 0 missing · 0 conflicts", {
      exact: true,
    }),
  ).toBeVisible();
  assert.equal((await persisted()).wordEdits["line-1:1"].end, 8.7);
  await editor
    .getByRole("button", { name: "Play timing playback", exact: true })
    .click();
  await expect.poll(() => source.evaluate((a) => a.paused)).toBe(false);
  await editor
    .getByRole("button", { name: "Pause timing playback", exact: true })
    .click();
  await expect.poll(() => source.evaluate((a) => a.paused)).toBe(true);
  // The live preview follows exact word boundaries, and hand panning never edits timing.
  await scrub(1.2);
  const live = editor.getByRole("region", {
    name: "Live lyric preview",
    exact: true,
  });
  await expect(live.locator('[aria-current="true"]')).toHaveText("Stay ");
  await scrub(2.2);
  await expect(live.locator('[aria-current="true"]')).toHaveText("right ");
  await scrub(12);
  await expect(
    live.getByText("No timed lyrics here", { exact: true }),
  ).toBeVisible();
  const beforePan = JSON.stringify((await persisted()).wordEdits);
  await editor
    .getByRole("button", { name: "Pan timeline", exact: true })
    .click();
  await waveform.click({ trial: true });
  let panBox = await waveform.boundingBox();
  await page.mouse.move(panBox.x + panBox.width * 0.75, panBox.y + 40);
  await page.mouse.down();
  await page.mouse.move(panBox.x + panBox.width * 0.5, panBox.y + 40, {
    steps: 8,
  });
  await page.mouse.up();
  await expect
    .poll(async () =>
      Number(
        await editor
          .getByLabel("Timeline window start", { exact: true })
          .inputValue(),
      ),
    )
    .toBeCloseTo(5, 1);
  assert.equal(JSON.stringify((await persisted()).wordEdits), beforePan);
  assert(Math.abs((await source.evaluate((a) => a.currentTime)) - 12) < 0.05);
  await editor.getByLabel("Timeline window start", { exact: true }).fill("0");
  await editor
    .getByRole("button", { name: "Select and move lyrics", exact: true })
    .click();
  await scrub(2.2);
  await editor
    .getByLabel("Editing audio", { exact: true })
    .selectOption("vocals");
  const stem = page.locator("audio[data-vocal-monitor]");
  await expect.poll(() => source.evaluate((a) => a.muted)).toBe(true);
  await expect
    .poll(() => stem.evaluate((a) => a.currentTime))
    .toBeCloseTo(2.2, 1);
  await editor
    .getByRole("button", { name: "Play timing playback", exact: true })
    .click();
  await expect.poll(() => stem.evaluate((a) => a.paused)).toBe(false);
  await expect
    .poll(async () =>
      Math.abs(
        (await source.evaluate((a) => a.currentTime)) -
          (await stem.evaluate((a) => a.currentTime)),
      ),
    )
    .toBeLessThan(0.15);
  await editor
    .getByRole("button", { name: "Pause timing playback", exact: true })
    .click();
  await expect.poll(() => stem.evaluate((a) => a.paused)).toBe(true);
  await scrub(8);
  await expect
    .poll(() => stem.evaluate((a) => a.currentTime))
    .toBeCloseTo(8, 1);
  await editor
    .getByRole("button", { name: "Close timing editor", exact: true })
    .click();
  await expect.poll(() => source.evaluate((a) => a.muted)).toBe(false);
  await expect(stem).toHaveCount(0);
  await editor
    .getByRole("button", { name: "Edit lyric timing", exact: true })
    .click();
  brokenVocal = true;
  await editor
    .getByLabel("Editing audio", { exact: true })
    .selectOption("vocals");
  await expect(editor.getByText(/Could not load the vocal stem/)).toBeVisible();
  await expect.poll(() => source.evaluate((a) => a.muted)).toBe(false);
  await expect(editor.getByLabel("Editing audio", { exact: true })).toHaveValue(
    "mix",
  );
  brokenVocal = false;
  await waveform.focus();
  await page.keyboard.press("Space");
  await expect.poll(() => source.evaluate((a) => a.paused)).toBe(false);
  await page.keyboard.press("Space");
  await expect.poll(() => source.evaluate((a) => a.paused)).toBe(true);
  await editor.getByLabel("Timeline zoom", { exact: true }).selectOption("2");
  await expect(
    editor.getByLabel("Timeline window start", { exact: true }),
  ).toHaveAttribute("max", "29");
  await editor.getByLabel("Timeline zoom", { exact: true }).selectOption("10");
  await editor.getByLabel("Timeline window start", { exact: true }).fill("15");
  await expect(
    editor.getByRole("button", {
      name: "Move line 3: Bring me home",
      exact: true,
    }),
  ).toBeVisible();
  await editor.getByLabel("Timeline zoom", { exact: true }).selectOption("20");
  await editor.getByLabel("Timeline window start", { exact: true }).fill("0");
  await editor.screenshot({
    path: "/private/tmp/sv-lyric-timeline-desktop.png",
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() =>
      page
        .locator(".primary-rail")
        .evaluate((e) => Math.round(e.getBoundingClientRect().width)),
    )
    .toBe(72);
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    )
    .toBe(true);
  assert(await editor.evaluate((e) => e.scrollWidth <= e.clientWidth));
  await editor
    .getByRole("heading", { name: "Lyric timing", exact: true })
    .scrollIntoViewIfNeeded();
  await page.screenshot({ path: "/private/tmp/sv-lyric-timeline-mobile.png" });
  await editor
    .getByRole("button", { name: "Time this line by tapping", exact: true })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: "/private/tmp/sv-lyric-timeline-mobile-words.png",
  });
  await page.setViewportSize({ width: 1440, height: 1100 });
  for (const name of [
    "Kinetic lyric video",
    "Visualizer video",
    "Music video",
  ]) {
    await page.getByRole("radio", { name, exact: true }).check();
    await expect(
      editor.getByText("8 words timed · 0 missing · 0 conflicts", {
        exact: true,
      }),
    ).toBeVisible();
  }
  await page
    .getByRole("button", { name: "Prepare video", exact: true })
    .click();
  await page.getByRole("button", { name: "Create video", exact: true }).click();
  await expect.poll(() => submitted !== null).toBe(true);
  assert.equal(submitted.cues.length, 3);
  assert.equal(submitted.cues[1].words[1].end, 8.7);
  assert.equal(submitted.omitUnusableWords, false);
  // Text corrections preserve the current storyboard, word timing, and renderable payload.
  const planId = submitted.planId;
  jobs[jobs.length - 1].state = "succeeded";
  await page
    .getByRole("button", { name: "Edit lyric timing", exact: true })
    .click();
  await editor
    .locator(".lyric-word-picker")
    .getByRole("button", { name: "right", exact: true })
    .click();
  await editor.getByLabel("Selected word start", { exact: true }).fill("2.2");
  await editor
    .locator(".lyric-word-picker")
    .getByRole("button", { name: "Stay", exact: true })
    .click();
  await editor
    .getByRole("button", { name: "Delete word", exact: true })
    .click();
  await expect(page.getByLabel("Video lyrics", { exact: true })).toHaveValue(
    "right here\nLost line\nBring me home",
  );
  let revision = (await persisted()).lyricRevision.alignment;
  assert.equal(revision.cues[0].words[0].start, 2.2);
  assert.equal(revision.cues[1].words[1].end, 8.7);
  await editor.getByRole("button", { name: "Undo timing change" }).click();
  await expect(page.getByLabel("Video lyrics", { exact: true })).toHaveValue(
    lyrics,
  );
  await editor.getByRole("button", { name: "Redo timing change" }).click();
  await expect(page.getByLabel("Video lyrics", { exact: true })).toHaveValue(
    "right here\nLost line\nBring me home",
  );
  await editor
    .getByRole("button", { name: "Delete phrase", exact: true })
    .click();
  await expect(page.getByLabel("Video lyrics", { exact: true })).toHaveValue(
    "Lost line\nBring me home",
  );
  await editor.getByRole("button", { name: "Undo timing change" }).click();
  // A typed phrase starts untimed, then can be duplicated at each repeated vocal.
  await editor.getByLabel("Timeline zoom", { exact: true }).selectOption("31");
  await scrub(20);
  await editor.getByRole("button", { name: "Add phrase", exact: true }).click();
  const phraseForm = editor.getByRole("form", {
    name: "Insert lyric phrase",
    exact: true,
  });
  await phraseForm
    .getByLabel("Phrase text", { exact: true })
    .fill("Megalomaniac");
  await phraseForm
    .getByRole("button", { name: "Insert phrase", exact: true })
    .click();
  await expect(
    editor.getByRole("heading", { name: "4. Megalomaniac", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Create video", exact: true }),
  ).toBeDisabled();
  await editor
    .getByRole("button", { name: "Time this line by tapping", exact: true })
    .click();
  await scrub(20);
  await editor
    .getByRole("button", { name: "Mark “Megalomaniac”", exact: true })
    .click();
  await scrub(21);
  await editor
    .getByRole("button", { name: "Mark line end", exact: true })
    .click();
  for (const time of [24, 28]) {
    await editor
      .getByRole("button", { name: "Duplicate word", exact: true })
      .click();
    await scrub(time);
    await expect(
      phraseForm.getByLabel("Reuse copied timing at playhead", { exact: true }),
    ).toBeChecked();
    await phraseForm
      .getByRole("button", { name: "Insert phrase", exact: true })
      .click();
  }
  const correctedLyrics =
    "right here\nLost line\nBring me home\nMegalomaniac\nMegalomaniac\nMegalomaniac";
  await expect(page.getByLabel("Video lyrics", { exact: true })).toHaveValue(
    correctedLyrics,
  );
  await editor.getByRole("button", { name: "Add phrase", exact: true }).click();
  await phraseForm
    .getByLabel("Phrase text", { exact: true })
    .fill("Bonus phrase\nLast phrase");
  await phraseForm
    .getByLabel("Phrase insert position", { exact: true })
    .selectOption("end");
  await phraseForm
    .getByRole("button", { name: "Insert 2 phrases", exact: true })
    .click();
  assert.equal((await persisted()).lyricRevision.alignment.cues.length, 8);
  await editor.getByRole("button", { name: "Undo timing change" }).click();
  await expect(page.getByLabel("Video lyrics", { exact: true })).toHaveValue(
    correctedLyrics,
  );
  await page.reload();
  await page
    .getByRole("button", { name: "Edit lyric timing", exact: true })
    .click();
  await expect(page.getByLabel("Video lyrics", { exact: true })).toHaveValue(
    correctedLyrics,
  );
  await expect(
    editor.getByText("10 words timed · 0 missing · 0 conflicts", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Prepare video", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Create video", exact: true }).click();
  await expect.poll(() => submitted?.lyrics).toBe(correctedLyrics);
  assert.equal(submitted.planId, planId);
  assert.equal(submitted.cues[0].words[0].start, 2.2);
  assert.equal(submitted.cues[1].words[1].end, 8.7);
  assert.deepEqual(
    submitted.cues.slice(3).map((c) => c.words[0].text),
    ["Megalomaniac", "Megalomaniac", "Megalomaniac"],
  );
  for (const [i, time] of [20, 24, 28].entries())
    assert(Math.abs(submitted.cues[i + 3].words[0].start - time) < 0.05);
  while (await editor.locator(".lyric-line-list > .lyric-line-row").count())
    await editor
      .getByRole("button", { name: "Delete phrase", exact: true })
      .click();
  await expect(editor.getByText(/No lyric words remain/)).toBeVisible();
  await expect(
    editor.getByRole("button", { name: "Add phrase", exact: true }),
  ).toBeEnabled();
  await editor.getByRole("button", { name: "Undo timing change" }).click();
  // A failed waveform fetch leaves the rest of the editor usable.
  brokenAudio = true;
  await page.reload();
  await page
    .getByRole("button", { name: "Edit lyric timing", exact: true })
    .click();
  await expect(editor.getByText(/Waveform unavailable/)).toBeVisible();
  await expect(
    editor.getByLabel("Selected word start", { exact: true }),
  ).toBeEnabled();
  assert.deepEqual(errors, []);
  console.log(
    "PASS real waveform decode, line drag/keyboard, word move/resize, scrubbing, tap repair, undo/redo, persistence, shared playback, zoom/pan, mobile, export payload and waveform failure",
  );
} finally {
  await browser.close();
}
