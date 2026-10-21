import { describe, expect, it } from "vitest";
import { visibleFlowSeries } from "./CashFlowView";

describe("Flows legend", () => {
  it("drops a series that is zero in every year, such as housing with no home", () => {
    const rows = [
      { incomeCents: 100, expensesCents: -40, contributionsCents: 0, housingCents: 0 },
      { incomeCents: 120, expensesCents: -50, contributionsCents: -10, housingCents: 0 },
    ];
    expect(visibleFlowSeries(rows).map((s) => s.key)).toEqual([
      "incomeCents",
      "expensesCents",
      "contributionsCents",
    ]);
  });
});
