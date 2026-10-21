import { expect, type Locator, type Page, test } from "@playwright/test";

/**
 * The one smoke test: visit all four surfaces
 * against a seeded example household, assert each shows a non-zero headline
 * figure, and that nothing errored in the console along the way.
 */

// A rendered figure with at least one significant digit — catches the class of
// bug where a shape mismatch renders €0.00 everywhere (the run-0 matrix bug).
async function expectNonZeroFigure(figure: Locator) {
  await expect(figure).toHaveText(/[1-9]/, { timeout: 20_000 });
}

function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(`console: ${msg.text()}`);
  });
  return errors;
}

test("all surfaces render non-zero headlines and no console errors", async ({ page }) => {
  const errors = collectErrors(page);

  // Today (accounts): total net worth.
  await page.goto("/#today");
  await expectNonZeroFigure(page.locator("dd.text-3xl").first());

  // Today: rename an account through the drawer.
  await page.getByRole("button", { name: "Edit" }).first().click();
  const drawer = page.getByRole("dialog");
  await expect(drawer).toBeVisible();
  await drawer.getByLabel("Name").fill("Renamed account");
  await drawer.getByRole("button", { name: "Save", exact: true }).click();
  await expect(drawer).not.toBeVisible();
  await expect(page.getByRole("cell", { name: "Renamed account", exact: true })).toBeVisible();

  // Legacy hash redirects.
  await page.goto("/#accounts");
  await expectNonZeroFigure(page.locator("dd.text-3xl").first());

  // Plan — Composition lens (default): headline strip figure + the beam chart.
  await page.goto("/#plan");
  await expectNonZeroFigure(page.locator("dd.text-2xl").first());
  await expect(page.locator("svg").first()).toBeVisible();

  // Plan — add a milestone from the deck, with a live create-preview.
  await page.getByRole("tab", { name: "Milestones" }).click();
  await page.getByRole("button", { name: "+ milestone" }).click();
  const milestoneDrawer = page.getByRole("dialog");
  // Unique per run: with reuseExistingServer, a second local run against the same
  // seeded database would otherwise find two "Test windfall" chips and fail strict mode.
  const windfallLabel = `Test windfall ${Date.now()}`;
  await milestoneDrawer.getByLabel("Label").fill(windfallLabel);
  await milestoneDrawer.getByRole("button", { name: "Lump sum in" }).click();
  await milestoneDrawer.getByLabel("Date", { exact: true }).fill("2030-01-01");
  await milestoneDrawer.getByLabel("Amount (EUR)").fill("50000");
  await milestoneDrawer.getByRole("button", { name: "Save", exact: true }).click();
  await expect(milestoneDrawer).not.toBeVisible();
  // The beam chart also gets a "Milestone: {label}" marker once the new milestone
  // falls inside the horizon — anchor to the chip's own accessible name.
  await expect(page.getByRole("button", { name: new RegExp(`^${windfallLabel}`) })).toBeVisible();

  // Legacy Timeline hash lands on Plan with the strip visible.
  await page.goto("/#timeline");
  await expectNonZeroFigure(page.locator("dd.text-2xl").first());

  // Plan — Uncertainty lens: run Monte Carlo from the deck's Run controls tab.
  await page.getByRole("tab", { name: "Uncertainty" }).click();
  await page.getByRole("tab", { name: "Run controls" }).click();
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page.locator("dd.text-2xl").nth(2)).toHaveText(/%/, { timeout: 60_000 });

  // Plan — Scenarios lens: end-state deck tab shows the baseline row.
  await page.getByRole("tab", { name: "Scenarios" }).click();
  await expect(page.getByRole("tab", { name: "End state" })).toBeVisible();
  await expectNonZeroFigure(page.locator("td.tabular-nums").first());

  // Flows: this year's income total.
  await page.goto("/#flows");
  await expectNonZeroFigure(page.locator(".tabular-nums").first());

  // Settings renders both controls.
  await page.goto("/#settings");
  await expect(page.getByLabel("Language")).toBeVisible();
  await expect(page.getByLabel("Theme")).toBeVisible();

  // Deep-hash lens selection: Uncertainty tab selected on monte-carlo hash.
  await page.goto("/#monte-carlo");
  await expect(page.getByRole("tab", { name: "Uncertainty" })).toHaveAttribute(
    "aria-selected",
    "true",
  );

  // Deep-hash lens selection: Scenarios tab selected on scenarios hash.
  await page.goto("/#scenarios");
  await expect(page.getByRole("tab", { name: "Scenarios" })).toHaveAttribute(
    "aria-selected",
    "true",
  );

  expect(errors).toEqual([]);
});
