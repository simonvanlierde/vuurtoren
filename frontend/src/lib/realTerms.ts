/** Real-terms deflation. A projection's `inflation_factor` is the cumulative
 * price level per month (`1.0` at the start); dividing a nominal euro series by it
 * restates every point in start-date ("today's") euros.
 *
 * Deflate *every* series drawn on one axis with the same factor: a chart mixing a
 * real line against a nominal band reads worse than either all-nominal or all-real. */
export function toReal(series: readonly number[], factor: readonly number[]): number[] {
  // A missing or zero factor entry (never expected — factor[0] is 1.0 and it only
  // grows) leaves that point nominal rather than dividing by zero.
  return series.map((v, i) => (factor[i] ? v / factor[i] : v));
}
