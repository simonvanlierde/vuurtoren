import { describe, expect, it } from "vitest";
import { todayLocal } from "./dates";

describe("todayLocal", () => {
  it("returns the local calendar date, not the UTC one", () => {
    const d = todayLocal();
    expect(d).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    const now = new Date();
    expect(d).toBe(
      `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`,
    );
  });
});
