import { expect, test } from "@playwright/test";

for (const { locale, name, floor, solvency, both } of [
  {
    locale: "en-US",
    name: /^Net worth from/,
    floor: "Bequest floor (€)",
    solvency: /cash lasts to the end/,
    both: /In 0% of 750 runs, the plan stays solvent and meets the bequest floor/,
  },
  {
    locale: "nl-NL",
    name: /^Vermogen van/,
    floor: "Nalatenschapsdrempel (€)",
    solvency: /ontstaat geen kastekort/,
    both: /In 0% van de 750 paden blijft het plan solvabel en haalt het de nalatenschapsdrempel/,
  },
]) {
  test.describe(locale, () => {
    test.use({ locale });
    test("Composition explains success with and without a bequest floor", async ({ page }) => {
      await page.goto("/#plan");
      const chart = page.getByRole("group", { name });
      await expect(chart).toHaveAccessibleName(solvency);
      await page.getByLabel(floor, { exact: true }).fill("1000000000");
      await expect(chart).toHaveAccessibleName(both);
      await page.getByLabel(floor, { exact: true }).fill("");
      await expect(chart).toHaveAccessibleName(solvency);
    });
  });
}
