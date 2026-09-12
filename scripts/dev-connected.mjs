import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { loadEnv } from "vite";
const env = loadEnv("development", process.cwd(), "");
const children = [];
let stopping = false;
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of children) child.kill("SIGTERM");
  process.exitCode = code;
}
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => stop());
if (env.SOUND_VISION_SSH_HOST) {
  const url = new URL(env.SOUND_VISION_BACKEND_URL || "http://127.0.0.1:5191");
  const token = readFileSync(env.SOUND_VISION_TOKEN_FILE, "utf8").trim();
  const healthy = async () => {
    try {
      return (
        await fetch(new URL("/api/health", url), {
          headers: { Authorization: `Bearer ${token}` },
          signal: AbortSignal.timeout(1000),
        })
      ).ok;
    } catch {
      return false;
    }
  };
  if (!(await healthy())) {
    const tunnel = spawn(
      "ssh",
      [
        "-N",
        "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "ControlMaster=no",
        "-o",
        "ControlPath=none",
        "-o",
        "ControlPersist=no",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ServerAliveInterval=30",
        "-o",
        "ServerAliveCountMax=3",
        "-L",
        `127.0.0.1:${url.port}:127.0.0.1:${env.SOUND_VISION_SSH_REMOTE_PORT || 5191}`,
        env.SOUND_VISION_SSH_HOST,
      ],
      { stdio: ["ignore", "ignore", "inherit"] },
    );
    children.push(tunnel);
    tunnel.on("exit", (code) => {
      if (!stopping) {
        console.error(
          "Music connection closed; restart npm run dev to reconnect.",
        );
        stop(code || 1);
      }
    });
    let ready = false;
    for (let n = 0; n < 20 && !stopping; n++) {
      if (await healthy()) {
        ready = true;
        break;
      }
      await new Promise((r) => setTimeout(r, 500));
    }
    if (!ready) {
      stop(1);
      throw new Error(
        "Could not reach the authenticated music API through SSH.",
      );
    }
  }
  if (env.SOUND_VISION_RENDER_BACKEND_URL && env.SOUND_VISION_SSH_HOST) {
    const render = new URL(env.SOUND_VISION_RENDER_BACKEND_URL);
    let connected = false;
    try {
      connected = (
        await fetch(new URL("/health", render), {
          signal: AbortSignal.timeout(1000),
        })
      ).ok;
    } catch {}
    if (!connected) {
      const tunnel = spawn(
        "ssh",
        [
          "-N",
          "-T",
          "-o",
          "BatchMode=yes",
          "-o",
          "ControlMaster=no",
          "-o",
          "ControlPath=none",
          "-o",
          "ExitOnForwardFailure=yes",
          "-o",
          "ServerAliveInterval=30",
          "-o",
          "ServerAliveCountMax=3",
          "-L",
          `127.0.0.1:${render.port}:127.0.0.1:5192`,
          env.SOUND_VISION_SSH_HOST,
        ],
        { stdio: ["ignore", "ignore", "inherit"] },
      );
      children.push(tunnel);
      tunnel.on("exit", (code) => {
        if (!stopping) {
          console.error(
            "Legion render connection closed; restart npm run dev to reconnect.",
          );
          stop(code || 1);
        }
      });
    }
  }
  console.log("Sound/Vision music backend connected through loopback.");
}
const vite = spawn(
  process.execPath,
  [
    "node_modules/vite/bin/vite.js",
    "--host",
    "127.0.0.1",
    "--port",
    "5190",
    "--strictPort",
  ],
  { stdio: "inherit" },
);
children.push(vite);
vite.on("exit", (code) => stop(code || 0));
