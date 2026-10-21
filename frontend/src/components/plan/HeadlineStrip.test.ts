import { afterAll, describe, expect, it } from "vitest";
import { formatMonth } from "./HeadlineStrip";

describe("formatMonth", () => {
  // A date-only ISO string parses as UTC midnight: west of UTC that is the evening
  // before, so January 2051 printed as December 2050.
  const tz = process.env.TZ;
  process.env.TZ = "America/New_York";
  afterAll(() => {
    process.env.TZ = tz;
  });

  it("keeps the month west of UTC", () => {
    expect(formatMonth("2051-01-01", "never", "en")).toBe("January 2051");
    expect(formatMonth("2044-11-01", "never", "nl")).toBe("november 2044");
  });

  it("says not reached for no date", () => {
    expect(formatMonth(null, "never", "en")).toBe("never");
  });
});
