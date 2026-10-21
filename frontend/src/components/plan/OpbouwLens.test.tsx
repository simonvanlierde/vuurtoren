import { renderToStaticMarkup } from "react-dom/server";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { TimelineChart } from "../../components/TimelineChart";
import { I18nProvider, MESSAGES } from "../../lib/i18n";
import { formatEuros } from "../../lib/money";
import { compositionCaption, compositionLegend } from "./OpbouwLens";

beforeAll(() => {
  vi.stubGlobal("localStorage", { getItem: () => "en", setItem: () => {} });
  vi.stubGlobal("navigator", { language: "en" });
  vi.stubGlobal("window", { matchMedia: () => ({ matches: false }) });
});

// The fixed-return path ends at 11 M, the Monte Carlo median at 5.8 M: the case where
// the caption once quoted the median under a chart that drew the fixed path.
const values = {
  netWorth: [500_000, 11_000_000],
  band: { p10: [500_000, 2_000_000], p50: [500_000, 5_800_000], p90: [500_000, 9_000_000] },
  endYear: 2085,
  runs: 750,
  pct: 99,
};

describe("Composition caption", () => {
  it.each(["en", "nl"] as const)("quotes the end of the drawn line and the median (%s)", (l) => {
    const caption = compositionCaption(MESSAGES[l]["plan.opbouw.caption"], values);
    expect(caption).toContain(formatEuros(11_000_000));
    expect(caption).toContain(formatEuros(5_800_000));
    expect(caption).not.toMatch(/\{\w+\}/);
  });

  it("states a share of runs, not a share of time", () => {
    const caption = compositionCaption(MESSAGES.en["plan.opbouw.caption"], values);
    expect(caption).not.toMatch(/of the time/);
    expect(caption).toContain("99% of 750 runs");
  });
});

describe("TimelineChart median", () => {
  it("draws the Monte Carlo median as a dashed line", () => {
    const html = renderToStaticMarkup(
      <I18nProvider>
        <TimelineChart
          months={["2026-01-01", "2085-01-01"]}
          netWorth={values.netWorth}
          components={{}}
          median={values.band.p50}
          markers={[]}
          ticks={[]}
          selectedId={null}
          onSelect={() => {}}
          caption=""
        />
      </I18nProvider>,
    );
    expect(html).toMatch(/<path[^>]*stroke-dasharray/);
  });
});

describe("Composition legend", () => {
  it("lists only the series that are non-zero somewhere in the projection", () => {
    const legend = compositionLegend({
      liquid_investments: [100, 200],
      cash: [50, 0],
      home_equity: [0, 0],
      pension: [0, 0],
    });
    expect(legend.map((l) => l.key)).toEqual(["liquid_investments", "cash"]);
  });
});
