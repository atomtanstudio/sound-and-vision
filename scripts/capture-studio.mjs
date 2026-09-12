import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH,
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  colorScheme: "dark",
});
const page = await context.newPage();
page.on("pageerror", (e) => console.error(e.message));
await mkdir("docs/redesign/evidence", { recursive: true });
await page.goto("http://127.0.0.1:5190/music");
await page.evaluate(() => document.fonts.ready);
await page.waitForFunction(() =>
  Array.from(document.images).every((i) => i.complete && i.naturalWidth > 0),
);
for (const [width, height, name] of [
  [1440, 1000, "desktop"],
  [1047, 881, "medium"],
  [390, 844, "mobile"],
]) {
  await page.setViewportSize({ width, height });
  for (const theme of ["Dark", "Light"]) {
    await page.getByRole("radio", { name: theme, exact: true }).click();
    await page.screenshot({
      path: `docs/redesign/evidence/simple-${theme.toLowerCase()}-${name}.png`,
      animations: "disabled",
    });
  }
  if (name === "mobile") {
    await page.getByRole("tab", { name: /Your music/ }).click();
    await page.screenshot({
      path: "docs/redesign/evidence/library-mobile.png",
    });
  }
}
await page.setViewportSize({ width: 1440, height: 1000 });
await page.getByRole("radio", { name: "Dark", exact: true }).click();
await page.getByRole("tab", { name: "Advanced", exact: true }).click();
await page.locator(".creator").evaluate((el) => (el.scrollTop = 0));
await page.screenshot({
  path: "docs/redesign/evidence/advanced-dark-desktop.png",
});
await page
  .getByRole("button", { name: "Collapse navigation", exact: true })
  .click();
await page.waitForFunction(
  () =>
    Math.round(
      document.querySelector(".primary-rail").getBoundingClientRect().width,
    ) === 72,
);
await page.screenshot({
  path: "docs/redesign/evidence/advanced-collapsed-desktop.png",
});
await page.getByRole("button", { name: "List view", exact: true }).click();
await page.screenshot({ path: "docs/redesign/evidence/list-dark-desktop.png" });
await page.getByRole("button", { name: "Home", exact: true }).click();
await page.screenshot({ path: "docs/redesign/evidence/home-dark-desktop.png" });
await browser.close();
console.log(
  "Saved current studio screenshots, including expanded and collapsed navigation",
);
