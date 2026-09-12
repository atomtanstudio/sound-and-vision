import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { createVisualizerExports } from "./scripts/video/visualizer-export-api.mjs";
import { visualizerRelay } from "./scripts/video/visualizer-export-relay.mjs";
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backend = env.SOUND_VISION_BACKEND_URL;
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
          });
          server.middlewares.use(
            env.SOUND_VISION_RENDER_BACKEND_URL
              ? visualizerRelay({
                  endpoint: env.SOUND_VISION_RENDER_BACKEND_URL,
                  token,
                  legacy: exports,
                })
              : exports.middleware,
          );
          server.httpServer?.once("listening", () => {
            if (!env.SOUND_VISION_RENDER_BACKEND_URL) void exports.start();
          });
          server.httpServer?.once("close", exports.close);
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
              !/^(127\.0\.0\.1|localhost):5190$/.test(host) ||
              (origin &&
                !["http://127.0.0.1:5190", "http://localhost:5190"].includes(
                  origin,
                )) ||
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
      host: "127.0.0.1",
      port: 5190,
      strictPort: true,
      cors: { origin: ["http://127.0.0.1:5190", "http://localhost:5190"] },
      fs: {
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
        usePolling: true,
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
