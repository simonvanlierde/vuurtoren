import { expect, test } from "@playwright/test";

// The browser build's end-to-end smoke: boot the demo (Pyodide + the real FastAPI app
// in a worker) and confirm the seeded household renders — proving the app, not just the
// engine, runs in wasm. Cold boot downloads the runtime + wheels, so timeouts are large.
test("browser build boots the demo and serves the seeded household in wasm", async ({ page }) => {
  test.setTimeout(180_000);
  page.on("console", (m) => console.log(`[console.${m.type()}] ${m.text()}`));
  page.on("pageerror", (e) => console.log(`[pageerror] ${e.message}`));
  await page.goto("/");

  // The gate says what the product is before asking for a 20 MB download.
  await expect(page.getByRole("heading", { name: "vuurtoren" })).toBeVisible();
  await expect(page.getByText(/FIRE planner for Dutch households/i)).toBeVisible();
  // Started from the keyboard: the button keeps focus while the engine loads, the stage
  // is announced, and focus lands in the app once it is ready (WCAG 4.1.3, 2.4.3).
  const start = page.getByRole("button", { name: /start the demo/i });
  await start.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status")).toHaveText(/\S/);
  await expect(start).toBeFocused();
  await expect(start).toHaveAttribute("aria-disabled", "true");

  // A first visit lands on the plan. The provenance stamp comes from
  // GET /api/tax-config?year=…, so it also proves the query string reaches the in-wasm app.
  await expect(page.getByText(/\d+ tax figures with source/i).first()).toBeVisible({
    timeout: 150_000,
  });
  expect(new URL(page.url()).hash).toBe("#plan");
  await expect(page.locator("main")).toBeFocused();

  // A seeded account rendering proves GET /api/accounts was served by the in-wasm app.
  // A hash change keeps the booted worker.
  await page.evaluate(() => {
    window.location.hash = "#today";
  });
  await expect(page.getByText("Cash buffer").first()).toBeVisible({ timeout: 20_000 });
  // Today shows one muted line in place of the price-refresh stat it cannot use.
  await expect(page.getByText(/Live prices need the self-hosted version/)).toBeVisible();
  await expect(page.getByRole("button", { name: /refresh/i })).toHaveCount(0);
});
