/** Pure math for the Today composition bar: one horizontal diverging
 * stacked bar — positive kind totals stack rightward from a zero baseline, negative
 * ones (debt) leftward, net worth as a marker. Percentages are of the full span
 * (assets + |debt|), so the bar always fills its box. */

import { SERIES } from "./chartColors";

export interface Segment {
  kind: string;
  startPct: number;
  widthPct: number;
}

export interface Composition {
  positives: Segment[];
  negatives: Segment[];
  zeroPct: number;
  netPct: number;
}

/** Fixed stacking + legend order (matches the account-kind union). */
export const KIND_ORDER = ["cash", "equity", "bond", "real_estate", "pension", "debt"] as const;

/** One sea-green lightness ramp for growth assets, navy for pension, brick for debt —
 * never beacon amber (the beam's colour). Identity is carried by the labeled legend
 * (the "By kind" dl), not by colour alone. */
export const KIND_COLORS: Record<string, string> = {
  cash: SERIES.cash,
  equity: SERIES.investments,
  bond: SERIES.bond,
  real_estate: SERIES.realEstate,
  pension: SERIES.pension,
  debt: SERIES.debt,
};

export function buildComposition(kindTotals: Record<string, number>): Composition | null {
  const entries = KIND_ORDER.map((kind) => [kind, kindTotals[kind] ?? 0] as const).filter(
    ([, cents]) => cents !== 0,
  );
  const assets = entries.filter(([, c]) => c > 0).reduce((s, [, c]) => s + c, 0);
  // Built by subtraction (not negation) so an empty sum stays +0, never -0.
  const debts = entries.filter(([, c]) => c < 0).reduce((s, [, c]) => s - c, 0);
  const span = assets + debts;
  if (span === 0) return null;

  const zeroPct = (debts / span) * 100;
  const positives: Segment[] = [];
  const negatives: Segment[] = [];
  let posCursor = zeroPct;
  let negCursor = zeroPct;
  for (const [kind, cents] of entries) {
    const widthPct = (Math.abs(cents) / span) * 100;
    if (cents > 0) {
      positives.push({ kind, startPct: posCursor, widthPct });
      posCursor += widthPct;
    } else {
      negCursor -= widthPct;
      negatives.push({ kind, startPct: negCursor, widthPct });
    }
  }
  return { positives, negatives, zeroPct, netPct: zeroPct + ((assets - debts) / span) * 100 };
}
