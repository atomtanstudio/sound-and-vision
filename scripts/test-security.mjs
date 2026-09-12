import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, realpath, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { resolveConfig, isFileServingAllowed } from "vite";
import configFactory from "../vite.config.ts";

test("private proxy rejects untrusted browser requests before forwarding", async () => {
  const fixture = await realpath(
    await mkdtemp(join(tmpdir(), "soundvision-security-")),
  );
  const before = process.cwd();
  try {
    process.chdir(fixture); // No operator .env or credential is loaded.
    const config = configFactory({ command: "serve", mode: "test" });
    let guard;
    config.plugins
      .find((p) => p.name === "soundvision-private-api")
      .configureServer({
        middlewares: {
          use(path, handler) {
            assert.equal(path, "/api");
            guard = handler;
          },
        },
      });
    for (const headers of [
      {},
      { host: "example.invalid:5190" },
      { host: "localhost:5190", origin: "https://example.invalid" },
      { host: "localhost:5190", "sec-fetch-site": "cross-site" },
      { host: "localhost:5190", "sec-fetch-site": "same-site" },
    ]) {
      let forwarded = false;
      const response = { statusCode: 200, end() {} };
      guard({ headers }, response, () => {
        forwarded = true;
      });
      assert.equal(response.statusCode, 403);
      assert.equal(forwarded, false);
    }
    for (const host of ["localhost:5190", "127.0.0.1:5190"]) {
      const response = { statusCode: 200, setHeader() {}, end() {} };
      guard(
        {
          headers: {
            host,
            origin: `http://${host}`,
            "sec-fetch-site": "same-origin",
          },
        },
        response,
        () => {},
      );
      assert.equal(response.statusCode, 503); // Valid client; fixture has no backend.
    }
    assert.deepEqual(config.server.cors.origin, [
      "http://127.0.0.1:5190",
      "http://localhost:5190",
    ]);
    const resolved = await resolveConfig(
      { ...config, root: fixture, configFile: false, envDir: false },
      "serve",
    );
    for (const path of [
      ".env.local",
      ".secrets/service.token",
      "providers.json",
      "service.env",
      "auth.json",
      ".git/config",
      "private.key",
      ".npmrc",
      "deliveries/private.json",
      ".build-archive-old/index.html",
      "docs/backend/evidence/receipt.json",
    ]) {
      assert.equal(
        isFileServingAllowed(resolved, join(fixture, path)),
        false,
        path,
      );
    }
    assert.equal(
      isFileServingAllowed(resolved, join(fixture, "src/main.tsx")),
      true,
    );
  } finally {
    process.chdir(before);
    await rm(fixture, { recursive: true, force: true });
  }
});
