import { expect, test } from "@playwright/test";

// The file picker is a visually hidden input inside a styled label, so the label has to
// show the focus the input receives (WCAG 2.4.7).
test("the import label shows keyboard focus", async ({ page }) => {
  await page.goto("/#settings");
  const input = page.getByLabel("Import JSON…");
  await expect(input).toBeAttached();
  for (let i = 0; i < 40; i++) {
    await page.keyboard.press("Tab");
    if (await input.evaluate((el) => el === document.activeElement)) break;
  }
  await expect(input).toBeFocused();
  const outline = await input.evaluate((el) => {
    const s = getComputedStyle(el.closest("label") as HTMLElement);
    return { style: s.outlineStyle, width: s.outlineWidth };
  });
  expect(outline.style).not.toBe("none");
  expect(outline.width).not.toBe("0px");
});

// A checkbox row is 44px tall, and the whole row toggles, not just the 20px box.
test("checkbox rows are a 44px target", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/#settings");
  const label = page.locator("label", { has: page.getByRole("checkbox") }).first();
  const box = await label.boundingBox();
  expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
});
