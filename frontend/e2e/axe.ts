import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

// WCAG 2.0 A/AA plus the 2.1 and 2.2 AA rule tags. axe checks against these specific
// rules; it does not certify conformance, it flags violations of them.
const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"];

export async function expectNoViolations(page: Page) {
  // A drawer that is still fading in has mid-transition colours, which fail color-contrast
  // at random. Wait for every finite animation; an infinite one (a spinner) never finishes.
  await page.evaluate(() =>
    Promise.all(
      document
        .getAnimations()
        .filter((a) => a.effect?.getTiming().iterations !== Number.POSITIVE_INFINITY)
        .map((a) => a.finished.catch(() => undefined)),
    ),
  );
  const { violations } = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
  // Map to rule, help and the failing elements, so a failure says what to fix, not just "[]".
  expect(
    violations.map(
      (v) => `${v.id}: ${v.help} at ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`,
    ),
  ).toEqual([]);
}
