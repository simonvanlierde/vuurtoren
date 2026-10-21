import { describe, expect, it } from "vitest";
import {
  addYears,
  buildBandPath,
  buildLinePath,
  dateToMonthIndex,
  linearScale,
  milestoneDate,
  niceTicks,
  yearTicks,
} from "./timeline";

describe("linearScale", () => {
  it("maps a domain onto a range", () => {
    const s = linearScale(0, 10, 100, 200);
    expect(s(0)).toBe(100);
    expect(s(5)).toBe(150);
    expect(s(10)).toBe(200);
  });

  it("pins a zero-width domain to the range start", () => {
    expect(linearScale(5, 5, 12, 99)(5)).toBe(12);
  });
});

describe("buildLinePath", () => {
  it("starts with a moveto and continues with linetos", () => {
    expect(
      buildLinePath([
        { x: 0, y: 1 },
        { x: 2, y: 3 },
      ]),
    ).toBe("M0,1 L2,3");
  });

  it("is empty for no points", () => {
    expect(buildLinePath([])).toBe("");
  });
});

describe("buildBandPath", () => {
  it("walks the top forward, the bottom back, and closes", () => {
    const top = [
      { x: 0, y: 0 },
      { x: 1, y: 0 },
    ];
    const bottom = [
      { x: 0, y: 10 },
      { x: 1, y: 10 },
    ];
    expect(buildBandPath(top, bottom)).toBe("M0,0 L1,0 L1,10 L0,10 Z");
  });

  it("collapses to a point at the origin when top and bottom meet", () => {
    // The beam's defining property: p10 == p90 at month 0.
    const path = buildBandPath(
      [
        { x: 0, y: 5 },
        { x: 1, y: 0 },
      ],
      [
        { x: 0, y: 5 },
        { x: 1, y: 10 },
      ],
    );
    expect(path).toBe("M0,5 L1,0 L1,10 L0,5 Z");
  });
});

describe("addYears", () => {
  it("adds whole years keeping month and day", () => {
    expect(addYears("1990-06-15", 67)).toBe("2057-06-15");
  });
});

describe("milestoneDate", () => {
  const births = new Map([[1, "1990-06-15"]]);

  it("prefers an explicit on_date", () => {
    expect(milestoneDate({ on_date: "2030-01-01", age_person_id: 1, age_years: 40 }, births)).toBe(
      "2030-01-01",
    );
  });

  it("falls back to a person's birth date plus age", () => {
    expect(milestoneDate({ on_date: null, age_person_id: 1, age_years: 40 }, births)).toBe(
      "2030-06-15",
    );
  });

  it("returns null when the person is unknown", () => {
    expect(milestoneDate({ on_date: null, age_person_id: 9, age_years: 40 }, births)).toBeNull();
  });
});

describe("dateToMonthIndex", () => {
  const months = ["2026-01-01", "2026-02-01", "2026-03-01"];

  it("is 0 at the first month and the last index at the last", () => {
    expect(dateToMonthIndex("2026-01-01", months)).toBe(0);
    expect(dateToMonthIndex("2026-03-01", months)).toBe(2);
  });

  it("interpolates between bracketing months", () => {
    // 2026-01-16 is roughly halfway through a 31-day January.
    const idx = dateToMonthIndex("2026-01-16", months);
    // 15 of January's 31 days have passed.
    expect(idx).toBeCloseTo(15 / 31, 5);
  });

  it("returns null outside the axis", () => {
    expect(dateToMonthIndex("2025-01-01", months)).toBeNull();
    expect(dateToMonthIndex("2027-01-01", months)).toBeNull();
  });
});

describe("niceTicks", () => {
  it("puts a millions-scale axis on round millions", () => {
    // The regression: 0..4_776_654 split five ways gave €1.3M / €2.5M / €3.8M.
    expect(niceTicks(0, 4_776_654, 5)).toEqual([0, 1_000_000, 2_000_000, 3_000_000, 4_000_000]);
  });

  it("covers the domain without ever exceeding it", () => {
    for (const [min, max] of [
      [0, 1],
      [-50_000, 320_000],
      [1_234, 9_876],
    ]) {
      const ticks = niceTicks(min, max, 5);
      expect(ticks[0]).toBeGreaterThanOrEqual(min);
      expect(ticks.at(-1)).toBeLessThanOrEqual(max);
      expect(ticks.length).toBeGreaterThan(1);
    }
  });

  it("degrades to a single value on a collapsed or non-finite domain", () => {
    expect(niceTicks(5, 5)).toEqual([5]);
    expect(niceTicks(10, 0)).toEqual([10]);
    expect(niceTicks(Number.NaN, 10)).toEqual([Number.NaN]);
  });
});

describe("yearTicks", () => {
  const monthlyAxis = (from: number, to: number) => {
    const out: string[] = [];
    for (let y = from; y <= to; y++) {
      for (let m = 1; m <= 12; m++) out.push(`${y}-${String(m).padStart(2, "0")}-01`);
    }
    return out;
  };

  it("lands on January of each stepped year and carries the age", () => {
    const ticks = yearTicks(monthlyAxis(2026, 2033), "1990-01-01");
    expect(ticks.map((t) => t.year)).toEqual([2026, 2027, 2028, 2029, 2030, 2031, 2032, 2033]);
    // January 2027 is the 13th month of an axis starting January 2026.
    expect(ticks[1].monthIndex).toBe(12);
    expect(ticks[1].age).toBe(37);
  });

  it("widens the step rather than crowding a long horizon", () => {
    const ticks = yearTicks(monthlyAxis(2026, 2091), null);
    expect(ticks.length).toBeLessThanOrEqual(8);
    expect(ticks[1].year - ticks[0].year).toBe(10);
    expect(ticks.every((t) => t.age === null)).toBe(true);
  });

  it("returns nothing for an empty axis", () => {
    expect(yearTicks([], "1990-01-01")).toEqual([]);
  });
});
