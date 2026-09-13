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
await p.setViewportSize({ width: 390, height: 844 });
await p.screenshot({ path: "/private/tmp/import-ui-mobile.png" });
assert(await p.getByLabel("Import song", { exact: true }).isEnabled());
console.log(
  "PASS import upload, automatic selection, correct duration, visualizer choice, reload, mobile control",
);
await b.close();
