import { describe, expect, it } from "vitest";
import { buildNetWorthSeries, monthDelta } from "./netWorthSeries";

describe("buildNetWorthSeries", () => {
  it("returns nothing when there is no price history yet", () => {
    expect(buildNetWorthSeries([{ id: 1, fallbackCents: 100_000 }], [])).toEqual([]);
  });

  it("forward-fills each account from its manual fallback to its latest known point", () => {
    const accounts = [
      { id: 1, fallbackCents: 100_000 }, // priced account, starts here
      { id: 2, fallbackCents: 50_000 }, // manual-only account, never gets a point
    ];
    const points = [
      { accountId: 1, date: "2026-01-01", valueCents: 110_000 },
      { accountId: 1, date: "2026-02-01", valueCents: 120_000 },
    ];
    expect(buildNetWorthSeries(accounts, points)).toEqual([
      { date: "2026-01-01", totalCents: 160_000 },
      { date: "2026-02-01", totalCents: 170_000 },
    ]);
  });

  it("merges same-day points across multiple accounts before totalling", () => {
    const accounts = [
      { id: 1, fallbackCents: 0 },
      { id: 2, fallbackCents: 0 },
    ];
    const points = [
      { accountId: 1, date: "2026-01-01", valueCents: 100 },
      { accountId: 2, date: "2026-01-01", valueCents: 200 },
    ];
    expect(buildNetWorthSeries(accounts, points)).toEqual([
      { date: "2026-01-01", totalCents: 300 },
    ]);
  });
});

describe("monthDelta", () => {
  const series = [
    { date: "2026-06-20", totalCents: 100_000_00 },
    { date: "2026-06-30", totalCents: 101_000_00 },
    { date: "2026-07-10", totalCents: 103_000_00 },
    { date: "2026-07-20", totalCents: 102_000_00 },
  ];
  it("compares the latest point against the last point before this month", () => {
    expect(monthDelta(series, "2026-07-24")).toBe(1_000_00); // 102k - 101k
  });
  it("is null when no point predates the current month", () => {
    expect(monthDelta(series.slice(2), "2026-07-24")).toBeNull();
  });
  it("is null for an empty series", () => {
    expect(monthDelta([], "2026-07-24")).toBeNull();
  });
});
