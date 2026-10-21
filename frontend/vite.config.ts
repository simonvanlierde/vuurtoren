/// <reference types="vitest/config" />
import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// One service, one origin: the build lands in src/vuurtoren/static/,
// which FastAPI mounts directly. `npm run dev` proxies /api to the same port
// uvicorn listens on so the browser never sees a second origin.
// GitHub Pages serves a project site under /<repo>/, so the deploy workflow passes that
// path as VITE_BASE (from actions/configure-pages). Defaults to "/" for a root/custom-domain
// site. import.meta.env.BASE_URL then carries it to the worker for its /pyodide/* fetches.
const rawBase = process.env.VITE_BASE || "/";
const base = rawBase.endsWith("/") ? rawBase : `${rawBase}/`;

export default defineConfig({
  base,
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "./src") },
  },
  build: {
    outDir: "../src/vuurtoren/static",
    emptyOutDir: true,
  },
  // The Pyodide worker is an ES module (it imports pyodide + boot.py?raw), so it needs
  // code-splitting — not the default iife worker format. Harmless for the server build.
  worker: { format: "es" },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  test: {
    // Vitest for pure helpers — no jsdom, no component framework. A .tsx test
    // renders through `react-dom/server`, which needs no DOM: enough to assert the markup
    // a field emits, not enough to click anything (that is Playwright's job).
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});
