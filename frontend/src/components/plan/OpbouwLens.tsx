/** The Opbouw (composition) lens: THE BEAM chart plus the milestone detail panel. Its
 * headline lives in the strip. */
import { useEffect, useMemo, useState } from "react";
import { TimelineChart, type TimelineMarker } from "../../components/TimelineChart";
import {
  type Account,
  type CashFlow,
  type Milestone,
  type Person,
  type PlanRequestBody,
  useAccounts,
  useCashFlows,
  useHouseholds,
  useMilestones,
  usePeople,
  useProjection,
  useProjectionBands,
  useSensitivity,
} from "../../lib/api";
import { BEAM, SERIES } from "../../lib/chartColors";
import { parseApiError } from "../../lib/fieldErrors";
import { type MsgKey, useLocale, useT } from "../../lib/i18n";
import { formatEuros, formatMoney } from "../../lib/money";
import { toReal } from "../../lib/realTerms";
import { dateToMonthIndex, milestoneDate, yearTicks } from "../../lib/timeline";
import type { usePlanState } from "../../lib/usePlanState";
import { treatmentLabel } from "../editor/AccountDrawer";
import { CrossoverPanel } from "./CrossoverPanel";
import { CsvButton } from "./CsvButton";
import { CumulativeTaxPanel } from "./CumulativeTaxPanel";
import { Deck } from "./Deck";
import { EarlyRetirementPanel } from "./EarlyRetirementPanel";
import { formatMonth, type HeadlineSlot } from "./HeadlineStrip";
import { SensitivityPanel } from "./SensitivityPanel";
import { SolvePanel } from "./SolvePanel";

const MONEY_KEYS = new Set([
  "price",
  "mortgage",
  "amount",
  "costs",
  "vve_monthly",
  "new_amount_monthly",
  "gift_used",
]);

// Projected figures: whole euros only — cents on a 2085 median are noise dressed as
// precision (money.ts documents the rule). Milestone params keep formatMoney: those are
// stored amounts, not projections.
const eur = (euros: number) => formatEuros(euros);

type ParamKey = Exclude<
  Milestone["params"] extends infer P ? (P extends unknown ? keyof P : never) : never,
  "type"
>;

// The editor drawer's field label for each stored param key, so the detail panel uses
// the same words. A param added to the API without an entry here fails the type check.
const PARAM_LABEL: Record<ParamKey, MsgKey> = {
  person_id: "editor.milestone.person",
  amount: "editor.milestone.amount",
  target_account_id: "editor.milestone.targetAccount",
  is_gift_exemption: "editor.milestone.giftExemption",
  price: "editor.milestone.price",
  mortgage: "editor.milestone.mortgage",
  annual_rate: "editor.milestone.annualRate",
  term_months: "editor.milestone.termMonths",
  vve_monthly: "editor.milestone.vveMonthly",
  buyer_person_id: "editor.milestone.buyer",
  gift_used: "editor.milestone.giftUsed",
  own_occupancy: "editor.milestone.ownOccupancy",
  costs: "editor.milestone.sellCosts",
  monthly_amount: "editor.milestone.extraRepayment",
  cash_flow_id: "editor.milestone.cashFlow",
  new_amount_monthly: "editor.milestone.newAmount",
  country: "editor.milestone.country",
  retag: "editor.milestone.retag",
};

const ID_KEYS = {
  person_id: "people",
  buyer_person_id: "people",
  target_account_id: "accounts",
  cash_flow_id: "cashFlows",
} as const;

/** The names a milestone's ids point at; an id with no entry shows as the number. */
interface ParamNames {
  people?: readonly Pick<Person, "id" | "name">[];
  accounts?: readonly Pick<Account, "id" | "name">[];
  cashFlows?: readonly Pick<CashFlow, "id" | "label">[];
}

