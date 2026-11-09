import { describe, expect, it } from "vitest";
import type { Household } from "./api";
import { draftFrom, isDirty, isSavable } from "./householdDraft";

const household: Household = {
  id: 1,
  name: "Test household",
  base_currency: "EUR",
  tax_country: "NL",
  fiscal_partners: false,
  life_expectancy_age: 95,
};

describe("household draft", () => {
  it("starts clean and not savable", () => {
    const draft = draftFrom(household);
    expect(isDirty(draft, household)).toBe(false);
    expect(isSavable(draft, household)).toBe(false);
  });

  it("is dirty and savable after an edit to any field", () => {
    for (const patch of [
      { name: "Other" },
      { tax_country: "AT" },
      { fiscal_partners: true },
      { life_expectancy_age: "90" },
    ]) {
      const draft = { ...draftFrom(household), ...patch };
      expect(isDirty(draft, household)).toBe(true);
      expect(isSavable(draft, household)).toBe(true);
    }
  });

  it("is dirty but not savable while the age is blank or not a whole number", () => {
    for (const age of ["", "  ", "9.5", "-1", "abc"]) {
      const draft = { ...draftFrom(household), life_expectancy_age: age };
      expect(isSavable(draft, household)).toBe(false);
    }
  });
});
