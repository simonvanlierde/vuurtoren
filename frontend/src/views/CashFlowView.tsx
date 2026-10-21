import { useDeferredValue, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Button } from "@/components/ui/button";
import { ChartFigure } from "../components/ChartFigure";
import { CashFlowDrawer } from "../components/editor/CashFlowDrawer";
import { DataTable } from "../components/ui/DataTable";
import {
  type CashFlow,
  type InlineOverrides,
  type ProjectRequestBody,
  useAccounts,
  useCashFlows,
  useHouseholds,
  usePeople,
  useProjection,
} from "../lib/api";
import { SERIES as PALETTE } from "../lib/chartColors";
import { todayLocal } from "../lib/dates";
import { aggregateFlowsByYear, type YearlyFlowTotals } from "../lib/flowTotals";
import { useT } from "../lib/i18n";
import { formatCents, formatEuroTick, formatMoney } from "../lib/money";
import { BELOW_SM, useMediaQuery } from "../lib/useMediaQuery";

/** Roughly how many bars a 320px plot can draw at a legible width. */
const NARROW_BAR_TARGET = 12;

/**
 * v1 is deliberately just "a stacked bar over the projected flows" —
 * the replace-Actual-Budget ambition is a post-v1 decision. Income stacks above the
 * axis; expenses, contributions and housing (mortgage + VvE) stack below it.
 *
 * The three outflows are separated by *hue*, not by lightness. They were three tints of
 * brick, on the reasoning that outflows share a colour — which collapses to one colour
 * under protanopia, on the only chart where the three below the axis have to be told
 * apart. Beacon amber stays out of it either way; that is the beam's.
 */
const SERIES: {
  key: keyof Omit<YearlyFlowTotals, "year" | "months">;
  msgKey: "flows.income" | "flows.expenses" | "flows.contributions" | "flows.housing";
  color: string;
}[] = [
  { key: "incomeCents", msgKey: "flows.income", color: PALETTE.income },
  { key: "expensesCents", msgKey: "flows.expenses", color: PALETTE.expenses },
  { key: "contributionsCents", msgKey: "flows.contributions", color: PALETTE.contributions },
  { key: "housingCents", msgKey: "flows.housing", color: PALETTE.housing },
];

/** The flow series worth a bar and a legend entry: one that is zero in every year
 * (housing for a household with no home) draws nothing, so naming it only misleads. */
export function visibleFlowSeries(
  rows: readonly Record<(typeof SERIES)[number]["key"], number>[],
): typeof SERIES {
  return SERIES.filter((s) => rows.some((r) => r[s.key] !== 0));
}