function paramRows(
  m: Milestone,
  t: (key: MsgKey) => string,
  names: ParamNames,
): [string, string[]][] {
  const nameOf = (list: keyof ParamNames, id: unknown) => {
    const hit = names[list]?.find((e) => e.id === Number(id));
    return hit ? ("name" in hit ? hit.name : hit.label) : String(id);
  };
  return Object.entries(m.params)
    .filter(([k]) => k !== "type")
    .map(([k, v]) => {
      let lines: string[];
      if (k === "retag" && typeof v === "object" && v !== null) {
        lines = Object.entries(v).map(
          ([id, treatment]) =>
            `${nameOf("accounts", id)} → ${treatmentLabel(String(treatment), t)}`,
        );
      } else if (k in ID_KEYS) {
        lines = [nameOf(ID_KEYS[k as keyof typeof ID_KEYS], v)];
      } else if (typeof v === "boolean") {
        lines = [t(v ? "common.yes" : "common.no")];
      } else if (MONEY_KEYS.has(k) && (typeof v === "string" || typeof v === "number")) {
        lines = [formatMoney(String(v))];
      } else {
        lines = [String(v)];
      }
      return [t(PARAM_LABEL[k as ParamKey]), lines];
    });
}

/** The milestone detail panel's parameter list. */
export function MilestoneParams({ milestone, ...names }: { milestone: Milestone } & ParamNames) {
  const t = useT();
  return (
    <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
      {paramRows(milestone, t, names).map(([k, lines]) => (
        <div key={k} className="contents">
          <dt className="text-ink-navy/70 dark:text-paper/60">{k}</dt>
          <dd className="text-right tabular-nums">
            {lines.map((line) => (
              <span key={line} className="block">
                {line}
              </span>
            ))}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** The sentence under the Composition chart. It quotes what the chart draws: the
 * solid line is the fixed-return path, so `{end}` is that path's last value. */
export function compositionCaption(
  template: string,
  v: {
    netWorth: number[];
    band: { p10: number[]; p50: number[]; p90: number[] };
    endYear: number;
    runs: number;
    pct: number;
  },
): string {
  return template
    .replace("{today}", eur(v.netWorth[0]))
    .replace("{end}", eur(v.netWorth[v.netWorth.length - 1]))
    .replace("{median}", eur(v.band.p50[v.band.p50.length - 1]))
    .replace("{year}", String(v.endYear))
    .replace("{p10}", eur(v.band.p10[v.band.p10.length - 1]))
    .replace("{p90}", eur(v.band.p90[v.band.p90.length - 1]))
    .replace("{runs}", String(v.runs))
    .replace("{pct}", String(v.pct));
}

// No beam entry: the cone is the Uncertainty lens's subject now, and drawing it here
// scaled the y axis to €5.0M against a €1.3M stack — home equity and pension had no
// height left. The caption still quotes p10/p50/p90, which is where the range belongs
// on a chart named "Composition".
const LEGEND = [
  {
    key: "liquid_investments",
    msgKey: "plan.opbouw.legend.investments",
    color: SERIES.investments,
  },
  { key: "cash", msgKey: "plan.opbouw.legend.cash", color: SERIES.cash },
  { key: "home_equity", msgKey: "plan.opbouw.legend.homeEquity", color: SERIES.homeEquity },
  { key: "pension", msgKey: "plan.opbouw.legend.pension", color: SERIES.pension },
] as const;

/** The stacked series worth a legend entry: one that is zero all the way (home equity
 * with no house) draws nothing, so naming it only sends the reader looking for it. */
export function compositionLegend(components: Record<string, number[]>) {
  return LEGEND.filter((l) => components[l.key]?.some((v) => v !== 0));
}

/** Owns the sensitivity query so it runs only while its tab is open: radix unmounts an
 * inactive tab's content, and the tornado costs nine projections per settled edit. */
function SensitivityTab({ request }: { request: PlanRequestBody }) {
  const sensitivity = useSensitivity(request);
  return <SensitivityPanel data={sensitivity.data} />;
}

export function OpbouwLens({
  plan,
  setSlot,
}: {
  plan: ReturnType<typeof usePlanState>;
  setSlot: (s: HeadlineSlot) => void;
}) {
  const t = useT();
  const [locale] = useLocale();
  const households = useHouseholds();
  const people = usePeople();
  const accounts = useAccounts();
  const cashFlows = useCashFlows();
  const milestones = useMilestones();
  const projection = useProjection(plan.deferredRequest);
  const bands = useProjectionBands(plan.deferredRequest);

  const [selectedId, setSelectedId] = useState<number | null>(null);

  const household = households.data?.[0];
  const primaryBirth = people.data?.[0]?.birth_date ?? null;

  const fire = projection.data?.fire;
  // biome-ignore lint/correctness/useExhaustiveDependencies: t is stable per locale, so locale substitutes for it in deps
  useEffect(() => {
    setSlot({
      label: t("plan.headline.coast"),
      value: fire ? formatMonth(fire.coast_fire_dates[0], t("plan.notReached"), locale) : "—",
    });
  }, [fire, locale]);

  const birthByPerson = useMemo(
    () => new Map((people.data ?? []).map((p) => [p.id, p.birth_date] as const)),
    [people.data],
  );

  const months = projection.data?.months ?? [];

  const resolved = useMemo(
    () =>
      (milestones.data ?? [])
        .filter((m) => m.household_id === household?.id)
        .map((m) => {
          const date = milestoneDate(m, birthByPerson);
          const idx = date ? dateToMonthIndex(date, months) : null;
          return idx == null || date == null ? null : { milestone: m, date, monthIndex: idx };
        })
        .filter((r): r is NonNullable<typeof r> => r !== null),
    [milestones.data, household, birthByPerson, months],
  );

  const markers: TimelineMarker[] = resolved.map((r) => ({
    id: r.milestone.id,
    label: r.milestone.label || t(`plan.milestones.type.${r.milestone.params.type}`),
    monthIndex: r.monthIndex,
    type: r.milestone.params.type,
  }));

  const ticks = useMemo(() => yearTicks(months, primaryBirth), [months, primaryBirth]);

  const LINES = [
    { label: t("plan.opbouw.legend.fixed"), color: "var(--foreground)", dash: undefined },
    { label: t("plan.opbouw.legend.median"), color: BEAM.line, dash: "6 4" },
  ];

  if (households.isLoading || projection.isLoading || bands.isLoading) {
    return <p className="px-4 sm:px-8">{t("plan.opbouw.loading")}</p>;
  }

  if (projection.isError || bands.isError || !projection.data || !bands.data) {
    return (
      <div className="px-4 sm:px-8">
        {/* `.general`, not `.message`: the engine's refusals — an unelected PFIC, an
            out-of-range tax override — arrive as a 400 whose *detail* is the sentence
            worth reading, while `.message` is only "POST /api/project failed: 400". */}
        <p role="alert" className="text-brick">
          {t("plan.opbouw.error")} {parseApiError(projection.error ?? bands.error).general}
        </p>
      </div>
    );
  }

  // Real-terms toggle: deflate the net-worth line, the stacked components
  // and the p10–p90 cone by the same inflation factor, so no series on the beam is
  // nominal while another is real. Nominal is each series untouched.
  const real = plan.realTerms;
  const factor = projection.data.inflation_factor;
  const netWorth = real
    ? toReal(projection.data.net_worth[0], factor)
    : projection.data.net_worth[0];
  const components = Object.fromEntries(
    Object.entries(projection.data.components).map(([k, v]) => [
      k,
      real ? toReal(v[0], factor) : v[0],
    ]),
  );
  const nominalBand = bands.data.bands;
  const bandFactor = bands.data.inflation_factor;
  const band = real
    ? {
        p10: toReal(nominalBand.p10, bandFactor),
        p50: toReal(nominalBand.p50, bandFactor),
        p90: toReal(nominalBand.p90, bandFactor),
      }
    : nominalBand;
  const pct = Math.round(bands.data.success_probability * 100);
  const endYear = Number(months[months.length - 1].slice(0, 4));

  const caption = compositionCaption(t("plan.opbouw.caption"), {
    netWorth,
    band,
    endYear,
    runs: bands.data.n_runs,
    pct,
  });

  const selected = resolved.find((r) => r.milestone.id === selectedId) ?? null;

  const csvColumns = [
    { header: "month", values: months },
    { header: "net_worth_eur", values: netWorth.map((v) => Math.round(v)) },
    ...Object.entries(components).map(([k, v]) => ({
      header: `${k}_eur`,
      values: v.map((n) => Math.round(n)),
    })),
  ];

  return (
    <div className="space-y-6 px-4 sm:px-8">
      <div className="flex items-start justify-between gap-4">
        <p className="max-w-prose text-sm text-ink-navy/70 dark:text-paper/70">{caption}</p>
        <CsvButton filename="opbouw.csv" columns={csvColumns} />
      </div>

      <TimelineChart
        months={months}
        netWorth={netWorth}
        components={components}
        markers={markers}
        ticks={ticks}
        selectedId={selectedId}
        onSelect={(id) => {
          setSelectedId(id);
          plan.setMilestoneEditor(id);
        }}
        median={band.p50}
        caption={caption}
      />

      <ul className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink-navy/70 dark:text-paper/70">
        {compositionLegend(components).map((l) => (
          <li key={l.key} className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="inline-block h-2.5 w-2.5 rounded-sm"
              style={{ backgroundColor: l.color }}
            />
            {t(l.msgKey)}
          </li>
        ))}
        {LINES.map((l) => (
          <li key={l.label} className="flex items-center gap-1.5">
            <svg aria-hidden="true" width="18" height="4" className="overflow-visible">
              <line
                x1="0"
                x2="18"
                y1="2"
                y2="2"
                stroke={l.color}
                strokeWidth="2"
                strokeDasharray={l.dash}
              />
            </svg>
            {l.label}
          </li>
        ))}
      </ul>

      <section aria-labelledby="milestone-heading" className="max-w-md">
        <h2
          id="milestone-heading"
          className="text-sm uppercase tracking-wide text-ink-navy/70 dark:text-paper/60"
        >
          {t("plan.opbouw.milestone.heading")}
        </h2>
        {selected ? (
          <div className="mt-2 border-t border-ink-navy/10 pt-2 dark:border-paper/10">
            <div className="flex items-baseline justify-between gap-4">
              <p className="font-display text-lg">{selected.milestone.label || "—"}</p>
              <p className="text-sm tabular-nums text-ink-navy/70 dark:text-paper/70">
                {formatMonth(selected.date, "—", locale)}
              </p>
            </div>
            <p className="text-sm text-ink-navy/70 dark:text-paper/60">
              {t(`plan.milestones.type.${selected.milestone.params.type}`)}
            </p>
            <MilestoneParams
              milestone={selected.milestone}
              people={people.data}
              accounts={accounts.data}
              cashFlows={cashFlows.data}
            />
          </div>
        ) : (
          <p className="mt-2 text-sm text-ink-navy/70 dark:text-paper/60">
            {markers.length > 0
              ? t("plan.opbouw.milestone.selectPrompt")
              : t("plan.opbouw.milestone.none")}
          </p>
        )}
      </section>

      <Deck
        plan={plan}
        extra={[
          {
            value: "kruispunt",
            label: t("plan.crossover.tab"),
            content: <CrossoverPanel data={projection.data} />,
          },
          {
            value: "belasting",
            label: t("plan.cumtax.tab"),
            // Only once the household is loaded: the panel names the country's own
            // schedule ("Box 3"), and an undefined country reads as a neutral
            // "Investment tax" that is wrong rather than merely unfinished.
            content: household ? (
              <CumulativeTaxPanel
                data={projection.data}
                grossSwr={plan.swr}
                country={household.tax_country}
              />
            ) : (
              <p className="p-4 text-sm sm:p-8">{t("plan.opbouw.loading")}</p>
            ),
          },
          {
            value: "oplossen",
            label: t("plan.solve.tab"),
            content: <SolvePanel plan={plan} />,
          },
          {
            value: "eerder-stoppen",
            label: t("plan.retire.tab"),
            content: <EarlyRetirementPanel plan={plan} />,
          },
          {
            value: "gevoeligheid",
            label: t("plan.deck.sensitivity"),
            content: <SensitivityTab request={plan.deferredAnalysisBase} />,
          },
        ]}
      />
    </div>
  );
}
