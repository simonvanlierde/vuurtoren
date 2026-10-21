import { defineConfig } from "@playwright/test";

// The smoke test and the first-run onboarding path share
// this config. Both build the frontend into the FastAPI static mount and serve it
// from a throwaway SQLite DB — the exact production shape, no Vite dev server
// involved. `locale: "en-US"` pins every spec to the English dictionary regardless
// of the host's own locale, since accessible names below are English strings.
export default defineConfig({
  testDir: "e2e",
  use: { baseURL: "http://127.0.0.1:8123", locale: "en-US" },
  webServer: [
    {
      command: "pnpm build && cd .. && uv run python scripts/smoke_server.py",
      url: "http://127.0.0.1:8123/api/households",
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
    },
    {
      // No build of its own: VUURTOREN_SMOKE_WAIT polls for the sibling's dist.
      command:
        "cd .. && VUURTOREN_SMOKE_WAIT=1 VUURTOREN_SMOKE_EMPTY=1 VUURTOREN_SMOKE_PORT=8124 uv run python scripts/smoke_server.py",
      url: "http://127.0.0.1:8124/api/households",
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
    },
  ],
});
