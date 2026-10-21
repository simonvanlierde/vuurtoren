/** "Rich, broke or dead" — the three bands of a plan's future.
 *
 * Every FIRE fan chart answers "will the money last" while quietly assuming you are
 * there to spend it. Multiplying by a survival curve puts the third outcome on the
 * chart, and most plans read as far less over-conservative once it is there.
 */
export interface OutcomeRow {
  month: string;
  /** Alive and solvent — the outcome the plan is actually for. */
  rich: number;
  /** Alive, but the cash ran out. The band worth designing against. */
  broke: number;
  /** No longer here. Not a failure, and not success either. */
  dead: number;
}

/** Split each month into the three mutually exclusive outcomes.
 *
 * Solvency and survival are treated as independent: the engine's runs know nothing
 * about mortality, and there is no evidence a household's portfolio path predicts its
 * lifespan. The three bands sum to 1 by construction, so the chart cannot mislead by
 * leaving a gap.
 */
export function buildOutcomeRows(
  months: readonly string[],
  solventFraction: readonly number[],
  survival: readonly number[],
): OutcomeRow[] {
  return months.map((month, i) => {
    const alive = survival[i] ?? 0;
    const solvent = solventFraction[i] ?? 0;
    return {
      month,
      rich: alive * solvent,
      broke: alive * (1 - solvent),
      dead: 1 - alive,
    };
  });
}

/** The sentence the chart is for: at the horizon, how the three outcomes divide.
 * Returns null when there is nothing to describe yet. */
export function outcomeSummary(rows: readonly OutcomeRow[]): OutcomeRow | null {
  return rows.length > 0 ? (rows[rows.length - 1] ?? null) : null;
}
