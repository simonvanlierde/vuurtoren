import { describe, expect, it } from "vitest";
import {
  formatCents,
  formatEuros,
  formatEuroTick,
  formatMoney,
  formatPercent,
  formatShare,
  isDecimalString,
  parsePercentInput,
  percentInputText,
  toCents,
} from "./money";

describe("toCents", () => {
  it("parses a plain amount", () => {
    expect(toCents("12345.67")).toBe(1234567);
  });

  it("parses a negative (debt) amount", () => {
    expect(toCents("-50000.00")).toBe(-5000000);
  });

  it("pads a missing or short fraction", () => {
    expect(toCents("10")).toBe(1000);
    expect(toCents("10.5")).toBe(1050);
  });

  it("does not drift the way float addition would", () => {
    // 0.1 + 0.2 !== 0.3 in float; the cents path must not inherit that.
    expect(toCents("0.10") + toCents("0.20")).toBe(toCents("0.30"));
  });
});

describe("formatMoney", () => {
  it("renders as EUR currency", () => {
    // `\s` also matches the non-breaking space nl-NL puts between symbol and amount,
    // so normalising here avoids a false diff over an invisible character.
    expect(formatMoney("12345.67").replace(/\s/g, " ")).toBe("€ 12.345,67");
  });

  it("renders a negative amount", () => {
    expect(formatMoney("-500.00")).toContain("500,00");
  });
});

describe("formatShare", () => {
  it("computes a percentage", () => {
    expect(formatShare(2500, 10000)).toBe("25,0%");
  });

  it("returns an em dash rather than dividing by zero", () => {
    expect(formatShare(100, 0)).toBe("—");
  });
});

describe("formatPercent", () => {
  it("formats a ratio directly, without dividing", () => {
    expect(formatPercent(0.325)).toBe("32,5%");
  });
});

describe("formatEuros", () => {
  it("renders a projected euro float without cents", () => {
    // A projection's cents are false precision — `€ 4.776.654,70` for 2085 claims
    // accuracy the model does not have.
    expect(formatEuros(12345.6).replace(/\s/g, " ")).toBe("€ 12.346");
  });

  it("renders a negative amount (debt component)", () => {
    expect(formatEuros(-500).replace(/\s/g, " ")).toContain("500");
  });

  it("leaves a stored balance's cents alone — that one really is exact", () => {
    expect(formatCents(1234567).replace(/\s/g, " ")).toBe("€ 12.345,67");
    expect(formatMoney("12345.67").replace(/\s/g, " ")).toBe("€ 12.345,67");
  });
});

describe("formatEuroTick", () => {
  it("compacts millions so axis labels never truncate", () => {
    expect(formatEuroTick(6_000_000).replace(/\s/g, " ")).toBe("€ 6 mln.");
    expect(formatEuroTick(1_500_000).replace(/\s/g, " ")).toBe("€ 1,5 mln.");
  });

  it("compacts thousands and keeps the sign", () => {
    expect(formatEuroTick(-60_000).replace(/\s/g, " ")).toBe("-€ 60K");
  });

  it("leaves small values plain", () => {
    expect(formatEuroTick(0).replace(/\s/g, " ")).toBe("€ 0");
  });
});

describe("the assumption rail's percent box", () => {
  it("round-trips a ratio through the text the box shows", () => {
    for (const ratio of [0, 0.02, 0.035, 0.0625]) {
      expect(parsePercentInput(percentInputText(ratio))).toBeCloseTo(ratio, 10);
    }
  });

  it("shows percentage points with an nl comma", () => {
    expect(percentInputText(0.035)).toBe("3,5");
    expect(percentInputText(0.02)).toBe("2");
    expect(percentInputText(0.0625)).toBe("6,25");
  });

  it("accepts either decimal separator", () => {
    expect(parsePercentInput("3,5")).toBeCloseTo(0.035, 10);
    expect(parsePercentInput("3.5")).toBeCloseTo(0.035, 10);
  });

  it("returns null for a box that is not a number yet", () => {
    for (const bad of ["", "   ", "-", "drie"]) {
      expect(parsePercentInput(bad)).toBeNull();
    }
  });
});

describe("isDecimalString", () => {
  it("accepts plain decimal strings and rejects everything else", () => {
    for (const ok of ["0", "1234.56", "-12.5", "0.923456", " 12 "]) {
      expect(isDecimalString(ok)).toBe(true);
    }
    for (const bad of ["", "12,50", "1e5", "twaalf", "12."]) {
      expect(isDecimalString(bad)).toBe(false);
    }
  });
});
