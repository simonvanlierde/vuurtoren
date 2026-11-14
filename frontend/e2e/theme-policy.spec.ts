import { expect, test } from "@playwright/test";

test("the production policy allows the saved theme without inline scripts", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript(() => localStorage.setItem("vuurtoren-theme", "dark"));
  await page.goto("/");
  await expect(page.locator("html")).toHaveClass(/dark/);
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
    "href",
    "https://simonvanlierde.com/vuurtoren/",
  );
  await expect(page.locator('meta[http-equiv="Content-Security-Policy"]')).toHaveAttribute(
    "content",
    /script-src 'self' 'wasm-unsafe-eval' https:\/\/cdn\.jsdelivr\.net;/,
  );
  expect(await page.locator("script:not([src])").count()).toBe(0);
  await expect(page.getByRole("button", { name: "Plan", exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});
