/** The Scenario's lens: overlay chart of the baseline against up to four selected
 * scenarios, with the picker chips directly under the chart; the end-state table and
 * templates live in the shared deck's own tabs. */
import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Button } from "@/components/ui/button";
import {
  useCreateScenario,
  useProjection,
  useScenarioProjections,
  useScenarioSuccess,
  useScenarios,
} from "../../lib/api";
import { useLocale, useT } from "../../lib/i18n";
import { formatEuros, formatEuroTick, formatPercent } from "../../lib/money";
import { toReal } from "../../lib/realTerms";
import {
  buildOverlayRows,
  hasUserTaxOverride,
  LINE_ENCODINGS,
  type OverlayColumn,
  standardTaxScenarios,
} from "../../lib/scenarioCompare";
import { BELOW_SM, useMediaQuery } from "../../lib/useMediaQuery";
import type { usePlanState } from "../../lib/usePlanState";
import { ChartFigure } from "../ChartFigure";
import { DataTable } from "../ui/DataTable";
import { EditedBadge } from "../ui/EditedBadge";
import { AflossenVsBeleggenForm } from "./AflossenVsBeleggenForm";
import { AllocationForm } from "./AllocationForm";
import { Deck } from "./Deck";
import { formatMonth, type HeadlineSlot } from "./HeadlineStrip";
import { IncomeShockForm } from "./IncomeShockForm";
import { RentVsBuyForm } from "./RentVsBuyForm";
import { RetirementSmileForm } from "./RetirementSmileForm";

const MAX_SELECTED = 4;
// One fixed seed across every column so success probabilities are comparable.
const SUCCESS_SEED = 20260724;

interface Column {
  key: string;
  label: string;
  marked: boolean;
  encoding: (typeof LINE_ENCODINGS)[number];
  netWorth?: number[];
  fiDate?: string | null;
}

