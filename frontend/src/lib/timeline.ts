/**
 * Pure geometry + date maths for the timeline. Everything the
 * hand-drawn SVG needs that can be tested without a DOM lives here: the scales,
 * the SVG path strings (the net-worth curve and THE BEAM), and resolving a
 * milestone's position on the life axis.
 */

export interface XY {
  x: number;
  y: number;
}

/** One x-axis tick: calendar year plus the primary person's age that year. */
export interface TimelineTick {
  monthIndex: number;
  year: number;
  age: number | null;
}

/** A linear scale `d0..d1 -> r0..r1`. A zero-width domain pins to `r0`. */
export function linearScale(d0: number, d1: number, r0: number, r1: number): (v: number) => number {
  const m = d1 === d0 ? 0 : (r1 - r0) / (d1 - d0);
  return (v) => r0 + (v - d0) * m;
}

const round = (n: number) => Math.round(n * 100) / 100;

/**
 * Gridline values on a round step, covering `[min, max]`. Splitting the raw domain into
 * n equal parts put the axis on €1.3M / €2.5M / €3.8M — arithmetically correct and
 * unreadable, because nobody holds a plan in units of 1.27 million. Snapping the step to
 * 1/2/2.5/5 × 10ⁿ gives €1M / €2M / €3M / €4M instead.
 */
export function niceTicks(min: number, max: number, count = 5): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) return [min];
  const raw = (max - min) / Math.max(1, count - 1);
  const mag = 10 ** Math.floor(Math.log10(raw));
  const ticksFor = (step: number) => {
    const first = Math.ceil(min / step) * step;
    const out: number[] = [];
    // Accumulate off the index, not by repeated addition: 0.1-style steps drift otherwise.
    for (let i = 0; first + i * step <= max + step / 1e6; i++) out.push(round(first + i * step));
    return out;
  };
  // Smallest nice step still inside the budget, not the first one wider than the raw
  // division: rounding 1.19M up landed on 2M and threw away the €1M/€2M/€3M/€4M axis.
  for (const m of [1, 2, 2.5, 5, 10]) {
    const out = ticksFor(m * mag);
    if (out.length > 1 && out.length <= count) return out;
  }
  const fallback = ticksFor(10 * mag);
  return fallback.length > 0 ? fallback : [min];
}

/** `M…L…` polyline through already-scaled points. */
export function buildLinePath(points: readonly XY[]): string {
  if (points.length === 0) return "";
  return points.map((p, i) => `${i === 0 ? "M" : "L"}${round(p.x)},${round(p.y)}`).join(" ");
}

/**
 * A closed band: `top` walked left→right, `bottom` walked back right→left, closed.
 * THE BEAM is this over (p90, p10): at month 0 every Monte-Carlo run shares the
 * seed starting value so p10≈p90 and the band is a point; it fans open as the
 * percentile spread grows with the horizon — the lighthouse cone.
 */
export function buildBandPath(top: readonly XY[], bottom: readonly XY[]): string {
  if (top.length === 0 || bottom.length === 0) return "";
  const fwd = top.map((p, i) => `${i === 0 ? "M" : "L"}${round(p.x)},${round(p.y)}`).join(" ");
  const back = [...bottom]
    .reverse()
    .map((p) => `L${round(p.x)},${round(p.y)}`)
    .join(" ");
  return `${fwd} ${back} Z`;
}

/** Add whole years to an ISO `yyyy-mm-dd` date, keeping month and day. */
export function addYears(iso: string, years: number): string {
  const [y, mo, d] = iso.split("-");
  return `${Number(y) + years}-${mo}-${d}`;
}

/**
 * Resolve where a milestone sits in time: an explicit `on_date`, else a person's
 * birth date plus `age_years`. Returns null when neither is available.
 */
export function milestoneDate(
  m: { on_date: string | null; age_person_id: number | null; age_years: number | null },
  birthByPerson: ReadonlyMap<number, string>,
): string | null {
  if (m.on_date) return m.on_date;
  if (m.age_person_id != null && m.age_years != null) {
    const birth = birthByPerson.get(m.age_person_id);
    if (birth) return addYears(birth, m.age_years);
  }
  return null;
}

/**
 * Fractional index of an ISO date along the projection's monthly axis, linearly
 * interpolated between the bracketing months. Null when the date falls outside
 * the axis so off-horizon milestones are simply not drawn.
 */
export function dateToMonthIndex(iso: string, months: readonly string[]): number | null {
  if (months.length === 0) return null;
  const t = Date.parse(iso);
  const first = Date.parse(months[0]);
  const last = Date.parse(months[months.length - 1]);
  if (t < first || t > last) return null;
  for (let i = 0; i < months.length - 1; i++) {
    const a = Date.parse(months[i]);
    const b = Date.parse(months[i + 1]);
    if (t >= a && t <= b) return b === a ? i : i + (t - a) / (b - a);
  }
  return months.length - 1;
}

/**
 * Whole-year ticks across a projection's monthly axis, on a step that keeps the count
 * near `count`. Shared by both lenses that draw the timeline: they were building the
 * same loop, and an axis that reads differently on two views of one plan is a bug.
 */
export function yearTicks(
  months: readonly string[],
  primaryBirth: string | null,
  count = 8,
): TimelineTick[] {
  if (months.length === 0) return [];
  const startYear = Number(months[0].slice(0, 4));
  const endYear = Number(months[months.length - 1].slice(0, 4));
  const step = Math.max(1, Math.ceil((endYear - startYear) / Math.max(1, count - 1)));
  const out: TimelineTick[] = [];
  for (let y = Math.ceil(startYear / step) * step; y <= endYear; y += step) {
    const monthIndex = dateToMonthIndex(`${y}-01-01`, months);
    if (monthIndex != null) {
      out.push({
        monthIndex,
        year: y,
        age: primaryBirth ? y - Number(primaryBirth.slice(0, 4)) : null,
      });
    }
  }
  return out;
}
