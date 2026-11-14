import { renderToStaticMarkup } from "react-dom/server";
import { beforeAll, describe, expect, it, vi } from "vitest";
import type { TaxExplanation } from "../../lib/api";
import { I18nProvider } from "../../lib/i18n";
import { annualTaxTotal } from "./CumulativeTaxPanel";
import { TaxExplanationDetails } from "./TaxExplanationPanel";

beforeAll(() => {
  vi.stubGlobal("navigator", { language: "en" });
});

const report: TaxExplanation = {
  year: 2026,
  country: "NL",
  first_month: "2026-07-01",
  fiscal_partners: true,
  calculations: [
    {
      label: "Box 3",
      person_id: null,
      steps: [
        {
          rule: "Heffingsvrij vermogen",
          value: "118714.00",
          unit: "currency",
          parameters: {
            box3_allowance_per_person: {
              value: "59357",
              unit: "currency",
              source_year: 2026,
              status: "provisional",
              source: "https://www.belastingdienst.nl/example",
              sources: [
                "https://www.belastingdienst.nl/example",
                "https://www.rijksoverheid.nl/example",
              ],
              verified_on: "2026-11-01",
            },
          },
        },
      ],
    },
  ],
  totals: { investment_tax: "100", housing_adjustment: "20", withdrawal_tax: "5" },
  limitations: [{ en: "No actual bank interest.", nl: "Geen werkelijke bankrente." }],
};

describe("Check my tax", () => {
  it.each(["en", "nl"] as const)(
    "shows the rule, source, date, status and return boundary (%s)",
    (locale) => {
      vi.stubGlobal("localStorage", { getItem: () => locale, setItem: () => {} });
      const html = renderToStaticMarkup(
        <I18nProvider>
          <TaxExplanationDetails data={report} />
        </I18nProvider>,
      );
      expect(html).toContain("Heffingsvrij vermogen");
      expect(html).toContain('href="https://www.belastingdienst.nl/example"');
      expect(html).toContain('href="https://www.rijksoverheid.nl/example"');
      expect(html).toContain("2026-11-01");
      expect(html).toContain("2026-07-01");
      expect(html).toContain(locale === "en" ? "tax return" : "belastingaangifte");
      expect(html).toContain(locale === "en" ? "provisional" : "voorlopig");
      expect(html).not.toMatch(/\{\w+\}/);
    },
  );

  it("subtracts housing refunds and adds housing tax to the cumulative bill", () => {
    const taxes = {
      investment_tax: [[100, 100]],
      housing_adjustment: [[20, -20]],
      withdrawal_tax: [[5, 5]],
    };
    expect(annualTaxTotal(taxes, 0)).toBe(85);
    expect(annualTaxTotal(taxes, 1)).toBe(125);
  });
});
