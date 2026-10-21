/** FIRE-date distribution: the fan chart shows
 * net-worth percentiles, but the question people ask is *when*. A histogram of FI dates
 * across the Monte Carlo runs, plus one plain-language sentence. Re-aggregation of the
 * per-run `fi_dates` the MC response now carries — no engine change. */
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { SERIES } from "../../lib/chartColors";
import { useT } from "../../lib/i18n";
import { formatPercent } from "../../lib/money";
import { ChartFigure } from "../ChartFigure";

const P90 = 0.9;

export function FireDateHistogram({ fiDates }: { fiDates: (string | null)[] }) {
  const t = useT();
  const total = fiDates.length;
  const reached = fiDates.filter((d): d is string => d !== null);

  const byYear = new Map<number, number>();
  for (const d of reached) {
    const year = Number(d.slice(0, 4));
    byYear.set(year, (byYear.get(year) ?? 0) + 1);
  }
  const years = [...byYear.keys()].sort((a, b) => a - b);
  const rows = years.map((year) => ({ year, runs: byYear.get(year) ?? 0 }));

  // The earliest year by which 90% of ALL runs (nevers included) have reached FI.
  let cumulative = 0;
  let p90Year: number | null = null;
  for (const year of years) {
    cumulative += byYear.get(year) ?? 0;
    if (cumulative / total >= P90) {
      p90Year = year;
      break;
    }
  }

  const sentence =
    p90Year !== null
      ? t("plan.onzekerheid.histogram.sentence")
          .replace("{pct}", formatPercent(P90))
          .replace("{year}", String(p90Year))
      : t("plan.onzekerheid.histogram.mostNever").replace(
          "{pct}",
          formatPercent(reached.length / total),
        );

  if (rows.length === 0) return null;

  // The modal year — the one a reader picks out of the bars at a glance.
  const peak = rows.reduce((best, r) => (r.runs > best.runs ? r : best), rows[0]);

  return (
    <section aria-labelledby="fire-hist-heading">
      <h2
        id="fire-hist-heading"
        className="text-sm uppercase tracking-wide text-ink-navy/70 dark:text-paper/60"
      >
        {t("plan.onzekerheid.histogram.heading")}
      </h2>
      <ChartFigure
        label={t("plan.onzekerheid.histogram.heading")}
        summary={[
          `${t("chart.start")} ${rows[0].year}`,
          `${t("chart.end")} ${rows[rows.length - 1].year}`,
          `${t("chart.high")} ${peak.year} (${peak.runs}/${total})`,
        ].join(" · ")}
        className="mt-2 h-56 w-full"
      >
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
            <CartesianGrid strokeOpacity={0.1} vertical={false} />
            <XAxis dataKey="year" tick={{ fontSize: 12 }} stroke="currentColor" minTickGap={24} />
            <YAxis tick={{ fontSize: 12 }} stroke="currentColor" width={40} allowDecimals={false} />
            <Tooltip
              formatter={(value) => [String(value), t("plan.onzekerheid.histogram.runs")]}
              labelFormatter={(label) => String(label)}
            />
            <Bar
              dataKey="runs"
              fill={SERIES.investments}
              fillOpacity={0.7}
              isAnimationActive={false}
            />
          </BarChart>
        </ResponsiveContainer>
      </ChartFigure>
      <p className="mt-2 max-w-prose text-sm text-ink-navy/70 dark:text-paper/70">{sentence}</p>
    </section>
  );
}
