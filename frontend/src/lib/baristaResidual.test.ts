import { describe, expect, it } from "vitest";
import { residualMonthly } from "./baristaResidual";

const ctx = { salary: 5000, expenses: 3000 };

describe("residualMonthly", () => {
  it("passes euros through untouched", () => {
    expect(residualMonthly(1500, "eur", ctx)).toBe(1500);
  });

  it("reads a percentage against the salary", () => {
    expect(residualMonthly(30, "pct_salary", ctx)).toBe(1500);
  });

  it("reads a percentage against expenses — the baristaFIRE framing", () => {
    // "I want the job to cover half my spending" is the question people actually ask.
    expect(residualMonthly(50, "pct_expenses", ctx)).toBe(1500);
  });

  it("rounds to whole cents rather than trailing a float", () => {
    expect(residualMonthly(33.333, "pct_salary", ctx)).toBe(1666.65);
  });

  it("floors at zero — a negative residual is not a thing", () => {
    expect(residualMonthly(-10, "eur", ctx)).toBe(0);
    expect(residualMonthly(-10, "pct_salary", ctx)).toBe(0);
  });

  it("is zero when the base it is a percentage of is zero", () => {
    expect(residualMonthly(50, "pct_salary", { salary: 0, expenses: 3000 })).toBe(0);
  });
});
