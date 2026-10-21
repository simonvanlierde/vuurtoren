/**
 * Household net worth over time, from stored `PricePoint`s.
 *
 * Only STOOQ-priced accounts ever gain price history (`prices.refresh_prices`)
 * — manual accounts have no points at all. So each account starts the series at
 * its manual fallback value and is forward-filled to its latest known
 * price point as the series walks forward through the dates that do exist.
 */

export interface PricePointLike {
  accountId: number;
  date: string; // ISO yyyy-mm-dd
  valueCents: number;
}

export interface AccountForSeries {
  id: number;
  fallbackCents: number;
}

export interface NetWorthPoint {
  date: string;
  totalCents: number;
}

export function buildNetWorthSeries(
  accounts: readonly AccountForSeries[],
  pricePoints: readonly PricePointLike[],
): NetWorthPoint[] {
  if (pricePoints.length === 0) return [];

  const current = new Map<number, number>();
  for (const account of accounts) current.set(account.id, account.fallbackCents);

  const byDate = new Map<string, PricePointLike[]>();
  for (const point of pricePoints) {
    const bucket = byDate.get(point.date);
    if (bucket) bucket.push(point);
    else byDate.set(point.date, [point]);
  }

  return [...byDate.keys()].sort().map((date) => {
    const points = byDate.get(date);
    if (!points) throw new Error(`missing price points for date ${date}`);
    for (const point of points) {
      current.set(point.accountId, point.valueCents);
    }
    return { date, totalCents: [...current.values()].reduce((sum, v) => sum + v, 0) };
  });
}

/** This-month change: latest series value minus the last value from before the
 * current month (the monthly ritual's delta). Null when the series
 * doesn't reach back past the 1st — a dash beats a fake zero. */
export function monthDelta(series: readonly NetWorthPoint[], todayISO: string): number | null {
  if (series.length === 0) return null;
  const monthStart = `${todayISO.slice(0, 7)}-01`;
  const baseline = [...series].reverse().find((p) => p.date < monthStart);
  if (!baseline) return null;
  return series[series.length - 1].totalCents - baseline.totalCents;
}
