import { expect, test } from "@playwright/test";

test.describe("Narrow touch layouts", () => {
  test.use({ hasTouch: true, reducedMotion: "reduce" });

  for (const width of [320, 375]) {
    test(`${width}px navigation and account editing fit the viewport`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 });
      await page.goto("/#today");
      const nav = page.getByRole("navigation", { name: "Views" });
      for (const name of ["Today", "Plan", "Flows", "Settings"]) {
        const destination = nav.getByRole("button", { name, exact: true });
        await destination.tap();
        await expect(destination).toHaveAttribute("aria-current", "page");
        if (name === "Settings") await expect(page.getByLabel("Theme")).toBeVisible();
        else {
          const figure =
            name === "Today" ? "dd.text-3xl" : name === "Plan" ? "dd.text-2xl" : ".tabular-nums";
          await expect(page.locator(figure).first()).toHaveText(/[1-9]/);
        }
        expect((await destination.boundingBox())?.height).toBeGreaterThanOrEqual(44);
        const dimensions = await page.evaluate(() => ({
          page: document.documentElement.scrollWidth,
          viewport: window.innerWidth,
          content: document.querySelector("main")?.scrollWidth,
          available: document.querySelector("main")?.clientWidth,
        }));
        expect(dimensions.viewport).toBe(width);
        expect(dimensions.page).toBeLessThanOrEqual(width);
        expect(dimensions.content).toBeLessThanOrEqual(dimensions.available ?? -1);
        if (name === "Plan") {
          const scenarios = page.getByRole("tab", { name: "Scenarios", exact: true });
          await scenarios.scrollIntoViewIfNeeded();
          expect(
            await scenarios.evaluate((el) => el.getBoundingClientRect().right),
          ).toBeLessThanOrEqual(width);
          await scenarios.tap();
          await expect(scenarios).toHaveAttribute("aria-selected", "true");
        }
      }
      await nav.getByRole("button", { name: "Today", exact: true }).tap();
      await page
        .getByRole("button", { name: /^Edit:/ })
        .first()
        .tap();
      const drawer = page.getByRole("dialog");
      await expect(drawer).toBeVisible();
      expect((await drawer.boundingBox())?.width).toBeLessThanOrEqual(width);
      await drawer.getByRole("button", { name: "Cancel", exact: true }).tap();
      await expect(drawer).not.toBeVisible();
    });
  }
});

test("keyboard opens and closes an account drawer with focus restored", async ({ page }) => {
  await page.goto("/#today");
  const edit = page.getByRole("button", { name: /^Edit:/ }).first();
  await edit.focus();
  await page.keyboard.press("Enter");
  const drawer = page.getByRole("dialog");
  await expect(drawer).toBeVisible();
  await expect.poll(() => drawer.evaluate((el) => el.contains(document.activeElement))).toBe(true);
  for (let i = 0; i < 30; i++) {
    await page.keyboard.press("Tab");
    expect(await drawer.evaluate((el) => el.contains(document.activeElement))).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(drawer).not.toBeVisible();
  await expect(edit).toBeFocused();
});

test("closing a drawer opened by a click never leaves focus on the page body", async ({ page }) => {
  // WebKit does not focus a clicked button, so the drawer has no opener to return to.
  await page.goto("/#today");
  await page
    .getByRole("button", { name: /^Edit:/ })
    .first()
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect.poll(() => page.evaluate(() => document.activeElement !== document.body)).toBe(true);
});

test("deleting an account returns keyboard focus to the main content", async ({
  page,
  request,
}) => {
  const created = await request.post("/api/accounts", {
    data: {
      household_id: 1,
      name: "Focus check account",
      kind: "cash",
      tax_treatment: "nl.box3_bank",
      manual_value: "0.00",
    },
  });
  expect(created.ok()).toBe(true);
  const account = await created.json();
  try {
    await page.goto("/#today");
    const edit = page.getByRole("button", { name: "Edit: Focus check account", exact: true });
    await edit.focus();
    await page.keyboard.press("Enter");
    await page.getByRole("button", { name: "Delete…", exact: true }).click();
    await page.getByRole("button", { name: "Delete", exact: true }).click();
    await expect(edit).toHaveCount(0);
    await expect(page.locator("main")).toBeFocused();
  } finally {
    await request.delete(`/api/accounts/${account.id}`);
  }
});
