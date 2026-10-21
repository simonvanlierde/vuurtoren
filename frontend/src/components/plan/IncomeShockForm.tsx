/** The income-shock template form: pick which
 * income flow takes the hit, how long it lasts, and get one scenario per life event.
 * Sabbatical, job loss and long illness share this one mechanism — they differ only in
 * how much income survives, which is why there is no WIA/AOV modelling here. */
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useCashFlows } from "../../lib/api";
import { type MsgKey, useT } from "../../lib/i18n";
import { incomeShockScenarios } from "../../lib/scenarioCompare";

/** First of the month, one year out — far enough that the shock lands on a plan the
 * user recognises rather than on this month's half-spent budget. */
function defaultStartMonth(): string {
  const now = new Date();
  return `${now.getFullYear() + 1}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

/** A life event minus its `label`, which only `t()` can supply — the scenario's name is
 * user-visible copy, so it is resolved at submit time rather than hardcoded here. */
interface PresetChoice {
  key: string;
  labelKey: MsgKey;
  fraction: number;
  months: number | null;
}

const PRESETS: PresetChoice[] = [
  {
    key: "sabbatical",
    labelKey: "plan.scenarios.incomeShock.preset.sabbatical",
    fraction: 0,
    months: 12,
  },
  {
    key: "jobLoss",
    labelKey: "plan.scenarios.incomeShock.preset.jobLoss",
    fraction: 0.7,
    months: 9,
  },
  {
    key: "disability",
    labelKey: "plan.scenarios.incomeShock.preset.disability",
    fraction: 0.7,
    months: null,
  },
];

const FIELD_CLS =
  "border-input mt-1 w-32 rounded border bg-transparent px-2 py-1 text-sm tabular-nums";
const LABEL_CLS = "text-ink-navy/70 dark:text-paper/60 block text-xs tracking-wide uppercase";

export function IncomeShockForm({
  householdId,
  existingNames,
  onCreate,
  pending,
}: {
  householdId: number;
  existingNames: Set<string>;
  onCreate: (payloads: ReturnType<typeof incomeShockScenarios>) => void;
  pending: boolean;
}) {
  const t = useT();
  const cashFlows = useCashFlows();
  const incomes = (cashFlows.data ?? []).filter((f) => f.kind === "income");

  const [incomeFlowId, setIncomeFlowId] = useState<number | undefined>(undefined);
  const [startMonth, setStartMonth] = useState(defaultStartMonth);
  const [chosen, setChosen] = useState<string[]>(PRESETS.map((p) => p.key));

  const incomeFlow = incomes.find((f) => f.id === incomeFlowId) ?? incomes[0];

  if (!cashFlows.isLoading && incomes.length === 0) {
    return (
      <p className="text-ink-navy/70 dark:text-paper/60 mt-3 text-sm">
        {t("plan.scenarios.incomeShock.noIncomeFlow")}
      </p>
    );
  }
  if (!incomeFlow) return null;

  const baselineMonthly = Math.round(Number(incomeFlow.amount_monthly));

  function submit() {
    if (!incomeFlow) return;
    // One call per preset rather than one call with all of them: `months` is per-event
    // (a sabbatical you choose, a long illness you do not), and the generator takes a
    // single duration for the whole set.
    const payloads = PRESETS.filter((p) => chosen.includes(p.key)).flatMap((p) =>
      incomeShockScenarios({
        householdId,
        incomeFlowId: incomeFlow.id,
        baselineMonthly,
        startDate: `${startMonth}-01`,
        months: p.months,
        presets: [{ key: p.key, fraction: p.fraction, label: t(p.labelKey) }],
      }),
    );
    onCreate(payloads.filter((p) => !existingNames.has(p.name)));
  }

  return (
    <div className="mt-3 flex flex-wrap items-end gap-4">
      <div>
        <label htmlFor="shock-flow" className={LABEL_CLS}>
          {t("plan.scenarios.incomeShock.flowLabel")}
        </label>
        <select
          id="shock-flow"
          value={incomeFlow.id}
          onChange={(e) => setIncomeFlowId(Number(e.target.value))}
          className={`${FIELD_CLS} w-auto`}
        >
          {incomes.map((f) => (
            <option key={f.id} value={f.id}>
              {f.label ||
                t("plan.scenarios.incomeShock.cashFlowFallback").replace("{id}", String(f.id))}{" "}
              (€{Math.round(Number(f.amount_monthly))})
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="shock-start" className={LABEL_CLS}>
          {t("plan.scenarios.incomeShock.startLabel")}
        </label>
        <input
          id="shock-start"
          type="month"
          value={startMonth}
          onChange={(e) => setStartMonth(e.target.value)}
          className={`${FIELD_CLS} w-auto`}
        />
      </div>

      <fieldset>
        <legend className={LABEL_CLS}>{t("plan.scenarios.incomeShock.eventsLabel")}</legend>
        <div className="mt-1 flex flex-wrap items-center gap-4 text-sm">
          {PRESETS.map((p) => (
            <label key={p.key} className="flex items-center gap-1 py-2">
              <input
                type="checkbox"
                checked={chosen.includes(p.key)}
                onChange={(e) =>
                  setChosen((prev) =>
                    e.target.checked ? [...prev, p.key] : prev.filter((k) => k !== p.key),
                  )
                }
              />{" "}
              {t(p.labelKey)}
            </label>
          ))}
        </div>
      </fieldset>

      <Button
        type="button"
        onClick={submit}
        disabled={pending || chosen.length === 0}
        variant="emphasis"
      >
        {t("plan.scenarios.incomeShock.addButton")}
      </Button>

      <p className="text-ink-navy/70 dark:text-paper/50 w-full max-w-prose text-xs">
        {t("plan.scenarios.incomeShock.hint").replace("{amount}", `€${baselineMonthly}`)}
      </p>
    </div>
  );
}
