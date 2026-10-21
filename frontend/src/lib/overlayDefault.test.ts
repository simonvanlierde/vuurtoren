import { describe, expect, it } from "vitest";
import { domicileDefault } from "./api";

describe("domicileDefault", () => {
  it("reads a US-domiciled fund off its ISIN prefix", () => {
    expect(domicileDefault("US9229087690")).toBe("us.non_pfic");
  });

  it("treats every other domicile as a PFIC, which is what a UCITS is", () => {
    expect(domicileDefault("IE00B3RBWM25")).toBe("us.pfic_mtm");
    expect(domicileDefault("LU0908500753")).toBe("us.pfic_mtm");
  });

  it("declines to guess from a Yahoo ticker, which the same column also holds", () => {
    // "VT" is a US-domiciled ETF and the answer would even be right — but "IWDA" is not,
    // and neither is ISIN-shaped, so the field is left for the user rather than guessed.
    expect(domicileDefault("VT")).toBe("");
    expect(domicileDefault("IWDA.AS")).toBe("");
  });

  it("declines on a missing or malformed identifier", () => {
    expect(domicileDefault(null)).toBe("");
    expect(domicileDefault(undefined)).toBe("");
    expect(domicileDefault("")).toBe("");
    expect(domicileDefault("US922908769")).toBe(""); // eleven characters, not twelve
  });
});
