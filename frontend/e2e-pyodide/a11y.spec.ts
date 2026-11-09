import { expect, type Page, test } from "@playwright/test";
import { expectNoViolations } from "../e2e/axe";

async function navigate(page: Page, hash: string) {
  await page.evaluate((next) => {
    window.location.hash = next;
  }, hash);
}

for (const colorScheme of ["light", "dark"] as const) {
  test.describe(`Browser demo accessibility — ${colorScheme}`, () => {
    test.use({ colorScheme, reducedMotion: "reduce" });

    test("gate, six surfaces and account drawer have no axe violations", async ({ page }) => {
      test.setTimeout(240_000);
      await page.goto("/");
      await expect(page.locator("html")).toHaveClass(
        colorScheme === "dark" ? /\bdark\b/ : /^(?!.*\bdark\b)/,
      );
      await expectNoViolations(page);
      await page.getByRole("button", { name: /start the demo/i }).click();
      await expect(page.getByText(/\d+ tax figures with source/i).first()).toBeVisible({
        timeout: 150_000,
      });
      for (const hash of ["today", "plan", "monte-carlo", "scenarios", "flows", "settings"]) {
        await navigate(page, hash);
        if (hash === "settings") await expect(page.getByLabel("Theme")).toBeVisible();
        else if (hash === "monte-carlo" || hash === "scenarios") {
          await expect(
            page.getByRole("tab", {
              name: hash === "scenarios" ? "Scenarios" : "Uncertainty",
              exact: true,
            }),
          ).toHaveAttribute("aria-selected", "true");
          if (hash === "scenarios") {
            await expect(page.locator("td.tabular-nums").first()).toHaveText(/[1-9]/);
          }
        } else {
          const selector =
            hash === "today" ? "dd.text-3xl" : hash === "plan" ? "dd.text-2xl" : ".tabular-nums";
          await expect(page.locator(selector).first()).toHaveText(/[1-9]/);
        }
        await expectNoViolations(page);
      }
      await navigate(page, "today");
      await page
        .getByRole("button", { name: /^Edit:/ })
        .first()
        .click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await expectNoViolations(page);
    });
  });
}

test.describe("Browser demo accessibility — Dutch", () => {
  test.use({ locale: "nl-NL" });

  test("the Dutch plan has a language and no axe violations", async ({ page }) => {
    test.setTimeout(180_000);
    await page.goto("/");
    await expect(page.locator("html")).toHaveAttribute("lang", "nl");
    await page.getByRole("button", { name: /start de demo/i }).click();
    await expect(page.locator("dd.text-2xl").first()).toHaveText(/[1-9]/, { timeout: 150_000 });
    await expectNoViolations(page);
  });
});