export function ScenariosLens({
  plan,
  setSlot,
}: {
  plan: ReturnType<typeof usePlanState>;
  setSlot: (s: HeadlineSlot) => void;
}) {
  const t = useT();
  const [locale] = useLocale();
  const narrow = useMediaQuery(BELOW_SM);
  const household = plan.household;
  const scenarios = useScenarios();
  const createScenario = useCreateScenario();

  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [runSuccess, setRunSuccess] = useState(false);

  const list = scenarios.data ?? [];
  const selected = list.filter((s) => selectedIds.includes(s.id));

  const baseline = useProjection(plan.deferredRequest);
  const scenarioProjections = useScenarioProjections(
    plan.scenarioBase,
    selected.map((s) => s.id),
  );
  const successQueries = useScenarioSuccess(
    plan.scenarioBase,
    [null, ...selected.map((s) => s.id)],
    SUCCESS_SEED,
    runSuccess,
  );

  const months = baseline.data?.months ?? [];

  // Real-terms toggle: deflate every overlaid line by its own inflation
  // factor, so the whole comparison — chart and end-state table — reads in one basis.
  const deflate = (nw?: number[], f?: number[]) => (plan.realTerms && nw && f ? toReal(nw, f) : nw);

  const columns: Column[] = [
    {
      key: "baseline",
      label: t("plan.scenarios.baselineLabel"),
      marked: false,
      encoding: LINE_ENCODINGS[0],
      netWorth: deflate(baseline.data?.net_worth[0], baseline.data?.inflation_factor),
      fiDate: baseline.data?.fire.fi_dates[0],
    },
    ...selected.map((s, i): Column => {
      const data = scenarioProjections[i]?.data;
      return {
        key: `s${s.id}`,
        label: s.name,
        marked: hasUserTaxOverride(s.overrides),
        encoding: LINE_ENCODINGS[(i + 1) % LINE_ENCODINGS.length],
        netWorth: deflate(data?.net_worth[0], data?.inflation_factor),
        fiDate: data?.fire.fi_dates[0],
      };
    }),
  ];

  const chartColumns: OverlayColumn[] = columns
    .filter((c) => c.netWorth)
    .map((c) => ({ key: c.key, netWorth: c.netWorth ?? [] }));
  const rows = useMemo(() => buildOverlayRows(months, chartColumns), [months, chartColumns]);

  // successQueries is aligned to [baseline, ...selected]; index 0 is the baseline column.
  const successFor = (colIndex: number): number | undefined =>
    runSuccess ? successQueries[colIndex]?.data?.success_probability : undefined;

  const firstSelectedColumn = columns[1];
  const baselineFi = baseline.data?.fire.fi_dates[0];
  // While the relevant column hasn't resolved yet, its netWorth is still undefined —
  // show "—" rather than formatMonth's not-reached text, which claims something
  // different (data arrived, but FI just isn't inside the horizon).
  const fiLoaded = firstSelectedColumn
    ? firstSelectedColumn.netWorth !== undefined
    : baseline.data !== undefined;
  // biome-ignore lint/correctness/useExhaustiveDependencies: t is stable per locale, so locale substitutes for it in deps
  useEffect(() => {
    setSlot({
      label: t("plan.headline.scenarioFi"),
      value: fiLoaded
        ? formatMonth(firstSelectedColumn?.fiDate ?? baselineFi, t("plan.notReached"), locale)
        : "—",
    });
  }, [fiLoaded, firstSelectedColumn?.fiDate, baselineFi, locale]);

  function toggle(id: number) {
    setRunSuccess(false);
    setSelectedIds((prev) =>
      prev.includes(id)
        ? prev.filter((x) => x !== id)
        : prev.length >= MAX_SELECTED
          ? prev
          : [...prev, id],
    );
  }

  function addStandardSet() {
    if (!household) return;
    const existing = new Set(list.map((s) => s.name));
    for (const payload of standardTaxScenarios(household.id, new Date().getFullYear())) {
      if (!existing.has(payload.name)) createScenario.mutate(payload);
    }
  }

  const successPending = runSuccess && successQueries.some((q) => q.isPending);

  return (
    <div className="space-y-6 px-4 sm:px-8">
      <p className="text-ink-navy/70 dark:text-paper/70 max-w-prose text-sm">
        {t("plan.scenarios.intro")}
      </p>

      <section aria-labelledby="overlay-heading">
        <h2
          id="overlay-heading"
          className="text-ink-navy/70 dark:text-paper/60 text-sm tracking-wide uppercase"
        >
          {t("plan.scenarios.chart.heading")}
        </h2>
        <ChartFigure label={t("plan.scenarios.chart.heading")} className="mt-2 h-80 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
              <CartesianGrid strokeOpacity={0.1} vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 12 }}
                stroke="currentColor"
                tickFormatter={(d: string) => d.slice(0, 4)}
                minTickGap={40}
              />
              <YAxis
                tick={{ fontSize: 12 }}
                stroke="currentColor"
                width={narrow ? 56 : 88}
                tickFormatter={(value: number) => formatEuroTick(value)}
              />
              <Tooltip
                labelFormatter={(d) => (typeof d === "string" ? d : String(d))}
                formatter={(value, name) => [
                  typeof value === "number" ? formatEuros(value) : value,
                  name,
                ]}
              />
              {columns
                .filter((c) => c.netWorth)
                .map((c) => (
                  <Line
                    key={c.key}
                    type="monotone"
                    dataKey={c.key}
                    name={c.marked ? `${c.label} (${t("plan.scenarios.editedRates")})` : c.label}
                    stroke={c.encoding.color}
                    strokeWidth={2}
                    strokeDasharray={c.encoding.dash}
                    dot={false}
                    isAnimationActive={false}
                    connectNulls
                  />
                ))}
            </LineChart>
          </ResponsiveContainer>
        </ChartFigure>
        {/* Text equivalent: the legend below plus the metrics table are
            the chart's non-visual reading. */}
        <ul className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-sm">
          {columns
            .filter((c) => c.netWorth)
            .map((c) => (
              <li key={c.key} className="flex items-center gap-2">
                <span
                  aria-hidden
                  className="inline-block h-0.5 w-6"
                  style={{
                    backgroundImage: c.encoding.dash
                      ? `repeating-linear-gradient(to right, ${c.encoding.color} 0 4px, transparent 4px 7px)`
                      : undefined,
                    backgroundColor: c.encoding.dash ? undefined : c.encoding.color,
                  }}
                />
                <span>{c.label}</span>
                {c.marked && <EditedBadge>{t("plan.scenarios.editedRates")}</EditedBadge>}
              </li>
            ))}
        </ul>
      </section>

      <section aria-labelledby="picker-heading">
        <h2
          id="picker-heading"
          className="text-ink-navy/70 dark:text-paper/60 text-sm tracking-wide uppercase"
        >
          {t("plan.scenarios.picker.heading")
            .replace("{selected}", String(selected.length))
            .replace("{max}", String(MAX_SELECTED))}
        </h2>

        {scenarios.isLoading ? (
          <p className="mt-3 text-sm">{t("plan.scenarios.picker.loading")}</p>
        ) : list.length === 0 ? (
          <p className="text-ink-navy/70 dark:text-paper/60 mt-3 text-sm">
            {t("plan.scenarios.picker.empty")}
          </p>
        ) : (
          <ul className="mt-3 flex flex-wrap gap-2">
            {list.map((s) => {
              const checked = selectedIds.includes(s.id);
              const marked = hasUserTaxOverride(s.overrides);
              const full = !checked && selectedIds.length >= MAX_SELECTED;
              return (
                <li key={s.id}>
                  <label
                    className={`flex min-h-11 items-center gap-2 rounded border px-3 py-1.5 text-sm ${
                      checked
                        ? "border-ink-navy dark:border-paper"
                        : "border-ink-navy/20 dark:border-paper/20"
                    } ${full ? "opacity-40" : ""}`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={full}
                      onChange={() => toggle(s.id)}
                      className="size-5 accent-ink-navy dark:accent-paper"
                    />
                    <span>{s.name}</span>
                    {marked && <EditedBadge>{t("plan.scenarios.editedRates")}</EditedBadge>}
                  </label>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <Deck
        plan={plan}
        extra={[
          {
            value: "eindstand",
            label: t("plan.deck.endstate"),
            content: (
              <section aria-labelledby="metrics-heading" className="p-4 sm:p-8">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h2
                    id="metrics-heading"
                    className="text-ink-navy/70 dark:text-paper/60 text-sm tracking-wide uppercase"
                  >
                    {t("plan.scenarios.metrics.heading")}
                  </h2>
                  <Button
                    type="button"
                    onClick={() => setRunSuccess(true)}
                    disabled={successPending}
                    variant="emphasis"
                  >
                    {successPending
                      ? t("plan.scenarios.computing")
                      : t("plan.scenarios.computeSuccess")}
                  </Button>
                </div>
                <DataTable
                  className="mt-2"
                  caption={t("plan.scenarios.table.scenario")}
                  rows={columns.map((c, index) => ({ ...c, index }))}
                  rowKey={(c) => c.key}
                  columns={[
                    {
                      header: t("plan.scenarios.table.scenario"),
                      title: true,
                      cell: (c) => (
                        <span className="flex items-center gap-2">
                          {c.label}
                          {c.marked && <EditedBadge>{t("plan.scenarios.editedRates")}</EditedBadge>}
                        </span>
                      ),
                    },
                    {
                      header: t("plan.scenarios.table.endWorth"),
                      numeric: true,
                      cell: (c) => (c.netWorth ? formatEuros(c.netWorth.at(-1) ?? 0) : "—"),
                    },
                    {
                      header: t("plan.scenarios.table.fiDate"),
                      numeric: true,
                      cell: (c) => formatMonth(c.fiDate, t("plan.notReached"), locale),
                    },
                    {
                      header: t("plan.scenarios.table.successRate"),
                      numeric: true,
                      cell: (c) =>
                        successFor(c.index) !== undefined
                          ? formatPercent(successFor(c.index) ?? 0)
                          : "—",
                    },
                  ]}
                />
                <p className="text-ink-navy/70 dark:text-paper/60 mt-2 text-xs">
                  {t("plan.scenarios.metrics.footnote")
                    .replace("{paths}", (1000).toLocaleString(locale === "nl" ? "nl-NL" : "en-US"))
                    .replace("{seed}", String(SUCCESS_SEED))}
                </p>
              </section>
            ),
          },
          {
            value: "sjablonen",
            label: t("plan.deck.templates"),
            content: (
              <div className="space-y-6 p-4 sm:p-8">
                <Button
                  type="button"
                  onClick={addStandardSet}
                  disabled={!household || createScenario.isPending}
                  variant="outline"
                >
                  {t("plan.scenarios.addStandardSet")}
                </Button>

                <section aria-labelledby="rent-vs-buy-heading">
                  <h2
                    id="rent-vs-buy-heading"
                    className="text-ink-navy/70 dark:text-paper/60 text-sm tracking-wide uppercase"
                  >
                    {t("plan.scenarios.rentVsBuy.heading")}
                  </h2>
                  {household && (
                    <RentVsBuyForm
                      householdId={household.id}
                      existingNames={new Set(list.map((s) => s.name))}
                      pending={createScenario.isPending}
                      onCreate={(payloads) => {
                        for (const p of payloads) createScenario.mutate(p);
                      }}
                    />
                  )}
                </section>

                <section aria-labelledby="allocation-heading">
                  <h2
                    id="allocation-heading"
                    className="text-ink-navy/70 dark:text-paper/60 text-sm tracking-wide uppercase"
                  >
                    {t("plan.scenarios.allocation.heading")}
                  </h2>
                  {household && (
                    <AllocationForm
                      householdId={household.id}
                      existingNames={new Set(list.map((s) => s.name))}
                      pending={createScenario.isPending}
                      onCreate={(payloads) => {
                        for (const p of payloads) createScenario.mutate(p);
                      }}
                    />
                  )}
                </section>

                <section aria-labelledby="aflossen-heading">
                  <h2
                    id="aflossen-heading"
                    className="text-ink-navy/70 dark:text-paper/60 text-sm tracking-wide uppercase"
                  >
                    {t("plan.scenarios.aflossen.heading")}
                  </h2>
                  {household && (
                    <AflossenVsBeleggenForm
                      householdId={household.id}
                      existingNames={new Set(list.map((s) => s.name))}
                      pending={createScenario.isPending}
                      onCreate={(payloads) => {
                        for (const p of payloads) createScenario.mutate(p);
                      }}
                    />
                  )}
                </section>

                <section aria-labelledby="income-shock-heading">
                  <h2
                    id="income-shock-heading"
                    className="text-ink-navy/70 dark:text-paper/60 text-sm tracking-wide uppercase"
                  >
                    {t("plan.scenarios.incomeShock.heading")}
                  </h2>
                  {household && (
                    <IncomeShockForm
                      householdId={household.id}
                      existingNames={new Set(list.map((s) => s.name))}
                      pending={createScenario.isPending}
                      onCreate={(payloads) => {
                        for (const p of payloads) createScenario.mutate(p);
                      }}
                    />
                  )}
                </section>

                <section aria-labelledby="smile-heading">
                  <h2
                    id="smile-heading"
                    className="text-ink-navy/70 dark:text-paper/60 text-sm tracking-wide uppercase"
                  >
                    {t("plan.scenarios.smile.heading")}
                  </h2>
                  {household && (
                    <RetirementSmileForm
                      householdId={household.id}
                      existingNames={new Set(list.map((s) => s.name))}
                      pending={createScenario.isPending}
                      onCreate={(payload) => createScenario.mutate(payload)}
                    />
                  )}
                </section>
              </div>
            ),
          },
        ]}
      />
    </div>
  );
}
