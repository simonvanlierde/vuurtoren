import { describe, expect, it } from "vitest";
import { aggregateFlowsByYear } from "./flowTotals";

describe("aggregateFlowsByYear", () => {
  it("sums months within the same calendar year", () => {
    const months = ["2026-01-01", "2026-02-01", "2026-03-01"];
    const flowTotals = {
      income: [0, 3000, 3000],
      expenses: [0, 1000, 1200],
      contributions: [0, 500, 500],
      housing: [0, 800, 800],
    };
    expect(aggregateFlowsByYear(months, flowTotals)).toEqual([
      {
        year: 2026,
        incomeCents: 600_000,
        expensesCents: 220_000,
        contributionsCents: 100_000,
        housingCents: 160_000,
        months: 3,
      },
    ]);
  });

  it("splits months across a year boundary into separate, sorted entries", () => {
    const months = ["2026-12-01", "2027-01-01"];
    const flowTotals = {
      income: [1000, 1500],
      expenses: [0, 0],
      contributions: [0, 0],
      housing: [0, 0],
    };
    expect(aggregateFlowsByYear(months, flowTotals)).toEqual([
      {
        year: 2026,
        incomeCents: 100_000,
        expensesCents: 0,
        contributionsCents: 0,
        housingCents: 0,
        months: 1,
      },
      {
        year: 2027,
        incomeCents: 150_000,
        expensesCents: 0,
        contributionsCents: 0,
        housingCents: 0,
        months: 1,
      },
    ]);
  });

  it("index 0's always-zero convention contributes nothing", () => {
    expect(
      aggregateFlowsByYear(["2026-01-01"], {
        income: [0],
        expenses: [0],
        contributions: [0],
        housing: [0],
      }),
    ).toEqual([
      {
        year: 2026,
        incomeCents: 0,
        expensesCents: 0,
        contributionsCents: 0,
        housingCents: 0,
        months: 1,
      },
    ]);
  });

  it("rounds fractional euros to whole cents without drifting across many months", () => {
    const months = Array.from(
      { length: 12 },
      (_, i) => `2026-${String(i + 1).padStart(2, "0")}-01`,
    );
    const flowTotals = {
      income: Array(12).fill(1000.005),
      expenses: Array(12).fill(0),
      contributions: Array(12).fill(0),
      housing: Array(12).fill(0),
    };
    const [year] = aggregateFlowsByYear(months, flowTotals);
    expect(year.incomeCents).toBe(12 * Math.round(1000.005 * 100));
  });
});
