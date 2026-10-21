/** "When can I stop?" — the early-retirement solver, both directions.
 *
 * Mode 1 bisects the retirement date against a success target; mode 2 names the date and
 * reports the odds. Behind an explicit Run button: this is the most expensive thing in
 * the app, a bisection over thousands of Monte Carlo paths.
 *
 * The readout deliberately shows the solved date *and* the 4%-rule FI date. They answer
 * different questions and usually disagree; showing one while the user assumes the other
 * would be worse than showing neither. */
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useCashFlows, usePeople, useRetirement } from "../../lib/api";
import { type ResidualUnit, residualMonthly } from "../../lib/baristaResidual";
import { useT } from "../../lib/i18n";
import { formatPercent } from "../../lib/money";
import type { usePlanState } from "../../lib/usePlanState";

const UNITS: ResidualUnit[] = ["eur", "pct_salary", "pct_expenses"];

/** First of the month, ten years out — a date far enough away to be a real question. */
function defaultRetireMonth(): string {
  const now = new Date();
  return `${now.getFullYear() + 10}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

const FIELD_CLS =
  "border-input mt-1 w-32 rounded border bg-transparent px-2 py-1 text-sm tabular-nums";
const LABEL_CLS = "text-ink-navy/70 dark:text-paper/60 block text-xs tracking-wide uppercase";

export function EarlyRetirementPanel({ plan }: { plan: ReturnType<typeof usePlanState> }) {
  const t = useT();
  const people = usePeople();
  const cashFlows = useCashFlows();
  const mutation = useRetirement();

  const [chosen, setChosen] = useState<number[]>([]);
  const [residual, setResidual] = useState("0");
  const [unit, setUnit] = useState<ResidualUnit>("eur");
  const [solveMode, setSolveMode] = useState(true);
  const [target, setTarget] = useState("85");
  const [atMonth, setAtMonth] = useState(defaultRetireMonth);

  const flows = cashFlows.data ?? [];
  const roster = people.data ?? [];
  // Default to everyone once the roster arrives, so the common case is one click.
  const selected = chosen.length > 0 ? chosen : roster.map((p) => p.id);

  const salary = flows
    .filter((f) => f.kind === "income" && selected.includes(f.owner_person_id ?? -1))
    .reduce((sum, f) => sum + Number(f.amount_monthly), 0);
  const expenses = flows
    .filter((f) => f.kind === "expense")
    .reduce((sum, f) => sum + Number(f.amount_monthly), 0);

  if (!people.isLoading && roster.length === 0) {
    return (
      <p className="text-ink-navy/70 dark:text-paper/60 text-sm">{t("plan.retire.noPeople")}</p>
    );
  }

  function toggle(id: number) {
    setChosen((prev) => {
      const base = prev.length > 0 ? prev : roster.map((p) => p.id);
      return base.includes(id) ? base.filter((x) => x !== id) : [...base, id];
    });
  }

  function run() {
    const amount = residualMonthly(Number(residual) || 0, unit, { salary, expenses });
    // The live assumption sliders and any tax edits ride along, exactly as SolvePanel
    // does: a retirement date computed against assumptions the user is not looking at
    // would answer the wrong question.
    mutation.mutate({
      ...plan.analysisBase,
      person_ids: selected,
      residual_monthly: amount.toFixed(2),
      ...(solveMode
        ? { probability: Math.min(100, Math.max(1, Number(target) || 85)) / 100 }
        : { at_date: `${atMonth}-01` }),
      n_runs: 1000,
    });
  }

  // Without an owner on the salary there is nothing to retire, and the solver would
  // return an unhelpful "no date works" — the metric is flat, so nothing brackets.
  // Say what is actually wrong instead of running a doomed bisection.
  const noOwnedIncome = !cashFlows.isLoading && flows.length > 0 && salary === 0;

  const result = mutation.data;
  const targetPct = formatPercent((Number(target) || 85) / 100);

  return (
    <div className="space-y-6 p-4 sm:p-8">
      <h2 className="text-ink-navy/70 dark:text-paper/60 text-sm tracking-wide uppercase">
        {t("plan.retire.heading")}
      </h2>

      {noOwnedIncome && (
        <p className="text-brick max-w-prose text-sm">{t("plan.retire.noOwnedIncome")}</p>
      )}

      {mutation.isError && (
        <p role="alert" className="text-brick text-sm">
          {t("plan.retire.error")} {(mutation.error as Error).message}
        </p>
      )}

      {result ? (
        <section className="max-w-prose space-y-2">
          {result.converged && result.retire_date ? (
            <>
              <p className="text-lg">
                {t("plan.retire.result")
                  .replace("{date}", result.retire_date.slice(0, 7))
                  .replace("{pct}", formatPercent(result.achieved ?? 0))}
              </p>
              <p className="text-ink-navy/70 dark:text-paper/60 text-sm">
                {result.fi_date
                  ? t("plan.retire.compare").replace("{fi}", result.fi_date.slice(0, 7))
                  : t("plan.retire.noFi")}
              </p>
            </>
          ) : (
            <p className="text-lg">{t("plan.retire.noConverge").replace("{pct}", targetPct)}</p>
          )}
        </section>
      ) : (
        !mutation.isPending && (
          <p className="text-ink-navy/70 dark:text-paper/60 max-w-prose text-sm">
            {t("plan.retire.idle")}
          </p>
        )
      )}

      <div className="flex flex-wrap items-end gap-6">
        <fieldset>
          <legend className={LABEL_CLS}>{t("plan.retire.who")}</legend>
          <div className="mt-1 flex flex-wrap items-center gap-4 text-sm">
            {roster.map((p) => (
              <label key={p.id} className="flex items-center gap-1 py-2">
                <input
                  type="checkbox"
                  checked={selected.includes(p.id)}
                  onChange={() => toggle(p.id)}
                />{" "}
                {p.name}
              </label>
            ))}
          </div>
        </fieldset>

        <div>
          <label htmlFor="retire-residual" className={LABEL_CLS}>
            {t("plan.retire.residual")}
          </label>
          <div className="mt-1 flex items-center gap-2">
            <input
              id="retire-residual"
              type="number"
              step="50"
              value={residual}
              onChange={(e) => setResidual(e.target.value)}
              className={`${FIELD_CLS} mt-0 w-24`}
            />
            <select
              value={unit}
              onChange={(e) => setUnit(e.target.value as ResidualUnit)}
              aria-label={t("plan.retire.residual")}
              className="border-input rounded border bg-transparent px-2 py-1 text-sm"
            >
              {UNITS.map((u) => (
                <option key={u} value={u}>
                  {t(`plan.retire.unit.${u}` as "plan.retire.unit.eur")}
                </option>
              ))}
            </select>
          </div>
        </div>

        <fieldset>
          <legend className={LABEL_CLS}>{t("plan.retire.mode")}</legend>
          <div className="mt-1 flex flex-wrap items-center gap-4 text-sm">
            <label className="flex items-center gap-1 py-2">
              <input
                type="radio"
                name="retire-mode"
                checked={solveMode}
                onChange={() => setSolveMode(true)}
              />{" "}
              {t("plan.retire.mode.solve")}
            </label>
            <label className="flex items-center gap-1 py-2">
              <input
                type="radio"
                name="retire-mode"
                checked={!solveMode}
                onChange={() => setSolveMode(false)}
              />{" "}
              {t("plan.retire.mode.test")}
            </label>
          </div>
        </fieldset>

        {solveMode ? (
          <div>
            <label htmlFor="retire-target" className={LABEL_CLS}>
              {t("plan.retire.target")}
            </label>
            <input
              id="retire-target"
              type="number"
              step="5"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              className={FIELD_CLS}
            />
          </div>
        ) : (
          <div>
            <label htmlFor="retire-at" className={LABEL_CLS}>
              {t("plan.retire.atDate")}
            </label>
            <input
              id="retire-at"
              type="month"
              value={atMonth}
              onChange={(e) => setAtMonth(e.target.value)}
              className={`${FIELD_CLS} w-auto`}
            />
          </div>
        )}

        <Button
          type="button"
          onClick={run}
          disabled={mutation.isPending || selected.length === 0 || noOwnedIncome}
          variant="emphasis"
        >
          {mutation.isPending ? t("plan.retire.running") : t("plan.retire.run")}
        </Button>
      </div>
    </div>
  );
}
