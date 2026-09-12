import { chromium } from "@playwright/test";
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
const base = process.env.SOUND_VISION_TEST_URL || "http://127.0.0.1:5190";
const output =
  process.env.SOUND_VISION_EVIDENCE || "/private/tmp/sv-provider-ui";
await mkdir(output, { recursive: true });
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH,
});
const errors = [],
  checks = [];
const check = (name) => {
  checks.push(name);
  console.log("PASS", name);
};
let cfg = {
  provider: "openai",
  textBackend: "ollama",
  textUrl: "http://127.0.0.1:11434",
  textModel: "qwen3.5:4b",
  textUseGpu: false,
  comfyUrl: "http://127.0.0.1:8188",
  imagePreset: "krea2",
  imageModel: "krea2_turbo_fp8_scaled.safetensors",
  textEncoder: "qwen3vl_4b_fp8_scaled.safetensors",
  vae: "qwen_image_vae.safetensors",
  modelRoot: "",
  workflow: null,
  promptNode: "",
  promptInput: "text",
  outputNode: "",
  hasTextApiKey: true,
};
let saved = 0,
  tests = 0;
const jobs = new Map();
try {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
  });
  const page = await context.newPage();
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/api/**", async (route) => {
    const req = route.request(),
      path = new URL(req.url()).pathname;
    const reply = (body, status = 200) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(body),
      });
    if (path === "/api/openai/account")
      return reply({
        available: true,
        connected: true,
        provider: cfg.provider,
        email: cfg.provider === "openai" ? "test@example.invalid" : null,
        plan: "Test",
        images: true,
        models: [{ id: "qwen3.5:4b", name: "Qwen 4B", default: true }],
      });
    if (path === "/api/providers") {
      if (req.method() === "PUT") {
        const body = req.postDataJSON();
        assert(!("hasTextApiKey" in body));
        cfg = { ...body, hasTextApiKey: true };
        saved++;
      }
      return reply({
        config: cfg,
        modelPathsYaml: cfg.modelRoot
          ? "soundvision:\n  base_path: " + JSON.stringify(cfg.modelRoot) + "\n"
          : "",
      });
    }
    if (path === "/api/providers/probe")
      return reply({
        models: [{ id: "qwen3.5:4b" }, { id: "qwen3.5:9b" }],
        comfy: {
          diffusionModels: [
            "krea2_turbo_fp8_scaled.safetensors",
            "my-krea-model.safetensors",
          ],
          checkpoints: ["sdxl.safetensors"],
          textEncoders: ["qwen3vl_4b_fp8_scaled.safetensors"],
          vaes: ["qwen_image_vae.safetensors"],
        },
        textError: null,
        imageError: null,
      });
    if (path === "/api/providers/tests") {
      const body = req.postDataJSON();
      tests++;
      assert(body.config.provider === "local");
      const job = {
        id: body.requestId,
        state: "succeeded",
        result:
          body.kind === "writing"
            ? {
                proposal: {
                  style:
                    "Nocturnal synth-pop with warm male baritone and analog bass.",
                },
                model: "qwen3.5:4b",
              }
            : {
                previewUrl: "/covers/amber.png",
                model: "krea2_turbo_fp8_scaled.safetensors",
              },
      };
      jobs.set(body.requestId, job);
      return reply(job, 202);
    }
    if (path.startsWith("/api/assistance/"))
      return reply(jobs.get(path.split("/").at(-1)));
    return reply({ detail: "Isolated offline fixture" }, 503);
  });
  await page.goto(base + "/music");
  assert.equal(await page.title(), "Sound/Vision — Music");
  await page.getByRole("button", { name: /Your account,/ }).click();
  await page.getByRole("heading", { name: "AI setup", exact: true }).waitFor();
  await page.getByLabel("Local models", { exact: true }).check();
  assert(await page.getByLabel("Text server URL").isVisible());
  assert.equal(
    await page.getByLabel("Text model", { exact: true }).inputValue(),
    "qwen3.5:4b",
  );
  assert.equal(
    await page.getByLabel("Image workflow", { exact: true }).inputValue(),
    "krea2",
  );
  assert.equal(saved, 0);
  assert.equal(tests, 0);
  check("Local selection makes no generation or saved-provider change");
  await page
    .getByRole("button", {
      name: "Test connections & refresh models",
      exact: true,
    })
    .click();
  await page
    .getByText("Both local providers are ready.", { exact: true })
    .waitFor();
  assert.equal(await page.locator("#models-imagemodel option").count(), 2);
  await page
    .getByLabel("Image model", { exact: true })
    .fill("my-krea-model.safetensors");
  assert.equal(await page.locator("#models-imagemodel option").count(), 2);
  check("Actual model choices survive selection edits");
  await page.getByRole("button", { name: "Test writing", exact: true }).click();
  await page
    .getByText("Nocturnal synth-pop with warm male baritone and analog bass.", {
      exact: true,
    })
    .waitFor();
  await page
    .getByRole("button", { name: "Generate test image", exact: true })
    .click();
  await page.getByAltText("Local image generation test").waitFor();
  assert.equal(tests, 2);
  check("Explicit writing and image tests show their results");
  await page
    .getByText("Models stored in another folder", { exact: true })
    .click();
  await page
    .getByLabel("ComfyUI models root", { exact: true })
    .fill("/mnt/my-models");
  await page
    .getByRole("button", { name: "Save AI setup", exact: true })
    .click();
  await page.getByText("AI setup saved.", { exact: true }).waitFor();
  assert.equal(cfg.provider, "local");
  assert.equal(cfg.imageModel, "my-krea-model.safetensors");
  assert.equal(saved, 1);
  assert(
    await page
      .getByRole("button", {
        name: "Download model-folder configuration",
        exact: true,
      })
      .isVisible(),
  );
  check(
    "Provider and model folder settings persist without returning an API key",
  );
  await page
    .getByLabel("Image workflow", { exact: true })
    .selectOption("custom");
  const workflow = {
    1: {
      class_type: "CLIPTextEncode",
      inputs: { text: "original prompt", clip: ["2", 1] },
    },
    2: {
      class_type: "CheckpointLoaderSimple",
      inputs: { ckpt_name: "sdxl.safetensors" },
    },
    3: {
      class_type: "SaveImage",
      inputs: { images: ["4", 0], filename_prefix: "test" },
    },
  };
  await page
    .getByLabel("API workflow JSON", { exact: true })
    .setInputFiles({
      name: "workflow.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(workflow)),
    });
  assert.equal(
    await page.getByLabel("Image output", { exact: true }).inputValue(),
    "3",
  );
  assert.equal(
    await page
      .getByLabel("Positive prompt field", { exact: true })
      .inputValue(),
    JSON.stringify(["1", "text"]),
  );
  check("API workflow import discovers prompt and output bindings");
  await page
    .getByLabel("Image workflow", { exact: true })
    .selectOption("krea2");
  await page
    .getByLabel("ComfyUI URL", { exact: true })
    .scrollIntoViewIfNeeded();
  await page.screenshot({ path: output + "/desktop.png" });
  await page.setViewportSize({ width: 390, height: 844 });
  await page
    .getByRole("button", { name: "Save AI setup", exact: true })
    .scrollIntoViewIfNeeded();
  await page.screenshot({ path: output + "/mobile.png" });
  const overflow = await page.evaluate(() => ({
    width: innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
    elements: [...document.querySelectorAll("body *")]
      .filter((e) => e.getBoundingClientRect().right > innerWidth)
      .map((e) => ({
        tag: e.tagName,
        cls: e.className,
        width: e.getBoundingClientRect().width,
        text: e.textContent.slice(0, 70),
      }))
      .slice(-12),
  }));
  assert(overflow.scrollWidth <= overflow.width, JSON.stringify(overflow));
  await page
    .getByLabel("Local models", { exact: true })
    .scrollIntoViewIfNeeded();
  assert(
    await page
      .locator(".modal")
      .evaluate((e) => e.scrollWidth <= e.clientWidth),
  );
  await page.screenshot({ path: output + "/mobile-top.png" });
  assert.equal(await page.locator("vite-error-overlay").count(), 0);
  assert.deepEqual(errors, []);
  check("Desktop and mobile setup stay usable without runtime errors");
} finally {
  await writeFile(
    output + "/checks.json",
    JSON.stringify({ checks, errors }, null, 2),
  );
  await browser.close();
}
