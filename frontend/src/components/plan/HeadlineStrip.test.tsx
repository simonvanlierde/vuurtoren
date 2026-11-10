import { renderToStaticMarkup } from "react-dom/server";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import type { ProjectionResponse } from "../../lib/api";
import { I18nProvider } from "../../lib/i18n";
import { formatMonth, HeadlineStrip } from "./HeadlineStrip";

describe("formatMonth", () => {
  // A date-only ISO string parses as UTC midnight: west of UTC that is the evening
  // before, so January 2051 printed as December 2050.
  const tz = process.env.TZ;
  process.env.TZ = "America/New_York";
  afterAll(() => {
    process.env.TZ = tz;
  });

  it("keeps the month west of UTC", () => {
    expect(formatMonth("2051-01-01", "never", "en")).toBe("January 2051");
    expect(formatMonth("2044-11-01", "never", "nl")).toBe("november 2044");
  });

  it("says not reached for no date", () => {
    expect(formatMonth(null, "never", "en")).toBe("never");
  });
});

describe("HeadlineStrip", () => {
  beforeAll(() => {
    vi.stubGlobal("localStorage", { getItem: () => "en", setItem: () => {} });
    vi.stubGlobal("navigator", { language: "en" });
  });

  const projection = (fire: Partial<ProjectionResponse["fire"]>) =>
    ({
      months: ["2026-01-01", "2031-03-01", "2045-05-01"],
      investment_income: [[0, 1000, 3000]],
      flow_totals: { expenses: [2500, 2500, 2500] },
      fire: {
        fire_number: 750_000,
        fi_dates: ["2043-12-01"],
        coast_fire_dates: ["2031-03-01"],
        savings_rate: 0.3,
        ...fire,
      },
    }) as unknown as ProjectionResponse;

  const render = (p: ProjectionResponse) =>
    renderToStaticMarkup(
      <I18nProvider>
        <HeadlineStrip projection={p} slot={null} />
      </I18nProvider>,
    );

  it("puts Coast-FIRE and the crossover under the FI date", () => {
    const html = render(projection({}));
    const fi = html.indexOf("December 2043");
    expect(fi).toBeGreaterThan(-1);
    expect(html.indexOf("Coast-FIRE")).toBeGreaterThan(fi);
    expect(html).toContain("March 2031");
    expect(html.indexOf("Crossover")).toBeGreaterThan(fi);
    expect(html).toContain("May 2045");
  });

  it("calls FI with no spending undefined, not missed", () => {
    const html = render(projection({ fire_number: 0, fi_dates: [null], coast_fire_dates: [null] }));
    expect(html).toContain("Not defined");
    expect(html).not.toContain("Not reached");
    expect(html).not.toContain("text-destructive");
    expect(html).not.toContain("Coast-FIRE");
  });

  it("marks a missed FI date as a shortfall", () => {
    const html = render(projection({ fi_dates: [null] }));
    expect(html).toMatch(/text-destructive">Not reached</);
  });
});
