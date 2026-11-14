import { expect, test } from "@playwright/test";

for (const locale of ["en-US", "nl-NL"] as const) {
  test.describe(locale, () => {
    test.use({ locale });
    test("detects the browser language and keeps Dutch tax names", async ({ page }) => {
      await page.goto("/#settings");
      const language = locale.startsWith("nl") ? "nl" : "en";
      await expect(page.locator("html")).toHaveAttribute("lang", language);
      await expect(page.locator("#settings-language")).toHaveValue(language);
      await expect(
        page.getByRole("heading", {
          name: language === "nl" ? "Instellingen" : "Settings",
          exact: true,
        }),
      ).toBeVisible();
      await expect(page.getByText("fiscale partners", { exact: true })).toBeVisible();
    });
  });
}

test("switches both bundled catalogs offline and remembers the choice", async ({
  page,
  context,
}) => {
  await page.goto("/#settings");
  await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible();
  await page.waitForLoadState("networkidle");
  const requests: string[] = [];
  page.on("request", (request) => requests.push(request.url()));
  await context.setOffline(true);
  for (const language of ["nl", "en", "nl"]) {
    await page.locator("#settings-language").selectOption(language);
    await expect(page.locator("html")).toHaveAttribute("lang", language);
    await expect(
      page.getByRole("heading", {
        name: language === "nl" ? "Instellingen" : "Settings",
        exact: true,
      }),
    ).toBeVisible();
  }
  expect(requests).toEqual([]);
  expect(await page.evaluate(() => localStorage.getItem("vuurtoren-locale"))).toBe("nl");
  await context.setOffline(false);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Instellingen", exact: true })).toBeVisible();
  await expect(page.locator("#settings-language")).toHaveValue("nl");
});
