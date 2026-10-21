import { expect, test } from "@playwright/test";

// Run on the Uncertainty lens must simulate the plan on screen: the same request the
// preview beam sends (sliders, floor, tax edits, drawer previews), plus the run knobs.
test("Monte Carlo Run sends the plan on screen", async ({ page }) => {
  await page.goto("/#plan");
  await page.getByRole("tab", { name: "Uncertainty" }).click();
  // The plan request settles 250 ms after the last edit; the preview beam refetching
  // with the new value is the sign it has.
  const settled = page.waitForRequest(
    (r) => r.url().endsWith("/api/project") && r.postDataJSON()?.assumptions?.inflation === 0.035,
  );
  await page.getByRole("textbox", { name: "Inflation" }).fill("3,5");
  await settled;

  await page.getByRole("tab", { name: "Run controls" }).click();
  const posted = page.waitForRequest(
    (r) => r.url().endsWith("/api/project") && r.postDataJSON()?.n_runs === 1000,
  );
  await page.getByRole("button", { name: "Run", exact: true }).click();
  const body = (await posted).postDataJSON();

  expect(body.assumptions.inflation).toBeCloseTo(0.035);
  expect(body.start).toMatch(/^\d{4}-\d{2}-01$/);
  expect(body.mode).toBe("gaussian");
});
