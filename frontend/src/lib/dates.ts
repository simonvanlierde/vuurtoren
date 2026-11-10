/** Local calendar date as YYYY-MM-DD. `new Date().toISOString().slice(0, 10)` is the
 * UTC date — around midnight CET that is yesterday, which mis-stamps price points
 * and projection starts. */
export function todayLocal(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

/** First of the month `count` months after `iso`, as YYYY-MM-01. The one place month
 * arithmetic lives; it rolls the year over at 12. */
export function monthsAfter(iso: string, count: number): string {
  const [y, m] = iso.split("-").map(Number);
  const zero = y * 12 + (m - 1) + count;
  return `${Math.floor(zero / 12)}-${String((zero % 12) + 1).padStart(2, "0")}-01`;
}

/** The month `count` months from today, as YYYY-MM (a month input's value). */
export function monthsFromNow(count: number): string {
  return monthsAfter(todayLocal(), count).slice(0, 7);
}
