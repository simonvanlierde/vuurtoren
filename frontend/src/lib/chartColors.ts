/**
 * The one place a chart series gets a colour.
 *
 * Values are `var(--vt-series-*)` references, not hex: SVG paint attributes and Recharts'
 * `stroke`/`fill` both resolve custom properties, so one name works for the hand-drawn
 * timeline, every Recharts chart and a legend swatch's `backgroundColor` alike — and all
 * three follow the theme, which a hex literal cannot (a test fails on one).
 *
 * Roles that share a swatch share it *here*, once and visibly, rather than by two files
 * happening to spell the same hex. Income is the investments green and expenses are the
 * debt brick because no chart draws both pairs at once.
 */

/** Named steps of the palette in `index.css`. Prefer a role below; reach for a step only
 * when a chart needs a colour the roles have no name for. */
const step = {
  green: "var(--vt-series-green)",
  greenMid: "var(--vt-series-green-mid)",
  greenSoft: "var(--vt-series-green-soft)",
  greenPale: "var(--vt-series-green-pale)",
  blue: "var(--vt-series-blue)",
  slate: "var(--vt-series-slate)",
  brick: "var(--vt-series-brick)",
  violet: "var(--vt-series-violet)",
  amber: "var(--vt-series-amber)",
} as const;

export const SERIES = {
  // Net-worth composition — one green ramp for growth assets, slate for pension, brick
  // for debt. Identity is carried by the labelled legend, never by colour alone, which
  // is why a ramp is acceptable here and not on Cash flow.
  investments: step.green,
  bond: step.greenMid,
  realEstate: step.greenSoft,
  cash: step.greenPale,
  homeEquity: step.blue,
  pension: step.slate,
  debt: step.brick,

  // Cash flow — four hues, not four lightnesses: two shades of one hue are one colour
  // under protanopia. Green / brick / blue / violet separate on hue as well as lightness.
  income: step.green,
  expenses: step.brick,
  contributions: step.blue,
  housing: step.violet,

  // Emphasis and its absence: the widest sensitivity bar against the rest, a scenario
  // baseline against its comparisons.
  focus: step.amber,
  neutral: step.slate,
} as const;

/** THE BEAM. Its fill stays headline amber in both themes — a wide translucent band
 * carrying the brand, not a mark that has to be found — while the median stroke and the
 * beacon ring use `focus`, which deepens on paper. */
export const BEAM = {
  fill: "var(--vt-beam-fill)",
  line: step.amber,
  core: "var(--vt-beam-core)",
} as const;

/** Scenario overlay lines: colour *and* dash, so the comparison never
 * rests on hue alone. */
export const LINE_COLORS = {
  baseline: "var(--foreground)",
  green: step.green,
  brick: step.brick,
  blue: step.blue,
} as const;
