/** Local calendar date as YYYY-MM-DD. `new Date().toISOString().slice(0, 10)` is the
 * UTC date — around midnight CET that is yesterday, which mis-stamps price points
 * and projection starts. */
export function todayLocal(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}
