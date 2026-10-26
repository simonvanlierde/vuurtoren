import { expect, type Page, test } from "@playwright/test";

import { expectNoViolations } from "./axe";

const figure = (page: Page, selector: string) =>
  expect(page.locator(selector).first()).toHaveText(/[1-9]/, { timeout: 20_000 });
const selectedTab = (page: Page, name: string) =>
  expect(page.getByRole("tab", { name })).toHaveAttribute("aria-selected", "true");

// [name, hash, wait until rendered]: axe checks only what is on the page, so each
// surface is scanned once its seeded figures are there.
const surfaces: [string, string, (page: Page) => Promise<void>][] = [
  ["Today", "today", (page) => figure(page, "dd.text-3xl")],
  ["Plan", "plan", (page) => figure(page, "dd.text-2xl")],
  ["Plan, Uncertainty lens", "monte-carlo", (page) => selectedTab(page, "Uncertainty")],
  [
    "Plan, Scenarios lens",
    "scenarios",
    async (page) => {
      await selectedTab(page, "Scenarios");
      await figure(page, "td.tabular-nums");
    },
  ],
  ["Flows", "flows", (page) => figure(page, ".tabular-nums")],
  ["Settings", "settings", (page) => expect(page.getByLabel("Theme")).toBeVisible()],
];

// Every surface and the account drawer against the seeded example household, in both
// colour schemes since contrast differs between them. The theme follows the system.
for (const scheme of ["light", "dark"] as const) {
  test.describe(`Accessibility (axe) — ${scheme}`, () => {
    test.use({ colorScheme: scheme });

    async function open(page: Page, hash: string) {
      await page.goto(`/#${hash}`);
      // Proves the scheme took effect, so the dark pass really scans the dark palette.
      const html = page.locator("html");
      await (scheme === "dark"
        ? expect(html).toHaveClass(/\bdark\b/)
        : expect(html).not.toHaveClass(/\bdark\b/));
    }

    for (const [name, hash, ready] of surfaces) {
      test(`${name} has no WCAG A/AA violations`, async ({ page }) => {
        await open(page, hash);
        await ready(page);
        await expectNoViolations(page);
      });
    }

    test("the account drawer has no WCAG A/AA violations", async ({ page }) => {
      await open(page, "today");
      await page.getByRole("button", { name: "Edit" }).first().click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await expectNoViolations(page);
    });
  });
}

// One Dutch pass: translated labels change lengths and the page language, which axe
// checks (html-has-lang, valid-lang).
test.describe("Accessibility (axe) — Dutch", () => {
  test.use({ locale: "nl-NL" });

  test("Plan has no WCAG A/AA violations and lang follows the locale", async ({ page }) => {
    await page.goto("/#plan");
    await expect(page.locator("html")).toHaveAttribute("lang", "nl");
    await figure(page, "dd.text-2xl");
    await expectNoViolations(page);
  });
});