export function CashFlowView() {
  const t = useT();
  const households = useHouseholds();
  const people = usePeople();
  const accounts = useAccounts();
  const cashFlows = useCashFlows();
  const household = households.data?.[0];

  const [editing, setEditing] = useState<{ flow: CashFlow | null } | null>(null);
  const [preview, setPreview] = useState<InlineOverrides | null>(null);

  const start = useMemo(() => todayLocal(), []);
  const requestBody = useMemo<ProjectRequestBody>(
    () => (preview ? { start, overrides: preview } : { start }),
    [start, preview],
  );
  const projection = useProjection(useDeferredValue(requestBody));

  const personNames = useMemo(
    () => new Map((people.data ?? []).map((p) => [p.id, p.name] as const)),
    [people.data],
  );
  const accountNames = useMemo(
    () => new Map((accounts.data ?? []).map((a) => [a.id, a.name] as const)),
    [accounts.data],
  );
  const householdFlows = useMemo(
    () => (cashFlows.data ?? []).filter((f) => f.household_id === household?.id),
    [cashFlows.data, household],
  );

  const seriesLabels = useMemo(
    () => new Map(SERIES.map((s) => [s.key as string, t(s.msgKey)] as const)),
    [t],
  );

  const narrow = useMediaQuery(BELOW_SM);

  if (projection.isLoading) {
    return <p className="p-8">{t("today.loading")}</p>;
  }

  const yearly = projection.data
    ? aggregateFlowsByYear(projection.data.months, projection.data.flow_totals)
    : [];
  const chartData = yearly.map((y) => ({
    year: y.year,
    incomeCents: y.incomeCents,
    expensesCents: -y.expensesCents,
    contributionsCents: -y.contributionsCents,
    housingCents: -y.housingCents,
  }));
  const shownSeries = visibleFlowSeries(chartData);
  // A 60-year horizon in a 320px plot left each bar under a pixel wide and Recharts drew
  // nothing at all — an empty chart with intact axes, which reads as "no data" rather than
  // "too narrow". Thin to roughly a dozen categories so the bars have real width; the
  // series is smooth, so every fifth year tells the same story and the tooltip still
  // carries the exact figures. The final year is always kept — it is the one a reader
  // looks for.
  const narrowChartData =
    narrow && chartData.length > NARROW_BAR_TARGET
      ? chartData.filter(
          (_, i) =>
            i % Math.ceil(chartData.length / NARROW_BAR_TARGET) === 0 || i === chartData.length - 1,
        )
      : chartData;

  // The first whole year: the start year holds only the months left after today, so its
  // totals read as half a salary.
  const summary = yearly.find((y) => y.months === 12) ?? yearly[0];
  const projectionFailed = projection.isError || !projection.data;

  return (
    <div className="space-y-8 p-4 sm:p-8">
      <h1 className="font-display text-2xl">{t("flows.title")}</h1>

      {projectionFailed ? (
        <p role="alert" className="text-brick">
          {t("flows.loadError")}
        </p>
      ) : (
        summary && (
          <section aria-labelledby="cash-flow-summary-heading">
            <h2
              id="cash-flow-summary-heading"
              className="text-sm uppercase tracking-wide text-ink-navy/70 dark:text-paper/60"
            >
              {t("flows.totals")} {summary.year}
            </h2>
            {/* One equation, two arrangements. Wrapping the horizontal form at 320px
                scattered the operators away from their terms and the arithmetic stopped
                reading; below sm it becomes a receipt column with the operator leading
                each line. */}
            <div className="mt-2 flex flex-col sm:flex-row sm:flex-wrap sm:items-end sm:gap-x-3 sm:gap-y-2">
              <EquationTerm label={t("flows.income")} cents={summary.incomeCents} />
              <EquationOperator symbol="−" />
              <EquationTerm
                label={t("flows.equation.spending")}
                cents={summary.expensesCents + summary.housingCents}
              />
              <EquationOperator symbol="−" />
              <EquationTerm label={t("flows.contributions")} cents={summary.contributionsCents} />
              <EquationOperator symbol="=" />
              <EquationTerm
                label={t("flows.equation.netSavings")}
                cents={
                  summary.incomeCents -
                  summary.expensesCents -
                  summary.housingCents -
                  summary.contributionsCents
                }
                emphasis
              />
            </div>
          </section>
        )
      )}

      <section aria-labelledby="flows-table-heading">
        <div className="flex items-baseline justify-between">
          <h2
            id="flows-table-heading"
            className="text-sm uppercase tracking-wide text-ink-navy/70 dark:text-paper/60"
          >
            {t("flows.tableHeading")}
          </h2>
          <Button type="button" onClick={() => setEditing({ flow: null })} variant="emphasis">
            {t("flows.add")}
          </Button>
        </div>
        {householdFlows.length > 0 ? (
          <DataTable
            className="mt-2"
            caption={t("flows.tableHeading")}
            rows={householdFlows}
            rowKey={(f) => String(f.id)}
            columns={[
              {
                header: t("flows.table.label"),
                title: true,
                cell: (f) => (
                  <>
                    {f.label}
                    {f.inflation_linked && (
                      <span className="ml-2 rounded border border-ink-navy/20 px-1 text-xs font-normal text-ink-navy/70 dark:border-paper/20 dark:text-paper/60">
                        {t("flows.indexedChip")}
                      </span>
                    )}
                  </>
                ),
              },
              { header: t("flows.table.kind"), cell: (f) => t(`flows.kind.${f.kind}`) },
              {
                header: t("flows.table.owner"),
                cell: (f) =>
                  f.owner_person_id != null
                    ? (personNames.get(f.owner_person_id) ?? "—")
                    : t("editor.account.household"),
              },
              {
                header: t("flows.table.target"),
                cell: (f) =>
                  f.target_account_id != null
                    ? (accountNames.get(f.target_account_id) ?? "—")
                    : "—",
              },
              {
                header: t("flows.table.period"),
                cell: (f) => (
                  <span className="tabular-nums">
                    {f.start_date ?? "…"} – {f.end_date ?? t("flows.period.open")}
                  </span>
                ),
              },
              {
                header: t("flows.table.amount"),
                numeric: true,
                cell: (f) => formatMoney(f.amount_monthly),
              },
              {
                header: t("today.actions"),
                headerHidden: true,
                full: true,
                cell: (f) => (
                  <div className="-my-2 flex sm:justify-end">
                    <Button
                      type="button"
                      onClick={() => setEditing({ flow: f })}
                      aria-label={`${t("today.edit")}: ${f.label}`}
                      variant="link"
                    >
                      {t("today.edit")}
                    </Button>
                  </div>
                ),
              },
            ]}
          />
        ) : (
          <div className="mt-2 flex flex-wrap items-center gap-3 py-2 text-ink-navy/70 dark:text-paper/60">
            <span>
              {households.data && households.data.length === 0
                ? t("empty.noHousehold")
                : t("flows.none")}
            </span>
            {households.data && households.data.length === 0 ? (
              <Button
                type="button"
                onClick={() => {
                  window.location.hash = "#settings";
                }}
              >
                {t("empty.noHousehold.cta")}
              </Button>
            ) : (
              <Button type="button" onClick={() => setEditing({ flow: null })} variant="emphasis">
                {t("flows.add")}
              </Button>
            )}
          </div>
        )}
      </section>

      {!projectionFailed && (
        <section aria-labelledby="cash-flow-chart-heading">
          <h2
            id="cash-flow-chart-heading"
            className="text-sm uppercase tracking-wide text-ink-navy/70 dark:text-paper/60"
          >
            {t("flows.chartHeading")}
          </h2>
          <ChartFigure
            label={t("flows.chartHeading")}
            summary={[
              `${t("chart.start")} ${chartData[0]?.year ?? ""}`,
              `${t("chart.end")} ${chartData.at(-1)?.year ?? ""}`,
              ...shownSeries.map(
                (s) =>
                  `${seriesLabels.get(s.key) ?? s.key} ${formatCents(
                    Math.abs(chartData.at(-1)?.[s.key] ?? 0),
                  )}`,
              ),
            ].join(" · ")}
            className="mt-2 h-80 w-full"
          >
            <ResponsiveContainer width="100%" height="100%">
              {/* stackOffset="sign": income (positive) and the negated outflows share one
                stackId, and the default cumulative offset would draw the outflow bands
                hanging down from the top of the income bar instead of below the axis. */}
              <BarChart
                data={narrowChartData}
                stackOffset="sign"
                margin={{ top: 8, right: 8, left: 0, bottom: 8 }}
              >
                <XAxis dataKey="year" tick={{ fontSize: 12 }} stroke="currentColor" />
                <YAxis
                  tick={{ fontSize: 12 }}
                  stroke="currentColor"
                  width={narrow ? 56 : 88}
                  tickFormatter={(value: number) => formatEuroTick(value / 100)}
                />
                <Tooltip
                  formatter={(value, name) => [
                    formatCents(Math.abs(value as number)),
                    seriesLabels.get(name as string) ?? name,
                  ]}
                />
                {/* Recharts draws legend text in the series colour by default, which is
                    what failed contrast in the dark theme (2.40:1, 3.51:1, 3.64:1). The
                    swatch keeps the colour and needs 3:1; the label is ink or paper and
                    is not carrying the encoding. */}
                <Legend
                  formatter={(value) => (
                    <span className="text-ink-navy dark:text-paper">
                      {seriesLabels.get(value as string) ?? value}
                    </span>
                  )}
                />
                <ReferenceLine y={0} stroke="currentColor" />
                {shownSeries.map((s) => (
                  <Bar key={s.key} dataKey={s.key} stackId="flow" fill={s.color} name={s.key} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </ChartFigure>
          <p className="mt-2 text-sm text-ink-navy/70 dark:text-paper/60">{t("flows.chartNote")}</p>
        </section>
      )}

      {editing && household && (
        <CashFlowDrawer
          key={editing.flow?.id ?? "new"}
          open
          onOpenChange={(o) => {
            if (!o) setEditing(null);
          }}
          cashFlow={editing.flow}
          householdId={household.id}
          people={people.data ?? []}
          accounts={(accounts.data ?? []).filter((a) => a.household_id === household.id)}
          onPreview={setPreview}
        />
      )}
    </div>
  );
}

function EquationTerm({
  label,
  cents,
  emphasis = false,
}: {
  label: string;
  cents: number;
  emphasis?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-t border-ink-navy/10 py-2 sm:block sm:justify-start sm:py-0 sm:pt-2 dark:border-paper/10">
      <div className="text-sm">{label}</div>
      <div className={`tabular-nums ${emphasis ? "font-display text-xl" : "font-medium"}`}>
        {formatCents(cents)}
      </div>
    </div>
  );
}

/** The operator between two equation terms: a leading glyph on the stacked mobile
 * arrangement, a separator between columns from `sm` up. */
function EquationOperator({ symbol }: { symbol: string }) {
  return (
    <div
      aria-hidden="true"
      className="text-lg leading-none text-ink-navy/70 sm:pb-1 dark:text-paper/60"
    >
      {symbol}
    </div>
  );
}
