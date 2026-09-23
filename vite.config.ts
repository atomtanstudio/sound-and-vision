import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { readFileSync, realpathSync } from "node:fs";
import { resolve } from "node:path";
import { createVisualizerExports } from "./scripts/video/visualizer-export-api.mjs";
import { visualizerRelay } from "./scripts/video/visualizer-export-relay.mjs";
import { createKineticExports } from "./scripts/video/kinetic-export-api.mjs";
import { kineticRelay } from "./scripts/video/kinetic-export-relay.mjs";
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const fsAllow = [process.cwd()];
  try {
    fsAllow.push(realpathSync(resolve(process.cwd(), "node_modules")));
  } catch {
    // The dependency directory may not exist during config-only tooling.
  }
  const backend = env.SOUND_VISION_BACKEND_URL;
  const uiHost = env.SOUND_VISION_UI_HOST || "127.0.0.1";
  const uiPort = Number(env.SOUND_VISION_UI_PORT || "5190");
  const publicHosts = (env.SOUND_VISION_UI_PUBLIC_HOSTS || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  const hostNames = new Set([
    "localhost",
    "127.0.0.1",
    ...(uiHost === "0.0.0.0" ? [] : [uiHost]),
    ...publicHosts,
  ]);
  const allowedHosts = [...hostNames].map((host) => `${host}:${uiPort}`);
  const allowedOrigins = [...hostNames].map(
    (host) => `http://${host}:${uiPort}`,
  );
  const token =
    backend && env.SOUND_VISION_TOKEN_FILE
      ? readFileSync(resolve(env.SOUND_VISION_TOKEN_FILE), "utf8").trim()
      : "";
  return {
    optimizeDeps: { include: ["fflate"] },
    plugins: [
      react(),
      {
        name: "soundvision-visualizer-exports",
        configureServer(server) {
          const exports = createVisualizerExports({
            projectRoot: process.cwd(),
            backend,
            token,
            allowedHosts,
            allowedOrigins,
          });
          const kinetic = createKineticExports({
            projectRoot: process.cwd(),
            backend,
            token,
            allowedHosts,
            allowedOrigins,
          });
          server.middlewares.use(
            env.SOUND_VISION_RENDER_BACKEND_URL
              ? visualizerRelay({
                  endpoint: env.SOUND_VISION_RENDER_BACKEND_URL,
                  token,
                  legacy: exports,
                  allowedHosts,
                  allowedOrigins,
                })
              : exports.middleware,
          );
          server.middlewares.use(
            env.SOUND_VISION_RENDER_BACKEND_URL
              ? kineticRelay({
                  endpoint: env.SOUND_VISION_RENDER_BACKEND_URL,
                  token,
                  allowedHosts,
                  allowedOrigins,
                })
              : kinetic.middleware,
          );
          server.httpServer?.once("listening", () => {
            if (!env.SOUND_VISION_RENDER_BACKEND_URL) void exports.start();
            if (!env.SOUND_VISION_RENDER_BACKEND_URL) void kinetic.start();
          });
          server.httpServer?.once("close", () => {
            exports.close();
            kinetic.close();
          });
        },
      },
      {
        name: "soundvision-private-api",
        configureServer(server) {
          server.middlewares.use("/api", (req, res, next) => {
            const origin = req.headers.origin;
            const host = req.headers.host;
            if (
              !host ||
              !allowedHosts.includes(host) ||
              (origin && !allowedOrigins.includes(origin)) ||
              ["cross-site", "same-site"].includes(
                req.headers["sec-fetch-site"] as string,
              )
            ) {
              res.statusCode = 403;
              res.end("Forbidden");
              return;
            }
            if (!backend) {
              res.statusCode = 503;
              res.setHeader("Content-Type", "application/json");
              res.end(
                JSON.stringify({ detail: "Music backend not configured" }),
              );
              return;
            }
            next();
          });
        },
      },
    ],
    server: {
      host: uiHost,
      port: uiPort,
      strictPort: true,
      cors: { origin: allowedOrigins },
      fs: {
        allow: fsAllow,
        deny: [
          ".env",
          ".env.*",
          "*.{crt,pem,key,p12,pfx,cer,der}",
          ".npmrc",
          ".yarnrc.yml",
          "**/.git/**",
          "**/.secrets/**",
          "**/*.token",
          "**/service.env",
          "**/providers.json",
          "**/auth.json",
          "**/deliveries/**",
          "**/.build-archive-*/**",
          "**/docs/**/evidence/**",
        ],
      },
      watch: {
        usePolling: env.SOUND_VISION_UI_POLLING === "true",
        interval: 800,
        ignored: ["**/.build-archive-*/**"],
      },
      proxy: backend
        ? {
            "/api": {
              target: backend,
              changeOrigin: true,
              configure(proxy) {
                proxy.on("proxyReq", (request) =>
                  request.setHeader("Authorization", `Bearer ${token}`),
                );
              },
            },
          }
        : undefined,
    },
  };
});
