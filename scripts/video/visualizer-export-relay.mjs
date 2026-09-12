import { request } from "node:http";
import { trustedLocalRequest } from "./visualizer-export-api.mjs";
// The editor proxies jobs and MP4 bytes; all new rendering work stays on Legion.
export function visualizerRelay({ endpoint, token, legacy }) {
  const origin = new URL(endpoint);
  if (
    origin.protocol !== "http:" ||
    !["127.0.0.1", "localhost"].includes(origin.hostname)
  )
    throw Error("Renderer must use a loopback SSH tunnel");
  return async (req, res, next) => {
    const url = new URL(req.url, "http://localhost:5190");
    if (!url.pathname.startsWith("/local-api/visualizer-renders"))
      return next();
    const fail = (status, detail) => {
      if (res.headersSent) return res.destroy();
      res.writeHead(status, {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      });
      res.end(JSON.stringify({ detail }));
    };
    if (!trustedLocalRequest(req)) return fail(403, "Forbidden");
    const id = url.pathname.split("/")[3];
    if (id && legacy.has(id)) return legacy.middleware(req, res, next);
    if (!id && req.method === "GET") {
      try {
        const data = await new Promise((resolve, reject) => {
          const upstream = request(
            new URL(req.url, origin),
            {
              headers: {
                Authorization: `Bearer ${token}`,
                Host: "localhost:5190",
              },
            },
            async (response) => {
              try {
                if (response.statusCode !== 200) {
                  response.resume();
                  throw Error(`Legion returned ${response.statusCode}`);
                }
                const parts = [];
                let size = 0;
                for await (const part of response) {
                  size += part.length;
                  if (size > 8 * 1024 ** 2)
                    throw Error("Render history too large");
                  parts.push(part);
                }
                resolve(JSON.parse(Buffer.concat(parts).toString()));
              } catch (error) {
                reject(error);
              }
            },
          );
          upstream.setTimeout(10000, () =>
            upstream.destroy(Error("Render status timed out")),
          );
          upstream.on("error", reject);
          upstream.end();
        });
        data.jobs = [
          ...data.jobs,
          ...legacy.list(url.searchParams.get("takeId")),
        ].sort((a, b) => b.created - a.created);
        res.writeHead(200, {
          "Content-Type": "application/json",
          "Cache-Control": "no-store",
        });
        return res.end(JSON.stringify(data));
      } catch {
        return fail(
          503,
          "Legion renderer is unreachable. Check the render service and SSH connection.",
        );
      }
    }
    const upstream = request(
      new URL(req.url, origin),
      {
        method: req.method,
        headers: {
          ...req.headers,
          host: "localhost:5190",
          authorization: `Bearer ${token}`,
        },
      },
      (response) => {
        res.writeHead(response.statusCode, response.headers);
        response.pipe(res);
        response.on("error", () => res.destroy());
      },
    );
    upstream.setTimeout(30000, () =>
      upstream.destroy(Error("Legion request timed out")),
    );
    upstream.on("error", () =>
      fail(
        503,
        "Legion renderer is unreachable. Your submitted render may still be running; reconnect to check its status.",
      ),
    );
    res.on("close", () => upstream.destroy());
    req.pipe(upstream);
  };
}
