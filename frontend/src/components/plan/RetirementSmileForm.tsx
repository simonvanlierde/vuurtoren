/** The retirement-smile template: real spending
 * drifts down through the active retirement years, then flattens. Expressible with
 * expense-change milestones already — this form is the one click. */
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { type ScenarioCreate, useCashFlows } from "../../lib/api";
import { monthsFromNow } from "../../lib/dates";
import { useT } from "../../lib/i18n";
import { retirementSmileScenario } from "../../lib/scenarioCompare";
import { LabelledInput, LabelledSelect } from "./templateForm";

/** First of the month, fifteen years out — the smile starts at retirement, which for
 * most households on this board is well after the next birthday. */
function defaultStartMonth(): string {
  return monthsFromNow(180);
}

export function RetirementSmileForm({
  householdId,
  existingNames,
  onCreate,
  pending,
}: {
  householdId: number;
  existingNames: Set<string>;
  onCreate: (payloads: ScenarioCreate[]) => void;
  pending: boolean;
}) {
  const t = useT();
  const cashFlows = useCashFlows();
  const expenses = (cashFlows.data ?? []).filter((f) => f.kind === "expense");

  const [expenseFlowId, setExpenseFlowId] = useState<number | undefined>(undefined);
  const [startMonth, setStartMonth] = useState(defaultStartMonth);
  const [declinePct, setDeclinePct] = useState("2");
  const [years, setYears] = useState("20");

  const expenseFlow = expenses.find((f) => f.id === expenseFlowId) ?? expenses[0];

  if (!cashFlows.isLoading && expenses.length === 0) {
    return (
      <p className="text-ink-navy/70 dark:text-paper/60 mt-3 text-sm">
        {t("plan.scenarios.smile.noExpenseFlow")}
      </p>
    );
  }
  if (!expenseFlow) return null;

  const baselineMonthly = Math.round(Number(expenseFlow.amount_monthly));

  function submit() {
    if (!expenseFlow) return;
    const payload = retirementSmileScenario({
      householdId,
      expenseFlowId: expenseFlow.id,
      baselineMonthly,
      startDate: `${startMonth}-01`,
      annualDeclinePct: Number(declinePct) || 0,
      years: Math.max(0, Math.round(Number(years) || 0)),
    });
    if (!existingNames.has(payload.name)) onCreate([payload]);
  }

  return (
    <div className="mt-3 flex flex-wrap items-end gap-4">
      <LabelledSelect
        id="smile-flow"
        label={t("plan.scenarios.smile.flowLabel")}
        value={expenseFlow.id}
        onChange={(e) => setExpenseFlowId(Number(e.target.value))}
      >
        {expenses.map((f) => (
          <option key={f.id} value={f.id}>
            {f.label || `#${f.id}`} (€{Math.round(Number(f.amount_monthly))})
          </option>
        ))}
      </LabelledSelect>

      <LabelledInput
        id="smile-start"
        label={t("plan.scenarios.smile.startLabel")}
        type="month"
        value={startMonth}
        onChange={(e) => setStartMonth(e.target.value)}
      />

      <LabelledInput
        id="smile-rate"
        label={t("plan.scenarios.smile.rateLabel")}
        type="number"
        step="0.5"
        value={declinePct}
        onChange={(e) => setDeclinePct(e.target.value)}
      />

      <LabelledInput
        id="smile-years"
        label={t("plan.scenarios.smile.yearsLabel")}
        type="number"
        step="1"
        value={years}
        onChange={(e) => setYears(e.target.value)}
      />

      <Button type="button" onClick={submit} disabled={pending} variant="emphasis">
        {t("plan.scenarios.smile.addButton")}
      </Button>

      <p className="text-ink-navy/70 dark:text-paper/50 w-full max-w-prose text-xs">
        {t("plan.scenarios.smile.hint")}
      </p>
    </div>
  );
}
