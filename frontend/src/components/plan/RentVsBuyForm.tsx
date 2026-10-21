/** The rent-vs-buy template form: pick which expense flow
 * is the rent, give price/mortgage/rate, get the four seed scenarios. The Vienna
 * fork stays a disabled affordance until a second tax regime exists. */
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useCashFlows } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { rentVsBuyScenarios } from "../../lib/scenarioCompare";

/** First of the month, one year out — a sensible default purchase month. */
function defaultBuyMonth(): string {
  const now = new Date();
  return `${now.getFullYear() + 1}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

const FIELD_CLS =
  "border-input mt-1 w-32 rounded border bg-transparent px-2 py-1 text-sm tabular-nums";
const LABEL_CLS = "text-ink-navy/70 dark:text-paper/60 block text-xs tracking-wide uppercase";

export function RentVsBuyForm({
  householdId,
  existingNames,
  onCreate,
  pending,
}: {
  householdId: number;
  existingNames: Set<string>;
  onCreate: (payloads: ReturnType<typeof rentVsBuyScenarios>) => void;
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
      <div>
        <label htmlFor="rvb-rent" className={LABEL_CLS}>
          {t("plan.scenarios.rentVsBuy.rentFlowLabel")}
        </label>
        <select
          id="rvb-rent"
          value={rentFlow.id}
          onChange={(e) => setRentFlowId(Number(e.target.value))}
          className={`${FIELD_CLS} w-auto`}
        >
          {expenses.map((f) => (
            <option key={f.id} value={f.id}>
              {f.label ||
                t("plan.scenarios.rentVsBuy.cashFlowFallback").replace("{id}", String(f.id))}{" "}
              (€{Math.round(Number(f.amount_monthly))})
            </option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor="rvb-nicer" className={LABEL_CLS}>
          {t("plan.scenarios.rentVsBuy.nicerRentLabel")}
        </label>
        <input
          id="rvb-nicer"
          type="number"
          value={nicerRent}
          placeholder={String(rentAmount + 500)}
          onChange={(e) => setNicerRent(e.target.value)}
          className={FIELD_CLS}
        />
      </div>
      <div>
        <label htmlFor="rvb-month" className={LABEL_CLS}>
          {t("plan.scenarios.rentVsBuy.buyMonthLabel")}
        </label>
        <input
          id="rvb-month"
          type="month"
          value={buyMonth}
          onChange={(e) => setBuyMonth(e.target.value)}
          className={`${FIELD_CLS} w-auto`}
        />
      </div>
      <div>
        <label htmlFor="rvb-price-a" className={LABEL_CLS}>
          {t("plan.scenarios.rentVsBuy.priceALabel")}
        </label>
        <input
          id="rvb-price-a"
          type="number"
          value={priceA}
          onChange={(e) => setPriceA(e.target.value)}
          className={FIELD_CLS}
        />
      </div>
      <div>
        <label htmlFor="rvb-mortgage" className={LABEL_CLS}>
          {t("plan.scenarios.rentVsBuy.mortgageALabel")}
        </label>
        <input
          id="rvb-mortgage"
          type="number"
          value={mortgageA}
          onChange={(e) => setMortgageA(e.target.value)}
          className={FIELD_CLS}
        />
      </div>
      <div>
        <label htmlFor="rvb-price-b" className={LABEL_CLS}>
          {t("plan.scenarios.rentVsBuy.priceBLabel")}
        </label>
        <input
          id="rvb-price-b"
          type="number"
          value={priceB}
          onChange={(e) => setPriceB(e.target.value)}
          className={FIELD_CLS}
        />
      </div>
      <div>
        <label htmlFor="rvb-rate" className={LABEL_CLS}>
          {t("plan.scenarios.rentVsBuy.rateLabel")}
        </label>
        <input
          id="rvb-rate"
          type="number"
          step="0.1"
          value={ratePct}
          onChange={(e) => setRatePct(e.target.value)}
          className={FIELD_CLS}
        />
      </div>
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
