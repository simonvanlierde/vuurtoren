/** The crossover chart: monthly passive income (investment returns) against
 * monthly expenses — the *Your Money or Your Life* chart. The crossover month, where
 * returns first cover expenses, is the genre's most motivating milestone. Deterministic;
 * `investment_income` and `flow_totals.expenses` are both already on the response. */
import {
  CartesianGrid,
  Legend,
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
import { useT } from "../../lib/i18n";
import { formatEuros, formatEuroTick } from "../../lib/money";
import { BELOW_SM, useMediaQuery } from "../../lib/useMediaQuery";
import { ChartFigure } from "../ChartFigure";
import { CsvButton } from "./CsvButton";

export function CrossoverPanel({ data }: { data: ProjectionResponse }) {
  const t = useT();
  const narrow = useMediaQuery(BELOW_SM);
  const passive = data.investment_income[0] ?? [];
  const expenses = data.flow_totals.expenses;
  const rows = data.months.map((month, i) => ({
    month,
    passive: Math.round(passive[i] ?? 0),
    expense: Math.round(expenses[i] ?? 0),
  }));

  // First month (past the opening index) where passive income covers expenses.
  const crossover = rows.find((r, i) => i > 0 && r.expense > 0 && r.passive >= r.expense);
  const sentence =
    crossover != null
      ? t("plan.crossover.sentence").replace("{month}", crossover.month)
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
              <ReferenceLine x={crossover.month} className="stroke-ring" strokeWidth={2} />
            )}
            {/* The chart's whole claim is "this line crosses that one", and it was made in
                colour alone — no legend at all, against the product's own floor. Named
                here, and the target line is dashed so the pair also separates without
                hue. Expenses moved off amber too: amber is the crossover marker's, and
                two ambers on one plot make the moment compete with the thing crossing. */}
            <Legend
              formatter={(value) => <span className="text-ink-navy dark:text-paper">{value}</span>}
            />
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
      <p className="max-w-prose text-sm text-ink-navy/70 dark:text-paper/70">{sentence}</p>
    </section>
  );
}
