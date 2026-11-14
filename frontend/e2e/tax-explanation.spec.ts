import { expect, test } from "@playwright/test";
import { expectNoViolations } from "./axe";

for (const locale of ["en-US", "nl-NL"]) {
  test.describe(`Tax explanation (${locale})`, () => {
    test.use({ locale, viewport: { width: 375, height: 812 } });
    test("opens by keyboard, changes tax year and exposes sourced steps", async ({ page }) => {
      const nl = locale === "nl-NL";
      await page.goto("/#plan");
      const taxTab = page.getByRole("tab", {
        name: nl ? "Belastingdruk" : "Tax burden",
        exact: true,
      });
      await taxTab.click();
      const open = page.getByRole("button", {
        name: nl ? "Controleer mijn belasting" : "Check my tax",
        exact: true,
      });
      await open.focus();
      await page.keyboard.press("Enter");
      await expect(open).toHaveAttribute("aria-expanded", "true");
      const report = page.locator("#check-tax-calculation");
      await expect(
        report.getByText("Heffingsvrij vermogen", { exact: true }).first(),
      ).toBeVisible();
      await expect(
        report.getByText(nl ? /geen bedragen om over te nemen/ : /not figures to copy/),
      ).toBeVisible();
      await expect(
        report.locator('a[href^="https://www.belastingdienst.nl"]').first(),
      ).toBeVisible();
      await expectNoViolations(page);
      const year = report.getByRole("combobox", { name: nl ? "Jaar" : "Year", exact: true });
      await year.selectOption("2028");
      await expect(
        report.getByText("Werkelijk rendement na heffingsvrij inkomen", { exact: true }).first(),
      ).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
      await open.click();
      await expect(report).toBeHidden();
    });
  });
}
