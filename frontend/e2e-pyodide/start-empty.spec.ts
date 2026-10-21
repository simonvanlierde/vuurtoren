import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";

// The way out of the example household, and the restore path it unlocks: the demo
// re-seeds on every boot, so Import only works once the visitor has started empty.
test("start empty, then import a saved export", async ({ page }) => {
  test.setTimeout(240_000);
  await page.goto("/#settings");
  await page.getByRole("button", { name: /start the demo/i }).click();
  await expect(page.getByLabel("Name", { exact: true })).toHaveValue("Example Household", {
    timeout: 150_000,
  });

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export JSON" }).click();
  const file = {
    name: "vuurtoren-export.json",
    mimeType: "application/json",
    buffer: await readFile(await (await download).path()),
  };

  // Import into the seeded database is refused, and the message names the way out.
  await page.getByLabel("Import JSON…").setInputFiles(file);
  await expect(page.getByRole("alert")).toContainText("Start with an empty household");

  // The banner's "Settings is where you replace them" lands on the button.
  await page.getByRole("link", { name: "Settings is where you replace them." }).click();
  await expect(page.getByRole("button", { name: "Start with an empty household" })).toBeFocused();

  await page.getByRole("button", { name: "Start with an empty household" }).click();
  await expect(page.getByRole("button", { name: "Cancel" })).toBeFocused();
  await page.getByRole("button", { name: "Delete and start empty" }).click();
  await expect(page.getByRole("button", { name: "Create household" })).toBeVisible();
  expect(new URL(page.url()).hash).toBe("#today");

  await page.getByRole("button", { name: "Create household" }).click();
  await page.getByLabel("Import JSON…").setInputFiles(file);
  await expect(page.getByText("Import complete.")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByLabel("Name", { exact: true })).toHaveValue("Example Household");
});
