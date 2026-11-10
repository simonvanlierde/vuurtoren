/** The crossover chart: monthly passive income (investment returns) against
 * monthly expenses — the *Your Money or Your Life* chart. The crossover month, where
 * returns first cover expenses, is the genre's most motivating milestone. Deterministic;
 * `investment_income` and `flow_totals.expenses` are both already on the response. */
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ProjectionResponse } from "../../lib/api";
import { SERIES } from "../../lib/chartColors";
import { crossoverMonth, crossoverRows } from "../../lib/crossover";
import { useLocale, useT } from "../../lib/i18n";
import { formatEuros, formatEuroTick } from "../../lib/money";
import { BELOW_SM, useMediaQuery } from "../../lib/useMediaQuery";
import { ChartFigure } from "../ChartFigure";
import { ChartLegend } from "../ChartLegend";
import { CsvButton } from "./CsvButton";
import { formatMonth } from "./HeadlineStrip";

export function CrossoverPanel({ data }: { data: ProjectionResponse }) {
  const t = useT();
  const [locale] = useLocale();
  const narrow = useMediaQuery(BELOW_SM);
  const rows = crossoverRows(data);
  const crossover = crossoverMonth(rows);
  const sentence =
    crossover != null
      ? t("plan.crossover.sentence").replace("{month}", formatMonth(crossover, "", locale))
      : t("plan.crossover.notYet");

  return (
    <section aria-labelledby="crossover-heading" className="space-y-3 p-4 sm:p-8">
      <div className="flex items-center justify-between gap-4">
        <h2
          id="crossover-heading"
          className="text-sm uppercase tracking-wide text-ink-navy/70 dark:text-paper/60"
        >
          {t("plan.crossover.heading")}
        </h2>
        <CsvButton
          filename="kruispunt.csv"
          columns={[
            { header: "month", values: rows.map((r) => r.month) },
            { header: "passive_income_eur", values: rows.map((r) => r.passive) },
            { header: "expenses_eur", values: rows.map((r) => r.expense) },
          ]}
        />
      </div>
      <ChartFigure
        label={t("plan.crossover.heading")}
        summary={[
          `${t("plan.crossover.passive")}: ${t("chart.start")} ${formatEuros(rows[0]?.passive ?? 0)}, ${t("chart.end")} ${formatEuros(rows.at(-1)?.passive ?? 0)}`,
          `${t("plan.crossover.expenses")}: ${t("chart.start")} ${formatEuros(rows[0]?.expense ?? 0)}, ${t("chart.end")} ${formatEuros(rows.at(-1)?.expense ?? 0)}`,
          sentence,
        ].join(" · ")}
        className="h-64 w-full"
      >
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
            <CartesianGrid strokeOpacity={0.1} vertical={false} />
            <XAxis
              dataKey="month"
              tick={{ fontSize: 12 }}
              stroke="currentColor"
              minTickGap={48}
              tickFormatter={(m: string) => m.slice(0, 4)}
            />
            <YAxis
              tick={{ fontSize: 12 }}
              stroke="currentColor"
              width={narrow ? 56 : 72}
              tickFormatter={formatEuroTick}
            />
            <Tooltip
              formatter={(value) =>
                typeof value === "number" ? formatEuros(value) : String(value)
              }
            />
            {/* stroke via class, not the prop: the literal amber was 1.73:1 on paper, so the
             * one marker this panel exists to show was invisible in the light theme. A CSS
             * rule also beats the presentation attribute, which cannot resolve var(). */}
            {crossover != null && (
              <ReferenceLine x={crossover} className="stroke-ring" strokeWidth={2} />
            )}
            <Line
              dataKey="passive"
              name={t("plan.crossover.passive")}
              stroke={SERIES.investments}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              dataKey="expense"
              name={t("plan.crossover.expenses")}
              stroke={SERIES.expenses}
              strokeWidth={2}
              strokeDasharray="6 3"
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </ChartFigure>
      {/* The chart's whole claim is "this line crosses that one", so the pair is named,
          and the target line is dashed so it also separates without hue. Expenses are
          off amber: amber is the crossover marker's. */}
      <ChartLegend
        items={[
          {
            key: "passive",
            label: t("plan.crossover.passive"),
            color: SERIES.investments,
            mark: "line",
          },
          {
            key: "expense",
            label: t("plan.crossover.expenses"),
            color: SERIES.expenses,
            mark: "line",
            dash: "6 3",
          },
        ]}
      />
      <p className="max-w-prose text-sm text-ink-navy/70 dark:text-paper/70">{sentence}</p>
    </section>
  );
}
