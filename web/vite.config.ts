import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The dashboard talks to the tiny Python API (web/api_server.py). Vite proxies
// /api and /health to it so the frontend and API share an origin in dev.
const API_PORT = process.env.API_PORT ?? "18082";
// The API requires a shared session token; start.sh generates it and exports
// API_TOKEN to both processes so this trusted proxy can inject it — the browser
// never sees it. Empty when running Vite standalone (the API then rejects /api).
const API_TOKEN = process.env.API_TOKEN ?? "";
const apiHeaders = API_TOKEN ? { "X-API-Token": API_TOKEN } : undefined;

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    proxy: {
      "/api": { target: `http://127.0.0.1:${API_PORT}`, changeOrigin: true, headers: apiHeaders },
      "/health": { target: `http://127.0.0.1:${API_PORT}`, changeOrigin: true },
    },
  },
});
