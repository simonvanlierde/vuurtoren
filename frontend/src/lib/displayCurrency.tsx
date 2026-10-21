/** Weergavevaluta: a display-only, user-wide three-way — EUR (default),
 * USD, or each account's own quote currency. Stored values, the engine and every
 * request stay EUR; conversion uses the most recent ECB rate the price refresh
 * already stored, and the rate's date is always shown beside the setting so
 * staleness is never hidden. Float math is fine here: this is formatting. */
import { createContext, type ReactNode, useContext, useState } from "react";
import { formatCents } from "./money";
import { readStored, writeStored } from "./storage";

export type DisplayPref = "EUR" | "USD" | "quote";

const STORAGE_KEY = "vuurtoren-display-currency";

export function getDisplayPref(): DisplayPref {
  const stored = readStored(STORAGE_KEY);
  return stored === "USD" || stored === "quote" ? stored : "EUR";
}

export interface UsdRate {
  usdPerEur: number;
  date: string;
}

/** From stored PricePoints: `fx_rate_to_eur` is EUR per 1 unit of `currency`. */
export function latestUsdRate(
  points: readonly { date: string; currency: string; fx_rate_to_eur: string }[],
): UsdRate | null {
  let latest: { date: string; fx: string } | null = null;
  for (const p of points) {
    if (p.currency === "USD" && (latest === null || p.date > latest.date)) {
      latest = { date: p.date, fx: p.fx_rate_to_eur };
    }
  }
  if (!latest) return null;
  const eurPerUsd = Number(latest.fx);
  if (!(eurPerUsd > 0)) return null;
  return { usdPerEur: 1 / eurPerUsd, date: latest.date };
}

/** `formatCents` (money.ts) shows two decimal places, so display-currency amounts
 * match it: without `maximumFractionDigits` the currency formatting keeps its default
 * 2dp, so EUR mode renders the same as `formatCents`. */
export function formatDisplayCents(
  cents: number,
  currency: "EUR" | "USD",
  usdPerEur: number,
): string {
  const amount = currency === "USD" ? (cents / 100) * usdPerEur : cents / 100;
  return new Intl.NumberFormat("nl-NL", {
    style: "currency",
    currency,
  }).format(amount);
}

export interface AccountPoint {
  currency: "EUR" | "USD";
  fxRate: number;
}

/** The Today value cell: EUR by default, converted household-wide in USD mode,
 * the account's own quote currency in quote mode (EUR-quoted rows stay EUR). */
export function accountValueText(
  cents: number,
  pref: DisplayPref,
  usdRate: UsdRate | null,
  point: AccountPoint | null,
): string {
  if (pref === "quote" && point && point.currency !== "EUR" && point.fxRate > 0) {
    return formatDisplayCents(cents, point.currency, 1 / point.fxRate);
  }
  if (pref === "USD" && usdRate) {
    return formatDisplayCents(cents, "USD", usdRate.usdPerEur);
  }
  return formatCents(cents);
}

const DisplayCurrencyContext = createContext<{
  pref: DisplayPref;
  setPref: (p: DisplayPref) => void;
} | null>(null);

export function DisplayCurrencyProvider({ children }: { children: ReactNode }) {
  const [pref, setPrefState] = useState<DisplayPref>(getDisplayPref);
  function setPref(next: DisplayPref) {
    writeStored(STORAGE_KEY, next);
    setPrefState(next);
  }
  return (
    <DisplayCurrencyContext.Provider value={{ pref, setPref }}>
      {children}
    </DisplayCurrencyContext.Provider>
  );
}

export function useDisplayCurrency() {
  const ctx = useContext(DisplayCurrencyContext);
  if (!ctx) throw new Error("useDisplayCurrency outside DisplayCurrencyProvider");
  return ctx;
}
