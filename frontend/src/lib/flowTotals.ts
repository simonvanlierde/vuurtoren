/**
 * Aggregates the engine's monthly flow totals into calendar-year
 * totals. A 65-year horizon is ~780 monthly bars — unreadable as a chart; grouping by
 * year gets it down to a few dozen.
 */

export interface MonthlyFlowTotals {
  income: number[];
  expenses: number[];
  contributions: number[];
  housing: number[];
}

export interface YearlyFlowTotals {
  year: number;
  incomeCents: number;
  expensesCents: number;
  contributionsCents: number;
  housingCents: number;
  /** Projection months that fall in this year: 12 except at the two ends. */
  months: number;
}

/**
 * `months[i]` is an ISO date, `flowTotals` fields hold euros per month (index 0
 * always 0, the engine's opening-position convention). Sums land in whole cents so
 * repeated euro addition across a 65-year horizon never drifts the way float
 * accumulation would.
 */
export function aggregateFlowsByYear(
  months: readonly string[],
  flowTotals: MonthlyFlowTotals,
): YearlyFlowTotals[] {
  const byYear = new Map<number, YearlyFlowTotals>();
  months.forEach((month, i) => {
    const year = Number(month.slice(0, 4));
    const entry: YearlyFlowTotals = byYear.get(year) ?? {
      year,
      incomeCents: 0,
      expensesCents: 0,
      contributionsCents: 0,
      housingCents: 0,
      months: 0,
    };
    entry.months += 1;
    entry.incomeCents += Math.round(flowTotals.income[i] * 100);
    entry.expensesCents += Math.round(flowTotals.expenses[i] * 100);
    entry.contributionsCents += Math.round(flowTotals.contributions[i] * 100);
    entry.housingCents += Math.round(flowTotals.housing[i] * 100);
    byYear.set(year, entry);
  });
  return [...byYear.values()].sort((a, b) => a.year - b.year);
}
