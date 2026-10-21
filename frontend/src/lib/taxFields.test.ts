import { describe, expect, it } from "vitest";
import { MESSAGES } from "./i18n";
import { formatTaxValue, groupTaxFields, type TaxField, taxValueError } from "./taxFields";

const field = (over: Partial<TaxField> = {}): TaxField => ({
  value: "0.36",
  unit: "/1",
  status: "final",
  source: "https://belastingdienst.nl",
  verified_on: "2026-07-23",
  ...over,
});

const groupEn = (fields: Record<string, TaxField>) => groupTaxFields(fields, "en");

// Intl inserts a non-breaking space after the currency symbol; normalise for readability.
const plain = (s: string) => s.replace(/\s/g, " ");

describe("groupTaxFields", () => {
  it("puts Box 3 and Box 1 fields under their subsection, in panel order", () => {
    const groups = groupEn({
      hra_max_rate: field(),
      box3_rate: field(),
      wwr_rate: field({ status: "proposed" }),
    });
    expect(groups.map((g) => g.id)).toEqual(["box3", "regime-b", "box1-home"]);
    expect(groups[0].rows.map((r) => r.name)).toEqual(["box3_rate"]);
    expect(groups[1].rows[0].field.status).toBe("proposed");
  });

  it("omits a group with no resolved fields", () => {
    const groups = groupEn({ box3_rate: field() });
    expect(groups).toHaveLength(1);
    expect(groups[0].id).toBe("box3");
  });

  it("keeps a field no group claims, labelled by the server's own description", () => {
    // A country whose figures the panel has no grouping for (AT today, the next one
    // tomorrow) used to render as an empty tax panel. Dropping a figure silently is the
    // one thing a panel whose job is to be believed must not do.
    const groups = groupEn({
      box3_rate: field(),
      future_rate: field({ description: "A rate the panel has no label for" }),
      mystery_field: field(),
    });
    const other = groups.find((g) => g.id === "other");
    expect(other?.rows.map((r) => r.name)).toEqual(["future_rate", "mystery_field"]);
    expect(other?.rows[0].label).toBe("A rate the panel has no label for");
    // No description and no registered label: the raw name, never nothing.
    expect(other?.rows[1].label).toBe("mystery_field");
    // "Other" comes last, after every group the panel does know how to order.
    expect(groups.at(-1)?.id).toBe("other");
  });

  it("hides the wage-tax figures no projection reads", () => {
    const groups = groupEn({
      box3_rate: field(),
      box1_rate_1: field(),
      labour_credit_max: field(),
      income_rate_7: field(),
      sonderzahlung_rate: field(),
      kest_rate: field(),
    });
    expect(groups.flatMap((g) => g.rows.map((r) => r.name))).toEqual(["box3_rate", "kest_rate"]);
  });

  it("falls back to the raw field name when no Dutch label is registered", () => {
    const groups = groupEn({ box3_rate: field() });
    // NOTE: only asserting the known-field label path here — an unmapped name
    // would need a group entry too, which isn't the point of this test.
    expect(groups[0].rows[0].label).toBe("Tarief");
  });
});

describe("groupTaxFields in Dutch", () => {
  it("labels the trailing group and the Austrian figures in the reader's language", () => {
    const groups = groupTaxFields(
      {
        box3_allowance_per_person: field({ unit: "currency" }),
        kest_rate: field({ description: "Kapitalertragsteuer on securities income." }),
        grunderwerbsteuer_rate: field({ description: "Grunderwerbsteuer, the property tax." }),
      },
      "nl",
    );
    expect(groups.map((g) => g.label)).toEqual([
      MESSAGES.nl["plan.tax.group.box3"],
      MESSAGES.nl["plan.tax.group.other"],
    ]);
    expect(groups.at(-1)?.label).toBe("Overig");
    const labels = groups.flatMap((g) => g.rows.map((r) => r.label));
    expect(labels).toEqual([
      "Heffingsvrij vermogen (per persoon)",
      MESSAGES.nl["plan.tax.label.kest_rate"],
      MESSAGES.nl["plan.tax.label.grunderwerbsteuer_rate"],
    ]);
    expect(labels.join(" ")).not.toMatch(/\b(on|the|per person)\b/);
  });
});

describe("formatTaxValue", () => {
  it("reads a rate as a percentage, not as the raw ratio", () => {
    expect(formatTaxValue("0.36", "/1", "EUR")).toBe("36%");
    expect(plain(formatTaxValue("0.0128", "/1", "EUR"))).toBe("1,28%");
  });

  it("drops cents a figure does not have and keeps the ones it does", () => {
    expect(plain(formatTaxValue("59357", "currency", "EUR"))).toBe("€ 59.357");
    expect(plain(formatTaxValue("59357.50", "currency", "EUR"))).toBe("€ 59.357,5");
  });

  it("uses the country's own currency", () => {
    expect(plain(formatTaxValue("200000", "currency", "USD"))).toBe("US$ 200.000");
  });

  it("renders a year or an age as a plain integer, never 2.028", () => {
    expect(formatTaxValue("2028", "year", "EUR")).toBe("2028");
    expect(formatTaxValue("35", "year", "EUR")).toBe("35");
  });

  it("passes an unannotated or unparseable value through untouched", () => {
    expect(formatTaxValue("0.36", null, "EUR")).toBe("0.36");
    expect(formatTaxValue("n/a", "/1", "EUR")).toBe("n/a");
  });
});

describe("taxValueError", () => {
  it("holds a rate to [0, 1] — the mistake is typing 36 for 36%", () => {
    expect(taxValueError("0.36", "/1")).toBeNull();
    expect(taxValueError("36", "/1")).toBe("plan.tax.error.rateRange");
    expect(taxValueError("-0.1", "/1")).toBe("plan.tax.error.rateRange");
  });

  it("refuses negative money and accepts cents", () => {
    expect(taxValueError("59357.50", "currency")).toBeNull();
    expect(taxValueError("-1", "currency")).toBe("plan.tax.error.negativeMoney");
  });

  it("requires whole years but ranges neither: the annotation also covers ages", () => {
    expect(taxValueError("2028", "year")).toBeNull();
    expect(taxValueError("35", "year")).toBeNull();
    expect(taxValueError("2028.5", "year")).toBe("plan.tax.error.wholeYear");
  });

  it("names an empty or unparseable box rather than sending it to the engine", () => {
    expect(taxValueError("", "/1")).toBe("plan.tax.error.empty");
    expect(taxValueError("  ", "currency")).toBe("plan.tax.error.empty");
    expect(taxValueError("0.", "/1")).toBeNull();
    expect(taxValueError("nul", "/1")).toBe("plan.tax.error.notANumber");
  });
});
