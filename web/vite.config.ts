import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The dashboard talks to the tiny Python API (web/api_server.py). Vite proxies
// /api and /health to it so the frontend and API share an origin in dev.
const API_PORT = process.env.API_PORT ?? "18082";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    proxy: {
      "/api": { target: `http://127.0.0.1:${API_PORT}`, changeOrigin: true },
      "/health": { target: `http://127.0.0.1:${API_PORT}`, changeOrigin: true },
    },
  },
});
