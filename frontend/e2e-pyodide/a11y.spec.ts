import { expect, type Page, test } from "@playwright/test";
import { expectNoViolations } from "../e2e/axe";

test.beforeEach(({ page, context }) => {
  page.on("console", (message) => {
    if (message.type() === "error") console.log(`[console.error] ${message.text()}`);
  });
  page.on("pageerror", (error) => console.log(`[pageerror] ${error.stack ?? error.message}`));
  context.on("requestfailed", (request) =>
    console.log(
      `[requestfailed] ${request.method()} ${request.url()}: ${request.failure()?.errorText}`,
    ),
  );
});

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
  test.use({ locale: "nl-NL", viewport: { width: 390, height: 800 }, hasTouch: true });

  test("the Dutch plan and its tax editor work on a phone without axe violations", async ({
    page,
  }) => {
    test.setTimeout(180_000);
    await page.goto("/");
    await expect(page.locator("html")).toHaveAttribute("lang", "nl");
    await page.getByRole("button", { name: /start de demo/i }).click();
    await expect(page.locator("dd.text-2xl").first()).toHaveText(/[1-9]/, { timeout: 150_000 });
    await expectNoViolations(page);

    await page.getByRole("tab", { name: "Belastingcijfers", exact: true }).tap();
    const group = page
      .getByRole("region", { name: "Belastingpaneel", exact: true })
      .locator("details")
      .first();
    const summary = group.locator("summary");
    await expect(summary).toBeVisible();
    await expect(group).not.toHaveAttribute("open");
    await summary.tap();
    await group
      .getByRole("button", { name: /^Aanpassen / })
      .first()
      .tap();
    await expect(group.getByRole("button", { name: /^Reset / }).first()).toBeVisible();
    await expectNoViolations(page);
  });
});
