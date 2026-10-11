import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Development: this serves the interface with hot reload and passes the API and media through to the app server
// (SV_SERVER, e.g. http://192.168.1.100:7660). From a network the server is open to (SV_OPEN_NETWORKS) nothing else is
// needed; otherwise copy its key (data/secrets/api-token) to SV_TOKEN_FILE (default ~/.config/sv/token, mode 0600)
// and the proxy carries it.
const SERVER = process.env.SV_SERVER ?? "http://127.0.0.1:7660";
let token = "";
try {
  token = readFileSync(process.env.SV_TOKEN_FILE ?? `${homedir()}/.config/sv/token`, "utf8").trim();
} catch {
  /* no key: fine on an open network */
}
const proxy = {
  target: SERVER,
  changeOrigin: true,
  headers: token ? { Authorization: `Bearer ${token}` } : {},
};

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5480,
    strictPort: true,
    proxy: { "/api/live": { ...proxy, ws: true }, "/api": proxy, "/files": proxy, "/pair": proxy },
  },
});
