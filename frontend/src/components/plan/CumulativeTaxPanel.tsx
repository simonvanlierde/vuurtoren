/** Cumulative tax over the plan: the engine already
 * returns tax per year in `tax_paid` — summing and charting it makes the lifetime cost of
 * Box 3 visceral. Frontend-only; the data is already on the deterministic response.
 *
 * NOTE: nominal euros. `tax_paid` is per-year while `inflation_factor` is per-month, so
 * real-terms deflation is fiddly and a cumulative total-cost figure is the number people
 * quote. Real-terms deferred. Transfer tax (a one-off closing cost, not recurring plan tax)
 * is left off the line. */
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ProjectionResponse } from "../../lib/api";
import { SERIES } from "../../lib/chartColors";
import { useT } from "../../lib/i18n";
import { formatEuros, formatEuroTick, formatPercent } from "../../lib/money";
import { BELOW_SM, useMediaQuery } from "../../lib/useMediaQuery";
import { ChartFigure } from "../ChartFigure";
import { CsvButton } from "./CsvButton";

const WEALTH_TAX = "investment_tax";

export function CumulativeTaxPanel({
  data,
  grossSwr,
  country,
}: {
  data: ProjectionResponse;
  grossSwr: number;
  /** The household's tax country. "Box 3" is the name of a Dutch schedule, so the copy
   * may only say it for NL; every other regime gets the neutral wording. */
  country: string | undefined;
}) {
  const t = useT();
  const nl = country === "NL";
  const narrow = useMediaQuery(BELOW_SM);
  const years = [...new Set(data.months.map((m) => Number(m.slice(0, 4))))];
  const keys = Object.keys(data.tax_paid);
  const yearCount = Math.min(years.length, data.tax_paid[keys[0]]?.[0]?.length ?? 0);

  let cumulative = 0;
  let cumulativeBox3 = 0;
  const rows: { year: number; cumulative: number }[] = [];
  for (let i = 0; i < yearCount; i++) {
    cumulative += keys.reduce((sum, k) => sum + (data.tax_paid[k][0][i] ?? 0), 0);
    cumulativeBox3 += data.tax_paid[WEALTH_TAX]?.[0]?.[i] ?? 0;
    rows.push({ year: years[i], cumulative });
  }

  if (rows.length === 0) {
    return (
      <p className="p-4 text-sm text-ink-navy/70 dark:text-paper/60 sm:p-8">
        {t("plan.cumtax.empty")}
      </p>
    );
  }

  const sentence = t(nl ? "plan.cumtax.sentence" : "plan.cumtax.sentenceOther").replace(
    "{box3}",
    formatEuros(cumulativeBox3),
  );
  const netSwr = data.fire.net_swr;
  const drag = Math.max(0, grossSwr - netSwr);
  const swrSentence = t(nl ? "plan.cumtax.netSwr" : "plan.cumtax.netSwrOther")
    .replace("{net}", formatPercent(netSwr))
    .replace("{drag}", formatPercent(drag))
    .replace("{gross}", formatPercent(grossSwr));

  return (
    <section aria-labelledby="cum-tax-heading" className="space-y-3 p-4 sm:p-8">
      <div className="flex items-center justify-between gap-4">
        <h2
          id="cum-tax-heading"
          className="text-sm uppercase tracking-wide text-ink-navy/70 dark:text-paper/60"
        >
          {t("plan.cumtax.heading")}
        </h2>
        <CsvButton
          filename="belasting-cumulatief.csv"
          columns={[
            { header: "year", values: rows.map((r) => r.year) },
            { header: "cumulative_tax_eur", values: rows.map((r) => Math.round(r.cumulative)) },
          ]}
        />
      </div>
      <ChartFigure
        label={t("plan.cumtax.heading")}
        summary={[
          `${t("chart.start")} ${rows[0].year} ${formatEuros(rows[0].cumulative)}`,
          `${t("chart.end")} ${rows[rows.length - 1].year} ${formatEuros(rows[rows.length - 1].cumulative)}`,
        ].join(" · ")}
        className="h-64 w-full"
      >
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
            <CartesianGrid strokeOpacity={0.1} vertical={false} />
            <XAxis dataKey="year" tick={{ fontSize: 12 }} stroke="currentColor" minTickGap={32} />
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
              labelFormatter={(label) => String(label)}
            />
            <Area
              dataKey="cumulative"
              stroke={SERIES.focus}
              fill={SERIES.focus}
              fillOpacity={0.18}
              strokeWidth={2}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </ChartFigure>
      <p className="max-w-prose text-sm text-ink-navy/70 dark:text-paper/70">{sentence}</p>
      <p className="max-w-prose border-t border-ink-navy/10 pt-3 text-sm text-ink-navy/70 dark:border-paper/10 dark:text-paper/70">
        {swrSentence}
      </p>
    </section>
  );
}
