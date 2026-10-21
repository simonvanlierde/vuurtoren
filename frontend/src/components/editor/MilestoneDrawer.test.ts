/** A milestone type lives in three lists: the engine's union, MILESTONE_TYPES,
 * and MilestoneDrawer's hand-written param blocks. Nothing type-checks the third against
 * the first two, so `extra_repayment` once reached the engine while the editor showed no
 * field for it.
 *
 * This reads the drawer's source rather than rendering it: the drawer lives inside a Radix
 * portal behind a react-query provider, neither of which exists without a DOM, and the
 * bug being guarded is a missing block of JSX — visible in the source, and the assertion
 * costs no test framework at all. Rendering it for real is the Playwright spec's job.
 */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { defaultParams, MILESTONE_TYPES } from "./milestoneDraft";

const source = readFileSync(new URL("./MilestoneDrawer.tsx", import.meta.url), "utf8");

describe("MilestoneDrawer covers every milestone type", () => {
  for (const type of MILESTONE_TYPES) {
    it(`renders a control for each ${type} param`, () => {
      expect(source).toContain(type);
      const params = Object.keys(defaultParams(type));
      expect(params.length).toBeGreaterThan(0);
      for (const param of params) {
        expect(source).toContain(`draft.params.${param}`);
      }
    });
  }
});
