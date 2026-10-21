import { describe, expect, it } from "vitest";
import { accountValueText, formatDisplayCents, latestUsdRate } from "./displayCurrency";
import { formatCents } from "./money";

describe("latestUsdRate", () => {
  it("uses the newest USD price point's stored ECB rate", () => {
    const rate = latestUsdRate([
      { date: "2026-07-01", currency: "USD", fx_rate_to_eur: "0.90" },
      { date: "2026-07-20", currency: "USD", fx_rate_to_eur: "0.92165898617511520737" },
      { date: "2026-07-21", currency: "EUR", fx_rate_to_eur: "1" },
    ]);
    expect(rate?.date).toBe("2026-07-20");
    // fx_rate_to_eur is EUR per 1 USD -> USD per EUR is its inverse
    expect(rate?.usdPerEur).toBeCloseTo(1.085, 3);
  });
  it("is null without any USD point", () => {
    expect(
      latestUsdRate([{ date: "2026-07-21", currency: "EUR", fx_rate_to_eur: "1" }]),
    ).toBeNull();
  });
});

describe("formatDisplayCents", () => {
  it("formats EUR unchanged and converts USD at the given rate", () => {
    expect(formatDisplayCents(100_000_00, "EUR", 1.085)).toBe(
      formatDisplayCents(100_000_00, "EUR", 999),
    );
    expect(formatDisplayCents(100_000_00, "USD", 1.085)).toContain("108");
    expect(formatDisplayCents(100_000_00, "USD", 1.085)).toMatch(/\$|US/);
  });
});

describe("accountValueText", () => {
  const usdRate = { usdPerEur: 1.085, date: "2026-07-20" };

  it("EUR pref shows plain EUR regardless of rate or point", () => {
    expect(accountValueText(100_00, "EUR", usdRate, null)).toBe(formatCents(100_00));
    expect(accountValueText(100_00, "EUR", usdRate, { currency: "USD", fxRate: 0.9 })).toBe(
      formatCents(100_00),
    );
  });

  it("USD pref converts at the household rate", () => {
    expect(accountValueText(100_00, "USD", usdRate, null)).toBe(
      formatDisplayCents(100_00, "USD", usdRate.usdPerEur),
    );
  });

  it("USD pref without a rate falls back to EUR", () => {
    expect(accountValueText(100_00, "USD", null, null)).toBe(formatCents(100_00));
  });

  it("quote pref with a USD point converts at that point's own fx rate", () => {
    const point = { currency: "USD" as const, fxRate: 0.92 };
    expect(accountValueText(100_00, "quote", usdRate, point)).toBe(
      formatDisplayCents(100_00, "USD", 1 / point.fxRate),
    );
  });

  it("quote pref with a EUR point stays EUR", () => {
    expect(accountValueText(100_00, "quote", usdRate, { currency: "EUR", fxRate: 1 })).toBe(
      formatCents(100_00),
    );
  });

  it("quote pref with no point stays EUR", () => {
    expect(accountValueText(100_00, "quote", usdRate, null)).toBe(formatCents(100_00));
  });
});
