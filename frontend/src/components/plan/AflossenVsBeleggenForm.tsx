/** Aflossen vs beleggen — the Dutch household question, as two scenarios.
 *
 * Extra euros into the mortgage, or the same euros into the portfolio, from the same
 * month. The engine side is an `extra_repayment` milestone against a
 * `contribution_change` one; this form only has to ask which contribution flow is the
 * investing one and how much is under debate. */
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useCashFlows, useMilestones } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { aflossenVsBeleggenScenarios } from "../../lib/scenarioCompare";

/** First of next month — this is a decision people make now, not in a decade. */
function defaultStartMonth(): string {
  const now = new Date();
  const m = now.getMonth() + 2;
  const y = now.getFullYear() + (m > 12 ? 1 : 0);
  return `${y}-${String(m > 12 ? m - 12 : m).padStart(2, "0")}`;
}

const FIELD_CLS =
  "border-input mt-1 w-32 rounded border bg-transparent px-2 py-1 text-sm tabular-nums";
const LABEL_CLS = "text-ink-navy/70 dark:text-paper/60 block text-xs tracking-wide uppercase";

export function AflossenVsBeleggenForm({
  householdId,
  existingNames,
  onCreate,
  pending,
}: {
  householdId: number;
  existingNames: Set<string>;
  onCreate: (payloads: ReturnType<typeof aflossenVsBeleggenScenarios>) => void;
  pending: boolean;
}) {
  const t = useT();
  const cashFlows = useCashFlows();
  const milestones = useMilestones();
  const contributions = (cashFlows.data ?? []).filter((f) => f.kind === "contribution");
  const buysAHouse = (milestones.data ?? []).some((m) => m.params.type === "buy_property");

  const [flowId, setFlowId] = useState<number | undefined>(undefined);
  const [extra, setExtra] = useState("500");
  const [startMonth, setStartMonth] = useState(defaultStartMonth);

  const flow = contributions.find((f) => f.id === flowId) ?? contributions[0];

  // Both arms need somewhere for the beleggen euros to go. Without a contribution flow
  // there is no symmetric comparison to draw, so say that instead of half-drawing one.
  if (!cashFlows.isLoading && contributions.length === 0) {
    return (
      <p className="text-ink-navy/70 dark:text-paper/60 mt-3 text-sm">
        {t("plan.scenarios.aflossen.noContributionFlow")}
      </p>
    );
  }
  // Without a mortgage the aflossen arm is silently inert, and the comparison would
  // read as "beleggen wins" when the truth is that there is nothing to repay. Refuse
  // rather than draw a rigged chart.
  if (!milestones.isLoading && !buysAHouse) {
    return (
      <p className="text-ink-navy/70 dark:text-paper/60 mt-3 text-sm">
        {t("plan.scenarios.aflossen.noMortgage")}
      </p>
    );
  }
  if (!flow) return null;

  const contributionMonthly = Math.round(Number(flow.amount_monthly));

  function submit() {
    if (!flow) return;
    const payloads = aflossenVsBeleggenScenarios({
      householdId,
      contributionFlowId: flow.id,
      contributionMonthly,
      extraMonthly: Math.max(0, Math.round(Number(extra) || 0)),
      startDate: `${startMonth}-01`,
    });
    onCreate(payloads.filter((p) => !existingNames.has(p.name)));
  }

  return (
    <div className="mt-3 flex flex-wrap items-end gap-4">
      <div>
        <label htmlFor="avb-extra" className={LABEL_CLS}>
          {t("plan.scenarios.aflossen.extraLabel")}
        </label>
        <input
          id="avb-extra"
          type="number"
          step="50"
          value={extra}
          onChange={(e) => setExtra(e.target.value)}
          className={FIELD_CLS}
        />
      </div>

      <div>
        <label htmlFor="avb-flow" className={LABEL_CLS}>
          {t("plan.scenarios.aflossen.flowLabel")}
        </label>
        <select
          id="avb-flow"
          value={flow.id}
          onChange={(e) => setFlowId(Number(e.target.value))}
          className={`${FIELD_CLS} w-auto`}
        >
          {contributions.map((f) => (
            <option key={f.id} value={f.id}>
              {f.label || `#${f.id}`} (€{Math.round(Number(f.amount_monthly))})
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="avb-start" className={LABEL_CLS}>
          {t("plan.scenarios.aflossen.startLabel")}
        </label>
        <input
          id="avb-start"
          type="month"
          value={startMonth}
          onChange={(e) => setStartMonth(e.target.value)}
          className={`${FIELD_CLS} w-auto`}
        />
      </div>

      <Button type="button" onClick={submit} disabled={pending} variant="emphasis">
        {t("plan.scenarios.aflossen.addButton")}
      </Button>

      <p className="text-ink-navy/70 dark:text-paper/50 w-full max-w-prose text-xs">
        {t("plan.scenarios.aflossen.hint")}
      </p>
    </div>
  );
}
