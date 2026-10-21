import { describe, expect, it } from "vitest";
import { buildOutcomeRows, outcomeSummary } from "./mortality";

describe("buildOutcomeRows", () => {
  it("splits a month into three bands that sum to one", () => {
    const [row] = buildOutcomeRows(["2040-01-01"], [0.8], [0.5]);
    expect(row.rich).toBeCloseTo(0.4);
    expect(row.broke).toBeCloseTo(0.1);
    expect(row.dead).toBeCloseTo(0.5);
    expect(row.rich + row.broke + row.dead).toBeCloseTo(1);
  });

  it("is all-rich while everyone is alive and solvent", () => {
    const [row] = buildOutcomeRows(["2026-01-01"], [1], [1]);
    expect(row).toEqual({ month: "2026-01-01", rich: 1, broke: 0, dead: 0 });
  });

  it("counts a certain death as dead, not as broke", () => {
    // The distinction the whole overlay exists to draw: running out of money at 95 and
    // never reaching 95 are different outcomes, and only one of them is a planning failure.
    const [row] = buildOutcomeRows(["2090-01-01"], [0], [0]);
    expect(row.dead).toBe(1);
    expect(row.broke).toBe(0);
  });

  it("keeps the bands summing to one at every month", () => {
    const rows = buildOutcomeRows(["a", "b", "c"], [1, 0.6, 0.2], [1, 0.9, 0.4]);
    for (const r of rows) expect(r.rich + r.broke + r.dead).toBeCloseTo(1);
  });

  it("treats a short series as zero rather than reading past its end", () => {
    const [row] = buildOutcomeRows(["a"], [], []);
    expect(row.dead).toBe(1);
  });
});

describe("outcomeSummary", () => {
  it("describes the horizon, which is where the three outcomes have diverged most", () => {
    const rows = buildOutcomeRows(["a", "b"], [1, 0.5], [1, 0.5]);
    expect(outcomeSummary(rows)?.month).toBe("b");
  });

  it("has nothing to say about an empty projection", () => {
    expect(outcomeSummary([])).toBeNull();
  });
});
