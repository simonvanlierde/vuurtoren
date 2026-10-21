import { defineConfig } from "@playwright/test";

// Isolated from playwright.config.ts (which serves the FastAPI build): the browser build
// is pure static files served by `vite preview`, and its Pyodide cold boot is slow, so it
// gets its own config, testDir, and generous timeouts. Run: pnpm exec playwright test
// --config playwright.pyodide.config.ts
export default defineConfig({
  testDir: "e2e-pyodide",
  use: { baseURL: "http://127.0.0.1:8125", locale: "en-US" },
  timeout: 180_000,
  // The boot pulls the Pyodide runtime from the CDN, so a transient network hiccup can
  // fail it. Retry in CI rather than masking real breakage with continue-on-error.
  retries: process.env.CI ? 2 : 0,
  webServer: {
    command:
      "pnpm build:browser && pnpm exec vite preview --mode pyodide --host 127.0.0.1 --port 8125 --strictPort",
    url: "http://127.0.0.1:8125/",
    reuseExistingServer: !process.env.CI,
    timeout: 300_000,
  },
});
