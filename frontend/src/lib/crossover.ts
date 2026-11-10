/** The crossover: the month monthly passive income (investment returns) first covers
 * monthly expenses. Shared by the Plan headline and the crossover chart, which must name
 * the same month. */
import type { ProjectionResponse } from "./api";

/** Whole euros per month, run 0 of the deterministic projection. */
export function crossoverRows(data: ProjectionResponse) {
  const passive = data.investment_income[0] ?? [];
  const expenses = data.flow_totals.expenses;
  return data.months.map((month, i) => ({
    month,
    passive: Math.round(passive[i] ?? 0),
    expense: Math.round(expenses[i] ?? 0),
  }));
}

/** The first month past the opening one where passive income covers expenses, or null
 * when it never does inside the horizon or there are no expenses to cover. */
export function crossoverMonth(rows: ReturnType<typeof crossoverRows>): string | null {
  return rows.find((r, i) => i > 0 && r.expense > 0 && r.passive >= r.expense)?.month ?? null;
}
