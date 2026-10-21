import { renderToStaticMarkup } from "react-dom/server";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { TimelineChart } from "../../components/TimelineChart";
import type { FbarWorksheet, ProjectionResponse } from "../../lib/api";
import { I18nProvider } from "../../lib/i18n";
import { CrossoverPanel } from "./CrossoverPanel";
import { StatusChip } from "./TaxPanel";
import { Sheet } from "./UsReportingPanel";

beforeAll(() => {
  vi.stubGlobal("localStorage", { getItem: () => "nl", setItem: () => {} });
  vi.stubGlobal("navigator", { language: "nl" });
  vi.stubGlobal("window", { matchMedia: () => ({ matches: false }) });
});

const nl = (node: React.ReactNode) => renderToStaticMarkup(<I18nProvider>{node}</I18nProvider>);

describe("Dutch UI strings", () => {
  it("names a provisional or proposed tax figure in Dutch", () => {
    expect(nl(<StatusChip status="provisional" />)).toContain("voorlopig");
    expect(nl(<StatusChip status="proposed" />)).toContain("voorgesteld");
  });

  it("shows the filing status as words, not the stored value", () => {
    const sheet = {
      person_id: 1,
      person_name: "Sam",
      filing_status: "married_filing_separately",
      accounts: [],
      aggregate_peak_usd: "0",
      aggregate_year_end_usd: "0",
      fbar_triggered: false,
      fbar_threshold_usd: "10000",
      fatca_triggered: false,
      fatca_trigger_reason: null,
      fatca_last_day_threshold_usd: "200000",
      fatca_any_time_threshold_usd: "300000",
    } satisfies FbarWorksheet;
    const html = nl(<Sheet sheet={sheet} />);
    expect(html).toContain("married filing separately");
    expect(html).not.toContain("married_filing_separately");
  });

  it("labels a milestone marker in Dutch", () => {
    const html = nl(
      <TimelineChart
        months={["2026-01-01", "2030-01-01"]}
        netWorth={[0, 1]}
        components={{}}
        markers={[{ id: 1, label: "Pensioen", monthIndex: 1, type: "retire" }]}
        ticks={[]}
        selectedId={null}
        onSelect={() => {}}
        caption=""
      />,
    );
    expect(html).toContain('aria-label="Mijlpaal: Pensioen"');
  });
});

describe("Crossover date", () => {
  it("prints the crossover as a month, not an ISO date", () => {
    const data = {
      months: ["2039-08-01", "2039-09-01"],
      investment_income: [[0, 3000]],
      flow_totals: { expenses: [0, 2500] },
    } as unknown as ProjectionResponse;
    const html = nl(<CrossoverPanel data={data} />);
    expect(html).toContain("Kruispunt: september 2039");
    expect(html).not.toContain("Kruispunt: 2039-09-01");
  });
});
