import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { SERIES } from "../lib/chartColors";
import { useT } from "../lib/i18n";
import { formatCents } from "../lib/money";
import type { NetWorthPoint } from "../lib/netWorthSeries";
import { BELOW_SM, useMediaQuery } from "../lib/useMediaQuery";
import { ChartFigure } from "./ChartFigure";

/** Recharts for standard charts — the timeline's hand-drawn beam is a later view. */
export function NetWorthChart({ series }: { series: readonly NetWorthPoint[] }) {
  const t = useT();
  const narrow = useMediaQuery(BELOW_SM);
  const data = series.map((point) => ({ date: point.date, euros: point.totalCents / 100 }));
  const cents = series.map((point) => point.totalCents);
  const summary = [
    `${t("chart.start")} ${series[0]?.date ?? ""} ${formatCents(cents[0] ?? 0)}`,
    `${t("chart.end")} ${series.at(-1)?.date ?? ""} ${formatCents(cents.at(-1) ?? 0)}`,
    `${t("chart.low")} ${formatCents(cents.length ? Math.min(...cents) : 0)}`,
    `${t("chart.high")} ${formatCents(cents.length ? Math.max(...cents) : 0)}`,
  ].join(" · ");

  return (
    <ChartFigure label={t("plan.chart.netWorth")} summary={summary} className="mt-2 h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
          <XAxis dataKey="date" tick={{ fontSize: 12 }} stroke="currentColor" />
          <YAxis
            tick={{ fontSize: 12 }}
            stroke="currentColor"
            width={narrow ? 56 : 88}
            tickFormatter={(value: number) => formatCents(Math.round(value * 100))}
          />
          <Tooltip
            formatter={(value) =>
              typeof value === "number" ? formatCents(Math.round(value * 100)) : value
            }
          />
          <Line
            type="monotone"
            dataKey="euros"
            stroke={SERIES.investments}
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </ChartFigure>
  );
}
