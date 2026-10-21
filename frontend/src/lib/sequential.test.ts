import { describe, expect, it } from "vitest";
import { failedStartYears } from "./sequential";

describe("failedStartYears", () => {
  it("names the start years whose run never reached FI", () => {
    const fiDates = ["2041-01-01", null, "2044-01-01", null];
    expect(failedStartYears(fiDates, [1970, 1971, 1972, 1973])).toEqual([1971, 1973]);
  });

  it("returns nothing when every start year makes it", () => {
    expect(failedStartYears(["2041-01-01", "2042-01-01"], [1970, 1971])).toEqual([]);
  });

  it("returns every year when none do", () => {
    expect(failedStartYears([null, null], [1970, 1971])).toEqual([1970, 1971]);
  });

  it("ignores runs it has no start year for, rather than mislabelling them", () => {
    // Defensive: a length mismatch means the wire disagreed with itself. Naming the
    // wrong year is worse than naming none.
    expect(failedStartYears([null, null, null], [1970, 1971])).toEqual([1970, 1971]);
  });
});
