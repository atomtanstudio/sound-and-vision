import { chromium } from "@playwright/test";
import assert from "node:assert/strict";
import { readFile, mkdir, writeFile } from "node:fs/promises";
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH,
});
const receipt = {
  date: new Date().toISOString(),
  browser: browser.version(),
  checks: [],
  errors: [],
};
const check = (name, detail) => {
  receipt.checks.push({ name, detail, result: "pass" });
  console.log("PASS", name);
};
const base = process.env.SOUND_VISION_TEST_URL || "http://127.0.0.1:5190";
try {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    colorScheme: "light",
  });
  const page = await context.newPage();
  page.on("pageerror", (e) => { receipt.errors.push(e.message); console.error(e.stack); });
  // Preserve offline UI coverage without spending GPU work on fixture tests.
  await page.route("**/api/**", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Offline test fixture" }),
    }),
  );
  await page.goto(base + "/music");
  await page.waitForFunction(() =>
    Array.from(document.images).every((i) => i.complete && i.naturalWidth > 0),
  );
  assert.equal(await page.locator("html").getAttribute("data-theme"), "light");
  assert.equal(
    await page
      .getByRole("tab", { name: "Simple", exact: true })
      .getAttribute("aria-selected"),
    "true",
  );
  assert.equal(await page.locator(".track").count(), 4);
  assert.equal(await page.locator("audio").count(), 1);
  check(
    "Clean initial state",
    "Simple default; four entries; all covers loaded; one shared player; system Light.",
  );
  const originalWordmark = await page
    .locator(".wordmark")
    .evaluate((el) =>
      Array.from(el.children).map((c) => c.getBoundingClientRect().top),
    );
  assert(Math.abs(originalWordmark[0] - originalWordmark[1]) < 2);
  assert.equal(
    Math.round((await page.locator(".primary-rail").boundingBox()).width),
    264,
  );
  await page
    .getByLabel("Describe your song", { exact: true })
    .fill("Keep this draft while resizing navigation");
  await page
    .getByRole("button", { name: "Collapse navigation", exact: true })
    .press("Enter");
  await page.waitForFunction(
    () =>
      Math.round(
        document.querySelector(".primary-rail").getBoundingClientRect().width,
      ) === 72,
  );
  assert.equal(await page.locator(".wordmark").isVisible(), false);
  assert(
    await page.getByRole("button", { name: "Music", exact: true }).isVisible(),
  );
  await page.reload();
  assert.equal(
    await page
      .getByRole("button", { name: "Expand navigation", exact: true })
      .getAttribute("aria-expanded"),
    "false",
  );
  assert.equal(
    await page.getByLabel("Describe your song", { exact: true }).inputValue(),
    "Keep this draft while resizing navigation",
  );
  await page
    .getByRole("button", { name: "Expand navigation", exact: true })
    .click();
  await page.waitForFunction(
    () =>
      Math.round(
        document.querySelector(".primary-rail").getBoundingClientRect().width,
      ) === 264,
  );
  await page.getByLabel("Describe your song", { exact: true }).fill("");
  assert.equal(
    await page
      .locator(".creator-fields")
      .evaluate((el) => getComputedStyle(el).overflowY),
    "visible",
  );
  assert.equal(await page.locator(".scroll-hint").count(), 0);
  assert.equal(
    await page
      .locator(".create-footer")
      .evaluate((el) => el.parentElement.className),
    "creator",
  );
  assert.equal(
    await page
      .getByLabel("Save new songs to project")
      .locator("option:checked")
      .textContent(),
    "Unsorted",
  );
  check(
    "Navigation and continuous form",
    "264px one-line wordmark, keyboard collapse to72px icons, persisted preference, no draft loss, one creator scroll container, explicit Unsorted project label.",
  );
  await page.getByRole("radio", { name: "Dark", exact: true }).click();
  await page.reload();
  assert.equal(await page.locator("html").getAttribute("data-theme"), "dark");
  await page
    .getByRole("radio", { name: "Dark", exact: true })
    .press("ArrowLeft");
  assert.equal(await page.locator("html").getAttribute("data-theme"), "light");
  check(
    "Appearance",
    "Explicit preference persists after reload; radio keyboard navigation changes theme.",
  );
  await page.getByRole("button", { name: "List view", exact: true }).click();
  assert(await page.locator(".tracks-list").isVisible());
  await page.getByRole("button", { name: "Ready", exact: true }).click();
  assert.equal(await page.locator(".track").count(), 2);
  await page.getByRole("button", { name: "Drafts", exact: true }).click();
  assert.equal(await page.locator(".track").count(), 2);
  await page.getByRole("button", { name: "Favorites", exact: true }).click();
  assert.equal(await page.locator(".track").count(), 1);
  await page.getByRole("button", { name: "All", exact: true }).click();
  await page
    .getByLabel("Search your music", { exact: true })
    .fill("NO RESULTS 498");
  assert(await page.getByText("No matching tracks").isVisible());
  await page
    .getByRole("button", { name: "Clear filters", exact: true })
    .click();
  await page.getByLabel("Filter by project").selectOption("Quiet hours");
  assert.equal(await page.locator(".track").count(), 2);
  await page.getByLabel("Filter by project").selectOption("all");
  await page.getByLabel("Sort music").selectOption("title");
  assert.equal(
    await page.locator(".track").last().getAttribute("data-track"),
    "soft-focus",
  );
  check(
    "Library discovery",
    "Grid/list, ready/draft/favorite filters, project filter, title sort, search empty state/reset.",
  );
  await page
    .getByRole("button", {
      name: "Play Desert Afterglow Amber take",
      exact: true,
    })
    .click();
  await page.waitForFunction(
    () =>
      !document.querySelector("audio").paused &&
      document.querySelector("audio").currentTime > 0,
  );
  await page.getByLabel("Playback position", { exact: true }).fill("65");
  assert(
    Math.abs(
      (await page.locator("audio").evaluate((a) => a.currentTime)) - 65,
    ) < 2,
  );
  await page
    .getByRole("button", {
      name: "Play Desert Afterglow Dusk take",
      exact: true,
    })
    .click();
  await page.waitForFunction(
    () =>
      document.querySelector("audio").currentSrc.includes("-2.mp3") &&
      !document.querySelector("audio").paused,
  );
  await page
    .getByRole("button", { name: "Pause playback", exact: true })
    .click();
  assert(await page.locator("audio").evaluate((a) => a.paused));
  assert(
    Math.abs((await page.locator("audio").evaluate((a) => a.duration)) - 240) <
      0.2,
  );
  await page.getByRole("button", { name: "Next take", exact: true }).click();
  await page.waitForFunction(() =>
    document.querySelector("audio").currentSrc.includes("-1.mp3"),
  );
  assert(await page.locator("audio").evaluate((a) => a.paused));
  check(
    "Real sample playback",
    "Both 240-second MP3s play; seek works; alternating audition plays requested take; next while paused remains paused.",
  );
  await page
    .getByRole("button", { name: "Create 2 takes", exact: true })
    .click();
  assert(await page.getByRole("alert").isVisible());
  await page
    .getByLabel("Describe your song", { exact: true })
    .fill("A quiet piano song about the sea.");
  await page.getByRole("tab", { name: "Advanced", exact: true }).click();
  await page.getByLabel("Song title", { exact: true }).fill("Coastline");
  await page
    .getByLabel("Lyrics", { exact: true })
    .fill("[Verse]\nThe sea is still\n[Chorus]\nWe follow the tide");
  await page.getByText("Generation settings", { exact: true }).click();
  await page.getByLabel("Seed", { exact: true }).fill("9223372036854775807");
  await page.getByLabel("Guidance", { exact: true }).fill("1.25");
  await page.getByLabel("Maximum tokens", { exact: true }).first().fill("10");
  await page
    .getByRole("button", { name: "Create 2 takes", exact: true })
    .click();
  assert(
    (await page.getByRole("alert").textContent()).includes("Token limits"),
  );
  await page.getByLabel("Maximum tokens", { exact: true }).first().fill("9000");
  await page.getByText("Composition", { exact: true }).click();
  await page
    .getByRole("combobox", { name: "Score planning", exact: true })
    .selectOption("melody");
  await page
    .getByLabel("ABC score", { exact: false })
    .fill("X:1\nV:Vocal\nK:C\nCDEF");
  await page
    .getByRole("button", { name: "Create 2 takes", exact: true })
    .click();
  assert.equal(await page.locator(".track").count(), 6);
  const added = await page.evaluate(() =>
    JSON.parse(localStorage.getItem("sv-library-v2")).filter(
      (t) => t.requestId,
    ),
  );
  assert.equal(added.length, 2);
  assert.equal(new Set(added.map((t) => t.id)).size, 2);
  assert.equal(new Set(added.map((t) => t.requestId)).size, 1);
  assert(added.every((t) => !t.audio && t.coverStatus === "requested"));
  await page.locator(`[data-track="${added[0].id}"] .track-title`).click();
  await page.getByLabel("Title", { exact: true }).fill("Coastline edited");
  await page
    .getByRole("combobox", { name: "Project", exact: true })
    .selectOption("Quiet hours");
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Request JSON", exact: true }).click();
  const download = await downloadPromise;
  const request = JSON.parse(await readFile(await download.path(), "utf8"));
  assert.equal(request.title, "Coastline edited");
  assert.equal(request.project, "Quiet hours");
  assert.equal(request.takes.length, 2);
  assert.equal(request.takes[0].song.seed, "9223372036854775807");
  assert.equal(request.takes[1].song.seed, "0");
  assert.equal(request.takes[0].song.cot, "melody");
  assert.equal(request.takes[0].song.cfg_scale, 1.25);
  assert.equal(request.takes[0].generation.semantic.max_tokens, 9000);
  assert.equal(request.takes[0].cover.model, "selected-in-ai-setup");
  assert.equal(request.takes[0].cover.provider, "configured");
  assert.notEqual(request.takes[0].cover.prompt, request.takes[1].cover.prompt);
  assert.equal(request.preparation.lyrics, "provided");
  await page.getByRole("button", { name: "Close dialog", exact: true }).click();
  check(
    "Two-take draft contract",
    "Validates input; saves two distinct drafts, one cover request per take; exports actual edited metadata, score settings and exact 63-bit seeds without precision loss.",
  );
  await page.getByRole("tab", { name: "Simple", exact: true }).click();
  await page.getByRole("button", { name: "1 take", exact: true }).click();
  await page
    .getByLabel("Describe your song", { exact: true })
    .fill("A single new draft");
  await page.getByRole("button", { name: "Create song", exact: true }).click();
  assert.equal(await page.locator(".track").count(), 7);
  await page.reload();
  assert.equal(await page.locator(".track").count(), 7);
  assert.equal(
    await page.getByLabel("Describe your song", { exact: true }).inputValue(),
    "A single new draft",
  );
  await page.getByLabel("Search your music", { exact: true }).fill("Unsorted");
  assert.equal(await page.locator(".track").count(), 2);
  await page.getByRole("button", { name: "Clear search", exact: true }).click();
  check(
    "One-take and persistence",
    "Single version adds exactly one draft; form and library survive reload.",
  );
  await page.getByRole("button", { name: "Home", exact: true }).click();
  await page.getByRole("button", { name: "New project", exact: true }).click();
  await page.getByLabel("Project name").fill("Unsorted");
  await page
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  assert(
    await page
      .getByText("A project with that name already exists.", { exact: true })
      .isVisible(),
  );
  await page.getByLabel("Project name").fill("September sketches");
  await page
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  assert(await page.getByText("No tracks here yet").isVisible());
  await page.getByRole("button", { name: "Home", exact: true }).click();
  assert(
    await page
      .getByRole("button", { name: "September sketches 0 tracks" })
      .isVisible(),
  );
  check(
    "Home and projects",
    "New named project appears on Home and opens a filtered empty library.",
  );
  await page.getByRole("button", { name: "Music", exact: true }).click();
  await page.getByLabel("Filter by project").selectOption("all");
  await page
    .getByRole("button", {
      name: "Options for Desert Afterglow dusk",
      exact: true,
    })
    .click();
  await page.getByRole("button", { name: "Make video", exact: true }).click();
  assert.equal(
    await page
      .getByRole("combobox", { name: "Soundtrack", exact: true })
      .inputValue(),
    "dusk",
  );
  await page.getByLabel("Visualizer video", { exact: true }).check();
  await page.getByRole("button", { name: "Home", exact: true }).click();
  await page.getByRole("button", { name: "Video", exact: true }).click();
  assert(await page.getByLabel("Visualizer video", { exact: true }).isChecked());
  check(
    "Video handoff",
    "Selected take is carried to the Video shell; soundtrack and format survive navigation.",
  );
  const musicVideoEnabled = await page.getByLabel("Lip-sync music video", {exact:true}).isEnabled();
  if (!musicVideoEnabled) {
    assert(await page.getByText("Coming soon", {exact:true}).isVisible());
    await page.goto(base + "/video?film=preserved-project-fixture");
    await page.getByRole("region", {name:"Music video coming soon"}).waitFor();
    assert.equal(await page.getByRole("button", {name:"Review scenes",exact:true}).count(),0);
    await page.getByRole("button", {name:"Make a kinetic lyric video",exact:true}).click();
    assert(await page.getByLabel("Kinetic lyric video",{exact:true}).isChecked());
    assert(!new URL(page.url()).searchParams.has("film"));
    check("Music video release gate", "Disabled Coming soon choice and preserved-project deep link show no scene generation controls; lyric video remains available.");
  } else {
  // These requests stay in the browser's isolated fixture; no production project
  // is created, trashed, restored or sent to the renderer.
  let film = {
    id: "trash-fixture",
    title: "Trash recovery fixture",
    artist: "",
    takeId: "dusk",
    revision: 1,
    cutRevision: 1,
    duration: 10,
    fps: 24,
    continuity: "One person.",
    deletedAt: null,
    exports: [],
    jobs: [],
    scenes: [
      {
        index: 0,
        name: "Opening",
        type: "narrative",
        start: 0,
        end: 10,
        action: "Stand by the window.",
        selected: "",
        continuity: "One person.",
        takes: [],
        referenceUrl: "/covers/amber.png",
        identityReferences: [],
        timing: { leadingRest: 10, uncertainWords: 0, words: [], spans: [] },
      },
    ],
  };
  let deleteOnRender = false,
    conflictOnRender = false,
    acceptedRenders = 0;
  const renderRequests = [];
  await page.route("**/api/films**", async (route) => {
    const req = route.request(),
      path = new URL(req.url()).pathname;
    const reply = (status, body) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(body),
      });
    if (path === "/api/films/credits/preview") return reply(503, { detail: "Offline credits preview fixture" });
    if (path === "/api/films") return reply(200, { films: [film] });
    if (path.endsWith("/restore")) {
      assert.equal(req.postDataJSON().revision, film.revision);
      film = { ...film, deletedAt: null, revision: film.revision + 1 };
      return reply(200, film);
    }
    if (path.endsWith("/recover")) {
      const jobId = path.split("/").at(-2);
      assert.equal(jobId, "failed-scene-fixture");
      film = { ...film, jobs: film.jobs.map((j) => j.id === jobId ? { ...j, state: "queued", phase: "Recovering the same run", queuePosition: 1 } : j) };
      return reply(202, film);
    }
    if (path.endsWith("/generate")) {
      const sceneIndex = Number(path.split("/").at(-2));
      const body = req.postDataJSON();
      renderRequests.push(body);
      if (deleteOnRender) {
        deleteOnRender = false;
        film = { ...film, deletedAt: Date.now(), revision: film.revision + 1 };
      }
      if (film.deletedAt)
        return reply(404, { detail: "Video project is in Trash" });
      if (conflictOnRender) {
        conflictOnRender = false;
        film = { ...film, revision: film.revision + 1 };
        return reply(409, {
          detail: "The film changed. Refresh it before applying this edit.",
        });
      }
      assert.equal(body.revision, film.revision);
      acceptedRenders++;
      film = {
        ...film,
        revision: film.revision + 1,
        jobs: [
          {
            id: body.requestId,
            index: sceneIndex,
            state: "queued",
            phase: "Queued",
            queuePosition: 1,
          },
        ],
        scenes: film.scenes.map((scene) => scene.index === sceneIndex ? {
          ...scene,
          takes: [...scene.takes, { id: body.requestId, label: `Take ${scene.takes.length + 1}`, state: "queued" }],
        } : scene),
      };
      return reply(202, film);
    }
    if (film.deletedAt)
      return reply(404, { detail: "Video project is in Trash" });
    return reply(200, film);
  });
  await page.getByLabel("Lip-sync music video", { exact: true }).check();
  await page
    .getByRole("button", { name: "Render scene", exact: true })
    .waitFor();
  film = { ...film, deletedAt: Date.now(), revision: film.revision + 1 };
  await page
    .getByRole("button", { name: "Restore project", exact: true })
    .waitFor({ timeout: 10000 });
  assert.equal(await page.getByRole("button", { name: /^Render/ }).count(), 0);
  await page
    .getByRole("button", { name: "Restore project", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Render scene", exact: true })
    .waitFor();
  check(
    "Cross-tab project deletion",
    "Polling replaces stale render controls with an actionable restore screen; restoring retains the scene.",
  );

  deleteOnRender = true;
  await page.getByRole("button", { name: /^Render remaining/ }).click();
  await page
    .getByRole("button", { name: "Restore project", exact: true })
    .waitFor();
  assert.equal(acceptedRenders, 0);
  assert.equal(await page.getByRole("button", { name: /^Render/ }).count(), 0);
  await page
    .getByRole("button", { name: "Restore project", exact: true })
    .click();
  conflictOnRender = true;
  await page.getByRole("button", { name: "Render scene", exact: true }).click();
  await page.getByRole("button", { name: "Queued · 1", exact: true }).waitFor();
  assert.equal(acceptedRenders, 1);
  assert.equal(
    renderRequests.at(-1).requestId,
    renderRequests.at(-2).requestId,
  );
  check(
    "Render deletion and revision races",
    "A trashed response removes render controls; after restoration a stale revision refreshes and submits exactly one fixture render.",
  );

  const unrendered = {
    ...film.scenes[0],
    index: 1,
    name: "Next shot",
    start: 10,
    end: 20,
    selected: "",
    takes: [],
  };
  film = {
    ...film,
    jobs: [],
    duration: 20,
    revision: film.revision + 1,
    scenes: [
      {
        ...film.scenes[0],
        selected: "ready-fixture",
        review: "flagged",
        issue: "lip-sync",
        correction: "Keep lips closed.",
        takes: [
          {
            id: "ready-fixture",
            label: "Take 1",
            state: "ready",
            mediaUrl: "/fixture-video.mp4",
            posterUrl: "/covers/amber.png",
            contextUrl: "/fixture-context.mp4",
            checks: {
              aiReview: {
                result: "needs-review",
                summary: "Possible mouthing during the opening rest.",
                findings: [],
                mouth: "possible-mouthing",
              },
            },
          },
        ],
      },
      unrendered,
    ],
  };
  await page
    .getByRole("button", { name: "Review scenes", exact: true })
    .waitFor({ timeout: 10000 });
  await page
    .getByRole("button", { name: "Review scenes", exact: true })
    .click();
  await page
    .getByRole("region", { name: "Music video scene review" })
    .waitFor();
  assert(
    await page
      .getByRole("button", { name: "Build updated film", exact: true })
      .isDisabled(),
  );
  assert(
    await page
      .getByRole("button", { name: "Full film", exact: true })
      .isDisabled(),
  );
  assert(
    await page
      .getByRole("button", { name: "Next scene", exact: true })
      .isEnabled(),
  );
  assert(
    await page
      .getByRole("button", { name: "Scene 2: Next shot", exact: true })
      .isEnabled(),
  );
  assert(
    await page
      .getByText("Possible mouthing during the opening rest.", { exact: true })
      .isVisible(),
  );
  check(
    "Review before full render",
    "One ready scene opens repairs and shows its mouth warning; missing scenes cannot be played or exported.",
  );

  await page.getByRole("button", { name: "Scene 2: Next shot", exact: true }).click();
  assert(await page.getByRole("heading", { name: "Next shot", exact: true }).isVisible());
  assert(await page.getByRole("button", { name: "Play scene", exact: true }).isDisabled());
  assert(await page.getByRole("button", { name: "Render scene", exact: true }).isEnabled());
  await page.getByRole("button", { name: "Render scene", exact: true }).click();
  await page.getByRole("button", { name: "Next", exact: true }).waitFor();
  assert.equal(acceptedRenders, 2);
  assert.equal(film.jobs[0].index, 1);
  assert.equal(film.scenes[0].selected, "ready-fixture");
  check("Unrendered scene selection", "Missing scene opens its controls, cannot play, and queues exactly that scene without touching the ready scene.");

  const failed = { id: "failed-scene-fixture", label: "Take 1", state: "failed", error: "Renderer connection interrupted" };
  film = { ...film, revision: film.revision + 1,
    jobs: [{ id: failed.id, index: 1, state: "failed", phase: "Failed", error: failed.error }],
    scenes: [film.scenes[0], { ...unrendered, takes: [failed] }] };
  await page.getByRole("button", { name: "Scene 2: Next shot · Repair failed", exact: true }).waitFor({timeout:10000});
  await page.getByRole("button", { name: "Previous scene", exact: true }).click();
  await page.getByRole("button", { name: "Scene 2: Next shot · Repair failed", exact: true }).click();
  assert(await page.getByRole("heading", { name: "Next shot", exact: true }).isVisible());
  assert(await page.getByRole("button", { name: "Render new take", exact: true }).isEnabled());
  const sceneEvidence = process.env.SOUND_VISION_EVIDENCE || "/private/tmp/sound-vision-studio-checks";
  await mkdir(sceneEvidence, { recursive: true });
  await page.screenshot({ path: sceneEvidence + "/failed-scene-controls.png" });
  await page.getByRole("button", { name: "Recover existing run", exact: true }).click();
  await page.locator('button[title="Recovering the same run"]').waitFor();
  assert.equal(acceptedRenders, 2);
  assert(await page.getByRole("button", { name: "Recover existing run", exact: true }).isDisabled());
  check("Failed scene recovery", "Failed scene remains selectable, exposes the saved error, and recovers the same job without submitting a new render.");

  film = { ...film, jobs: [{ id: failed.id, index: 1, state: "failed", phase: "Failed", error: failed.error }] };
  await page.getByRole("button", { name: "Render new take", exact: true }).waitFor();
  await page.getByRole("button", { name: "Render new take", exact: true }).click();
  await page.getByRole("button", { name: "Next", exact: true }).waitFor();
  assert.equal(acceptedRenders, 3);
  assert.equal(film.scenes[1].takes[0].id, failed.id);
  assert.equal(film.scenes[1].takes.length, 2);
  check("Failed scene replacement", "A new render preserves the failed attempt and uses the initial-generation endpoint when no completed source take exists.");

  film = {
    ...film,
    deletedAt: Date.now(),
    revision: film.revision + 1,
    jobs: [],
    scenes: [{ ...film.scenes[0], takes: [] }],
  };
  await page.goto(base + "/video?film=trash-fixture");
  await page
    .getByRole("button", { name: "Restore project", exact: true })
    .waitFor();
  assert.equal(await page.getByRole("button", { name: /^Render/ }).count(), 0);
  check(
    "Trashed project deep link",
    "Reloading a trashed project's URL displays Restore project instead of stale scene actions.",
  );
  }
  await page
    .getByRole("button", { name: "Your account, not connected", exact: true })
    .click();
  assert(
    await page.getByText("Not connected", { exact: true }).last().isVisible(),
  );
  await page.keyboard.press("Escape");
  assert.equal(await page.locator("dialog[open]").count(), 0);
  check(
    "Honest account state",
    "Connection panel identifies unavailable sign-in; native dialog closes with Escape.",
  );
  await page.getByRole("button", { name: "Music", exact: true }).click();
  for (const [width, height] of [
    [1920, 1080],
    [1440, 1000],
    [1047, 881],
    [820, 740],
    [390, 844],
    [320, 640],
  ]) {
    await page.setViewportSize({ width, height });
    for (const theme of ["Light", "Dark"]) {
      await page.getByRole("radio", { name: theme, exact: true }).click();
      if (width <= 760)
        await page.getByRole("tab", { name: "Create", exact: true }).click();
      assert(
        await page
          .getByRole("button", { name: "Music", exact: true })
          .isVisible(),
      );
      await page.locator(".create-button").first().scrollIntoViewIfNeeded();
      const box = await page.locator(".create-button").first().boundingBox();
      assert(box.y + box.height <= height - 75, `Create obscured at ${width}`);
      assert(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        `Overflow ${width}`,
      );
      if (width <= 1000) {
        await page
          .getByRole("button", { name: "Expand navigation", exact: true })
          .click();
        await page.waitForFunction(
          () =>
            Math.round(
              document.querySelector(".primary-rail").getBoundingClientRect()
                .width,
            ) === 264,
        );
        assert.equal(
          await page.locator(".workspace-body").evaluate((el) => el.inert),
          true,
        );
        assert(await page.locator(".wordmark").isVisible());
        await page.keyboard.press("Escape");
        assert.equal(
          await page.locator(".workspace-body").evaluate((el) => el.inert),
          false,
        );
        await page
          .getByRole("button", { name: "Expand navigation", exact: true })
          .click();
        await page.getByRole("button", { name: "Music", exact: true }).click();
        assert.equal(await page.locator(".rail-backdrop").count(), 0);
      }
      if (width <= 760) {
        await page.getByRole("tab", { name: /Your music/ }).click();
        assert(
          await page
            .getByLabel("Search your music", { exact: true })
            .isVisible(),
        );
        assert(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        );
      }
    }
  }
  check(
    "Responsive layouts",
    "Both themes at 1920, 1440, 1047, 820, 390, 320 px; no horizontal overflow; Create scrolls into view above player; compact navigation drawer opens/closes with Escape or navigation, and mobile workspace tabs remain usable.",
  );
  assert.equal(receipt.errors.length, 0, receipt.errors.join("\n"));
  check("Runtime", "No uncaught browser errors.");
} finally {
  const evidence =
    process.env.SOUND_VISION_EVIDENCE ||
    "/private/tmp/sound-vision-studio-checks";
  await mkdir(evidence, { recursive: true });
  await writeFile(
    `${evidence}/verification.json`,
    JSON.stringify(receipt, null, 2),
  );
  await browser.close();
}
