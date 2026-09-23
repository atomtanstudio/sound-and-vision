import { request } from "node:http";

function trustedLocalRequest(req, options = {}) {
  const allowedHosts = new Set(
    options.allowedHosts || ["localhost:5190", "127.0.0.1:5190"],
  );
  const allowedOrigins = new Set(
    options.allowedOrigins || [
      "http://localhost:5190",
      "http://127.0.0.1:5190",
    ],
  );
  return (
    allowedHosts.has(req.headers.host || "") &&
    (!req.headers.origin ||
      allowedOrigins.has(req.headers.origin)) &&
    !["cross-site", "same-site"].includes(req.headers["sec-fetch-site"])
  );
}

export function kineticRelay({ endpoint, token, allowedHosts, allowedOrigins }) {
  const origin = new URL(endpoint);
  if (origin.protocol !== "http:" || !["127.0.0.1", "localhost"].includes(origin.hostname))
    throw Error("Renderer must use a loopback SSH tunnel");
  return async (req, res, next) => {
    const url = new URL(req.url, "http://localhost:5190");
    if (!url.pathname.startsWith("/local-api/kinetic-renders")) return next();
    const fail = (status, detail) => {
      if (res.headersSent) return res.destroy();
      res.writeHead(status, { "Content-Type": "application/json", "Cache-Control": "no-store" });
      res.end(JSON.stringify({ detail }));
    };
    if (!trustedLocalRequest(req, { allowedHosts, allowedOrigins }))
      return fail(403, "Forbidden");
    const upstream = request(
      new URL(req.url, origin),
      {
        method: req.method,
        headers: {
          ...req.headers,
          host: "localhost:5190",
          origin: "http://localhost:5190",
          authorization: `Bearer ${token}`,
        },
      },
      (response) => {
        res.writeHead(response.statusCode, response.headers);
        response.pipe(res);
        response.on("error", () => res.destroy());
      },
    );
    upstream.setTimeout(10 * 60 * 1000, () => upstream.destroy(Error("Legion kinetic render request timed out")));
    upstream.on("error", () => fail(503, "Legion renderer is unreachable. Your upload or render may still be running; reconnect to check its status."));
    res.on("close", () => upstream.destroy());
    req.pipe(upstream);
  };
}
