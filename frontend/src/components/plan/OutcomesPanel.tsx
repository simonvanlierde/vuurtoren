/** "Rich, broke or dead" — the chart no Dutch planner has.
 *
 * A success probability quietly assumes you are alive to spend the money. Stacking the
 * three outcomes shows what the fan chart cannot: most plans look far less
 * over-conservative once "alive to enjoy it" is on the axis. */
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { SERIES } from "../../lib/chartColors";
import { useT } from "../../lib/i18n";
import { formatPercent } from "../../lib/money";
import { buildOutcomeRows, outcomeSummary } from "../../lib/mortality";
import { BELOW_SM, useMediaQuery } from "../../lib/useMediaQuery";
import { ChartFigure } from "../ChartFigure";

export function OutcomesPanel({
  months,
  solventFraction,
  survival,
}: {
  months?: string[];
  solventFraction?: number[];
  survival?: number[];
}) {
  const t = useT();
  const narrow = useMediaQuery(BELOW_SM);

  if (!months || !solventFraction || !survival) {
    return <p className="text-ink-navy/70 dark:text-paper/60 text-sm">{t("plan.outcomes.idle")}</p>;
  }

  const rows = buildOutcomeRows(months, solventFraction, survival);
  const end = outcomeSummary(rows);

  return (
    <section aria-labelledby="outcomes-heading" className="space-y-2">
      <h3
        id="outcomes-heading"
        className="text-ink-navy/70 dark:text-paper/60 text-sm tracking-wide uppercase"
      >
        {t("plan.outcomes.heading")}
      </h3>
      <ChartFigure label={t("plan.outcomes.heading")} className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
            <CartesianGrid strokeOpacity={0.1} vertical={false} />
            <XAxis
              dataKey="month"
              tick={{ fontSize: 12 }}
              stroke="currentColor"
              tickFormatter={(d: string) => d.slice(0, 4)}
              minTickGap={40}
            />
            <YAxis
              tick={{ fontSize: 12 }}
              stroke="currentColor"
              width={narrow ? 40 : 52}
              domain={[0, 1]}
              tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
            />
            <Tooltip
              formatter={(v) => (typeof v === "number" ? formatPercent(v) : v)}
              labelFormatter={(d) => (typeof d === "string" ? d : String(d))}
            />
            {/* Three stacked bands told apart by colour alone fail WCAG 1.4.1; the legend
                names them, styled like the crossover chart's. */}
            <Legend
              iconType="square"
              formatter={(value) => <span className="text-ink-navy dark:text-paper">{value}</span>}
            />
            <Area
              dataKey="rich"
              stackId="o"
              name={t("plan.outcomes.rich")}
              stroke="none"
              fill={SERIES.income}
              fillOpacity={0.75}
              isAnimationActive={false}
            />
            <Area
              dataKey="broke"
              stackId="o"
              name={t("plan.outcomes.broke")}
              stroke="none"
              fill={SERIES.expenses}
              fillOpacity={0.75}
              isAnimationActive={false}
            />
            <Area
              dataKey="dead"
              stackId="o"
              name={t("plan.outcomes.dead")}
              stroke="none"
              fill={SERIES.neutral}
              fillOpacity={0.45}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </ChartFigure>
      {end && (
        <p className="text-ink-navy/70 dark:text-paper/70 max-w-prose text-sm">
          {t("plan.outcomes.caption")
            .replace("{year}", end.month.slice(0, 4))
            .replace("{rich}", formatPercent(end.rich))
            .replace("{broke}", formatPercent(end.broke))
            .replace("{dead}", formatPercent(end.dead))}
        </p>
      )}
      <p className="text-ink-navy/70 dark:text-paper/50 max-w-prose text-xs">
        {t("plan.outcomes.source")}
      </p>
    </section>
  );
}
