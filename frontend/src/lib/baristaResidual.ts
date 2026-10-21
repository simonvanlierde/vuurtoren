/** BaristaFIRE's residual income, in whichever unit the user thinks in.
 *
 * Three ways to say the same thing: an absolute amount, a share of the salary being
 * given up, or a share of the spending it has to cover. All three resolve here, in the
 * client, so the API only ever sees an absolute euro figure — the backend has no opinion
 * about which framing produced it.
 */
export type ResidualUnit = "eur" | "pct_salary" | "pct_expenses";

export function residualMonthly(
  value: number,
  unit: ResidualUnit,
  ctx: { salary: number; expenses: number },
): number {
  const base = unit === "eur" ? 1 : unit === "pct_salary" ? ctx.salary / 100 : ctx.expenses / 100;
  return Math.max(0, Math.round(value * base * 100) / 100);
}
