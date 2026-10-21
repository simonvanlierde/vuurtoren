import { describe, expect, it } from "vitest";
import type { Account } from "../../lib/api";
import { toDraft, treatmentLabel, treatmentOptions } from "./AccountDrawer";

// The regime's vocabulary as GET /api/tax-config reports it, sorted.
const NL = [
  "nl.box1_home",
  "nl.box1_pension",
  "nl.box3_bank",
  "nl.box3_debt",
  "nl.box3_investment",
];
const AT = ["at.investment", "at.investment_nonreporting", "at.none"];

// Only the field under test matters; toDraft reads the rest with `?.` defaults.
const stored = (tax_treatment: string) => ({ tax_treatment }) as Account;

describe("account tax_treatment options", () => {
  it("gives a new account no treatment at all, rather than the list's first", () => {
    // The list is sorted, so "the regime's first" was `nl.box1_home`: a brokerage
    // account born as an owner-occupied home. There is no defensible default — the
    // picker opens on "— kies —" and the empty value blocks the save.
    expect(toDraft(null).tax_treatment).toBe("");
  });

  it("keeps what the account already carries", () => {
    expect(toDraft(stored("nl.box3_investment")).tax_treatment).toBe("nl.box3_investment");
  });

  it("offers exactly what the regime accepts", () => {
    expect(treatmentOptions("", AT)).toEqual(AT);
    expect(treatmentOptions("", NL)).toEqual(NL);
  });

  it("keeps a treatment the regime no longer lists, rather than silently reassigning it", () => {
    // Emigrating to AT leaves the Dutch strings on the accounts until they are edited;
    // dropping the current value from the list would rewrite it on the next save.
    expect(treatmentOptions("nl.box3_bank", AT)).toEqual(["nl.box3_bank", ...AT]);
  });

  it("survives a response that has not arrived yet", () => {
    // Nothing to choose from and nothing chosen: the empty value is what blocks the save
    // until the config lands. An existing account still shows its own stored string.
    expect(treatmentOptions("", [])).toEqual([]);
    expect(treatmentOptions("nl.box3_bank", [])).toEqual(["nl.box3_bank"]);
  });
});

describe("treatmentLabel", () => {
  const t = (k: string) => `<${k}>`;
  it("names the box and the kind instead of showing the stored key", () => {
    expect(treatmentLabel("nl.box3_bank", t)).toBe("Box 3 · <treatment.bank>");
  });
  it("labels every treatment both regimes list", () => {
    for (const key of [...NL, ...AT]) expect(treatmentLabel(key, t)).not.toBe(key);
  });
  it("falls back to the key for one it does not know", () => {
    expect(treatmentLabel("xx.new", t)).toBe("xx.new");
  });
});
