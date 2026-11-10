/** The rent-vs-buy template form: pick which expense flow
 * is the rent, give price/mortgage/rate, get the four seed scenarios. The Vienna
 * fork stays a disabled affordance until a second tax regime exists. */
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { type ScenarioCreate, useCashFlows } from "../../lib/api";
import { monthsFromNow } from "../../lib/dates";
import { useT } from "../../lib/i18n";
import { rentVsBuyScenarios } from "../../lib/scenarioCompare";
import { LabelledInput, LabelledSelect } from "./templateForm";

/** First of the month, one year out — a sensible default purchase month. */
function defaultBuyMonth(): string {
  return monthsFromNow(12);
}

export function RentVsBuyForm({
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

  const [rentFlowId, setRentFlowId] = useState<number | undefined>(undefined);
  const [nicerRent, setNicerRent] = useState("");
  const [buyMonth, setBuyMonth] = useState(defaultBuyMonth);
  const [priceA, setPriceA] = useState("360000");
  const [priceB, setPriceB] = useState("500000");
  const [mortgageA, setMortgageA] = useState("340000");
  const [ratePct, setRatePct] = useState("4.2");

  const rentFlow = expenses.find((f) => f.id === rentFlowId) ?? expenses[0];

  if (!cashFlows.isLoading && expenses.length === 0) {
    return (
      <p className="text-ink-navy/70 dark:text-paper/60 mt-3 text-sm">
        {t("plan.scenarios.rentVsBuy.noExpenseFlow")}
      </p>
    );
  }
  if (!rentFlow) return null;

  const rentAmount = Math.round(Number(rentFlow.amount_monthly));

  function submit() {
    if (!rentFlow) return;
    const payloads = rentVsBuyScenarios({
      householdId,
      rentFlowId: rentFlow.id,
      rentAmount,
      nicerRentAmount: Math.round(Number(nicerRent) || rentAmount + 500),
      buyDate: `${buyMonth}-01`,
      priceA: Number(priceA),
      priceB: Number(priceB),
      mortgageA: Number(mortgageA),
      annualRate: Number(ratePct) / 100,
    });
    onCreate(payloads.filter((p) => !existingNames.has(p.name)));
  }

  return (
    <div className="mt-3 flex flex-wrap items-end gap-4">
      <LabelledSelect
        id="rvb-rent"
        label={t("plan.scenarios.rentVsBuy.rentFlowLabel")}
        value={rentFlow.id}
        onChange={(e) => setRentFlowId(Number(e.target.value))}
      >
        {expenses.map((f) => (
          <option key={f.id} value={f.id}>
            {f.label ||
              t("plan.scenarios.rentVsBuy.cashFlowFallback").replace("{id}", String(f.id))}{" "}
            (€{Math.round(Number(f.amount_monthly))})
          </option>
        ))}
      </LabelledSelect>
      <LabelledInput
        id="rvb-nicer"
        label={t("plan.scenarios.rentVsBuy.nicerRentLabel")}
        type="number"
        value={nicerRent}
        placeholder={String(rentAmount + 500)}
        onChange={(e) => setNicerRent(e.target.value)}
      />
      <LabelledInput
        id="rvb-month"
        label={t("plan.scenarios.rentVsBuy.buyMonthLabel")}
        type="month"
        value={buyMonth}
        onChange={(e) => setBuyMonth(e.target.value)}
      />
      <LabelledInput
        id="rvb-price-a"
        label={t("plan.scenarios.rentVsBuy.priceALabel")}
        type="number"
        value={priceA}
        onChange={(e) => setPriceA(e.target.value)}
      />
      <LabelledInput
        id="rvb-mortgage"
        label={t("plan.scenarios.rentVsBuy.mortgageALabel")}
        type="number"
        value={mortgageA}
        onChange={(e) => setMortgageA(e.target.value)}
      />
      <LabelledInput
        id="rvb-price-b"
        label={t("plan.scenarios.rentVsBuy.priceBLabel")}
        type="number"
        value={priceB}
        onChange={(e) => setPriceB(e.target.value)}
      />
      <LabelledInput
        id="rvb-rate"
        label={t("plan.scenarios.rentVsBuy.rateLabel")}
        type="number"
        step="0.1"
        value={ratePct}
        onChange={(e) => setRatePct(e.target.value)}
      />
      <Button type="button" onClick={submit} disabled={pending} variant="emphasis">
        {t("plan.scenarios.rentVsBuy.addButton")}
      </Button>
      <Button
        type="button"
        disabled
        title={t("plan.scenarios.rentVsBuy.viennaTitle")}
        className="border-ink-navy/20 dark:border-paper/20 text-ink-navy/40 dark:text-paper/40 cursor-not-allowed rounded border border-dashed px-3 py-1 text-sm"
      >
        {t("plan.scenarios.rentVsBuy.viennaButton")}
      </Button>
    </div>
  );
}
