/** The retirement-smile template: real spending
 * drifts down through the active retirement years, then flattens. Expressible with
 * expense-change milestones already — this form is the one click. */
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useCashFlows } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { retirementSmileScenario } from "../../lib/scenarioCompare";

/** First of the month, fifteen years out — the smile starts at retirement, which for
 * most households on this board is well after the next birthday. */
function defaultStartMonth(): string {
  const now = new Date();
  return `${now.getFullYear() + 15}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

const FIELD_CLS =
  "border-input mt-1 w-32 rounded border bg-transparent px-2 py-1 text-sm tabular-nums";
const LABEL_CLS = "text-ink-navy/70 dark:text-paper/60 block text-xs tracking-wide uppercase";

export function RetirementSmileForm({
  householdId,
  existingNames,
  onCreate,
  pending,
}: {
  householdId: number;
  existingNames: Set<string>;
  onCreate: (payload: ReturnType<typeof retirementSmileScenario>) => void;
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
    if (!existingNames.has(payload.name)) onCreate(payload);
  }

  return (
    <div className="mt-3 flex flex-wrap items-end gap-4">
      <div>
        <label htmlFor="smile-flow" className={LABEL_CLS}>
          {t("plan.scenarios.smile.flowLabel")}
        </label>
        <select
          id="smile-flow"
          value={expenseFlow.id}
          onChange={(e) => setExpenseFlowId(Number(e.target.value))}
          className={`${FIELD_CLS} w-auto`}
        >
          {expenses.map((f) => (
            <option key={f.id} value={f.id}>
              {f.label || `#${f.id}`} (€{Math.round(Number(f.amount_monthly))})
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="smile-start" className={LABEL_CLS}>
          {t("plan.scenarios.smile.startLabel")}
        </label>
        <input
          id="smile-start"
          type="month"
          value={startMonth}
          onChange={(e) => setStartMonth(e.target.value)}
          className={`${FIELD_CLS} w-auto`}
        />
      </div>

      <div>
        <label htmlFor="smile-rate" className={LABEL_CLS}>
          {t("plan.scenarios.smile.rateLabel")}
        </label>
        <input
          id="smile-rate"
          type="number"
          step="0.5"
          value={declinePct}
          onChange={(e) => setDeclinePct(e.target.value)}
          className={FIELD_CLS}
        />
      </div>

      <div>
        <label htmlFor="smile-years" className={LABEL_CLS}>
          {t("plan.scenarios.smile.yearsLabel")}
        </label>
        <input
          id="smile-years"
          type="number"
          step="1"
          value={years}
          onChange={(e) => setYears(e.target.value)}
          className={FIELD_CLS}
        />
      </div>

      <Button type="button" onClick={submit} disabled={pending} variant="emphasis">
        {t("plan.scenarios.smile.addButton")}
      </Button>

      <p className="text-ink-navy/70 dark:text-paper/50 w-full max-w-prose text-xs">
        {t("plan.scenarios.smile.hint")}
      </p>
    </div>
  );
}
