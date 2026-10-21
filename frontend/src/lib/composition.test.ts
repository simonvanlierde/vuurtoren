import { describe, expect, it } from "vitest";
import { buildComposition, KIND_COLORS } from "./composition";

describe("buildComposition", () => {
  it("stacks positives rightward from zero, negatives leftward, in kind order", () => {
    const c = buildComposition({ cash: 100_00, equity: 300_00, debt: -100_00 });
    expect(c).not.toBeNull();
    if (!c) return;
    // span = 400 assets + 100 |debt| = 500 -> zero line at 20%
    expect(c.zeroPct).toBeCloseTo(20);
    expect(c.negatives).toEqual([{ kind: "debt", startPct: 0, widthPct: 20 }]);
    expect(c.positives).toEqual([
      { kind: "cash", startPct: 20, widthPct: 20 },
      { kind: "equity", startPct: 40, widthPct: 60 },
    ]);
    // net = 300 -> marker at 20 + 300/500*100 = 80
    expect(c.netPct).toBeCloseTo(80);
  });

  it("handles the no-debt case with the zero line at 0", () => {
    const c = buildComposition({ equity: 500_00 });
    expect(c?.zeroPct).toBe(0);
    expect(c?.netPct).toBeCloseTo(100);
  });

  it("returns null when there is nothing to draw", () => {
    expect(buildComposition({})).toBeNull();
    expect(buildComposition({ cash: 0 })).toBeNull();
  });

  it("colours every kind from a theme token, never a literal and never the beam's", () => {
    for (const kind of ["cash", "equity", "bond", "real_estate", "pension", "debt"]) {
      // A hex here cannot follow the theme, which is how the Cash flow legend came to
      // fail contrast in the dark theme. Every series colour is a `var(--vt-series-*)`.
      expect(KIND_COLORS[kind]).toMatch(/^var\(--vt-series-/);
      expect(KIND_COLORS[kind]).not.toContain("amber");
    }
  });
});
