/** The sequential backtest's one readout: which real start years fail.
 *
 * The fan chart's percentiles are anonymous — p10 is not a year. Sequential mode's
 * whole point is that a run has a name, so "every start year since 1970 works except
 * 2000" is sayable. `fi_dates[r]` is null when run r never reached FI, and
 * `start_years[r]` is the calendar year run r began in.
 */
export function failedStartYears(fiDates: (string | null)[], startYears: number[]): number[] {
  return startYears.filter((_, i) => i < fiDates.length && fiDates[i] === null);
}
