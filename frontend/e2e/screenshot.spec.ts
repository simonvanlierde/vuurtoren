import { test } from "@playwright/test";

test("capture README hero", async ({ page }) => {
  test.skip(!process.env.SCREENSHOT, "set SCREENSHOT=1 to capture");
  await page.setViewportSize({ width: 1280, height: 920 });
  await page.goto("/#plan");
  await page.getByRole("tab", { name: "Composition" }).waitFor();
  // let the beam band + chart settle
  await page.waitForTimeout(3000);
  await page.screenshot({ path: "../docs/assets/plan.png", fullPage: false });
});
