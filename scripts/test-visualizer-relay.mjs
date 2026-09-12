import test from "node:test";
import assert from "node:assert/strict";
import { createServer, request } from "node:http";
import { once } from "node:events";
import { visualizerRelay } from "./video/visualizer-export-relay.mjs";
async function listen(server) {
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  return `http://127.0.0.1:${server.address().port}`;
}
function call(origin, path, body, headers = {}) {
  return new Promise((resolve, reject) => {
    const r = request(
      new URL(path, origin),
      {
        method: body ? "POST" : "GET",
        headers: { host: "localhost:5190", ...headers },
      },
      (res) => {
        const chunks = [];
        res.on("data", (c) => chunks.push(c));
        res.on("end", () =>
          resolve({
            status: res.statusCode,
            body: Buffer.concat(chunks).toString(),
          }),
        );
      },
    );
    r.on("error", reject);
    r.end(body);
  });
}
test("Legion relay sends new jobs remotely, retains local downloads, and rejects cross-site calls", async () => {
  let posted = "",
    requests = 0;
  const backend = createServer(async (req, res) => {
    requests++;
    assert.equal(req.headers.authorization, "Bearer test-token");
    assert.equal(req.headers.host, "localhost:5190");
    for await (const c of req) posted += c;
    res.setHeader("Content-Type", "application/json");
    res.end(
      JSON.stringify(
        req.method === "POST"
          ? { id: "remote-new", renderHost: "Legion" }
          : {
              renderer: "Legion",
              available: true,
              jobs: [{ id: "remote", created: 2 }],
            },
      ),
    );
  });
  const endpoint = await listen(backend);
  const relay = visualizerRelay({
    endpoint,
    token: "test-token",
    legacy: {
      has: (id) => id === "old",
      list: () => [{ id: "old", created: 1 }],
      middleware: (_req, res) => res.end("retained-video"),
    },
  });
  const local = createServer(
    (req, res) => void relay(req, res, () => res.end("next")),
  );
  const origin = await listen(local);
  try {
    const list = await call(origin, "/local-api/visualizer-renders");
    assert.equal(list.status, 200);
    assert.deepEqual(
      JSON.parse(list.body).jobs.map((j) => j.id),
      ["remote", "old"],
    );
    const sent = await call(
      origin,
      "/local-api/visualizer-renders",
      '{"takeId":"example"}',
      { "content-type": "application/json" },
    );
    assert.equal(JSON.parse(sent.body).renderHost, "Legion");
    assert.equal(posted, '{"takeId":"example"}');
    assert.equal(
      (await call(origin, "/local-api/visualizer-renders/old/video")).body,
      "retained-video",
    );
    const denied = await call(origin, "/local-api/visualizer-renders", "{}", {
      origin: "https://example.com",
    });
    assert.equal(denied.status, 403);
    assert.equal(requests, 2);
    backend.closeAllConnections();
    await new Promise((r) => backend.close(r));
    const offline = await call(origin, "/local-api/visualizer-renders");
    assert.equal(offline.status, 503);
    assert.match(offline.body, /Legion renderer is unreachable/);
  } finally {
    local.closeAllConnections();
    await new Promise((r) => local.close(r));
    if (backend.listening) {
      backend.closeAllConnections();
      await new Promise((r) => backend.close(r));
    }
  }
});
